import { useTranslation } from "react-i18next";
import {
  asicApi,
  type AsicCornerStudy,
  type AsicEco,
  type AsicFaCase,
  type AsicFaEvent,
  type AsicFaultInjection,
  type AsicFmedaItem,
  type AsicGateReport,
  type AsicMeasurementRun,
  type AsicQualPlan,
  type AsicSafetyItem,
  type AsicSignalChain,
} from "../../lib/api";
import { makeSeedTr } from "../../lib/seedL10n";
import { Histogram } from "./asicCharts";
import { READINESS_LEVELS, round2, type AsicTemplate } from "./asicModel";
import { Chip, LiveChip, SectionCard, td, th } from "./asicUi";

// Backend-backed panels for the ASIC workbench (지시서 v1.1 R1). Every row on
// these panels comes from the golden dataset through /api/v1/asic/* — the UI
// never invents a blocker, a pass, or an RCA approval. Backend prose is
// authored in Korean and overlaid at render time with seedTr (ja/en).
// Synthetic provenance stays explicit: SYNTHETIC chips + disclosure strings.

const KIND_COLOR: Record<string, string> = {
  sensor: "#fbbf24",
  analog: "#34d399",
  mixed: "#38bdf8",
  digital: "#a78bfa",
  io: "#f472b6",
  power: "#f87171",
};

export type LiveState = "loading" | "ready" | "empty" | "error";

export type Live = {
  chains: AsicSignalChain[];
  studies: AsicCornerStudy[];
  runs: AsicMeasurementRun[];
  plans: AsicQualPlan[];
  safety: AsicSafetyItem[];
  fmeda: AsicFmedaItem[];
  injections: AsicFaultInjection[];
  faCases: AsicFaCase[];
  faEvents: Record<string, AsicFaEvent[]>;
  ecos: AsicEco[];
  gate: AsicGateReport | null;
};

export const EMPTY_LIVE: Live = {
  chains: [],
  studies: [],
  runs: [],
  plans: [],
  safety: [],
  fmeda: [],
  injections: [],
  faCases: [],
  faEvents: {},
  ecos: [],
  gate: null,
};

// ── data loading (best-effort: a backend miss degrades to the fixture view) ──
export async function loadLive(templateId: string): Promise<{ live: Live; state: LiveState }> {
  const settled = await Promise.allSettled([
    asicApi.listSignalChains(templateId),
    asicApi.listCornerStudies(templateId),
    asicApi.listMeasurementRuns(templateId),
    asicApi.listQualificationPlans(templateId),
    asicApi.listSafetyItems(templateId),
    asicApi.listFmedaItems(templateId),
    asicApi.listFaultInjections(templateId),
    asicApi.listFaCases(templateId),
    asicApi.listEcos(templateId),
    asicApi.gateReport(templateId),
  ]);
  const pick = <T,>(i: number): T[] | null => (settled[i].status === "fulfilled" ? (settled[i] as PromiseFulfilledResult<T[]>).value : null);
  const gate = settled[9].status === "fulfilled" ? (settled[9] as PromiseFulfilledResult<AsicGateReport>).value : null;
  const faCases = pick<AsicFaCase>(7) ?? [];
  const eventLists = await Promise.allSettled(faCases.map((c) => asicApi.listFaEvents(c.id)));
  const faEvents: Record<string, AsicFaEvent[]> = {};
  faCases.forEach((c, i) => {
    if (eventLists[i].status === "fulfilled") faEvents[c.id] = (eventLists[i] as PromiseFulfilledResult<AsicFaEvent[]>).value;
  });
  const live: Live = {
    chains: pick<AsicSignalChain>(0) ?? [],
    studies: pick<AsicCornerStudy>(1) ?? [],
    runs: pick<AsicMeasurementRun>(2) ?? [],
    plans: pick<AsicQualPlan>(3) ?? [],
    safety: pick<AsicSafetyItem>(4) ?? [],
    fmeda: pick<AsicFmedaItem>(5) ?? [],
    injections: pick<AsicFaultInjection>(6) ?? [],
    faCases,
    faEvents,
    ecos: pick<AsicEco>(8) ?? [],
    gate,
  };
  const hasData =
    live.chains.length + live.studies.length + live.runs.length + live.plans.length + live.safety.length +
    live.faCases.length + live.ecos.length + (live.gate ? 1 : 0);
  const anyFail = settled.some((s) => s.status === "rejected");
  const state: LiveState = anyFail ? "error" : hasData > 0 ? "ready" : "empty";
  return { live, state };
}

// ── ② signal chain block diagram (EPIC A A02) ───────────────────────────────
// Deterministic SVG chain: colored blocks left→right with error-budget sigma
// beneath. Renders the backend revision; falls back to the template fixture.

export function latestChain(chains: AsicSignalChain[]): AsicSignalChain | null {
  return chains.length ? chains.reduce((a, b) => (b.revision > a.revision ? b : a)) : null;
}

