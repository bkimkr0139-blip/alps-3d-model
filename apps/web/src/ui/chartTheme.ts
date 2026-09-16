import { font, fontMono } from "./tokens";
import { useUiTheme } from "./useTheme";
import type { UiTheme } from "../store";

// Shared ECharts look — the graph half of the precision-instrument design
// language (ui/tokens.ts). Every chart in the twin spreads the `chartBase`
// for the active theme and builds its axes from `chartAxis()` so sweep,
// correlation, DOE and the air replay read as one instrument: hairline
// spines, mono tick readouts, dashed scaffold grids, glass tooltips, traces
// that sit slightly above the panel in their own signal color.
//
// ECharts renders to canvas and parses colors with its own parser — it can
// take neither var() nor color-mix(). So palettes are CONCRETE hexes per
// mode, selected by useChartTheme(); components subscribe through the hook
// and re-render when the header toggle flips.

interface ChartPalette {
  spine: string; // axis spine — visible, never competing with traces
  label: string; // tick labels: readable but recessive
  grid: string; // dashed scaffold, color reserved for data
  body: string;
  bright: string;
  muted: string;
  tooltipBg: string;
  tooltipBorder: string;
  tooltipShadow: string;
  traces: string[];
}

const DARK: ChartPalette = {
  spine: "#3b4a63",
  label: "#8fa1bd",
  grid: "rgba(51, 65, 85, 0.4)",
  body: "#e2e8f0",
  bright: "#f1f5f9",
  muted: "#94a3b8",
  tooltipBg: "rgba(10, 16, 29, 0.94)",
  tooltipBorder: "#334155",
  tooltipShadow: "rgba(2, 6, 23, 0.5)",
  // Curated trace order — saturated signals only (ISA-101: color is data).
  traces: ["#38bdf8", "#fbbf24", "#4ade80", "#f472b6", "#a78bfa", "#ff6b35"],
};

// Daylight variant: same roles, darkened to hold contrast on the light
// panels (audit-checked, like the status tokens in light mode).
const LIGHT: ChartPalette = {
  spine: "#8fa0b5",
  label: "#51627a",
  grid: "rgba(100, 116, 139, 0.35)",
  body: "#243044",
  bright: "#0f1a2c",
  muted: "#46586f",
  tooltipBg: "rgba(255, 255, 255, 0.96)",
  tooltipBorder: "#9aabbf",
  tooltipShadow: "rgba(15, 23, 42, 0.25)",
  traces: ["#0369a1", "#b45309", "#15803d", "#be185d", "#6d28d9", "#c2410c"],
};

const PALETTES: Record<UiTheme, ChartPalette> = { dark: DARK, light: LIGHT };

export function useChartTheme() {
  const mode = useUiTheme();
  const p = PALETTES[mode];
  return {
    mode,
    bright: p.bright,
    traces: p.traces,
    traceColor: (i: number) => p.traces[i % p.traces.length],
    chartBase: {
      backgroundColor: "transparent",
      textStyle: { color: p.body, fontFamily: font.ui },
      legend: {
        textStyle: { color: p.body, fontSize: 11 },
        icon: "roundRect",
        itemWidth: 14,
        itemHeight: 8,
        itemGap: 16,
      },
      tooltip: {
        backgroundColor: p.tooltipBg,
        borderColor: p.tooltipBorder,
        borderWidth: 1,
        padding: [7, 10],
        textStyle: { color: p.bright, fontFamily: fontMono, fontSize: 11 },
        extraCssText: `border-radius: 6px; box-shadow: 0 4px 16px ${p.tooltipShadow};`,
      },
    },
    // One axis = hairline spine + mono tick labels + dashed split lines. The
    // axis is scaffolding; the trace is the signal. Spread LAST so its
    // styling wins over anything the caller set, and pass overrides (type,
    // name, gridIndex, per-axis label/splitLine changes) as `extra`.
    chartAxis: (extra: Record<string, unknown> = {}) => ({
      axisLine: { lineStyle: { color: p.spine } },
      axisLabel: { color: p.label, fontSize: 10, fontFamily: fontMono, hideOverlap: true },
      splitLine: { lineStyle: { color: p.grid, type: "dashed" as const } },
      nameTextStyle: { color: p.muted, fontSize: 10, fontFamily: font.ui },
      ...extra,
    }),
  };
}

type Rgba = readonly [number, number, number];

function hexToRgb(hex: string): Rgba {
  const n = parseInt(hex.slice(1), 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

// A trace lifted off the panel the way a phosphor line sits in its bezel: a
// soft self-colored glow under the stroke. Spread into a line series. Alpha
// is composed here (canvas needs a concrete rgba, not a template suffix).
export function traceGlow(color: string, width = 2) {
  const [r, g, b] = hexToRgb(color);
  return {
    lineStyle: { color, width, shadowColor: `rgba(${r}, ${g}, ${b}, 0.33)`, shadowBlur: 5 },
  };
}
