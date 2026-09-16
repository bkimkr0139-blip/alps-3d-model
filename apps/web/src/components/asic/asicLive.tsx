import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  asicApi,
  type AsicAssumption,
  type AsicAssumptionEvent,
  type AsicCopilotDiff,
  type AsicCopilotInteraction,
  type AsicCornerStudy,
  type AsicDeviation,
  type AsicEvidenceReport,
  type AsicEco,
  type AsicFaCase,
  type AsicFaEvent,
  type AsicFaultInjection,
  type AsicFmedaItem,
  type AsicGateReport,
  type AsicImpactScan,
  type AsicLotTraveler,
  type AsicMeasurementRun,
  type AsicPartner,
  type AsicQualPlan,
  type AsicSafetyItem,
  type AsicSignalChain,
  type AsicTestFlowAnalysis,
  type AsicToolRun,
  type AsicTradeStudy,
  type AsicWaferMap,
} from "../../lib/api";
import { keycloak } from "../../lib/keycloak";
import { makeSeedTr } from "../../lib/seedL10n";
import { sha256Hex } from "../../lib/sha256";
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
  // R2 (EPIC B·C·D·H)
  tradeStudies: AsicTradeStudy[];
  toolRuns: AsicToolRun[];
  flowAnalysis: AsicTestFlowAnalysis | null;
  waferMaps: AsicWaferMap[];
  partners: AsicPartner[];
  travelers: AsicLotTraveler[];
  // R3 (EPIC I·J)
  assumptions: AsicAssumption[];
  scans: Record<string, AsicImpactScan[]>;
  deviations: AsicDeviation[];
  copilot: AsicCopilotInteraction[];
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
  tradeStudies: [],
  toolRuns: [],
  flowAnalysis: null,
  waferMaps: [],
  partners: [],
  travelers: [],
  assumptions: [],
  scans: {},
  deviations: [],
  copilot: [],
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
    // R2 — listTradeStudies is CAN_COST-restricted: a 403 for roles without
    // the group is a legitimate state (panel shows "restricted"), not an
    // outage, so it must not flip the whole workspace to "error"
    asicApi.listTradeStudies(templateId),
    asicApi.listToolRuns(templateId),
    asicApi.testFlowAnalysis(templateId),
    asicApi.listWaferMaps(templateId),
    asicApi.listPartners(),
    asicApi.listLotTravelers(templateId),
    // R3 — EPIC I·J (lists are open to every authenticated role)
    asicApi.listAssumptions(templateId),
    asicApi.listDeviations(templateId),
    asicApi.listCopilot(templateId),
  ]);
  const pick = <T,>(i: number): T[] | null => (settled[i].status === "fulfilled" ? (settled[i] as PromiseFulfilledResult<T[]>).value : null);
  const one = <T,>(i: number): T | null => (settled[i].status === "fulfilled" ? (settled[i] as PromiseFulfilledResult<T>).value : null);
  const gate = one<AsicGateReport>(9);
  const flowAnalysis = one<AsicTestFlowAnalysis>(12);
  const faCases = pick<AsicFaCase>(7) ?? [];
  const eventLists = await Promise.allSettled(faCases.map((c) => asicApi.listFaEvents(c.id)));
  const faEvents: Record<string, AsicFaEvent[]> = {};
  faCases.forEach((c, i) => {
    if (eventLists[i].status === "fulfilled") faEvents[c.id] = (eventLists[i] as PromiseFulfilledResult<AsicFaEvent[]>).value;
  });
  // per-assumption impact scans (가정 수가 적어 N+1 허용 — 패널이 findings 상태를 그려야 한다)
  const assumptions = pick<AsicAssumption>(16) ?? [];
  const scanLists = await Promise.allSettled(assumptions.map((a) => asicApi.listImpactScans(a.id)));
  const scans: Record<string, AsicImpactScan[]> = {};
  assumptions.forEach((a, i) => {
    if (scanLists[i].status === "fulfilled") scans[a.id] = (scanLists[i] as PromiseFulfilledResult<AsicImpactScan[]>).value;
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
    tradeStudies: pick<AsicTradeStudy>(10) ?? [],
    toolRuns: pick<AsicToolRun>(11) ?? [],
    flowAnalysis,
    waferMaps: pick<AsicWaferMap>(13) ?? [],
    partners: pick<AsicPartner>(14) ?? [],
    travelers: pick<AsicLotTraveler>(15) ?? [],
    assumptions,
    scans,
    deviations: pick<AsicDeviation>(17) ?? [],
    copilot: pick<AsicCopilotInteraction>(18) ?? [],
  };
  const hasData =
    live.chains.length + live.studies.length + live.runs.length + live.plans.length + live.safety.length +
    live.faCases.length + live.ecos.length + (live.gate ? 1 : 0);
  // a rejection counts as an outage unless it's an authorization miss (403) —
  // api.ts throws "${status} ${path}: …" so the status is always in the message
  const anyFail = settled.some(
    (s) => s.status === "rejected" && !/(^|\s)403\s/.test(String((s as PromiseRejectedResult).reason)),
  );
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

// ══ R2 (EPIC B·C·D·H + P1-08) — trade study · EDA tool runs · test program
// ══ twin analysis · supply chain · 3-language evidence report ═══════════════

const money = (v: number | null | undefined, cur = "KRW") =>
  v == null ? null : `${v.toLocaleString()} ${cur}`;

function RestrictedNote() {
  const { t } = useTranslation();
  return <div style={{ fontSize: 12, color: "#64748b" }}>{t("asic.r2.restricted")}</div>;
}

// ── s3 · EPIC B: cost/schedule trade study (CAN_COST — money behind role) ──
export function TradeStudyPanel({ live, liveState }: { live: Live; liveState: LiveState }) {
  const { t } = useTranslation();
  const { i18n } = useTranslation();
  const tr = makeSeedTr(i18n.resolvedLanguage);
  return (
    <SectionCard title={t("asic.r2.trade.title")} right={<LiveChip state={liveState} />}>
      {live.tradeStudies.length === 0 ? (
        <RestrictedNote />
      ) : (
        <div style={{ display: "grid", gap: 8 }}>
          {live.tradeStudies.map((s) => {
            const byOption = new Map((s.result?.per_option ?? []).map((p) => [p.option_id, p]));
            const winner = s.decision ? byOption.get(s.decision.option_id) : undefined;
            return (
              <div key={s.id} style={{ border: "1px solid #1e293b", borderRadius: 8, padding: 10, background: "#0f172a" }}>
                <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
                  <b style={{ fontFamily: "monospace", color: "#7dd3fc", fontSize: 12 }}>{s.business_id}</b>
                  <span style={{ fontSize: 12, flex: 1 }}>{tr(s.title)}</span>
                  <Chip color={s.status === "decided" ? "#34d399" : "#fbbf24"}>{s.status}</Chip>
                </div>
                {s.result && (
                  <div style={{ overflowX: "auto", marginTop: 8 }}>
                    <table style={{ width: "100%", borderCollapse: "collapse" }}>
                      <thead>
                        <tr>
                          <th style={th}>{t("asic.r2.trade.option")}</th>
                          <th style={th}>{t("asic.r2.trade.nre")}</th>
                          <th style={th}>{t("asic.r2.trade.unit")}</th>
                          <th style={th}>{t("asic.r2.trade.weeks")}</th>
                          <th style={th}>{t("asic.r2.trade.score")}</th>
                        </tr>
                      </thead>
                      <tbody>
                        {s.result.per_option.map((p) => (
                          <tr key={p.option_id}>
                            <td style={{ ...td, fontFamily: "monospace", color: "#7dd3fc" }}>
                              {p.business_id}
                              <span style={{ display: "block", fontSize: 9, color: "#64748b" }}>{tr(p.foundry)} · {p.node} · {p.package}</span>
                            </td>
                            <td style={td}>
                              {p.nre_total == null
                                ? <Chip color="#fbbf24" title={tr(s.result?.tbd_note)}>{t("asic.r2.tbd")}: {p.nre_tbd_components.join(", ")}</Chip>
                                : money(p.nre_total)}
                            </td>
                            <td style={td}>
                              {p.unit_cost_total == null
                                ? <Chip color="#fbbf24">{t("asic.r2.tbd")}: {p.unit_tbd_components.join(", ")}</Chip>
                                : money(p.unit_cost_total)}
                            </td>
                            <td style={{ ...td, fontFamily: "monospace" }}>{p.schedule_weeks_total ?? "—"}</td>
                            <td style={td}>
                              {p.score.complete
                                ? <b style={{ color: "#34d399" }}>{p.score.score}</b>
                                : <Chip color="#94a3b8" title={p.score.tbd_axes.join(", ")}>{t("asic.r2.trade.partial")}</Chip>}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
                {s.decision && (
                  <div style={{ fontSize: 11, color: "#34d399", marginTop: 8 }}>
                    ✓ {t("asic.r2.trade.decided")}: <b style={{ fontFamily: "monospace" }}>{winner?.business_id ?? s.decision.option_id}</b>
                    {" · "}{tr(s.decision.rationale)}
                    {(s.decision.residual_risks ?? []).length > 0 && (
                      <div style={{ color: "#fbbf24" }}>⚠ {t("asic.r2.trade.risks")}: {(s.decision.residual_risks ?? []).map(tr).join(" / ")}</div>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </SectionCard>
  );
}

// ── s4 · EPIC C: EDA tool runs — lineage + runner class provenance ─────────
export function ToolRunsPanel({ live, liveState }: { live: Live; liveState: LiveState }) {
  const { t } = useTranslation();
  if (live.toolRuns.length === 0) {
    return (
      <SectionCard title={t("asic.r2.tool.title")} right={<LiveChip state={liveState} />}>
        <div style={{ fontSize: 12, color: "#64748b" }}>— {t("asic.r2.none")}</div>
      </SectionCard>
    );
  }
  return (
    <SectionCard title={t("asic.r2.tool.title")} right={<LiveChip state={liveState} />}>
      <div style={{ overflowX: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr>
              <th style={th}>run</th>
              <th style={th}>{t("asic.r2.tool.tool")}</th>
              <th style={th}>rev</th>
              <th style={th}>{t("asic.r2.tool.runner")}</th>
              <th style={th}>input·output hash</th>
              <th style={th}>{t("asic.r2.tool.lineage")}</th>
              <th style={th}>exit</th>
            </tr>
          </thead>
          <tbody>
            {live.toolRuns.map((r) => (
              <tr key={r.id}>
                <td style={{ ...td, fontFamily: "monospace", color: "#7dd3fc" }}>{r.business_id}</td>
                <td style={{ ...td, fontFamily: "monospace" }}>{r.tool}<span style={{ display: "block", fontSize: 9, color: "#64748b" }}>{r.tool_version}</span></td>
                <td style={{ ...td, fontFamily: "monospace" }}>r{r.design_revision}</td>
                <td style={td}>
                  <Chip color={r.runner_class === "real_adapter" ? "#34d399" : "#fbbf24"}>{r.runner_class}</Chip>
                </td>
                <td style={{ ...td, fontFamily: "monospace", fontSize: 9, color: "#94a3b8" }}>
                  {r.input_hash.slice(0, 10)}… → {r.output_hash ? `${r.output_hash.slice(0, 10)}…` : "—"}
                </td>
                <td style={{ ...td, fontFamily: "monospace", color: "#a78bfa" }}>{r.lineage_id.slice(0, 8)}…</td>
                <td style={td}>
                  <Chip color={r.exit_code === 0 ? "#34d399" : "#f87171"}>{r.exit_code}</Chip>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </SectionCard>
  );
}

// ── s6 · EPIC D: test program twin analysis — time/cost/coverage/dup/gap ──
export function TestFlowAnalysisPanel({ live, liveState }: { live: Live; liveState: LiveState }) {
  const { t } = useTranslation();
  const { i18n } = useTranslation();
  const tr = makeSeedTr(i18n.resolvedLanguage);
  const a = live.flowAnalysis;
  if (!a) {
    return (
      <SectionCard title={t("asic.r2.flow.title")} right={<LiveChip state={liveState} />}>
        <div style={{ fontSize: 12, color: "#64748b" }}>— {t("asic.r2.none")}</div>
      </SectionCard>
    );
  }
  const targets = Object.entries(a.per_target);
  return (
    <SectionCard title={t("asic.r2.flow.title")} right={<Chip color="#38bdf8">{a.tool_version}</Chip>}>
      <div style={{ overflowX: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr>
              <th style={th}>{t("asic.r2.flow.target")}</th>
              <th style={th}>{t("asic.r2.flow.silicon")}</th>
              <th style={th}>{t("asic.r2.flow.items")}</th>
              <th style={th}>{t("asic.r2.flow.wall")}</th>
              <th style={th}>{t("asic.r2.flow.cost")}</th>
              <th style={th}>{t("asic.r2.flow.coverage")}</th>
              <th style={th}>{t("asic.r2.flow.compat")}</th>
            </tr>
          </thead>
          <tbody>
            {targets.map(([target, p]) => (
              <tr key={p.flow_id}>
                <td style={{ ...td, fontFamily: "monospace", color: "#7dd3fc" }}>
                  {target} <span style={{ color: "#64748b" }}>r{p.program_revision}</span>
                </td>
                <td style={{ ...td, fontFamily: "monospace" }}>{p.silicon_revision}</td>
                <td style={{ ...td, fontFamily: "monospace" }}>{p.totals.item_count}</td>
                <td style={{ ...td, fontFamily: "monospace" }}>{round2(p.totals.wall_time_s_per_die)}s</td>
                <td style={td}>
                  {p.totals.cost_per_die == null
                    ? <Chip color="#fbbf24" title={tr(a.tbd_note)}>{t("asic.r2.tbd")}</Chip>
                    : money(p.totals.cost_per_die)}
                </td>
                <td style={td}>
                  {p.coverage.aggregate_avg_pct}%{(p.coverage.uncovered_classes.length > 0) && (
                    <span style={{ display: "block", fontSize: 9, color: "#fbbf24" }}>— {p.coverage.uncovered_classes.join(", ")}</span>
                  )}
                </td>
                <td style={td}>
                  <Chip color={p.compatibility.compatible ? "#34d399" : "#f87171"}>
                    {p.compatibility.compatible ? "✓" : `✕ ${p.compatibility.mismatches.join(", ")}`}
                  </Chip>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {a.cross_target && (
        <div style={{ marginTop: 10, fontSize: 11, color: "#94a3b8" }}>
          <b>{t("asic.r2.flow.cross")}</b>
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginTop: 6 }}>
            {a.cross_target.duplicates.map((d) => (
              <Chip key={d.name} color={d.drop_candidate ? "#fbbf24" : "#64748b"} title={tr(d.reason)}>
                {d.drop_candidate ? `⚠ ${tr(d.name)}` : tr(d.name)}
              </Chip>
            ))}
            {a.cross_target.coverage_gaps.map((g) => (
              <Chip key={g.defect_class} color="#f87171" title={tr(g.reason)}>
                {t("asic.r2.flow.gap")}: {g.defect_class}
              </Chip>
            ))}
            {a.cross_target.duplicates.length + a.cross_target.coverage_gaps.length === 0 && (
              <span style={{ color: "#34d399" }}>✓ {t("asic.r2.flow.clean")}</span>
            )}
          </div>
        </div>
      )}
    </SectionCard>
  );
}

// ── s9 · EPIC H: partners · lot travelers · wafer maps (portal data) ───────
export function SupplyChainPanel({ live, liveState }: { live: Live; liveState: LiveState }) {
  const { t } = useTranslation();
  const partnerName = (id: string | null) =>
    id ? (live.partners.find((p) => p.id === id)?.business_id ?? id.slice(0, 8)) : "—";
  return (
    <SectionCard title={t("asic.r2.chain.title")} right={<LiveChip state={liveState} />}>
      {live.partners.length === 0 && live.travelers.length === 0 && live.waferMaps.length === 0 ? (
        <div style={{ fontSize: 12, color: "#64748b" }}>— {t("asic.r2.none")}</div>
      ) : (
        <div style={{ display: "grid", gap: 10 }}>
          {live.partners.length > 0 && (
            <div>
              <div style={{ fontSize: 10, color: "#475569", marginBottom: 4 }}>{t("asic.r2.chain.partners")}</div>
              <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                {live.partners.map((p) => (
                  <Chip key={p.id} color={p.status === "approved" ? "#34d399" : p.status === "suspended" ? "#f87171" : "#fbbf24"}>
                    {p.business_id} · {p.kind} · {p.status}
                  </Chip>
                ))}
              </div>
            </div>
          )}
          {live.travelers.length > 0 && (
            <div style={{ overflowX: "auto" }}>
              <div style={{ fontSize: 10, color: "#475569", marginBottom: 4 }}>{t("asic.r2.chain.lots")}</div>
              <table style={{ width: "100%", borderCollapse: "collapse" }}>
                <thead>
                  <tr>
                    <th style={th}>lot</th>
                    <th style={th}>{t("asic.r2.chain.revs")}</th>
                    <th style={th}>{t("asic.r2.chain.route")}</th>
                    <th style={th}>{t("asic.r2.chain.parent")}</th>
                  </tr>
                </thead>
                <tbody>
                  {live.travelers.map((lt) => (
                    <tr key={lt.id}>
                      <td style={{ ...td, fontFamily: "monospace", color: "#7dd3fc" }}>
                        {lt.lot_ref}
                        <span style={{ display: "block", fontSize: 9, color: "#64748b" }}>{lt.status}</span>
                      </td>
                      <td style={{ ...td, fontFamily: "monospace", fontSize: 10 }}>
                        {lt.silicon_revision} / {lt.mask_rev} / {lt.package_rev}
                      </td>
                      <td style={td}>
                        {lt.steps.map((s, i) => (
                          <span key={i} style={{ fontFamily: "monospace", fontSize: 10 }}>
                            {i > 0 && " → "}{s.partner_business_id}:{s.step}
                          </span>
                        ))}
                        <span style={{ display: "block", fontSize: 9, color: "#64748b" }}>
                          {t("asic.r2.chain.current")}: {partnerName(lt.current_partner_id)}
                        </span>
                      </td>
                      <td style={{ ...td, fontFamily: "monospace", fontSize: 10 }}>{(lt.parent_lot_refs ?? []).join(", ") || "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {live.waferMaps.length > 0 && (
            <div style={{ overflowX: "auto" }}>
              <div style={{ fontSize: 10, color: "#475569", marginBottom: 4 }}>{t("asic.r2.chain.maps")}</div>
              <table style={{ width: "100%", borderCollapse: "collapse" }}>
                <thead>
                  <tr>
                    <th style={th}>wafer</th>
                    <th style={th}>{t("asic.r2.chain.yield")}</th>
                    <th style={th}>{t("asic.r2.chain.retest")}</th>
                    <th style={th}>{t("asic.r2.chain.overkill")}</th>
                    <th style={th}>class</th>
                  </tr>
                </thead>
                <tbody>
                  {live.waferMaps.map((m) => (
                    <tr key={m.id}>
                      <td style={{ ...td, fontFamily: "monospace", color: "#7dd3fc" }}>
                        {m.wafer_ref ?? m.business_id}
                        {m.lot_ref && <span style={{ display: "block", fontSize: 9, color: "#64748b" }}>lot {m.lot_ref}</span>}
                      </td>
                      <td style={{ ...td, fontFamily: "monospace" }}>{m.analysis ? `${m.analysis.yield_pct}%` : "—"}</td>
                      <td style={{ ...td, fontFamily: "monospace" }}>{m.analysis ? `${m.analysis.retest_rate_pct}%` : "—"}</td>
                      <td style={td}>
                        {m.analysis?.confusion
                          ? <Chip color={m.analysis.confusion.overkill_count > 0 ? "#fbbf24" : "#34d399"}>
                              {m.analysis.confusion.overkill_count} / {m.analysis.confusion.escaped_underkill}
                            </Chip>
                          : "—"}
                      </td>
                      <td style={td}><Chip color={m.source_class === "SYNTHETIC" ? "#a78bfa" : "#34d399"}>{m.source_class}</Chip></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </SectionCard>
  );
}

// ── s8 · P1-08: 3-language evidence report (follows the UI language) ───────
export function EvidenceReportPanel({ tplId }: { tplId: string }) {
  const { t, i18n } = useTranslation();
  const lang = (["ko", "en", "ja"].includes(i18n.resolvedLanguage ?? "") ? i18n.resolvedLanguage : "ko") as
    | "ko" | "en" | "ja";
  const [report, setReport] = useState<AsicEvidenceReport | null>(null);
  const [state, setState] = useState<"loading" | "ready" | "error">("loading");

  // the report is generated server-side per language and the UI language is
  // the single source — a stale ko report must never linger under a ja UI
  useEffect(() => {
    let on = true;
    setState("loading");
    asicApi.evidenceReport(tplId, lang).then(
      (r) => {
        if (on) {
          setReport(r);
          setState("ready");
        }
      },
      () => {
        if (on) setState("error");
      },
    );
    return () => {
      on = false;
    };
  }, [tplId, lang]);

  const download = () => {
    if (!report) return;
    const md = [
      `# ${report.title} — ${report.template_id}`,
      `${t("asic.r2.report.generated")}: ${report.generated_at} · v${report.report_version}`,
      "",
      ...report.notes.map((n) => `> ${n}`),
      "",
      ...report.sections.map((s) => [
        `## ${s.title}`,
        ...s.rows.map((r) => `- **${r.label}**: ${String(r.value)}`),
        "",
      ].join("\n")),
    ].join("\n");
    const url = URL.createObjectURL(new Blob([md], { type: "text/markdown" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = `evidence-report-${report.template_id}-${report.lang}.md`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <SectionCard title={t("asic.r2.report.title")} right={<Chip color="#38bdf8">{lang}</Chip>}>
      {state === "loading" && <div style={{ fontSize: 12, color: "#64748b" }}>…</div>}
      {state === "error" && <div style={{ fontSize: 12, color: "#f87171" }}>{t("asic.r2.report.error")}</div>}
      {state === "ready" && report && (
        <div>
          <div style={{ fontSize: 10, color: "#475569", marginBottom: 8, fontFamily: "monospace" }}>
            {report.title} · v{report.report_version} · {report.generated_at}
          </div>
          {report.sections.map((s) => (
            <div key={s.key} style={{ marginBottom: 8 }}>
              <div style={{ fontSize: 11, color: "#7dd3fc", fontWeight: 600 }}>{s.title}</div>
              {s.rows.map((r, i) => (
                <div key={i} style={{ fontSize: 11, color: "#94a3b8", paddingLeft: 10 }}>
                  · <span style={{ color: "#cbd5e1" }}>{r.label}</span>: {String(r.value)}
                </div>
              ))}
            </div>
          ))}
          <button style={{ border: "1px solid #38bdf8", background: "#38bdf822", color: "#7dd3fc", borderRadius: 6, padding: "4px 10px", fontSize: 11, cursor: "pointer" }} onClick={download}>
            ↓ {t("asic.r2.report.download")} ({lang})
          </button>
        </div>
      )}
    </SectionCard>
  );
}

// ══ R3 · EPIC I: Concurrent Engineering 제어판 (가정·영향 탐색·편차) ═════════

const ACT_BTN: React.CSSProperties = {
  border: "1px solid #38bdf8",
  background: "#38bdf822",
  color: "#7dd3fc",
  borderRadius: 6,
  padding: "2px 8px",
  fontSize: 10,
  cursor: "pointer",
  whiteSpace: "nowrap",
};

const RISK_COLOR: Record<string, string> = { high: "#f87171", medium: "#fbbf24", low: "#94a3b8" };
const STATUS_COLOR: Record<string, string> = {
  open: "#fbbf24", resolved: "#34d399", invalidated: "#f87171", superseded: "#64748b",
  submitted: "#fbbf24", approved: "#34d399", rejected: "#f87171",
};
const CE_ROLES = new Set(["system_architect", "electrical_asic_engineer"]); // CAN_DESIGN
const DECIDE_ROLES = new Set(["system_architect", "reviewer_approver"]); // CAN_CE_DECIDE

function useRoles(): Set<string> {
  // 백엔드 security.py와 같은 소스(realm_access.roles) — keycloak-js 타입에는
  // 없는 필드라 한 번 캐스팅한다. 미로그인/토큰 전이면 빈 집합 (버튼만 숨김).
  const parsed = keycloak.tokenParsed as { realm_access?: { roles?: string[] } } | undefined;
  return new Set(parsed?.realm_access?.roles ?? []);
}

function myUsername(): string {
  const parsed = keycloak.tokenParsed as { preferred_username?: string } | undefined;
  return parsed?.preferred_username ?? "";
}

export function ConcurrentEngineeringPanel({
  live, liveState, onChanged,
}: { live: Live; liveState: LiveState; onChanged: () => void }) {
  const { t } = useTranslation();
  const { i18n } = useTranslation();
  const tr = makeSeedTr(i18n.resolvedLanguage);
  const roles = useRoles();
  const me = myUsername();
  const canDesign = [...roles].some((r) => CE_ROLES.has(r));
  const canDecide = [...roles].some((r) => DECIDE_ROLES.has(r));
  const [err, setErr] = useState<string | null>(null);
  const [events, setEvents] = useState<Record<string, AsicAssumptionEvent[] | null>>({});
  const [openScan, setOpenScan] = useState<Record<string, boolean>>({});
  const [resolveRef, setResolveRef] = useState<Record<string, string>>({});

  const act = async (label: string, fn: () => Promise<unknown>) => {
    setErr(null);
    try {
      await fn();
      onChanged();
    } catch (e) {
      setErr(`${label}: ${String(e).slice(0, 160)}`);
    }
  };
  const idem = () => crypto.randomUUID();

  const openScansOf = (a: AsicAssumption) => (live.scans[a.id] ?? []).filter((s) => s.status === "open");

  return (
    <SectionCard title={t("asic.r3.ce.title")} right={<LiveChip state={liveState} />}>
      <div style={{ fontSize: 11, color: "#64748b", marginBottom: 8 }}>{t("asic.r3.ce.hint")}</div>
      {err && <div style={{ fontSize: 11, color: "#f87171", marginBottom: 8 }}>⚠ {err}</div>}
      <div style={{ display: "grid", gap: 8 }}>
        {live.assumptions.length === 0 && <div style={{ fontSize: 12, color: "#64748b" }}>— {t("asic.r2.none")}</div>}
        {live.assumptions.map((a) => {
          const scans = live.scans[a.id] ?? [];
          const openScans = openScansOf(a);
          const ev = events[a.id];
          return (
            <div key={a.id} style={{ border: "1px solid #1e293b", borderRadius: 8, padding: 10, background: "#0f172a" }}>
              <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
                <b style={{ fontFamily: "monospace", color: "#7dd3fc", fontSize: 12 }}>{a.business_id}</b>
                <span style={{ fontSize: 12, flex: 1 }}>{tr(a.title)}</span>
                <Chip color={RISK_COLOR[a.risk] ?? "#94a3b8"}>{a.risk}</Chip>
                <Chip color={STATUS_COLOR[a.status] ?? "#94a3b8"}>{a.status}</Chip>
              </div>
              <div style={{ fontSize: 11, color: "#94a3b8", marginTop: 4 }}>
                {tr(a.detail)}
              </div>
              <div style={{ fontSize: 10, color: "#64748b", marginTop: 4, display: "flex", gap: 12, flexWrap: "wrap" }}>
                <span>{t("asic.r3.ce.confidence")}: {(a.confidence * 100).toFixed(0)}% ({t("asic.r3.ce.heuristic")})</span>
                <span>{t("asic.r3.ce.owner")}: {a.owner}</span>
                {a.due_at && <span>{t("asic.r3.ce.due")}: {a.due_at.slice(0, 10)}</span>}
                {a.resolved_evidence != null && (
                  <span style={{ color: "#34d399" }}>
                    ✓ {String((a.resolved_evidence as Record<string, unknown>).ref ?? "")}
                  </span>
                )}
              </div>
              {a.downstream.length > 0 && (
                <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginTop: 6 }}>
                  {a.downstream.map((d, i) => (
                    <Chip key={i} color="#38bdf8" title={tr(d.label)}>{d.kind} · {d.ref}</Chip>
                  ))}
                </div>
              )}
              {/* 영향 탐색 — findings는 pending→done→clear 순서로만 종결된다 */}
              <div style={{ marginTop: 8 }}>
                <button style={{ ...ACT_BTN, border: "1px solid #475569", background: "transparent", color: "#94a3b8" }}
                  onClick={() => setOpenScan((m) => ({ ...m, [a.id]: !m[a.id] }))}>
                  {t("asic.r3.ce.scans")} ({scans.length}){openScans.length > 0 ? ` · ${t("asic.r3.ce.openCount")} ${openScans.length}` : ""}
                </button>
                {openScan[a.id] && (
                  <div style={{ display: "grid", gap: 6, marginTop: 6 }}>
                    {scans.map((s) => (
                      <div key={s.id} style={{ border: "1px solid #141c2e", borderRadius: 6, padding: 8 }}>
                        <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap", fontSize: 11 }}>
                          <b style={{ fontFamily: "monospace", color: "#a78bfa" }}>{s.business_id}</b>
                          <span style={{ color: "#64748b" }}>{t(`asic.r3.ce.trigger.${s.trigger}` as never)}</span>
                          <Chip color={s.status === "open" ? "#fbbf24" : "#34d399"}>{s.status}</Chip>
                          {s.status === "open" && canDesign && openScans.length === 1 && s.findings.every((f) => f.status === "done") && (
                            <button style={ACT_BTN} onClick={() => act("clear", () => asicApi.clearScan(s.id, idem()))}>
                              {t("asic.r3.ce.clear")}
                            </button>
                          )}
                        </div>
                        <table style={{ width: "100%", borderCollapse: "collapse", marginTop: 4 }}>
                          <tbody>
                            {s.findings.map((f, i) => (
                              <tr key={i}>
                                <td style={{ ...td, color: "#7dd3fc", fontFamily: "monospace", width: 70 }}>{f.kind}</td>
                                <td style={{ ...td, fontFamily: "monospace", color: "#94a3b8" }}>{f.ref}</td>
                                <td style={td}>{tr(f.reason)}</td>
                                <td style={td}>
                                  <Chip color={f.action === "rerun" ? "#fbbf24" : "#38bdf8"}>{t(`asic.r3.ce.action.${f.action}` as never)}</Chip>
                                </td>
                                <td style={td}>
                                  {f.status === "done"
                                    ? <Chip color="#34d399">✓ {t("asic.r3.ce.done")}</Chip>
                                    : canDesign
                                      ? <button style={ACT_BTN} onClick={() => act("done", () => asicApi.findingDone(s.id, f.ref, t("asic.r3.ce.doneNote"), idem()))}>
                                          {t("asic.r3.ce.markDone")}
                                        </button>
                                      : <Chip color="#64748b">{t("asic.r3.ce.pending")}</Chip>}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    ))}
                  </div>
                )}
              </div>
              {/* 해결 — 열린 탐색이 남아 있으면 서버가 412로 거부한다 */}
              {a.status === "open" && (
                <div style={{ display: "flex", gap: 6, marginTop: 8, alignItems: "center", flexWrap: "wrap" }}>
                  <input
                    value={resolveRef[a.id] ?? ""}
                    onChange={(e) => setResolveRef((m) => ({ ...m, [a.id]: e.target.value }))}
                    placeholder={t("asic.r3.ce.resolvePlaceholder")}
                    style={{ background: "#020617", border: "1px solid #1e293b", borderRadius: 6, color: "#cbd5e1", fontSize: 11, padding: "3px 8px", minWidth: 220 }}
                  />
                  <button style={ACT_BTN} disabled={!canDesign}
                    onClick={() => act("resolve", () => asicApi.resolveAssumption(
                      a.id, "resolved",
                      { ref: resolveRef[a.id] || `MANUAL-${new Date().toISOString().slice(0, 10)}`, label: t("asic.r3.ce.resolveEvidence") },
                      t("asic.r3.ce.resolveNote"), idem(),
                    ))}>
                    {t("asic.r3.ce.resolve")}
                  </button>
                </div>
              )}
              {/* 변경 이력 — append-only ledger (created/field_changed/resolved…) */}
              <div style={{ marginTop: 8 }}>
                <button style={{ ...ACT_BTN, border: "1px solid #475569", background: "transparent", color: "#94a3b8" }}
                  onClick={() => {
                    if (ev) { setEvents((m) => ({ ...m, [a.id]: null })); return; }
                    asicApi.listAssumptionEvents(a.id).then((rows) => setEvents((m) => ({ ...m, [a.id]: rows })));
                  }}>
                  {t("asic.r3.ce.ledger")}
                </button>
                {ev && (
                  <div style={{ marginTop: 4, fontSize: 10, color: "#94a3b8" }}>
                    {ev.map((e) => (
                      <div key={e.id}>
                        · <span style={{ fontFamily: "monospace", color: "#a78bfa" }}>{e.kind}</span>{" "}
                        {e.created_at.slice(0, 16).replace("T", " ")} {e.created_by} — {Object.keys(e.payload).join(", ")}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* 편차 — 생략 활동은 숨겨지지 않고 승인된 편차로 조회된다 (수용기준 3) */}
      <div style={{ fontSize: 12, color: "#7dd3fc", fontWeight: 600, margin: "14px 0 6px" }}>{t("asic.r3.ce.deviations")}</div>
      <div style={{ display: "grid", gap: 8 }}>
        {live.deviations.length === 0 && <div style={{ fontSize: 12, color: "#64748b" }}>— {t("asic.r2.none")}</div>}
        {live.deviations.map((d) => (
          <div key={d.id} style={{ border: "1px solid #1e293b", borderRadius: 8, padding: 10, background: "#0f172a" }}>
            <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
              <b style={{ fontFamily: "monospace", color: "#7dd3fc", fontSize: 12 }}>{d.business_id}</b>
              <Chip color={STATUS_COLOR[d.status] ?? "#94a3b8"}>{d.status}</Chip>
              <span style={{ fontSize: 10, color: "#64748b" }}>
                {d.requested_by}{d.decided_by ? ` → ${d.decided_by}` : ""}
                {d.decided_at ? ` · ${d.decided_at.slice(0, 16).replace("T", " ")}` : ""}
              </span>
              {d.status === "submitted" && canDecide && d.requested_by !== me && (
                <span style={{ display: "flex", gap: 6, marginLeft: "auto" }}>
                  <button style={ACT_BTN} onClick={() => act("approve", () => asicApi.decideDeviation(d.id, "approved", t("asic.r3.ce.decideNote"), idem()))}>
                    ✓ {t("asic.r3.ce.approve")}
                  </button>
                  <button style={{ ...ACT_BTN, border: "1px solid #f87171", background: "#f8717122", color: "#f87171" }}
                    onClick={() => act("reject", () => asicApi.decideDeviation(d.id, "rejected", t("asic.r3.ce.decideRejectNote"), idem()))}>
                    ✕ {t("asic.r3.ce.reject")}
                  </button>
                </span>
              )}
            </div>
            <div style={{ fontSize: 11, color: "#94a3b8", marginTop: 4 }}>
              {t("asic.r3.ce.skipped")}: {d.skipped.map((s) => `${s.stage} · ${s.ref} — ${tr(s.label)}`).join(" / ")}
            </div>
            <div style={{ fontSize: 11, color: "#94a3b8" }}>{tr(d.rationale)}</div>
            <div style={{ fontSize: 11, color: "#fbbf24" }}>⚠ {t("asic.r3.ce.residual")}: {tr(d.residual_risk)}</div>
            {d.note && <div style={{ fontSize: 10, color: "#64748b" }}>{tr(d.note)}</div>}
          </div>
        ))}
      </div>
    </SectionCard>
  );
}

// ══ R3 · EPIC J: 근거 중심 AI Copilot (유스케이스 7종 · diff 수락) ════════════

const COPILOT_ROLES = new Set(["system_architect", "electrical_asic_engineer", "quality_engineer", "test_emc_engineer"]);
const USECASES = ["req_draft", "similar_fa", "corner_sensitivity", "wafer_anomaly", "test_efficiency", "gate_gap", "fa_hypothesis"] as const;
type Usecase = (typeof USECASES)[number];
const TEXT_USECASES: Set<Usecase> = new Set(["req_draft", "similar_fa"]);

const ABSTAIN_COLOR = "#fbbf24";

export function CopilotPanel({
  live, liveState, tplId, onChanged,
}: { live: Live; liveState: LiveState; tplId: string; onChanged: () => void }) {
  const { t } = useTranslation();
  const { i18n } = useTranslation();
  const tr = makeSeedTr(i18n.resolvedLanguage);
  const roles = useRoles();
  const canCopilot = [...roles].some((r) => COPILOT_ROLES.has(r));
  const [usecase, setUsecase] = useState<Usecase>("gate_gap");
  const [text, setText] = useState("");
  const [faCaseId, setFaCaseId] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [diffs, setDiffs] = useState<Record<string, AsicCopilotDiff | undefined>>({});
  const openCases = live.faCases.filter(
    (c) => !c.root_cause_confirmed && !["rca_approved", "eco_open", "verified", "closed"].includes(c.status),
  );

  const run = async () => {
    setErr(null);
    setBusy(true);
    try {
      await asicApi.runCopilot(
        tplId,
        usecase,
        TEXT_USECASES.has(usecase) && text.trim() ? text.trim() : undefined,
        usecase === "fa_hypothesis" ? faCaseId || undefined : undefined,
      );
      onChanged();
    } catch (e) {
      setErr(String(e).slice(0, 200));
    } finally {
      setBusy(false);
    }
  };

  const loadDiff = (iid: string, pid: string) => {
    const k = `${iid}:${pid}`;
    if (diffs[k]) { setDiffs((m) => ({ ...m, [k]: undefined })); return; }
    asicApi.copilotDiff(iid, pid).then((d) => setDiffs((m) => ({ ...m, [k]: d })));
  };

  const accept = async (iid: string, pid: string) => {
    setErr(null);
    const k = `${iid}:${pid}`;
    const d = diffs[k];
    if (!d) return;
    try {
      // 수용기준 2: 브라우저에서 diff 본문의 sha256을 계산해 대조 — 서버가
      // 재계산한 해시와 어긋나면 422 (diff를 확인하지 않은 수락은 없다)
      await asicApi.acceptCopilotProposal(iid, pid, sha256Hex(d.diff));
      onChanged();
    } catch (e) {
      setErr(String(e).slice(0, 200));
    }
  };

  const recent = live.copilot.slice(0, 5);

  return (
    <SectionCard title={t("asic.r3.copilot.title")} right={<LiveChip state={liveState} />}>
      <div style={{ fontSize: 11, color: "#64748b", marginBottom: 8 }}>{t("asic.r3.copilot.hint")}</div>
      {err && <div style={{ fontSize: 11, color: "#f87171", marginBottom: 8 }}>⚠ {err}</div>}
      {/* 실행 바 — 유스케이스 7종 (근거 없는 제안은 엔진이 만들지 않는다) */}
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 8 }}>
        {USECASES.map((u) => (
          <button key={u}
            onClick={() => setUsecase(u)}
            style={{
              ...ACT_BTN,
              ...(usecase === u ? {} : { border: "1px solid #475569", background: "transparent", color: "#94a3b8" }),
            }}>
            {t(`asic.r3.copilot.uc.${u}` as never)}
          </button>
        ))}
      </div>
      {TEXT_USECASES.has(usecase) && (
        <input
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder={t("asic.r3.copilot.textPlaceholder")}
          style={{ width: "100%", background: "#020617", border: "1px solid #1e293b", borderRadius: 6, color: "#cbd5e1", fontSize: 11, padding: "5px 8px", marginBottom: 8 }}
        />
      )}
      {usecase === "fa_hypothesis" && (
        <select value={faCaseId} onChange={(e) => setFaCaseId(e.target.value)}
          style={{ background: "#020617", border: "1px solid #1e293b", borderRadius: 6, color: "#cbd5e1", fontSize: 11, padding: "4px 8px", marginBottom: 8, maxWidth: "100%" }}>
          <option value="">{t("asic.r3.copilot.selectCase")}</option>
          {openCases.map((c) => (
            <option key={c.id} value={c.id}>{c.business_id} — {tr(c.symptom).slice(0, 40)}</option>
          ))}
        </select>
      )}
      <div style={{ marginBottom: 12 }}>
        <button style={ACT_BTN} disabled={busy || !canCopilot || (usecase === "fa_hypothesis" && !faCaseId)}
          onClick={run}>
          {busy ? "…" : `▶ ${t("asic.r3.copilot.run")}`}
        </button>
        {!canCopilot && <span style={{ fontSize: 10, color: "#fbbf24", marginLeft: 8 }}>{t("asic.r3.copilot.roleNeeded")}</span>}
      </div>
      {/* 최근 상호작록 — 감사 재현 메타데이터(input_hash·engine_version) 표시 */}
      {recent.length === 0 && <div style={{ fontSize: 12, color: "#64748b" }}>— {t("asic.r2.none")}</div>}
      <div style={{ display: "grid", gap: 8 }}>
        {recent.map((it) => {
          const r = it.result;
          const acceptedPids = new Set((it.accepted_proposals ?? []).map((p) => p.pid));
          return (
            <div key={it.id} style={{ border: "1px solid #1e293b", borderRadius: 8, padding: 10, background: "#0f172a" }}>
              <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
                <Chip color="#38bdf8">{t(`asic.r3.copilot.uc.${it.usecase}` as never)}</Chip>
                <span style={{ fontSize: 10, color: "#64748b", fontFamily: "monospace" }}>
                  {it.engine_version} · {it.input_hash.slice(0, 10)}… · {it.created_by}
                </span>
                <span style={{ fontSize: 10, color: "#64748b" }}>
                  {t("asic.r3.copilot.confidence")}: {(r.confidence * 100).toFixed(0)}% ({t("asic.r3.ce.heuristic")})
                </span>
                {r.abstain && <Chip color={ABSTAIN_COLOR}>{t("asic.r3.copilot.abstain")}: {t(`asic.r3.copilot.abstainReason.${r.abstain_reason}` as never)}</Chip>}
              </div>
              <div style={{ fontSize: 12, color: "#e2e8f0", marginTop: 6 }}>{tr(r.summary)}</div>
              {r.abstain && (
                <div style={{ fontSize: 11, color: ABSTAIN_COLOR, marginTop: 4, border: `1px solid ${ABSTAIN_COLOR}44`, borderRadius: 6, padding: "4px 8px" }}>
                  ⚠ {t("asic.r3.copilot.abstainNote")}
                </div>
              )}
              {(r.facts ?? []).length > 0 && (
                <div style={{ marginTop: 6 }}>
                  <div style={{ fontSize: 10, color: "#64748b", fontWeight: 600 }}>{t("asic.r3.copilot.facts")}</div>
                  {r.facts.map((f, i) => (
                    <div key={i} style={{ fontSize: 11, color: "#94a3b8", paddingLeft: 10 }}>· {tr(f)}</div>
                  ))}
                </div>
              )}
              {(r.evidence ?? []).length > 0 && (
                <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginTop: 6 }}>
                  {r.evidence.map((e, i) => (
                    <Chip key={i} color="#34d399" title={`${e.kind}:${e.ref}`}>{e.kind} · {e.ref}</Chip>
                  ))}
                </div>
              )}
              {(r.proposals ?? []).length > 0 && (
                <div style={{ marginTop: 8, display: "grid", gap: 6 }}>
                  <div style={{ fontSize: 10, color: "#64748b", fontWeight: 600 }}>{t("asic.r3.copilot.proposals")}</div>
                  {r.proposals.map((p) => {
                    const k = `${it.id}:${p.pid}`;
                    const d = diffs[k];
                    const accepted = acceptedPids.has(p.pid);
                    return (
                      <div key={p.pid} style={{ border: "1px solid #141c2e", borderRadius: 6, padding: 8 }}>
                        <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
                          <b style={{ fontFamily: "monospace", color: "#a78bfa", fontSize: 10 }}>{p.pid}</b>
                          <span style={{ fontSize: 11, color: "#cbd5e1", flex: 1 }}>{tr(p.text)}</span>
                          {accepted
                            ? <Chip color="#34d399">✓ {t("asic.r3.copilot.accepted")}</Chip>
                            : (
                              <>
                                <button style={ACT_BTN} onClick={() => loadDiff(it.id, p.pid)}>{d ? "▲" : t("asic.r3.copilot.showDiff")}</button>
                                {d && (
                                  <button style={{ ...ACT_BTN, border: "1px solid #34d399", background: "#34d39922", color: "#34d399" }}
                                    onClick={() => accept(it.id, p.pid)}>
                                    ✓ {t("asic.r3.copilot.accept")}
                                  </button>
                                )}
                              </>
                            )}
                        </div>
                        <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginTop: 4 }}>
                          {p.evidence.map((e, i) => (
                            <Chip key={i} color="#34d399" title={`${e.kind}:${e.ref}`}>🔗 {e.kind} · {e.ref}{e.label ? ` — ${tr(e.label)}` : ""}</Chip>
                          ))}
                        </div>
                        {d && (
                          <pre style={{ margin: "6px 0 0", padding: 8, background: "#020617", borderRadius: 6, fontSize: 10, fontFamily: "monospace", color: "#94a3b8", overflowX: "auto" }}>
                            {d.diff}
                            {"\n"}sha256 = {d.sha256.slice(0, 16)}…
                          </pre>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </SectionCard>
  );
}
