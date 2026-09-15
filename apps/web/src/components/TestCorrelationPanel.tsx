import { useEffect, useState } from "react";
import ReactECharts from "echarts-for-react";
import { useTranslation } from "react-i18next";
import { enumLabel } from "../i18n";
import { api, type CorrelationRecord, type GapAnalysisDto, type Measurement, type SimulationRun } from "../lib/api";
// Curve-family table + parser shared with the Test Bench F–S overlay
// (lib/curve.ts mirrors the mech worker's MODEL_METRICS and the API's
// app/correlation.py CURVE_FAMILIES — keep the three tables in sync).
import { CURVE_FAMILIES, parseCurveMetric, predictedCurve, type CurveFamily } from "../lib/curve";
import { seedTr } from "../lib/seedL10n";

/** Residual-cause candidates (§AI-05 lite): read-only view over the stored
 * correlation's residuals. Output is explicitly "check required" hints —
 * never a verdict (§10.2: the AI doesn't finalize engineering judgments). */
function GapSection({ correlationId }: { correlationId: string }) {
  const { t, i18n } = useTranslation();
  // candidate title/detail are composed backend f-strings (correlation insights).
  const tr = (s: string) => seedTr(s, i18n.resolvedLanguage);
  const [gap, setGap] = useState<GapAnalysisDto | null>(null);

  useEffect(() => {
    api.gapAnalysis(correlationId).then(setGap);
  }, [correlationId]);

  if (!gap) return null;
  const option = {
    grid: { left: 46, right: 12, top: 18, bottom: 24 },
    xAxis: { type: "value", name: gap.stats.x_unit, nameTextStyle: { color: "#94a3b8" }, axisLabel: { color: "#94a3b8", fontSize: 9 } },
    yAxis: {
      type: "value",
      name: "Δ",
      nameTextStyle: { color: "#94a3b8" },
      axisLabel: { color: "#94a3b8", fontSize: 9 },
    },
    tooltip: { trigger: "axis" },
    series: [
      {
        type: "line",
        data: gap.residuals.x.map((x, i) => [x, gap.residuals.residual[i]]),
        symbol: "circle",
        symbolSize: 5,
        lineStyle: { color: "#f87171", width: 1.4 },
        itemStyle: { color: "#f87171" },
      },
    ],
  };

  return (
    <div style={{ marginTop: 12, borderTop: "1px solid #1e293b", paddingTop: 8 }}>
      <h4 style={{ margin: "0 0 4px", fontSize: 12.5 }}>{t("gap.title")}</h4>
      <div style={{ fontSize: 11.5, opacity: 0.7, marginBottom: 4 }}>
        {t("gap.stats", {
          n: gap.stats.n_points,
          mean: gap.stats.mean.toFixed(2),
          sd: gap.stats.sd.toFixed(2),
        })}
      </div>
      <ReactECharts option={option} style={{ height: 150 }} />
      {gap.candidates.length === 0 ? (
        <div style={{ opacity: 0.6, fontSize: 12, marginTop: 6 }}>{t("gap.noCandidates")}</div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 6, marginTop: 6 }}>
          {gap.candidates.map((c, i) => (
            <div
              key={i}
              style={{
                background: "#0b1220",
                borderLeft: "3px solid #fbbf24",
                borderRadius: 6,
                padding: "5px 8px",
                fontSize: 12,
              }}
            >
              <div style={{ display: "flex", gap: 6, alignItems: "baseline", flexWrap: "wrap" }}>
                <span style={{ background: "#fbbf24", color: "#0b1220", padding: "0 6px", borderRadius: 4, fontWeight: 700, fontSize: 10 }}>
                  {(t as (k: string) => string)(`gap.cause.${c.cause}`)}
                </span>
                <span style={{ fontWeight: 600 }}>{tr(c.title)}</span>
                <span style={{ marginLeft: "auto", fontSize: 10, color: "#fbbf24" }}>
                  {(t as (k: string) => string)(`gap.confidence.${c.confidence}`)}
                </span>
              </div>
              <div style={{ opacity: 0.8, marginTop: 3, fontSize: 11.5 }}>{tr(c.detail)}</div>
            </div>
          ))}
          <div style={{ fontSize: 11, opacity: 0.55 }}>{t("gap.disclaimer")}</div>
        </div>
      )}
    </div>
  );
}

