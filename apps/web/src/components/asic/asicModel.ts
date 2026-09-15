import { mulberry32, strSeed } from "../eda/edaRunner";
import { L, type LStr, type LStrLike } from "../../lib/lstr";

// Alps Alpine 9-stage ASIC development workbench — data model.
// Content follows docs/AgentIC_AlpsAlpine_ASIC_Turnkey_DigitalTwin_고도화_개발지시서_v1.0.md:
// §2 maps the nine Alps stages to workspaces/gates, §5 defines the four product
// templates, §10 the gate/readiness discipline, §11 ES/CS correlation, §12 the
// versioned AEC-Q100 policy, §13 production quality.
//
// This is the education/prototype twin: every number is deterministic and
// synthetic. Per §0.1/§15.3 nothing here can claim sign-off — result cards
// carry an explicit confidence badge (educational_estimate / synthetic_fixture)
// and the release gate in stage 8 stays honestly blocked by "mock result
// present" (§10.2 blocker #1). UI chrome is i18n (ko/en/ja); user-visible row
// prose (requirement texts, risks, milestones, …) is L() triplets so the ja
// UI shows Japanese end to end, while pure technical strings (lot ids, JEDEC
// conditions, fab aliases) stay plain — the way fab data actually reads.

export type Confidence = "educational_estimate" | "synthetic_fixture";

export type ReqStatus = "draft" | "provisional" | "approved" | "superseded";
export type VerMethod = "rtl-sim" | "bench" | "spice+synth" | "qualification" | "monte-carlo" | "fault-campaign";

export type ReqCategory = "function" | "quality" | "environment" | "interface" | "safety";

export type Requirement = {
  id: string;
  text: LStr;
  source: LStrLike;
  category: ReqCategory;
  priority: "must" | "should";
  status: ReqStatus;
  method: VerMethod;
  /** verification item this requirement is traced to ("" = unlinked) */
  verId: string;
  /** provisional specs carry an assumption id (§2.1) */
  assumptionId?: string;
};

export type ArchBlock = { key: string; label: string; kind: "sensor" | "analog" | "mixed" | "digital" | "io" | "power" };

export type Spec = { key: string; value: number; unit: string; tol: string };

export type ProcessOption = {
  id: string;
  foundry: string; // masked alias (§6.4 — no real fab names)
  node: string;
  pkg: string;
  risk: "low" | "medium" | "high";
  leadWeeks: [number, number];
  nreIdx: number; // relative cost index, masked
};

export type Risk = { id: string; text: LStr; sev: "high" | "medium" | "low"; owner: string; mitigation: LStr };

export type VerItem = {
  id: string;
  reqId: string;
  method: VerMethod;
  env: LStrLike;
  target: number; // coverage target 0..1
  owner: string; // role from §3
  done: boolean;
};

export type Milestone = { id: string; text: LStr; due: string; status: "done" | "open" };

export type Eco = {
  id: string;
  text: LStr;
  status: "proposed" | "analyzed" | "closed";
  impactReq: string[];
  impactRuns: string[];
  maskRev: string;
};

export type QualRow = {
  group: string;
  method: LStrLike;
  cond: LStrLike;
  duration: string;
  samples: string;
  status: "pass" | "pending" | "fail" | "waiver";
  note?: LStr;
};

export type CorrParam = { key: string; unit: string; tempCoef: number; tolerance: number };

export type Lot = {
  id: string;
  wafers: number;
  yieldPct: number;
  bins: { good: number; retest: number; fail1: number; fail2: number };
  spc: number[]; // key parametric per-lot
  excursion?: LStr; // rule violation description (§13.2 — notification only)
  disposition?: "held" | "released" | "mrb_reviewed";
};

export type AsicTemplate = {
  id: string;
  name: LStr;
  grade: "G2" | "G1" | "G0"; // AEC-Q100 target grade (§5, §12)
  missionSlug: "risc32" | "uart_tx" | "fifo_sync"; // reused EDA-training digital mission (stage 4)
  color: string;
  blocks: ArchBlock[];
  specs: Spec[];
  corrParams: CorrParam[];
  requirements: Requirement[];
  verItems: VerItem[];
  options: ProcessOption[];
  risks: Risk[];
  milestones: Milestone[];
  ecos: Eco[];
  qual: QualRow[];
  lots: Lot[];
  nre: { item: LStr; amount: LStrLike }[];
};

const T = (grade: "G2" | "G1" | "G0", temps: [number, number]) => ({ grade, temps });

// AEC-Q100 grade → temperature window used by the qualification condition
// strings (§12: conditions derive from the target grade, never hardcoded pass).
export const GRADE_TEMP: Record<"G2" | "G1" | "G0", [number, number]> = { G2: [-40, 105], G1: [-40, 125], G0: [-40, 150] };
void T;

