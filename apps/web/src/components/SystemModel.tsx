import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  api,
  type ImpactPaths,
  type ModelCardDto,
  type ReviewRunDto,
  type SystemModel,
  type UQAnalysisDto,
} from "../lib/api";
import { useTwinStore } from "../store";
import { seedTr } from "../lib/seedL10n";

// Domain palette — one hue per engineering domain (§E02). Fills are the hue
// at low alpha so blocks stay readable on the dark panel background.
const DOMAIN_COLORS: Record<string, string> = {
  mechanical: "#38bdf8",
  electrical: "#fbbf24",
  control: "#a78bfa",
  kansei: "#f472b6",
};

// AI-inferred edges stay visually loud until a human approves them (§AI-06:
// they may never back gate evidence, so the UI must never let them read as
// established fact).
function provenanceStyle(provenance: string): { color: string; dashed: boolean; key: string } {
  if (provenance === "ai_inferred") return { color: "#f59e0b", dashed: true, key: "sysmodel.provAi" };
  if (provenance === "human_approved") return { color: "#4ade80", dashed: false, key: "sysmodel.provApproved" };
  if (provenance === "rule_derived") return { color: "#94a3b8", dashed: false, key: "sysmodel.provRule" };
  return { color: "#94a3b8", dashed: false, key: "sysmodel.provImported" };
}

const BLOCK_W = 168;
const BLOCK_H = 78;

type Block = {
  element: SystemModel["elements"][number];
  x: number;
  y: number;
};

function canvasBlocks(elements: SystemModel["elements"]): Block[] {
  // Positions are seeded in abstract units; if any are missing, fall back to
  // a simple wrap grid so the canvas still renders for hand-made data.
  const positioned = elements.filter((e) => e.position);
  if (positioned.length !== elements.length || elements.length === 0) {
    const perRow = 4;
    return elements.map((element, i) => ({
      element,
      x: (i % perRow) * (BLOCK_W + 48),
      y: Math.floor(i / perRow) * (BLOCK_H + 64),
    }));
  }
  return elements.map((element) => ({
    element,
    x: element.position!.x,
    y: element.position!.y,
  }));
}

