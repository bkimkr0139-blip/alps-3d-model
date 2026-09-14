// Client-side educational EDA runners — TypeScript port of AgentIC's
// mock lint / simulation / synthesis / place&route services
// (apps/api/app/services/eda/runners.py). Runs entirely in the browser:
// no backend job, no external tool. Numbers are heuristics derived from the
// student's RTL (operator counts, block counts) so they respond to edits,
// and every run is deterministic for a given input (seeded PRNG replaces
// Python's random.Random(hash(...))).

export type LintIssue = { line: number; severity: "error" | "warning"; message: string };

export type LintResult = {
  status: "success" | "failed";
  errors: LintIssue[];
  warnings: LintIssue[];
  log: string;
};

export type WaveSignal = { name: string; width: number; transitions: [number, string][] };
export type Waveform = { timescale: string; end_time: number; signals: WaveSignal[] };

export type Scenario = { name: string; description: string; expected_pass: boolean };

export type SimResult = {
  status: "success" | "failed";
  waveform: Waveform | null;
  coverage: { line: number; toggle: number; branch: number; fsm: number; overall: number };
  scenarios: Scenario[];
  testCount: number;
  passed: number;
  failed: number;
  log: string;
};

export type CriticalPath = {
  id: number;
  startpoint: string;
  endpoint: string;
  stages: string[];
  delayNs: number;
  slackNs: number;
  cellDelayNs: number;
  netDelayNs: number;
  status: "MET" | "VIOLATED";
};

export type SynthResult = {
  status: "success" | "failed";
  gateCount: number;
  cellCount: number;
  flopCount: number;
  lutCount: number;
  cellsByType: Record<string, number>;
  areaUm2: number;
  areaBreakdown: { combinationalUm2: number; sequentialUm2: number; interconnectUm2: number; totalUm2: number };
  power: { dynamicMw: number; leakageUw: number; totalMw: number; frequencyMhz: number };
  clockPeriodNs: number;
  timingSlackNs: number;
  warnings: string[];
  criticalPaths: CriticalPath[];
  log: string;
};

export type FloorplanConfig = {
  dieW: number;
  dieD: number;
  utilization: number;
  numMacros: number;
  padDensity: "low" | "medium" | "high";
  powerGridPitch: number;
  signalRoutingDensity: number;
};

export type PnrResult = {
  dieAreaUm2: number;
  coreAreaUm2: number;
  utilization: number;
  placedCells: number;
  routedNets: number;
  macros: number;
  wnsNs: number;
  tnsNs: number;
  drcViolations: number;
  log: string;
};