export const ASIC_TEMPLATES: AsicTemplate[] = [
  {
    id: "cap_afe",
    name: L("Template A — 정전용량 센서 AFE/SoC", "Template A — Capacitive sensor AFE/SoC", "Template A — 静電容量センサー AFE/SoC"),
    grade: "G2",
    missionSlug: "risc32",
    color: "#22d3ee",
    blocks: [
      { key: "electrode", label: "Electrode matrix + shield/guard", kind: "sensor" },
      { key: "cdc", label: "CDC front end (charge transfer)", kind: "analog" },
      { key: "scan", label: "MUX + 16ch scan controller", kind: "digital" },
      { key: "afe", label: "PGA / filter / ADC", kind: "mixed" },
      { key: "base", label: "Baseline tracking", kind: "digital" },
      { key: "temp", label: "Temp/env compensation", kind: "mixed" },
      { key: "feat", label: "Touch/proximity feature extraction", kind: "digital" },
      { key: "mcu", label: "MCU/DSP + SRAM/OTP", kind: "digital" },
      { key: "spi", label: "SPI / UART", kind: "io" },
      { key: "pmu", label: "Power/reset/diag/test mode", kind: "power" },
    ],
    specs: [
      { key: "channels", value: 16, unit: "ch", tol: "—" },
      { key: "scan", value: 200, unit: "Hz", tol: "±10%" },
      { key: "enob", value: 10.5, unit: "bit", tol: "min 10" },
      { key: "hover", value: 20, unit: "mm", tol: "glove ≥95%" },
      { key: "power", value: 1.8, unit: "mW", tol: "max" },
      { key: "wake", value: 12, unit: "ms", tol: "max" },
    ],
    corrParams: [
      { key: "offset", unit: "LSB", tempCoef: 0.0018, tolerance: 0.04 },
      { key: "sensitivity", unit: "count/mm", tempCoef: -0.0011, tolerance: 0.05 },
      { key: "scan_period", unit: "µs", tempCoef: 0.0004, tolerance: 0.02 },
    ],
    requirements: [
      { id: "REQ-A101", text: L("장갑 착용 상태에서 20 mm hover 검출 확률 ≥ 95 %", "≥ 95 % hover detection probability at 20 mm with glove on", "手袋着用状態で20 mmホバー検出確率 ≥ 95 %"), source: L("고객 회의 2026-06-12", "Customer meeting 2026-06-12", "顧客会議 2026-06-12"), category: "function", priority: "must", status: "approved", method: "bench", verId: "VER-A01" },
      { id: "REQ-A102", text: L("16채널 동시 스캔, 스캔 레이트 200 Hz", "16-channel simultaneous scan at 200 Hz scan rate", "16チャネル同時スキャン、スキャンレート200 Hz"), source: L("시스템 사양서 v2.1", "System spec v2.1", "システム仕様書 v2.1"), category: "function", priority: "must", status: "approved", method: "rtl-sim", verId: "VER-A02" },
      { id: "REQ-A103", text: L("AEC-Q100 Grade 2 (-40~+105 °C) 동작 보장", "AEC-Q100 Grade 2 (-40~+105 °C) operation guaranteed", "AEC-Q100 Grade 2(-40~+105 ℃)動作保証"), source: L("품질 요구서", "Quality requirements", "品質要求書"), category: "environment", priority: "must", status: "approved", method: "qualification", verId: "VER-A03" },
      { id: "REQ-A104", text: L("스캔 동작 전력 ≤ 1.8 mW", "Scan-mode power ≤ 1.8 mW", "スキャン動作電力 ≤ 1.8 mW"), source: L("시스템 사양서 v2.1", "System spec v2.1", "システム仕様書 v2.1"), category: "quality", priority: "must", status: "approved", method: "spice+synth", verId: "VER-A04" },
      { id: "REQ-A105", text: L("채널 간 초기 오정합 ≤ 2 % (사전 가정치)", "Initial channel-to-channel mismatch ≤ 2 % (assumption)", "チャネル間初期ミスマッチ ≤ 2 %(前提値)"), source: L("선행 칩 측정치", "Previous-silicon measurement", "先行チップ実測値"), category: "quality", priority: "should", status: "provisional", method: "monte-carlo", verId: "VER-A05", assumptionId: "ASM-011" },
      { id: "REQ-A106", text: L("전극 단락/개방 진단 검출", "Electrode short/open diagnostic detection", "電極短絡/断線の診断検出"), source: L("고객 품질 부서", "Customer quality department", "顧客品質部門"), category: "safety", priority: "must", status: "draft", method: "fault-campaign", verId: "" },
      { id: "REQ-A107", text: L("SPI 10 MHz 검증", "SPI 10 MHz verification", "SPI 10 MHz検証"), source: L("인터페이스 사양 r1", "Interface spec r1", "インタフェース仕様 r1"), category: "interface", priority: "must", status: "superseded", method: "rtl-sim", verId: "VER-A07" },
      { id: "REQ-A108", text: L("SPI 20 MHz 검증 (REQ-A107 대체)", "SPI 20 MHz verification (supersedes REQ-A107)", "SPI 20 MHz検証(REQ-A107を置換)"), source: L("인터페이스 사양 r2", "Interface spec r2", "インタフェース仕様 r2"), category: "interface", priority: "must", status: "approved", method: "rtl-sim", verId: "VER-A07" },
    ],
    verItems: [
      { id: "VER-A01", reqId: "REQ-A101", method: "bench", env: L("ES 샘플 + 거리 스테이지 (5/10/15/20 mm)", "ES samples + distance stage (5/10/15/20 mm)", "ESサンプル+距離ステージ(5/10/15/20 mm)"), target: 0.95, owner: "Product/Test Engineer", done: true },
      { id: "VER-A02", reqId: "REQ-A102", method: "rtl-sim", env: "RTL regression (scan controller)", target: 1.0, owner: "Digital Designer", done: true },
      { id: "VER-A03", reqId: "REQ-A103", method: "qualification", env: L("AEC-Q100 매트릭스 (S07)", "AEC-Q100 matrix (S07)", "AEC-Q100マトリクス(S07)"), target: 1.0, owner: "Quality/Reliability", done: false },
      { id: "VER-A04", reqId: "REQ-A104", method: "spice+synth", env: L("전력 추정: 합성 게이트 수 + SPICE", "Power estimate: synthesized gate count + SPICE", "電力推定: 合成ゲート数+SPICE"), target: 1.0, owner: "Analog Designer", done: true },
      { id: "VER-A05", reqId: "REQ-A105", method: "monte-carlo", env: L("MC 500 pts (공정 코너)", "MC 500 pts (process corners)", "MC 500 pts(プロセスコーナー)"), target: 0.98, owner: "Analog Designer", done: true },
      { id: "VER-A07", reqId: "REQ-A108", method: "rtl-sim", env: L("SPI 마스터 모델 20 MHz", "SPI master model 20 MHz", "SPIマスターモデル 20 MHz"), target: 1.0, owner: "Verification Engineer", done: true },
    ],
    options: [
      { id: "OPT-1", foundry: "FAB-A (alias)", node: "180 nm BCD", pkg: "QFN-32", risk: "low", leadWeeks: [10, 14], nreIdx: 1.0 },
      { id: "OPT-2", foundry: "FAB-B (alias)", node: "110 nm CMOS", pkg: "WLCSP-24", risk: "medium", leadWeeks: [14, 20], nreIdx: 1.45 },
      { id: "OPT-3", foundry: "FAB-C (alias)", node: "180 nm CMOS", pkg: "LQFP-48", risk: "low", leadWeeks: [8, 12], nreIdx: 0.9 },
    ],
    risks: [
      { id: "RSK-01", text: L("장갑 유전율 편차 → hover 마진 감소", "Glove permittivity spread → reduced hover margin", "手袋誘電率のばらつき → ホバーマージン低減"), sev: "high", owner: "System Architect", mitigation: L("field-sim GOLD 시나리오로 마진 검증 + 게인 ECO 준비", "verify margin with field-sim GOLD scenarios + prepare gain ECO", "field-sim GOLDシナリオでマージン検証+ゲインECO準備") },
      { id: "RSK-02", text: L("16ch MUX 누설 전류 → 스캔 노이즈", "16ch MUX leakage current → scan noise", "16ch MUXリーク電流 → スキャンノイズ"), sev: "medium", owner: "Analog Designer", mitigation: L("corner 시뮬레이션 + 쉴드 구동", "corner simulation + shield driving", "コーナーシミュレーション+シールド駆動") },
      { id: "RSK-03", text: L("WLCSP 리플로우 스토넬링", "WLCSP reflow beading", "WLCSPリフロービーディング"), sev: "low", owner: "Physical Designer", mitigation: L("패키지 후보 2·3 비교 평가", "compare package candidates 2 and 3", "パッケージ候補2・3の比較評価") },
    ],
    milestones: [
      { id: "M1", text: L("요구 동결 (baseline)", "Requirements freeze (baseline)", "要求凍結(ベースライン)"), due: "2026-07-10", status: "done" },
      { id: "M2", text: L("아키텍처 승인", "Architecture approval", "アーキテクチャ承認"), due: "2026-08-14", status: "done" },
      { id: "M3", text: L("디자인 freeze / TAPEOUT", "Design freeze / TAPEOUT", "デザインフリーズ/TAPEOUT"), due: "2026-10-30", status: "open" },
      { id: "M4", text: L("ES 샘플 입고 · 평가 착수", "ES samples received · evaluation starts", "ESサンプル入荷・評価開始"), due: "2027-01-15", status: "open" },
      { id: "M5", text: L("CS · 신뢰성 완료", "CS · reliability complete", "CS・信頼性完了"), due: "2027-04-30", status: "open" },
      { id: "M6", text: L("개발 완료 (Release)", "Development complete (Release)", "開発完了(リリース)"), due: "2027-05-30", status: "open" },
    ],
    ecos: [
      { id: "CR-001", text: L("스캔 클록 게이팅 추가 — REQ-A104 전력 마진 확보", "Add scan clock gating — secure REQ-A104 power margin", "スキャンクロックゲーティング追加 — REQ-A104電力マージン確保"), status: "closed", impactReq: ["REQ-A104"], impactRuns: ["synth"], maskRev: "r3 → r4" },
      { id: "CR-002", text: L("CDC 리셋 타이밍 수정 (first-silicon 관찰)", "Fix CDC reset timing (first-silicon observation)", "CDCリセットタイミング修正(first-silicon観察)"), status: "proposed", impactReq: ["REQ-A102"], impactRuns: ["sim", "synth"], maskRev: "r4 → r5" },
    ],
    qual: [
      { group: "TC", method: "Temp Cycling JESD22-A104", cond: "-40 ↔ +105 °C", duration: "1,000 cy", samples: "3 lot × 77", status: "pass" },
      { group: "TH", method: "Temp/Humidity Bias 85/85", cond: L("85 °C / 85 %RH, 바이어스 인가", "85 °C / 85 %RH, biased", "85 ℃/85 %RH、バイアス印加"), duration: "1,000 h", samples: "3 lot × 77", status: "pass" },
      { group: "HTSL", method: "High Temp Storage", cond: L("150 °C (passivation 후)", "150 °C (after passivation)", "150 ℃(パッシベーション後)"), duration: "1,000 h", samples: "3 lot × 77", status: "pass" },
      { group: "HAST", method: "Unbiased HAST", cond: "130 °C / 85 %RH", duration: "96 h", samples: "2 lot × 77", status: "pending" },
      { group: "TCBIAS", method: "Power Temp Cycling", cond: L("-40 ↔ +105 °C, 동작 bias", "-40 ↔ +105 °C, operating bias", "-40 ↔ +105 ℃、動作バイアス"), duration: "500 cy", samples: "2 lot × 77", status: "pending" },
      { group: "ESD", method: "HBM / CDM", cond: "HBM ≥ 2 kV · CDM ≥ 500 V", duration: "—", samples: "3 lot × 6", status: "pass" },
      { group: "LU", method: "Latch-Up", cond: "+/- 100 mA, 105 °C", duration: "—", samples: "3 lot × 6", status: "pass" },
      { group: "FG", method: L("Failure Grid / 진단 커버리지", "Failure Grid / diagnostic coverage", "Failure Grid/診断カバレッジ"), cond: L("전극 단락·개방 주입", "electrode short/open injection", "電極短絡・断線注入"), duration: "—", samples: "1 lot × 30", status: "fail", note: L("진단 커버리지 미달 (REQ-A106 관련) — CAPA 진행", "Diagnostic coverage shortfall (REQ-A106) — CAPA in progress", "診断カバレッジ未達(REQ-A106関連)— CAPA進行中") },
    ],
    lots: [
      { id: "PL-2601", wafers: 6, yieldPct: 91.2, bins: { good: 91, retest: 4, fail1: 3, fail2: 2 }, spc: [1.02, 0.99, 1.0, 1.01, 0.98], disposition: "released" },
      { id: "PL-2602", wafers: 6, yieldPct: 92.8, bins: { good: 93, retest: 3, fail1: 2, fail2: 2 }, spc: [1.0, 1.01, 0.99, 1.0, 1.02], disposition: "released" },
      { id: "PL-2603", wafers: 8, yieldPct: 89.5, bins: { good: 90, retest: 4, fail1: 4, fail2: 2 }, spc: [0.98, 0.97, 1.0, 0.99, 1.01], disposition: "released" },
      { id: "PL-2604", wafers: 8, yieldPct: 78.4, bins: { good: 78, retest: 6, fail1: 10, fail2: 6 }, spc: [1.06, 1.12, 1.18, 1.09, 1.04], excursion: L("SPC rule 2×σ 초과 3점 연속 (offset drift) — 공정 코너 이탈 의심", "SPC rule: 3 consecutive points beyond 2×σ (offset drift) — process corner excursion suspected", "SPCルール2×σ超過3点連続(offsetドリフト)— プロセスコーナー逸脱の疑い"), disposition: "held" },
      { id: "PL-2605", wafers: 8, yieldPct: 93.7, bins: { good: 94, retest: 2, fail1: 2, fail2: 2 }, spc: [1.0, 0.99, 1.01, 1.0, 0.99], disposition: "released" },
      { id: "PL-2606", wafers: 12, yieldPct: 94.1, bins: { good: 94, retest: 3, fail1: 2, fail2: 1 }, spc: [0.99, 1.0, 1.0, 1.01, 1.0], disposition: "released" },
    ],
    nre: [
      { item: L("마스크 세트", "Mask set", "マスクセット"), amount: L("기준 지수 1.00 (금액 마스킹)", "reference index 1.00 (amount masked)", "基準指数1.00(金額マスキング)") },
      { item: L("설계·검증 인력 (12 MM)", "Design & verification effort (12 MM)", "設計・検証工数(12 MM)"), amount: L("기준 지수 1.00", "reference index 1.00", "基準指数1.00") },
      { item: L("테스트 프로그램 + ATE 보드", "Test program + ATE board", "テストプログラム+ATEボード"), amount: L("기준 지수 0.35", "reference index 0.35", "基準指数0.35") },
      { item: L("신뢰성 시험 (Grade 2 매트릭스)", "Reliability test (Grade 2 matrix)", "信頼性試験(Grade 2マトリクス)"), amount: L("기준 지수 0.6", "reference index 0.6", "基準指数0.6") },
    ],
  },
  {
    id: "current_sensor",
    name: L("Template B — 전류 센서 신호조절 ASIC", "Template B — Current sensor signal-conditioning ASIC", "Template B — 電流センサー信号調整ASIC"),
    grade: "G0",
    missionSlug: "uart_tx",
    color: "#f97316",
    blocks: [
      { key: "gmr", label: "GMR element (behavioral)", kind: "sensor" },
      { key: "bias", label: "Sensor bias / activation", kind: "analog" },
      { key: "lna", label: "Low-noise amp + offset cancel", kind: "analog" },
      { key: "tc", label: "Temp compensation + trim", kind: "mixed" },
      { key: "clamp", label: "Output clamp / fail-safe", kind: "analog" },
      { key: "drv", label: "Analog output driver", kind: "io" },
      { key: "diag", label: "Diagnostic", kind: "digital" },
      { key: "trim", label: "Digital trim interface", kind: "io" },
    ],
    specs: [
      { key: "sens", value: 26.4, unit: "mV/A", tol: "±1%" },
      { key: "lin", value: 0.8, unit: "%FS", tol: "max" },
      { key: "offset", value: 8, unit: "mV", tol: "max" },
      { key: "bw", value: 120, unit: "kHz", tol: "min" },
      { key: "range", value: 100, unit: "A", tol: "±100" },
    ],
    corrParams: [
      { key: "sens", unit: "mV/A", tempCoef: 0.0007, tolerance: 0.03 },
      { key: "offset", unit: "mV", tempCoef: 0.0022, tolerance: 0.05 },
      { key: "bw", unit: "kHz", tempCoef: -0.0006, tolerance: 0.04 },
    ],
    requirements: [
      { id: "REQ-B101", text: L("정비례 출력 26.4 mV/A (100 A 범위)", "Linear output 26.4 mV/A (100 A range)", "比例出力26.4 mV/A(100 Aレンジ)"), source: L("고객 사양서 r3", "Customer spec r3", "顧客仕様書 r3"), category: "function", priority: "must", status: "approved", method: "bench", verId: "VER-B01" },
      { id: "REQ-B102", text: L("AEC-Q100 Grade 0 (-40~+150 °C)", "AEC-Q100 Grade 0 (-40~+150 °C)", "AEC-Q100 Grade 0(-40~+150 ℃)"), source: L("품질 요구서", "Quality requirements", "品質要求書"), category: "environment", priority: "must", status: "approved", method: "qualification", verId: "VER-B02" },
      { id: "REQ-B103", text: L("폐루프 안정도: 위상 마진 ≥ 45°", "Closed-loop stability: phase margin ≥ 45°", "閉ループ安定度: 位相マージン ≥ 45°"), source: L("회로 검토서", "Circuit review", "回路検討書"), category: "function", priority: "must", status: "approved", method: "spice+synth", verId: "VER-B03" },
      { id: "REQ-B104", text: L("외부 자계 교란 200 mT에서 오출력 ≤ 1 %FS", "Output error ≤ 1 %FS under 200 mT external field disturbance", "外部磁界擾乱200 mTで誤出力 ≤ 1 %FS"), source: L("고객 EM 시험 결과", "Customer EMC test results", "顧客EM試験結果"), category: "safety", priority: "should", status: "provisional", method: "bench", verId: "VER-B04", assumptionId: "ASM-021" },
      { id: "REQ-B105", text: L("fail-safe: 전원 단락 시 출력 클램프", "Fail-safe: output clamp on power short", "フェイルセーフ: 電源短絡時に出力クランプ"), source: L("안전 요구서", "Safety requirements", "安全要求書"), category: "safety", priority: "must", status: "approved", method: "fault-campaign", verId: "VER-B05" },
    ],
    verItems: [
      { id: "VER-B01", reqId: "REQ-B101", method: "bench", env: L("ES 샘플 + 정밀 전류원", "ES samples + precision current source", "ESサンプル+精密電流源"), target: 0.99, owner: "Product/Test Engineer", done: true },
      { id: "VER-B02", reqId: "REQ-B102", method: "qualification", env: L("AEC-Q100 매트릭스 (S07)", "AEC-Q100 matrix (S07)", "AEC-Q100マトリクス(S07)"), target: 1.0, owner: "Quality/Reliability", done: false },
      { id: "VER-B03", reqId: "REQ-B103", method: "spice+synth", env: L("AC/TS 폐루프 해석", "AC/TS closed-loop analysis", "AC/TS閉ループ解析"), target: 1.0, owner: "Analog Designer", done: true },
      { id: "VER-B04", reqId: "REQ-B104", method: "bench", env: L("헤름홀츠 코일 교란 시험", "Helmholtz coil disturbance test", "ヘルムホルツコイル擾乱試験"), target: 0.99, owner: "Product/Test Engineer", done: false },
      { id: "VER-B05", reqId: "REQ-B105", method: "fault-campaign", env: L("fault 주입 캠페인", "fault injection campaign", "フォルト注入キャンペーン"), target: 1.0, owner: "Verification Engineer", done: true },
    ],
    options: [
      { id: "OPT-1", foundry: "FAB-D (alias)", node: "180 nm BCD", pkg: "SOIC-8", risk: "low", leadWeeks: [9, 13], nreIdx: 0.85 },
      { id: "OPT-2", foundry: "FAB-A (alias)", node: "180 nm BCD", pkg: "TSSOP-16", risk: "medium", leadWeeks: [12, 16], nreIdx: 1.1 },
    ],
    risks: [
      { id: "RSK-11", text: L("GMR 온도 드리프트 → trim 범위 초과", "GMR temperature drift → trim range exceeded", "GMR温度ドリフト → トリム範囲超過"), sev: "high", owner: "Analog Designer", mitigation: L("2점 trim + 보상 계수 산포 검증", "2-point trim + verify compensation coefficient spread", "2点トリム+補正係数のばらつき検証") },
      { id: "RSK-12", text: L("Grade 0 시험 샘플 수 확보 지연", "Delay securing the Grade 0 test sample count", "Grade 0試験サンプル数確保の遅れ"), sev: "medium", owner: "Program Manager", mitigation: L("ES/CS lot 계획 조기 확정", "fix the ES/CS lot plan early", "ES/CSロット計画の前倒し確定") },
    ],
    milestones: [
      { id: "M1", text: L("요구 동결", "Requirements freeze", "要求凍結"), due: "2026-08-28", status: "done" },
      { id: "M2", text: L("아키텍처 승인", "Architecture approval", "アーキテクチャ承認"), due: "2026-09-25", status: "done" },
      { id: "M3", text: L("디자인 freeze / TAPEOUT", "Design freeze / TAPEOUT", "デザインフリーズ/TAPEOUT"), due: "2026-12-18", status: "open" },
      { id: "M4", text: L("ES 평가", "ES evaluation", "ES評価"), due: "2027-03-12", status: "open" },
      { id: "M5", text: L("신뢰성 완료 (Grade 0)", "Reliability complete (Grade 0)", "信頼性完了(Grade 0)"), due: "2027-07-30", status: "open" },
      { id: "M6", text: L("개발 완료", "Development complete", "開発完了"), due: "2027-08-27", status: "open" },
    ],
    ecos: [{ id: "CR-101", text: L("오프셋 캔슬 스위치 사이즈 증가 (드리프트 대응)", "Increase offset-cancel switch size (drift countermeasure)", "オフセットキャンセルスイッチのサイズ増大(ドリフト対応)"), status: "analyzed", impactReq: ["REQ-B101"], impactRuns: ["sim"], maskRev: "r2 → r3" }],
    qual: [
      { group: "TC", method: "Temp Cycling", cond: "-40 ↔ +150 °C", duration: "2,000 cy", samples: "6 lot × 77", status: "pending" },
      { group: "TH", method: "THB 85/85", cond: "85 °C / 85 %RH", duration: "1,000 h", samples: "3 lot × 77", status: "pass" },
      { group: "HTSL", method: "High Temp Storage", cond: "170 °C", duration: "1,000 h", samples: "3 lot × 77", status: "pass" },
      { group: "HTRB", method: "High Temp Reverse Bias", cond: L("150 °C, 최대 역전압", "150 °C, max reverse voltage", "150 ℃、最大逆電圧"), duration: "1,000 h", samples: "3 lot × 77", status: "pending" },
      { group: "ESD", method: "HBM / CDM", cond: "HBM ≥ 2 kV · CDM ≥ 500 V", duration: "—", samples: "3 lot × 6", status: "pass" },
      { group: "LU", method: "Latch-Up", cond: "±200 mA, 150 °C", duration: "—", samples: "3 lot × 6", status: "pass" },
    ],
    lots: [
      { id: "PL-3501", wafers: 5, yieldPct: 94.2, bins: { good: 94, retest: 3, fail1: 2, fail2: 1 }, spc: [1.0, 1.0, 0.99, 1.01, 1.0], disposition: "released" },
      { id: "PL-3502", wafers: 5, yieldPct: 95.1, bins: { good: 95, retest: 2, fail1: 2, fail2: 1 }, spc: [1.01, 1.0, 1.0, 0.99, 1.0], disposition: "released" },
      { id: "PL-3503", wafers: 10, yieldPct: 93.4, bins: { good: 93, retest: 3, fail1: 3, fail2: 1 }, spc: [0.99, 1.0, 1.0, 1.0, 1.01], disposition: "released" },
    ],
    nre: [
      { item: L("마스크 세트", "Mask set", "マスクセット"), amount: L("기준 지수 0.8 (금액 마스킹)", "reference index 0.8 (amount masked)", "基準指数0.8(金額マスキング)") },
      { item: L("설계·검증 인력 (8 MM)", "Design & verification effort (8 MM)", "設計・検証工数(8 MM)"), amount: L("기준 지수 0.7", "reference index 0.7", "基準指数0.7") },
      { item: L("신뢰성 시험 (Grade 0)", "Reliability test (Grade 0)", "信頼性試験(Grade 0)"), amount: L("기준 지수 1.2", "reference index 1.2", "基準指数1.2") },
    ],
  },
  {
    id: "motor_ripple",
    name: L("Template C — DC 모터 전류·전압·리플 검출 ASIC", "Template C — DC motor current/voltage/ripple detection ASIC", "Template C — DCモーター電流・電圧・リプル検出ASIC"),
    grade: "G1",
    missionSlug: "uart_tx",
    color: "#a78bfa",
    blocks: [
      { key: "prot", label: "-10~+60 V protection / level shift", kind: "power" },
      { key: "vsense", label: "Terminal voltage sensing", kind: "analog" },
      { key: "ripple", label: "Ripple extraction + filter", kind: "mixed" },
      { key: "cmp", label: "Comparator / pulse gen", kind: "mixed" },
      { key: "uart", label: "UART single-wire I/F", kind: "io" },
      { key: "pwr", label: "Power/reset/diag/protection", kind: "power" },
    ],
    specs: [
      { key: "vin", value: 60, unit: "V", tol: "-10 ~ +60" },
      { key: "ripple", value: 45, unit: "mA", tol: "min pk" },
      { key: "jitter", value: 2, unit: "µs", tol: "max" },
      { key: "baud", value: 10.4, unit: "kbps", tol: "single-wire" },
    ],
    corrParams: [
      { key: "thresh", unit: "mA", tempCoef: 0.0012, tolerance: 0.05 },
      { key: "pulse_w", unit: "µs", tempCoef: 0.0008, tolerance: 0.03 },
    ],
    requirements: [
      { id: "REQ-C101", text: L("-10 ~ +60 V 입력에서 보호·정상 동작", "Protected normal operation across -10 ~ +60 V input", "-10 ~ +60 V入力で保護・正常動作"), source: L("고객 사양서 r5", "Customer spec r5", "顧客仕様書 r5"), category: "function", priority: "must", status: "approved", method: "bench", verId: "VER-C01" },
      { id: "REQ-C102", text: L("정격 전류 리플 45 mA(pk) 검출 · 펄스 출력", "Detect rated current ripple 45 mA(pk) · pulse output", "定格電流リプル45 mA(pk)検出・パルス出力"), source: L("고객 사양서 r5", "Customer spec r5", "顧客仕様書 r5"), category: "function", priority: "must", status: "approved", method: "bench", verId: "VER-C02" },
      { id: "REQ-C103", text: L("리플 펄스와 모터 정위치 상관 오차 ≤ 2 %", "Ripple-pulse vs motor position correlation error ≤ 2 %", "リプルパルスとモーター位置の相関誤差 ≤ 2 %"), source: L("시스템 검토서", "System review", "システム検討書"), category: "quality", priority: "must", status: "approved", method: "bench", verId: "VER-C03" },
      { id: "REQ-C104", text: L("역접속 / 부성 과도에서 무손상", "No damage under reverse connection / negative transient", "逆接続/負性過渡で無損傷"), source: L("안전 요구서", "Safety requirements", "安全要求書"), category: "safety", priority: "must", status: "approved", method: "fault-campaign", verId: "VER-C04" },
      { id: "REQ-C105", text: L("AEC-Q100 Grade 1 (-40~+125 °C)", "AEC-Q100 Grade 1 (-40~+125 °C)", "AEC-Q100 Grade 1(-40~+125 ℃)"), source: L("품질 요구서", "Quality requirements", "品質要求書"), category: "environment", priority: "must", status: "provisional", method: "qualification", verId: "VER-C05", assumptionId: "ASM-031" },
    ],
    verItems: [
      { id: "VER-C01", reqId: "REQ-C101", method: "bench", env: L("전원 과도 시험기", "power transient tester", "電源過渡試験機"), target: 1.0, owner: "Product/Test Engineer", done: true },
      { id: "VER-C02", reqId: "REQ-C102", method: "bench", env: L("모터 플랜트 리플레이", "motor plant replay", "モータープラント再生"), target: 0.98, owner: "Product/Test Engineer", done: true },
      { id: "VER-C03", reqId: "REQ-C103", method: "bench", env: L("엔코더 동시 계측", "simultaneous encoder measurement", "エンコーダ同時計測"), target: 0.98, owner: "System Architect", done: false },
      { id: "VER-C04", reqId: "REQ-C104", method: "fault-campaign", env: L("fault 주입 캠페인", "fault injection campaign", "フォルト注入キャンペーン"), target: 1.0, owner: "Verification Engineer", done: true },
      { id: "VER-C05", reqId: "REQ-C105", method: "qualification", env: L("AEC-Q100 매트릭스 (S07)", "AEC-Q100 matrix (S07)", "AEC-Q100マトリクス(S07)"), target: 1.0, owner: "Quality/Reliability", done: false },
    ],
    options: [
      { id: "OPT-1", foundry: "FAB-A (alias)", node: "180 nm BCD 60 V", pkg: "SOP-8", risk: "low", leadWeeks: [10, 14], nreIdx: 0.95 },
      { id: "OPT-2", foundry: "FAB-D (alias)", node: "130 nm BCD 70 V", pkg: "TSSOP-10", risk: "medium", leadWeeks: [13, 18], nreIdx: 1.3 },
    ],
    risks: [
      { id: "RSK-21", text: L("60 V 입력 보호 소자의 ESOA 마진", "ESOA margin of the 60 V input protection element", "60 V入力保護素子のESOAマージン"), sev: "high", owner: "Analog Designer", mitigation: L("로드라인 해석 + 실장 보호 소자 협의", "load-line analysis + align on the onboard protection element", "ロードライン解析+実装保護素子の協議") },
      { id: "RSK-22", text: L("리플 S/N이 하네스 길이에 따라 열화", "Ripple S/N degrades with harness length", "リプルS/Nがハーネス長により劣化"), sev: "medium", owner: "System Architect", mitigation: L("차동 감지 검토, 차량 배선 모델 반영", "study differential sensing; reflect the vehicle wiring model", "差動検出の検討、車両配線モデルの反映") },
    ],
    milestones: [
      { id: "M1", text: L("요구 동결", "Requirements freeze", "要求凍結"), due: "2026-09-11", status: "done" },
      { id: "M2", text: L("아키텍처 승인", "Architecture approval", "アーキテクチャ承認"), due: "2026-10-23", status: "open" },
      { id: "M3", text: L("TAPEOUT", "TAPEOUT", "TAPEOUT"), due: "2027-01-29", status: "open" },
      { id: "M4", text: L("ES 평가", "ES evaluation", "ES評価"), due: "2027-04-23", status: "open" },
      { id: "M5", text: L("신뢰성 완료", "Reliability complete", "信頼性完了"), due: "2027-08-27", status: "open" },
      { id: "M6", text: L("개발 완료", "Development complete", "開発完了"), due: "2027-09-24", status: "open" },
    ],
    ecos: [],
    qual: [
      { group: "TC", method: "Temp Cycling", cond: "-40 ↔ +125 °C", duration: "1,000 cy", samples: "3 lot × 77", status: "pass" },
      { group: "TH", method: "THB 85/85", cond: "85 °C / 85 %RH", duration: "1,000 h", samples: "3 lot × 77", status: "pending" },
      { group: "HTSL", method: "High Temp Storage", cond: "150 °C", duration: "1,000 h", samples: "3 lot × 77", status: "pass" },
      { group: "ESD", method: "HBM / CDM", cond: "HBM ≥ 2 kV · CDM ≥ 500 V", duration: "—", samples: "3 lot × 6", status: "pass" },
      { group: "LU", method: "Latch-Up", cond: "±100 mA, 125 °C", duration: "—", samples: "3 lot × 6", status: "pass" },
      { group: "VF", method: "Vibration / Mechanical Shock", cond: L("차량 규격 프로파일", "automotive standard profile", "車載規格プロファイル"), duration: "—", samples: "2 lot × 15", status: "pending" },
    ],
    lots: [
      { id: "PL-4201", wafers: 4, yieldPct: 92.5, bins: { good: 93, retest: 3, fail1: 3, fail2: 1 }, spc: [1.0, 1.01, 0.99, 1.0, 1.0], disposition: "released" },
      { id: "PL-4202", wafers: 4, yieldPct: 91.8, bins: { good: 92, retest: 4, fail1: 3, fail2: 1 }, spc: [1.0, 0.99, 1.0, 1.02, 1.0], disposition: "released" },
    ],
    nre: [
      { item: L("마스크 세트", "Mask set", "マスクセット"), amount: L("기준 지수 0.9 (금액 마스킹)", "reference index 0.9 (amount masked)", "基準指数0.9(金額マスキング)") },
      { item: L("설계·검증 인력 (6 MM)", "Design & verification effort (6 MM)", "設計・検証工数(6 MM)"), amount: L("기준 지수 0.55", "reference index 0.55", "基準指数0.55") },
      { item: L("신뢰성 시험 (Grade 1)", "Reliability test (Grade 1)", "信頼性試験(Grade 1)"), amount: L("기준 지수 0.8", "reference index 0.8", "基準指数0.8") },
    ],
  },
  {
    id: "env_sensor",
    name: L("Template D — 습도·기압·지자기 센서 신호조절 ASIC", "Template D — Humidity/pressure/geomagnetic sensor conditioning ASIC", "Template D — 湿度・気圧・地磁気センサー信号調整ASIC"),
    grade: "G1",
    missionSlug: "fifo_sync",
    color: "#34d399",
    blocks: [
      { key: "act", label: "Sensor activation / bias", kind: "analog" },
      { key: "amp", label: "Analog amp / filter", kind: "analog" },
      { key: "adc", label: "ADC", kind: "mixed" },
      { key: "cal", label: "Calibration / temp comp", kind: "digital" },
      { key: "calc", label: "Digital calc + memory", kind: "digital" },
      { key: "if", label: "I2C / SPI output", kind: "io" },
    ],
    specs: [
      { key: "rh", value: 2.0, unit: "%RH", tol: "max" },
      { key: "press", value: 0.6, unit: "hPa", tol: "max" },
      { key: "mag", value: 0.15, unit: "µT", tol: "rms max" },
      { key: "odr", value: 25, unit: "Hz", tol: "±5%" },
    ],
    corrParams: [
      { key: "rh_offset", unit: "%RH", tempCoef: 0.0015, tolerance: 0.04 },
      { key: "press_sens", unit: "cnt/hPa", tempCoef: -0.0009, tolerance: 0.03 },
    ],
    requirements: [
      { id: "REQ-D101", text: L("습도 ±2.0 %RH (25 °C, 보정 후)", "Humidity ±2.0 %RH (25 °C, after calibration)", "湿度 ±2.0 %RH(25 ℃、校正後)"), source: L("고객 사양서 r2", "Customer spec r2", "顧客仕様書 r2"), category: "function", priority: "must", status: "approved", method: "bench", verId: "VER-D01" },
      { id: "REQ-D102", text: L("기압 ±0.6 hPa (-20~+85 °C)", "Pressure ±0.6 hPa (-20~+85 °C)", "気圧 ±0.6 hPa(-20~+85 ℃)"), source: L("고객 사양서 r2", "Customer spec r2", "顧客仕様書 r2"), category: "function", priority: "must", status: "approved", method: "bench", verId: "VER-D02" },
      { id: "REQ-D103", text: L("보정 계수 OTP 기록 · 메모리 고장 검출 (CRC)", "Calibration coefficients to OTP · memory fault detection (CRC)", "校正係数のOTP記録・メモリ故障検出(CRC)"), source: L("품질 요구서", "Quality requirements", "品質要求書"), category: "safety", priority: "should", status: "approved", method: "fault-campaign", verId: "VER-D03" },
      { id: "REQ-D104", text: L("I2C 400 kHz / SPI 1 MHz 인터페이스 회귀", "I2C 400 kHz / SPI 1 MHz interface regression", "I2C 400 kHz/SPI 1 MHzインタフェース回帰"), source: L("인터페이스 사양", "Interface spec", "インタフェース仕様"), category: "interface", priority: "must", status: "approved", method: "rtl-sim", verId: "VER-D04" },
      { id: "REQ-D105", text: L("챔버 ES 실측과 시뮬레이션 상관 R² ≥ 0.95", "Chamber ES measurement vs simulation correlation R² ≥ 0.95", "チャンバーES実測とシミュレーションの相関 R² ≥ 0.95"), source: L("검증 계획서", "Verification plan", "検証計画書"), category: "quality", priority: "should", status: "provisional", method: "monte-carlo", verId: "VER-D05", assumptionId: "ASM-041" },
    ],
    verItems: [
      { id: "VER-D01", reqId: "REQ-D101", method: "bench", env: L("항온항습 챔버", "temperature/humidity chamber", "恒温恒湿チャンバー"), target: 0.95, owner: "Product/Test Engineer", done: true },
      { id: "VER-D02", reqId: "REQ-D102", method: "bench", env: L("압력 캘리브레이터", "pressure calibrator", "圧力キャリブレータ"), target: 0.95, owner: "Product/Test Engineer", done: true },
      { id: "VER-D03", reqId: "REQ-D103", method: "fault-campaign", env: L("메모리 비트 고장 주입", "memory bit fault injection", "メモリビット故障注入"), target: 1.0, owner: "Verification Engineer", done: true },
      { id: "VER-D04", reqId: "REQ-D104", method: "rtl-sim", env: L("프로토콜 회귀 (BFM)", "protocol regression (BFM)", "プロトコル回帰(BFM)"), target: 1.0, owner: "Digital Designer", done: true },
      { id: "VER-D05", reqId: "REQ-D105", method: "monte-carlo", env: L("센서 모델 × ASIC 코너", "sensor model × ASIC corners", "センサーモデル×ASICコーナー"), target: 0.95, owner: "Analog Designer", done: false },
    ],
    options: [
      { id: "OPT-1", foundry: "FAB-C (alias)", node: "180 nm CMOS + MEMS", pkg: "LGA-12", risk: "medium", leadWeeks: [16, 22], nreIdx: 1.2 },
      { id: "OPT-2", foundry: "FAB-B (alias)", node: "110 nm CMOS", pkg: "WLCSP-16", risk: "high", leadWeeks: [18, 26], nreIdx: 1.5 },
    ],
    risks: [
      { id: "RSK-31", text: L("MEMS-CMOS 이종 통합 수율 불확실", "MEMS-CMOS heterogeneous integration yield uncertainty", "MEMS-CMOS異種統合の歩留まり不確実性"), sev: "high", owner: "Program Manager", mitigation: L("2개 공정 후보 병행 견적, 수율 시나리오 분석", "parallel quotes for 2 process candidates; yield scenario analysis", "2つの工程候補を並行見積り、歩留まりシナリオ分析") },
      { id: "RSK-32", text: L("습도 소자 히스테리시스 모델 미검증", "Humidity element hysteresis model unverified", "湿度素子のヒステリシスモデル未検証"), sev: "medium", owner: "Analog Designer", mitigation: L("ES 실측 후 모델 보정 (calibrated revision)", "calibrate the model after ES measurement (calibrated revision)", "ES実測後にモデル校正(calibrated revision)") },
    ],
    milestones: [
      { id: "M1", text: L("요구 동결", "Requirements freeze", "要求凍結"), due: "2026-10-09", status: "done" },
      { id: "M2", text: L("아키텍처 승인", "Architecture approval", "アーキテクチャ承認"), due: "2026-11-20", status: "open" },
      { id: "M3", text: L("TAPEOUT", "TAPEOUT", "TAPEOUT"), due: "2027-03-05", status: "open" },
      { id: "M4", text: L("ES 평가", "ES evaluation", "ES評価"), due: "2027-06-04", status: "open" },
      { id: "M5", text: L("신뢰성 완료", "Reliability complete", "信頼性完了"), due: "2027-10-08", status: "open" },
      { id: "M6", text: L("개발 완료", "Development complete", "開発完了"), due: "2027-11-05", status: "open" },
    ],
    ecos: [],
    qual: [
      { group: "TC", method: "Temp Cycling", cond: "-40 ↔ +125 °C", duration: "1,000 cy", samples: "3 lot × 77", status: "pass" },
      { group: "TH", method: "THB 85/85", cond: "85 °C / 85 %RH", duration: "1,000 h", samples: "3 lot × 77", status: "pending" },
      { group: "HAST", method: "Unbiased HAST", cond: "130 °C / 85 %RH", duration: "96 h", samples: "2 lot × 77", status: "fail", note: L("2샘플 습도 소자 박리 — 패키지 소재 CAPA", "2 samples: humidity element delamination — package material CAPA", "2サンプルで湿度素子剥離 — パッケージ材料CAPA") },
      { group: "ESD", method: "HBM / CDM", cond: "HBM ≥ 2 kV · CDM ≥ 500 V", duration: "—", samples: "3 lot × 6", status: "pass" },
      { group: "LU", method: "Latch-Up", cond: "±100 mA, 125 °C", duration: "—", samples: "3 lot × 6", status: "pass" },
    ],
    lots: [
      { id: "PL-5101", wafers: 3, yieldPct: 84.6, bins: { good: 85, retest: 5, fail1: 6, fail2: 4 }, spc: [1.0, 1.01, 0.99, 1.0, 1.0], disposition: "released" },
      { id: "PL-5102", wafers: 3, yieldPct: 86.2, bins: { good: 86, retest: 4, fail1: 6, fail2: 4 }, spc: [1.0, 1.0, 1.01, 0.99, 1.0], disposition: "released" },
    ],
    nre: [
      { item: L("마스크 세트 + MEMS 공정", "Mask set + MEMS process", "マスクセット+MEMS工程"), amount: L("기준 지수 1.3 (금액 마스킹)", "reference index 1.3 (amount masked)", "基準指数1.3(金額マスキング)") },
      { item: L("설계·검증 인력 (10 MM)", "Design & verification effort (10 MM)", "設計・検証工数(10 MM)"), amount: L("기준 지수 0.9", "reference index 0.9", "基準指数0.9") },
      { item: L("신뢰성 시험 (Grade 1)", "Reliability test (Grade 1)", "信頼性試験(Grade 1)"), amount: L("기준 지수 0.8", "reference index 0.8", "基準指数0.8") },
    ],
  },
];