function ModelCanvas({ model }: { model: SystemModel }) {
  const { t, i18n } = useTranslation();
  // Seed-dataset prose (DB-seeded Korean) rendered per ui language.
  const tr = (s: string) => seedTr(s, i18n.resolvedLanguage);
  const selectedComponentId = useTwinStore((s) => s.selectedComponentId);
  const setSelectedComponentId = useTwinStore((s) => s.setSelectedComponentId);
  const blocks = useMemo(() => canvasBlocks(model.elements), [model]);

  const minX = Math.min(...blocks.map((b) => b.x));
  const minY = Math.min(...blocks.map((b) => b.y));
  const maxX = Math.max(...blocks.map((b) => b.x + BLOCK_W));
  const maxY = Math.max(...blocks.map((b) => b.y + BLOCK_H));
  const pad = 28;

  return (
    <div style={{ overflowX: "auto" }}>
      <svg
        viewBox={`${minX - pad} ${minY - pad} ${maxX - minX + pad * 2} ${maxY - minY + pad * 2}`}
        style={{ width: "100%", minHeight: 240, background: "#0b1220", borderRadius: 8 }}
        onClick={() => setSelectedComponentId(null)}
      >
        <defs>
          <marker id="sm-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
            <path d="M 0 0 L 10 5 L 0 10 z" fill="#8b99b5" />
          </marker>
        </defs>
        {model.links.map((link) => {
          const src = blocks.find((b) => b.element.id === link.source_element_id);
          const dst = blocks.find((b) => b.element.id === link.target_element_id);
          if (!src || !dst) return null;
          const x1 = src.x + BLOCK_W;
          const y1 = src.y + BLOCK_H / 2;
          const x2 = dst.x;
          const y2 = dst.y + BLOCK_H / 2;
          const mx = (x1 + x2) / 2;
          const label = link.unit ? `${tr(link.signal)} [${link.unit}]` : tr(link.signal);
          return (
            <g key={link.id}>
              <path
                d={`M ${x1} ${y1} C ${mx} ${y1}, ${mx} ${y2}, ${x2} ${y2}`}
                fill="none"
                stroke="#8b99b5"
                strokeWidth={1.6}
                markerEnd="url(#sm-arrow)"
              />
              <text x={mx} y={(y1 + y2) / 2 - 6} textAnchor="middle" fontSize={10} fill="#94a3b8">
                {label}
              </text>
              {link.unit_conversion && (
                <text x={mx} y={(y1 + y2) / 2 + 6} textAnchor="middle" fontSize={9} fill="#38bdf8">
                  {link.unit_conversion}
                </text>
              )}
            </g>
          );
        })}
        {/* Port contract dots (SM-03): IN ports left edge, OUT ports right. */}
        {blocks.map(({ element, x, y }) => {
          const ports = model.ports.filter((p) => p.element_id === element.id);
          const inPorts = ports.filter((p) => p.direction === "in" || p.direction === "inout");
          const outPorts = ports.filter((p) => p.direction === "out" || p.direction === "inout");
          return (
            <g key={`ports-${element.id}`}>
              {inPorts.map((p, i) => (
                <circle key={p.id} cx={x} cy={y + 14 + i * 16} r={3.5} fill="#38bdf8" stroke="#0b1220" strokeWidth={1}>
                  <title>{`IN ${tr(p.name)} [${p.unit}]`}</title>
                </circle>
              ))}
              {outPorts.map((p, i) => (
                <circle key={p.id} cx={x + BLOCK_W} cy={y + 14 + i * 16} r={3.5} fill="#fbbf24" stroke="#0b1220" strokeWidth={1}>
                  <title>{`OUT ${tr(p.name)} [${p.unit}]`}</title>
                </circle>
              ))}
            </g>
          );
        })}
        {blocks.map(({ element, x, y }) => {
          const color = DOMAIN_COLORS[element.domain] ?? "#94a3b8";
          const linked = !!element.geometry_component_id;
          const selected = !!element.geometry_component_id && element.geometry_component_id === selectedComponentId;
          return (
            <g
              key={element.id}
              transform={`translate(${x} ${y})`}
              onClick={(e) => {
                e.stopPropagation();
                // §9.3 bidirectional link: block click highlights the 3D part.
                setSelectedComponentId(element.geometry_component_id ?? null);
              }}
              style={{ cursor: linked ? "pointer" : "default" }}
            >
              <rect
                width={BLOCK_W}
                height={BLOCK_H}
                rx={8}
                fill={color}
                fillOpacity={selected ? 0.28 : 0.12}
                stroke={selected ? "#ff6b35" : color}
                strokeWidth={selected ? 2.5 : 1.4}
              />
              <rect width={BLOCK_W} height={4} rx={2} fill={color} />
              <text x={10} y={22} fontSize={12} fontWeight="bold" fill="#e2e8f0">
                {tr(element.name)}
              </text>
              {element.equation_text && (
                <text x={10} y={42} fontSize={9.5} fill="#cbd5e1">
                  {(() => {
                    const eq = tr(element.equation_text);
                    return eq.length > 34 ? eq.slice(0, 33) + "…" : eq;
                  })()}
                </text>
              )}
              <text x={10} y={62} fontSize={9.5} fill={color}>
                {(t as (k: string) => string)(`sysmodel.domain.${element.domain}`)}
                {element.unit ? ` · [${element.unit}]` : ""}
              </text>
              {linked && (
                <text x={BLOCK_W - 12} y={22} fontSize={9} fill="#ff6b35" textAnchor="end">
                  3D↔
                </text>
              )}
            </g>
          );
        })}
      </svg>
      <div style={{ display: "flex", gap: 14, fontSize: 11, marginTop: 6, flexWrap: "wrap" }}>
        {Object.entries(DOMAIN_COLORS).map(([domain, color]) => (
          <span key={domain} style={{ display: "flex", alignItems: "center", gap: 5, opacity: 0.85 }}>
            <span style={{ width: 10, height: 10, borderRadius: 3, background: color, display: "inline-block" }} />
            {(t as (k: string) => string)(`sysmodel.domain.${domain}`)}
          </span>
        ))}
        <span style={{ opacity: 0.6 }}>3D↔ = {t("sysmodel.linked3d")}</span>
        <span style={{ opacity: 0.6 }}>{t("sysmodel.canvasDisclaimer")}</span>
      </div>
    </div>
  );
}

