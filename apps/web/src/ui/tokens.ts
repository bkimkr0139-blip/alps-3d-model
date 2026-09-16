// Design tokens — the single source for the slate palette, status colors and
// shared control metrics. Every value here mirrors a hex already in use across
// the twin (App shell, asicUi, TwinControls, the 3D scenes); files adopt them
// opportunistically as they are touched, not in one big sweep.
//
// Depth model ("precision instrument", grounded in a survey of industrial HMI
// practice — ISA-101-style muted surfaces with color reserved for signal,
// Siemens-dark-theme-style layered tonal panels, product-photo metalwork):
// surfaces are LAYERED darks, never flat black — each level one step lighter
// with a 1px top rim light, controls are embossed metal, and the saturated
// palette (status + accent below) is the only strong color on screen.

export const bg = {
  page: "#060b15",
  card: "#0c1322",
  panel: "#101a2c",
  panelAlt: "#152034",
  raise: "#1d2940",
  // Canvas-overlay glass — the HUD family background (TwinControls, cockpit
  // drawers, factory station drawer all share it so overlays read as one system).
  hud: "rgba(13, 20, 35, 0.86)",
  // Brushed-metal faces: subtle vertical gradients (never flat fills) for the
  // header bar, panels and raised controls.
  metalHeader: "linear-gradient(180deg, #1c2740 0%, #141e31 52%, #101828 100%)",
  metalPanel: "linear-gradient(180deg, #131c2e 0%, #0f1725 100%)",
  metalRaise: "linear-gradient(180deg, #26334d 0%, #1c2839 100%)",
  metalWell: "linear-gradient(180deg, #0a101d 0%, #0e1626 100%)",
} as const;

export const border = {
  subtle: "#17203366",
  base: "#1e293b",
  strong: "#334155",
  // Hairline rim light — the top edge of an embossed surface catches light.
  rim: "rgba(148, 178, 255, 0.14)",
} as const;

// Layered shadow recipes. Inline styles compose these with gradients.
export const emboss = {
  // A raised control: lit top edge, soft drop.
  lift: "inset 0 1px 0 rgba(255,255,255,0.08), 0 1px 2px rgba(2,6,23,0.55), 0 2px 8px rgba(2,6,23,0.3)",
  // A panel: gentler rim, tighter drop.
  panel: "inset 0 1px 0 rgba(255,255,255,0.05), 0 1px 3px rgba(2,6,23,0.4)",
  // A pressed control / sunken readout well.
  well: "inset 0 2px 5px rgba(2,6,23,0.6), inset 0 0 0 1px rgba(2,6,23,0.4)",
} as const;

export const text = {
  body: "#e2e8f0",
  bright: "#f1f5f9",
  muted: "#94a3b8",
  // Tertiary text clears WCAG 4.5:1 on every surface in the depth model
  // (page, panel, raise) — the full-app contrast audit reads these.
  faint: "#8b99b5",
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
export const status = {
  ok: "#34d399", // asic-side green (gate pass, verified ingest)
  okAlt: "#4ade80", // product-side green (lot ok, in-control)
  attention: "#fbbf24", // quarantine, rule hit, drift, needs review
  violation: "#f87171", // reject, out-of-window, blocked, expired
  synthetic: "#a78bfa", // ◈ synthetic fixture / sysmodel tab
  info: "#38bdf8", // backend-backed info cyan
  idle: "#8b99b5", // no data / idle (kept ≥4.5:1 as chip text)
} as const;

export const accent = {
  primary: "#ff6b35", // 3D selection, active state
  orange: "#f97316", // bench controls, EDA tab
  kpi: "#67e8f9", // KPI tile default value color
  id: "#7dd3fc", // monospace business ids
  warn: "#facc15", // scope CH1, warning traces
} as const;

// Tab identity colors — the nav bar reads by dot+label together.
export const tabColor = {
  model: "#60a5fa",
  bench: "#fbbf24",
  sysmodel: "#a78bfa",
  proc: "#4ade80",
  air: "#22d3ee",
  eda: "#f97316",
  asic: "#e879f9",
  docs: "#94a3b8",
} as const;

export const radius = { sm: 6, md: 8, pill: 9 } as const;

export const fontMono = font.mono;