// ── 9 stages (§2 mapping) ──
export type StageId = "s1" | "s2" | "s3" | "s4" | "s5" | "s6" | "s7" | "s8" | "s9";

export const STAGES: { id: StageId; num: number; ws: string; gate: string }[] = [
  { id: "s1", num: 1, ws: "Requirement Review", gate: "REQ_TRACE_100" },
  { id: "s2", num: 2, ws: "Feasibility & Architecture", gate: "ARCH_APPROVED" },
  { id: "s3", num: 3, ws: "Program Baseline", gate: "BASELINE_SIGNED" },
  { id: "s4", num: 4, ws: "Design & Verification", gate: "DESIGN_VERIFIED" },
  { id: "s5", num: 5, ws: "Engineering Sample", gate: "ES_ACCEPTED" },
  { id: "s6", num: 6, ws: "ECO & Test Program", gate: "ECO_CLOSED" },
  { id: "s7", num: 7, ws: "Commercial Sample & Qualification", gate: "QUAL_PASS" },
  { id: "s8", num: 8, ws: "Release & Evidence Pack", gate: "RELEASE_SIGNED" },
  { id: "s9", num: 9, ws: "Production Quality", gate: "LOT_RELEASE" },
];

// ── Deterministic ES sample measurements (synthetic_fixture, §18.2) ──
export type EsSample = {
  sn: string;
  wafer: string;
  corner: -40 | 25 | 85 | 105; // °C read temperature
  values: number[]; // aligned with template.corrParams
};

