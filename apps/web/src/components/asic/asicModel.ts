import { mulberry32, strSeed } from "../eda/edaRunner";

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
// present" (§10.2 blocker #1). UI chrome is i18n (ko/en/ja); the engineering
// row data (spec conditions, test groups, lot ids) stays as technical strings,
// the way fab data actually reads.

export type Confidence = "educational_estimate" | "synthetic_fixture";

export type ReqStatus = "draft" | "provisional" | "approved" | "superseded";
export type VerMethod = "rtl-sim" | "bench" | "spice+synth" | "qualification" | "monte-carlo" | "fault-campaign";

export type Requirement = {
  id: string;
  text: string;
  source: string;
  category: "기능" | "품질" | "환경" | "인터페이스" | "안전";
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

export type Risk = { id: string; text: string; sev: "high" | "medium" | "low"; owner: string; mitigation: string };

export type VerItem = {
  id: string;
  reqId: string;
  method: VerMethod;
  env: string;
  target: number; // coverage target 0..1
  owner: string; // role from §3
  done: boolean;
};

export type Milestone = { id: string; text: string; due: string; status: "done" | "open" };

export type Eco = {
  id: string;
  text: string;
  status: "proposed" | "analyzed" | "closed";
  impactReq: string[];
  impactRuns: string[];
  maskRev: string;
};

export type QualRow = {
  group: string;
  method: string;
  cond: string;
  duration: string;
  samples: string;
  status: "pass" | "pending" | "fail" | "waiver";
  note?: string;
};

export type CorrParam = { key: string; unit: string; tempCoef: number; tolerance: number };

export type Lot = {
  id: string;
  wafers: number;
  yieldPct: number;
  bins: { good: number; retest: number; fail1: number; fail2: number };
  spc: number[]; // key parametric per-lot
  excursion?: string; // rule violation description (§13.2 — notification only)
  disposition?: "held" | "released" | "mrb_reviewed";
};

export type AsicTemplate = {
  id: string;
  name: string;
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
  nre: { item: string; amount: string }[];
};

const T = (grade: "G2" | "G1" | "G0", temps: [number, number]) => ({ grade, temps });

// AEC-Q100 grade → temperature window used by the qualification condition
// strings (§12: conditions derive from the target grade, never hardcoded pass).
export const GRADE_TEMP: Record<"G2" | "G1" | "G0", [number, number]> = { G2: [-40, 105], G1: [-40, 125], G0: [-40, 150] };
void T;

export const ASIC_TEMPLATES: AsicTemplate[] = [
  {
    id: "cap_afe",
    name: "Template A — 정전용량 센서 AFE/SoC",
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
      { id: "REQ-A101", text: "장갑 착용 상태에서 20 mm hover 검출 확률 ≥ 95 %", source: "고객 회의 2026-06-12", category: "기능", priority: "must", status: "approved", method: "bench", verId: "VER-A01" },
      { id: "REQ-A102", text: "16채널 동시 스캔, 스캔 레이트 200 Hz", source: "시스템 사양서 v2.1", category: "기능", priority: "must", status: "approved", method: "rtl-sim", verId: "VER-A02" },
      { id: "REQ-A103", text: "AEC-Q100 Grade 2 (-40~+105 °C) 동작 보장", source: "품질 요구서", category: "환경", priority: "must", status: "approved", method: "qualification", verId: "VER-A03" },
      { id: "REQ-A104", text: "스캔 동작 전력 ≤ 1.8 mW", source: "시스템 사양서 v2.1", category: "품질", priority: "must", status: "approved", method: "spice+synth", verId: "VER-A04" },
      { id: "REQ-A105", text: "채널 간 초기 오정합 ≤ 2 % (사전 가정치)", source: "선행 칩 측정치", category: "품질", priority: "should", status: "provisional", method: "monte-carlo", verId: "VER-A05", assumptionId: "ASM-011" },
      { id: "REQ-A106", text: "전극 단락/개방 진단 검출", source: "고객 품질 부서", category: "안전", priority: "must", status: "draft", method: "fault-campaign", verId: "" },
      { id: "REQ-A107", text: "SPI 10 MHz 검증", source: "인터페이스 사양 r1", category: "인터페이스", priority: "must", status: "superseded", method: "rtl-sim", verId: "VER-A07" },
      { id: "REQ-A108", text: "SPI 20 MHz 검증 (REQ-A107 대체)", source: "인터페이스 사양 r2", category: "인터페이스", priority: "must", status: "approved", method: "rtl-sim", verId: "VER-A07" },
    ],
    verItems: [
      { id: "VER-A01", reqId: "REQ-A101", method: "bench", env: "ES 샘플 + 거리 스테이지 (5/10/15/20 mm)", target: 0.95, owner: "Product/Test Engineer", done: true },
      { id: "VER-A02", reqId: "REQ-A102", method: "rtl-sim", env: "RTL regression (scan controller)", target: 1.0, owner: "Digital Designer", done: true },
      { id: "VER-A03", reqId: "REQ-A103", method: "qualification", env: "AEC-Q100 매트릭스 (S07)", target: 1.0, owner: "Quality/Reliability", done: false },
      { id: "VER-A04", reqId: "REQ-A104", method: "spice+synth", env: "전력推定: 합성 게이트 수 + SPICE", target: 1.0, owner: "Analog Designer", done: true },
      { id: "VER-A05", reqId: "REQ-A105", method: "monte-carlo", env: "MC 500 pts (공정 코너)", target: 0.98, owner: "Analog Designer", done: true },
      { id: "VER-A07", reqId: "REQ-A108", method: "rtl-sim", env: "SPI 마스터 모델 20 MHz", target: 1.0, owner: "Verification Engineer", done: true },
    ],
    options: [
      { id: "OPT-1", foundry: "FAB-A (alias)", node: "180 nm BCD", pkg: "QFN-32", risk: "low", leadWeeks: [10, 14], nreIdx: 1.0 },
      { id: "OPT-2", foundry: "FAB-B (alias)", node: "110 nm CMOS", pkg: "WLCSP-24", risk: "medium", leadWeeks: [14, 20], nreIdx: 1.45 },
      { id: "OPT-3", foundry: "FAB-C (alias)", node: "180 nm CMOS", pkg: "LQFP-48", risk: "low", leadWeeks: [8, 12], nreIdx: 0.9 },
    ],
    risks: [
      { id: "RSK-01", text: "장갑 유전율 편차 → hover 마진 감소", sev: "high", owner: "System Architect", mitigation: "(field-sim GOLD 시나리오로 마진 검증 + 게인 ECO 준비)" },
      { id: "RSK-02", text: "16ch MUX 누설 전류 → 스캔 노이즈", sev: "medium", owner: "Analog Designer", mitigation: "corner 시뮬레이션 + 쉴드 구동" },
      { id: "RSK-03", text: "WLCSP 리플로우 스토넬링", sev: "low", owner: "Physical Designer", mitigation: "패키지 후보 2·3 비교 평가" },
    ],
    milestones: [
      { id: "M1", text: "요구 동결 (baseline)", due: "2026-07-10", status: "done" },
      { id: "M2", text: "아키텍처 승인", due: "2026-08-14", status: "done" },
      { id: "M3", text: "디자인 freeze / TAPEOUT", due: "2026-10-30", status: "open" },
      { id: "M4", text: "ES 샘플 입고 · 평가 착수", due: "2027-01-15", status: "open" },
      { id: "M5", text: "CS · 신뢰성 완료", due: "2027-04-30", status: "open" },
      { id: "M6", text: "개발 완료 (Release)", due: "2027-05-30", status: "open" },
    ],
    ecos: [
      { id: "CR-001", text: "스캔 클록 게이팅 추가 — REQ-A104 전력 마진 확보", status: "closed", impactReq: ["REQ-A104"], impactRuns: ["synth"], maskRev: "r3 → r4" },
      { id: "CR-002", text: "CDC 리셋 타이밍 수정 (first-silicon 관찰)", status: "proposed", impactReq: ["REQ-A102"], impactRuns: ["sim", "synth"], maskRev: "r4 → r5 (보류)" },
    ],
    qual: [
      { group: "TC", method: "Temp Cycling JESD22-A104", cond: "-40 ↔ +105 °C", duration: "1,000 cy", samples: "3 lot × 77", status: "pass" },
      { group: "TH", method: "Temp/Humidity Bias 85/85", cond: "85 °C / 85 %RH, bias 인가", duration: "1,000 h", samples: "3 lot × 77", status: "pass" },
      { group: "HTSL", method: "High Temp Storage", cond: "150 °C (passivation 후)", duration: "1,000 h", samples: "3 lot × 77", status: "pass" },
      { group: "HAST", method: "Unbiased HAST", cond: "130 °C / 85 %RH", duration: "96 h", samples: "2 lot × 77", status: "pending" },
      { group: "TCBIAS", method: "Power Temp Cycling", cond: "-40 ↔ +105 °C, 동작 bias", duration: "500 cy", samples: "2 lot × 77", status: "pending" },
      { group: "ESD", method: "HBM / CDM", cond: "HBM ≥ 2 kV · CDM ≥ 500 V", duration: "—", samples: "3 lot × 6", status: "pass" },
      { group: "LU", method: "Latch-Up", cond: "+/- 100 mA, 105 °C", duration: "—", samples: "3 lot × 6", status: "pass" },
      { group: "FG", method: "Failure Grid / 진단 커버리지", cond: "전극 단락·개방 주입", duration: "—", samples: "1 lot × 30", status: "fail", note: "진단 커버리지 미달 (REQ-A106 관련) — CAPA 진행" },
    ],
    lots: [
      { id: "PL-2601", wafers: 6, yieldPct: 91.2, bins: { good: 91, retest: 4, fail1: 3, fail2: 2 }, spc: [1.02, 0.99, 1.0, 1.01, 0.98], disposition: "released" },
      { id: "PL-2602", wafers: 6, yieldPct: 92.8, bins: { good: 93, retest: 3, fail1: 2, fail2: 2 }, spc: [1.0, 1.01, 0.99, 1.0, 1.02], disposition: "released" },
      { id: "PL-2603", wafers: 8, yieldPct: 89.5, bins: { good: 90, retest: 4, fail1: 4, fail2: 2 }, spc: [0.98, 0.97, 1.0, 0.99, 1.01], disposition: "released" },
      { id: "PL-2604", wafers: 8, yieldPct: 78.4, bins: { good: 78, retest: 6, fail1: 10, fail2: 6 }, spc: [1.06, 1.12, 1.18, 1.09, 1.04], excursion: "SPC rule 2×σ 초과 3점 연속 (offset drift) — 공정 코너 이탈 의심", disposition: "held" },
      { id: "PL-2605", wafers: 8, yieldPct: 93.7, bins: { good: 94, retest: 2, fail1: 2, fail2: 2 }, spc: [1.0, 0.99, 1.01, 1.0, 0.99], disposition: "released" },
      { id: "PL-2606", wafers: 12, yieldPct: 94.1, bins: { good: 94, retest: 3, fail1: 2, fail2: 1 }, spc: [0.99, 1.0, 1.0, 1.01, 1.0], disposition: "released" },
    ],
    nre: [
      { item: "마스크 세트 (mask set)", amount: "기준 지수 1.00 (금액 마스킹)" },
      { item: "설계·검증 인력 (12 MM)", amount: "기준 지수 1.00" },
      { item: "테스트 프로그램 + ATE 보드", amount: "기준 지수 0.35" },
      { item: "신뢰성 시험 (Grade 2 매트릭스)", amount: "기준 지수 0.6" },
    ],
  },
  {
    id: "current_sensor",
    name: "Template B — 전류 센서 신호조절 ASIC",
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
      { id: "REQ-B101", text: "정비례 출력 26.4 mV/A (100 A 범위)", source: "고객 사양서 r3", category: "기능", priority: "must", status: "approved", method: "bench", verId: "VER-B01" },
      { id: "REQ-B102", text: "AEC-Q100 Grade 0 (-40~+150 °C)", source: "품질 요구서", category: "환경", priority: "must", status: "approved", method: "qualification", verId: "VER-B02" },
      { id: "REQ-B103", text: "폐루프 안정도: 위상 마진 ≥ 45°", source: "회로 검토서", category: "기능", priority: "must", status: "approved", method: "spice+synth", verId: "VER-B03" },
      { id: "REQ-B104", text: "외부 자계 교란 200 mT에서 오출력 ≤ 1 %FS", source: "고객 EM 시험 결과", category: "안전", priority: "should", status: "provisional", method: "bench", verId: "VER-B04", assumptionId: "ASM-021" },
      { id: "REQ-B105", text: "fail-safe: 전원 단락 시 출력 클램프", source: "안전 요구서", category: "안전", priority: "must", status: "approved", method: "fault-campaign", verId: "VER-B05" },
    ],
    verItems: [
      { id: "VER-B01", reqId: "REQ-B101", method: "bench", env: "ES 샘플 + 정밀 전류원", target: 0.99, owner: "Product/Test Engineer", done: true },
      { id: "VER-B02", reqId: "REQ-B102", method: "qualification", env: "AEC-Q100 매트릭스 (S07)", target: 1.0, owner: "Quality/Reliability", done: false },
      { id: "VER-B03", reqId: "REQ-B103", method: "spice+synth", env: "AC/TS 폐루프 해석", target: 1.0, owner: "Analog Designer", done: true },
      { id: "VER-B04", reqId: "REQ-B104", method: "bench", env: "헤름홀츠 코일 교란 시험", target: 0.99, owner: "Product/Test Engineer", done: false },
      { id: "VER-B05", reqId: "REQ-B105", method: "fault-campaign", env: "fault 주입 캠페인", target: 1.0, owner: "Verification Engineer", done: true },
    ],
    options: [
      { id: "OPT-1", foundry: "FAB-D (alias)", node: "180 nm BCD", pkg: "SOIC-8", risk: "low", leadWeeks: [9, 13], nreIdx: 0.85 },
      { id: "OPT-2", foundry: "FAB-A (alias)", node: "180 nm BCD", pkg: "TSSOP-16", risk: "medium", leadWeeks: [12, 16], nreIdx: 1.1 },
    ],
    risks: [
      { id: "RSK-11", text: "GMR 온도 드리프트 → trim 범위 초과", sev: "high", owner: "Analog Designer", mitigation: "2점 trim + 보상 계수 산포 검증" },
      { id: "RSK-12", text: "Grade 0 시험 샘플 수 확보 지연", sev: "medium", owner: "Program Manager", mitigation: "ES/CS lot 계획 조기 확정" },
    ],
    milestones: [
      { id: "M1", text: "요구 동결", due: "2026-08-28", status: "done" },
      { id: "M2", text: "아키텍처 승인", due: "2026-09-25", status: "done" },
      { id: "M3", text: "디자인 freeze / TAPEOUT", due: "2026-12-18", status: "open" },
      { id: "M4", text: "ES 평가", due: "2027-03-12", status: "open" },
      { id: "M5", text: "신뢰성 완료 (Grade 0)", due: "2027-07-30", status: "open" },
      { id: "M6", text: "개발 완료", due: "2027-08-27", status: "open" },
    ],
    ecos: [{ id: "CR-101", text: "오프셋 캔슬 스위치 사이즈 증가 (드리프트 대응)", status: "analyzed", impactReq: ["REQ-B101"], impactRuns: ["sim"], maskRev: "r2 → r3 (대기)" }],
    qual: [
      { group: "TC", method: "Temp Cycling", cond: "-40 ↔ +150 °C", duration: "2,000 cy", samples: "6 lot × 77", status: "pending" },
      { group: "TH", method: "THB 85/85", cond: "85 °C / 85 %RH", duration: "1,000 h", samples: "3 lot × 77", status: "pass" },
      { group: "HTSL", method: "High Temp Storage", cond: "170 °C", duration: "1,000 h", samples: "3 lot × 77", status: "pass" },
      { group: "HTRB", method: "High Temp Reverse Bias", cond: "150 °C, 최대 역전압", duration: "1,000 h", samples: "3 lot × 77", status: "pending" },
      { group: "ESD", method: "HBM / CDM", cond: "HBM ≥ 2 kV · CDM ≥ 500 V", duration: "—", samples: "3 lot × 6", status: "pass" },
      { group: "LU", method: "Latch-Up", cond: "±200 mA, 150 °C", duration: "—", samples: "3 lot × 6", status: "pass" },
    ],
    lots: [
      { id: "PL-3501", wafers: 5, yieldPct: 94.2, bins: { good: 94, retest: 3, fail1: 2, fail2: 1 }, spc: [1.0, 1.0, 0.99, 1.01, 1.0], disposition: "released" },
      { id: "PL-3502", wafers: 5, yieldPct: 95.1, bins: { good: 95, retest: 2, fail1: 2, fail2: 1 }, spc: [1.01, 1.0, 1.0, 0.99, 1.0], disposition: "released" },
      { id: "PL-3503", wafers: 10, yieldPct: 93.4, bins: { good: 93, retest: 3, fail1: 3, fail2: 1 }, spc: [0.99, 1.0, 1.0, 1.0, 1.01], disposition: "released" },
    ],
    nre: [
      { item: "마스크 세트", amount: "기준 지수 0.8 (금액 마스킹)" },
      { item: "설계·검증 인력 (8 MM)", amount: "기준 지수 0.7" },
      { item: "신뢰성 시험 (Grade 0)", amount: "기준 지수 1.2" },
    ],
  },
  {
    id: "motor_ripple",
    name: "Template C — DC 모터 전류·전압·리플 검출 ASIC",
    grade: "G1",
    missionSlug: "uart_tx",
    color: "#a78bfa",
    blocks: [
      { key: "prot", label: "-10~+60 V 보호 / level shift", kind: "power" },
      { key: "vsense", label: "Terminal voltage sensing", kind: "analog" },
      { key: "ripple", label: "Ripple 추출 + 필터", kind: "mixed" },
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
      { id: "REQ-C101", text: "-10 ~ +60 V 입력에서 보호·정상 동작", source: "고객 사양서 r5", category: "기능", priority: "must", status: "approved", method: "bench", verId: "VER-C01" },
      { id: "REQ-C102", text: "정격 전류 리플 45 mA(pk) 검출 · 펄스 출력", source: "고객 사양서 r5", category: "기능", priority: "must", status: "approved", method: "bench", verId: "VER-C02" },
      { id: "REQ-C103", text: "리플 펄스와 모터 정위치 상관 오차 ≤ 2 %", source: "시스템 검토서", category: "품질", priority: "must", status: "approved", method: "bench", verId: "VER-C03" },
      { id: "REQ-C104", text: "역접속 / 부성 과도에서 무손상", source: "안전 요구서", category: "안전", priority: "must", status: "approved", method: "fault-campaign", verId: "VER-C04" },
      { id: "REQ-C105", text: "AEC-Q100 Grade 1 (-40~+125 °C)", source: "품질 요구서", category: "환경", priority: "must", status: "provisional", method: "qualification", verId: "VER-C05", assumptionId: "ASM-031" },
    ],
    verItems: [
      { id: "VER-C01", reqId: "REQ-C101", method: "bench", env: "전원 과도 시험기", target: 1.0, owner: "Product/Test Engineer", done: true },
      { id: "VER-C02", reqId: "REQ-C102", method: "bench", env: "모터 플랜트 리플레이", target: 0.98, owner: "Product/Test Engineer", done: true },
      { id: "VER-C03", reqId: "REQ-C103", method: "bench", env: "엔코더 동시 계측", target: 0.98, owner: "System Architect", done: false },
      { id: "VER-C04", reqId: "REQ-C104", method: "fault-campaign", env: "fault 주입 캠페인", target: 1.0, owner: "Verification Engineer", done: true },
      { id: "VER-C05", reqId: "REQ-C105", method: "qualification", env: "AEC-Q100 매트릭스 (S07)", target: 1.0, owner: "Quality/Reliability", done: false },
    ],
    options: [
      { id: "OPT-1", foundry: "FAB-A (alias)", node: "180 nm BCD 60 V", pkg: "SOP-8", risk: "low", leadWeeks: [10, 14], nreIdx: 0.95 },
      { id: "OPT-2", foundry: "FAB-D (alias)", node: "130 nm BCD 70 V", pkg: "TSSOP-10", risk: "medium", leadWeeks: [13, 18], nreIdx: 1.3 },
    ],
    risks: [
      { id: "RSK-21", text: "60 V 입력 보호 소자의 ESOA 마진", sev: "high", owner: "Analog Designer", mitigation: "로드라인 해석 + 실장 보호 소자 협의" },
      { id: "RSK-22", text: "리플 S/N이 하네스 길이에 따라 열화", sev: "medium", owner: "System Architect", mitigation: "차동 감지 검토, 차량 배선 모델 반영" },
    ],
    milestones: [
      { id: "M1", text: "요구 동결", due: "2026-09-11", status: "done" },
      { id: "M2", text: "아키텍처 승인", due: "2026-10-23", status: "open" },
      { id: "M3", text: "TAPEOUT", due: "2027-01-29", status: "open" },
      { id: "M4", text: "ES 평가", due: "2027-04-23", status: "open" },
      { id: "M5", text: "신뢰성 완료", due: "2027-08-27", status: "open" },
      { id: "M6", text: "개발 완료", due: "2027-09-24", status: "open" },
    ],
    ecos: [],
    qual: [
      { group: "TC", method: "Temp Cycling", cond: "-40 ↔ +125 °C", duration: "1,000 cy", samples: "3 lot × 77", status: "pass" },
      { group: "TH", method: "THB 85/85", cond: "85 °C / 85 %RH", duration: "1,000 h", samples: "3 lot × 77", status: "pending" },
      { group: "HTSL", method: "High Temp Storage", cond: "150 °C", duration: "1,000 h", samples: "3 lot × 77", status: "pass" },
      { group: "ESD", method: "HBM / CDM", cond: "HBM ≥ 2 kV · CDM ≥ 500 V", duration: "—", samples: "3 lot × 6", status: "pass" },
      { group: "LU", method: "Latch-Up", cond: "±100 mA, 125 °C", duration: "—", samples: "3 lot × 6", status: "pass" },
      { group: "VF", method: "Vibration / Mechanical Shock", cond: "차량 규격 프로파일", duration: "—", samples: "2 lot × 15", status: "pending" },
    ],
    lots: [
      { id: "PL-4201", wafers: 4, yieldPct: 92.5, bins: { good: 93, retest: 3, fail1: 3, fail2: 1 }, spc: [1.0, 1.01, 0.99, 1.0, 1.0], disposition: "released" },
      { id: "PL-4202", wafers: 4, yieldPct: 91.8, bins: { good: 92, retest: 4, fail1: 3, fail2: 1 }, spc: [1.0, 0.99, 1.0, 1.02, 1.0], disposition: "released" },
    ],
    nre: [
      { item: "마스크 세트", amount: "기준 지수 0.9 (금액 마스킹)" },
      { item: "설계·검증 인력 (6 MM)", amount: "기준 지수 0.55" },
      { item: "신뢰성 시험 (Grade 1)", amount: "기준 지수 0.8" },
    ],
  },
  {
    id: "env_sensor",
    name: "Template D — 습도·기압·지자기 센서 신호조절 ASIC",
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
      { id: "REQ-D101", text: "습도 ±2.0 %RH (25 °C, 보정 후)", source: "고객 사양서 r2", category: "기능", priority: "must", status: "approved", method: "bench", verId: "VER-D01" },
      { id: "REQ-D102", text: "기압 ±0.6 hPa (-20~+85 °C)", source: "고객 사양서 r2", category: "기능", priority: "must", status: "approved", method: "bench", verId: "VER-D02" },
      { id: "REQ-D103", text: "보정 계수 OTP 기록 · 메모리 고장 검출 (CRC)", source: "품질 요구서", category: "안전", priority: "should", status: "approved", method: "fault-campaign", verId: "VER-D03" },
      { id: "REQ-D104", text: "I2C 400 kHz / SPI 1 MHz 인터페이스 회귀", source: "인터페이스 사양", category: "인터페이스", priority: "must", status: "approved", method: "rtl-sim", verId: "VER-D04" },
      { id: "REQ-D105", text: "챔버 ES 실측과 시뮬레이션 상관 R² ≥ 0.95", source: "검증 계획서", category: "품질", priority: "should", status: "provisional", method: "monte-carlo", verId: "VER-D05", assumptionId: "ASM-041" },
    ],
    verItems: [
      { id: "VER-D01", reqId: "REQ-D101", method: "bench", env: "항온항습 챔버", target: 0.95, owner: "Product/Test Engineer", done: true },
      { id: "VER-D02", reqId: "REQ-D102", method: "bench", env: "압력 캘리브레이터", target: 0.95, owner: "Product/Test Engineer", done: true },
      { id: "VER-D03", reqId: "REQ-D103", method: "fault-campaign", env: "메모리 비트 고장 주입", target: 1.0, owner: "Verification Engineer", done: true },
      { id: "VER-D04", reqId: "REQ-D104", method: "rtl-sim", env: "프로토콜 회귀 (BFM)", target: 1.0, owner: "Digital Designer", done: true },
      { id: "VER-D05", reqId: "REQ-D105", method: "monte-carlo", env: "센서 모델 × ASIC 코너", target: 0.95, owner: "Analog Designer", done: false },
    ],
    options: [
      { id: "OPT-1", foundry: "FAB-C (alias)", node: "180 nm CMOS + MEMS", pkg: "LGA-12", risk: "medium", leadWeeks: [16, 22], nreIdx: 1.2 },
      { id: "OPT-2", foundry: "FAB-B (alias)", node: "110 nm CMOS", pkg: "WLCSP-16", risk: "high", leadWeeks: [18, 26], nreIdx: 1.5 },
    ],
    risks: [
      { id: "RSK-31", text: "MEMS-CMOS 이종 통합 수율 불확실", sev: "high", owner: "Program Manager", mitigation: "2개 공정 후보 병행 견적, 수율 시나리오 분석" },
      { id: "RSK-32", text: "습도 소자 히스테리시스 모델 미검증", sev: "medium", owner: "Analog Designer", mitigation: "ES 실측 후 모델 보정 (calibrated revision)" },
    ],
    milestones: [
      { id: "M1", text: "요구 동결", due: "2026-10-09", status: "done" },
      { id: "M2", text: "아키텍처 승인", due: "2026-11-20", status: "open" },
      { id: "M3", text: "TAPEOUT", due: "2027-03-05", status: "open" },
      { id: "M4", text: "ES 평가", due: "2027-06-04", status: "open" },
      { id: "M5", text: "신뢰성 완료", due: "2027-10-08", status: "open" },
      { id: "M6", text: "개발 완료", due: "2027-11-05", status: "open" },
    ],
    ecos: [],
    qual: [
      { group: "TC", method: "Temp Cycling", cond: "-40 ↔ +125 °C", duration: "1,000 cy", samples: "3 lot × 77", status: "pass" },
      { group: "TH", method: "THB 85/85", cond: "85 °C / 85 %RH", duration: "1,000 h", samples: "3 lot × 77", status: "pending" },
      { group: "HAST", method: "Unbiased HAST", cond: "130 °C / 85 %RH", duration: "96 h", samples: "2 lot × 77", status: "fail", note: "2샘플 습도 소자 박리 — 패키지 소재 CAPA" },
      { group: "ESD", method: "HBM / CDM", cond: "HBM ≥ 2 kV · CDM ≥ 500 V", duration: "—", samples: "3 lot × 6", status: "pass" },
      { group: "LU", method: "Latch-Up", cond: "±100 mA, 125 °C", duration: "—", samples: "3 lot × 6", status: "pass" },
    ],
    lots: [
      { id: "PL-5101", wafers: 3, yieldPct: 84.6, bins: { good: 85, retest: 5, fail1: 6, fail2: 4 }, spc: [1.0, 1.01, 0.99, 1.0, 1.0], disposition: "released" },
      { id: "PL-5102", wafers: 3, yieldPct: 86.2, bins: { good: 86, retest: 4, fail1: 6, fail2: 4 }, spc: [1.0, 1.0, 1.01, 0.99, 1.0], disposition: "released" },
    ],
    nre: [
      { item: "마스크 세트 + MEMS 공정", amount: "기준 지수 1.3 (금액 마스킹)" },
      { item: "설계·검증 인력 (10 MM)", amount: "기준 지수 0.9" },
      { item: "신뢰성 시험 (Grade 1)", amount: "기준 지수 0.8" },
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
  kind: string;
  rev: string;
  classification: "INTERNAL" | "CUSTOMER_CONFIDENTIAL";
  approved: boolean;
  author: string;
  approver: string;
};

