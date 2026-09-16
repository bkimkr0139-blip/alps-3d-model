import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { enumLabel } from "../i18n";
import {
  api,
  type Capa,
  type CapaEvent,
  type CavityComparison,
  type Defect,
  type FailureAnalysis,
  type LotCard,
  type LotGenealogy,
  type RootCauseHypothesis,
} from "../lib/api";
import { DoeStudyPanel } from "./DoeStudyPanel";
import { ProcessMonitoring } from "./ProcessMonitoring";
import { seedTr } from "../lib/seedL10n";
import { FactoryViewer, stationToKitStatus } from "./proc/FactoryViewer";
import { aggregateStations, type FactoryStation } from "./proc/factoryScene";
import { GlassDrawer } from "../ui/GlassDrawer";
import { useIsMobile } from "../ui/useIsMobile";
import { StatusBadge, type KitStatus } from "../ui/kit";

const inputStyle: React.CSSProperties = {
  background: "#0f172a",
  color: "white",
  border: "1px solid #334155",
  borderRadius: 4,
  padding: "4px 6px",
  fontSize: 11.5,
};

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
  const { t, i18n } = useTranslation();
  // Root-cause candidates + disclaimer come from the backend as composed
  // Korean f-strings / seeded text — overlaid per ui language at render.
  const tr = (s: string) => seedTr(s, i18n.resolvedLanguage);
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
                <span style={{ fontWeight: 600 }}>{tr(c.title)}</span>
                <span style={{ marginLeft: "auto", fontSize: 10, color: "#fbbf24" }}>{t("proc.rootCause.checkRequired")}</span>
              </div>
              <div style={{ opacity: 0.8, marginTop: 3 }}>{tr(c.detail)}</div>
              {c.evidence.length > 0 && (
                <div style={{ display: "flex", gap: 4, flexWrap: "wrap", marginTop: 4 }}>
                  {c.evidence.map((e, j) => (
                    <span key={j} style={{ background: "#1e293b", borderRadius: 4, padding: "1px 6px", fontSize: 10.5 }} title={e.note ? tr(e.note) : undefined}>
                      {e.kind}: {e.business_id}
                    </span>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
      <div style={{ fontSize: 11, opacity: 0.55, marginTop: 6 }}>{tr(hypo.disclaimer)}</div>
    </div>
  );
}

/** TS10 Defect & FA Workspace lite: one CAPA's status + append-only event
 * trail + the one legal next action for its current state. RBAC (reviewer
 * role for approve/reject/close) is server-enforced only — same pattern as
 * GatePanel.tsx, which shows its buttons unconditionally and lets the API
 * 403 an unauthorized actor. */
function CapaCard({
  capa,
  testRunOptions,
  onChange,
}: {
  capa: Capa;
  testRunOptions: { id: string; business_id: string }[];
  onChange: () => void;
}) {
  const { t, i18n } = useTranslation();
  const tr = (s: string) => seedTr(s, i18n.resolvedLanguage);
  const [events, setEvents] = useState<CapaEvent[]>([]);
  const [comment, setComment] = useState("");
  const [testRunId, setTestRunId] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.listCapaEvents(capa.id).then(setEvents).catch(() => {});
  }, [capa.id, capa.status]);

  async function run(action: () => Promise<unknown>) {
    setError(null);
    try {
      await action();
      setComment("");
      onChange();
    } catch (e) {
      setError(String(e));
    }
  }

  const needsComment = ["draft", "pending_review", "approved", "implemented", "effectiveness_verified"].includes(
    capa.status
  );

  return (
    <div style={{ background: "#0b1220", border: "1px solid #334155", borderRadius: 8, padding: "8px 10px", marginTop: 6 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 6, flexWrap: "wrap" }}>
        <strong style={{ fontSize: 12.5 }}>{tr(capa.title)}</strong>
        <span style={{ fontSize: 11 }}>{enumLabel(t, "capaStatus", capa.status)}</span>
      </div>
      <div style={{ opacity: 0.6, fontSize: 10.5 }}>
        {capa.business_id} · {enumLabel(t, "capaType", capa.capa_type)} · {t("proc.quality.capa.owner")}: {capa.owner}
      </div>
      <div style={{ fontSize: 11.5, marginTop: 4 }}>{tr(capa.description)}</div>

      {events.length > 0 && (
        <div style={{ marginTop: 6, display: "flex", flexDirection: "column", gap: 2 }}>
          {events.map((e) => (
            <div key={e.id} style={{ fontSize: 10, opacity: 0.65, borderLeft: "2px solid #334155", paddingLeft: 6 }}>
              {enumLabel(t, "capaEventType", e.event_type)} · {e.actor} ({new Date(e.occurred_at).toLocaleString()})
              {e.comment ? ` — ${tr(e.comment)}` : ""}
              {e.evidence?.test_run_business_id
                ? ` · ${t("proc.quality.capa.retest")}: ${String(e.evidence.test_run_business_id)}`
                : ""}
            </div>
          ))}
        </div>
      )}

      {needsComment && (
        <textarea
          value={comment}
          onChange={(e) => setComment(e.target.value)}
          placeholder={t("proc.quality.capa.commentPlaceholder")}
          style={{ ...inputStyle, width: "100%", minHeight: 32, marginTop: 6 }}
        />
      )}

      <div style={{ display: "flex", gap: 6, marginTop: 6, flexWrap: "wrap", alignItems: "center" }}>
        {capa.status === "draft" && (
          <button onClick={() => run(() => api.submitCapa(capa.id, comment))}>{t("proc.quality.capa.submit")}</button>
        )}
        {capa.status === "pending_review" && (
          <>
            <button style={{ background: "#166534" }} onClick={() => run(() => api.decideCapa(capa.id, "approved", comment))}>
              {t("proc.quality.capa.approve")}
            </button>
            <button style={{ background: "#7f1d1d" }} onClick={() => run(() => api.decideCapa(capa.id, "rejected", comment))}>
              {t("proc.quality.capa.reject")}
            </button>
          </>
        )}
        {capa.status === "approved" && (
          <button onClick={() => run(() => api.implementCapa(capa.id, comment))}>{t("proc.quality.capa.markImplemented")}</button>
        )}
        {capa.status === "implemented" && (
          <>
            <select value={testRunId} onChange={(e) => setTestRunId(e.target.value)} style={inputStyle}>
              <option value="">{t("proc.quality.capa.selectTestRun")}</option>
              {testRunOptions.map((tr) => (
                <option key={tr.id} value={tr.id}>
                  {tr.business_id}
                </option>
              ))}
            </select>
            <button disabled={!testRunId} onClick={() => run(() => api.verifyCapaEffectiveness(capa.id, testRunId, comment))}>
              {t("proc.quality.capa.verify")}
            </button>
          </>
        )}
        {capa.status === "effectiveness_verified" && (
          <button onClick={() => run(() => api.closeCapa(capa.id, comment))}>{t("proc.quality.capa.close")}</button>
        )}
      </div>
      {error && <div style={{ color: "#ef4444", fontSize: 11, marginTop: 4 }}>{error}</div>}
    </div>
  );
}

/** Per-defect FA/CAPA management: create an FA, then create/drive CAPAs
 * under it. `testRunOptions` (the lot's own inspection runs) feeds the
 * effectiveness-verification picker — a retest must point at a real
 * TestRun, never a free-text claim. */
function DefectQualitySection({

  defectId,
  testRunOptions,
}: {
  defectId: string;
  testRunOptions: { id: string; business_id: string }[];
}) {
  const { t, i18n } = useTranslation();
  const tr = (s: string) => seedTr(s, i18n.resolvedLanguage);
  const [fas, setFas] = useState<FailureAnalysis[]>([]);
  const [capasByFa, setCapasByFa] = useState<Record<string, Capa[]>>({});
  const [showFaForm, setShowFaForm] = useState(false);
  const [faForm, setFaForm] = useState({ method: "5-Why", findings: "", analyst: "", root_cause: "", root_cause_confirmed: false });
  const [capaFormFor, setCapaFormFor] = useState<string | null>(null);
  const [capaForm, setCapaForm] = useState<{ title: string; capa_type: "corrective" | "preventive" | "both"; description: string; owner: string }>({
    title: "",
    capa_type: "corrective",
    description: "",
    owner: "",
  });
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    const list = await api.listFailureAnalyses(defectId);
    setFas(list);
    const entries = await Promise.all(list.map(async (fa) => [fa.id, await api.listCapas(fa.id)] as const));
    setCapasByFa(Object.fromEntries(entries));
  }

  useEffect(() => {
    refresh().catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [defectId]);

  async function createFa() {
    setError(null);
    try {
      const bid = `FA-${defectId.slice(0, 8)}-${Date.now()}`;
      await api.createFailureAnalysis(defectId, {
        business_id: bid,
        method: faForm.method,
        findings: faForm.findings,
        analyst: faForm.analyst,
        analyzed_at: new Date().toISOString(),
        root_cause: faForm.root_cause || null,
        root_cause_confirmed: faForm.root_cause_confirmed,
      });
      setShowFaForm(false);
      setFaForm({ method: "5-Why", findings: "", analyst: "", root_cause: "", root_cause_confirmed: false });
      await refresh();
    } catch (e) {
      setError(String(e));
    }
  }

  async function createCapa(faId: string) {
    setError(null);
    try {
      const bid = `CAPA-${faId.slice(0, 8)}-${Date.now()}`;
      await api.createCapa(faId, { business_id: bid, ...capaForm });
      setCapaFormFor(null);
      setCapaForm({ title: "", capa_type: "corrective", description: "", owner: "" });
      await refresh();
    } catch (e) {
      setError(String(e));
    }
  }

  return (
    <div style={{ marginTop: 8, borderTop: "1px dashed #334155", paddingTop: 8 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div style={{ fontSize: 11.5, fontWeight: 700, opacity: 0.85 }}>{t("proc.quality.title")}</div>
        <button onClick={() => setShowFaForm((s) => !s)} style={{ fontSize: 10.5, padding: "2px 6px" }}>
          {t("proc.quality.fa.createButton")}
        </button>
      </div>

      {showFaForm && (
        <div style={{ display: "flex", flexDirection: "column", gap: 4, marginTop: 6 }}>
          <input
            placeholder={t("proc.quality.fa.method")}
            value={faForm.method}
            onChange={(e) => setFaForm({ ...faForm, method: e.target.value })}
            style={inputStyle}
          />
          <textarea
            placeholder={t("proc.quality.fa.findings")}
            value={faForm.findings}
            onChange={(e) => setFaForm({ ...faForm, findings: e.target.value })}
            style={{ ...inputStyle, minHeight: 40 }}
          />
          <input
            placeholder={t("proc.quality.fa.analyst")}
            value={faForm.analyst}
            onChange={(e) => setFaForm({ ...faForm, analyst: e.target.value })}
            style={inputStyle}
          />
          <textarea
            placeholder={t("proc.quality.fa.rootCause")}
            value={faForm.root_cause}
            onChange={(e) => setFaForm({ ...faForm, root_cause: e.target.value })}
            style={{ ...inputStyle, minHeight: 30 }}
          />
          <label style={{ fontSize: 11, display: "flex", gap: 4, alignItems: "center" }}>
            <input
              type="checkbox"
              checked={faForm.root_cause_confirmed}
              onChange={(e) => setFaForm({ ...faForm, root_cause_confirmed: e.target.checked })}
            />
            {t("proc.quality.fa.rootCauseConfirmed")}
          </label>
          <button onClick={createFa} disabled={!faForm.findings.trim() || !faForm.analyst.trim()}>
            {t("proc.quality.fa.create")}
          </button>
        </div>
      )}

      {fas.length === 0 ? (
        <div style={{ fontSize: 11, opacity: 0.6, marginTop: 4 }}>{t("proc.quality.fa.empty")}</div>
      ) : (
        fas.map((fa) => (
          <div key={fa.id} style={{ marginTop: 8 }}>
            <div style={{ fontSize: 12, fontWeight: 600 }}>
              {fa.method} <span style={{ opacity: 0.6, fontWeight: 400 }}>· {fa.analyst} · {new Date(fa.analyzed_at).toLocaleDateString()}</span>
            </div>
            <div style={{ fontSize: 11.5, opacity: 0.85 }}>{tr(fa.findings)}</div>
            {fa.root_cause && (
              <div style={{ fontSize: 11, marginTop: 2 }}>
                <span style={{ color: fa.root_cause_confirmed ? "#4ade80" : "#fbbf24", fontWeight: 600 }}>
                  {fa.root_cause_confirmed ? t("proc.quality.fa.confirmed") : t("proc.quality.fa.unconfirmed")}
                </span>{" "}
                {tr(fa.root_cause)}
              </div>
            )}

            {(capasByFa[fa.id] ?? []).map((capa) => (
              <CapaCard key={capa.id} capa={capa} testRunOptions={testRunOptions} onChange={refresh} />
            ))}

            {capaFormFor === fa.id ? (
              <div style={{ display: "flex", flexDirection: "column", gap: 4, marginTop: 6 }}>
                <input
                  placeholder={t("proc.quality.capa.titleField")}
                  value={capaForm.title}
                  onChange={(e) => setCapaForm({ ...capaForm, title: e.target.value })}
                  style={inputStyle}
                />
                <select
                  value={capaForm.capa_type}
                  onChange={(e) => setCapaForm({ ...capaForm, capa_type: e.target.value as typeof capaForm.capa_type })}
                  style={inputStyle}
                >
                  <option value="corrective">{t("enums.capaType.corrective")}</option>
                  <option value="preventive">{t("enums.capaType.preventive")}</option>
                  <option value="both">{t("enums.capaType.both")}</option>
                </select>
                <textarea
                  placeholder={t("proc.quality.capa.description")}
                  value={capaForm.description}
                  onChange={(e) => setCapaForm({ ...capaForm, description: e.target.value })}
                  style={{ ...inputStyle, minHeight: 40 }}
                />
                <input
                  placeholder={t("proc.quality.capa.owner")}
                  value={capaForm.owner}
                  onChange={(e) => setCapaForm({ ...capaForm, owner: e.target.value })}
                  style={inputStyle}
                />
                <button onClick={() => createCapa(fa.id)} disabled={!capaForm.title.trim() || !capaForm.description.trim() || !capaForm.owner.trim()}>
                  {t("proc.quality.capa.create")}
                </button>
              </div>
            ) : (
              <button onClick={() => setCapaFormFor(fa.id)} style={{ fontSize: 10.5, padding: "2px 6px", marginTop: 4 }}>
                {t("proc.quality.capa.createButton")}
              </button>
            )}
          </div>
        ))
      )}
      {error && <div style={{ color: "#ef4444", fontSize: 11, marginTop: 4 }}>{error}</div>}
    </div>
  );
}

function LotDetail({ lot }: { lot: LotCard }) {
  const { t } = useTranslation();
  const [gene, setGene] = useState<LotGenealogy | null>(null);
  const [defects, setDefects] = useState<Defect[]>([]);
  const [expandedDefectId, setExpandedDefectId] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .lotGenealogy(lot.id)
      .then((g) => {
        if (!cancelled) setGene(g);
      })
      .catch(() => {});
    api
      .listLotDefects(lot.id)
      .then((d) => {
        if (!cancelled) setDefects(d);
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
            gene.defects.map((d) => {
              const real = defects.find((rd) => rd.business_id === d.business_id);
              const expanded = real && real.id === expandedDefectId;
              return (
                <div
                  key={d.business_id}
                  onClick={() => real && setExpandedDefectId(expanded ? null : real.id)}
                  style={{ fontSize: 12, cursor: real ? "pointer" : "default" }}
                  title={real ? t("proc.quality.expandHint") : undefined}
                >
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
                  {real && <span style={{ opacity: 0.4, fontSize: 11 }}> {expanded ? "▲" : "▼"}</span>}
                </div>
              );
            })
          )}
        </div>
      </div>

      {expandedDefectId && <DefectQualitySection defectId={expandedDefectId} testRunOptions={gene.test_runs} />}

      <RootCauseSection lotId={lot.id} />
    </div>
  );
}

function CavityStrip({ comparison }: { comparison: CavityComparison }) {
  const { t, i18n } = useTranslation();
  const tr = (s: string) => seedTr(s, i18n.resolvedLanguage);
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
        <div style={{ marginTop: 4, fontSize: 11.5, opacity: 0.65 }}>{tr(comparison.check_note)}</div>
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
  const isMobile = useIsMobile();
  const [lots, setLots] = useState<LotCard[]>([]);
  const [comparison, setComparison] = useState<CavityComparison | null>(null);
  const [selectedLotId, setSelectedLotId] = useState<string | null>(null);
  // Production-line 3D twin: stations from the global operation route, health
  // from the variant's control charts (worst parameter wins), conveyor dots
  // from the lot list. Silent degradation matches the rest of the tab.
  const [stations, setStations] = useState<FactoryStation[]>([]);
  const [selectedStation, setSelectedStation] = useState<string | null>(null);
  const specBand = productBusinessId === "PROD-TACT-SWITCH" ? TACT_SPEC_BAND : undefined;

  useEffect(() => {
    if (!variantId) return;
    api.listLots(variantId).then(setLots).catch(() => {});
    api.cavityCompare(variantId, specBand).then(setComparison).catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [variantId, productBusinessId]);

  useEffect(() => {
    if (!variantId) {
      setStations([]);
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const [ops, paramInfos] = await Promise.all([api.listProcessOperations(), api.listProcessParameters(variantId)]);
        const settled = await Promise.allSettled(paramInfos.map((pi) => api.controlChart(variantId, pi.parameter)));
        const charts = new Map<string, import("../lib/api").ControlChart>();
        paramInfos.forEach((pi, i) => {
          const r = settled[i];
          if (r.status === "fulfilled") charts.set(pi.parameter, r.value);
        });
        if (!cancelled) setStations(aggregateStations(ops, paramInfos, charts));
      } catch {
        /* the tab degrades to the table views, as before */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [variantId]);

  if (!variantId) return null;
  const selectedLot = lots.find((l) => l.id === selectedLotId) ?? null;
  const drawerStation = selectedStation ? (stations.find((s) => s.key === selectedStation) ?? null) : null;
  const stationDrawer = drawerStation ? (
    <StationDrawer variantId={variantId} station={drawerStation} comparison={comparison} onClose={() => setSelectedStation(null)} />
  ) : null;

  return (
    <div style={{ height: "100%", overflowY: "auto", padding: 4 }}>
      <h3 style={{ margin: "0 0 10px", fontSize: 15 }}>{t("proc.title")}</h3>

      {/* Production-line 3D twin — the tab's new primary surface. The real
          data panels below stay exactly where they were; the line anchors
          them. Clicking a station opens the chart drawer over the canvas. */}
      {stations.length > 0 && (
        <div
          style={{
            position: "relative",
            height: "clamp(300px, 46vh, 480px)",
            marginBottom: 12,
            border: "1px solid #334155",
            borderRadius: 8,
            overflow: "hidden",
          }}
        >
          <FactoryViewer
            stations={stations}
            lots={lots}
            selectedKey={selectedStation}
            onSelect={setSelectedStation}
            onJumpDoe={() => document.getElementById("doe-panel")?.scrollIntoView({ behavior: "smooth", block: "start" })}
          />
          {!isMobile && stationDrawer}
        </div>
      )}
      {isMobile && stationDrawer}

      <ProcessMonitoring variantId={variantId} />

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

      <div id="doe-panel">
        <DoeStudyPanel
          key={variantId}
          variantId={variantId}
          defaultTargetBand={specBand ? { min: specBand.lsl, max: specBand.usl, unit: "mN" } : undefined}
        />
      </div>

      <div style={{ marginTop: 12, fontSize: 11, opacity: 0.55 }}>{t("proc.disclaimer")}</div>
    </div>
  );
}

// Station detail drawer — opened by clicking a machine on the production
// line. Reuses the real data surfaces (control chart, cavity strip) instead
// of inventing a parallel display; the worst parameter preselects the chart.
function StationDrawer({
  variantId,
  station,
  comparison,
  onClose,
}: {
  variantId: string;
  station: FactoryStation;
  comparison: CavityComparison | null;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const kit: KitStatus = stationToKitStatus(station.status);
  const statusLabel =
    station.status === "in_control"
      ? t("proc.mon.legend.inControl")
      : station.status === "rule_hit"
        ? t("proc.mon.legend.violation")
        : station.status === "excluded"
          ? t("proc.mon.legend.excluded")
          : t("factory.noParams");
  // Worst parameter (excluded points outrank rule hits) preselects the chart.
  const worst = [...station.params].sort((a, b) => b.excluded - a.excluded || b.ruleHits - a.ruleHits)[0];
  // The cavity comparison belongs to the molding station (mold equipment id).
  const isMolding = /mold/i.test(station.equipment ?? "");

  return (
    <GlassDrawer
      side="right"
      width={390}
      title={`${station.name}${station.equipment ? ` · ${station.equipment}` : ""}`}
      onClose={onClose}
    >
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center", marginBottom: 8 }}>
        <StatusBadge status={kit} label={statusLabel} />
        <span style={{ fontSize: 11, opacity: 0.6 }}>{station.key}</span>
      </div>

      <div style={{ fontSize: 11.5, fontWeight: 700, margin: "4px 0 4px" }}>{t("factory.params")}</div>
      {station.params.length === 0 ? (
        <div style={{ fontSize: 11.5, opacity: 0.6, marginBottom: 6 }}>{t("factory.noParams")}</div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 3, marginBottom: 8 }}>
          {station.params.map((p) => (
            <div key={p.parameter} style={{ display: "flex", gap: 8, fontSize: 11, fontFamily: "monospace", alignItems: "baseline" }}>
              <span style={{ color: "#7dd3fc" }}>{p.parameter}</span>
              <span style={{ opacity: 0.55 }}>{p.unit ?? ""}</span>
              <span style={{ marginLeft: "auto", color: p.ruleHits > 0 ? "#fbbf24" : undefined }}>▲{p.ruleHits}</span>
              <span style={{ color: p.excluded > 0 ? "#f87171" : undefined }}>✕{p.excluded}</span>
            </div>
          ))}
        </div>
      )}

      {isMolding && comparison && (
        <>
          <div style={{ fontSize: 11.5, fontWeight: 700, margin: "4px 0 4px" }}>{t("proc.cavity.title")}</div>
          <div style={{ marginBottom: 8 }}>
            <CavityStrip comparison={comparison} />
          </div>
        </>
      )}

      <ProcessMonitoring variantId={variantId} initialParameter={worst?.parameter} />
    </GlassDrawer>
  );
}
