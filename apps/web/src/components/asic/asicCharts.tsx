// Small SVG charts for the ASIC workbench (correlation scatter §11.2, yield
// trend / bin Pareto / SPC control chart §13.2). Kept dependency-free — same
// slate/cyan palette as the rest of the twin.

import { useSvgPalette } from "../../ui/useTheme";

export function Scatter({
  points,
  xLabel,
  yLabel,
  height = 190,
}: {
  points: [number, number][];
  xLabel: string;
  yLabel: string;
  height?: number;
}) {
  const W = 320;
  const c = useSvgPalette();
  const P = 34;
  const all = points.flat();
  const lo = Math.min(...all);
  const hi = Math.max(...all);
  const pad = (hi - lo) * 0.08 || 1;
  const a = lo - pad;
  const b = hi + pad;
  const x = (v: number) => P + ((v - a) / (b - a)) * (W - P - 8);
  const y = (v: number) => height - 22 - ((v - a) / (b - a)) * (height - 34);
  return (
    <svg width={W} height={height} style={{ display: "block", maxWidth: "100%" }}>
      <line x1={P} y1={height - 22} x2={W - 8} y2={height - 22} stroke={c.axis} />
      <line x1={P} y1={12} x2={P} y2={height - 22} stroke={c.axis} />
      {/* y = x reference: prediction should land on measurement */}
      <line x1={x(a)} y1={y(a)} x2={x(b)} y2={y(b)} stroke={c.faint} strokeDasharray="4 3" />
      {points.map(([px, m], i) => (
        <circle key={i} cx={x(px)} cy={y(m)} r={2.6} fill={c.series[0]} opacity={0.85} />
      ))}
      <text x={(W + P) / 2} y={height - 6} fill={c.dim} fontSize={9} textAnchor="middle">{xLabel}</text>
      <text x={10} y={16} fill={c.dim} fontSize={9}>{yLabel}</text>
    </svg>
  );
}

export function TrendLine({
  values,
  labels,
  yLabel,
  height = 170,
}: {
  values: number[];
  labels: string[];
  yLabel: string;
  height?: number;
}) {
  const W = 320;
  const c = useSvgPalette();
  const P = 34;
  const lo = Math.min(...values) - 1.5;
  const hi = Math.max(...values) + 1.5;
  const x = (i: number) => P + (i / Math.max(1, values.length - 1)) * (W - P - 10);
  const y = (v: number) => height - 22 - ((v - lo) / (hi - lo)) * (height - 34);
  const path = values.map((v, i) => `${i ? "L" : "M"}${x(i)},${y(v)}`).join(" ");
  return (
    <svg width={W} height={height} style={{ display: "block", maxWidth: "100%" }}>
      <line x1={P} y1={height - 22} x2={W - 10} y2={height - 22} stroke={c.axis} />
      <line x1={P} y1={12} x2={P} y2={height - 22} stroke={c.axis} />
      <path d={path} fill="none" stroke={c.series[1]} strokeWidth={1.6} />
      {values.map((v, i) => (
        <g key={i}>
          <circle cx={x(i)} cy={y(v)} r={2.6} fill={c.series[1]} />
          <text x={x(i)} y={height - 8} fill={c.dim} fontSize={8} textAnchor="middle" fontFamily="monospace">{labels[i]}</text>
        </g>
      ))}
      <text x={10} y={16} fill={c.dim} fontSize={9}>{yLabel}</text>
    </svg>
  );
}

export function Pareto({ bars, height = 170 }: { bars: { label: string; value: number }[]; height?: number }) {
  const W = 320;
  const c = useSvgPalette();
  const P = 30;
  const max = Math.max(...bars.map((b) => b.value)) || 1;
  const bw = (W - P - 10) / bars.length;
  const colors = c.series;
  return (
    <svg width={W} height={height} style={{ display: "block", maxWidth: "100%" }}>
      <line x1={P} y1={height - 22} x2={W - 10} y2={height - 22} stroke={c.axis} />
      {bars.map((b, i) => {
        const h = ((height - 40) * b.value) / max;
        return (
          <g key={b.label}>
            <rect x={P + i * bw + 4} y={height - 22 - h} width={bw - 8} height={h} fill={colors[i % colors.length]} rx={2} />
            <text x={P + i * bw + bw / 2} y={height - 22 - h - 4} fill={c.body} fontSize={9} textAnchor="middle" fontFamily="monospace">
              {b.value}
            </text>
            <text x={P + i * bw + bw / 2} y={height - 8} fill={c.dim} fontSize={8} textAnchor="middle">{b.label}</text>
          </g>
        );
      })}
    </svg>
  );
}

