import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  MISSIONS,
  mergedFloorplan,
  runLint,
  runPlaceRoute,
  runSimulation,
  runSynthesis,
  type FloorplanConfig,
  type LintResult,
  type Mission,
  type PnrResult,
  type SimResult,
  type SynthResult,
} from "./edaRunner";
import { buildLayoutScene, buildProcessScene, buildSynthesisScene, silProfileOf } from "./edaScene";
import { pickL } from "../../lib/lstr";
import { Eda3DViewer } from "./Eda3DViewer";
import { EdaWaveform } from "./EdaWaveform";

// EDA training workbench — ported from the AgentIC education platform
// (github.com/bkimkr0139-blip/AgentIC) as a self-contained, client-only
// menu: mission-based IC chip design flow (RTL → Lint → Simulation →
// Synthesis → Place&Route) with the Unity-MCP 3D browser replaced by the
// in-house react-three-fiber viewer. No backend, no Unity — everything
// runs in the browser so employees can train offline.

type CoachHint = { key: string; params?: Record<string, string | number> };
type StageState = "idle" | "running" | "ok" | "failed";

const card: React.CSSProperties = {
  border: "1px solid #1e293b",
  borderRadius: 8,
  padding: 12,
  background: "#0b1220",
};

function StatusDot({ state }: { state: StageState }) {
  const color = state === "ok" ? "#34d399" : state === "failed" ? "#f87171" : state === "running" ? "#facc15" : "#475569";
  return <span style={{ width: 8, height: 8, borderRadius: 8, background: color, display: "inline-block" }} />;
}

function Kpi({ label, value, warn }: { label: string; value: string | number; warn?: boolean }) {
  return (
    <div style={{ background: "#0f172a", borderRadius: 6, padding: "6px 10px", minWidth: 86 }}>
      <div style={{ fontSize: 10, color: "#64748b", whiteSpace: "nowrap" }}>{label}</div>
      <div style={{ fontSize: 15, fontFamily: "monospace", color: warn ? "#f87171" : "#67e8f9" }}>{value}</div>
    </div>
  );
}