/** S09: predicted-vs-measured overlay + RMSE/MAE/max error/correlation
 * (§5.3) — every card also shows the model tool version and run status
 * per §6.2, never a bare chart. Axis/unit labels follow the run's curve
 * family, so the same panel serves every product's prediction model. */
export function TestCorrelationPanel({ mechRun }: { mechRun: SimulationRun | null }) {
  const { t } = useTranslation();
  const [correlation, setCorrelation] = useState<CorrelationRecord | null>(null);
  const [measurements, setMeasurements] = useState<Measurement[]>([]);

  useEffect(() => {
    if (!mechRun || mechRun.status !== "succeeded") return;
    api.listCorrelations(mechRun.id).then(async (records) => {
      const record = records[0] ?? null;
      setCorrelation(record);
      if (record) setMeasurements(await api.listMeasurements(record.test_run_id));
    });
  }, [mechRun]);

  if (!mechRun) return <div style={{ opacity: 0.6 }}>{t("correlation.emptyNoRun")}</div>;
  if (mechRun.status !== "succeeded")
    return (
      <div style={{ opacity: 0.6 }}>
        {t("correlation.runStatusPrefix")} {enumLabel(t, "runStatus", mechRun.status)}
      </div>
    );

  const predicted = predictedCurve(mechRun);
  const firstFamily = mechRun.metrics
    .map((m) => parseCurveMetric(m.name)?.family)
    .find((f): f is CurveFamily => f !== undefined);
  const family = CURVE_FAMILIES[firstFamily ?? "force_mN_at_x"];
  const errorUnit = family.errorUnit;

  const option = {
    backgroundColor: "transparent",
    textStyle: { color: "#e2e8f0" },
    legend: { data: [t("correlation.legendPredicted"), t("correlation.legendMeasured")], textStyle: { color: "#e2e8f0" } },
    grid: { left: 55, right: 20, top: 40, bottom: 40 },
    xAxis: { type: "value", name: t(family.xAxis), nameLocation: "middle", nameGap: 28, axisLine: { lineStyle: { color: "#64748b" } } },
    yAxis: { type: "value", name: t(family.yAxis), axisLine: { lineStyle: { color: "#64748b" } } },
    series: [
      { name: t("correlation.legendPredicted"), type: "line", data: predicted.map((p) => [p.x, p.y]), smooth: true },
      {
        name: t("correlation.legendMeasured"),
        type: "scatter",
        symbolSize: 8,
        data: measurements.map((m) => [m.x_value, m.y_value]),
      },
    ],
  };

  return (
    <div>
      <div style={{ fontSize: 12, opacity: 0.7, marginBottom: 4 }}>
        {t("correlation.modelPrefix")} {mechRun.tool_version} · {t("correlation.runPrefix")} {mechRun.business_id}
      </div>
      <ReactECharts option={option} style={{ height: 220 }} />
      {correlation && (
        <table style={{ width: "100%", marginTop: 8, fontSize: 12 }}>
          <tbody>
            <tr>
              <td style={{ opacity: 0.7 }}>{t("correlation.metricRmse")}</td>
              <td style={{ textAlign: "right" }}>{correlation.rmse.toFixed(2)} {errorUnit}</td>
            </tr>
            <tr>
              <td style={{ opacity: 0.7 }}>{t("correlation.metricMae")}</td>
              <td style={{ textAlign: "right" }}>{correlation.mae.toFixed(2)} {errorUnit}</td>
            </tr>
            <tr>
              <td style={{ opacity: 0.7 }}>{t("correlation.metricMaxError")}</td>
              <td style={{ textAlign: "right" }}>{correlation.max_error.toFixed(2)} {errorUnit}</td>
            </tr>
            <tr>
              <td style={{ opacity: 0.7 }}>{t("correlation.metricCorrelation")}</td>
              <td style={{ textAlign: "right" }}>{correlation.correlation_coefficient.toFixed(3)}</td>
            </tr>
          </tbody>
        </table>
      )}
      {correlation?.extrapolation_warning && (
        <div style={{ color: "#eab308", fontSize: 12, marginTop: 6 }}>
          {t("correlation.extrapolationWarning")}
        </div>
      )}
      {!correlation && <div style={{ opacity: 0.6, fontSize: 12, marginTop: 6 }}>{t("correlation.emptyNoCorrelation")}</div>}
      {correlation && <GapSection correlationId={correlation.id} />}
    </div>
  );
}