export function makeEvidence(tpl: AsicTemplate, maskRev: string, testProgRev: number): EvidenceItem[] {
  return [
    { id: `SPEC-BASELINE-${tpl.id.toUpperCase()}`, kind: "요구·사양 기준선", rev: "r2", classification: "CUSTOMER_CONFIDENTIAL", approved: true, author: "System Architect", approver: "Customer Engineer" },
    { id: `RTL-DESIGN-${tpl.id.toUpperCase()}`, kind: "RTL + lint/sim/synth 로그", rev: maskRev, classification: "INTERNAL", approved: true, author: "Digital Designer", approver: "Verification Engineer" },
    { id: `GDS-${tpl.id.toUpperCase()}`, kind: "GDS/OASIS (layout)", rev: maskRev, classification: "INTERNAL", approved: true, author: "Physical Designer", approver: "Program Manager" },
    { id: `QUAL-REPORT-${tpl.id.toUpperCase()}`, kind: "AEC-Q100 시험 보고서", rev: "policy alps-asic-v1.0", classification: "CUSTOMER_CONFIDENTIAL", approved: false, author: "Quality/Reliability", approver: "" },
    { id: `TESTPROG-${tpl.id.toUpperCase()}`, kind: "ATE 테스트 프로그램", rev: `v${testProgRev}`, classification: "INTERNAL", approved: true, author: "Product/Test Engineer", approver: "Quality/Reliability" },
    { id: `CORR-${tpl.id.toUpperCase()}`, kind: "ES/CS 상관 보고서", rev: "r1", classification: "CUSTOMER_CONFIDENTIAL", approved: false, author: "Product/Test Engineer", approver: "" },
  ];
}

// Readiness ladder (§10.3) — education mode caps at engineering_review_ready:
// synthetic results can never become signoff_candidate or released (§0.1).
export const READINESS_LEVELS = [
  { key: "education_only", reachable: true },
  { key: "prototype_evidence", reachable: true },
  { key: "engineering_review_ready", reachable: true },
  { key: "signoff_candidate", reachable: false },
  { key: "released", reachable: false },
] as const;
