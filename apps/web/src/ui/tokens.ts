// Design tokens — the single source for the slate palette, status colors and
// shared control metrics. Every value here mirrors a hex already in use across
// the twin (App shell, asicUi, TwinControls, the 3D scenes); files adopt them
// opportunistically as they are touched, not in one big sweep.

export const bg = {
  page: "#020617",
  card: "#0b1220",
  panel: "#0f172a",
  panelAlt: "#141c2e",
  raise: "#1e293b",
  // Canvas-overlay glass — the HUD family background (TwinControls, cockpit
  // drawers, factory station drawer all share it so overlays read as one system).
  hud: "rgba(15, 23, 42, 0.88)",
} as const;

export const border = {
  subtle: "#141c2e",
  base: "#1e293b",
  strong: "#334155",
} as const;

export const text = {
  body: "#e2e8f0",
  bright: "#f1f5f9",
  muted: "#94a3b8",
  faint: "#64748b",
} as const;

// Status palette. Rule everywhere: a mark/label always accompanies the color —
// never colour alone (the §5.1 legend rule the process chart already follows).
export const status = {
  ok: "#34d399", // asic-side green (gate pass, verified ingest)
  okAlt: "#4ade80", // product-side green (lot ok, in-control)
  attention: "#fbbf24", // quarantine, rule hit, drift, needs review
  violation: "#f87171", // reject, out-of-window, blocked, expired
  synthetic: "#a78bfa", // ◈ synthetic fixture / sysmodel tab
  info: "#38bdf8", // backend-backed info cyan
  idle: "#64748b", // no data / idle
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

export const fontMono = "monospace";
