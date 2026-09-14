import type { SimulationRun } from "./api";

// Metric naming contract per prediction model type — mirrors the mech-model
// worker's MODEL_METRICS and the API's app/correlation.py CURVE_FAMILIES
// (keep the three tables in sync). `as const` keeps the i18n keys literal so
// t() stays type-checked. Shared by the S09 correlation panel and the Test
// Bench F–S overlay so both parse runs identically.
export const CURVE_FAMILIES = {
  force_mN_at_x: { xAxis: "correlation.axis.stroke", yAxis: "correlation.axis.force", errorUnit: "mN" },
  torque_mNm_at_deg: { xAxis: "correlation.axis.angle", yAxis: "correlation.axis.torque", errorUnit: "mN·m" },
  vout_mv_at_kpa: { xAxis: "correlation.axis.pressure", yAxis: "correlation.axis.output", errorUnit: "mV" },
  delta_c_fF_at_d: { xAxis: "correlation.axis.distance", yAxis: "correlation.axis.capacitance", errorUnit: "fF" },
} as const;

export type CurveFamily = keyof typeof CURVE_FAMILIES;

export function parseCurveMetric(name: string): { family: CurveFamily; x: number } | null {
  for (const family of Object.keys(CURVE_FAMILIES) as CurveFamily[]) {
    if (!name.startsWith(`${family}_`)) continue;
    const x = Number(name.slice(family.length + 1));
    return Number.isFinite(x) ? { family, x } : null;
  }
  return null;
}

export function predictedCurve(run: SimulationRun) {
  return run.metrics
    .map((m) => {
      const parsed = parseCurveMetric(m.name);
      return parsed ? { x: parsed.x, y: m.value } : null;
    })
    .filter((p): p is { x: number; y: number } => p !== null)
    .sort((a, b) => a.x - b.x);
}
