import ReactECharts from "echarts-for-react";
import { useTranslation } from "react-i18next";
import type { SimulationRun } from "../lib/api";
import { chartAxis, chartBase, traceColor, traceGlow } from "../ui/chartTheme";

const SWEEP_METRIC = /^v_out_rc_([\d.]+)$/;

function sweepSeries(run: SimulationRun) {
  return run.metrics
    .map((m) => {
      const match = SWEEP_METRIC.exec(m.name);
      return match ? { rc: Number(match[1]), v: m.value } : null;
    })
    .filter((p): p is { rc: number; v: number } => p !== null)
    .sort((a, b) => a.rc - b.rc);
}

/** §12.2: "Variant 2개 이상을 동일 축과 동일 단위로 비교" — same log-Ω x-axis,
 * same V y-axis, both variants' SPICE sweeps overlaid. */
export function SweepChart({ runsByVariant }: { runsByVariant: { label: string; run: SimulationRun }[] }) {
  const { t } = useTranslation();
  const series = runsByVariant
    .map(({ label, run }, i) => {
      const points = sweepSeries(run);
      if (points.length === 0) return null;
      const color = traceColor(i);
      return {
        name: label,
        type: "line" as const,
        data: points.map((p) => [p.rc, p.v]),
        itemStyle: { color },
        ...traceGlow(color),
      };
    })
    .filter(Boolean);

  if (series.length === 0) return null;

  const option = {
    ...chartBase,
    legend: { ...chartBase.legend, data: runsByVariant.map((r) => r.label) },
    grid: { left: 50, right: 20, top: 40, bottom: 40 },
    xAxis: {
      type: "log",
      name: t("sweep.xAxis"),
      nameLocation: "middle",
      nameGap: 28,
      ...chartAxis(),
    },
    yAxis: {
      type: "value",
      name: t("sweep.yAxis"),
      ...chartAxis(),
    },
    series,
  };

  return <ReactECharts option={option} style={{ height: 240 }} />;
}
