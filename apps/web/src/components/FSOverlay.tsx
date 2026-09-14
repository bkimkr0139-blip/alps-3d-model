import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { api, type SimulationRun } from "../lib/api";
import { CURVE_FAMILIES, predictedCurve, type CurveFamily } from "../lib/curve";
import { useTwinStore, useBenchStore } from "../store";

// 지시서 ③ SL-02 (co-sim completion, lite): the prediction-model curve lives
// in the Test Bench and a cursor moves across it IN SYNC with the bench
// actuation animation — press the switch, the cursor sweeps the F–S curve;
// rotate the encoder, it sweeps the torque curve; slide MEMS pressure, it
// tracks the transfer curve. Same exponential approach (dt·22) as the 3D
// TwinAnimator, so bench motion and curve motion feel like one mechanism.

const W = 300;
const H = 130;
const M = { l: 38, r: 10, t: 10, b: 24 };

function familyOf(run: SimulationRun): CurveFamily {
  const first = run.metrics
    .map((m) => m.name)
    .map((n) => (Object.keys(CURVE_FAMILIES) as CurveFamily[]).find((f) => n.startsWith(`${f}_`)))
    .find((f): f is CurveFamily => !!f);
  return first ?? "force_mN_at_x";
}

type Chip = { key: string; value: number };

function kanseiChips(family: CurveFamily, curve: { x: number; y: number }[]): Chip[] {
  // Illustrative kansei mapping (§10.2: labelled as such, not a validated
  // kansei model) — click clarity from the peak-to-valley drop, lightness
  // from how low the peak force sits in a typical switch force band.
  if (curve.length < 2) return [];
  const peak = Math.max(...curve.map((p) => p.y));
  const valley = Math.min(...curve.map((p) => p.y));
  if (family === "force_mN_at_x") {
    return [
      { key: "bench.kanseiClarity", value: (peak - valley) / peak },
      { key: "bench.kanseiLight", value: Math.max(0, 1 - peak / 500) },
    ];
  }
  if (family === "torque_mNm_at_deg") {
    return [{ key: "bench.kanseiClarity", value: (peak - valley) / peak }];
  }
  const end = curve[curve.length - 1].y;
  return [{ key: "bench.kanseiTrust", value: end / peak }];
}

