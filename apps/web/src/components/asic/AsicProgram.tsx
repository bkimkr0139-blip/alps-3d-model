import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  DEFAULT_FLOORPLAN,
  MISSIONS,
  runLint,
  runPlaceRoute,
  runSimulation,
  runSynthesis,
  type LintResult,
  type PnrResult,
  type SimResult,
  type SynthResult,
} from "../eda/edaRunner";
import { Eda3DViewer } from "../eda/Eda3DViewer";
import { EdaWaveform } from "../eda/EdaWaveform";
import {
  ASIC_TEMPLATES,
  GRADE_TEMP,
  READINESS_LEVELS,
  STAGES,
  corrBase,
  corrStats,
  eduHash,
  makeEsSamples,
  makeEvidence,
  round2,
  type AsicTemplate,
  type Eco,
  type EvidenceItem,
  type Lot,
  type QualRow,
  type Requirement,
  type StageId,
} from "./asicModel";
import { Pareto, Scatter, SpcChart, TrendLine } from "./asicCharts";
import { buildPackageScene } from "./packageScene";
import { pickL, pickText, L } from "../../lib/lstr";
import { btn, card, Chip, ConfidenceBadge, GateDot, Kpi, SectionCard, td, th } from "./asicUi";
import {
  ChainBudgetPanel,
  ChainRevisionPanel,
  ConcurrentEngineeringPanel,
  CopilotPanel,
  CornerStudiesPanel,
  EvidenceReportPanel,
  EMPTY_LIVE,
  EquipmentRunsPanel,
  FaStudio,
  GateReportPanel,
  BackendQualPanel,
  SafetyTracePanel,
  SupplyChainPanel,
  TestFlowAnalysisPanel,
  TestProgramTwin,
  ToolRunsPanel,
  TradeStudyPanel,
  loadLive,
  type Live,
  type LiveState,
} from "./asicLive";

// Alps Alpine ASIC development 9-stage work center — standalone tab next to
// the EDA training module (docs/AgentIC_AlpsAlpine_ASIC_Turnkey_DigitalTwin_고도화_개발지시서_v1.0.md
// + v1.1 추가개발 지시서). Stage ②③④⑤⑥⑦⑧⑨ panels gained live golden-dataset
// views (asicLive.tsx) alongside the interactive fixtures; the stage-8 release
// gate report is computed SERVER-SIDE (asic_gate_policy.py) and rendered
// verbatim — the UI never hand-authors a blocker (§6 불변규칙 4). Everything
// stays explicitly synthetic: this twin can reach controlled_pilot, never
// production_candidate / released (§15).

type GateStatus = "pass" | "blocked";
type Gate = { status: GateStatus; blockers: string[] };

