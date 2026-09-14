import { useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import type { FieldGridPayload } from "../../lib/air";

// Potential heatmap of the y=0 plane at the touch pose, from the FD solver's
// field-grid artifact (values downsampled worker-side for transport). Pure
// canvas rendering of solver OUTPUT — no physics computed here (지시서:
// Three.js/클라이언트 field 계산 금지).
export function AirFieldSlice({ field }: { field: FieldGridPayload | null }) {
  const { t } = useTranslation();
  const ref = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = ref.current;
    const slice = field?.potential_slice_y_mid;
    if (!canvas || !slice || slice.values.length === 0) return;
    const rows = slice.values;
    const nx = rows.length;
    const nz = rows[0].length;
    let lo = Infinity;
    let hi = -Infinity;
    for (const row of rows) for (const v of row) { if (v < lo) lo = v; if (v > hi) hi = v; }
    const span = hi - lo || 1;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    const img = ctx.createImageData(nx, nz);
    for (let i = 0; i < nx; i++) {
      for (let j = 0; j < nz; j++) {
        const u = (rows[i][j] - lo) / span;
        // dark-blue → cyan → yellow colormap
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
  }, [field]);

  if (!field?.potential_slice_y_mid) {
    return <div style={{ fontSize: 12, opacity: 0.6 }}>{t("air.slice.unavailable")}</div>;
  }
  return (
    <div>
      <canvas
        ref={ref}
        width={field.potential_slice_y_mid.values.length}
        height={field.potential_slice_y_mid.values[0]?.length ?? 1}
        style={{ width: "100%", imageRendering: "pixelated", borderRadius: 6, border: "1px solid #334155" }}
      />
      <div style={{ fontSize: 11, opacity: 0.65, marginTop: 4 }}>{t("air.slice.note")}</div>
    </div>
  );
}
