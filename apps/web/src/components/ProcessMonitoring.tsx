import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import type { TFunction } from "i18next";
import {
  api,
  type AnomalyExplanation,
  type ControlChart,
  type ControlChartPoint,
  type ProcessParameterInfo,
} from "../lib/api";
import { seedTr } from "../lib/seedL10n";
import { bg, emboss, fontMono, radius } from "../ui/tokens";

const RULE_KEYS: Record<
  string,
  "proc.mon.rules.beyond_3_sigma" | "proc.mon.rules.two_of_three_beyond_2_sigma" | "proc.mon.rules.run_of_7_same_side"
> = {
  beyond_3_sigma: "proc.mon.rules.beyond_3_sigma",
  two_of_three_beyond_2_sigma: "proc.mon.rules.two_of_three_beyond_2_sigma",
  run_of_7_same_side: "proc.mon.rules.run_of_7_same_side",
};

const ruleLabel = (t: TFunction, rule: string) => {
  const key = RULE_KEYS[rule];
  return key ? t(key) : rule;
};

const W = 600;
const H = 220;
const PAD = { l: 52, r: 12, t: 12, b: 26 };

function chartScale(chart: ControlChart) {
  const values = chart.points.map((p) => p.value);
  let lo = Math.min(...values);
  let hi = Math.max(...values);
  for (const v of [chart.lcl, chart.ucl]) {
    if (v !== null) {
      lo = Math.min(lo, v);
      hi = Math.max(hi, v);
    }
  }
  const pad = (hi - lo) * 0.08 || Math.abs(hi) * 0.05 || 0.01;
  lo -= pad;
  hi += pad;
  const x = (i: number) =>
    PAD.l + (i / Math.max(chart.points.length - 1, 1)) * (W - PAD.l - PAD.r);
  const y = (v: number) => PAD.t + (1 - (v - lo) / (hi - lo)) * (H - PAD.t - PAD.b);
  return { x, y, lo, hi };
}

function PointMark({ p, cx, cy }: { p: ControlChartPoint; cx: number; cy: number }) {
  const { t } = useTranslation();
  const rules = p.violations.map((r) => ruleLabel(t, r)).join(", ");
  const title = [
    `${p.lot_business_id} · ${p.process_run_business_id}`,
    `${p.cavity_label} · ${p.value}`,
    p.excluded_from_limits ? t("proc.mon.legend.excluded") : null,
    rules || null,
  ]
    .filter(Boolean)
    .join("\n");
  if (p.excluded_from_limits)
    return <circle cx={cx} cy={cy} r={4.5} fill="none" stroke="#f87171" strokeWidth={2}><title>{title}</title></circle>;
  if (p.violations.length > 0)
    return <circle cx={cx} cy={cy} r={4.5} fill="#fbbf24"><title>{title}</title></circle>;
  return <circle cx={cx} cy={cy} r={3.5} fill="#60a5fa"><title>{title}</title></circle>;
}

