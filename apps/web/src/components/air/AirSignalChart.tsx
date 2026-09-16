import ReactECharts from "echarts-for-react";
import { useTranslation } from "react-i18next";
import type { ReplayPayload, AsicConfigPayload } from "../../lib/air";
import { AIR_STATE_COLOR, dcThresholdFf } from "../../lib/air";
import { chartAxis, chartBase, traceGlow } from "../../ui/chartTheme";

// Seeded ASIC replay trace: truth vs noisy counts, the v2 EMA baseline, and
// the derived count thresholds. The v1/v2 state rows render as colored
// strips under the counts — the §11.2 오검출 comparison is visible as v1
// firing inside the deep-IDLE hold where v2 stays flat.
export function AirSignalChart({ replay, cursorMs }: { replay: ReplayPayload | null; cursorMs: number | null }) {
  const { t } = useTranslation();
  if (!replay) return <div style={{ fontSize: 12, opacity: 0.6 }}>{t("air.signal.unavailable")}</div>;

  const cfg: AsicConfigPayload = replay.asic_config;
  const ticks = replay.ticks;
  const tms = ticks.map((r) => r.t_ms);
  const nearC = cfg.near_threshold_counts;
  const touchC = cfg.touch_threshold_counts;

  const stateStrip = (key: "truth" | "v1" | "v2", y: number) =>
    ticks.map((r, i) => ({
      value: [r.t_ms, y],
      itemStyle: { color: AIR_STATE_COLOR[r[key]] },
      tooltip: { formatter: () => `${key.toUpperCase()} @ tick ${i}: ${r[key]}` },
    }));

  const option = {
    ...chartBase,
    animation: false,
    legend: { ...chartBase.legend, data: [t("air.signal.truth"), t("air.signal.noisy"), t("air.signal.baseline")] },
    grid: [{ left: 50, right: 16, top: 30, height: "55%" }, { left: 50, right: 16, top: "72%", height: "20%" }],
    xAxis: [
      // Dense category axes: hairline spine only — no splitLines, no ticks,
      // labels only on the bottom grid (mono ms readouts).
      { type: "category", data: tms, gridIndex: 0, ...chartAxis({ axisLabel: { show: false }, splitLine: { show: false } }) },
      { type: "category", data: tms, gridIndex: 1, name: "t [ms]", nameLocation: "middle", nameGap: 22, ...chartAxis({ splitLine: { show: false } }) },
    ],
    yAxis: [
      { type: "value", name: "counts", gridIndex: 0, ...chartAxis() },
      { type: "value", min: 0, max: 2, show: false, gridIndex: 1 },
    ],
    dataZoom: [{ type: "inside", xAxisIndex: [0, 1] }],
    series: [
      {
        name: t("air.signal.truth"),
        type: "line",
        xAxisIndex: 0,
        yAxisIndex: 0,
        data: ticks.map((r) => r.counts_truth),
        symbol: "none",
        ...traceGlow("#94a3b8", 1.5),
      },
      {
        name: t("air.signal.noisy"),
        type: "line",
        xAxisIndex: 0,
        yAxisIndex: 0,
        data: ticks.map((r) => r.counts),
        symbol: "none",
        ...traceGlow("#38bdf8", 1.5),
        markLine: {
          symbol: "none",
          silent: true,
          data: [
            { yAxis: nearC, lineStyle: { color: "#38bdf8", type: "dashed" as const }, label: { formatter: `NEAR ${nearC}`, color: "#38bdf8" } },
            ...(touchC != null
              ? [{ yAxis: touchC, lineStyle: { color: "#f97316", type: "dashed" as const }, label: { formatter: `TOUCH ${touchC}`, color: "#f97316" } }]
              : []),
          ],
        },
      },
      {
        name: t("air.signal.baseline"),
        type: "line",
        xAxisIndex: 0,
        yAxisIndex: 0,
        data: ticks.map((r) => r.baseline_v2),
        symbol: "none",
        lineStyle: { color: "#a78bfa", width: 1, type: "dashed" as const },
        markLine:
          cursorMs != null
            ? { symbol: "none", data: [{ xAxis: cursorMs, lineStyle: { color: "#f8fafc" } }, { xAxis: cursorMs, xAxisIndex: 1, lineStyle: { color: "#f8fafc" } }] }
            : undefined,
      },
      { name: "truth", type: "scatter", xAxisIndex: 1, yAxisIndex: 1, data: stateStrip("truth", 1.0), symbolSize: 8, tooltip: { show: false } },
      { name: "v1", type: "scatter", xAxisIndex: 1, yAxisIndex: 1, data: stateStrip("v1", 0.55), symbolSize: 8, tooltip: { show: false } },
      { name: "v2", type: "scatter", xAxisIndex: 1, yAxisIndex: 1, data: stateStrip("v2", 0.1), symbolSize: 8, tooltip: { show: false } },
    ],
  };
  return <ReactECharts option={option} style={{ height: 260 }} notMerge />;
}

// Provenance line under the chart: ΔC thresholds derived from counts config.
export function AirThresholdNote({ cfg }: { cfg: AsicConfigPayload | null }) {
  const { t } = useTranslation();
  if (!cfg) return null;
  const near = dcThresholdFf(cfg, cfg.near_threshold_counts);
  const touch = cfg.touch_threshold_counts != null ? dcThresholdFf(cfg, cfg.touch_threshold_counts) : null;
  return (
    <div style={{ fontSize: 11, opacity: 0.7, marginTop: 4 }}>
      {t("air.signal.derived", { near: near.toFixed(4), touch: touch != null ? touch.toFixed(4) : "—" })}
    </div>
  );
}