export function makeEsSamples(tpl: AsicTemplate, specBase: number[]): EsSample[] {
  const rng = mulberry32(strSeed(`es-${tpl.id}`));
  const out: EsSample[] = [];
  const wafers = ["W03", "W05", "W07"];
  const temps: (-40 | 25 | 85 | 105)[] = [-40, 25, 85, 105];
  let n = 0;
  for (const w of wafers) {
    for (const tt of temps) {
      n += 1;
      out.push({
        sn: `ES-${String(1000 + n)}`,
        wafer: w,
        corner: tt,
        values: tpl.corrParams.map((p, i) => {
          const pred = specBase[i] * (1 + p.tempCoef * (tt - 25));
          return pred * (1 + (rng() * 2 - 1) * p.tolerance) + (rng() * 2 - 1) * specBase[i] * 0.004;
        }),
      });
    }
  }
  return out;
}

// Correlation stats per §11.2: bias, MAE, RMSE, R² (against the temperature
// model — degenerate R² guards for near-constant predictions).
export function corrStats(pred: number[], meas: number[]) {
  const n = pred.length;
  const bias = meas.reduce((a, m, i) => a + (m - pred[i]), 0) / n;
  const mae = meas.reduce((a, m, i) => a + Math.abs(m - pred[i]), 0) / n;
  const rmse = Math.sqrt(meas.reduce((a, m, i) => a + (m - pred[i]) ** 2, 0) / n);
  const mp = pred.reduce((a, b) => a + b, 0) / n;
  const ssTot = pred.reduce((a, p) => a + (p - mp) ** 2, 0);
  const ssRes = pred.reduce((a, p, i) => a + (p - meas[i]) ** 2, 0);
  const r2 = ssTot < 1e-12 ? 1 : 1 - ssRes / ssTot;
  return { bias, mae, rmse, r2 };
}