function ChartSvg({ chart }: { chart: ControlChart }) {
  const { t } = useTranslation();
  const { x, y, hi, lo } = chartScale(chart);
  const fmt = (v: number) => (Math.abs(v) >= 1000 ? v.toFixed(0) : String(Math.round(v * 1e4) / 1e4));
  const path = chart.points.map((p, i) => `${i === 0 ? "M" : "L"}${x(i)},${y(p.value)}`).join(" ");

  return (
    // The chart sits in a sunken readout well — same bezel family as the KPI
    // tiles — with the in-control band faintly tinted and the trace glowing
    // softly above it (matches the ECharts trace-glow look in ui/chartTheme).
    <svg
      viewBox={`0 0 ${W} ${H}`}
      style={{
        width: "100%",
        maxWidth: 760,
        display: "block",
        background: bg.metalWell,
        borderRadius: radius.sm,
        boxShadow: emboss.well,
      }}
      role="img"
    >
      {chart.lcl !== null && chart.ucl !== null && (
        <rect
          x={PAD.l}
          y={y(chart.ucl)}
          width={W - PAD.l - PAD.r}
          height={Math.max(y(chart.lcl) - y(chart.ucl), 0)}
          fill="rgba(251, 191, 36, 0.045)"
        />
      )}
      {[hi, lo].map((v, i) => (
        <g key={i}>
          <line x1={PAD.l} x2={W - PAD.r} y1={y(v)} y2={y(v)} stroke="#1e293b" strokeWidth={1} />
          <text x={PAD.l - 6} y={y(v) + 3.5} textAnchor="end" fontSize={10} fill="#64748b" fontFamily={fontMono}>{fmt(v)}</text>
        </g>
      ))}
      {chart.center_line !== null && (
        <line x1={PAD.l} x2={W - PAD.r} y1={y(chart.center_line)} y2={y(chart.center_line)} stroke="#94a3b8" strokeWidth={1.2} />
      )}
      {[chart.lcl, chart.ucl].map((v, i) =>
        v !== null ? (
          <line key={i} x1={PAD.l} x2={W - PAD.r} y1={y(v)} y2={y(v)} stroke="#fbbf24" strokeWidth={1.2} strokeDasharray="6 4" />
        ) : null,
      )}
      <path
        d={path}
        fill="none"
        stroke="#60a5fa"
        strokeWidth={1.4}
        opacity={0.85}
        style={{ filter: "drop-shadow(0 0 3px rgba(96, 165, 250, 0.45))" }}
      />
      {chart.points.map((p, i) => (
        <PointMark key={p.process_run_business_id} p={p} cx={x(i)} cy={y(p.value)} />
      ))}
      {/* §5.1: icon + text together, never colour alone */}
      <g fontSize={10} fill="#94a3b8">
        <circle cx={PAD.l + 8} cy={H - 8} r={3.5} fill="#60a5fa" />
        <text x={PAD.l + 16} y={H - 4.5}>{t("proc.mon.legend.inControl")}</text>
        <circle cx={PAD.l + 118} cy={H - 8} r={4.5} fill="#fbbf24" />
        <text x={PAD.l + 126} y={H - 4.5}>{t("proc.mon.legend.violation")}</text>
        <circle cx={PAD.l + 236} cy={H - 8} r={4.5} fill="none" stroke="#f87171" strokeWidth={2} />
        <text x={PAD.l + 244} y={H - 4.5}>{t("proc.mon.legend.excluded")}</text>
      </g>
    </svg>
  );
}

function HypothesisCard({ chart }: { chart: ControlChart }) {
  const { t, i18n } = useTranslation();
  // facts_used are composed backend f-strings; disclaimer is a seeded string.
  // (hypo.hypothesis itself is LLM output, already following ui_language.)
  const tr = (s: string) => seedTr(s, i18n.resolvedLanguage);
  const [hypo, setHypo] = useState<AnomalyExplanation | null>(null);
  const [busy, setBusy] = useState(false);

  const load = () => {
    setBusy(true);
    api
      .anomalyExplanation(chart.variant_id, chart.parameter)
      .then(setHypo)
      .catch(() => setHypo(null))
      .finally(() => setBusy(false));
  };

  if (!hypo)
    return (
      <button
        onClick={load}
        disabled={busy}
        style={{ marginTop: 8, padding: "5px 10px", borderRadius: 6, background: "#1e293b", color: "#e2e8f0", border: "1px solid #334155", cursor: busy ? "wait" : "pointer", fontSize: 12 }}
      >
        {busy ? t("proc.mon.hypoLoading") : t("proc.mon.hypoButton")}
      </button>
    );

  return (
    <div style={{ marginTop: 10, background: "#0b1220", borderLeft: "3px solid #60a5fa", borderRadius: 6, padding: "8px 10px" }}>
      <div style={{ display: "flex", gap: 6, alignItems: "baseline", flexWrap: "wrap", marginBottom: 4 }}>
        <span style={{ background: "#60a5fa", color: "#0b1220", padding: "0 6px", borderRadius: 4, fontWeight: 700, fontSize: 10 }}>
          {t("proc.mon.hypoTitle")}
        </span>
        <span style={{ fontSize: 10, opacity: 0.6 }}>
          {t("proc.mon.model")}: {hypo.model}
        </span>
      </div>
      <div style={{ fontSize: 12, lineHeight: 1.55 }}>{hypo.hypothesis}</div>
      {hypo.facts_used.length > 0 && (
        <div style={{ marginTop: 6 }}>
          <div style={{ fontSize: 10.5, opacity: 0.6, marginBottom: 3 }}>{t("proc.mon.facts")}</div>
          <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
            {hypo.facts_used.map((f, i) => (
              <span key={i} style={{ background: "#1e293b", borderRadius: 4, padding: "1px 6px", fontSize: 10.5 }}>
                {tr(f)}
              </span>
            ))}
          </div>
        </div>
      )}
      <div style={{ fontSize: 11, opacity: 0.55, marginTop: 6 }}>{tr(hypo.disclaimer)}</div>
    </div>
  );
}

/** AN-03 관리도 + AI-03 이상 설명. Read-only over the P1 rows: control
 * limits are robust stats of the measured process (never spec limits — the
 * server note under the chart says so verbatim), out-of-window points stay
 * on the chart but are excluded from the limit basis, and the AI answer is
 * an investigation hypothesis, never a confirmed cause. */
