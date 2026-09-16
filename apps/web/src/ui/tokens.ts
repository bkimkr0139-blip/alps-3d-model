// Design tokens — the single source for the slate palette, status colors and
// shared control metrics. Every value here mirrors a CSS variable defined in
// index.css; files adopt them opportunistically as they are touched, not in
// one big sweep.
//
// Depth model ("precision instrument", grounded in a survey of industrial HMI
// practice — ISA-101-style muted surfaces with color reserved for signal,
// Siemens-dark-theme-style layered tonal panels, product-photo metalwork):
// surfaces are LAYERED, never flat — each level one step away from the page
// with a 1px top rim light, controls are embossed metal, and the saturated
// palette (status + accent below) is the only strong color on screen.
//
// Theme model: the surface/text/status groups are CSS variables that flip
// with [data-theme="light"] on <html> (set by the store). Inline styles
// compose these var() strings freely — EXCEPT contexts that are parsed as
// literal colors, not CSS:
//   • three.js material props (r3f `color=`) → use rawAccent/rawStatus
//   • <canvas> 2D contexts and ECharts options (own color parsers) →
//     concrete hexes from ui/chartTheme (useChartTheme) / svgPalette
//   • SVG presentation ATTRIBUTES (fill="…") → svgPalette via useUiTheme
// Alpha-tinted compositions of var colors use color-mix(in srgb, …).

export const bg = {
  page: "var(--alps-bg-page)",
  card: "var(--alps-bg-card)",
  panel: "var(--alps-bg-panel)",
  panelAlt: "var(--alps-bg-panel-alt)",
  raise: "var(--alps-bg-raise)",
  // Sunken instrument wells that stay dark in BOTH themes (scope glass,
  // schematic canvases) — a deliberate exception to the variable set.
  wellDark: "var(--alps-well-dark)",
  // Canvas-overlay glass — the HUD family background (TwinControls, cockpit
  // drawers, factory station drawer all share it so overlays read as one system).
  hud: "var(--alps-bg-hud)",
  // Brushed-metal faces: subtle vertical gradients (never flat fills) for the
  // header bar, panels and raised controls.
  metalHeader: "var(--alps-metal-header)",
  metalPanel: "var(--alps-metal-panel)",
  metalRaise: "var(--alps-metal-raise)",
  metalWell: "var(--alps-metal-well)",
} as const;

export const border = {
  subtle: "var(--alps-border-subtle)",
  base: "var(--alps-border-base)",
  strong: "var(--alps-border-strong)",
  // Hairline rim light — the top edge of an embossed surface catches light.
  rim: "var(--alps-border-rim)",
} as const;

// Layered shadow recipes. Inline styles compose these with gradients.
// Var-driven because the light theme needs white rim lights and softer drops.
export const emboss = {
  // A raised control: lit top edge, soft drop.
  lift: "var(--alps-emboss-lift)",
  // A panel: gentler rim, tighter drop.
  panel: "var(--alps-emboss-panel)",
  // A pressed control / sunken readout well.
  well: "var(--alps-emboss-well)",
} as const;

export const text = {
  body: "var(--alps-text)",
  bright: "var(--alps-text-bright)",
  muted: "var(--alps-text-muted)",
  // Tertiary text clears WCAG 4.5:1 on every surface in the depth model
  // (page, panel, raise) in BOTH themes — the full-app contrast audit
  // reads these.
  faint: "var(--alps-text-faint)",
} as const;

export const font = {
  ui: "'Pretendard Variable', Pretendard, Inter, system-ui, 'Segoe UI', Roboto, 'Apple SD Gothic Neo', 'Noto Sans KR', sans-serif",
  mono: "'JetBrains Mono', ui-monospace, 'SF Mono', Menlo, Consolas, monospace",
} as const;

// Micro-label tracking — uppercase captions get loosened spacing the way
// instrument front panels do.
export const tracking = { micro: "0.55px", wider: "1.1px" } as const;

// Status palette. Rule everywhere: a mark/label always accompanies the color —
// never colour alone (the §5.1 legend rule the process chart already follows).
// Var-driven: the light theme darkens every hue so chip text keeps ≥4.5:1.
export const status = {
  ok: "var(--alps-ok)", // asic-side green (gate pass, verified ingest)
  okAlt: "var(--alps-ok-alt)", // product-side green (lot ok, in-control)
  attention: "var(--alps-attention)", // quarantine, rule hit, drift, needs review
  violation: "var(--alps-violation)", // reject, out-of-window, blocked, expired
  synthetic: "var(--alps-synthetic)", // ◈ synthetic fixture / sysmodel tab
  info: "var(--alps-info)", // backend-backed info cyan
  idle: "var(--alps-idle)", // no data / idle (kept ≥4.5:1 as chip text)
} as const;

// Raw status hexes for three.js materials (THREE.Color cannot parse var()).
export const rawStatus = {
  ok: "#34d399",
  okAlt: "#4ade80",
  attention: "#fbbf24",
  violation: "#f87171",
  synthetic: "#a78bfa",
  info: "#38bdf8",
  idle: "#8b99b5",
} as const;

export const accent = {
  primary: "var(--alps-accent)", // 3D selection, active state
  orange: "var(--alps-accent-orange)", // bench controls, EDA tab
  kpi: "var(--alps-accent-kpi)", // KPI tile default value color
  id: "var(--alps-accent-id)", // monospace business ids
  warn: "var(--alps-accent-warn)", // scope CH1, warning traces
} as const;

// Raw accent hexes for three.js materials (see rawStatus).
export const rawAccent = {
  primary: "#ff6b35",
  orange: "#f97316",
  kpi: "#67e8f9",
  id: "#7dd3fc",
  warn: "#facc15",
} as const;

// Tab identity colors — the nav bar reads by dot+label together.
export const tabColor = {
  model: "var(--alps-tab-model)",
  bench: "var(--alps-tab-bench)",
  sysmodel: "var(--alps-tab-sysmodel)",
  proc: "var(--alps-tab-proc)",
  air: "var(--alps-tab-air)",
  eda: "var(--alps-tab-eda)",
  asic: "var(--alps-tab-asic)",
  docs: "var(--alps-tab-docs)",
} as const;

// Concrete per-mode palettes for SVG presentation attributes and hand-rolled
// SVG charts, which cannot take var() in attributes. Same roles everywhere:
// axis = hairlines/grid, mark = default trace, dim = tertiary labels.
// series = curated data-mark order (dark saturated / light darkened), kept
// in sync role-wise with chartTheme traces.
export const svgPalette = {
  dark: {
    axis: "#334155",
    mark: "#60a5fa",
    dim: "#94a3b8",
    faint: "#8b99b5",
    body: "#e2e8f0",
    bright: "#f1f5f9",
    well: "#0b1220",
    grid: "#1e293b",
    series: ["#22d3ee", "#4ade80", "#fbbf24", "#f87171", "#a78bfa"],
  },
  light: {
    axis: "#9aabbf",
    mark: "#2563eb",
    dim: "#4b5c74",
    faint: "#5d6e87",
    body: "#243044",
    bright: "#0f1a2c",
    well: "#e6ebf3",
    grid: "#c3cedd",
    series: ["#0e7490", "#15803d", "#b45309", "#dc2626", "#6d28d9"],
  },
} as const;

export type SvgMode = keyof typeof svgPalette;

export const radius = { sm: 6, md: 8, pill: 9 } as const;

export const fontMono = font.mono;