export const round2 = (v: number) => Math.round(v * 100) / 100;

// Spec values used as the correlation base per template (aligned corrParams).
export function corrBase(tpl: AsicTemplate): number[] {
  const byKey: Record<string, number> = Object.fromEntries(tpl.specs.map((s) => [s.key, s.value]));
  const pick: Record<string, string[]> = {
    cap_afe: ["offset", "scan", "wake"],
    current_sensor: ["sens", "offset", "bw"],
    motor_ripple: ["ripple", "jitter"],
    env_sensor: ["rh", "press"],
  };
  return pick[tpl.id].map((k) => byKey[k] ?? 1);
}

// ── Evidence pack (stage 8) — deterministic content hashes (education digest:
//    16-hex strSeed summary, NOT a cryptographic hash; the real artifact
//    sha256 lives in the enterprise store per §7.1 ArtifactVersion). ──
export function eduHash(s: string): string {
  let h = strSeed(s);
  let out = "";
  for (let i = 0; i < 4; i++) {
    h = Math.imul(h ^ (h >>> 13), 0x5bd1e995) >>> 0;
    out += h.toString(16).padStart(8, "0").slice(0, 4);
  }
  return out;
}

export type EvidenceItem = {
  id: string;
  kind: LStr;
  rev: string;
  classification: "INTERNAL" | "CUSTOMER_CONFIDENTIAL";
  approved: boolean;
  author: string;
  approver: string;
};