// MC/corner sample histogram with spec-limit rails (지시서 v1.1 EPIC A D04).
// bins/counts come pre-computed by the caller from the raw draw samples — the
// SVG stays a dumb renderer like the rest of this file.
export function Histogram({
  values,
  specMin,
  specMax,
  height = 150,
}: {
  values: number[];
  specMin?: number | null;
  specMax?: number | null;
  height?: number;
}) {
  const W = 320;
  const c = useSvgPalette();
  const P = 30;
  if (values.length === 0) return null;
  let lo = Math.min(...values);
  let hi = Math.max(...values);
  if (specMin != null) lo = Math.min(lo, specMin);
  if (specMax != null) hi = Math.max(hi, specMax);
  const pad = (hi - lo) * 0.06 || 1;
  lo -= pad;
  hi += pad;
  const nb = 24;
  const w = (hi - lo) / nb;
  const counts = new Array(nb).fill(0);
  for (const v of values) {
    const b = Math.min(nb - 1, Math.max(0, Math.floor((v - lo) / w)));
    counts[b] += 1;
  }
  const max = Math.max(...counts) || 1;
  const x = (v: number) => P + ((v - lo) / (hi - lo)) * (W - P - 8);
  const y = (c: number) => height - 20 - (c / max) * (height - 34);
  return (
    <svg width={W} height={height} style={{ display: "block", maxWidth: "100%" }}>
      <line x1={P} y1={height - 20} x2={W - 8} y2={height - 20} stroke={c.axis} />
      {/* bin 개수 매개변수는 n — c(팔레트)로 두면 가려져 c.series 크래시 */}
      {counts.map((n, i) => (
        <rect key={i} x={x(lo + i * w)} y={y(n)} width={Math.max(1, (W - P - 8) / nb - 1)} height={height - 20 - y(n)} fill={c.series[0]} opacity={0.75} rx={1} />
      ))}
      {specMin != null && (
        <>
          <line x1={x(specMin)} y1={10} x2={x(specMin)} y2={height - 20} stroke={c.series[3]} strokeDasharray="4 3" />
          <text x={x(specMin)} y={9} fill={c.series[3]} fontSize={8} textAnchor="middle" fontFamily="monospace">min</text>
        </>
      )}
      {specMax != null && (
        <>
          <line x1={x(specMax)} y1={10} x2={x(specMax)} y2={height - 20} stroke={c.series[3]} strokeDasharray="4 3" />
          <text x={x(specMax)} y={9} fill={c.series[3]} fontSize={8} textAnchor="middle" fontFamily="monospace">max</text>
        </>
      )}
      <text x={P} y={height - 6} fill={c.dim} fontSize={8} fontFamily="monospace">{lo.toFixed(2)}</text>
      <text x={W - 8} y={height - 6} fill={c.dim} fontSize={8} textAnchor="end" fontFamily="monospace">{hi.toFixed(2)}</text>
    </svg>
  );
}

export function SpcChart({
  points,
  ucl,
  lcl,
  target,
  violIdx,
  height = 170,
}: {
  points: number[];
  ucl: number;
  lcl: number;
  target: number;
  violIdx: number[];
  height?: number;
}) {
  const W = 320;
  const c = useSvgPalette();
  const P = 34;
  const lo = Math.min(lcl, ...points) - 0.02;
  const hi = Math.max(ucl, ...points) + 0.02;
  const x = (i: number) => P + (i / Math.max(1, points.length - 1)) * (W - P - 10);
  const y = (v: number) => height - 20 - ((v - lo) / (hi - lo)) * (height - 32);
  // x-charts plot per-subgroup means; the lot table feeds pre-aggregated spc
  // rows, so flatten to a plain run chart with control limits.
  const flat = points;
  const path = flat.map((v, i) => `${i ? "L" : "M"}${x(i)},${y(v)}`).join(" ");
  return (
    <svg width={W} height={height} style={{ display: "block", maxWidth: "100%" }}>
      <line x1={P} y1={height - 20} x2={W - 10} y2={height - 20} stroke={c.axis} />
      <line x1={P} y1={y(ucl)} x2={W - 10} y2={y(ucl)} stroke={c.series[3]} strokeDasharray="4 3" />
      <line x1={P} y1={y(lcl)} x2={W - 10} y2={y(lcl)} stroke={c.series[3]} strokeDasharray="4 3" />
      <line x1={P} y1={y(target)} x2={W - 10} y2={y(target)} stroke={c.faint} />
      <path d={path} fill="none" stroke={c.series[4]} strokeWidth={1.6} />
      {flat.map((v, i) => (
        <circle key={i} cx={x(i)} cy={y(v)} r={violIdx.includes(i) ? 4 : 2.4} fill={violIdx.includes(i) ? c.series[3] : c.series[4]} />
      ))}
      <text x={W - 12} y={y(ucl) - 3} fill={c.series[3]} fontSize={8} textAnchor="end">UCL</text>
      <text x={W - 12} y={y(lcl) + 9} fill={c.series[3]} fontSize={8} textAnchor="end">LCL</text>
    </svg>
  );
}
