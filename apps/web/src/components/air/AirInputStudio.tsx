import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { api, type CorrelationRecord, type SimulationRun } from "../../lib/api";
import {
  AIR_STATE_COLOR,
  evalSurrogate,
  isOod,
  type FieldGridPayload,
  type FingerPose,
  type ReplayPayload,
  type SurrogatePayload,
  type VolumePayload,
} from "../../lib/air";
import { AirScene } from "./AirScene";
import { AirFieldSlice } from "./AirFieldSlice";
import { AirSignalChart, AirThresholdNote } from "./AirSignalChart";
import { AirScenarioTable, AirTierPanel } from "./AirTierPanel";

// AirInput 3D Interaction Field Twin studio (지시서 ①–⑦). Component-local
// state only — no new store slice (C8); remounts per variant via the key in
// App. All numbers shown come from worker artifacts (solver / surrogate /
// replay) or the live TS surrogate eval of the pinned parity formula —
// nothing is computed here that the worker doesn't already pin.
const TOOL = {
  field: "fd-electrostatic-solver-v1",
  surrogate: "surrogate-rbf-trainer-v1",
  volume: "sensitivity-volume-v1",
  replay: "asic-algo-replay-v1",
} as const;

async function fetchArtifactJson<T>(versionId: string | null): Promise<T | null> {
  if (!versionId) return null;
  try {
    const buf = await api.artifactContent(versionId);
    return JSON.parse(new TextDecoder().decode(buf)) as T;
  } catch {
    return null; // artifact missing/unreadable → panel shows its placeholder
  }
}

function latestSucceeded(runs: SimulationRun[], toolVersion: string): SimulationRun | null {
  return runs.filter((r) => r.tool_version === toolVersion && r.status === "succeeded").slice(-1)[0] ?? null;
}

