import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  api,
  type CavityComparison,
  type LotCard,
  type LotGenealogy,
  type RootCauseHypothesis,
} from "../lib/api";
import { DoeStudyPanel } from "./DoeStudyPanel";

/** Status uses icon + text together (§5.1: never colour alone). */
function DispositionBadge({ disposition }: { disposition: LotCard["disposition"] }) {
  const { t } = useTranslation();
  const map = {
    ok: { color: "#4ade80", mark: "●", label: t("proc.disposition.ok") },
    quarantine: { color: "#fbbf24", mark: "▲", label: t("proc.disposition.quarantine") },
    reject: { color: "#f87171", mark: "✕", label: t("proc.disposition.reject") },
  } as const;
  const s = map[disposition];
  return (
    <span style={{ color: s.color, fontSize: 12, fontWeight: 600, whiteSpace: "nowrap" }}>
      {s.mark} {s.label}
    </span>
  );
}

function RootCauseSection({ lotId }: { lotId: string }) {
  const { t } = useTranslation();
  const [hypo, setHypo] = useState<RootCauseHypothesis | null>(null);

  const load = () =>
    api
      .rootCauseHypotheses(lotId)
      .then(setHypo)
      .catch(() => setHypo(null));

  if (!hypo)
    return (
      <button
        onClick={load}
        style={{ marginTop: 8, padding: "5px 10px", borderRadius: 6, background: "#1e293b", color: "#e2e8f0", border: "1px solid #334155", cursor: "pointer", fontSize: 12 }}
      >
        {t("proc.rootCause.button")}
      </button>
    );

  return (
    <div style={{ marginTop: 10 }}>
      <div style={{ fontSize: 12.5, fontWeight: 700, marginBottom: 6 }}>{t("proc.rootCause.title")}</div>
      {hypo.candidates.length === 0 ? (
        <div style={{ fontSize: 12, opacity: 0.6 }}>{t("proc.rootCause.none")}</div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          {hypo.candidates.map((c, i) => (
            <div key={i} style={{ background: "#0b1220", borderLeft: "3px solid #fbbf24", borderRadius: 6, padding: "6px 9px", fontSize: 12 }}>
              <div style={{ display: "flex", gap: 6, alignItems: "baseline", flexWrap: "wrap" }}>
                <span style={{ background: "#fbbf24", color: "#0b1220", padding: "0 6px", borderRadius: 4, fontWeight: 700, fontSize: 10 }}>
                  {t(`proc.cause.${c.cause}`)}
                </span>
                <span style={{ fontWeight: 600 }}>{c.title}</span>
                <span style={{ marginLeft: "auto", fontSize: 10, color: "#fbbf24" }}>{t("proc.rootCause.checkRequired")}</span>
              </div>
              <div style={{ opacity: 0.8, marginTop: 3 }}>{c.detail}</div>
              {c.evidence.length > 0 && (
                <div style={{ display: "flex", gap: 4, flexWrap: "wrap", marginTop: 4 }}>
                  {c.evidence.map((e, j) => (
                    <span key={j} style={{ background: "#1e293b", borderRadius: 4, padding: "1px 6px", fontSize: 10.5 }} title={e.note}>
                      {e.kind}: {e.business_id}
                    </span>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
      <div style={{ fontSize: 11, opacity: 0.55, marginTop: 6 }}>{hypo.disclaimer}</div>
    </div>
  );
}

function LotDetail({ lot }: { lot: LotCard }) {
  const { t } = useTranslation();
  const [gene, setGene] = useState<LotGenealogy | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .lotGenealogy(lot.id)
      .then((g) => {
        if (!cancelled) setGene(g);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [lot.id]);

  if (!gene) return <div style={{ marginTop: 8, fontSize: 12, opacity: 0.6 }}>…</div>;

  const kv = (label: string, value: React.ReactNode) => (
    <div style={{ display: "flex", gap: 8, fontSize: 12 }}>
      <span style={{ opacity: 0.6, minWidth: 92 }}>{label}</span>
      <span>{value}</span>
    </div>
  );

  return (
    <div style={{ marginTop: 10, borderTop: "1px solid #1e293b", paddingTop: 10 }}>
      <div style={{ fontSize: 12.5, fontWeight: 700, marginBottom: 6 }}>{t("proc.genealogy.title")}</div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: 10 }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
          {kv(t("proc.genealogy.material"), gene.lot.material_lot_id ?? "—")}
          {kv(t("proc.genealogy.mold"), `${gene.mold.business_id} (rev ${gene.mold.tool_revision})`)}
          {kv(t("proc.genealogy.cavity"), gene.cavity.label)}
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
          {kv(t("proc.genealogy.workOrder"), gene.lot.work_order_id ?? "—")}
          {kv(t("proc.genealogy.produced"), new Date(gene.lot.produced_at).toLocaleDateString())}
          {kv(t("proc.genealogy.quantity"), gene.lot.quantity ?? "—")}
        </div>
      </div>

      <div style={{ fontSize: 12, fontWeight: 700, margin: "10px 0 4px" }}>{t("proc.genealogy.processRuns")}</div>
      <table style={{ width: "100%", fontSize: 12, borderCollapse: "collapse" }}>
        <thead>
          <tr style={{ opacity: 0.6, textAlign: "left" }}>
            <th style={{ padding: "2px 6px" }}>#</th>
            <th style={{ padding: "2px 6px" }}>{t("proc.genealogy.operation")}</th>
            <th style={{ padding: "2px 6px" }}>{t("proc.genealogy.setpoint")}</th>
            <th style={{ padding: "2px 6px" }}>{t("proc.genealogy.actual")}</th>
          </tr>
        </thead>
        <tbody>
          {gene.process_runs.map((r) => (
            <tr key={r.business_id} style={{ borderTop: "1px solid #1e293b" }}>
              <td style={{ padding: "3px 6px", opacity: 0.6 }}>{r.seq_no}</td>
              <td style={{ padding: "3px 6px" }}>
                {r.operation} <span style={{ opacity: 0.5 }}>({r.equipment ?? "—"})</span>
              </td>
              <td style={{ padding: "3px 6px", opacity: 0.75 }}>
                {r.setpoint ? Object.entries(r.setpoint).map(([k, v]) => `${k}=${String(v)}`).join(", ") : "—"}
              </td>
              <td style={{ padding: "3px 6px" }}>
                {r.out_of_window && (
                  <span title={r.window_findings?.map((f) => `${f.parameter}: ${f.actual} ∉ [${f.min}, ${f.max}]`).join("\n")}>
                    ▲{" "}
                  </span>
                )}
                {r.actual ? Object.entries(r.actual).map(([k, v]) => `${k}=${String(v)}`).join(", ") : "—"}
                {r.out_of_window && (
                  <span style={{ color: "#f87171", fontSize: 11 }}> {t("proc.genealogy.oow")}</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginTop: 10 }}>
        <div>
          <div style={{ fontSize: 12, fontWeight: 700, marginBottom: 4 }}>{t("proc.genealogy.testRuns")}</div>
          {gene.test_runs.length === 0 ? (
            <div style={{ fontSize: 12, opacity: 0.6 }}>{t("proc.genealogy.none")}</div>
          ) : (
            gene.test_runs.map((tr) => (
              <div key={tr.id} style={{ fontSize: 12 }}>
                ● {tr.business_id}{" "}
                <span style={{ opacity: 0.6 }}>
                  ({t("proc.genealogy.measurements", { count: tr.measurement_count })})
                </span>
              </div>
            ))
          )}
        </div>
        <div>
          <div style={{ fontSize: 12, fontWeight: 700, marginBottom: 4 }}>{t("proc.genealogy.defects")}</div>
          {gene.defects.length === 0 ? (
            <div style={{ fontSize: 12, opacity: 0.6 }}>{t("proc.genealogy.none")}</div>
          ) : (
            gene.defects.map((d) => (
              <div key={d.business_id} style={{ fontSize: 12 }}>
                <span
                  style={{
                    color: d.severity === "critical" ? "#f87171" : d.severity === "major" ? "#fbbf24" : "#7dd3fc",
                    fontWeight: 600,
                  }}
                >
                  ✕ {d.defect_class}
                </span>{" "}
                <span style={{ opacity: 0.6 }}>
                  ({t(`proc.severity.${d.severity}`)} ×{d.quantity})
                </span>
              </div>
            ))
          )}
        </div>
      </div>

      <RootCauseSection lotId={lot.id} />
    </div>
  );
}

function CavityStrip({ comparison }: { comparison: CavityComparison }) {
  const { t } = useTranslation();
  return (
    <div>
      <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
        {comparison.cavities.map((c) => (
          <div key={c.cavity_id} style={{ background: "#0b1220", border: "1px solid #334155", borderRadius: 8, padding: "8px 12px", minWidth: 170 }}>
            <div style={{ fontWeight: 700, fontSize: 12.5 }}>{c.cavity_label}</div>
            <div style={{ fontSize: 12, marginTop: 2 }}>
              {t("proc.cavity.n", { count: c.n_values })} · {t("proc.cavity.mean")} {c.mean !== null ? c.mean.toFixed(1) : "—"}
              {c.sd !== null ? ` ± ${c.sd.toFixed(2)}` : ""}
            </div>
            {c.cp !== null && c.cpk !== null && (
              <div style={{ fontSize: 11.5, opacity: 0.75, marginTop: 2 }}>
                Cp {c.cp.toFixed(2)} · Cpk {c.cpk.toFixed(2)}
              </div>
            )}
          </div>
        ))}
      </div>
      {comparison.drift_suspected && (
        <div style={{ marginTop: 8, fontSize: 12.5, color: "#fbbf24" }}>
          ▲ {t("proc.cavity.drift")}
        </div>
      )}
      {comparison.check_note && (
        <div style={{ marginTop: 4, fontSize: 11.5, opacity: 0.65 }}>{comparison.check_note}</div>
      )}
    </div>
  );
}

/** TS03+TS04+TS05+TS09 lite in one screen: cavity CTQ map, lot table with
 * genealogy drill-down and rule-based root-cause candidates. All quality
 * signals are check-required hints — the screen never passes a lot by itself. */
// TACT 데모 사양 밴드 (UQ target band와 동일한 합성 스펙 — 출처 표기는 specNote로)
const TACT_SPEC_BAND = { lsl: 260, usl: 360 };

export function ProcessTwin({
  variantId,
  productBusinessId,
}: {
  variantId: string | null;
  productBusinessId?: string;
}) {
  const { t } = useTranslation();
  const [lots, setLots] = useState<LotCard[]>([]);
  const [comparison, setComparison] = useState<CavityComparison | null>(null);
  const [selectedLotId, setSelectedLotId] = useState<string | null>(null);
  const specBand = productBusinessId === "PROD-TACT-SWITCH" ? TACT_SPEC_BAND : undefined;

  useEffect(() => {
    if (!variantId) return;
    api.listLots(variantId).then(setLots).catch(() => {});
    api.cavityCompare(variantId, specBand).then(setComparison).catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [variantId, productBusinessId]);

  if (!variantId) return null;
  const selectedLot = lots.find((l) => l.id === selectedLotId) ?? null;

  return (
    <div style={{ height: "100%", overflowY: "auto", padding: 4 }}>
      <h3 style={{ margin: "0 0 10px", fontSize: 15 }}>{t("proc.title")}</h3>

      <div style={{ fontSize: 12.5, fontWeight: 700, marginBottom: 6 }}>
        {t("proc.cavity.title")}
        {specBand && (
          <span style={{ fontWeight: 400, opacity: 0.6, marginLeft: 8, fontSize: 11.5 }}>
            {t("proc.cavity.specNote", { lsl: specBand.lsl, usl: specBand.usl })}
          </span>
        )}
      </div>
      {comparison ? <CavityStrip comparison={comparison} /> : <div style={{ fontSize: 12, opacity: 0.6 }}>…</div>}

      <div style={{ fontSize: 12.5, fontWeight: 700, margin: "14px 0 6px" }}>{t("proc.lotTable.title")}</div>
      {lots.length === 0 ? (
        <div style={{ fontSize: 12, opacity: 0.6 }}>{t("proc.lotTable.empty")}</div>
      ) : (
        <table style={{ width: "100%", fontSize: 12, borderCollapse: "collapse" }}>
          <thead>
            <tr style={{ opacity: 0.6, textAlign: "left" }}>
              <th style={{ padding: "3px 8px" }}>{t("proc.lotTable.lot")}</th>
              <th style={{ padding: "3px 8px" }}>{t("proc.lotTable.cavity")}</th>
              <th style={{ padding: "3px 8px" }}>{t("proc.lotTable.disposition")}</th>
              <th style={{ padding: "3px 8px" }}>{t("proc.lotTable.defects")}</th>
              <th style={{ padding: "3px 8px" }}>{t("proc.lotTable.oow")}</th>
            </tr>
          </thead>
          <tbody>
            {lots.map((lot) => (
              <tr
                key={lot.id}
                onClick={() => setSelectedLotId(lot.id === selectedLotId ? null : lot.id)}
                style={{
                  borderTop: "1px solid #1e293b",
                  cursor: "pointer",
                  background: lot.id === selectedLotId ? "#1e293b" : "transparent",
                }}
              >
                <td style={{ padding: "4px 8px" }}>{lot.business_id}</td>
                <td style={{ padding: "4px 8px" }}>{lot.cavity_label}</td>
                <td style={{ padding: "4px 8px" }}>
                  <DispositionBadge disposition={lot.disposition} />
                </td>
                <td style={{ padding: "4px 8px" }}>{lot.defect_count > 0 ? `✕ ${lot.defect_count}` : "—"}</td>
                <td style={{ padding: "4px 8px" }}>
                  {lot.out_of_window_runs > 0 ? (
                    <span style={{ color: "#f87171" }}>▲ {lot.out_of_window_runs}</span>
                  ) : (
                    "—"
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {selectedLot && <LotDetail key={selectedLot.id} lot={selectedLot} />}

      <DoeStudyPanel
        key={variantId}
        variantId={variantId}
        defaultTargetBand={specBand ? { min: specBand.lsl, max: specBand.usl, unit: "mN" } : undefined}
      />

      <div style={{ marginTop: 12, fontSize: 11, opacity: 0.55 }}>{t("proc.disclaimer")}</div>
    </div>
  );
}