export function ProcessMonitoring({ variantId, initialParameter }: { variantId: string; initialParameter?: string }) {
  const { t, i18n } = useTranslation();
  // chart.note is a composed backend string (control-limit basis note).
  const tr = (s: string) => seedTr(s, i18n.resolvedLanguage);
  const [params, setParams] = useState<ProcessParameterInfo[]>([]);
  const [parameter, setParameter] = useState<string | null>(null);
  const [chart, setChart] = useState<ControlChart | null>(null);
  // initialParameter is a mount-time hint (factory station drawer remounts
  // this chart per open) — captured once so the effect stays variant-scoped.
  const initialHint = useRef(initialParameter);

  useEffect(() => {
    let cancelled = false;
    setParams([]);
    setParameter(null);
    setChart(null);
    api
      .listProcessParameters(variantId)
      .then((ps) => {
        if (cancelled) return;
        setParams(ps);
        // initialParameter preselects once at load (factory station drawer);
        // unknown or absent falls back to the first parameter as before.
        setParameter(
          (initialHint.current && ps.find((p) => p.parameter === initialHint.current)?.parameter) ??
            ps[0]?.parameter ??
            null
        );
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [variantId]);

  useEffect(() => {
    if (!parameter) return;
    let cancelled = false;
    setChart(null);
    api
      .controlChart(variantId, parameter)
      .then((c) => !cancelled && setChart(c))
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [variantId, parameter]);

  if (params.length === 0)
    return (
      <div style={{ fontSize: 12.5, fontWeight: 700, margin: "14px 0 6px" }}>
        {t("proc.mon.title")}
        <span style={{ fontWeight: 400, opacity: 0.6, marginLeft: 8, fontSize: 11.5 }}>{t("proc.mon.noData")}</span>
      </div>
    );

  const selected = params.find((p) => p.parameter === parameter) ?? null;
  const excludedPoints = chart?.points.filter((p) => p.excluded_from_limits) ?? [];

  return (
    <div>
      <div style={{ fontSize: 12.5, fontWeight: 700, margin: "14px 0 6px", display: "flex", gap: 10, alignItems: "baseline", flexWrap: "wrap" }}>
        {t("proc.mon.title")}
        <select
          value={parameter ?? ""}
          onChange={(e) => setParameter(e.target.value)}
          style={{ background: "#0b1220", color: "#e2e8f0", border: "1px solid #334155", borderRadius: 6, fontSize: 12, padding: "3px 6px" }}
        >
          {params.map((p) => (
            <option key={p.parameter} value={p.parameter}>
              {p.parameter}
              {p.unit ? ` (${p.unit})` : ""} · n={p.n_points}
            </option>
          ))}
        </select>
        {selected && (
          <span style={{ fontWeight: 400, opacity: 0.6, fontSize: 11 }}>
            {t("proc.mon.nBasis", { n: chart?.n_basis ?? 0, total: selected.n_points })}
          </span>
        )}
      </div>

      {chart ? (
        <>
          <ChartSvg chart={chart} />
          <div style={{ fontSize: 11, opacity: 0.6, marginTop: 4, maxWidth: 760 }}>{tr(chart.note)}</div>
          <div style={{ fontSize: 11, marginTop: 6 }}>
            <span style={{ opacity: 0.6 }}>{t("proc.mon.hits")}: </span>
            {chart.rule_hits.length === 0 ? (
              <span style={{ opacity: 0.6 }}>{t("proc.mon.noHits")}</span>
            ) : (
              chart.rule_hits.map((r) => (
                <span key={r} style={{ background: "#78350f", color: "#fbbf24", borderRadius: 4, padding: "1px 6px", fontSize: 10.5, marginRight: 4 }}>
                  ▲ {ruleLabel(t, r)}
                </span>
              ))
            )}
          </div>
          {excludedPoints.length > 0 && (
            <div style={{ fontSize: 11, marginTop: 3 }}>
              <span style={{ opacity: 0.6 }}>{t("proc.mon.excludedList")}: </span>
              {excludedPoints.map((p) => (
                <span key={p.process_run_business_id} style={{ color: "#f87171", marginRight: 8 }} title={p.exclusion_reason ?? undefined}>
                  {p.lot_business_id} ({p.process_run_business_id})
                </span>
              ))}
            </div>
          )}
          <HypothesisCard chart={chart} />
        </>
      ) : (
        <div style={{ fontSize: 12, opacity: 0.6, maxWidth: 760 }}>…</div>
      )}
    </div>
  );
}
