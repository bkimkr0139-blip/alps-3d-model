// AirInput 3D Interaction Field Twin — client-side types + the surrogate
// evaluation contract. The RBF formula here is a BYTE-LEVEL mirror of
// apps/workers/mech-model/surrogate.py (eval_surrogate / is_ood): the
// browser must land on the identical number the worker's pytest pins,
// because the surrogate is an interpolator of the disclosed FD solver —
// NOT an LLM, NOT evidence (지시서 금지 목록), and poses outside the DOE
// envelope are flagged OOD and must never display as a normal result.

export interface ChannelModel {
  channel: string;
  centers_norm: number[][];
  weights: number[];
  mean: number;
  l2: number;
  lam: number;
  pred_log_lo: number;
  pred_log_hi: number;
  n_train: number;
  holdout: { rmse_fF: number; mae_fF: number; max_err_fF: number };
}

export interface SurrogatePayload {
  schema: string;
  tier: string;
  disclosure: string;
  layout: string;
  cell_mm: number;
  target_transform: string;
  doe: {
    seed: number;
    grid: string;
    n_bare: number;
    n_glove: number;
    ranges_mm: { x: [number, number]; y: [number, number]; gap: [number, number] };
  };
  channels: Record<string, ChannelModel>;
  glove_channels: Record<string, ChannelModel>;
  holdout_points: {
    bare: { x_mm: number; y_mm: number; gap_mm: number; is_glove: boolean }[];
    glove: { x_mm: number; y_mm: number; gap_mm: number; is_glove: boolean }[];
  };
}

export interface VolumePayload {
  schema: string;
  tier: string;
  disclosure: string;
  axes: { x_mm: number[]; y_mm: number[]; gap_mm: number[] };
  delta_c_fF: number[];
  detect_near: number[];
  detect_touch: number[];
  thresholds_fF: { near: number; touch: number | null };
  asic_config: Record<string, number | null>;
  layout_note: string;
  center_detection_gap_mm: { near: number; touch: number };
}

export interface FieldGridPayload {
  schema: string;
  tier: string;
  disclosure: string;
  layout: string;
  cell_mm: number;
  grid_shape: number[];
  baseline_sweeps: number;
  baseline_converged: boolean;
  curve: { distance_mm: number[]; delta_c_total_fF: number[] };
  touch_pose_channels_fF: Record<string, number>;
  potential_slice_y_mid: { plane: string; values: number[][] } | null;
  slice_note: string;
}

export interface AsicConfigPayload {
  gain_counts_per_fF: number;
  offset_counts: number;
  near_threshold_counts: number;
  touch_threshold_counts: number | null;
  noise_sigma_counts: number;
  adc_bits: number | null;
  ma_taps: number;
  ema_alpha: number;
  enter_near_counts: number;
  exit_near_counts: number;
  enter_touch_counts: number;
  exit_touch_counts: number;
  debounce_window: number;
  debounce_votes: number;
  [k: string]: unknown;
}

export interface TickRow {
  t_ms: number;
  x_mm: number;
  y_mm: number;
  gap_mm: number;
  is_glove: boolean;
  dc_fF: Record<string, number>;
  counts_truth: number;
  counts: number;
  baseline_v2: number;
  truth: AirState;
  v1: AirState;
  v2: AirState;
  ood?: boolean;
}

export type AirState = "IDLE" | "NEAR" | "TOUCH";

export interface ReplayPayload {
  schema: string;
  tier: string;
  disclosure: string;
  scenario_id: string;
  scenario_description: string;
  engine: string;
  seed: number;
  tick_period_s: number;
  asic_config: AsicConfigPayload;
  dc_thresholds_derived: { near_fF: number; touch_fF: number | null };
  channels: string[];
  expected: Record<string, number | boolean>;
  comparisons: Record<string, { expected_min?: number; expected_max?: number; expected?: unknown; actual: unknown; ok: boolean }>;
  pass: boolean;
  actual: {
    v1: { false_trigger_ticks: number; missed_ticks: number; state_changes: number; first_nonidle_tick: number | null };
    v2: { false_trigger_ticks: number; missed_ticks: number; state_changes: number; first_nonidle_tick: number | null };
    ood_flagged: boolean;
  };
  ticks: TickRow[];
}

export interface FingerPose {
  x_mm: number;
  y_mm: number;
  gap_mm: number;
  is_glove: boolean;
}

const RANGE_KEYS = ["x", "y", "gap"] as const;

function normalize(payload: SurrogatePayload, pose: FingerPose): [number, number, number] {
  const r = payload.doe.ranges_mm;
  return [
    (pose.x_mm - r.x[0]) / (r.x[1] - r.x[0]),
    (pose.y_mm - r.y[0]) / (r.y[1] - r.y[0]),
    (pose.gap_mm - r.gap[0]) / (r.gap[1] - r.gap[0]),
  ];
}

function evalChannel(m: ChannelModel, xn: [number, number, number]): number {
  let acc = 0;
  for (let i = 0; i < m.weights.length; i++) {
    const c = m.centers_norm[i];
    const d2 = (c[0] - xn[0]) ** 2 + (c[1] - xn[1]) ** 2 + (c[2] - xn[2]) ** 2;
    acc += m.weights[i] * Math.exp(-d2 / (2 * m.l2 * m.l2));
  }
  const pred = Math.min(Math.max(m.mean + acc, m.pred_log_lo), m.pred_log_hi);
  return 10 ** pred;
}

/** Per-channel ΔC (fF) for one pose — the exact formula the worker's pytest
 * pins as the TS-parity contract (targets log10-floored, output clamped). */
export function evalSurrogate(
  payload: SurrogatePayload,
  x_mm: number,
  y_mm: number,
  gap_mm: number,
  is_glove: boolean
): Record<string, number> {
  const table = is_glove ? payload.glove_channels : payload.channels;
  const xn = normalize(payload, { x_mm, y_mm, gap_mm, is_glove });
  const out: Record<string, number> = {};
  for (const [ch, m] of Object.entries(table)) out[ch] = evalChannel(m, xn);
  return out;
}

/** Outside the DOE envelope ⇒ OOD: the prediction must never display as a
 * normal result (GOLD-05 hover z=35 is the pinned scenario). */
export function isOod(payload: SurrogatePayload, x_mm: number, y_mm: number, gap_mm: number): boolean {
  const r = payload.doe.ranges_mm;
  return !RANGE_KEYS.every((_, i) => {
    const [lo, hi] = (i === 0 ? r.x : i === 1 ? r.y : r.gap) as [number, number];
    const v = i === 0 ? x_mm : i === 1 ? y_mm : gap_mm;
    return v >= lo && v <= hi;
  });
}

/** Provenance rule (signal_chain.AsicConfig.dc_threshold_fF): ΔC thresholds
 * are DERIVED from the counts config — never invented in fF. */
export function dcThresholdFf(cfg: AsicConfigPayload, counts: number): number {
  return (counts - cfg.offset_counts) / cfg.gain_counts_per_fF;
}

export const AIR_STATE_COLOR: Record<AirState, string> = {
  IDLE: "#64748b",
  NEAR: "#38bdf8",
  TOUCH: "#f97316",
};

/** Volume flat index — worker layout_note: "x-major within y within gap
 * (gap outer)": i = (gi·ny + yi)·nx + xi. */
export function volumeIndex(vol: VolumePayload, gi: number, yi: number, xi: number): number {
  return (gi * vol.axes.y_mm.length + yi) * vol.axes.x_mm.length + xi;
}
