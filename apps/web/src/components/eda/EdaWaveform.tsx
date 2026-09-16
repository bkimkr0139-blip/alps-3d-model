import { useState } from "react";
import { useTranslation } from "react-i18next";
import type { Waveform, WaveSignal } from "./edaRunner";

// SVG waveform browser — port of AgentIC's WaveformViewer.tsx (same bit/bus
// rendering, cursor line, and value-at-cursor table; colors matched to the
// ALPS slate/cyan theme).

export function EdaWaveform({ data }: { data: Waveform | null }) {
  const { t } = useTranslation();
  const [cursor, setCursor] = useState(0);
  if (!data) return <div style={{ fontSize: 12, color: "var(--alps-text-faint)" }}>{t("eda.wave.empty")}</div>;

  const W = 640;
  const ROW = 30;
  const PAD = 96;
  const tEnd = Math.max(1, data.end_time);
  const xOf = (tt: number) => PAD + (tt / tEnd) * (W - PAD - 10);

  const valueAt = (s: WaveSignal, tt: number) => {
    let v = "x";
    for (const [tv, vv] of s.transitions) {
      if (tv <= tt) v = vv;
      else break;
    }
    return v;
  };

  const onClick = (e: React.MouseEvent) => {
    const rect = (e.currentTarget as HTMLDivElement).getBoundingClientRect();
    const x = e.clientX - rect.left;
    setCursor(Math.max(0, Math.round(((x - PAD) / (W - PAD - 10)) * tEnd)));
  };

  return (
    <div style={{ background: "#020617", border: "1px solid #1e293b", borderRadius: 8, padding: 10, overflowX: "auto" }}>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 6, fontSize: 11, color: "#94a3b8" }}>
        <span>
          timescale: {data.timescale} · end: {tEnd}ns
        </span>
        <span>
          {t("eda.wave.cursor")}: <span style={{ color: "#22d3ee", fontFamily: "monospace" }}>{cursor}</span>
        </span>
      </div>
      <div onClick={onClick} style={{ cursor: "crosshair", width: W, height: data.signals.length * ROW + 16 }}>
        <svg width={W} height={data.signals.length * ROW + 16} style={{ display: "block" }}>
          {data.signals.map((s, i) => {
            const y = i * ROW + 14;
            return (
              <g key={s.name}>
                <text x={4} y={y + 4} fill="#94a3b8" fontSize={10} fontFamily="monospace">
                  {s.name}
                  {s.width > 1 ? `[${s.width - 1}:0]` : ""}
                </text>
                <line x1={PAD} y1={y + 12} x2={W - 6} y2={y + 12} stroke="#1e293b" />
                {s.width === 1 ? bitWave(s, xOf, y, tEnd) : busWave(s, xOf, y, tEnd)}
              </g>
            );
          })}
          <line x1={xOf(cursor)} y1={0} x2={xOf(cursor)} y2={data.signals.length * ROW} stroke="#22d3ee" strokeWidth={1} />
        </svg>
      </div>
      <table style={{ marginTop: 8, fontSize: 11, width: "100%", borderCollapse: "collapse" }}>
        <thead>
          <tr style={{ color: "#8b99b5" }}>
            <th style={{ textAlign: "left" }}>signal</th>
            <th style={{ textAlign: "left" }}>value @ cursor</th>
          </tr>
        </thead>
        <tbody>
          {data.signals.map((s) => (
            <tr key={s.name} style={{ borderTop: "1px solid var(--alps-border-base)" }}>
              <td style={{ padding: "3px 0", fontFamily: "monospace", color: "#cbd5e1" }}>{s.name}</td>
              <td style={{ padding: "3px 0", fontFamily: "monospace", color: "#22d3ee" }}>
                {s.width > 1 ? prettyBus(valueAt(s, cursor)) : valueAt(s, cursor)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function bitWave(s: WaveSignal, xOf: (t: number) => number, y: number, tEnd: number) {
  const segs: React.ReactNode[] = [];
  let prevT = 0;
  let prevV = "x";
  for (const [tt, v] of s.transitions) {
    const x1 = xOf(prevT);
    const x2 = xOf(tt);
    const yy = prevV === "1" ? y + 3 : y + 20;
    segs.push(<line key={`h${tt}`} x1={x1} y1={yy} x2={x2} y2={yy} stroke="#22d3ee" strokeWidth={1.5} />);
    if (v !== prevV) segs.push(<line key={`v${tt}`} x1={x2} y1={y + 3} x2={x2} y2={y + 20} stroke="#22d3ee" strokeWidth={1.5} />);
    prevT = tt;
    prevV = v;
  }
  segs.push(
    <line
      key="tail"
      x1={xOf(prevT)}
      y1={prevV === "1" ? y + 3 : y + 20}
      x2={xOf(tEnd)}
      y2={prevV === "1" ? y + 3 : y + 20}
      stroke="#22d3ee"
      strokeWidth={1.5}
    />,
  );
  return segs;
}

function busWave(s: WaveSignal, xOf: (t: number) => number, y: number, tEnd: number) {
  const segs: React.ReactNode[] = [];
  let prevT = 0;
  let prevV = "0";
  const drawSeg = (t1: number, t2: number, v: string) => {
    if (t2 <= t1) return; // static signal (single t=0 sample) — nothing to draw
    const x1 = xOf(t1);
    const x2 = xOf(t2);
    segs.push(
      <polygon
        key={`p${t1}`}
        points={`${x1},${y + 12} ${x1 + 3},${y + 3} ${x2 - 3},${y + 3} ${x2},${y + 12} ${x2 - 3},${y + 20} ${x1 + 3},${y + 20}`}
        fill="#0f172a"
        stroke="#a78bfa"
        strokeWidth={1}
      />,
    );
    // clip the hex label to what the segment can hold (~5.5 px/char at 9 px)
    const full = prettyBus(v);
    const label = full.slice(0, Math.max(1, Math.floor((x2 - x1 - 8) / 5.5)));
    segs.push(
      <text key={`t${t1}`} x={(x1 + x2) / 2} y={y + 15} fontSize={9} fill="#e9d5ff" textAnchor="middle" fontFamily="monospace">
        {label}
      </text>,
    );
  };
  for (const [tt, v] of s.transitions) {
    drawSeg(prevT, tt, prevV);
    prevT = tt;
    prevV = v;
  }
  drawSeg(prevT, tEnd, prevV);
  return segs;
}

function prettyBus(bits: string): string {
  if (/^[01]+$/.test(bits))
    return (
      parseInt(bits, 2)
        .toString(16)
        .toUpperCase()
        .padStart(Math.ceil(bits.length / 4), "0") + "h"
    );
  return bits;
}