function ImpactPathStrip({ paths }: { paths: ImpactPaths }) {
  const { t, i18n } = useTranslation();
  const tr = (s: string) => seedTr(s, i18n.resolvedLanguage);
  const [openEdge, setOpenEdge] = useState<string | null>(null);
  if (paths.edges.length === 0) return <div style={{ opacity: 0.6, fontSize: 13 }}>{t("sysmodel.noPaths")}</div>;
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
      {paths.edges.map((edge) => {
        const style = provenanceStyle(edge.provenance);
        const open = openEdge === edge.id;
        return (
          <div
            key={edge.id}
            onClick={() => setOpenEdge(open ? null : edge.id)}
            style={{
              display: "flex",
              alignItems: "center",
              gap: 8,
              padding: "5px 8px",
              borderRadius: 6,
              cursor: "pointer",
              background: "#0b1220",
              borderLeft: `3px ${style.dashed ? "dashed" : "solid"} ${style.color}`,
              fontSize: 12,
            }}
          >
            <span
              style={{
                background: DOMAIN_COLORS[edge.source_domain],
                color: "#0b1220",
                padding: "1px 7px",
                borderRadius: 999,
                fontWeight: 600,
                whiteSpace: "nowrap",
              }}
            >
              {tr(edge.source)}
            </span>
            <span style={{ color: style.color }}>→</span>
            <span
              style={{
                background: DOMAIN_COLORS[edge.target_domain],
                color: "#0b1220",
                padding: "1px 7px",
                borderRadius: 999,
                fontWeight: 600,
                whiteSpace: "nowrap",
              }}
            >
              {tr(edge.target)}
            </span>
            <span style={{ marginLeft: "auto", display: "flex", gap: 6, alignItems: "center", whiteSpace: "nowrap" }}>
              {edge.provenance === "ai_inferred" && (
                <span style={{ background: "#f59e0b", color: "#0b1220", padding: "1px 6px", borderRadius: 4, fontWeight: 700, fontSize: 10 }}>
                  AI
                </span>
              )}
              <span style={{ color: style.color }}>{(t as (k: string) => string)(style.key)}</span>
              {edge.confidence != null && <span style={{ opacity: 0.7 }}>{Math.round(edge.confidence * 100)}%</span>}
            </span>
            {open && (
              <div style={{ flexBasis: "100%", fontSize: 11.5, opacity: 0.85, padding: "4px 2px 2px" }}>
                {edge.mechanism && <div>{tr(edge.mechanism)}</div>}
                {edge.evidence.length > 0 && (
                  <div style={{ marginTop: 3 }}>
                    {t("sysmodel.evidence")}:{" "}
                    {edge.evidence.map((ev, i) => (
                      <span key={i} style={{ fontFamily: "monospace", background: "#1e293b", padding: "1px 5px", borderRadius: 4, marginRight: 5 }}>
                        {ev.business_id}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        );
      })}
      <div style={{ fontSize: 11, opacity: 0.6, marginTop: 2 }}>{t("sysmodel.provenanceNote")}</div>
    </div>
  );
}

const TRUST_STEPS = ["draft", "verified", "validated_for_purpose", "approved_for_reuse", "retired"] as const;

function ModelCardDrawer({ card, onClose }: { card: ModelCardDto; onClose: () => void }) {
  const { t, i18n } = useTranslation();
  const tr = (s: string) => seedTr(s, i18n.resolvedLanguage);
  const stepIndex = TRUST_STEPS.indexOf(card.trust_state);
  return (
    <div
      style={{
        position: "absolute",
        inset: 0,
        background: "rgba(2,6,23,0.72)",
        display: "flex",
        justifyContent: "flex-end",
        zIndex: 30,
      }}
      onClick={onClose}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          width: 420,
          maxWidth: "92%",
          height: "100%",
          overflowY: "auto",
          background: "#0f172a",
          borderLeft: "1px solid #334155",
          padding: 16,
        }}
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "start", gap: 8 }}>
          <h3 style={{ margin: 0, fontSize: 15 }}>{tr(card.title)}</h3>
          <button onClick={onClose} style={{ padding: "2px 9px", borderRadius: 6 }}>✕</button>
        </div>
        <div style={{ fontFamily: "monospace", fontSize: 11, opacity: 0.6, margin: "4px 0 10px" }}>{card.business_id}</div>

        {/* Trust ladder: current state highlighted, retirement to the right */}
        <div style={{ display: "flex", gap: 3, alignItems: "center", marginBottom: 14, flexWrap: "wrap" }}>
          {TRUST_STEPS.map((step, i) => (
            <span key={step} style={{ display: "flex", alignItems: "center", gap: 3 }}>
              <span
                style={{
                  fontSize: 9.5,
                  padding: "2px 6px",
                  borderRadius: 4,
                  background: i === stepIndex ? "#f97316" : "#1e293b",
                  color: i === stepIndex ? "#0b1220" : "#94a3b8",
                  fontWeight: i === stepIndex ? 700 : 400,
                  textDecoration: step === "retired" && i !== stepIndex ? "line-through" : "none",
                }}
              >
                {(t as (k: string) => string)(`sysmodel.trust.${step}`)}
              </span>
              {i < TRUST_STEPS.length - 1 && <span style={{ color: "#7b8aa6", fontSize: 9 }}>→</span>}
            </span>
          ))}
        </div>

        <h4 style={{ margin: "10px 0 4px", fontSize: 12, color: "#94a3b8" }}>{t("sysmodel.cardPurpose")}</h4>
        <p style={{ margin: 0, fontSize: 12.5 }}>{tr(card.purpose)}</p>

        {card.equation_text && (
          <>
            <h4 style={{ margin: "12px 0 4px", fontSize: 12, color: "#94a3b8" }}>{t("sysmodel.cardEquation")}</h4>
            <code style={{ fontSize: 12, background: "#1e293b", padding: "6px 8px", borderRadius: 6, display: "block" }}>{tr(card.equation_text)}</code>
          </>
        )}

        {card.assumptions && card.assumptions.length > 0 && (
          <>
            <h4 style={{ margin: "12px 0 4px", fontSize: 12, color: "#94a3b8" }}>{t("sysmodel.cardAssumptions")}</h4>
            <ul style={{ margin: 0, paddingLeft: 18, fontSize: 12 }}>
              {card.assumptions.map((a, i) => (
                <li key={i} style={{ marginBottom: 2 }}>{tr(a)}</li>
              ))}
            </ul>
          </>
        )}

        {card.evidence && card.evidence.length > 0 && (
          <>
            <h4 style={{ margin: "12px 0 4px", fontSize: 12, color: "#94a3b8" }}>{t("sysmodel.cardEvidence")}</h4>
            {card.evidence.map((ev, i) => (
              <div key={i} style={{ display: "flex", gap: 7, alignItems: "baseline", fontSize: 12, marginBottom: 3 }}>
                <span style={{ fontSize: 10, color: "#38bdf8", textTransform: "uppercase" }}>
                  {ev.kind === "simulation_run" ? t("sysmodel.evSim") : t("sysmodel.evTest")}
                </span>
                <span style={{ fontFamily: "monospace", background: "#1e293b", padding: "1px 6px", borderRadius: 4 }}>
                  {ev.business_id}
                </span>
                {ev.note && <span style={{ opacity: 0.65, fontSize: 11 }}>{tr(ev.note)}</span>}
              </div>
            ))}
          </>
        )}

        {card.validity_envelope && card.validity_envelope.length > 0 && (
          <>
            <h4 style={{ margin: "12px 0 4px", fontSize: 12, color: "#94a3b8" }}>{t("sysmodel.cardValidity")}</h4>
            <table style={{ width: "100%", fontSize: 12, borderCollapse: "collapse" }}>
              <tbody>
                {card.validity_envelope.map((v, i) => (
                  <tr key={i}>
                    <td style={{ padding: "3px 4px", fontFamily: "monospace" }}>{v.parameter}</td>
                    <td style={{ padding: "3px 4px", textAlign: "right" }}>
                      {v.min} – {v.max} {v.unit}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div style={{ fontSize: 11, color: "#eab308", marginTop: 4 }}>{t("sysmodel.validityNote")}</div>
          </>
        )}

        {card.notes && <p style={{ margin: "12px 0 0", fontSize: 11.5, opacity: 0.7 }}>{tr(card.notes)}</p>}
        <div style={{ fontSize: 11, opacity: 0.5, marginTop: 10 }}>
          {t("sysmodel.cardBy")} {card.created_by}
        </div>
      </div>
    </div>
  );
}

const SEVERITY_COLORS: Record<string, string> = {
  error: "#f87171",
  warning: "#fbbf24",
  suggestion: "#7dd3fc",
};

function ReviewSection({ variantId }: { variantId: string }) {
  const { t, i18n } = useTranslation();
  const tr = (s: string) => seedTr(s, i18n.resolvedLanguage);
  const [review, setReview] = useState<ReviewRunDto | null>(null);
  const [running, setRunning] = useState(false);

  useEffect(() => {
    api.latestModelReview(variantId).then(setReview);
  }, [variantId]);

  const runReview = async () => {
    setRunning(true);
    try {
      setReview(await api.runModelReview(variantId));
    } finally {
      setRunning(false);
    }
  };

  const counts = { error: 0, warning: 0, suggestion: 0 };
  for (const f of review?.findings ?? []) counts[f.severity] += 1;

  return (
    <div style={{ marginTop: 16 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
        <h4 style={{ margin: 0, fontSize: 13 }}>
          {t("review.title")}
          {review && (
            <span style={{ marginLeft: 8, opacity: 0.6, fontSize: 11 }}>
              #{review.run_no} · {counts.error}E / {counts.warning}W / {counts.suggestion}S
            </span>
          )}
        </h4>
        <button
          onClick={runReview}
          disabled={running}
          style={{
            padding: "3px 10px",
            borderRadius: 6,
            border: "1px solid #334155",
            background: "#1e293b",
            color: "#e2e8f0",
            fontSize: 12,
            cursor: "pointer",
          }}
        >
          {running ? t("review.running") : t("review.runButton")}
        </button>
      </div>
      {!review ? (
        <div style={{ opacity: 0.6, fontSize: 12.5, marginTop: 6 }}>{t("review.empty")}</div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 6, marginTop: 8 }}>
          {review.findings.map((f) => (
            <div
              key={f.id}
              style={{
                background: "#0b1220",
                borderLeft: `3px solid ${SEVERITY_COLORS[f.severity]}`,
                borderRadius: 6,
                padding: "6px 9px",
                fontSize: 12,
              }}
            >
              <div style={{ display: "flex", gap: 7, alignItems: "baseline", flexWrap: "wrap" }}>
                <span
                  style={{
                    background: SEVERITY_COLORS[f.severity],
                    color: "#0b1220",
                    padding: "0 6px",
                    borderRadius: 4,
                    fontWeight: 700,
                    fontSize: 10,
                    whiteSpace: "nowrap",
                  }}
                >
                  {(t as (k: string) => string)(`review.sev.${f.severity}`)}
                </span>
                <span style={{ fontWeight: 600 }}>{tr(f.title)}</span>
                <span style={{ marginLeft: "auto", opacity: 0.45, fontSize: 10.5, fontFamily: "monospace" }}>
                  {f.business_id}
                </span>
              </div>
              {f.detail && <div style={{ opacity: 0.8, marginTop: 3, fontSize: 11.5 }}>{tr(f.detail)}</div>}
              {f.evidence && f.evidence.length > 0 && (
                <div style={{ marginTop: 4, display: "flex", gap: 5, flexWrap: "wrap" }}>
                  {f.evidence.map((ev, i) => (
                    <span
                      key={i}
                      style={{ fontFamily: "monospace", background: "#1e293b", padding: "1px 6px", borderRadius: 4, fontSize: 10.5 }}
                    >
                      {ev.business_id}
                    </span>
                  ))}
                </div>
              )}
              {f.resolution && (
                <div style={{ opacity: 0.6, marginTop: 3, fontSize: 11 }}>→ {tr(f.resolution)}</div>
              )}
            </div>
          ))}
          <div style={{ fontSize: 11, opacity: 0.55, marginTop: 2 }}>{t("review.appendOnlyNote")}</div>
        </div>
      )}
    </div>
  );
}

function UQSection({ variantId }: { variantId: string }) {
  const { t } = useTranslation();
  const [uq, setUq] = useState<UQAnalysisDto | null>(null);

  useEffect(() => {
    api.latestUQ(variantId).then(setUq);
  }, [variantId]);

  if (!uq) return null;
  const { hist, target_band: band } = uq.results;
  const lo = hist.bin_edges[0];
  const hi = hist.bin_edges[hist.bin_edges.length - 1];
  const span = hi - lo || 1;
  const maxCount = Math.max(...hist.counts, 1);
  const H = 64;
  // band edges mapped into the chart's x range for the overlay
  const bandX = (v: number) => Math.max(0, Math.min(1, (v - lo) / span));

  return (
    <div style={{ marginTop: 16 }}>
      <h4 style={{ margin: 0, fontSize: 13 }}>
        {t("uq.title")}
        <span style={{ marginLeft: 8, opacity: 0.6, fontSize: 11 }}>
          {t("uq.meta", { n: uq.n_samples, seed: uq.seed })}
        </span>
      </h4>
      <svg viewBox="0 0 320 84" style={{ width: "100%", maxWidth: 560, marginTop: 6, background: "#0b1220", borderRadius: 8 }}>
        {/* target band overlay */}
        <rect x={bandX(band.min) * 320} y={0} width={(bandX(band.max) - bandX(band.min)) * 320} height={H} fill="#22c55e" opacity={0.10} />
        <line x1={bandX(band.min) * 320} y1={0} x2={bandX(band.min) * 320} y2={H} stroke="#22c55e" strokeDasharray="3 3" strokeWidth={1} />
        <line x1={bandX(band.max) * 320} y1={0} x2={bandX(band.max) * 320} y2={H} stroke="#22c55e" strokeDasharray="3 3" strokeWidth={1} />
        {hist.counts.map((c, i) => {
          const bw = 320 / hist.counts.length;
          const bh = (c / maxCount) * (H - 6);
          return <rect key={i} x={i * bw + 0.5} y={H - bh} width={bw - 1} height={bh} fill="#38bdf8" opacity={0.85} />;
        })}
        {[["p05", uq.results.p05, "#fbbf24"], ["p50", uq.results.p50, "#f97316"], ["p95", uq.results.p95, "#f87171"]].map(
          ([key, v, color]) => {
            const x = bandX(v as number) * 320;
            return (
              <g key={key as string}>
                <line x1={x} y1={0} x2={x} y2={H} stroke={color as string} strokeWidth={1.2} />
                <text x={x + 2} y={H - 2} fontSize={8} fill={color as string}>
                  {key as string}
                </text>
              </g>
            );
          }
        )}
        <text x={2} y={H + 12} fontSize={8.5} fill="#94a3b8">
          {lo.toFixed(1)}
        </text>
        <text x={318} y={H + 12} fontSize={8.5} fill="#94a3b8" textAnchor="end">
          {hi.toFixed(1)} {uq.metric_unit}
        </text>
      </svg>
      <div style={{ display: "flex", gap: 12, flexWrap: "wrap", fontSize: 12, marginTop: 5 }}>
        <span>{t("uq.violation")}: <b style={{ color: uq.results.violation_prob > 0.05 ? "#f87171" : "#4ade80" }}>
          {(uq.results.violation_prob * 100).toFixed(1)}%
        </b></span>
        <span>P05 {uq.results.p05.toFixed(1)}</span>
        <span>P50 {uq.results.p50.toFixed(1)}</span>
        <span>P95 {uq.results.p95.toFixed(1)} {uq.metric_unit}</span>
      </div>
      <table style={{ fontSize: 11.5, borderCollapse: "collapse", marginTop: 6 }}>
        <tbody>
          {uq.inputs.map((inp) => (
            <tr key={inp.name}>
              <td style={{ paddingRight: 8, fontFamily: "monospace" }}>{inp.name}</td>
              <td style={{ paddingRight: 8 }}>
                {(t as (k: string) => string)(`uq.dist.${inp.distribution}`)}{" "}
                {Object.values(inp.params).join(" / ")}
                {inp.unit ? ` ${inp.unit}` : ""}
              </td>
              <td>
                <span
                  style={{
                    background: "#1e293b",
                    color: "#fbbf24",
                    padding: "0 5px",
                    borderRadius: 4,
                    fontSize: 10,
                  }}
                >
                  {inp.source}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <div style={{ fontSize: 11, opacity: 0.55, marginTop: 4 }}>{t("uq.assumedNote")}</div>
    </div>
  );
}

export function SystemModelView({ variantId }: { variantId: string | null }) {
  const { t } = useTranslation();
  const [model, setModel] = useState<SystemModel | null>(null);
  const [paths, setPaths] = useState<ImpactPaths | null>(null);
  const [card, setCard] = useState<ModelCardDto | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);

  useEffect(() => {
    if (!variantId) return;
    // Stale-data reset happens via the remount `key` in App.tsx — this effect
    // only FETCHES (async setState keeps the linter's cascading-render rule happy).
    api.systemModel(variantId).then(setModel);
    api.impactPaths(variantId).then(setPaths);
    api.modelCard(variantId).then(setCard);
  }, [variantId]);

  return (
    <div style={{ position: "relative", height: "100%", overflowY: "auto", padding: 4 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8, gap: 8 }}>
        <h3 style={{ margin: 0, fontSize: 14 }}>{t("sysmodel.title")}</h3>
        {card && (
          <button
            onClick={() => setDrawerOpen(true)}
            style={{
              padding: "4px 10px",
              borderRadius: 6,
              border: "1px solid #334155",
              background: "#1e293b",
              color: "#e2e8f0",
              fontSize: 12,
              cursor: "pointer",
            }}
          >
            {t("sysmodel.cardButton")}
          </button>
        )}
      </div>

      {model && model.elements.length > 0 ? (
        <ModelCanvas model={model} />
      ) : (
        <div style={{ opacity: 0.6, fontSize: 13, marginBottom: 12 }}>{t("sysmodel.emptyCanvas")}</div>
      )}

      <h4 style={{ margin: "14px 0 6px", fontSize: 13 }}>{t("sysmodel.pathsTitle")}</h4>
      {paths ? <ImpactPathStrip paths={paths} /> : null}

      {variantId && <ReviewSection variantId={variantId} />}
      {variantId && <UQSection variantId={variantId} />}

      {drawerOpen && card && <ModelCardDrawer card={card} onClose={() => setDrawerOpen(false)} />}
    </div>
  );
}