// Program state is per-template: switching template remounts the workbench.
function Workbench({ tpl }: { tpl: AsicTemplate }) {
  const { t, i18n } = useTranslation();
  const lang = i18n.resolvedLanguage;
  const [stage, setStage] = useState<StageId>("s1");

  // S1 — requirements (mutable copy: draft reqs get linked via the AI-suggest action)
  const [reqs, setReqs] = useState<Requirement[]>(tpl.requirements);
  const [verDone, setVerDone] = useState<Record<string, boolean>>(Object.fromEntries(tpl.verItems.map((v) => [v.id, v.done])));

  // S2 — selected process/package option; S3 — baseline signature
  const [optId, setOptId] = useState<string | null>(null);
  const [signed, setSigned] = useState(false);

  // S4 — design runs (reuse of the EDA-training mock runners)
  const mission = MISSIONS.find((m) => m.slug === tpl.missionSlug) ?? MISSIONS[0];
  const [lint, setLint] = useState<LintResult | null>(null);
  const [sim, setSim] = useState<SimResult | null>(null);
  const [synth, setSynth] = useState<SynthResult | null>(null);
  const [pnr, setPnr] = useState<PnrResult | null>(null);
  const [ranAt, setRanAt] = useState<string>("");

  // S5 — correlation + package twin
  const [corrDone, setCorrDone] = useState(false);

  // S6 — ECO lifecycle
  const [ecos, setEcos] = useState<Eco[]>(tpl.ecos);
  const [maskRev, setMaskRev] = useState("r3");
  const [testProgRev, setTestProgRev] = useState(2);

  // S7 — qualification rows (mutable: evidence upload / CAPA / waiver)
  const [qual, setQual] = useState<QualRow[]>(tpl.qual);

  // S8 — evidence approvals
  const [evidence, setEvidence] = useState<EvidenceItem[]>(makeEvidence(tpl, "r3", 2));

  // S9 — production lots (MRB disposition on the excursion lot)
  const [lots, setLots] = useState<Lot[]>(tpl.lots);

  const tempGrade = GRADE_TEMP[tpl.grade];

  // ── v1.1 golden-dataset views (best-effort backend loads — the fixture
  //    workspace below keeps working when the API is unreachable) ──
  const [live, setLive] = useState<Live>(EMPTY_LIVE);
  const [liveState, setLiveState] = useState<LiveState>("loading");
  // R3 패널의 쓰기(가정 해결·findings·편차 결정·copilot 수락) 후 라이브 재적재
  const [liveVer, setLiveVer] = useState(0);
  const reloadLive = () => setLiveVer((v) => v + 1);
  useEffect(() => {
    let on = true;
    setLiveState("loading");
    loadLive(tpl.id).then((r) => {
      if (on) {
        setLive(r.live);
        setLiveState(r.state);
      }
    });
    return () => {
      on = false;
    };
  }, [tpl.id, liveVer]);

  // ── Gate evaluation (§2 완료 게이트 / §10 rule style) ──
  const gates = useMemo(() => {
    const draftReqs = reqs.filter((r) => r.status === "draft");
    const unlinkedMust = reqs.filter((r) => r.priority === "must" && r.status !== "superseded" && !r.verId);
    const g1: Gate = {
      status: draftReqs.length === 0 && unlinkedMust.length === 0 ? "pass" : "blocked",
      blockers: [
        ...draftReqs.map((r) => `${r.id} draft`),
        ...unlinkedMust.map((r) => `${r.id} ${t("asic.gate.unlinked")}`),
      ],
    };
    const g2: Gate = { status: optId ? "pass" : "blocked", blockers: optId ? [] : [t("asic.gate.opt")] };
    const g3: Gate = { status: signed ? "pass" : "blocked", blockers: signed ? [] : [t("asic.gate.sign")] };
    const ok4 = lint?.status === "success" && sim?.status === "success" && synth?.status === "success";
    const g4: Gate = { status: ok4 ? "pass" : "blocked", blockers: ok4 ? [] : [t("asic.gate.design")] };
    const g5: Gate = { status: corrDone ? "pass" : "blocked", blockers: corrDone ? [] : [t("asic.gate.corr")] };
    const openEco = ecos.filter((e) => e.status !== "closed");
    const g6: Gate = { status: openEco.length === 0 ? "pass" : "blocked", blockers: openEco.map((e) => `${e.id} ${e.status}`) };
    const badQual = qual.filter((r) => r.status === "pending" || r.status === "fail");
    const g7: Gate = { status: badQual.length === 0 ? "pass" : "blocked", blockers: badQual.map((r) => `${r.group} ${r.status}`) };
    const unapproved = evidence.filter((e) => !e.approved);
    const g8: Gate = { status: unapproved.length === 0 ? "pass" : "blocked", blockers: unapproved.map((e) => `${e.id} ${t("asic.gate.unapproved")}`) };
    const held = lots.filter((l) => l.disposition === "held");
    const g9: Gate = { status: held.length === 0 ? "pass" : "blocked", blockers: held.map((l) => `${l.id} held`) };
    const map: Record<StageId, Gate> = { s1: g1, s2: g2, s3: g3, s4: g4, s5: g5, s6: g6, s7: g7, s8: g8, s9: g9 };
    return map;
  }, [reqs, optId, signed, lint, sim, synth, corrDone, ecos, qual, evidence, lots, t]);

  const currentStage = STAGES.find((s) => gates[s.id].status === "blocked")?.id ?? "s9";
  const mustReqs = reqs.filter((r) => r.priority === "must" && r.status !== "superseded");
  const tracePct = Math.round((mustReqs.filter((r) => r.verId).length / Math.max(1, mustReqs.length)) * 100);
  const qualPct = Math.round((qual.filter((r) => r.status === "pass" || r.status === "waiver").length / Math.max(1, qual.length)) * 100);

  // Correlation (S5): prediction from the spec × temperature model vs
  // synthetic ES samples (marked synthetic_fixture per §18.2).
  const corr = useMemo(() => {
    const base = corrBase(tpl);
    const samples = makeEsSamples(tpl, base);
    const perParam = tpl.corrParams.map((p, i) => {
      const pred = samples.map((s) => base[i] * (1 + p.tempCoef * (s.corner - 25)));
      return { key: p.key, unit: p.unit, stats: corrStats(pred, samples.map((s) => s.values[i])), pred };
    });
    return { samples, perParam, base };
  }, [tpl]);

  const pkgScene = useMemo(() => buildPackageScene(tpl), [tpl]);

  // ── S1 action: reflect the AI proposal — create the missing verification
  //    item and approve the draft requirement (demo of the §9.1 Requirements
  //    Analyst loop; the real flow needs human approval before apply) ──
  const linkDraftReq = (r: Requirement) => {
    const verId = `VER-${r.id.slice(-3)}`;
    setVerDone((v) => ({ ...v, [verId]: false }));
    setReqs((rs) => rs.map((x) => (x.id === r.id ? { ...x, status: "approved", verId } : x)));
  };

  const runStage = (fn: () => void) => {
    fn();
    setRanAt(new Date().toLocaleTimeString());
  };

  // ECO lifecycle: analyze → close (bump mask/test-program revisions)
  const ecoAnalyze = (id: string) => setEcos((es) => es.map((e) => (e.id === id ? { ...e, status: "analyzed" } : e)));
  const ecoClose = (id: string) => {
    setEcos((es) => es.map((e) => (e.id === id ? { ...e, status: "closed", maskRev: `${maskRev} → ${nextRev(maskRev)}` } : e)));
    setMaskRev((r) => nextRev(r));
    setTestProgRev((v) => v + 1);
    // affected evidence gets a NEW revision (never overwritten in place, §14.3)
    setEvidence((es) =>
      es.map((e) =>
        e.id.includes("RTL") || e.id.includes("GDS")
          ? { ...e, rev: nextRev(maskRev), approved: false, approver: "" }
          : e.id.startsWith("TESTPROG")
            ? { ...e, rev: `v${testProgRev + 1}`, approved: false, approver: "" }
            : e,
      ),
    );
    // re-run the design flow so the stale evidence is regenerated
    if (lint) setLint(runLint(mission.starterRtl, mission.topModule));
    if (sim) setSim(runSimulation(mission.starterRtl, mission.topModule));
    if (synth) setSynth(runSynthesis(mission.starterRtl, mission.topModule, 10));
  };

  const qualAction = (group: string, action: "evidence" | "capa" | "waiver") =>
    setQual((qs) =>
      qs.map((r) =>
        r.group !== group ? r : { ...r, status: action === "waiver" ? "waiver" : "pass", note: action === "capa" ? L("CAPA 완료 후 재시험 합격 (synthetic)", "retest passed after CAPA completion (synthetic)", "CAPA完了後の再試験合格(synthetic)") : action === "evidence" ? L("lab evidence 업로드 (synthetic fixture)", "lab evidence uploaded (synthetic fixture)", "ラボエビデンス登録(synthetic fixture)") : r.note },
      ),
    );

  const approveEvidence = (id: string) =>
    setEvidence((es) => es.map((e) => (e.id === id ? { ...e, approved: true, approver: "demo.architect (Approver)" } : e)));

  const mrbDone = (lotId: string) => setLots((ls) => ls.map((l) => (l.id === lotId ? { ...l, disposition: "mrb_reviewed" } : l)));

  const staleActive = ecos.some((e) => e.status === "analyzed");

  return (
    <div>
      {/* ── Cockpit strip (§4.2) ── */}
      <div style={{ ...card, display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center", marginBottom: 10 }}>
        <Kpi label={t("asic.cockpit.stage")} value={`${STAGES.find((s) => s.id === currentStage)!.num}/9 · ${t(`asic.stage.${currentStage}` as never)}`} />
        <Kpi label={t("asic.cockpit.nextGate")} value={STAGES.find((s) => s.id === currentStage)!.gate} color={gates[currentStage].status === "pass" ? "#34d399" : "#fbbf24"} />
        <Kpi label={t("asic.cockpit.trace")} value={`${tracePct}%`} color={tracePct === 100 ? "#34d399" : "#fbbf24"} />
        <Kpi label={t("asic.cockpit.qual")} value={`${qualPct}%`} color={qualPct === 100 ? "#34d399" : "#fbbf24"} />
        <Kpi label={t("asic.cockpit.r2")} value={corrDone ? round2(corr.perParam[0].stats.r2) : "—"} />
        {live.gate && (
          <Kpi
            label={t("asic.cockpit.readiness")}
            value={live.gate.readiness}
            color={live.gate.readiness_reachable ? "#67e8f9" : "#fbbf24"}
          />
        )}
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginLeft: "auto" }}>
          <ConfidenceBadge kind="educational_estimate" />
          <ConfidenceBadge kind="synthetic_fixture" />
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "236px 1fr", gap: 12, alignItems: "start" }}>
        {/* ── Work-centered 9-stage menu ── */}
        <div style={{ ...card, padding: 8 }}>
          {STAGES.map((s) => {
            const g = gates[s.id];
            const active = stage === s.id;
            return (
              <button
                key={s.id}
                onClick={() => setStage(s.id)}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 8,
                  width: "100%",
                  textAlign: "left",
                  padding: "7px 8px",
                  marginBottom: 3,
                  borderRadius: 6,
                  border: `1px solid ${active ? tpl.color : "transparent"}`,
                  background: active ? `${tpl.color}14` : "transparent",
                  color: active ? "#f1f5f9" : "#cbd5e1",
                  cursor: "pointer",
                  fontFamily: "inherit",
                }}
              >
                <GateDot status={g.status} />
                <span style={{ fontSize: 12, fontWeight: active ? 600 : 400, flex: 1 }}>
                  {t(`asic.stage.${s.id}` as never)}
                  <span style={{ display: "block", fontSize: 9, color: "#64748b" }}>{s.ws}</span>
                </span>
              </button>
            );
          })}
          <div style={{ fontSize: 9, color: "#475569", padding: "6px 4px", lineHeight: 1.5 }}>{t("asic.menuHint")}</div>
        </div>

        {/* ── Stage panel ── */}
        <div style={{ minWidth: 0 }}>
          {staleActive && (
            <div style={{ border: "1px solid #fbbf2466", background: "#fbbf2411", borderRadius: 8, padding: "8px 12px", marginBottom: 10, fontSize: 12, color: "#fbbf24" }}>
              ⚠ {t("asic.stale")}
            </div>
          )}

          {stage === "s1" && (
            <SectionCard title={`${t("asic.stage.s1")} — ${t("asic.s1.matrix")}`} right={<ConfidenceBadge kind="educational_estimate" />}>
              <div style={{ overflowX: "auto" }}>
                <table style={{ width: "100%", borderCollapse: "collapse" }}>
                  <thead>
                    <tr>
                      <th style={th}>Req ID</th>
                      <th style={th}>text</th>
                      <th style={th}>cat</th>
                      <th style={th}>pri</th>
                      <th style={th}>status</th>
                      <th style={th}>verification</th>
                      <th style={th}></th>
                    </tr>
                  </thead>
                  <tbody>
                    {reqs.map((r) => (
                      <tr key={r.id}>
                        <td style={{ ...td, fontFamily: "monospace", color: "#7dd3fc" }}>{r.id}</td>
                        <td style={td}>
                          {pickText(r.text, lang)}
                          <span style={{ display: "block", fontSize: 9, color: "#475569" }}>{pickText(r.source, lang)}</span>
                        </td>
                        <td style={td}>{t(`asic.cat.${r.category}` as never)}</td>
                        <td style={td}>{r.priority}</td>
                        <td style={td}>
                          <Chip color={r.status === "approved" ? "#34d399" : r.status === "draft" ? "#f87171" : r.status === "provisional" ? "#fbbf24" : "#94a3b8"}>
                            {r.status === "provisional" ? `provisional · ${r.assumptionId}` : r.status}
                          </Chip>
                        </td>
                        <td style={{ ...td, fontFamily: "monospace" }}>{r.verId || <span style={{ color: "#f87171" }}>unlinked</span>}</td>
                        <td style={td}>
                          {r.status === "draft" && (
                            <button style={btn(true, "#fbbf24")} onClick={() => linkDraftReq(r)}>
                              {t("asic.act.linkReq")}
                            </button>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div style={{ marginTop: 8, display: "flex", gap: 14, alignItems: "center", flexWrap: "wrap", fontSize: 11, color: "#94a3b8" }}>
                <span>
                  {t("asic.cockpit.trace")}: <b style={{ fontFamily: "monospace", color: tracePct === 100 ? "#34d399" : "#fbbf24" }}>{tracePct}%</b>
                </span>
                <span>
                  {t("asic.s1.conflict")}: <b style={{ fontFamily: "monospace", color: reqs.some((r) => r.status === "draft") ? "#f87171" : "#34d399" }}>{reqs.filter((r) => r.status === "draft").length}</b>
                </span>
                <span style={{ color: "#475569" }}>{t("asic.s1.gate")}: REQ_TRACE_100</span>
              </div>
            </SectionCard>
          )}

          {stage === "s2" && (
            <>
              <ChainRevisionPanel live={live} liveState={liveState} tpl={tpl} />
              <SectionCard title={`${t("asic.stage.s2")} — ${t("asic.s2.options")}`}>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))", gap: 8 }}>
                {tpl.options.map((o) => (
                  <div
                    key={o.id}
                    onClick={() => setOptId(o.id)}
                    style={{
                      border: `1px solid ${optId === o.id ? tpl.color : "#1e293b"}`,
                      background: optId === o.id ? `${tpl.color}14` : "#0f172a",
                      borderRadius: 8,
                      padding: 10,
                      cursor: "pointer",
                    }}
                  >
                    <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 6 }}>
                      <b style={{ fontSize: 12, fontFamily: "monospace" }}>{o.id}</b>
                      <Chip color={o.risk === "low" ? "#34d399" : o.risk === "medium" ? "#fbbf24" : "#f87171"}>risk {o.risk}</Chip>
                    </div>
                    <div style={{ fontSize: 11, color: "#cbd5e1", lineHeight: 1.7 }}>
                      {o.foundry} · {o.node}
                      <br />
                      pkg {o.pkg} · lead {o.leadWeeks[0]}–{o.leadWeeks[1]} wk
                      <br />
                      NRE ×{o.nreIdx.toFixed(2)}
                    </div>
                    <div style={{ marginTop: 6 }}>
                      {optId === o.id ? <Chip color="#34d399">✓ {t("asic.s2.approved")}</Chip> : <Chip color="#64748b">{t("asic.s2.clickApprove")}</Chip>}
                    </div>
                  </div>
                ))}
              </div>
              <div style={{ marginTop: 12, overflowX: "auto" }}>
                <table style={{ width: "100%", borderCollapse: "collapse" }}>
                  <thead>
                    <tr>
                      <th style={th}>Risk</th>
                      <th style={th}>sev</th>
                      <th style={th}>owner</th>
                      <th style={th}>mitigation</th>
                    </tr>
                  </thead>
                  <tbody>
                    {tpl.risks.map((r) => (
                      <tr key={r.id}>
                        <td style={{ ...td, fontFamily: "monospace", color: "#7dd3fc" }}>{r.id}</td>
                        <td style={td}>
                          <Chip color={r.sev === "high" ? "#f87171" : r.sev === "medium" ? "#fbbf24" : "#34d399"}>{r.sev}</Chip>
                        </td>
                        <td style={td}>{r.owner}</td>
                        <td style={td}>{pickText(r.text, lang)} → {pickText(r.mitigation, lang)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              </SectionCard>
            </>
          )}

          {stage === "s3" && (
            <>
              <ChainBudgetPanel live={live} liveState={liveState} />
            <SectionCard title={`${t("asic.stage.s3")} — ${t("asic.s3.wbs")}`}>
              <table style={{ width: "100%", borderCollapse: "collapse", marginBottom: 12 }}>
                <tbody>
                  {tpl.milestones.map((m) => (
                    <tr key={m.id}>
                      <td style={{ ...td, fontFamily: "monospace", color: "#7dd3fc", width: 36 }}>{m.id}</td>
                      <td style={td}>{pickL(m.text, lang)}</td>
                      <td style={{ ...td, fontFamily: "monospace", color: "#94a3b8", width: 100 }}>{m.due}</td>
                      <td style={td}>
                        <Chip color={m.status === "done" ? "#34d399" : "#64748b"}>{m.status}</Chip>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <div style={{ border: "1px solid #1e293b", borderRadius: 8, padding: 10, background: "#0f172a" }}>
                <div style={{ fontSize: 12, marginBottom: 8 }}>
                  {t("asic.s3.baseline")} — <span style={{ fontFamily: "monospace", color: "#7dd3fc" }}>hash {eduHash(tpl.id + "baseline")}</span>{" "}
                  <Chip color="#a78bfa">{t("asic.conf.synthetic_fixture")}</Chip>
                </div>
                {signed ? (
                  <div style={{ fontSize: 12, color: "#34d399" }}>
                    ✓ {t("asic.s3.signedBy")} demo.architect (Approver) · {t("asic.s3.sod")} {t("asic.s3.sodOk")}
                  </div>
                ) : (
                  <button
                    aria-label="asic-sign-baseline"
                    disabled={gates.s1.status === "blocked" || gates.s2.status === "blocked"}
                    style={{ ...btn(gates.s1.status === "pass" && gates.s2.status === "pass"), opacity: gates.s1.status === "pass" && gates.s2.status === "pass" ? 1 : 0.4 }}
                    onClick={() => setSigned(true)}
                  >
                    {t("asic.act.sign")} (BASELINE_SIGNED)
                  </button>
                )}
                <div style={{ fontSize: 10, color: "#475569", marginTop: 6 }}>{t("asic.s3.sodNote")}</div>
              </div>
              <table style={{ width: "100%", borderCollapse: "collapse", marginTop: 12 }}>
                <thead>
                  <tr>
                    <th style={th}>NRE item</th>
                    <th style={th}>{t("asic.s3.scope")}</th>
                  </tr>
                </thead>
                <tbody>
                  {tpl.nre.map((n) => (
                    <tr key={pickText(n.item, "ko")}>
                      <td style={td}>{pickText(n.item, lang)}</td>
                      <td style={td}>{pickText(n.amount, lang)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              </SectionCard>
              <TradeStudyPanel live={live} liveState={liveState} />
            </>
          )}

          {stage === "s4" && (
            <>
              <SectionCard
                title={`${t("asic.stage.s4")} — ${t("asic.s4.design")}`}
                right={
                  <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                    {ranAt && <span style={{ fontSize: 10, color: "#475569", fontFamily: "monospace" }}>{ranAt}</span>}
                    <ConfidenceBadge kind="educational_estimate" />
                  </div>
                }
              >
                <div style={{ fontSize: 11, color: "#94a3b8", marginBottom: 8 }}>
                  {t("asic.s4.reuse")} <b style={{ color: "#7dd3fc", fontFamily: "monospace" }}>{mission.slug}</b> ({mission.title}) — digital control block · engine educational-mock v1 (browser)
                </div>
                <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 10 }}>
                  <button aria-label="asic-run-lint" style={btn(true)} onClick={() => runStage(() => { setLint(runLint(mission.starterRtl, mission.topModule)); setSim(null); setSynth(null); setPnr(null); })}>
                    ① Lint
                  </button>
                  <button aria-label="asic-run-sim" style={btn(true)} onClick={() => runStage(() => { setSim(runSimulation(mission.starterRtl, mission.topModule)); setSynth(null); setPnr(null); })}>
                    ② Simulation
                  </button>
                  <button aria-label="asic-run-synth" style={btn(true)} onClick={() => runStage(() => { setSynth(runSynthesis(mission.starterRtl, mission.topModule, 10)); setPnr(null); })}>
                    ③ Synthesis + STA
                  </button>
                  <button aria-label="asic-run-pnr" style={btn(true)} onClick={() => runStage(() => { setPnr(runPlaceRoute(mission.topModule, DEFAULT_FLOORPLAN)); })}>
                    ④ P&R
                  </button>
                </div>
                <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                  {lint && <Kpi label="lint E/W" value={`${lint.errors.length}/${lint.warnings.length}`} color={lint.errors.length ? "#f87171" : "#34d399"} />}
                  {sim && <Kpi label="sim pass" value={`${sim.passed}/${sim.testCount}`} color={sim.failed ? "#f87171" : "#34d399"} />}
                  {sim && <Kpi label="coverage" value={`${Math.round(sim.coverage.overall * 100)}%`} />}
                  {synth && <Kpi label="gates" value={synth.gateCount} />}
                  {synth && <Kpi label="FFs" value={synth.flopCount} />}
                  {synth && <Kpi label="WNS" value={`${synth.timingSlackNs} ns`} color={synth.timingSlackNs < 0 ? "#f87171" : "#34d399"} />}
                  {pnr && <Kpi label="DRC" value={pnr.drcViolations} color={pnr.drcViolations ? "#f87171" : "#34d399"} />}
                </div>
                {staleActive && <div style={{ marginTop: 8, fontSize: 11, color: "#fbbf24" }}>⚠ {t("asic.s4.rerunHint")}</div>}
              </SectionCard>
              {sim?.waveform && (
                <SectionCard title={t("asic.s4.wave")}>
                  <EdaWaveform data={sim.waveform} />
                </SectionCard>
              )}
              <SectionCard title={t("asic.s4.vmatrix")}>
                <div style={{ overflowX: "auto" }}>
                  <table style={{ width: "100%", borderCollapse: "collapse" }}>
                    <thead>
                      <tr>
                        <th style={th}>VER</th>
                        <th style={th}>req</th>
                        <th style={th}>method</th>
                        <th style={th}>environment</th>
                        <th style={th}>target</th>
                        <th style={th}>owner</th>
                        <th style={th}>status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {tpl.verItems.map((v) => (
                        <tr key={v.id}>
                          <td style={{ ...td, fontFamily: "monospace", color: "#7dd3fc" }}>{v.id}</td>
                          <td style={{ ...td, fontFamily: "monospace" }}>{v.reqId}</td>
                          <td style={td}>{v.method}</td>
                          <td style={td}>{pickText(v.env, lang)}</td>
                          <td style={{ ...td, fontFamily: "monospace" }}>{Math.round(v.target * 100)}%</td>
                          <td style={td}>{v.owner}</td>
                          <td style={td}>
                            <Chip color={verDone[v.id] || v.method !== "qualification" ? "#34d399" : "#fbbf24"}>
                              {verDone[v.id] || v.method !== "qualification" ? "linked/evidence" : "→ S07"}
                            </Chip>
                          </td>
                        </tr>
                      ))}
                      {reqs
                        .filter((r) => r.verId && !tpl.verItems.some((v) => v.id === r.verId))
                        .map((r) => (
                          <tr key={r.verId}>
                            <td style={{ ...td, fontFamily: "monospace", color: "#fbbf24" }}>{r.verId}</td>
                            <td style={{ ...td, fontFamily: "monospace" }}>{r.id}</td>
                            <td style={td}>{r.method}</td>
                            <td style={td}>{t("asic.s4.newVer")}</td>
                            <td style={{ ...td, fontFamily: "monospace" }}>100%</td>
                            <td style={td}>Verification Engineer</td>
                            <td style={td}>
                              <Chip color="#fbbf24">planned</Chip>
                            </td>
                          </tr>
                        ))}
                    </tbody>
                  </table>
                </div>
              </SectionCard>
              <CornerStudiesPanel live={live} liveState={liveState} />
              <ToolRunsPanel live={live} liveState={liveState} />
            </>
          )}

          {stage === "s5" && (
            <>
              <SectionCard title={`${t("asic.stage.s5")} — ${t("asic.s5.pkg")}`} right={<Chip color={tpl.color}>react-three-fiber · {t("asic.s5.schematic")}</Chip>}>
                <div style={{ height: 360 }}>
                  <Eda3DViewer scene={pkgScene} />
                </div>
                <div style={{ fontSize: 10, color: "#475569", marginTop: 6 }}>{t("asic.s5.pkgNote")}</div>
              </SectionCard>
              <SectionCard
                title={t("asic.s5.corr")}
                right={
                  <button aria-label="asic-run-corr" style={btn(!corrDone, "#34d399")} onClick={() => setCorrDone(true)}>
                    {t("asic.act.runCorr")}
                  </button>
                }
              >
                <div style={{ fontSize: 11, color: "#94a3b8", marginBottom: 8, fontFamily: "monospace" }}>
                  {t("asic.s5.genealogy")}: GDS {maskRev} [{eduHash(tpl.id + maskRev)}] → mask MS-{maskRev} → wafer lot WL-{tpl.id.slice(0, 3).toUpperCase()}-09 (FAB alias) → assembly AL-1120 ({tpl.options[0].pkg}) → ES-1001..1012
                </div>
                {corrDone ? (
                  <div style={{ display: "grid", gridTemplateColumns: "minmax(260px, 340px) 1fr", gap: 12, alignItems: "start" }}>
                    <div>
                      <Scatter points={corr.samples.map((s, i) => [corr.perParam[0].pred[i], s.values[0]])} xLabel="prediction" yLabel="measurement" />
                      <div style={{ marginTop: 4 }}>
                        <ConfidenceBadge kind="synthetic_fixture" />
                      </div>
                    </div>
                    <div style={{ overflowX: "auto" }}>
                      <table style={{ width: "100%", borderCollapse: "collapse" }}>
                        <thead>
                          <tr>
                            <th style={th}>param</th>
                            <th style={th}>bias</th>
                            <th style={th}>MAE</th>
                            <th style={th}>RMSE</th>
                            <th style={th}>R²</th>
                            <th style={th}>unit</th>
                          </tr>
                        </thead>
                        <tbody>
                          {corr.perParam.map((p) => (
                            <tr key={p.key}>
                              <td style={{ ...td, fontFamily: "monospace", color: "#7dd3fc" }}>{p.key}</td>
                              <td style={{ ...td, fontFamily: "monospace" }}>{p.stats.bias.toExponential(2)}</td>
                              <td style={{ ...td, fontFamily: "monospace" }}>{round2(p.stats.mae)}</td>
                              <td style={{ ...td, fontFamily: "monospace" }}>{round2(p.stats.rmse)}</td>
                              <td style={{ ...td, fontFamily: "monospace", color: p.stats.r2 >= 0.95 ? "#34d399" : "#fbbf24" }}>{round2(p.stats.r2)}</td>
                              <td style={td}>{p.unit}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                      <div style={{ fontSize: 10, color: "#475569", marginTop: 6 }}>{t("asic.s5.corrNote")}</div>
                    </div>
                  </div>
                ) : (
                  <div style={{ fontSize: 12, color: "#64748b" }}>{t("asic.s5.corrHint")}</div>
                )}
              </SectionCard>
              <EquipmentRunsPanel live={live} liveState={liveState} />
            </>
          )}

          {stage === "s6" && (
            <>
            <SectionCard title={`${t("asic.stage.s6")} — ECO & Test Program`}>
              {ecos.length === 0 && <div style={{ fontSize: 12, color: "#64748b" }}>{t("asic.s6.none")}</div>}
              {ecos.map((e) => (
                <div key={e.id} style={{ border: "1px solid #1e293b", borderRadius: 8, padding: 10, marginBottom: 8, background: "#0f172a" }}>
                  <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
                    <b style={{ fontFamily: "monospace", color: "#7dd3fc", fontSize: 12 }}>{e.id}</b>
                    <span style={{ fontSize: 12, flex: 1 }}>{pickL(e.text, lang)}</span>
                    <Chip color={e.status === "closed" ? "#34d399" : e.status === "analyzed" ? "#fbbf24" : "#94a3b8"}>{e.status}</Chip>
                  </div>
                  <div style={{ fontSize: 11, color: "#94a3b8", marginTop: 6 }}>
                    {t("asic.s6.impact")}: {e.impactReq.join(", ") || "—"} / runs {e.impactRuns.join(", ")} / mask {e.maskRev}
                  </div>
                  <div style={{ display: "flex", gap: 6, marginTop: 8 }}>
                    {e.status === "proposed" && (
                      <button style={btn(true, "#fbbf24")} onClick={() => ecoAnalyze(e.id)}>
                        {t("asic.act.ecoAnalyze")}
                      </button>
                    )}
                    {e.status === "analyzed" && (
                      <button aria-label={`asic-eco-close-${e.id}`} style={btn(true, "#34d399")} onClick={() => ecoClose(e.id)}>
                        {t("asic.act.ecoClose")}
                      </button>
                    )}
                  </div>
                </div>
              ))}
              <div style={{ fontSize: 11, color: "#94a3b8" }}>
                {t("asic.s6.mask")}: <b style={{ fontFamily: "monospace", color: "#7dd3fc" }}>{maskRev}</b> · {t("asic.s6.testprog")}: <b style={{ fontFamily: "monospace", color: "#7dd3fc" }}>ATE v{testProgRev}</b>
              </div>
            </SectionCard>
            <TestProgramTwin tpl={tpl} testProgRev={testProgRev} maskRev={maskRev} />
            <TestFlowAnalysisPanel live={live} liveState={liveState} />
            </>
          )}

          {stage === "s7" && (
            <>
            <BackendQualPanel live={live} liveState={liveState} />
            <SectionCard
              title={`${t("asic.stage.s7")} — AEC-Q100 (${tpl.grade} · ${tempGrade[0]}~+${tempGrade[1]} °C)`}
              right={<Chip color="#38bdf8">{live.gate?.policy_version ?? "policy alps-asic-v1.1"}</Chip>}
            >
              <div style={{ overflowX: "auto" }}>
                <table style={{ width: "100%", borderCollapse: "collapse" }}>
                  <thead>
                    <tr>
                      <th style={th}>group</th>
                      <th style={th}>method</th>
                      <th style={th}>condition</th>
                      <th style={th}>duration</th>
                      <th style={th}>samples</th>
                      <th style={th}>status</th>
                      <th style={th}></th>
                    </tr>
                  </thead>
                  <tbody>
                    {qual.map((r) => (
                      <tr key={r.group}>
                        <td style={{ ...td, fontFamily: "monospace", color: "#7dd3fc" }}>{r.group}</td>
                        <td style={td}>
                          {pickText(r.method, lang)}
                          {r.note && <span style={{ display: "block", fontSize: 9, color: r.status === "fail" ? "#f87171" : "#64748b" }}>{pickL(r.note, lang)}</span>}
                        </td>
                        <td style={td}>{pickText(r.cond, lang)}</td>
                        <td style={{ ...td, fontFamily: "monospace" }}>{r.duration}</td>
                        <td style={{ ...td, fontFamily: "monospace" }}>{r.samples}</td>
                        <td style={td}>
                          <Chip color={r.status === "pass" ? "#34d399" : r.status === "fail" ? "#f87171" : r.status === "waiver" ? "#a78bfa" : "#fbbf24"}>{r.status}</Chip>
                        </td>
                        <td style={td}>
                          <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
                            {r.status === "pending" && (
                              <button style={btn(true)} onClick={() => qualAction(r.group, "evidence")}>
                                {t("asic.act.qualEvidence")}
                              </button>
                            )}
                            {r.status === "fail" && (
                              <>
                                <button style={btn(true, "#34d399")} onClick={() => qualAction(r.group, "capa")}>
                                  {t("asic.act.qualCapa")}
                                </button>
                                <button style={btn(true, "#a78bfa")} onClick={() => qualAction(r.group, "waiver")}>
                                  {t("asic.act.qualWaiver")}
                                </button>
                              </>
                            )}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div style={{ fontSize: 10, color: "#475569", marginTop: 8 }}>{t("asic.s7.note")}</div>
            </SectionCard>
            <SafetyTracePanel live={live} liveState={liveState} />
            </>
          )}

          {stage === "s8" && (
            <>
              {/* R3 EPIC I: 가정·영향 탐색·편차 — 게이트 블로커의 원인이 되는 데이터 */}
              <ConcurrentEngineeringPanel live={live} liveState={liveState} onChanged={reloadLive} />
              <SectionCard title={`${t("asic.stage.s8")} — ${t("asic.s8.pack")}`}>
                <div style={{ overflowX: "auto" }}>
                  <table style={{ width: "100%", borderCollapse: "collapse" }}>
                    <thead>
                      <tr>
                        <th style={th}>artifact</th>
                        <th style={th}>kind</th>
                        <th style={th}>rev</th>
                        <th style={th}>hash</th>
                        <th style={th}>classification</th>
                        <th style={th}>author → approver</th>
                        <th style={th}></th>
                      </tr>
                    </thead>
                    <tbody>
                      {evidence.map((e) => (
                        <tr key={e.id}>
                          <td style={{ ...td, fontFamily: "monospace", color: "#7dd3fc" }}>{e.id}</td>
                          <td style={td}>{pickL(e.kind, lang)}</td>
                          <td style={{ ...td, fontFamily: "monospace" }}>{e.rev}</td>
                          <td style={{ ...td, fontFamily: "monospace", color: "#475569" }}>{eduHash(e.id + e.rev)}…</td>
                          <td style={td}>
                            <Chip color={e.classification === "CUSTOMER_CONFIDENTIAL" ? "#f87171" : "#64748b"} title={t("asic.s8.clsNote")}>
                              {e.classification}
                            </Chip>
                          </td>
                          <td style={td}>
                            {e.author} → {e.approver || "—"}
                          </td>
                          <td style={td}>
                            {e.approved ? (
                              <Chip color="#34d399">✓ approved</Chip>
                            ) : (
                              <button style={btn(true)} onClick={() => approveEvidence(e.id)}>
                                {t("asic.act.approveEv")}
                              </button>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </SectionCard>
              {/* gate report computed SERVER-SIDE and rendered verbatim —
                  the fixture pre below only appears when the API is down */}
              <GateReportPanel
                live={live}
                liveState={liveState}
                fallback={
                  <div>
                    <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 10 }}>
                      {READINESS_LEVELS.map((l) => {
                        const reached = l.reachable && gates.s8.status === "pass" ? l.key === "controlled_pilot" : l.key === "education_only";
                        return (
                          <Chip key={l.key} color={reached ? "#34d399" : l.reachable ? "#64748b" : "#7f1d1d"}>
                            {reached ? "● " : l.reachable ? "○ " : "✕ "}
                            {l.key}
                          </Chip>
                        );
                      })}
                    </div>
                    <pre style={{ margin: 0, padding: 10, background: "#020617", borderRadius: 8, fontSize: 10, fontFamily: "monospace", color: "#94a3b8", overflowX: "auto" }}>
{JSON.stringify(
  {
    gate_id: "G8_RELEASE",
    status: gates.s8.status === "pass" ? "review_ready" : "blocked",
    policy_version: "alps-asic-v1.1",
    checks: [
      { check_id: "EVIDENCE_APPROVALS", status: gates.s8.status === "pass" ? "pass" : "fail", actual: evidence.filter((e) => e.approved).length, target: evidence.length },
      { check_id: "REQ_TRACE_COVERAGE", status: tracePct === 100 ? "pass" : "fail", actual: tracePct / 100, target: 1.0 },
      { check_id: "MOCK_RESULT_PRESENT", status: "fail", actual: 3, target: 0, blocking_refs: ["run:lint", "run:sim", "run:synth"], note: "educational-mock — §10.2" },
    ],
    decision_required: true,
  },
  null,
  2,
)}
                    </pre>
                    <div style={{ fontSize: 11, color: "#fbbf24", marginTop: 8 }}>⚠ {t("asic.s8.blockedNote")}</div>
                  </div>
                }
              />
              <EvidenceReportPanel tplId={tpl.id} />
            </>
          )}

          {stage === "s9" && (
            <>
              {/* R3 EPIC J: 근거 중심 AI Copilot — 모든 제안은 근거 링크 + diff 확인 후 수락 */}
              <CopilotPanel live={live} liveState={liveState} tplId={tpl.id} onChanged={reloadLive} />
              <FaStudio live={live} liveState={liveState} />
              <SupplyChainPanel live={live} liveState={liveState} />
              <SectionCard title={`${t("asic.stage.s9")} — ${t("asic.s9.quality")}`} right={<Chip color="#a78bfa">{t("asic.conf.synthetic_fixture")}</Chip>}>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: 12 }}>
                  <div>
                    <TrendLine values={lots.map((l) => l.yieldPct)} labels={lots.map((l) => l.id.slice(-2))} yLabel="yield %" />
                  </div>
                  <div>
                    <Pareto
                      bars={[
                        { label: "bin1 good", value: lots.reduce((a, l) => a + l.bins.good, 0) },
                        { label: "retest", value: lots.reduce((a, l) => a + l.bins.retest, 0) },
                        { label: "fail-1", value: lots.reduce((a, l) => a + l.bins.fail1, 0) },
                        { label: "fail-2", value: lots.reduce((a, l) => a + l.bins.fail2, 0) },
                      ]}
                    />
                  </div>
                  <div>
                    <SpcChart
                      points={lots.flatMap((l) => l.spc)}
                      ucl={1.05}
                      lcl={0.95}
                      target={1.0}
                      violIdx={lots.flatMap((l, li) => l.spc.map((v, i) => (v > 1.05 || v < 0.95 ? li * 5 + i : -1))).filter((i) => i >= 0)}
                    />
                  </div>
                </div>
              </SectionCard>
              <SectionCard title={t("asic.s9.lots")}>
                <div style={{ overflowX: "auto" }}>
                  <table style={{ width: "100%", borderCollapse: "collapse" }}>
                    <thead>
                      <tr>
                        <th style={th}>lot</th>
                        <th style={th}>wafers</th>
                        <th style={th}>yield</th>
                        <th style={th}>bins (good/retest/f1/f2)</th>
                        <th style={th}>status</th>
                        <th style={th}></th>
                      </tr>
                    </thead>
                    <tbody>
                      {lots.map((l) => (
                        <tr key={l.id}>
                          <td style={{ ...td, fontFamily: "monospace", color: "#7dd3fc" }}>{l.id}</td>
                          <td style={{ ...td, fontFamily: "monospace" }}>{l.wafers}</td>
                          <td style={{ ...td, fontFamily: "monospace", color: l.yieldPct < 85 ? "#f87171" : "#34d399" }}>{l.yieldPct}%</td>
                          <td style={{ ...td, fontFamily: "monospace" }}>{l.bins.good}/{l.bins.retest}/{l.bins.fail1}/{l.bins.fail2}</td>
                          <td style={td}>
                            {l.excursion && <div style={{ fontSize: 10, color: "#f87171", maxWidth: 260 }}>⚠ {pickL(l.excursion, lang)}</div>}
                            <Chip color={l.disposition === "released" ? "#34d399" : l.disposition === "held" ? "#f87171" : "#a78bfa"}>{l.disposition}</Chip>
                          </td>
                          <td style={td}>
                            {l.disposition === "held" && (
                              <button aria-label={`asic-mrb-${l.id}`} style={btn(true, "#a78bfa")} onClick={() => mrbDone(l.id)}>
                                {t("asic.act.mrb")}
                              </button>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <div style={{ fontSize: 10, color: "#475569", marginTop: 8 }}>{t("asic.s9.note")}</div>
              </SectionCard>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

const nextRev = (r: string) => `r${parseInt(r.slice(1), 10) + 1}`;

export function AsicProgram() {
  const { t, i18n } = useTranslation();
  const [tplId, setTplId] = useState(ASIC_TEMPLATES[0].id);
  const tpl = ASIC_TEMPLATES.find((x) => x.id === tplId)!;
  return (
    <div style={{ height: "100%", overflowY: "auto" }}>
      <div style={{ display: "flex", alignItems: "baseline", gap: 10, marginBottom: 8, flexWrap: "wrap" }}>
        <h2 style={{ margin: 0, fontSize: 16 }}>{t("asic.title")}</h2>
        <span style={{ fontSize: 12, color: "#64748b" }}>{t("asic.subtitle")}</span>
      </div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 10 }}>
        {ASIC_TEMPLATES.map((x) => (
          <button key={x.id} onClick={() => setTplId(x.id)} style={{ ...btn(tplId === x.id, x.color), fontWeight: tplId === x.id ? 600 : 400 }}>
            {pickL(x.name, i18n.resolvedLanguage)} · {x.grade}
          </button>
        ))}
      </div>
      <Workbench key={tplId} tpl={tpl} />
    </div>
  );
}
