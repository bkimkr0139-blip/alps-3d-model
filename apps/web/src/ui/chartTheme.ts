import { border, font, fontMono, text } from "./tokens";

// Shared ECharts look — the graph half of the precision-instrument design
// language (ui/tokens.ts). Every chart in the twin spreads `chartBase` and
// builds its axes from `chartAxis()` so sweep, correlation, DOE and the air
// replay read as one instrument: hairline spines, mono tick readouts, dashed
// scaffold grids, dark-glass tooltips, traces that sit slightly above the
// panel in their own signal color.

const SPINE = "#3b4a63"; // axis spine — visible, never competing with traces
const LABEL = "#8fa1bd"; // tick labels: readable but recessive
const GRID = "rgba(51, 65, 85, 0.4)"; // dashed scaffold, color reserved for data

export const chartBase = {
  backgroundColor: "transparent",
  textStyle: { color: text.body, fontFamily: font.ui },
  legend: {
    textStyle: { color: text.body, fontSize: 11 },
    icon: "roundRect",
    itemWidth: 14,
    itemHeight: 8,
    itemGap: 16,
  },
  tooltip: {
    backgroundColor: "rgba(10, 16, 29, 0.94)",
    borderColor: border.strong,
    borderWidth: 1,
    padding: [7, 10],
    textStyle: { color: text.bright, fontFamily: fontMono, fontSize: 11 },
    extraCssText: "border-radius: 6px; box-shadow: 0 4px 16px rgba(2, 6, 23, 0.5);",
  },
};

// Curated trace order — saturated signals only (ISA-101: color is data).
export const TRACE_PALETTE = ["#38bdf8", "#fbbf24", "#4ade80", "#f472b6", "#a78bfa", "#ff6b35"];
export const traceColor = (i: number) => TRACE_PALETTE[i % TRACE_PALETTE.length];

// One axis = hairline spine + mono tick labels + dashed split lines. The axis
// is scaffolding; the trace is the signal. Spread LAST so its styling wins
// over anything the caller set, and pass overrides (type, name, gridIndex,
// per-axis label/splitLine changes) as `extra`.
export function chartAxis(extra: Record<string, unknown> = {}) {
  return {
    axisLine: { lineStyle: { color: SPINE } },
    axisLabel: { color: LABEL, fontSize: 10, fontFamily: fontMono, hideOverlap: true },
    splitLine: { lineStyle: { color: GRID, type: "dashed" as const } },
    nameTextStyle: { color: text.muted, fontSize: 10, fontFamily: font.ui },
    ...extra,
  };
}

// A trace lifted off the panel the way a phosphor line sits in its bezel: a
// soft self-colored glow under the stroke. Spread into a line series.
export function traceGlow(color: string, width = 2) {
  return {
    lineStyle: { color, width, shadowColor: `${color}55`, shadowBlur: 5 },
  };
}