export function FSOverlay({
  mechRun,
  family,
  pressure,
}: {
  mechRun: SimulationRun | null;
  family: "tact" | "encoder" | "mems";
  pressure: number;
}) {
  const { t } = useTranslation();
  const actuated = useTwinStore((s) => s.actuated);
  const rotating = useBenchStore((s) => s.rotating);
  const actRef = useRef(0);
  const cursorRef = useRef<SVGLineElement | null>(null);
  const readoutRef = useRef<HTMLSpanElement | null>(null);
  const [measured, setMeasured] = useState<{ x: number; y: number }[]>([]);

  const predicted = useMemo(
    () => (mechRun && mechRun.status === "succeeded" ? predictedCurve(mechRun) : []),
    [mechRun]
  );
  const fam: CurveFamily = mechRun ? familyOf(mechRun) : "force_mN_at_x";
  const labels = CURVE_FAMILIES[fam];
  const chips = kanseiChips(fam, predicted);

  useEffect(() => {
    if (!mechRun || mechRun.status !== "succeeded") return;
    let cancelled = false;
    api.listCorrelations(mechRun.id).then(async (records) => {
      // All setState inside async continuations — a synchronous reset here
      // would cascade an extra render per run switch.
      if (!records[0]) {
        setMeasured([]);
        return;
      }
      const ms = await api.listMeasurements(records[0].test_run_id);
      if (!cancelled) setMeasured(ms.map((m) => ({ x: m.x_value, y: m.y_value })));
    });
    return () => {
      cancelled = true;
    };
  }, [mechRun]);

  useEffect(() => {
    if (predicted.length < 2) return;
    const xs = predicted.map((p) => p.x);
    const xMin = Math.min(...xs);
    const xMax = Math.max(...xs);

    const drawFraction = (frac: number) => {
      const clamped = Math.max(0, Math.min(1, frac));
      const xAt = xMin + (xMax - xMin) * clamped;
      // piecewise-linear sample of the curve at the cursor x
      let y = predicted[0].y;
      for (let i = 1; i < predicted.length; i++) {
        if (predicted[i].x >= xAt) {
          const a = predicted[i - 1];
          const b = predicted[i];
          y = a.y + (b.y - a.y) * ((xAt - a.x) / (b.x - a.x || 1));
          break;
        }
        y = predicted[i].y;
      }
      const px = M.l + ((xAt - xMin) / (xMax - xMin || 1)) * (W - M.l - M.r);
      if (cursorRef.current) {
        cursorRef.current.setAttribute("x1", String(px));
        cursorRef.current.setAttribute("x2", String(px));
      }
      if (readoutRef.current) readoutRef.current.textContent = `${xAt.toFixed(2)} / ${y.toFixed(1)}`;
    };

    let raf = 0;
    let last = performance.now();
    const tick = (now: number) => {
      const dt = Math.min(0.05, (now - last) / 1000);
      last = now;
      // Same approach curve as TwinAnimator — bench animation and 3D twin
      // stay in lockstep. MEMS has no animation: pressure IS the input.
      if (family === "encoder" && rotating) {
        // looping sweep while the shaft spins
        actRef.current = (actRef.current + dt * 0.35) % 1.15;
        drawFraction(actRef.current);
        raf = requestAnimationFrame(tick);
        return;
      }
      const target = family === "tact" ? (actuated ? 1 : 0) : family === "encoder" ? 0 : (pressure - 40) / 360;
      actRef.current += (target - actRef.current) * Math.min(1, dt * 22);
      drawFraction(actRef.current);
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [predicted, family, actuated, rotating, pressure]);

  if (!mechRun || predicted.length < 2) return null;

  const xs = predicted.map((p) => p.x);
  const ys = predicted.map((p) => p.y);
  const xMin = Math.min(...xs);
  const xMax = Math.max(...xs);
  const yMin = Math.min(...ys);
  const yMax = Math.max(...ys);
  const sx = (x: number) => M.l + ((x - xMin) / (xMax - xMin || 1)) * (W - M.l - M.r);
  const sy = (y: number) => H - M.b - ((y - yMin) / (yMax - yMin || 1)) * (H - M.t - M.b);
  const path = predicted.map((p, i) => `${i === 0 ? "M" : "L"} ${sx(p.x).toFixed(1)} ${sy(p.y).toFixed(1)}`).join(" ");

  return (
    <div style={{ border: "1px solid #334155", borderRadius: 8, padding: 10, background: "#0b1220" }}>
      <div style={{ fontSize: 12, opacity: 0.75, marginBottom: 4 }}>
        {t("bench.fsTitle")} · <span style={{ fontFamily: "monospace", fontSize: 11 }}>{mechRun.business_id}</span>
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} style={{ width: "100%", display: "block" }}>
        <path d={path} fill="none" stroke="#38bdf8" strokeWidth={2} />
        {measured.map((p, i) => (
          <circle key={i} cx={sx(p.x)} cy={sy(p.y)} r={2.5} fill="#f97316" opacity={0.9} />
        ))}
        <line ref={cursorRef} x1={M.l} y1={M.t} x2={M.l} y2={H - M.b} stroke="#f97316" strokeWidth={1.4} strokeDasharray="4 3" />
        <text x={M.l} y={H - 6} fontSize={9} fill="#94a3b8">{t(labels.xAxis)}</text>
        <text x={4} y={M.t + 8} fontSize={9} fill="#94a3b8">{t(labels.yAxis)}</text>
        <circle cx={W - M.r - 44} cy={8} r={2.5} fill="#f97316" />
        <text x={W - M.r - 38} y={11} fontSize={9} fill="#f97316">{t("correlation.legendMeasured")}</text>
      </svg>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", fontSize: 11, marginTop: 4 }}>
        <span style={{ fontFamily: "monospace" }} ref={readoutRef} />
        <span style={{ opacity: 0.6 }}>{t("bench.fsSyncHint")}</span>
      </div>
      {chips.length > 0 && (
        <div style={{ display: "flex", gap: 6, marginTop: 7, flexWrap: "wrap", alignItems: "center" }}>
          <span style={{ fontSize: 10.5, opacity: 0.6 }}>{t("bench.kanseiTitle")}</span>
          {chips.map((chip) => (
            <span
              key={chip.key}
              style={{
                fontSize: 11,
                padding: "2px 8px",
                borderRadius: 999,
                background: "rgba(244,114,182,0.16)",
                border: "1px solid rgba(244,114,182,0.55)",
                color: "#f9a8d4",
              }}
            >
              {(t as (k: string) => string)(chip.key)} {Math.round(Math.max(0, Math.min(1, chip.value)) * 100)}%
            </span>
          ))}
          <span style={{ fontSize: 10, opacity: 0.45 }}>{t("bench.illustrative")}</span>
        </div>
      )}
    </div>
  );
}