export function EdaTraining() {
  const { t, i18n } = useTranslation();
  const [mission, setMission] = useState<Mission>(MISSIONS[0]);
  const [rtl, setRtl] = useState(MISSIONS[0].starterRtl);
  const [clockPeriod, setClockPeriod] = useState(10);
  // The floorplan starts from the selected product's die defaults, not a
  // generic sample — pickMission re-applies them on every switch.
  const [fp, setFp] = useState<FloorplanConfig>(mergedFloorplan(silProfileOf(MISSIONS[0].slug).fp));
  const [lint, setLint] = useState<LintResult | null>(null);
  const [sim, setSim] = useState<SimResult | null>(null);
  const [synth, setSynth] = useState<SynthResult | null>(null);
  const [pnr, setPnr] = useState<PnrResult | null>(null);
  const [stageState, setStageState] = useState<Record<string, StageState>>({});
  const [view3d, setView3d] = useState<"process" | "synthesis" | "layout">("synthesis");
  const [coach, setCoach] = useState<CoachHint[]>([]);

  const stage = (name: string, fn: () => void) => {
    setStageState((s) => ({ ...s, [name]: "running" }));
    // Small delay so the running state is visible — the mock runners are
    // instant, but a student should see *something* happen.
    setTimeout(() => {
      fn();
      setStageState((s) => ({ ...s, [name]: "ok" }));
    }, 120);
  };

  // ── RTL static analysis (port of the coach's analyze_rtl) ──
  const rtlIssues = (code: string): CoachHint[] => {
    const hints: CoachHint[] = [];
    const modules = (code.match(/^\s*module\s+(\w+)/gm) ?? []).length;
    const endModules = (code.match(/^\s*endmodule/gm) ?? []).length;
    if (modules === 0) hints.push({ key: "eda.coach.noModule" });
    else if (modules !== endModules)
      hints.push({ key: "eda.coach.moduleMismatch", params: { m: modules, e: endModules } });
    const openB = (code.match(/\bbegin\b/g) ?? []).length;
    // substring counts like the Python coach — "end" inside "endmodule" counts
    const closeB =
      (code.match(/end/g) ?? []).length -
      (code.match(/endmodule/g) ?? []).length -
      (code.match(/endcase/g) ?? []).length;
    if (openB > closeB) hints.push({ key: "eda.coach.beginEnd", params: { b: openB, e: closeB } });
    if (!code.includes("always_ff") && !code.includes("always @") && code.trim())
      hints.push({ key: "eda.coach.noSeq" });
    return hints;
  };

  const runLintNow = () =>
    stage("lint", () => {
      const r = runLint(rtl, mission.topModule);
      setLint(r);
      setSim(null);
      setSynth(null);
      setPnr(null);
      setCoach([
        ...rtlIssues(rtl),
        ...(r.status === "failed" ? [{ key: "eda.coach.lintFail", params: { n: r.errors.length } }] : [{ key: "eda.coach.lintOk" }]),
      ]);
    });

  const runSimNow = () =>
    stage("sim", () => {
      const r = runSimulation(rtl, mission.topModule);
      setSim(r);
      setSynth(null);
      setPnr(null);
      const hints: CoachHint[] = rtlIssues(rtl);
      if (r.status === "success") {
        hints.push(
          r.failed === 0
            ? { key: "eda.coach.simAllPass", params: { n: r.passed } }
            : { key: "eda.coach.simFail", params: { f: r.failed } },
        );
        hints.push({ key: "eda.coach.coverage", params: { c: Math.round(r.coverage.overall * 100) } });
      }
      setCoach(hints);
    });

  const runSynthNow = () =>
    stage("synth", () => {
      const r = runSynthesis(rtl, mission.topModule, clockPeriod);
      setSynth(r);
      setPnr(null);
      setView3d("process"); // the fab-flow view is the default after synthesis
      const hints = rtlIssues(rtl);
      if (r.status === "success") {
        hints.push(
          r.timingSlackNs < 0
            ? { key: "eda.coach.slackNeg", params: { s: r.timingSlackNs } }
            : { key: "eda.coach.slackOk", params: { f: r.power.frequencyMhz } },
        );
        if (r.flopCount === 0) hints.push({ key: "eda.coach.noFlop" });
      }
      setCoach(hints);
    });

  const runPnrNow = () =>
    stage("pnr", () => {
      const cfg = mergedFloorplan(fp);
      const r = runPlaceRoute(mission.topModule, cfg);
      setPnr(r);
      setView3d("layout");
      const hints: CoachHint[] = [];
      if (r.drcViolations > 0) hints.push({ key: "eda.coach.drc", params: { d: r.drcViolations } });
      if (r.wnsNs < 0) hints.push({ key: "eda.coach.wnsNeg", params: { w: r.wnsNs } });
      if (cfg.utilization > 0.8) hints.push({ key: "eda.coach.utilHigh", params: { u: Math.round(cfg.utilization * 100) } });
      if (hints.length === 0) hints.push({ key: "eda.coach.pnrClean" });
      setCoach(hints);
    });

  const pickMission = (m: Mission) => {
    setMission(m);
    setRtl(m.starterRtl);
    setFp(mergedFloorplan(silProfileOf(m.slug).fp));
    setLint(null);
    setSim(null);
    setSynth(null);
    setPnr(null);
    setCoach([]);
    setStageState({});
    setView3d("synthesis");
  };

  // 3D scenes — rebuilt only when their inputs change. The layout scene also
  // follows live floorplan-slider moves (the builder is pure + seeded).
  const synthScene = useMemo(() => (synth?.status === "success" ? buildSynthesisScene(synth, mission.slug) : null), [synth, mission.slug]);
  const procScene = useMemo(() => (synth?.status === "success" ? buildProcessScene(synth, mission.slug) : null), [synth, mission.slug]);
  const layoutScene = useMemo(
    () => (synth?.status === "success" ? buildLayoutScene(mergedFloorplan(fp), pnr?.drcViolations ?? 0, mission.slug) : null),
    [synth, fp, pnr, mission.slug],
  );
  const scene = view3d === "layout" ? layoutScene : view3d === "process" ? procScene : synthScene;

  const stageDone = (s: StageState | undefined) => s === "ok";
  const stages: { id: string; label: string; run: () => void; state: StageState }[] = [
    { id: "lint", label: t("eda.stage.lint"), run: runLintNow, state: stageState.lint ?? "idle" },
    { id: "sim", label: t("eda.stage.sim"), run: runSimNow, state: stageState.sim ?? "idle" },
    { id: "synth", label: t("eda.stage.synth"), run: runSynthNow, state: stageState.synth ?? "idle" },
    { id: "pnr", label: t("eda.stage.pnr"), run: runPnrNow, state: stageState.pnr ?? "idle" },
  ];

  return (
    <div style={{ height: "100%", overflowY: "auto", display: "flex", flexDirection: "column", gap: 12 }}>
      {/* Intro + mission picker */}
      <div style={card}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", flexWrap: "wrap", gap: 8 }}>
          <h3 style={{ margin: 0, color: "#f97316" }}>{t("eda.title")}</h3>
          <span style={{ fontSize: 11, color: "#94a3b8" }}>{t("eda.note")}</span>
        </div>
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginTop: 8 }}>
          {MISSIONS.map((m) => (
            <button
              key={m.slug}
              onClick={() => pickMission(m)}
              style={{
                fontSize: 12,
                padding: "5px 12px",
                borderRadius: 14,
                border: `1px solid ${mission.slug === m.slug ? "#f97316" : "#334155"}`,
                background: mission.slug === m.slug ? "#7c2d12" : "#0f172a",
                color: mission.slug === m.slug ? "#fed7aa" : "#cbd5e1",
                cursor: "pointer",
              }}
            >
              {t(`eda.mission.${m.slug}.name` as never)}
              <span style={{ opacity: 0.6, marginLeft: 6, fontSize: 10 }}>{t(`eda.difficulty.${m.difficulty}`)}</span>
            </button>
          ))}
        </div>
        <p style={{ margin: "8px 0 0", fontSize: 12, color: "#94a3b8" }}>{t(`eda.mission.${mission.slug}.desc` as never)}</p>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "minmax(300px, 1fr) minmax(320px, 1.1fr)", gap: 12, alignItems: "start" }}>
        {/* RTL editor */}
        <div style={card}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
            <span style={{ fontSize: 13, color: "#e2e8f0" }}>
              {t("eda.rtl")} · <span style={{ fontFamily: "monospace", color: "#67e8f9" }}>{mission.topModule}</span>
            </span>
            <button
              onClick={() => setRtl(mission.starterRtl)}
              style={{ fontSize: 11, padding: "3px 10px", borderRadius: 6, border: "1px solid #334155", background: "#0f172a", color: "#94a3b8", cursor: "pointer" }}
            >
              {t("eda.rtlReset")}
            </button>
          </div>
          <textarea
            value={rtl}
            onChange={(e) => setRtl(e.target.value)}
            spellCheck={false}
            rows={16}
            style={{
              width: "100%",
              boxSizing: "border-box",
              minHeight: 300,
              background: "#020617",
              color: "#a5f3fc",
              border: "1px solid #1e293b",
              borderRadius: 6,
              padding: 10,
              fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
              fontSize: 12,
              lineHeight: 1.5,
              resize: "vertical",
              whiteSpace: "pre",
            }}
          />
        </div>

        {/* Stage flow */}
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          {/* stage chips */}
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center" }}>
            {stages.map((s, i) => (
              <span key={s.id} style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <button
                  onClick={s.run}
                  style={{
                    fontSize: 12,
                    padding: "5px 12px",
                    borderRadius: 6,
                    display: "flex",
                    alignItems: "center",
                    gap: 6,
                    border: "1px solid #334155",
                    background: stageDone(s.state) ? "#064e3b" : "#0f172a",
                    color: stageDone(s.state) ? "#a7f3d0" : "#e2e8f0",
                    cursor: "pointer",
                  }}
                >
                  <StatusDot state={s.state} />
                  {s.label}
                </button>
                {i < stages.length - 1 && <span style={{ color: "#475569", fontSize: 12 }}>→</span>}
              </span>
            ))}
            <span style={{ display: "flex", alignItems: "center", gap: 4, marginLeft: "auto", fontSize: 11, color: "#94a3b8" }}>
              {t("eda.clockPeriod")}
              <input
                type="number"
                min={2}
                max={20}
                step={0.5}
                value={clockPeriod}
                onChange={(e) => setClockPeriod(parseFloat(e.target.value) || 10)}
                style={{ width: 52, background: "#0f172a", color: "#e2e8f0", border: "1px solid #334155", borderRadius: 4, padding: "2px 4px" }}
              />
              ns
            </span>
          </div>

          {/* Lint results */}
          {lint && (
            <div style={card}>
              <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                <Kpi label={t("eda.kpi.errors")} value={lint.errors.length} warn={lint.errors.length > 0} />
                <Kpi label={t("eda.kpi.warnings")} value={lint.warnings.length} warn={lint.warnings.length > 0} />
                <span style={{ fontSize: 11, color: "#64748b", alignSelf: "center", fontFamily: "monospace" }}>{t("eda.log")}: {lint.log.split("\n").slice(-2, -1)[0]}</span>
              </div>
              {(lint.errors.length > 0 || lint.warnings.length > 0) && (
                <ul style={{ margin: "8px 0 0", paddingLeft: 18, fontSize: 11, color: "#fca5a5" }}>
                  {lint.errors.map((e, i) => (
                    <li key={`e${i}`}>[E] {e.message}</li>
                  ))}
                  {lint.warnings.map((w, i) => (
                    <li key={`w${i}`} style={{ color: "#fbbf24" }}>
                      [W] {w.message}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}

          {/* Simulation results */}
          {sim && sim.status === "success" && (
            <div style={card}>
              <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                <Kpi label={t("eda.kpi.tests")} value={`${sim.passed}/${sim.testCount}`} warn={sim.failed > 0} />
                <Kpi label={t("eda.kpi.coverage")} value={`${Math.round(sim.coverage.overall * 100)}%`} />
              </div>
              <div style={{ marginTop: 8 }}>
                <EdaWaveform data={sim.waveform} />
              </div>
              <div style={{ marginTop: 8, fontSize: 11, color: "#94a3b8" }}>
                {t("eda.scenarios")}
                <ul style={{ margin: "4px 0 0", paddingLeft: 18 }}>
                  {sim.scenarios.map((s) => (
                    <li key={s.name} style={{ color: s.expected_pass ? "#86efac" : "#fca5a5" }}>
                      <span style={{ fontFamily: "monospace" }}>{s.name}</span> — {pickL(s.description, i18n.resolvedLanguage)}
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          )}

          {/* Synthesis results */}
          {synth && synth.status === "success" && (
            <div style={card}>
              <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                <Kpi label={t("eda.kpi.gates")} value={synth.gateCount} />
                <Kpi label={t("eda.kpi.ffs")} value={synth.flopCount} />
                <Kpi label={t("eda.kpi.luts")} value={synth.lutCount} />
                <Kpi label={t("eda.kpi.area")} value={`${synth.areaUm2} µm²`} />
                <Kpi label={t("eda.kpi.slack")} value={`${synth.timingSlackNs} ns`} warn={synth.timingSlackNs < 0} />
                <Kpi label={t("eda.kpi.power")} value={`${synth.power.totalMw} mW`} />
              </div>
              <div style={{ marginTop: 8, fontSize: 11, color: "#94a3b8" }}>
                {t("eda.criticalPaths")}
                <table style={{ width: "100%", marginTop: 4, borderCollapse: "collapse", fontSize: 10, fontFamily: "monospace" }}>
                  <tbody>
                    {synth.criticalPaths.map((p) => (
                      <tr key={p.id} style={{ borderTop: "1px solid #1e293b" }}>
                        <td style={{ padding: "3px 4px", color: "#cbd5e1" }}>{p.startpoint} → {p.endpoint}</td>
                        <td style={{ padding: "3px 4px", color: "#94a3b8" }}>{p.delayNs} ns</td>
                        <td style={{ padding: "3px 4px", color: p.status === "MET" ? "#86efac" : "#fca5a5" }}>{p.slackNs} ns {p.status}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* P&R results */}
          {pnr && (
            <div style={card}>
              <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                <Kpi label={t("eda.kpi.die")} value={`${pnr.dieAreaUm2} µm²`} />
                <Kpi label={t("eda.kpi.placed")} value={pnr.placedCells} />
                <Kpi label={t("eda.kpi.nets")} value={pnr.routedNets} />
                <Kpi label={t("eda.kpi.wns")} value={`${pnr.wnsNs} ns`} warn={pnr.wnsNs < 0} />
                <Kpi label={t("eda.kpi.drc")} value={pnr.drcViolations} warn={pnr.drcViolations > 0} />
              </div>
            </div>
          )}

          {/* Floorplan controls (P&R) */}
          <div style={card}>
            <div style={{ fontSize: 12, color: "#e2e8f0", marginBottom: 6 }}>{t("eda.floorplan")}</div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "6px 16px", fontSize: 11, color: "#94a3b8" }}>
              {(
                [
                  ["fpDieW", "dieW", 6, 18, 0.5, (v: number) => `${v} µm`],
                  ["fpDieD", "dieD", 4, 14, 0.5, (v: number) => `${v} µm`],
                  ["fpUtil", "utilization", 0.3, 0.9, 0.05, (v: number) => `${Math.round(v * 100)}%`],
                  ["fpPitch", "powerGridPitch", 0.7, 3.5, 0.1, (v: number) => `${v.toFixed(1)} µm`],
                  ["fpDensity", "signalRoutingDensity", 0.1, 1.0, 0.05, (v: number) => `${Math.round(v * 100)}%`],
                ] as const
              ).map(([key, field, min, max, stepStep, fmt]) => (
                <label key={field} style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                  <span>
                    {t(`eda.${key}`)}: <b style={{ color: "#67e8f9" }}>{fmt(fp[field])}</b>
                  </span>
                  <input
                    type="range"
                    min={min}
                    max={max}
                    step={stepStep}
                    value={fp[field]}
                    onChange={(e) => setFp({ ...fp, [field]: parseFloat(e.target.value) })}
                  />
                </label>
              ))}
              <label style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                <span>
                  {t("eda.fpMacros")}: <b style={{ color: "#67e8f9" }}>{fp.numMacros}</b>
                </span>
                <input type="range" min={0} max={4} step={1} value={fp.numMacros} onChange={(e) => setFp({ ...fp, numMacros: parseInt(e.target.value, 10) })} />
              </label>
              <label style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                <span>{t("eda.fpPad")}</span>
                <select
                  value={fp.padDensity}
                  onChange={(e) => setFp({ ...fp, padDensity: e.target.value as FloorplanConfig["padDensity"] })}
                  style={{ background: "#0f172a", color: "#e2e8f0", border: "1px solid #334155", borderRadius: 4, padding: 2 }}
                >
                  <option value="low">low</option>
                  <option value="medium">medium</option>
                  <option value="high">high</option>
                </select>
              </label>
            </div>
            <div style={{ fontSize: 10, color: "#64748b", marginTop: 6 }}>{t("eda.fpHint")}</div>
          </div>
        </div>
      </div>

      {/* 3D viewer — the Unity replacement */}
      <div style={{ ...card, padding: 8 }}>
        <div style={{ display: "flex", gap: 6, marginBottom: 8, alignItems: "center", flexWrap: "wrap" }}>
          <button
            onClick={() => setView3d("process")}
            disabled={!procScene}
            style={{
              fontSize: 12,
              padding: "4px 12px",
              borderRadius: 6,
              border: `1px solid ${view3d === "process" ? "#34d399" : "#334155"}`,
              background: view3d === "process" ? "#064e3b" : "#0f172a",
              color: view3d === "process" ? "#a7f3d0" : "#94a3b8",
              cursor: procScene ? "pointer" : "not-allowed",
              opacity: procScene ? 1 : 0.4,
            }}
          >
            {t("eda.view3dProcess")}
          </button>
          <button
            onClick={() => setView3d("synthesis")}
            disabled={!synthScene}
            style={{
              fontSize: 12,
              padding: "4px 12px",
              borderRadius: 6,
              border: `1px solid ${view3d === "synthesis" ? "#22d3ee" : "#334155"}`,
              background: view3d === "synthesis" ? "#164e63" : "#0f172a",
              color: view3d === "synthesis" ? "#a5f3fc" : "#94a3b8",
              cursor: synthScene ? "pointer" : "not-allowed",
              opacity: synthScene ? 1 : 0.4,
            }}
          >
            {t("eda.view3dSynth")}
          </button>
          <button
            onClick={() => setView3d("layout")}
            disabled={!layoutScene}
            style={{
              fontSize: 12,
              padding: "4px 12px",
              borderRadius: 6,
              border: `1px solid ${view3d === "layout" ? "#a78bfa" : "#334155"}`,
              background: view3d === "layout" ? "#4c1d95" : "#0f172a",
              color: view3d === "layout" ? "#ddd6fe" : "#94a3b8",
              cursor: layoutScene ? "pointer" : "not-allowed",
              opacity: layoutScene ? 1 : 0.4,
            }}
          >
            {t("eda.view3dLayout")}
          </button>
          <span style={{ marginLeft: "auto", fontSize: 11, fontFamily: "monospace", color: "#fbbf24" }}>
            ◈ {t("eda.view3dChip")}: {silProfileOf(mission.slug).chip} · {mission.topModule}
            {synth?.status === "success" ? ` · ${synth.gateCount} gates` : ""}
          </span>
          <span style={{ fontSize: 11, color: "#64748b" }}>{t("eda.view3dHint")}</span>
        </div>
        <div style={{ height: 430 }}>
          <Eda3DViewer scene={scene} />
        </div>
      </div>

      {/* Coach */}
      {coach.length > 0 && (
        <div style={card}>
          <div style={{ fontSize: 12, color: "#f97316", marginBottom: 4 }}>{t("eda.coach.title")}</div>
          <ul style={{ margin: 0, paddingLeft: 18, fontSize: 12, color: "#cbd5e1" }}>
            {coach.map((h, i) => (
              <li key={i} style={{ marginTop: 2 }}>
                {t(h.key as never, h.params)}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