export function ChainFlowSvg({ blocks, height = 108 }: { blocks: { key: string; kind: string; label: string; budget?: number | null }[]; height?: number }) {
  const W = 760;
  const n = Math.max(1, blocks.length);
  const bw = Math.min(132, (W - 40 - (n - 1) * 26) / n);
  const y0 = height / 2 - 24;
  return (
    <svg viewBox={`0 0 ${W} ${height}`} style={{ width: "100%", height: "auto", display: "block" }}>
      {blocks.map((b, i) => {
        const x = 20 + i * (bw + 26);
        const color = KIND_COLOR[b.kind] ?? "#94a3b8";
        const label = b.label.length > 16 ? `${b.label.slice(0, 15)}…` : b.label;
        return (
          <g key={b.key || i}>
            <rect x={x} y={y0} width={bw} height={48} rx={7} fill={`${color}1c`} stroke={color} strokeWidth={1.2} />
            <text x={x + bw / 2} y={y0 + 20} textAnchor="middle" fontSize={9.5} fontFamily="monospace" fill="#e2e8f0">
              {label}
            </text>
            <text x={x + bw / 2} y={y0 + 34} textAnchor="middle" fontSize={8.5} fill={color} fontFamily="monospace">
              {b.kind}
              {b.budget != null ? ` · σ=${b.budget}` : ""}
            </text>
            {i < blocks.length - 1 && (
              <>
                <line x1={x + bw + 3} y1={y0 + 24} x2={x + bw + 21} y2={y0 + 24} stroke="#475569" strokeWidth={1.2} />
                <polygon points={`${x + bw + 21},${y0 + 20} ${x + bw + 26},${y0 + 24} ${x + bw + 21},${y0 + 28}`} fill="#475569" />
              </>
            )}
          </g>
        );
      })}
    </svg>
  );
}

export function ChainRevisionPanel({ live, liveState, tpl }: { live: Live; liveState: LiveState; tpl: AsicTemplate }) {
  const { i18n } = useTranslation();
  const tr = makeSeedTr(i18n.resolvedLanguage);
  const chain = latestChain(live.chains);
  const blocks = chain
    ? chain.blocks.map((b) => ({
        key: b.key,
        kind: b.kind,
        label: tr(b.label),
        budget: Math.sqrt(Object.values(b.error_budget ?? {}).reduce((a, v) => a + Number(v ?? 0) ** 2, 0)) || null,
      }))
    : tpl.blocks.map((b) => ({ key: b.key, kind: b.kind, label: b.label, budget: null as number | null }));
  return (
    <SectionCard
      title={`ASIC Twin v1.1 — ${tpl.id}`}
      right={
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
          {chain && <Chip color="#38bdf8">{chain.business_id} · rev {chain.revision}</Chip>}
          {chain && <Chip color={chain.source_class === "SYNTHETIC" ? "#a78bfa" : "#34d399"}>{chain.source_class}</Chip>}
          <LiveChip state={liveState} />
        </div>
      }
    >
      <ChainFlowSvg blocks={blocks} />
      {live.chains.length > 1 && (
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginTop: 8 }}>
          {live.chains
            .slice()
            .sort((a, b) => a.revision - b.revision)
            .map((c) => (
              <Chip key={c.id} color={c.status === "superseded" ? "#64748b" : "#34d399"}>
                rev {c.revision} · {c.status}
                {c.supersedes_id ? " ⟲ supersedes" : ""}
              </Chip>
            ))}
          <span style={{ fontSize: 10, color: "#475569", fontFamily: "monospace", alignSelf: "center" }}>
            {chain ? `hash ${chain.content_hash.slice(0, 12)}…` : ""}
          </span>
        </div>
      )}
    </SectionCard>
  );
}

// ── ③ error budget table (frozen with the baseline) ─────────────────────────
const BUDGET_KEYS = ["offset", "gain_error", "inl", "dnl", "noise", "drift"] as const;

