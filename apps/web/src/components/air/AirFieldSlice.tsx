import { useEffect, useMemo, useRef } from "react";
import { useTranslation } from "react-i18next";
import type { FieldGridPayload, FingerPose } from "../../lib/air";

// Potential heatmap of the y=0 plane from the FD solver's field-grid
// artifact. POSE-DRIVEN: the artifact carries a library of solved poses
// (gap sweep at center + radial line at touch) and the panel displays the
// nearest solved pose to the live finger — a pure lookup of worker-computed
// fields, never interpolation or client-side physics (지시서: Three.js/
// 클라이언트 field 계산 금지). The color scale is FIXED across poses of one
// artifact so moving the finger shows comparable fields, not renormalized
// ones.
type SliceEntry = { pose: { x_mm: number; y_mm: number; gap_mm: number; is_glove: boolean }; slice: { plane: string; values: number[][] } };

const R_SPAN = 20; // mm — normalizes the radius axis of the lookup score
const G_SPAN = 35; // mm — normalizes the gap axis of the lookup score

function nearestSlice(entries: SliceEntry[], pose: FingerPose | null): { entry: SliceEntry; exact: boolean } | null {
  if (entries.length === 0) return null;
  if (!pose) return { entry: entries[0], exact: true };
  const r = Math.hypot(pose.x_mm, pose.y_mm);
  let best = entries[0];
  let bestScore = Infinity;
  for (const e of entries) {
    const er = Math.hypot(e.pose.x_mm, e.pose.y_mm);
    const score = ((er - r) / R_SPAN) ** 2 + ((e.pose.gap_mm - pose.gap_mm) / G_SPAN) ** 2;
    if (score < bestScore) {
      bestScore = score;
      best = e;
    }
  }
  const br = Math.hypot(best.pose.x_mm, best.pose.y_mm);
  const exact = Math.abs(br - r) < 1e-6 && Math.abs(best.pose.gap_mm - pose.gap_mm) < 1e-6;
  return { entry: best, exact };
}

export function AirFieldSlice({ field, pose }: { field: FieldGridPayload | null; pose: FingerPose | null }) {
  const { t } = useTranslation();
  const ref = useRef<HTMLCanvasElement>(null);

  // Fixed display scale: one lo/hi across every solved slice of this run.
  const [lo, hi] = useMemo(() => {
    let lo = Infinity;
    let hi = -Infinity;
    const scan = (rows: number[][]) => {
      for (const row of rows) for (const v of row) { if (v < lo) lo = v; if (v > hi) hi = v; }
    };
    if (field?.pose_slices?.length) {
      for (const p of field.pose_slices) scan(p.slice.values);
    } else if (field?.potential_slice_y_mid) {
      scan(field.potential_slice_y_mid.values);
    }
    return [lo === Infinity ? 0 : lo, hi === -Infinity ? 1 : hi];
  }, [field]);

  const picked = useMemo(() => {
    if (!field) return null;
    if (field.pose_slices?.length) return nearestSlice(field.pose_slices, pose);
    if (field.potential_slice_y_mid)
      return { entry: { pose: { x_mm: 0, y_mm: 0, gap_mm: 0, is_glove: false }, slice: field.potential_slice_y_mid }, exact: true };
    return null;
  }, [field, pose]);

  useEffect(() => {
    const canvas = ref.current;
    const rows = picked?.entry.slice.values;
    if (!canvas || !rows || rows.length === 0) return;
    const nx = rows.length;
    const nz = rows[0].length;
    const span = hi - lo || 1;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    const img = ctx.createImageData(nx, nz);
    for (let i = 0; i < nx; i++) {
      for (let j = 0; j < nz; j++) {
        // gamma tone map (display only — makes the faint mid-field readable
        // on the fixed 0–1 V scale; the solver values are untouched)
        const u = Math.pow(Math.min(1, Math.max(0, (rows[i][j] - lo) / span)), 0.45);
        // dark-blue → cyan → yellow colormap (fixed scale, see lo/hi)
        const r = Math.round(255 * Math.min(1, Math.max(0, 2.2 * u - 0.55)));
        const g = Math.round(255 * Math.min(1, Math.max(0, 1.6 * u)));
        const b = Math.round(60 + 195 * (1 - u));
        const px = (j * nx + i) * 4; // plane rows are x, cols are z → transpose for display
        img.data[px] = r;
        img.data[px + 1] = g;
        img.data[px + 2] = b;
        img.data[px + 3] = 255;
      }
    }
    ctx.putImageData(img, 0, 0);
    // Live lateral-position marker: a thin line at the finger's current x so
    // the eye connects the pose sliders to the slice's x axis. Display-level
    // geometry only (grid extent from the artifact's own metadata).
    const shape = field?.grid_shape;
    const cell = field?.cell_mm ?? 1;
    if (shape && shape.length === 3 && pose) {
      const stride = shape[0] / nx;
      const col = Math.round(pose.x_mm / cell / stride + shape[0] / 2 / stride);
      if (col >= 0 && col < nx) {
        ctx.fillStyle = "rgba(255,255,255,0.75)";
        ctx.fillRect(col, 0, 1, nz);
      }
    }
  }, [picked, lo, hi, field, pose]);

  if (!picked) {
    return <div style={{ fontSize: 12, opacity: 0.6 }}>{t("air.slice.unavailable")}</div>;
  }
  const p = picked.entry.pose;
  return (
    <div>
      <canvas
        ref={ref}
        width={picked.entry.slice.values.length}
        height={picked.entry.slice.values[0]?.length ?? 1}
        style={{ width: "100%", imageRendering: "pixelated", borderRadius: 6, border: "1px solid var(--alps-border-strong)" }}
      />
      <div style={{ fontSize: 11, opacity: 0.65, marginTop: 4 }}>
        {t("air.slice.solvedAt", { r: Math.hypot(p.x_mm, p.y_mm).toFixed(1), gap: p.gap_mm.toFixed(1) })}
        {!picked.exact && <span> {t("air.slice.nearest")}</span>}
        <div>
          {t("air.slice.scale", { lo: lo.toFixed(2), hi: hi.toFixed(2) })}
        </div>
        <div>{t("air.slice.note")}</div>
      </div>
    </div>
  );
}