// ── Deterministic RNG (replaces random.Random(hash(title) & mask)) ──
export function strSeed(s: string): number {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

export function mulberry32(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const round = (v: number, d = 3) => Math.round(v * 10 ** d) / 10 ** d;

// ── Mission catalog (ported from AgentIC seed.py MISSIONS) ──
export type Mission = {
  slug: string;
  title: string;
  difficulty: "beginner" | "intermediate" | "advanced";
  topModule: string;
  starterRtl: string;
  /** known-top flag: unlocks the signal presets + scenario suite below */
  known: boolean;
};

export const MISSIONS: Mission[] = [
  {
    slug: "counter_4bit",
    title: "4-bit Counter",
    difficulty: "beginner",
    topModule: "counter4",
    known: true,
    starterRtl: `module counter4 (
    input  wire        clk,
    input  wire        rst_n,
    input  wire        en,
    output reg  [3:0]  count
);
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n)
            count <= 4'd0;
        else if (en)
            count <= count + 4'd1;
    end
endmodule
`,
  },
  {
    slug: "alu_4bit",
    title: "4-bit ALU",
    difficulty: "beginner",
    topModule: "alu",
    known: true,
    starterRtl: `module alu (
    input  wire [3:0] a,
    input  wire [3:0] b,
    input  wire [1:0] op,   // 00 ADD, 01 SUB, 10 AND, 11 OR
    output reg  [4:0] y
);
    always @* begin
        case (op)
            2'b00: y = a + b;
            2'b01: y = a - b;
            2'b10: y = {1'b0, a & b};
            2'b11: y = {1'b0, a | b};
        endcase
    end
endmodule
`,
  },
  {
    slug: "fifo_sync",
    title: "Synchronous FIFO",
    difficulty: "intermediate",
    topModule: "fifo",
    known: true,
    starterRtl: `module fifo #(parameter DEPTH = 8, WIDTH = 8) (
    input  wire             clk,
    input  wire             rst_n,
    input  wire             wr_en,
    input  wire [WIDTH-1:0] din,
    input  wire             rd_en,
    output reg  [WIDTH-1:0] dout,
    output wire             full,
    output wire             empty
);
    // student to implement
endmodule
`,
  },
  {
    slug: "uart_tx",
    title: "UART TX Mini",
    difficulty: "advanced",
    topModule: "uart_tx",
    known: true,
    starterRtl: `module uart_tx (
    input  wire       clk,
    input  wire       rst_n,
    input  wire [7:0] data,
    input  wire       send,
    output reg        tx,
    output reg        busy
);
    // student to implement (8N1, 16 cycles per bit)
endmodule
`,
  },
];

// ── LINT (port of run_lint) ──
export function runLint(rtl: string, topModule: string): LintResult {
  const log: string[] = ["Verilator (mock) lint started", `-- Top module: ${topModule}`, "-- Parsing top.sv"];
  const errors: LintIssue[] = [];
  const warnings: LintIssue[] = [];

  if (!rtl.trim()) errors.push({ line: 1, severity: "error", message: "Empty RTL source" });
  if (!/^\s*module\s+\w+/m.test(rtl)) errors.push({ line: 1, severity: "error", message: "No module declaration found" });

  const openB = (rtl.match(/\bbegin\b/g) ?? []).length;
  // NOTE: plain substring counts, faithful to the Python original — "end"
  // inside "endmodule"/"endcase" IS counted, which is what makes the
  // begin/end balance come out right for well-formed code.
  const closeB =
    (rtl.match(/end/g) ?? []).length -
    (rtl.match(/endmodule/g) ?? []).length -
    (rtl.match(/endcase/g) ?? []).length -
    (rtl.match(/endgenerate/g) ?? []).length;
  if (openB > closeB) errors.push({ line: 0, severity: "error", message: `Unmatched begin/end (${openB}/${closeB})` });

  if (!rtl.trimEnd().endsWith("endmodule")) warnings.push({ line: 0, severity: "warning", message: "Source does not end with endmodule" });
  if (!rtl.includes("always_ff") && !rtl.includes("always @")) warnings.push({ line: 0, severity: "warning", message: "No sequential block detected" });

  log.push(`-- ${errors.length} error(s), ${warnings.length} warning(s)`, "Done.");
  return { status: errors.length ? "failed" : "success", errors, warnings, log: log.join("\n") };
}

// ── SIMULATION (port of _signals_for_top + _generate_generic_vcd + coverage) ──
const SIGNAL_PRESETS: Record<string, [string, number][]> = {
  counter4: [["clk", 1], ["rst_n", 1], ["en", 1], ["count", 4]],
  alu: [["a", 4], ["b", 4], ["op", 2], ["y", 5]],
  fifo: [["clk", 1], ["rst_n", 1], ["wr_en", 1], ["rd_en", 1], ["din", 8], ["dout", 8], ["full", 1], ["empty", 1]],
  uart_tx: [["clk", 1], ["rst_n", 1], ["data", 8], ["send", 1], ["tx", 1], ["busy", 1]],
};

function signalsForTop(top: string, rtl: string): [string, number][] {
  if (SIGNAL_PRESETS[top]) return SIGNAL_PRESETS[top];
  const out: [string, number][] = [];
  const re = /\b(input|output)\b\s+(?:wire|reg)?\s*(?:\[(\d+):0\])?\s*(\w+)/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(rtl)) && out.length < 12) out.push([m[3], m[2] ? parseInt(m[2], 10) + 1 : 1]);
  return out.length ? out : [["clk", 1], ["data", 8]];
}

