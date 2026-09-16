import { useEffect, useMemo, useState } from "react";
import ReactECharts from "echarts-for-react";
import { useTranslation } from "react-i18next";
import { api, type DoeStudy, type ProcessOperationDto } from "../lib/api";
import { seedTr } from "../lib/seedL10n";
import { chartAxis, chartBase } from "../ui/chartTheme";

/** One (operation, parameter) pair a DOE study can be run against — every
 * operation window bound is a candidate regression target. */
interface ParamOption {
  key: string;
  operationId: string;
  operationName: string;
  parameter: string;
  unit: string | null;
}

function paramOptions(operations: ProcessOperationDto[]): ParamOption[] {
  const out: ParamOption[] = [];
  for (const op of operations) {
    for (const bound of op.window ?? []) {
      out.push({
        key: `${op.id}:${bound.parameter}`,
        operationId: op.id,
        operationName: op.name,
        parameter: bound.parameter,
        unit: bound.unit,
      });
    }
  }
  return out;
}

/** AN-04 DOE / optimization: response-surface sensitivity (linear fit) +
 * ranked candidate comparison over already-persisted process-run/CTQ data.
 * Regression + ranking are check-required investigation support, never a
 * finalized "optimal" answer (§7: AI가 단일 해를 임의 확정하지 않는다) —
 * see study.disclaimer, always shown verbatim. */
export function DoeStudyPanel({
  variantId,
  defaultTargetBand,
}: {
  variantId: string;
  defaultTargetBand?: { min: number; max: number; unit?: string };
}) {
  const { t, i18n } = useTranslation();
  const [operations, setOperations] = useState<ProcessOperationDto[]>([]);
  const [studies, setStudies] = useState<DoeStudy[]>([]);
  const [selectedKey, setSelectedKey] = useState<string>("");
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // operationName is a seeded DB string (process-op name) — overlay per ui lang.
  const tr = (s: string) => seedTr(s, i18n.resolvedLanguage);

  const options = useMemo(() => paramOptions(operations), [operations]);

  useEffect(() => {
    api.listProcessOperations().then(setOperations).catch(() => {});
    api.listDoeStudies(variantId).then(setStudies).catch(() => {});
  }, [variantId]);

  if (options.length === 0) return null;

  const selected = options.find((o) => o.key === selectedKey) ?? options[0];
  const latest = studies[0] ?? null;

  const runStudy = async () => {
    setRunning(true);
    setError(null);
    try {
      const study = await api.runDoeStudy({
        business_id: `DOE-${selected.parameter}-${Date.now()}`,
        variant_id: variantId,
        operation_id: selected.operationId,
        parameter: selected.parameter,
        metric: "peak",
        target_band: defaultTargetBand,
        candidate_grid_size: 5,
      });
      setStudies((prev) => [study, ...prev]);
    } catch {
      setError(t("doe.runError"));
    } finally {
      setRunning(false);
    }
  };

  return (
    <div style={{ marginTop: 14 }}>
      <div style={{ fontSize: 12.5, fontWeight: 700, marginBottom: 6 }}>{t("doe.title")}</div>
      <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
        <select
          value={selected.key}
          onChange={(e) => setSelectedKey(e.target.value)}
          style={{ padding: "5px 8px", borderRadius: 6, background: "#1e293b", color: "white", border: "1px solid #334155", fontSize: 12 }}
        >
          {options.map((o) => (
            <option key={o.key} value={o.key}>
              {tr(o.operationName)} — {o.parameter}
              {o.unit ? ` (${o.unit})` : ""}
            </option>
          ))}
        </select>
        <button
          onClick={runStudy}
          disabled={running}
          style={{ padding: "5px 10px", borderRadius: 6, background: "#1e293b", color: "#e2e8f0", border: "1px solid #334155", cursor: running ? "default" : "pointer", fontSize: 12 }}
        >
          {running ? t("doe.loading") : t("doe.runButton")}
        </button>
      </div>
      {error && <div style={{ fontSize: 11.5, color: "#f87171", marginTop: 4 }}>{error}</div>}

      {latest ? (
        <DoeStudyResult study={latest} />
      ) : (
        <div style={{ fontSize: 12, opacity: 0.6, marginTop: 8 }}>{t("doe.empty")}</div>
      )}
    </div>
  );
}