export function AirInputStudio({ variantId, runs }: { variantId: string | null; runs: SimulationRun[] }) {
  const { t } = useTranslation();
  const [surrogate, setSurrogate] = useState<SurrogatePayload | null>(null);
  const [volume, setVolume] = useState<VolumePayload | null>(null);
  const [field, setField] = useState<FieldGridPayload | null>(null);
  const [replays, setReplays] = useState<{ run: SimulationRun; payload: ReplayPayload }[]>([]);
  const [activeScenario, setActiveScenario] = useState<string | null>(null);
  const [showVolume, setShowVolume] = useState(true);
  const [showTrajectory, setShowTrajectory] = useState(true);
  const [pose, setPose] = useState<FingerPose>({ x_mm: 0, y_mm: 0, gap_mm: 12, is_glove: false });
  const [cursor, setCursor] = useState<number | null>(null); // playing tick index
  const playTimer = useRef<number | null>(null);

  // Load the PROMOTED artifacts behind the studio (runs list arrives from
  // App's useTwinData; artifacts stream through the authenticated API).
  useEffect(() => {
    let cancelled = false;
    const sur = latestSucceeded(runs, TOOL.surrogate);
    const vol = latestSucceeded(runs, TOOL.volume);
    const fld = latestSucceeded(runs, TOOL.field);
    const rps = runs.filter((r) => r.tool_version === TOOL.replay && r.status === "succeeded");
    (async () => {
      const [surP, volP, fldP, rpPs] = await Promise.all([
        fetchArtifactJson<SurrogatePayload>(sur?.output_artifact_version_id ?? null),
        fetchArtifactJson<VolumePayload>(vol?.output_artifact_version_id ?? null),
        fetchArtifactJson<FieldGridPayload>(fld?.output_artifact_version_id ?? null),
        Promise.all(rps.map((r) => fetchArtifactJson<ReplayPayload>(r.output_artifact_version_id))),
      ]);
      if (cancelled) return;
      setSurrogate(surP);
      setVolume(volP);
      setField(fldP);
      const loaded = rps
        .map((run, i) => ({ run, payload: rpPs[i] }))
        .filter((x): x is { run: SimulationRun; payload: ReplayPayload } => x.payload !== null);
      setReplays(loaded);
      if (loaded[0]) setActiveScenario(loaded[0].payload.scenario_id);
    })();
    return () => {
      cancelled = true;
    };
  }, [runs]);

  const activeReplay = replays.find((r) => r.payload.scenario_id === activeScenario)?.payload ?? null;

  // Scenario playback: step the finger along the replay's tick trajectory at
  // the disclosed 20 Hz, then stop on the last tick.
  useEffect(() => {
    if (cursor === null || !activeReplay) return;
    if (cursor >= activeReplay.ticks.length - 1) {
      setCursor(null);
      return;
    }
    playTimer.current = window.setTimeout(() => {
      const next = (cursor ?? 0) + 1;
      const tick = activeReplay.ticks[next];
      setPose({ x_mm: tick.x_mm, y_mm: tick.y_mm, gap_mm: tick.gap_mm, is_glove: tick.is_glove });
      setCursor(next);
    }, activeReplay.tick_period_s * 1000);
    return () => {
      if (playTimer.current !== null) window.clearTimeout(playTimer.current);
    };
  }, [cursor, activeReplay]);

  function playScenario(id: string) {
    setActiveScenario(id);
    const rp = replays.find((r) => r.payload.scenario_id === id)?.payload;
    if (!rp) return;
    const tick = rp.ticks[0];
    setPose({ x_mm: tick.x_mm, y_mm: tick.y_mm, gap_mm: tick.gap_mm, is_glove: tick.is_glove });
    setCursor(0);
  }

  // Live surrogate-tier preview at the current pose (parity formula, clamped;
  // OOD flagged — never shown as a normal result).
  const ood = surrogate ? isOod(surrogate, pose.x_mm, pose.y_mm, pose.gap_mm) : false;
  const liveDc = useMemo(
    () => (surrogate && !ood ? evalSurrogate(surrogate, pose.x_mm, pose.y_mm, pose.gap_mm, pose.is_glove) : null),
    [surrogate, pose, ood]
  );
  const cfg = activeReplay?.asic_config ?? null;
  const liveCounts = liveDc && cfg ? cfg.offset_counts + cfg.gain_counts_per_fF * Object.values(liveDc).reduce((a, b) => a + b, 0) : null;
  const liveState: "IDLE" | "NEAR" | "TOUCH" | null =
    liveCounts == null || cfg == null
      ? null
      : (cfg.touch_threshold_counts != null && liveCounts >= cfg.touch_threshold_counts)
        ? "TOUCH"
        : liveCounts >= cfg.near_threshold_counts
          ? "NEAR"
          : "IDLE";

  const splitRing = (surrogate?.layout ?? field?.layout ?? "A") === "B";
  const hasGroundPlate = (() => {
    const fld = runs.find((r) => r.tool_version === TOOL.field && r.status === "succeeded");
    const g = (fld?.parameters as { geometry?: { ground_plate?: number[] } } | null)?.geometry;
    return Array.isArray(g?.ground_plate);
  })();
  // 예측–실측 검증 (지시서 ⑥): the field run's correlation record
  // (CORR-FIELD-01, synthetic FD CSV) — RMSE/r shown as PIPELINE checks.
  const [correlation, setCorrelation] = useState<CorrelationRecord | null>(null);
  useEffect(() => {
    const fld = latestSucceeded(runs, TOOL.field);
    if (!fld) return;
    api.listCorrelations(fld.id).then((rs) => setCorrelation(rs[rs.length - 1] ?? null)).catch(() => setCorrelation(null));
  }, [runs]);

  if (!variantId) return <div style={{ padding: 24, opacity: 0.6 }}>{t("air.noVariant")}</div>;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10, height: "100%", overflowY: "auto" }}>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 300px", gap: 10, height: 420, flex: "0 0 auto" }}>
        <div style={{ position: "relative", border: "1px solid #334155", borderRadius: 8, overflow: "hidden", height: "100%" }}>
          <AirScene
            pose={pose}
            ood={ood}
            splitRing={splitRing}
            hasGroundPlate={hasGroundPlate}
            liveState={liveState}
            volume={volume}
            showVolume={showVolume}
            trajectory={activeReplay ? activeReplay.ticks : null}
            showTrajectory={showTrajectory}
          />
          <div style={{ position: "absolute", left: 10, top: 10, display: "flex", gap: 8, alignItems: "center", fontSize: 12 }}>
            {(["IDLE", "NEAR", "TOUCH"] as const).map((s) => (
              <span key={s} style={{ display: "flex", gap: 4, alignItems: "center" }}>
                <span style={{ width: 10, height: 10, borderRadius: 2, background: AIR_STATE_COLOR[s], display: "inline-block" }} />
                {t(`air.state.${s}`)}
              </span>
            ))}
          </div>
          {ood && (
            <div style={{ position: "absolute", right: 10, top: 10, background: "#7f1d1d", color: "#fecaca", padding: "4px 8px", borderRadius: 6, fontSize: 12 }}>
              {t("air.ood")}
            </div>
          )}
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 8, fontSize: 12, overflowY: "auto" }}>
          <div style={{ border: "1px solid #334155", borderRadius: 6, padding: 8 }}>
            <div style={{ fontWeight: 600, marginBottom: 6 }}>{t("air.controls.title")}</div>
            {(
              [
                ["x_mm", "x_mm", -20, 20],
                ["y_mm", "y_mm", -16, 16],
                ["gap_mm", "gap_mm", 0, 35],
              ] as const
            ).map(([key, label, min, max]) => (
              <label key={key} style={{ display: "block", marginBottom: 4 }}>
                {t(`air.controls.${label}`)}: {pose[key].toFixed(1)} mm
                <input
                  type="range"
                  min={min}
                  max={max}
                  step={0.5}
                  value={pose[key]}
                  onChange={(e) => {
                    setCursor(null);
                    setPose((p) => ({ ...p, [key]: Number(e.target.value) }));
                  }}
                  style={{ width: "100%" }}
                />
              </label>
            ))}
            <label style={{ display: "block", marginBottom: 4 }}>
              <input
                type="checkbox"
                checked={pose.is_glove}
                onChange={(e) => setPose((p) => ({ ...p, is_glove: e.target.checked }))}
              />{" "}
              {t("air.controls.glove")}
            </label>
            <label style={{ display: "block" }}>
              <input type="checkbox" checked={showVolume} onChange={(e) => setShowVolume(e.target.checked)} />{" "}
              {t("air.controls.volume")}
            </label>
            <label style={{ display: "block" }}>
              <input type="checkbox" checked={showTrajectory} onChange={(e) => setShowTrajectory(e.target.checked)} />{" "}
              {t("air.controls.trajectory")}
            </label>
            {liveState && (
              <div style={{ marginTop: 8 }}>
                <span style={{ color: "#94a3b8" }}>{t("air.live")}: </span>
                <span style={{ color: AIR_STATE_COLOR[liveState], fontWeight: 700 }}>{t(`air.state.${liveState}`)}</span>
                {liveCounts != null && <span style={{ opacity: 0.7 }}> · {liveCounts.toFixed(0)} counts · ΔC {liveDc ? Object.values(liveDc).reduce((a, b) => a + b, 0).toFixed(4) : "—"} fF</span>}
              </div>
            )}
          </div>
          <AirTierPanel field={field} surrogate={surrogate} correlation={correlation} />
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr", gap: 10, maxHeight: 320 }}>
        <div style={{ border: "1px solid #334155", borderRadius: 8, padding: 8, overflowY: "auto" }}>
          <div style={{ fontWeight: 600, marginBottom: 4 }}>
            {t("air.panels.signal")}
            {activeReplay ? ` — ${activeReplay.scenario_id} (${activeReplay.engine})` : ""}
          </div>
          <AirSignalChart replay={activeReplay} cursorMs={cursor != null && activeReplay ? activeReplay.ticks[cursor]?.t_ms ?? null : null} />
          <AirThresholdNote cfg={cfg} />
        </div>
        <div style={{ border: "1px solid #334155", borderRadius: 8, padding: 8, overflowY: "auto" }}>
          <div style={{ fontWeight: 600, marginBottom: 4 }}>{t("air.panels.slice")}</div>
          <AirFieldSlice field={field} />
        </div>
      </div>

      <div style={{ border: "1px solid #334155", borderRadius: 8, padding: 8, maxHeight: 220, overflowY: "auto" }}>
        <div style={{ fontWeight: 600, marginBottom: 4 }}>{t("air.panels.scenarios")}</div>
        {replays.length > 0 ? (
          <AirScenarioTable replays={replays} activeId={activeScenario} onSelect={playScenario} />
        ) : (
          <div style={{ fontSize: 12, opacity: 0.6 }}>{t("air.scn.unavailable")}</div>
        )}
      </div>
    </div>
  );
}