// Role-based heuristic waveform — each signal gets a plausible trace (clk
// toggles, rst_n releases after reset, counters increment on rising edges…)
// so any mission shows meaningful waves without a real simulator.
function generateWaveform(top: string, signals: [string, number][], periodNs = 10, cycles = 24): Waveform {
  const end = periodNs * cycles;
  const half = Math.max(1, Math.floor(periodNs / 2));
  const rstDoneAt = periodNs * 4;
  const wav: WaveSignal[] = signals.map(([name, width]) => ({
    name,
    width,
    transitions: [[0, width === 1 ? "0" : "0".repeat(width)]],
  }));
  const byName = new Map(wav.map((s) => [s.name, s]));
  const push = (name: string, t: number, v: string) => {
    const s = byName.get(name)!;
    if (s.transitions[s.transitions.length - 1][1] !== v) s.transitions.push([t, v]);
  };

  const instrSeq = [0x00500093, 0x00300113, 0x002081b3, 0x40208233, 0x0020f2b3, 0x00302023, 0x00002303, 0x00618463];
  let count = 0;
  let pc = 0;
  let addr = 0x10;
  let instrIdx = 0;

  for (let i = 1; i <= cycles * 2; i++) {
    const t = i * half;
    const phase = (i - 1) % 2; // 0 = falling, 1 = rising
    const afterRst = t > rstDoneAt;
    for (const [name, w] of signals) {
      const ln = name.toLowerCase();
      let v: string | null = null;
      if (ln === "clk" || ln === "clock") v = String(phase);
      else if (ln === "rst_n" || ln === "resetn" || ln === "rstn") v = t >= rstDoneAt ? "1" : "0";
      else if (ln === "rst" || ln === "reset") v = t >= rstDoneAt ? "0" : "1";
      else if (ln === "en" || ln === "enable" || ln === "valid" || ln === "send") v = t >= rstDoneAt ? "1" : "0";
      else if (phase === 1 && afterRst) {
        if (ln === "count" || ln === "counter") {
          count = (count + 1) & ((1 << w) - 1);
          v = count.toString(2).padStart(w, "0");
        } else if (ln === "a" || ln === "b" || ln === "op" || ln === "din") {
          // combinational stimulus walk — keeps ALU/FIFO input buses live
          const step = (i - 1) / 2;
          const mult = ln === "b" ? 3 : ln === "op" ? 5 : 1;
          v = ((step * mult) & ((1 << w) - 1)).toString(2).padStart(w, "0");
        } else if (ln === "pc") {
          pc = (pc + 4) & ((1 << w) - 1);
          v = pc.toString(2).padStart(w, "0");
        } else if (ln.includes("instr")) {
          const val = instrSeq[instrIdx++ % instrSeq.length] & ((1 << w) - 1);
          v = val.toString(2).padStart(w, "0");
        } else if (ln.includes("addr")) {
          addr = (addr + 4) & ((1 << w) - 1);
          v = addr.toString(2).padStart(w, "0");
        } else if (ln.includes("data") || ["y", "result", "out", "tx", "dout"].includes(ln)) {
          if (w === 1) v = Math.floor(i / 2) % 3 === 0 ? "1" : "0";
          else v = ((i * 7) & ((1 << w) - 1)).toString(2).padStart(w, "0");
        } else if (ln === "full" || ln === "busy") {
          v = Math.floor(i / 2) % 8 === 7 ? "1" : "0";
        } else if (ln === "empty") {
          v = Math.floor(i / 2) % 8 === 0 ? "1" : "0";
        }
      }
      if (v !== null) push(name, t, v);
    }
  }
  void top;
  return { timescale: "1ns", end_time: end, signals: wav };
}

const SCENARIO_PRESETS: Record<string, Scenario[]> = {
  counter4: [
    { name: "reset_then_count", description: "rst_n 해제 후 en=1로 16사이클 카운팅", expected_pass: true },
    { name: "rollover", description: "0xF → 0x0 wrap-around 동작 확인", expected_pass: true },
    { name: "enable_pause", description: "en=0일 때 카운트 정지 확인", expected_pass: true },
    { name: "async_reset_mid", description: "카운팅 중 비동기 reset 0 즉시 적용", expected_pass: true },
  ],
  alu: [
    { name: "ADD_basic", description: "0x3 + 0x5 = 0x8", expected_pass: true },
    { name: "SUB_borrow", description: "0x1 - 0x3 borrow", expected_pass: true },
    { name: "AND_OR", description: "비트 연산 코너", expected_pass: true },
    { name: "overflow", description: "ADD에서 5번째 비트 캐리아웃", expected_pass: true },
  ],
  fifo: [
    { name: "write_then_read", description: "8개 push, 8개 pop 일치 확인", expected_pass: true },
    { name: "full_flag", description: "DEPTH개 push 시 full=1", expected_pass: true },
    { name: "empty_flag", description: "초기 empty=1", expected_pass: true },
    { name: "simultaneous_rw", description: "동시 wr_en+rd_en 시 동작", expected_pass: true },
  ],
  uart_tx: [
    { name: "byte_send", description: "1바이트 송신 후 busy 해제", expected_pass: true },
    { name: "back_to_back", description: "연속 2바이트 송신", expected_pass: true },
  ],
};