export function ChainBudgetPanel({ live, liveState }: { live: Live; liveState: LiveState }) {
  const { i18n } = useTranslation();
  const tr = makeSeedTr(i18n.resolvedLanguage);
  const chain = latestChain(live.chains);
  if (!chain) {
    return (
      <SectionCard title="NRE — error budget (ASIC Twin v1.1)" right={<LiveChip state={liveState} />}>
        <div style={{ fontSize: 12, color: "#64748b" }}>— no backend signal chain for this template</div>
      </SectionCard>
    );
  }
  return (
    <SectionCard
      title={`${chain.business_id} — error budget`}
      right={<LiveChip state={liveState} />}
    >
      <div style={{ overflowX: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr>
              <th style={th}>block</th>
              <th style={th}>kind</th>
              {BUDGET_KEYS.map((k) => (
                <th key={k} style={th}>{k}</th>
              ))}
              <th style={th}>reqs</th>
            </tr>
          </thead>
          <tbody>
            {chain.blocks.map((b) => (
              <tr key={b.key}>
                <td style={{ ...td, fontFamily: "monospace", color: "#7dd3fc" }}>{tr(b.label)}</td>
                <td style={td}>
                  <Chip color={KIND_COLOR[b.kind] ?? "#94a3b8"}>{b.kind}</Chip>
                </td>
                {BUDGET_KEYS.map((k) => (
                  <td key={k} style={{ ...td, fontFamily: "monospace" }}>
                    {b.error_budget?.[k] != null ? String(b.error_budget[k]) : "—"}
                  </td>
                ))}
                <td style={{ ...td, fontFamily: "monospace", color: "#94a3b8" }}>{(b.requirement_ids ?? []).join(", ") || "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </SectionCard>
  );
}

// ── ④ corner / monte-carlo studies (EPIC A D04) ─────────────────────────────
export function CornerStudiesPanel({ live, liveState }: { live: Live; liveState: LiveState }) {
  const { i18n, t } = useTranslation();
  const tr = makeSeedTr(i18n.resolvedLanguage);
  if (live.studies.length === 0) {
    return (
      <SectionCard title="Corner / Monte-Carlo (ASIC Twin v1.1)" right={<LiveChip state={liveState} />}>
        <div style={{ fontSize: 12, color: "#64748b" }}>{t("asic.mc.none")}</div>
      </SectionCard>
    );
  }
  return (
    <SectionCard title="Corner / Monte-Carlo (ASIC Twin v1.1)" right={<LiveChip state={liveState} />}>
      {live.studies.map((s) => (
        <div key={s.id} style={{ border: "1px solid #1e293b", borderRadius: 8, padding: 10, marginBottom: 10, background: "#0f172a" }}>
          <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap", marginBottom: 8 }}>
            <b style={{ fontFamily: "monospace", color: "#7dd3fc", fontSize: 12 }}>{s.business_id}</b>
            <Chip color="#38bdf8">{s.kind}</Chip>
            <Chip color="#64748b">n={s.n_draws} · seed={s.seed}</Chip>
            <Chip color="#a78bfa">{s.source_class}</Chip>
            {s.result?.model_ood ? (
              <Chip color="#f87171" title={(s.result.ood_reason ?? []).join(" | ")}>⚠ {t("asic.mc.ood")}</Chip>
            ) : null}
            <span style={{ fontSize: 10, color: "#475569", fontFamily: "monospace" }}>{s.tool_version}</span>
          </div>
          {(s.result?.per_output ?? []).map((o) => (
            <div key={o.output} style={{ display: "grid", gridTemplateColumns: "minmax(200px, 300px) 1fr", gap: 12, alignItems: "start", marginBottom: 8 }}>
              <div style={{ overflowX: "auto" }}>
                <table style={{ width: "100%", borderCollapse: "collapse" }}>
                  <tbody>
                    <tr>
                      <th style={th}>{o.output}{o.unit ? ` (${o.unit})` : ""}</th>
                      <th style={th}>p50</th>
                      <th style={th}>p95</th>
                      <th style={th}>p99</th>
                      <th style={th}>viol</th>
                    </tr>
                    <tr>
                      <td style={{ ...td, fontFamily: "monospace", color: "#94a3b8" }}>nom {o.nominal}</td>
                      <td style={{ ...td, fontFamily: "monospace" }}>{round2(o.p50)}</td>
                      <td style={{ ...td, fontFamily: "monospace" }}>{round2(o.p95)}</td>
                      <td style={{ ...td, fontFamily: "monospace" }}>{round2(o.p99)}</td>
                      <td style={{ ...td, fontFamily: "monospace", color: o.violation_rate > 0 ? "#fbbf24" : "#34d399" }}>
                        {(o.violation_rate * 100).toFixed(2)}%
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
              <div>
                {o.hist && o.hist.counts.length > 0 ? (
                  <Histogram values={histValues(o.hist.edges, o.hist.counts)} specMin={o.spec_min} specMax={o.spec_max} height={110} />
                ) : null}
                <div style={{ fontSize: 10, color: "#475569", fontFamily: "monospace" }}>
                  spec [{o.spec_min ?? "—"}, {o.spec_max ?? "—"}] · T={s.result?.temperatures_c.join("/")} °C
                </div>
              </div>
            </div>
          ))}
          {s.result?.disclosure && (
            <div style={{ fontSize: 10, color: "#a78bfa" }}>◈ {tr(s.result.disclosure)}</div>
          )}
        </div>
      ))}
    </SectionCard>
  );
}

// The backend stores binned counts; re-expand to per-bin values so the shared
// Histogram renderer can bucket them again without the raw draws.
function histValues(edges: number[], counts: number[]): number[] {
  const out: number[] = [];
  counts.forEach((c, i) => {
    for (let k = 0; k < c; k++) out.push(edges.length > i + 1 ? (edges[i] + edges[i + 1]) / 2 : edges[i]);
  });
  return out;
}

// ── ⑤ equipment measurement runs (EPIC E) ───────────────────────────────────
export function EquipmentRunsPanel({ live, liveState }: { live: Live; liveState: LiveState }) {
  const { i18n } = useTranslation();
  const tr = makeSeedTr(i18n.resolvedLanguage);
  const now = Date.now();
  if (live.runs.length === 0) {
    return (
      <SectionCard title="Equipment measurement runs (EPIC E)" right={<LiveChip state={liveState} />}>
        <div style={{ fontSize: 12, color: "#64748b" }}>— no imported measurement run</div>
      </SectionCard>
    );
  }
  return (
    <SectionCard title="Equipment measurement runs (EPIC E)" right={<LiveChip state={liveState} />}>
      <div style={{ overflowX: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr>
              <th style={th}>run</th>
              <th style={th}>equipment</th>
              <th style={th}>prog</th>
              <th style={th}>executed</th>
              <th style={th}>points</th>
              <th style={th}>calibration</th>
              <th style={th}>findings</th>
              <th style={th}>status</th>
            </tr>
          </thead>
          <tbody>
            {live.runs.map((r) => {
              const calExpired = r.calibration_expires_at ? new Date(r.calibration_expires_at).getTime() < now : false;
              return (
                <tr key={r.id}>
                  <td style={{ ...td, fontFamily: "monospace", color: "#7dd3fc" }}>
                    {r.business_id}
                    {r.lot_ref && <span style={{ display: "block", fontSize: 9, color: "#64748b" }}>lot {r.lot_ref}</span>}
                  </td>
                  <td style={{ ...td, fontFamily: "monospace" }}>
                    {r.equipment_id}
                    <span style={{ display: "block", fontSize: 9, color: "#64748b" }}>
                      {r.equipment_type}{r.equipment_model ? ` · ${r.equipment_model}` : ""}
                    </span>
                  </td>
                  <td style={{ ...td, fontFamily: "monospace" }}>{r.program_revision ?? "—"}</td>
                  <td style={{ ...td, fontFamily: "monospace", color: "#94a3b8" }}>{r.executed_at?.slice(0, 10) ?? "—"}</td>
                  <td style={{ ...td, fontFamily: "monospace" }}>{r.points?.length ?? 0}</td>
                  <td style={td}>
                    <Chip color={calExpired ? "#f87171" : "#34d399"}>
                      {calExpired ? "✕ EXPIRED" : "✓ valid"}
                      {r.calibration_expires_at ? ` ${r.calibration_expires_at.slice(0, 10)}` : ""}
                    </Chip>
                  </td>
                  <td style={td}>
                    {(r.findings ?? []).length === 0 ? (
                      <span style={{ color: "#475569" }}>—</span>
                    ) : (
                      <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
                        {(r.findings ?? []).map((f, i) => (
                          <Chip key={i} color="#fbbf24" title={f.detail ? tr(f.detail) : undefined}>{f.code}</Chip>
                        ))}
                      </div>
                    )}
                  </td>
                  <td style={td}>
                    <Chip color={r.status === "verified_ingest" ? "#34d399" : r.status === "rejected" ? "#f87171" : "#fbbf24"}>{r.status}</Chip>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </SectionCard>
  );
}

// ── ⑥ test program twin (T05, fixture) ──────────────────────────────────────
const TP_STEP_LIMITS: Record<string, { specKey: string; fmt: (v: number) => string }[]> = {};

export function TestProgramTwin({ tpl, testProgRev, maskRev }: { tpl: AsicTemplate; testProgRev: number; maskRev: string }) {
  const { t } = useTranslation();
  // Deterministic flow derived from the template spec — no hardcoding per
  // product; limits carry the same ±tol strings as the spec table.
  const steps = [
    { key: "cont", limit: t("asic.tp.limElec"), time: 40 },
    { key: "dc", limit: t("asic.tp.limElec"), time: 65 },
    { key: "sens", limit: specLim(tpl, 0), time: 120 },
    { key: "off", limit: specLim(tpl, 1), time: 95 },
    { key: "inl", limit: specLim(tpl, 2), time: 180 },
    { key: "temp", limit: `${t("asic.tp.limTemp")} ${tpl.grade}`, time: 240 },
    { key: "obd", limit: t("asic.tp.limDiag"), time: 70 },
  ];
  const total = steps.reduce((a, s) => a + s.time, 0);
  const covered = tpl.verItems.filter((v) => v.done).length;
  const coverage = Math.round((covered / Math.max(1, tpl.verItems.length)) * 100);
  return (
    <SectionCard
      title={`${t("asic.s6.tp")} — ATE v${testProgRev}`}
      right={<Chip color="#a78bfa" title={t("asic.conf.title")}>◈ {t("asic.conf.synthetic_fixture")}</Chip>}
    >
      <div style={{ fontSize: 11, color: "#94a3b8", marginBottom: 8, fontFamily: "monospace" }}>
        mask {maskRev} · site 1–4 · {coverage}% {t("asic.s6.tpCoverage")}
      </div>
      <div style={{ overflowX: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr>
              <th style={th}>#</th>
              <th style={th}>{t("asic.s6.tpStep")}</th>
              <th style={th}>{t("asic.s6.tpLimit")}</th>
              <th style={th}>{t("asic.s6.tpTime")}</th>
            </tr>
          </thead>
          <tbody>
            {steps.map((s, i) => (
              <tr key={s.key}>
                <td style={{ ...td, fontFamily: "monospace", color: "#475569" }}>{i + 1}</td>
                <td style={td}>{t(`asic.tp.${s.key}` as never)}</td>
                <td style={{ ...td, fontFamily: "monospace", color: "#7dd3fc" }}>{s.limit}</td>
                <td style={{ ...td, fontFamily: "monospace" }}>{s.time} ms</td>
              </tr>
            ))}
            <tr>
              <td style={td} />
              <td style={{ ...td, fontWeight: 600 }}>{t("asic.s6.tpTotal")}</td>
              <td style={td} />
              <td style={{ ...td, fontFamily: "monospace", color: "#fbbf24" }}>{(total / 1000).toFixed(2)} s</td>
            </tr>
          </tbody>
        </table>
      </div>
      <div style={{ fontSize: 10, color: "#475569", marginTop: 8 }}>{t("asic.s6.tpNote")}</div>
    </SectionCard>
  );
}

function specLim(tpl: AsicTemplate, i: number): string {
  const s = tpl.specs[Math.min(i, tpl.specs.length - 1)];
  return `${s.value} ${s.unit} ${s.tol}`;
}

void TP_STEP_LIMITS;

// ── ⑦ qualification matrix from the golden dataset (EPIC F Q07) ─────────────
export function BackendQualPanel({ live, liveState }: { live: Live; liveState: LiveState }) {
  const { i18n } = useTranslation();
  const tr = makeSeedTr(i18n.resolvedLanguage);
  if (live.plans.length === 0) {
    return (
      <SectionCard title="Qualification matrix — golden dataset" right={<LiveChip state={liveState} />}>
        <div style={{ fontSize: 12, color: "#64748b" }}>— no backend qualification plan</div>
      </SectionCard>
    );
  }
  return (
    <SectionCard title="Qualification matrix — golden dataset" right={<LiveChip state={liveState} />}>
      {live.plans.map((p) => (
        <div key={p.id} style={{ marginBottom: 12 }}>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 6, alignItems: "center" }}>
            <b style={{ fontFamily: "monospace", color: "#7dd3fc", fontSize: 12 }}>{p.business_id}</b>
            <Chip color="#38bdf8">{p.grade}</Chip>
            <Chip color="#64748b">{p.policy_version}</Chip>
            {p.standard_version && <Chip color="#a78bfa">{p.standard_version}</Chip>}
            {p.note && <span style={{ fontSize: 11, color: "#94a3b8" }}>{tr(p.note)}</span>}
          </div>
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead>
                <tr>
                  <th style={th}>group</th>
                  <th style={th}>method</th>
                  <th style={th}>condition</th>
                  <th style={th}>samples</th>
                  <th style={th}>status</th>
                  <th style={th}>notes</th>
                </tr>
              </thead>
              <tbody>
                {p.results.map((r) => (
                  <tr key={r.id}>
                    <td style={{ ...td, fontFamily: "monospace", color: "#7dd3fc" }}>{r.group}</td>
                    <td style={td}>{tr(r.method)}</td>
                    <td style={{ ...td, fontFamily: "monospace", color: "#94a3b8" }}>
                      {Object.entries(r.condition ?? {})
                        .map(([k, v]) => `${k}=${typeof v === "object" ? JSON.stringify(v) : tr(String(v))}`)
                        .join(" · ")}
                    </td>
                    <td style={{ ...td, fontFamily: "monospace" }}>{r.samples}</td>
                    <td style={td}>
                      <Chip color={r.status === "pass" ? "#34d399" : r.status === "fail" ? "#f87171" : "#fbbf24"}>{r.status}</Chip>
                    </td>
                    <td style={{ ...td, fontSize: 10, color: "#94a3b8" }}>
                      {r.failed_param && <span style={{ color: "#f87171" }}>failed: {r.failed_param} </span>}
                      {r.fa_case_id && <span>→ FA case </span>}
                      {r.waiver_ref && (
                        <span style={{ color: "#a78bfa" }}>
                          waiver {r.waiver_ref}
                          {r.waiver_expires_at ? ` (→ ${r.waiver_expires_at.slice(0, 10)})` : ""}
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ))}
    </SectionCard>
  );
}

// ── ⑦ safety trace SG→FSR→TSR→HW + FMEDA + fault injection (EPIC F S07) ─────
const LEVEL_COLOR: Record<string, string> = {
  safety_goal: "#f87171",
  fsr: "#fbbf24",
  tsr: "#38bdf8",
  hw_req: "#34d399",
};

export function SafetyTracePanel({ live, liveState }: { live: Live; liveState: LiveState }) {
  const { i18n } = useTranslation();
  const tr = makeSeedTr(i18n.resolvedLanguage);
  if (live.safety.length === 0) {
    return (
      <SectionCard title="Safety trace (EPIC F)" right={<LiveChip state={liveState} />}>
        <div style={{ fontSize: 12, color: "#64748b" }}>— no backend safety items</div>
      </SectionCard>
    );
  }
  const byParent = new Map<string | null, AsicSafetyItem[]>();
  for (const s of live.safety) {
    const list = byParent.get(s.parent_id) ?? [];
    list.push(s);
    byParent.set(s.parent_id, list);
  }
  const rows: { item: AsicSafetyItem; depth: number }[] = [];
  const walk = (parent: string | null, depth: number) => {
    for (const item of byParent.get(parent) ?? []) {
      rows.push({ item, depth });
      walk(item.id, depth + 1);
    }
  };
  walk(null, 0);
  const fmedaByItem = new Map<string, AsicFmedaItem[]>();
  for (const f of live.fmeda) {
    const list = fmedaByItem.get(f.safety_item_id) ?? [];
    list.push(f);
    fmedaByItem.set(f.safety_item_id, list);
  }
  return (
    <SectionCard title="Safety trace SG→FSR→TSR→HW (EPIC F)" right={<LiveChip state={liveState} />}>
      <div style={{ overflowX: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr>
              <th style={th}>level</th>
              <th style={th}>item</th>
              <th style={th}>ASIL</th>
              <th style={th}>mechanism / safe state</th>
              <th style={th}>DC</th>
              <th style={th}>FITT</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(({ item, depth }) => {
              return (
                <tr key={item.id}>
                  <td style={td}>
                    <Chip color={LEVEL_COLOR[item.level] ?? "#94a3b8"}>{item.level}</Chip>
                  </td>
                  <td style={td}>
                    <span style={{ paddingLeft: depth * 14 }}>
                      {depth > 0 && <span style={{ color: "#475569" }}>└ </span>}
                      {tr(item.title)}
                    </span>
                    {item.safe_state && <span style={{ display: "block", fontSize: 9, color: "#64748b" }}>safe state: {tr(item.safe_state)}</span>}
                  </td>
                  <td style={{ ...td, fontFamily: "monospace", color: item.asil === "B" ? "#fbbf24" : "#94a3b8" }}>{item.asil ?? "—"}</td>
                  <td style={{ ...td, fontSize: 10, color: "#94a3b8" }}>{item.safety_mechanism ? tr(item.safety_mechanism) : "—"}</td>
                  <td style={{ ...td, fontFamily: "monospace" }}>{item.diagnostic_coverage_pct != null ? `${item.diagnostic_coverage_pct}%` : "—"}</td>
                  <td style={{ ...td, fontFamily: "monospace" }}>{item.response_time_ms != null ? `${item.response_time_ms} ms` : "—"}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {live.fmeda.length > 0 && (
        <>
          <div style={{ fontSize: 11, color: "#64748b", margin: "10px 0 6px", fontFamily: "monospace" }}>FMEDA</div>
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead>
                <tr>
                  <th style={th}>failure mode</th>
                  <th style={th}>dist</th>
                  <th style={th}>DC</th>
                  <th style={th}>FIT</th>
                  <th style={th}>source</th>
                </tr>
              </thead>
              <tbody>
                {live.fmeda.map((f) => (
                  <tr key={f.id}>
                    <td style={td}>{tr(f.failure_mode)}</td>
                    <td style={{ ...td, fontFamily: "monospace" }}>{f.distribution_pct}%</td>
                    <td style={{ ...td, fontFamily: "monospace" }}>{f.dc_pct != null ? `${f.dc_pct}%` : "—"}</td>
                    <td style={{ ...td, fontFamily: "monospace" }}>{f.fit_rate ?? "—"}</td>
                    <td style={{ ...td, fontFamily: "monospace", fontSize: 10, color: "#475569" }}>
                      {f.source_ref}
                      {f.formula_version ? ` · ${f.formula_version}` : ""}
                      {f.source_hash ? ` · sha ${f.source_hash.slice(0, 8)}…` : ""}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
      {live.injections.length > 0 && (
        <>
          <div style={{ fontSize: 11, color: "#64748b", margin: "10px 0 6px", fontFamily: "monospace" }}>Fault injection</div>
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead>
                <tr>
                  <th style={th}>run</th>
                  <th style={th}>method</th>
                  <th style={th}>stimulus</th>
                  <th style={th}>expected</th>
                  <th style={th}>observed</th>
                  <th style={th}>verdict</th>
                </tr>
              </thead>
              <tbody>
                {live.injections.map((fi) => (
                  <tr key={fi.id}>
                    <td style={{ ...td, fontFamily: "monospace", color: "#7dd3fc" }}>{fi.business_id}</td>
                    <td style={{ ...td, fontFamily: "monospace" }}>{tr(fi.method)}</td>
                    <td style={{ ...td, fontSize: 10 }}>{tr(fi.stimulus)}</td>
                    <td style={{ ...td, fontSize: 10 }}>{tr(fi.expected)}</td>
                    <td style={{ ...td, fontSize: 10 }}>{tr(fi.observed)}</td>
                    <td style={td}>
                      <Chip color={fi.status === "pass" ? "#34d399" : fi.status === "fail" ? "#f87171" : "#fbbf24"}>{fi.status}</Chip>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </SectionCard>
  );
}

// ── ⑧ gate report — rendered VERBATIM from the backend (§6 불변규칙 4) ───────
export function GateReportPanel({ live, liveState, fallback }: { live: Live; liveState: LiveState; fallback: React.ReactNode }) {
  const { i18n } = useTranslation();
  const tr = makeSeedTr(i18n.resolvedLanguage);
  const gate = live.gate;
  if (!gate) {
    return (
      <SectionCard title="Release gate report (ASIC Twin v1.1)" right={<LiveChip state={liveState} />}>
        <div style={{ fontSize: 12, color: "#64748b", marginBottom: 8 }}>— gate-report unavailable; fixture evaluation below</div>
        {fallback}
      </SectionCard>
    );
  }
  const ladderKey = (key: string) => READINESS_LEVELS.find((l) => l.key === key);
  return (
    <SectionCard
      title="Release gate report (ASIC Twin v1.1)"
      right={
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
          <Chip color={gate.status === "pass" ? "#34d399" : "#f87171"}>{gate.status}</Chip>
          <Chip color="#64748b">{gate.policy_version}</Chip>
          <LiveChip state={liveState} />
        </div>
      }
    >
      <div style={{ fontSize: 10, color: "#475569", marginBottom: 8, fontFamily: "monospace" }}>
        {gate.gate_id} · evaluated_at {gate.evaluated_at.slice(0, 19).replace("T", " ")}
      </div>
      {/* readiness ladder — the backend's rung lights up; unreachable rungs stay ✕ */}
      <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 10 }}>
        {READINESS_LEVELS.map((l) => {
          const isCurrent = l.key === gate.readiness;
          const reachable = ladderKey(gate.readiness) ? READINESS_LEVELS.findIndex((x) => x.key === l.key) <= READINESS_LEVELS.findIndex((x) => x.key === gate.readiness) : false;
          return (
            <Chip key={l.key} color={isCurrent ? "#34d399" : reachable ? "#64748b" : "#7f1d1d"}>
              {isCurrent ? "● " : reachable ? "○ " : "✕ "}
              {l.key}
            </Chip>
          );
        })}
        {!gate.readiness_reachable && <Chip color="#fbbf24">readiness capped (synthetic evidence)</Chip>}
      </div>
      {gate.blockers.length > 0 && (
        <div style={{ marginBottom: 10 }}>
          {gate.blockers.map((b) => (
            <div key={b.code} style={{ border: "1px solid #f8717155", background: "#f8717111", borderRadius: 8, padding: "8px 10px", marginBottom: 6 }}>
              <b style={{ fontFamily: "monospace", fontSize: 11, color: "#f87171" }}>▌ {b.code}</b>
              <div style={{ fontSize: 11, color: "#fca5a5", marginTop: 2 }}>{tr(b.detail)}</div>
              {b.evidence.length > 0 && (
                <div style={{ fontSize: 10, fontFamily: "monospace", color: "#94a3b8", marginTop: 3 }}>evidence: {b.evidence.join(", ")}</div>
              )}
            </div>
          ))}
        </div>
      )}
      <div style={{ overflowX: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr>
              <th style={th}>check</th>
              <th style={th}>status</th>
              <th style={th}>actual</th>
              <th style={th}>target</th>
              <th style={th}>evidence</th>
            </tr>
          </thead>
          <tbody>
            {gate.checks.map((c) => (
              <tr key={c.check_id}>
                <td style={{ ...td, fontFamily: "monospace", color: "#7dd3fc" }}>{c.check_id}</td>
                <td style={td}>
                  <Chip color={c.status === "pass" ? "#34d399" : "#f87171"}>{c.status}</Chip>
                </td>
                <td style={{ ...td, fontFamily: "monospace" }}>{typeof c.actual === "object" ? JSON.stringify(c.actual) : String(c.actual)}</td>
                <td style={{ ...td, fontFamily: "monospace", color: "#94a3b8" }}>{typeof c.target === "object" ? JSON.stringify(c.target) : String(c.target)}</td>
                <td style={{ ...td, fontFamily: "monospace", fontSize: 10, color: "#475569" }}>{c.evidence_refs.join(", ") || "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </SectionCard>
  );
}

// ── ⑨ failure analysis studio — case → RCA → ECO → verification (EPIC G) ────
export function FaStudio({ live, liveState }: { live: Live; liveState: LiveState }) {
  const { i18n } = useTranslation();
  const tr = makeSeedTr(i18n.resolvedLanguage);
  if (live.faCases.length === 0 && live.ecos.length === 0) {
    return (
      <SectionCard title="FA studio — closed loop (EPIC G)" right={<LiveChip state={liveState} />}>
        <div style={{ fontSize: 12, color: "#64748b" }}>— no backend FA case / ECO</div>
      </SectionCard>
    );
  }
  const FA_STATUS_COLOR: Record<string, string> = {
    open: "#fbbf24",
    analyzing: "#38bdf8",
    rca_approved: "#a78bfa",
    eco_open: "#f472b6",
    verified: "#34d399",
    closed: "#34d399",
  };
  const ECO_STATUS_COLOR: Record<string, string> = {
    open: "#fbbf24",
    analyzed: "#38bdf8",
    regression_pending: "#a78bfa",
    closed: "#34d399",
  };
  return (
    <SectionCard title="FA studio — closed loop (EPIC G)" right={<LiveChip state={liveState} />}>
      {live.faCases.map((c) => (
        <div key={c.id} style={{ border: "1px solid #1e293b", borderRadius: 8, padding: 10, marginBottom: 10, background: "#0f172a" }}>
          <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
            <b style={{ fontFamily: "monospace", color: "#7dd3fc", fontSize: 12 }}>{c.business_id}</b>
            <Chip color="#64748b">{c.scope}</Chip>
            {c.lot_ref && <Chip color="#64748b">lot {c.lot_ref}</Chip>}
            <Chip color={FA_STATUS_COLOR[c.status] ?? "#94a3b8"}>{c.status}</Chip>
            {c.cause_class && <Chip color="#a78bfa">{c.cause_class}</Chip>}
          </div>
          <div style={{ fontSize: 12, color: "#e2e8f0", margin: "6px 0" }}>{tr(c.symptom)}</div>
          {(c.observations ?? []).length > 0 && (
            <div style={{ marginBottom: 6 }}>
              <div style={{ fontSize: 10, color: "#64748b", fontFamily: "monospace" }}>observations</div>
              {(c.observations ?? []).map((o, i) => (
                <div key={i} style={{ fontSize: 11, color: "#cbd5e1" }}>
                  • {tr(o.fact)}
                  {o.source && <span style={{ color: "#475569", fontFamily: "monospace" }}> ← {o.source}</span>}
                </div>
              ))}
            </div>
          )}
          {(c.hypotheses ?? []).length > 0 && (
            <div style={{ marginBottom: 6 }}>
              <div style={{ fontSize: 10, color: "#64748b", fontFamily: "monospace" }}>hypotheses</div>
              {(c.hypotheses ?? []).map((h, i) => (
                <div key={i} style={{ fontSize: 11, color: h.excluded ? "#64748b" : "#cbd5e1" }}>
                  {h.excluded ? "✕ " : "• "}
                  <span style={h.excluded ? { textDecoration: "line-through" } : undefined}>{tr(h.text)}</span>
                  {h.excluded && h.exclusion_basis ? ` — ${tr(h.exclusion_basis)}` : ""}
                  {(h.confirm_tests ?? []).length > 0 && !h.excluded && (
                    <span style={{ color: "#475569", fontFamily: "monospace" }}> [{(h.confirm_tests ?? []).map((ct) => tr(ct)).join(", ")}]</span>
                  )}
                </div>
              ))}
            </div>
          )}
          {c.root_cause_confirmed && c.root_cause && (
            <div style={{ border: "1px solid #a78bfa55", background: "#a78bfa11", borderRadius: 8, padding: "8px 10px", marginTop: 6 }}>
              <b style={{ fontSize: 11, color: "#a78bfa" }}>root cause confirmed{c.cause_class ? ` · ${c.cause_class}` : ""}</b>
              <div style={{ fontSize: 11, color: "#ddd6fe", marginTop: 2 }}>{tr(c.root_cause)}</div>
              {c.location && (
                <div style={{ fontSize: 10, fontFamily: "monospace", color: "#64748b", marginTop: 3 }}>
                  location: {String((c.location as Record<string, unknown>).ref ?? "—")}
                </div>
              )}
            </div>
          )}
          {(live.faEvents[c.id] ?? []).length > 0 && (
            <div style={{ marginTop: 8, borderLeft: "2px solid #1e293b", paddingLeft: 10 }}>
              <div style={{ fontSize: 10, color: "#64748b", fontFamily: "monospace", marginBottom: 4 }}>event ledger (append-only)</div>
              {(live.faEvents[c.id] ?? []).map((e) => (
                <div key={e.id} style={{ fontSize: 10.5, marginBottom: 3, color: "#94a3b8" }}>
                  <span style={{ fontFamily: "monospace", color: "#38bdf8" }}>{e.event_type}</span>{" "}
                  <span style={{ color: "#475569" }}>{e.occurred_at.slice(0, 16).replace("T", " ")} · {e.actor}</span>
                  {e.comment && <span> — {tr(e.comment)}</span>}
                </div>
              ))}
            </div>
          )}
        </div>
      ))}
      {live.ecos.map((e) => (
        <div key={e.id} style={{ border: "1px solid #1e293b", borderRadius: 8, padding: 10, marginBottom: 10, background: "#0f172a" }}>
          <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
            <b style={{ fontFamily: "monospace", color: "#7dd3fc", fontSize: 12 }}>{e.business_id}</b>
            <Chip color="#64748b">{e.trigger}</Chip>
            <Chip color={ECO_STATUS_COLOR[e.status] ?? "#94a3b8"}>{e.status}</Chip>
            {e.design_rev_from && e.design_rev_to && (
              <Chip color="#38bdf8">{e.design_rev_from} → {e.design_rev_to}</Chip>
            )}
            {e.mask_revision && <Chip color="#a78bfa">mask {e.mask_revision}</Chip>}
            {e.test_program_revision && <Chip color="#fbbf24">TP {e.test_program_revision}</Chip>}
          </div>
          <div style={{ fontSize: 12, color: "#e2e8f0", margin: "6px 0" }}>{tr(e.title)}</div>
          {e.description && <div style={{ fontSize: 11, color: "#94a3b8" }}>{tr(e.description)}</div>}
          {(e.impact ?? []).length > 0 && (
            <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginTop: 6 }}>
              {(e.impact ?? []).map((row, i) => (
                <Chip key={i} color="#64748b" title={tr(String(row.detail ?? ""))}>
                  {String(row.area ?? "?")}
                </Chip>
              ))}
            </div>
          )}
          {(e.regression_run_ids ?? []).length > 0 && (
            <div style={{ fontSize: 10, fontFamily: "monospace", color: "#475569", marginTop: 6 }}>
              regression: {(e.regression_run_ids ?? []).join(", ")}
            </div>
          )}
          {e.verification_note && (
            <div style={{ fontSize: 11, color: "#34d399", marginTop: 6 }}>
              ✓ {tr(e.verification_note)}
              {e.closed_at && <span style={{ color: "#475569", fontFamily: "monospace" }}> · closed {e.closed_at.slice(0, 10)}</span>}
            </div>
          )}
        </div>
      ))}
    </SectionCard>
  );
}