export function makeEvidence(tpl: AsicTemplate, maskRev: string, testProgRev: number): EvidenceItem[] {
  return [
    { id: `SPEC-BASELINE-${tpl.id.toUpperCase()}`, kind: L("요구·사양 기준선", "Requirements/spec baseline", "要求・仕様ベースライン"), rev: "r2", classification: "CUSTOMER_CONFIDENTIAL", approved: true, author: "System Architect", approver: "Customer Engineer" },
    { id: `RTL-DESIGN-${tpl.id.toUpperCase()}`, kind: L("RTL + lint/sim/synth 로그", "RTL + lint/sim/synth logs", "RTL+lint/sim/synthログ"), rev: maskRev, classification: "INTERNAL", approved: true, author: "Digital Designer", approver: "Verification Engineer" },
    { id: `GDS-${tpl.id.toUpperCase()}`, kind: L("GDS/OASIS (레이아웃)", "GDS/OASIS (layout)", "GDS/OASIS(レイアウト)"), rev: maskRev, classification: "INTERNAL", approved: true, author: "Physical Designer", approver: "Program Manager" },
    { id: `QUAL-REPORT-${tpl.id.toUpperCase()}`, kind: L("AEC-Q100 시험 보고서", "AEC-Q100 test report", "AEC-Q100試験報告書"), rev: "policy alps-asic-v1.0", classification: "CUSTOMER_CONFIDENTIAL", approved: false, author: "Quality/Reliability", approver: "" },
    { id: `TESTPROG-${tpl.id.toUpperCase()}`, kind: L("ATE 테스트 프로그램", "ATE test program", "ATEテストプログラム"), rev: `v${testProgRev}`, classification: "INTERNAL", approved: true, author: "Product/Test Engineer", approver: "Quality/Reliability" },
    { id: `CORR-${tpl.id.toUpperCase()}`, kind: L("ES/CS 상관 보고서", "ES/CS correlation report", "ES/CS相関報告書"), rev: "r1", classification: "CUSTOMER_CONFIDENTIAL", approved: false, author: "Product/Test Engineer", approver: "" },
  ];
}

// Readiness ladder v1.1 (지시서 §8 개편) — six rungs from education to release.
// The backend gate report (asic_gate_policy.py) picks the rung from DATABASE
// evidence depth; production_candidate/released stay unreachable from
// synthetic evidence — real, attested measurements are the only way up
// (§15: this twin never substitutes a certification body).
export const READINESS_LEVELS = [
  { key: "education_only", reachable: true },
  { key: "connected_nonvalidated", reachable: true },
  { key: "validated_shadow", reachable: true },
  { key: "controlled_pilot", reachable: true },
  { key: "production_candidate", reachable: false },
  { key: "released", reachable: false },
] as const;