export function runSimulation(rtl: string, topModule: string): SimResult {
  const log: string[] = ["Verilator (mock) sim started", `-- Top: ${topModule}`, "-- Compiling RTL + TB"];
  const broken = !/^\s*module\s+\w+/m.test(rtl);
  if (broken) {
    log.push("-- COMPILATION FAILED", "Simulation aborted.");
    return {
      status: "failed",
      waveform: null,
      coverage: { line: 0, toggle: 0, branch: 0, fsm: 0, overall: 0 },
      scenarios: [],
      testCount: 0,
      passed: 0,
      failed: 0,
      log: log.join("\n"),
    };
  }
  const sigs = signalsForTop(topModule, rtl);
  const waveform = generateWaveform(topModule, sigs);
  const rtlLines = Math.max(1, rtl.split("\n").length);
  const lineCov = round(Math.min(0.95, 0.55 + sigs.length * 0.04 - rtlLines / 2000));
  const coverage = {
    line: lineCov,
    toggle: round(Math.min(0.92, lineCov - 0.05 - rtlLines / 4000)),
    branch: round(Math.min(0.9, lineCov - 0.1)),
    fsm: round(Math.min(0.95, lineCov + 0.02)),
    overall: 0,
  };
  coverage.overall = round((coverage.line + coverage.toggle + coverage.branch + coverage.fsm) / 4);
  const scenarios = SCENARIO_PRESETS[topModule] ?? [
    { name: "default", description: "기본 시나리오", expected_pass: true },
  ];
  const passed = scenarios.filter((s) => s.expected_pass).length;
  log.push(
    `-- Tests: ${passed}/${scenarios.length} passed`,
    `-- Coverage: line ${(coverage.line * 100).toFixed(1)}% / toggle ${(coverage.toggle * 100).toFixed(1)}% / branch ${(coverage.branch * 100).toFixed(1)}% / fsm ${(coverage.fsm * 100).toFixed(1)}%`,
    "Simulation finished OK.",
  );
  return {
    status: "success",
    waveform,
    coverage,
    scenarios,
    testCount: scenarios.length,
    passed,
    failed: scenarios.length - passed,
    log: log.join("\n"),
  };
}

// ── SYNTHESIS (port of _mock_cells_by_type + run_synthesis) ──
function mockCellsByType(rtl: string, flops: number, luts: number): Record<string, number> {
  const clean = rtl.replace(/\/\/.*$|\/\*[\s\S]*?\*\/|"[^"]*"/gm, "");
  const count = (re: RegExp) => (clean.match(re) ?? []).length;
  const weights: Record<string, number> = {
    "$_AND_": count(/&/g) - count(/&&/g) * 2,
    "$_OR_": count(/\|/g) - count(/\|\|/g) * 2,
    "$_XOR_": count(/\^/g),
    "$_NOT_": count(/~/g) + count(/!/g),
    "$_MUX_": count(/\?/g) + count(/\bcase\b/g),
    "$_NAND_": count(/==|!=|<|>/g),
  };
  for (const k of Object.keys(weights)) weights[k] = Math.max(0, weights[k]);
  if (Object.values(weights).reduce((a, b) => a + b, 0) === 0) {
    weights["$_AND_"] = 1;
    weights["$_OR_"] = 1;
    weights["$_NOT_"] = 1;
  }
  const total = Object.values(weights).reduce((a, b) => a + b, 0);
  const out: Record<string, number> = {};
  let remaining = Math.max(0, luts);
  const items = Object.entries(weights).sort((a, b) => b[1] - a[1]);
  items.forEach(([k, w], i) => {
    const n = i === items.length - 1 ? remaining : Math.min(round0((luts * w) / total), remaining);
    if (n > 0) {
      out[k] = n;
      remaining -= n;
    }
  });
  if (flops > 0) out["$_DFF_PP_"] = flops;
  return out;
}