function DoeStudyResult({ study }: { study: DoeStudy }) {
  const { t, i18n } = useTranslation();
  const tr = (s: string) => seedTr(s, i18n.resolvedLanguage);
  const fit = study.fit;
  const sign = fit.slope > 0 ? "+" : "";

  const xs = [...study.observations.map((o) => o.parameter_value), ...study.candidates.map((c) => c.parameter_value)];
  const xMin = Math.min(...xs);
  const xMax = Math.max(...xs);
  const trendLine = [
    [xMin, fit.slope * xMin + fit.intercept],
    [xMax, fit.slope * xMax + fit.intercept],
  ];

  const option = {
    ...chartBase,
    legend: {
      ...chartBase.legend,
      data: [t("doe.chart.observed"), t("doe.chart.fitted")],
      top: 0,
    },
    grid: { left: 50, right: 20, top: 30, bottom: 36 },
    xAxis: {
      type: "value",
      name: `${study.parameter}${study.parameter_unit ? ` (${study.parameter_unit})` : ""}`,
      nameLocation: "middle",
      nameGap: 26,
      ...chartAxis(),
    },
    yAxis: {
      type: "value",
      name: study.metric_unit ?? study.metric,
      ...chartAxis(),
    },
    tooltip: { ...chartBase.tooltip, trigger: "item" },
    series: [
      {
        name: t("doe.chart.observed"),
        type: "scatter",
        symbolSize: 8,
        data: study.observations.map((o) => [o.parameter_value, o.ctq_value]),
        itemStyle: { color: "#7dd3fc", borderColor: "rgba(2, 6, 23, 0.6)", borderWidth: 1 },
      },
      {
        name: t("doe.chart.fitted"),
        type: "line",
        data: trendLine,
        symbol: "none",
        lineStyle: { color: "#fbbf24", width: 1.6, type: "dashed" as const, shadowColor: "#fbbf2455", shadowBlur: 5 },
      },
    ],
  };

  return (
    <div style={{ marginTop: 8 }}>
      <div style={{ fontSize: 12, marginBottom: 4 }}>
        {t("doe.fit.summary", {
          parameter: study.parameter,
          sign,
          slope: fit.slope.toFixed(2),
          xUnit: study.parameter_unit ?? "",
          yUnit: study.metric_unit ?? "",
          r2: fit.r_squared.toFixed(3),
          n: fit.n_observations,
        })}{" "}
        <span style={{ opacity: 0.7 }}>({t(`doe.fit.direction.${fit.direction}`)})</span>
      </div>
      {study.target_band && (
        <div style={{ fontSize: 11, opacity: 0.6, marginBottom: 6 }}>
          {t("doe.targetNote", {
            min: study.target_band.min,
            max: study.target_band.max,
            unit: study.target_band.unit ?? "",
            source: tr(study.target_band.source ?? ""),
          })}
        </div>
      )}

      <ReactECharts option={option} style={{ height: 200 }} />

      <div style={{ fontSize: 12, fontWeight: 700, margin: "10px 0 4px" }}>{t("doe.violations.title")}</div>
      {study.constraint_violations.length === 0 ? (
        <div style={{ fontSize: 11.5, opacity: 0.6 }}>{t("doe.violations.none")}</div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
          {study.constraint_violations.map((v) => (
            <div key={v.process_run_business_id} style={{ fontSize: 11.5, color: "#fbbf24" }}>
              ▲ {v.process_run_business_id} ({v.lot_business_id}) — {study.parameter}={v.parameter_value}
            </div>
          ))}
        </div>
      )}

      <div style={{ fontSize: 12, fontWeight: 700, margin: "10px 0 4px" }}>{t("doe.candidates.title")}</div>
      <table style={{ width: "100%", fontSize: 11.5, borderCollapse: "collapse" }}>
        <thead>
          <tr style={{ opacity: 0.6, textAlign: "left" }}>
            <th style={{ padding: "2px 6px" }}>{t("doe.candidates.rank")}</th>
            <th style={{ padding: "2px 6px" }}>{t("doe.candidates.parameter")}</th>
            <th style={{ padding: "2px 6px" }}>{t("doe.candidates.predicted")}</th>
            <th style={{ padding: "2px 6px" }}>{t("doe.candidates.inWindow")}</th>
            <th style={{ padding: "2px 6px" }}>{t("doe.candidates.meetsTarget")}</th>
            <th style={{ padding: "2px 6px" }}>{t("doe.candidates.sourceHeader")}</th>
          </tr>
        </thead>
        <tbody>
          {[...study.candidates]
            .sort((a, b) => (a.rank ?? 0) - (b.rank ?? 0) || a.parameter_value - b.parameter_value)
            .map((c, i) => (
              <tr key={i} style={{ borderTop: "1px solid #1e293b" }}>
                <td style={{ padding: "3px 6px", opacity: 0.7 }}>{c.rank ?? "—"}</td>
                <td style={{ padding: "3px 6px" }}>{c.parameter_value.toFixed(3)}</td>
                <td style={{ padding: "3px 6px" }}>{c.predicted_ctq.toFixed(1)}</td>
                <td style={{ padding: "3px 6px", color: c.in_window ? "#4ade80" : "#f87171" }}>
                  {c.in_window ? "✓" : "✕"}
                </td>
                <td style={{ padding: "3px 6px", color: c.meets_target === null ? undefined : c.meets_target ? "#4ade80" : "#f87171" }}>
                  {c.meets_target === null ? "—" : c.meets_target ? "✓" : "✕"}
                </td>
                <td style={{ padding: "3px 6px", opacity: 0.7 }}>{t(`doe.candidates.source.${c.source}`)}</td>
              </tr>
            ))}
        </tbody>
      </table>

      <div style={{ fontSize: 11, opacity: 0.55, marginTop: 8 }}>{tr(study.disclaimer)}</div>
    </div>
  );
}