const round0 = (v: number) => Math.round(v);

export function runSynthesis(rtl: string, topModule: string, clockPeriodNs: number): SynthResult {
  const log: string[] = ["Yosys (mock) synthesis started", `read_verilog ${topModule}.sv`, `synth -top ${topModule}`, "stat"];
  if (!/^\s*module\s+\w+/m.test(rtl)) {
    return {
      status: "failed",
      gateCount: 0, cellCount: 0, flopCount: 0, lutCount: 0, cellsByType: {},
      areaUm2: 0,
      areaBreakdown: { combinationalUm2: 0, sequentialUm2: 0, interconnectUm2: 0, totalUm2: 0 },
      power: { dynamicMw: 0, leakageUw: 0, totalMw: 0, frequencyMhz: 0 },
      clockPeriodNs, timingSlackNs: 0, warnings: [], criticalPaths: [],
      log: [...log, "ERROR: No module found"].join("\n"),
    };
  }
  const lines = rtl.split("\n").length;
  const baseCells = Math.max(8, Math.floor(lines / 2));
  const flops = (rtl.match(/always_ff/g) ?? []).length + (rtl.match(/always @/g) ?? []).length;
  const luts = baseCells * 2 + 4;
  const gateCount = luts + flops * 6;
  const cellsByType = mockCellsByType(rtl, flops, luts);

  const comboArea = round(luts * 1.1, 2);
  const seqArea = round(flops * 7.2, 2);
  const interconnect = round((comboArea + seqArea) * 0.18, 2);
  const totalArea = round(comboArea + seqArea + interconnect, 2);

  const freqGhz = 1.0 / Math.max(0.5, clockPeriodNs);
  const activity = 0.15;
  const capPf = gateCount * 0.012;
  const vdd = 0.9;
  const dynamicMw = round(capPf * vdd * vdd * freqGhz * 1000 * activity);
  const leakageUw = round(gateCount * 0.05, 2);
  const totalMw = round(dynamicMw + leakageUw / 1000);

  const rng = mulberry32(strSeed(topModule));
  const slack = round(clockPeriodNs - (2.1 + rng() * 1.3));
  const critPaths = criticalPathsFor(topModule, clockPeriodNs, slack);

  log.push(
    `=== ${topModule} ===`,
    `  Number of cells:     ${baseCells}`,
    `  Number of FFs:       ${flops}`,
    `  Number of LUTs:      ${luts}`,
    `  Estimated area:      ${totalArea} um^2`,
    `  Slack:               ${slack} ns`,
    "Done.",
  );
  return {
    status: "success",
    gateCount,
    cellCount: baseCells,
    flopCount: flops,
    lutCount: luts,
    cellsByType,
    areaUm2: totalArea,
    areaBreakdown: {
      combinationalUm2: comboArea,
      sequentialUm2: seqArea,
      interconnectUm2: interconnect,
      totalUm2: totalArea,
    },
    power: { dynamicMw, leakageUw, totalMw, frequencyMhz: round(1000 / clockPeriodNs, 1) },
    clockPeriodNs,
    timingSlackNs: slack,
    warnings: flops === 0 ? ["mock: latch inferred for x"] : [],
    criticalPaths: critPaths,
    log: log.join("\n"),
  };
}

// Port of _generate_critical_paths — worst path's slack equals the reported
// synthesis slack so the STA table and the synth KPIs agree.
function criticalPathsFor(top: string, clockPeriod: number, slack: number): CriticalPath[] {
  const presets: Record<string, [string, string, string[]][]> = {
    counter4: [
      ["count[3]/Q", "count[3]/D", ["count[3]/CLK", "ADD4/co", "MUX/sel", "count[3]/D"]],
      ["count[2]/Q", "count[2]/D", ["count[2]/CLK", "ADD4/s2", "count[2]/D"]],
      ["rst_n", "count[0]/D", ["rst_n", "AND2/y", "count[0]/D"]],
    ],
    alu: [
      ["a[3]", "y[4]", ["a[3]", "ADD/co", "y[4]"]],
      ["op[1]", "y[3]", ["op[1]", "MUX/sel", "y[3]"]],
    ],
    fifo: [
      ["din[7]/Q", "dout[7]/D", ["din[7]/Q", "RAM/wr", "RAM/rd", "dout[7]/D"]],
      ["wr_ptr[2]/Q", "full", ["wr_ptr[2]/Q", "CMP/eq", "full"]],
    ],
  };
  const raw = presets[top] ?? [
    ["clk", "out", ["clk", "logic", "out"]],
    ["in[0]", "out", ["in[0]", "logic", "out"]],
  ];
  const rng = mulberry32(strSeed(top));
  return raw.map(([start, end, stages], i) => {
    const pathSlack = i === 0 ? slack : round(slack + (0.4 + rng() * 2.1) * (i + 1));
    const delay = round(clockPeriod - pathSlack);
    return {
      id: i,
      startpoint: start,
      endpoint: end,
      stages,
      delayNs: delay,
      slackNs: pathSlack,
      cellDelayNs: round(delay * 0.55),
      netDelayNs: round(delay * 0.45),
      status: pathSlack >= 0 ? "MET" : "VIOLATED",
    };
  });
}

// ── PLACE & ROUTE (port of run_place_route mock + merged_floorplan clamps) ──
export const DEFAULT_FLOORPLAN: FloorplanConfig = {
  dieW: 12.0,
  dieD: 8.0,
  utilization: 0.55,
  numMacros: 3,
  padDensity: "medium",
  powerGridPitch: 1.5,
  signalRoutingDensity: 0.6,
};

const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v));

export function mergedFloorplan(cfg: Partial<FloorplanConfig> | null): FloorplanConfig {
  const c = { ...DEFAULT_FLOORPLAN, ...(cfg ?? {}) };
  return {
    dieW: clamp(c.dieW, 6, 18),
    dieD: clamp(c.dieD, 4, 14),
    utilization: clamp(c.utilization, 0.3, 0.9),
    numMacros: clamp(Math.round(c.numMacros), 0, 4),
    padDensity: ["low", "medium", "high"].includes(c.padDensity) ? c.padDensity : "medium",
    powerGridPitch: clamp(c.powerGridPitch, 0.7, 3.5),
    signalRoutingDensity: clamp(c.signalRoutingDensity, 0.1, 1.0),
  };
}

export function runPlaceRoute(topModule: string, fp: FloorplanConfig): PnrResult {
  const dieArea = fp.dieW * fp.dieD * 100;
  const coreArea = dieArea * fp.utilization * 0.78;
  const placedCells = Math.max(0, Math.round(60 + fp.utilization * fp.signalRoutingDensity * 200 - fp.numMacros * 10));
  const routedNets = Math.round(40 + fp.signalRoutingDensity * 200);
  const drc =
    fp.signalRoutingDensity < 0.85 && fp.utilization < 0.85
      ? 0
      : Math.max(0, Math.round((fp.signalRoutingDensity + fp.utilization - 1.6) * 8));
  const wns = round(0.5 - fp.utilization * 1.3 - fp.signalRoutingDensity * 0.5 + 0.4);
  const tns = wns < 0 ? round(wns * 4.2) : 0;
  const log = [
    "OpenROAD (mock) P&R complete",
    `-- die:    ${fp.dieW} x ${fp.dieD} (${Math.round(dieArea)} um^2)`,
    `-- core:   ${Math.round(coreArea)} um^2 @ util ${fp.utilization}`,
    `-- placed: ${placedCells} cells, ${routedNets} nets`,
    `-- WNS:    ${wns} ns / TNS ${tns} ns`,
    `-- DRC:    ${drc} violations`,
    `Top module: ${topModule}`,
  ].join("\n");
  return {
    dieAreaUm2: round(dieArea, 1),
    coreAreaUm2: round(coreArea, 1),
    utilization: fp.utilization,
    placedCells,
    routedNets,
    macros: fp.numMacros,
    wnsNs: wns,
    tnsNs: tns,
    drcViolations: drc,
    log,
  };
}
