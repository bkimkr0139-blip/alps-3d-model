// 3D scene data builders — TypeScript port of AgentIC's Unity scene builder
// (apps/api/app/services/unity/scene_builder.py). The original emitted
// Unity-MCP commands (manage_gameobject / manage_material) that a Unity
// Editor executed; here the exact same geometry is produced as plain box
// specs rendered directly by react-three-fiber — no Unity, no MCP, no
// server. Geometry, colors, layout algorithms and naming conventions are
// kept 1:1 so the training content is unchanged.
import { mulberry32, strSeed, type FloorplanConfig, type SynthResult } from "./edaRunner";

export type RGB = [number, number, number];

export type EdaBox = {
  name: string;
  /** layer key — drives explode grouping + visibility toggle */
  layer: string;
  pos: [number, number, number];
  size: [number, number, number];
  color: RGB;
  cyl?: boolean;
  emissive?: number;
  metalness?: number;
  roughness?: number;
  opacity?: number;
};

export type EdaLegendEntry = { key: string; label: string; color: RGB; count: number };

export type EdaScene = {
  mode: "synthesis" | "layout" | "process" | "package";
  boxes: EdaBox[];
  legend: EdaLegendEntry[];
  /** process mode only — ordered step keys for the build-up slider */
  steps?: string[];
  /** per-layer explode anchors; default is each layer's min box y */
  explodeAnchors?: Record<string, number>;
  /** studio lighting — generated env map + contact shadow so polished
   *  metal reads as metal (photoreal scenes; no HDR assets, all local) */
  studio?: boolean;
  /** suggested orbit target + camera distance for framing */
  target: [number, number, number];
  distance: number;
};

// ── Layer registry (natural Y heights; explode multiplies the separation) ──
export const LAYER_REGISTRY: { key: string; y: number; color: RGB }[] = [
  { key: "die", y: 0.0, color: [0.05, 0.06, 0.09] },
  { key: "core", y: 0.22, color: [0.07, 0.1, 0.18] },
  { key: "diff", y: 0.26, color: [0.55, 0.32, 0.18] },
  { key: "poly", y: 0.29, color: [0.85, 0.3, 0.4] },
  { key: "cell", y: 0.31, color: [0.18, 0.22, 0.34] },
  { key: "macro", y: 0.32, color: [0.2, 0.55, 0.78] },
  { key: "M1", y: 0.36, color: [0.3, 0.55, 0.95] },
  { key: "via1", y: 0.39, color: [0.96, 0.85, 0.32] },
  { key: "M2", y: 0.42, color: [0.95, 0.4, 0.4] },
  { key: "via2", y: 0.45, color: [0.96, 0.85, 0.32] },
  { key: "M3", y: 0.48, color: [0.3, 0.85, 0.55] },
  { key: "via3", y: 0.51, color: [0.96, 0.85, 0.32] },
  { key: "M4", y: 0.54, color: [0.95, 0.65, 0.25] },
  { key: "via4", y: 0.57, color: [0.96, 0.85, 0.32] },
  { key: "M5", y: 0.6, color: [0.55, 0.3, 0.85] },
  { key: "via5", y: 0.63, color: [0.96, 0.85, 0.32] },
  { key: "M6", y: 0.66, color: [0.85, 0.85, 0.3] },
  { key: "seal", y: 0.7, color: [0.66, 0.55, 0.22] },
  { key: "pad", y: 0.74, color: [0.96, 0.78, 0.31] },
  { key: "drc", y: 1.4, color: [0.27, 0.86, 0.46] },
];
const LAYER_Y = Object.fromEntries(LAYER_REGISTRY.map((l) => [l.key, l.y])) as Record<string, number>;
const LAYER_COLOR = Object.fromEntries(LAYER_REGISTRY.map((l) => [l.key, l.color])) as Record<string, RGB>;

// ── Per-mission silicon profile ────────────────────────────────────────
// The Python original drew one generic sample die for every project. The
// training missions now represent the workbench's own product silicon
// (see MISSIONS in edaRunner.ts), so each mission carries the chip
// identity of the product block it models: die footprint, floorplan
// defaults, real floorplan macros (functional blocks), an analog AFE
// island and a memory array. The builders key off mission.slug via
// silProfileOf(); unknown slugs keep the old generic sample.
export type SilMacro = [label: string, w: number, d: number, color: RGB, fx: number, fz: number];

type SilAnalog = {
  label: string;
  w: number;
  d: number;
  /** region center as a fraction of the process-scene die (−0.5..0.5) */
  fx: number;
  fz: number;
  /** touch-style electrode combs (top metal, 0 = no touch front-end) */
  electrodes: number;
  /** MIM cap pairs (FEOL analog structures) */
  caps: number;
  /** poly resistor serpentine segments */
  res: number;
};
type SilMem = { label: string; cols: number; rows: number; fx: number; fz: number };

export type SilProfile = {
  /** training part code — heuristic label for the twin (◈-class data) */
  chip: string;
  /** process-scene die footprint (scene units) */
  dieW: number;
  dieD: number;
  /** synthesis floor aspect (w/d) — the product's die proportion */
  aspect: number;
  /** floorplan defaults merged over DEFAULT_FLOORPLAN */
  fp: Partial<FloorplanConfig>;
  /** floorplan macro catalog; fp.numMacros picks the first N */
  macros: SilMacro[];
  /** analog front-end island (mixed-signal missions only) */
  analog?: SilAnalog;
  /** dense memory array (process scene) */
  mem?: SilMem;
  /** bond-pad counts: tb = per top/bottom edge, side = per left edge */
  pads: { tb: number; side: number };
};

export const SIL_PROFILES: Record<string, SilProfile> = {
  // TACT-DB4 — pure-digital contact-filter block: small die, no analog.
  counter_4bit: {
    chip: "TACT-DB4",
    dieW: 9.5,
    dieD: 7.0,
    aspect: 1.3,
    fp: { dieW: 6, dieD: 4.5, numMacros: 1, padDensity: "low" },
    macros: [
      ["DEBCNT", 2.2, 1.4, [0.96, 0.62, 0.1], -0.22, -0.2],
      ["SYNC2", 1.2, 1.0, [0.55, 0.3, 0.85], 0.3, 0.28],
      ["EDGDET", 1.3, 1.0, [0.3, 0.85, 0.55], 0.28, -0.25],
      ["KEYIF", 1.4, 1.1, [0.65, 0.3, 0.65], -0.25, 0.3],
    ],
    pads: { tb: 4, side: 1 },
  },
  // TCH-ALU4 — touch snap judgement: digital ALU + capacitive AFE island.
  alu_4bit: {
    chip: "TCH-ALU4",
    dieW: 11.0,
    dieD: 8.0,
    aspect: 1.35,
    fp: { dieW: 7, dieD: 5.5, numMacros: 2, padDensity: "medium" },
    macros: [
      ["TOUCH_AFE", 2.0, 1.6, [0.1, 0.65, 0.6], -0.24, 0.0],
      ["ALU4", 2.2, 1.4, [0.13, 0.83, 0.93], 0.24, -0.24],
      ["SNAPCTL", 1.6, 1.2, [0.96, 0.62, 0.1], 0.26, 0.26],
      ["REGF", 1.4, 1.1, [0.65, 0.3, 0.65], -0.24, 0.3],
    ],
    analog: { label: "TOUCH_AFE", w: 2.6, d: 2.2, fx: -0.26, fz: 0.05, electrodes: 8, caps: 6, res: 4 },
    pads: { tb: 6, side: 2 },
  },
  // AFE-FIFO — AFE sample ring buffer: AFE island + dense ring RAM.
  fifo_sync: {
    chip: "AFE-FIFO",
    dieW: 12.0,
    dieD: 8.5,
    aspect: 1.4,
    fp: { dieW: 8, dieD: 6, numMacros: 2, padDensity: "medium", utilization: 0.6 },
    macros: [
      ["AFE", 1.9, 1.5, [0.1, 0.65, 0.6], -0.26, 0.0],
      ["RING_RAM", 2.6, 1.6, [0.2, 0.55, 0.78], 0.24, -0.22],
      ["RDPTR", 1.2, 1.0, [0.96, 0.62, 0.1], 0.28, 0.28],
      ["WRPTR", 1.2, 1.0, [0.96, 0.45, 0.1], -0.26, 0.3],
    ],
    analog: { label: "AFE", w: 2.4, d: 2.0, fx: -0.28, fz: 0.05, electrodes: 0, caps: 8, res: 3 },
    mem: { label: "RING_RAM", cols: 10, rows: 6, fx: 0.24, fz: -0.18 },
    pads: { tb: 7, side: 2 },
  },
  // SNS-UART — sensor UART TX: narrow SOIC-style die, AFE + serial logic.
  uart_tx: {
    chip: "SNS-UART",
    dieW: 13.0,
    dieD: 7.5,
    aspect: 1.6,
    fp: { dieW: 8.5, dieD: 5.5, numMacros: 2, padDensity: "medium" },
    macros: [
      ["AFE", 1.9, 1.5, [0.1, 0.65, 0.6], -0.3, 0.0],
      ["TX_SHFT", 2.0, 1.2, [0.13, 0.83, 0.93], 0.26, -0.22],
      ["BAUD16", 1.5, 1.1, [0.55, 0.3, 0.85], 0.28, 0.26],
      ["PCTL", 1.3, 1.0, [0.96, 0.62, 0.1], -0.28, 0.3],
    ],
    analog: { label: "AFE", w: 2.6, d: 2.0, fx: -0.3, fz: 0.0, electrodes: 0, caps: 6, res: 5 },
    pads: { tb: 7, side: 2 },
  },
  // AFE-SOC1 — AFE/SoC control core: largest die, AFE + RISC + memories.
  risc32: {
    chip: "AFE-SOC1",
    dieW: 15.0,
    dieD: 11.0,
    aspect: 1.35,
    fp: { dieW: 12, dieD: 9, numMacros: 3, padDensity: "high", utilization: 0.65 },
    macros: [
      ["AFE", 1.9, 1.5, [0.1, 0.65, 0.6], -0.3, 0.0],
      ["RISC_CORE", 2.6, 1.8, [0.96, 0.62, 0.1], 0.22, -0.24],
      ["SRAM32K", 2.4, 1.6, [0.2, 0.55, 0.78], 0.24, 0.28],
      ["BOOT_ROM", 1.8, 1.2, [0.65, 0.3, 0.65], -0.28, 0.3],
    ],
    analog: { label: "AFE", w: 2.6, d: 2.2, fx: -0.3, fz: 0.05, electrodes: 0, caps: 8, res: 4 },
    mem: { label: "SRAM32K", cols: 12, rows: 8, fx: 0.24, fz: -0.16 },
    pads: { tb: 10, side: 3 },
  },
};

const GENERIC_PROFILE: SilProfile = {
  chip: "GEN-EDA",
  dieW: 12.5,
  dieD: 8.5,
  aspect: 1.0,
  fp: {},
  macros: [
    ["SRAM", 2.8, 1.8, [0.2, 0.55, 0.78], -0.33, 0.28],
    ["REGS", 2.4, 1.6, [0.65, 0.3, 0.65], 0.3, -0.28],
    ["PLL", 1.8, 1.3, [0.25, 0.7, 0.5], -0.36, -0.3],
    ["DSP", 2.0, 1.4, [0.85, 0.45, 0.2], 0.33, 0.3],
  ],
  pads: { tb: 8, side: 2 },
};

export function silProfileOf(slug: string): SilProfile {
  return SIL_PROFILES[slug] ?? GENERIC_PROFILE;
}

// ── Synthesis scene — per-cell-type cluster diagram ──
// Port of build_synthesis_scene: every cell from the yosys-style
// cells_by_type breakdown becomes a cube, grouped into ⌈√N⌉×⌈N/⌈√N⌉⌉ blocks
// per gate type, strip-packed left-to-right. Sequential cells first, then
// combinational by frequency. Row silkscreens (label bars) sit in front of
// each block; KPI bars (gates/area/slack) stand on the right edge.
const GATE_PALETTE: Record<string, RGB> = {
  "$_DFF_PP_": [0.96, 0.62, 0.1], "$_DFF_NP_": [0.96, 0.55, 0.1],
  "$_DFF_PN_": [0.96, 0.5, 0.1], "$_DFFE_PP_": [0.96, 0.45, 0.05],
  "$_LATCH_": [0.85, 0.4, 0.05],
  "$_AND_": [0.13, 0.83, 0.93], "$_NAND_": [0.2, 0.65, 0.85],
  "$_OR_": [0.3, 0.85, 0.55], "$_NOR_": [0.2, 0.7, 0.45],
  "$_XOR_": [0.55, 0.78, 0.3], "$_XNOR_": [0.45, 0.65, 0.25],
  "$_NOT_": [0.94, 0.3, 0.45],
  "$_MUX_": [0.55, 0.3, 0.85], "$_NMUX_": [0.45, 0.25, 0.7],
  "$_BUF_": [0.6, 0.65, 0.78],
  $lut: [0.13, 0.83, 0.93], "$_LUT_": [0.13, 0.83, 0.93],
};

export function gateColor(cellType: string): RGB {
  if (GATE_PALETTE[cellType]) return GATE_PALETTE[cellType];
  const up = cellType.toUpperCase();
  if (up.includes("DFF") || up.includes("FF") || up.includes("LATCH")) return GATE_PALETTE["$_DFF_PP_"];
  if (up.includes("MUX")) return GATE_PALETTE["$_MUX_"];
  if (up.includes("NAND")) return GATE_PALETTE["$_NAND_"];
  if (up.includes("AND")) return GATE_PALETTE["$_AND_"];
  if (up.includes("NOR")) return GATE_PALETTE["$_NOR_"];
  if (up.includes("OR")) return GATE_PALETTE["$_OR_"];
  if (up.includes("XOR")) return GATE_PALETTE["$_XOR_"];
  if (up.includes("NOT") || up.includes("INV")) return GATE_PALETTE["$_NOT_"];
  if (up.includes("BUF")) return GATE_PALETTE["$_BUF_"];
  if (up.includes("LUT")) return GATE_PALETTE.$lut;
  return [0.55, 0.65, 0.78];
}

export function shortGateLabel(cellType: string): string {
  const s = cellType.replace(/^\$_|_\$$/g, "").replace(/\$/g, "").toUpperCase();
  for (const tok of ["DFFE", "DFF", "LATCH", "NAND", "NOR", "XNOR", "XOR", "AND", "OR", "NOT", "INV", "MUX", "NMUX", "BUF", "LUT"]) {
    if (s.includes(tok)) return tok;
  }
  return s.slice(0, 6) || "?";
}

// ── Synthesis scene — placed-die industrial model ──────────────────────
// Gate-type clusters are rendered the way a placement viewer shows real
// silicon, not toy cubes: each type is a placed region of standard-cell
// ROWS bounded by M1 VDD/VSS power rails, dressed with copper M2 and
// silver M3 routes stitched by gold vias, all on a lidded die substrate
// framed by a gold seal ring and photolithography alignment keys.
// Materials are polished metal lit by the generated studio env (studio:
// true) so the die reads as inspected silicon under review lighting.
export function buildSynthesisScene(report: SynthResult, projectTitle: string): EdaScene {
  const cells = Math.max(1, report.cellCount || 8);
  const flops = report.flopCount;
  const luts = report.lutCount;
  const gateCount = report.gateCount || cells;
  const area = report.areaUm2;
  const slack = report.timingSlackNs;

  // Fallback for reports without a per-type breakdown (mirrors the builder).
  let cellsByType: Record<string, number> = { ...report.cellsByType };
  if (Object.keys(cellsByType).length === 0) {
    cellsByType = {};
    if (flops > 0) cellsByType["$_DFF_PP_"] = flops;
    if (luts > 0) cellsByType.$lut = luts;
    const leftover = Math.max(0, cells - flops - luts);
    if (leftover > 0) cellsByType["$_BUF_"] = leftover;
  }

  const isSeq = (t: string) => {
    const u = t.toUpperCase();
    return u.includes("DFF") || u.includes("FF") || u.includes("LATCH");
  };
  const types = Object.entries(cellsByType)
    .filter(([, n]) => n > 0)
    .sort((a, b) => (isSeq(a[0]) === isSeq(b[0]) ? b[1] - a[1] : isSeq(a[0]) ? -1 : 1));

  type Block = { type: string; count: number; disp: number; tw: number; td: number; color: RGB; label: string };
  // Render cap per type — rows + rails + routing cost ~1.4 meshes per cell,
  // so the cap keeps a 544-FF core (AFE-SOC1) inside a smooth mesh budget;
  // the true count stays in the label/legend.
  const CAP = 96;
  const blocks: Block[] = types.map(([type, n]) => ({
    type,
    count: n,
    disp: Math.min(n, CAP),
    tw: Math.max(1, Math.ceil(Math.sqrt(Math.min(n, CAP)))),
    td: 0,
    color: gateColor(type),
    label: shortGateLabel(type),
  }));
  for (const b of blocks) b.td = Math.max(1, Math.ceil(b.disp / b.tw));

  // Strip-pack: left-to-right, wrap when the running width exceeds MAX.
  const PITCH = 1.05; // standard-cell row pitch (toy cubes used 1.4)
  const INTRA = 1.6;
  const INTER = 2.0;
  const totalCells = Math.max(1, blocks.reduce((a, b) => a + b.count, 0));
  const targetSide = Math.max(4, Math.ceil(Math.sqrt(totalCells * 1.5)));
  const MAX_STRIP_W = Math.max(6, Math.min(20, targetSide + 2));

  const strips: Block[][] = [[]];
  const stripWidths: number[] = [0];
  for (const b of blocks) {
    const cur = stripWidths[stripWidths.length - 1];
    if (strips[strips.length - 1].length && cur + INTRA + b.tw > MAX_STRIP_W) {
      strips.push([b]);
      stripWidths.push(b.tw);
    } else {
      strips[strips.length - 1].push(b);
      stripWidths[stripWidths.length - 1] = cur + (strips[strips.length - 1].length > 1 ? INTRA : 0) + b.tw;
    }
  }
  const stripDepths = strips.map((s) => Math.max(1, ...s.map((b) => b.td)));
  const totalWCubes = Math.max(1, ...stripWidths);
  const totalDCubes = stripDepths.reduce((a, b) => a + b, 0) + INTER * (strips.length - 1);
  // The floor plane follows the product's die aspect (silProfileOf), so a
  // narrow sensor die and a square SoC no longer share the same slab — the
  // unused margin is the chip's real floorplan headroom.
  const prof = silProfileOf(projectTitle);
  const floorW = totalWCubes * PITCH * prof.aspect + 2.0;
  const floorD = totalDCubes * PITCH + 1.5;

  const rng = mulberry32(strSeed(projectTitle));
  const boxes: EdaBox[] = [];

  // Die substrate: silicon base + lapped lid (top at y 0.18) + gold seal
  // ring around the active area + corner alignment keys.
  boxes.push({
    name: "eda_die_Base",
    layer: "die",
    pos: [0, 0, 0],
    size: [floorW, 0.22, floorD],
    color: [0.09, 0.11, 0.16],
    metalness: 0.45,
    roughness: 0.5,
  });
  boxes.push({
    name: "eda_die_Lid",
    layer: "die",
    pos: [0, 0.145, 0],
    size: [floorW - 0.36, 0.07, floorD - 0.36],
    color: [0.16, 0.2, 0.29],
    metalness: 0.55,
    roughness: 0.35,
  });
  const sW = floorW / 2 - 0.2;
  const sD = floorD / 2 - 0.2;
  for (const [px, pz, sx, sz] of [
    [0, -sD, floorW - 0.3, 0.1],
    [0, sD, floorW - 0.3, 0.1],
    [-sW, 0, 0.1, floorD - 0.7],
    [sW, 0, 0.1, floorD - 0.7],
  ] as const)
    boxes.push({
      name: "eda_die_Seal",
      layer: "die",
      pos: [px, 0.2, pz],
      size: [sx, 0.05, sz],
      color: [0.95, 0.78, 0.3],
      metalness: 0.95,
      roughness: 0.22,
      emissive: 0.1,
    });
  for (const [kx, kz] of [
    [-1, -1],
    [1, -1],
    [-1, 1],
    [1, 1],
  ] as const) {
    const kX = kx * (floorW / 2 - 0.75);
    const kZ = kz * (floorD / 2 - 0.75);
    boxes.push({
      name: "eda_die_AlignH",
      layer: "die",
      pos: [kX, 0.19, kZ],
      size: [0.34, 0.02, 0.07],
      color: [0.85, 0.9, 0.98],
      metalness: 0.8,
      roughness: 0.3,
      emissive: 0.25,
    });
    boxes.push({
      name: "eda_die_AlignV",
      layer: "die",
      pos: [kX, 0.19, kZ],
      size: [0.07, 0.02, 0.34],
      color: [0.85, 0.9, 0.98],
      metalness: 0.8,
      roughness: 0.3,
      emissive: 0.25,
    });
  }

  // Analog macro island — a mixed-signal part's AFE never comes out of the
  // synthesizer as gates; it sits beside the standard-cell sea as a hard
  // macro with its own cap array and guard ring.
  if (prof.analog) {
    const a = prof.analog;
    const marginX = (floorW - totalWCubes * PITCH) / 2;
    const aW = Math.min(a.w * 0.8, Math.max(1.0, marginX - 0.7));
    const aD = Math.min(a.d, Math.max(1.2, totalDCubes * PITCH * 0.6));
    // near (+x, +z) corner — the default camera looks from there, so the
    // AFE island is the first thing a mixed-signal twin shows
    const ax = floorW / 2 - aW / 2 - 0.55;
    const az = floorD / 2 - aD / 2 - 0.75;
    boxes.push({
      name: `eda_analog_${a.label}`,
      layer: "analog",
      pos: [ax, 0.3, az],
      size: [aW, 0.6, aD],
      color: [0.1, 0.65, 0.6],
      metalness: 0.35,
      roughness: 0.45,
      emissive: 0.18,
    });
    for (let i = 0; i < Math.min(a.caps, 8); i++) {
      const cx = ax - aW / 2 + 0.35 + (i % 4) * ((aW - 0.5) / 3.5);
      const cz = az - aD / 2 + 0.28 + Math.floor(i / 4) * (aD - 0.5);
      boxes.push({
        name: `eda_analog_mim${i}`,
        layer: "analog",
        pos: [cx, 0.68, cz],
        size: [0.22, 0.14, 0.16],
        color: [0.3, 0.85, 0.75],
        metalness: 0.7,
        roughness: 0.3,
        emissive: 0.25,
      });
    }
    for (const [px, pz, sx, sz] of [
      [ax, az - aD / 2 - 0.08, aW + 0.24, 0.08],
      [ax, az + aD / 2 + 0.08, aW + 0.24, 0.08],
      [ax - aW / 2 - 0.08, az, 0.08, aD + 0.24],
      [ax + aW / 2 + 0.08, az, 0.08, aD + 0.24],
    ] as const)
      boxes.push({
        name: "eda_analog_guard",
        layer: "analog",
        pos: [px, 0.3, pz],
        size: [sx, 0.2, sz],
        color: [0.95, 0.78, 0.3],
        metalness: 0.85,
        roughness: 0.3,
        emissive: 0.15,
      });
  }

  let cellIdx = 0;
  let railN = 0;
  let m2N = 0;
  let m3N = 0;
  let viaN = 0;
  const zTop = -(totalDCubes / 2.0) * PITCH;
  let zCursor = zTop;
  strips.forEach((strip, si) => {
    const stripLeftX = -(stripWidths[si] / 2.0) * PITCH;
    let xCursor = stripLeftX;
    const stripD = stripDepths[si];
    for (const b of strip) {
      const color = b.color;
      const bw = b.tw * PITCH;
      const bd = b.td * PITCH;
      const bx = xCursor + bw / 2;
      const bz = zCursor + bd / 2;
      // Placement-region tray (darker shade of the type color) — hiding the
      // cell layer leaves the placed footprint readable.
      boxes.push({
        name: `eda_place_${b.label}`,
        layer: "die",
        pos: [bx, 0.205, bz],
        size: [bw + 0.24, 0.05, bd + 0.24],
        color: [color[0] * 0.4, color[1] * 0.4, color[2] * 0.4],
        metalness: 0.4,
        roughness: 0.55,
        emissive: 0.06,
      });
      // Etched silkscreen plate in front of the region
      boxes.push({
        name: `eda_gateLabel_${b.label}_${b.count}x`,
        layer: "label",
        pos: [bx, 0.24, zCursor - 0.5],
        size: [Math.min(3.0, bw * 0.85), 0.3, 0.26],
        color: [color[0] * 0.65, color[1] * 0.65, color[2] * 0.65],
        metalness: 0.6,
        roughness: 0.35,
        emissive: 0.22,
      });
      // M1 power rails bound every standard-cell row (shared edges → one rail)
      for (let r = 0; r <= b.td; r++) {
        boxes.push({
          name: `eda_m1_rail_${b.label}_${r}`,
          layer: "m1",
          pos: [bx, 0.26, zCursor + r * PITCH],
          size: [bw, 0.045, 0.08],
          color: r % 2 ? [0.92, 0.32, 0.28] : [0.36, 0.6, 0.98],
          metalness: 0.8,
          roughness: 0.28,
          emissive: 0.12,
        });
        railN++;
      }
      // Cells: flat poly-over-diffusion strips tucked between the rails
      let placed = 0;
      for (let r = 0; r < b.td && placed < b.disp; r++) {
        const rowZ = zCursor + (r + 0.5) * PITCH;
        for (let c = 0; c < b.tw && placed < b.disp; c++) {
          boxes.push({
            name: `eda_cell_${String(cellIdx).padStart(3, "0")}`,
            layer: "cell",
            pos: [xCursor + (c + 0.5) * PITCH, 0.335, rowZ],
            size: [0.72, 0.12, PITCH * 0.6],
            color,
            metalness: 0.55,
            roughness: 0.3,
            emissive: 0.1,
          });
          cellIdx++;
          placed++;
        }
      }
      // BEOL dress over the placed region: copper M2 runs horizontally,
      // silver M3 vertically, stitched with gold vias
      const nM2 = Math.min(6, 2 + Math.floor(b.tw / 4));
      for (let i = 0; i < nM2; i++) {
        const w = bw * (0.45 + rng() * 0.5);
        boxes.push({
          name: `eda_m2_${b.label}_${i}`,
          layer: "m2",
          pos: [bx + (rng() - 0.5) * (bw - w) * 0.7, 0.5, zCursor + 0.25 + rng() * Math.max(0.1, bd - 0.5)],
          size: [w, 0.04, 0.09],
          color: [0.87, 0.52, 0.3],
          metalness: 0.9,
          roughness: 0.24,
          emissive: 0.08,
        });
        m2N++;
      }
      const nM3 = Math.min(6, 2 + Math.floor(b.td / 4));
      for (let i = 0; i < nM3; i++) {
        const d = bd * (0.45 + rng() * 0.5);
        boxes.push({
          name: `eda_m3_${b.label}_${i}`,
          layer: "m3",
          pos: [bx + (rng() - 0.5) * Math.max(0.1, bw - 0.4), 0.62, bz + (rng() - 0.5) * (bd - d) * 0.7],
          size: [0.09, 0.04, d],
          color: [0.78, 0.84, 0.94],
          metalness: 0.9,
          roughness: 0.24,
          emissive: 0.08,
        });
        m3N++;
      }
      const nVia = Math.min(5, 2 + Math.floor(b.tw / 5));
      for (let i = 0; i < nVia; i++) {
        boxes.push({
          name: `eda_via_${b.label}_${i}`,
          layer: "via",
          cyl: true,
          pos: [bx + (rng() - 0.5) * bw * 0.8, 0.56, bz + (rng() - 0.5) * bd * 0.8],
          size: [0.11, 0.1, 0.11],
          color: [0.96, 0.85, 0.32],
          metalness: 0.9,
          roughness: 0.2,
          emissive: 0.15,
        });
        viaN++;
      }
      xCursor += bw + INTRA * PITCH;
    }
    zCursor += stripD * PITCH + INTER * PITCH;
  });

  // Title strip — green when timing is met, red otherwise
  boxes.push({
    name: "eda_drc_Title",
    layer: "drc",
    pos: [0, 2.6, -floorD / 2 - 1.0],
    size: [4.0, 0.45, 0.1],
    color: slack >= 0 ? [0.27, 0.86, 0.46] : [0.94, 0.3, 0.45],
    emissive: 0.6,
  });

  // KPI gauge posts on the right edge (gates / area / slack), standing on
  // the lid — short metallic pedestals so they don't tower over the die
  const bars: [RGB, number][] = [
    [[0.13, 0.83, 0.93], Math.min(2.4, gateCount / 30)],
    [[0.96, 0.62, 0.1], Math.min(2.4, area / 200)],
    [slack >= 0 ? [0.27, 0.86, 0.46] : [0.94, 0.3, 0.45], Math.min(2.4, Math.max(0.5, Math.abs(slack) * 2))],
  ];
  bars.forEach(([color, h], j) => {
    boxes.push({
      name: `eda_kpi_${j}`,
      layer: "kpi",
      pos: [floorW / 2 + 0.9, 0.18 + h / 2, (j - 1) * 0.95],
      size: [0.42, h, 0.42],
      color,
      metalness: 0.6,
      roughness: 0.3,
      emissive: 0.22,
    });
  });

  const legend: EdaLegendEntry[] = blocks.map((b) => ({
    key: b.type,
    label: `${b.label} ×${b.count}`,
    color: b.color,
    count: b.count,
  }));
  if (prof.analog)
    legend.push({ key: "analog", label: `${prof.analog.label} ×1`, color: [0.1, 0.65, 0.6], count: 1 });
  legend.push({ key: "m1", label: `M1 VDD/VSS ×${railN}`, color: [0.36, 0.6, 0.98], count: railN });
  legend.push({ key: "m2", label: `M2 Cu ×${m2N}`, color: [0.87, 0.52, 0.3], count: m2N });
  legend.push({ key: "m3", label: `M3 Al ×${m3N}`, color: [0.78, 0.84, 0.94], count: m3N });
  legend.push({ key: "via", label: `Via ×${viaN}`, color: [0.96, 0.85, 0.32], count: viaN });

  // Explode lifts the stack in fab order: die frame → labels → analog macro
  // → cell rows → M1 rails → M2 → vias → M3 → KPI → timing strip.
  const radius = Math.max(floorW, floorD);
  return {
    mode: "synthesis",
    boxes,
    legend,
    studio: true,
    target: [0, 1, 0],
    distance: radius * 1.6 + 4,
    explodeAnchors: {
      die: 0,
      label: 0.35,
      analog: 0.6,
      cell: 0.95,
      m1: 1.35,
      m2: 1.9,
      via: 2.3,
      m3: 2.65,
      kpi: 3.2,
      drc: 3.6,
    },
  };
}

// ── Layout scene — real-process layer cake ──
// Port of build_layout_scene: substrate → pads → seal ring → core → macros
// → diffusion/poly/standard-cell rows with M1 VDD/VSS rails → Manhattan
// routing across M2..M6 with vias → power grid → DRC indicator.
export function buildLayoutScene(fp: FloorplanConfig, drcViolations: number, projectTitle: string): EdaScene {
  const rng = mulberry32(strSeed(projectTitle + "layout"));
  const boxes: EdaBox[] = [];
  const DIE_W = fp.dieW;
  const DIE_D = fp.dieD;
  const util = fp.utilization;
  const PAD_INSET = 0.3;
  const PAD_SIZE = 0.36;
  const SEAL_W = 0.06;
  const SEAL_INSET = PAD_INSET + PAD_SIZE;
  const CORE_INSET = SEAL_INSET + SEAL_W + 0.18;
  const utilMargin = (0.85 - util) * 0.5;
  const CORE_W = Math.max(2.0, DIE_W - 2 * (CORE_INSET + utilMargin));
  const CORE_D = Math.max(2.0, DIE_D - 2 * (CORE_INSET + utilMargin));

  // 1. Die substrate
  boxes.push({
    name: "eda_die_Substrate", layer: "die", pos: [0, LAYER_Y.die, 0],
    size: [DIE_W, 0.15, DIE_D], color: [0.05, 0.06, 0.09], roughness: 0.95,
  });

  // 2. Pad ring (gold) — count from pad_density
  const padDensityMap = { low: [10, 6], medium: [18, 12], high: [28, 20] } as const;
  const [nTop, nSide] = padDensityMap[fp.padDensity];
  let padIdx = 0;
  const edgeX = (DIE_W - 2 * PAD_INSET) / (nTop + 1);
  for (let i = 0; i < nTop; i++) {
    const x = -DIE_W / 2 + PAD_INSET + edgeX * (i + 1);
    for (const z of [-DIE_D / 2 + PAD_INSET, DIE_D / 2 - PAD_INSET]) {
      boxes.push({
        name: `eda_pad_${String(padIdx++).padStart(3, "0")}`, layer: "pad",
        pos: [x, LAYER_Y.pad, z], size: [PAD_SIZE, 0.1, PAD_SIZE],
        color: [0.96, 0.78, 0.31], metalness: 0.85, roughness: 0.32, emissive: 0.1,
      });
    }
  }
  const edgeZ = (DIE_D - 2 * PAD_INSET) / (nSide + 1);
  for (let i = 0; i < nSide; i++) {
    const z = -DIE_D / 2 + PAD_INSET + edgeZ * (i + 1);
    for (const x of [-DIE_W / 2 + PAD_INSET, DIE_W / 2 - PAD_INSET]) {
      boxes.push({
        name: `eda_pad_${String(padIdx++).padStart(3, "0")}`, layer: "pad",
        pos: [x, LAYER_Y.pad, z], size: [PAD_SIZE, 0.1, PAD_SIZE],
        color: [0.96, 0.78, 0.31], metalness: 0.85, roughness: 0.32, emissive: 0.1,
      });
    }
  }

  // 3. Seal ring
  const sealWX = DIE_W - 2 * SEAL_INSET;
  const sealWZ = DIE_D - 2 * SEAL_INSET;
  (
    [
      [0, -DIE_D / 2 + SEAL_INSET + SEAL_W / 2, sealWX, SEAL_W],
      [0, DIE_D / 2 - SEAL_INSET - SEAL_W / 2, sealWX, SEAL_W],
      [-DIE_W / 2 + SEAL_INSET + SEAL_W / 2, 0, SEAL_W, sealWZ],
      [DIE_W / 2 - SEAL_INSET - SEAL_W / 2, 0, SEAL_W, sealWZ],
    ] as const
  ).forEach(([px, pz, sx, sz], i) => {
    boxes.push({
      name: `eda_seal_${i}`, layer: "seal", pos: [px, LAYER_Y.seal, pz],
      size: [sx, 0.04, sz], color: [0.66, 0.55, 0.22], metalness: 0.7, roughness: 0.45,
    });
  });

  // 4. Core
  boxes.push({
    name: "eda_core_Area", layer: "core", pos: [0, LAYER_Y.core, 0],
    size: [CORE_W, 0.04, CORE_D], color: [0.07, 0.1, 0.18], roughness: 0.85,
  });

  // 5. Macros — the mission's real functional blocks (silProfileOf: an AFE
  // chip places its analog front-end, the SoC places RISC + memories), the
  // first numMacros of the catalog, clamped inside the core area.
  const prof = silProfileOf(projectTitle);
  const macros = prof.macros.slice(0, fp.numMacros).map(([label, mw0, md0, color, fx, fz]) => {
    const mw = Math.min(mw0, CORE_W * 0.46);
    const md = Math.min(md0, CORE_D * 0.44);
    const mx = Math.max(-(CORE_W - mw) / 2 + 0.15, Math.min((CORE_W - mw) / 2 - 0.15, fx * CORE_W));
    const mz = Math.max(-(CORE_D - md) / 2 + 0.15, Math.min((CORE_D - md) / 2 - 0.15, fz * CORE_D));
    return { label, mx, mz, mw, md, color };
  });
  const macroBboxes: [number, number, number, number][] = [];
  for (const m of macros) {
    boxes.push({
      name: `eda_macro_${m.label}`, layer: "macro", pos: [m.mx, LAYER_Y.macro, m.mz],
      size: [m.mw, 0.2, m.md], color: m.color, metalness: 0.25, roughness: 0.55, emissive: 0.08,
    });
    macroBboxes.push([m.mx, m.mz, m.mw, m.md]);
  }
  const hitsMacro = (x: number, z: number, w = 0.0, d = 0.0) =>
    macroBboxes.some(
      ([mx, mz, mw, md]) =>
        mx - mw / 2 - 0.08 < x + w / 2 && x - w / 2 < mx + mw / 2 + 0.08 &&
        mz - md / 2 - 0.08 < z + d / 2 && z - d / 2 < mz + md / 2 + 0.08,
    );

  // 6. Diffusion + poly + standard cells per row + M1 power rails
  const ROW_H = 0.18;
  const ROW_GAP = 0.06;
  const ROW_PITCH = ROW_H + ROW_GAP;
  const nRows = Math.max(1, Math.floor((CORE_D - 0.4) / ROW_PITCH));
  const UNIT_W = 0.2;
  let cellIdx = 0;
  let polyIdx = 0;
  for (let r = 0; r < nRows; r++) {
    const zRow = -CORE_D / 2 + 0.2 + r * ROW_PITCH + ROW_H / 2;
    const well: RGB = r % 2 === 0 ? [0.13, 0.2, 0.3] : [0.18, 0.16, 0.3];

    boxes.push({
      name: `eda_diff_Row_${String(r).padStart(2, "0")}`, layer: "diff",
      pos: [0, LAYER_Y.diff, zRow], size: [CORE_W - 0.4, 0.02, ROW_H - 0.05],
      color: [0.55, 0.32, 0.18], roughness: 0.92,
    });

    const xLeft = -CORE_W / 2 + 0.2;
    const xRight = CORE_W / 2 - 0.2;
    let x = xLeft;
    while (x < xRight && cellIdx < 320) {
      const cw = UNIT_W * [1, 1, 1, 2, 2, 3][Math.floor(rng() * 6)];
      if (hitsMacro(x + cw / 2, zRow, cw, ROW_H)) {
        let advanced = false;
        for (const [mx, mz, mw, md] of macroBboxes) {
          if (mz - md / 2 - 0.08 <= zRow && zRow <= mz + md / 2 + 0.08 && x < mx + mw / 2 + 0.1) {
            x = Math.max(x, mx + mw / 2 + 0.12);
            advanced = true;
            break;
          }
        }
        if (!advanced) x += UNIT_W;
        continue;
      }
      if (x + cw > xRight) break;
      boxes.push({
        name: `eda_cell_${String(cellIdx).padStart(3, "0")}`, layer: "cell",
        pos: [x + cw / 2, LAYER_Y.cell, zRow], size: [cw - 0.025, 0.1, ROW_H - 0.04],
        color: well, roughness: 0.6,
      });
      const nUnits = Math.max(1, Math.round(cw / UNIT_W));
      for (let u = 0; u < nUnits; u++) {
        const px = x + (u + 0.5) * (cw / nUnits);
        boxes.push({
          name: `eda_poly_${String(polyIdx++).padStart(4, "0")}`, layer: "poly",
          pos: [px, LAYER_Y.poly, zRow], size: [0.025, 0.02, ROW_H - 0.05],
          color: [0.85, 0.3, 0.4], emissive: 0.15,
        });
      }
      cellIdx++;
      x += cw + 0.005;
    }

    // M1 VDD/VSS rails
    const railLen = CORE_W - 0.5;
    for (const [which, railZ, railColor] of [
      ["Vss", zRow - ROW_H / 2 - 0.005, [0.85, 0.28, 0.2]],
      ["Vdd", zRow + ROW_H / 2 + 0.005, [0.3, 0.55, 0.95]],
    ] as const) {
      boxes.push({
        name: `eda_M1_Rail_${String(r).padStart(2, "0")}_${which}`, layer: "M1",
        pos: [0, LAYER_Y.M1, railZ], size: [railLen, 0.02, 0.025],
        color: railColor as RGB, metalness: 0.55, roughness: 0.32, emissive: 0.22,
      });
    }
  }

  // 7. Manhattan routing across M2..M6 with vias
  const GRID = 0.1;
  const snap = (v: number) => Math.round(v / GRID) * GRID;
  const ROUTE_PLAN: [string, string, number, string][] = [
    ["M3", "M2", 0.5, "via2"],
    ["M5", "M4", 0.3, "via4"],
    ["M6", "M6", 0.2, "via5"],
  ];
  const nRoutes = Math.max(6, Math.min(80, Math.round(6 + 74 * fp.signalRoutingDensity)));
  let viaIdx = 0;
  for (let ri = 0; ri < nRoutes; ri++) {
    const r = rng();
    let plan = ROUTE_PLAN[0];
    let cum = 0.0;
    for (const p of ROUTE_PLAN) {
      cum += p[2];
      if (r < cum) {
        plan = p;
        break;
      }
    }
    const [hLayer, vLayer, , viaLayer] = plan;
    const sx = snap(-CORE_W / 2 + 0.3 + rng() * (CORE_W - 0.6));
    const sz = snap(-CORE_D / 2 + 0.3 + rng() * (CORE_D - 0.6));
    const dx = snap(-CORE_W / 2 + 0.3 + rng() * (CORE_W - 0.6));
    const dz = snap(-CORE_D / 2 + 0.3 + rng() * (CORE_D - 0.6));

    boxes.push({
      name: `eda_${hLayer}_RouteH_${String(ri).padStart(3, "0")}`, layer: hLayer,
      pos: [(sx + dx) / 2, LAYER_Y[hLayer], sz],
      size: [Math.max(0.12, Math.abs(dx - sx)), 0.018, "M5" === hLayer ? 0.05 : 0.04],
      color: LAYER_COLOR[hLayer], metalness: 0.55, roughness: 0.32, emissive: 0.22,
    });
    boxes.push({
      name: `eda_${vLayer}_RouteV_${String(ri).padStart(3, "0")}`, layer: vLayer,
      pos: [dx, LAYER_Y[vLayer], (sz + dz) / 2],
      size: [vLayer === "M4" ? 0.05 : 0.04, 0.018, Math.max(0.12, Math.abs(dz - sz))],
      color: LAYER_COLOR[vLayer], metalness: 0.55, roughness: 0.32, emissive: 0.22,
    });
    boxes.push({
      name: `eda_${viaLayer}_${String(viaIdx++).padStart(3, "0")}`, layer: viaLayer,
      pos: [dx, (LAYER_Y[hLayer] + LAYER_Y[vLayer]) / 2, sz],
      size: [0.08, 0.1, 0.08], cyl: true,
      color: [0.96, 0.85, 0.32], metalness: 0.95, roughness: 0.2, emissive: 0.3,
    });
  }

  // 7b. Power grid stripes
  const nVPg = Math.max(2, Math.floor(CORE_W / fp.powerGridPitch));
  const nHPg = Math.max(2, Math.floor(CORE_D / fp.powerGridPitch));
  const pgXStep = CORE_W / (nVPg + 1);
  const pgZStep = CORE_D / (nHPg + 1);
  for (let i = 0; i < nVPg; i++) {
    boxes.push({
      name: `eda_M4_PowerV_${String(i).padStart(2, "0")}`, layer: "M4",
      pos: [-CORE_W / 2 + (i + 1) * pgXStep, LAYER_Y.M4, 0],
      size: [0.07, 0.025, CORE_D - 0.4], color: [0.95, 0.65, 0.25],
      metalness: 0.55, roughness: 0.32, emissive: 0.22,
    });
  }
  for (let i = 0; i < nHPg; i++) {
    boxes.push({
      name: `eda_M5_PowerH_${String(i).padStart(2, "0")}`, layer: "M5",
      pos: [0, LAYER_Y.M5, -CORE_D / 2 + (i + 1) * pgZStep],
      size: [CORE_W - 0.4, 0.025, 0.07], color: [0.55, 0.3, 0.85],
      metalness: 0.55, roughness: 0.32, emissive: 0.22,
    });
  }

  // 8. DRC indicator
  boxes.push({
    name: "eda_drc_Indicator", layer: "drc", pos: [0, LAYER_Y.drc, -DIE_D / 2 - 0.7],
    size: [2.5, 0.45, 0.1], color: drcViolations === 0 ? [0.27, 0.86, 0.46] : [0.94, 0.3, 0.45],
    emissive: 0.6,
  });

  // Legend: layers that actually appear, with counts
  const counts = new Map<string, number>();
  for (const b of boxes) counts.set(b.layer, (counts.get(b.layer) ?? 0) + 1);
  const order = LAYER_REGISTRY.map((l) => l.key);
  const legend: EdaLegendEntry[] = [...counts.keys()]
    .sort((a, b) => order.indexOf(a) - order.indexOf(b))
    .map((key) => ({
      key,
      label: key,
      color: LAYER_COLOR[key] ?? [0.5, 0.5, 0.5],
      count: counts.get(key) ?? 0,
    }));

  return {
    mode: "layout",
    boxes,
    legend,
    target: [0, 0.3, 0],
    distance: Math.max(DIE_W, DIE_D) * 1.9 + 3,
  };
}

// ── Process scene — the die as a real fab flow ─────────────────────────
// The gate-cluster view answers "what gates did I get"; this one answers
// "how does a fab actually build it": wafer → STI → wells → gate stack →
// LDD/S-D → spacers/silicide/contacts → M1 → via/M2 → upper metals →
// passivation → bond pads/seal/PCM. Every step carries floor-level detail
// (alignment keys, ion beam, stepper reticle frames, CMP check bar, die-ID
// matrix, scribe street, PCM test structures). Step k is a layer key, so
// the viewer's chips/explode work unchanged and a slider can build the
// chip up stage by stage.
type ProcStep = { key: string; label: string; color: RGB };

const PROC_STEPS: ProcStep[] = [
  { key: "S00 wafer",        label: "wafer",        color: [0.42, 0.46, 0.52] },
  { key: "S01 STI",          label: "STI/CMP",      color: [0.62, 0.7, 0.62] },
  { key: "S02 well",         label: "well implant", color: [0.28, 0.48, 0.88] },
  { key: "S03 gate",         label: "gate ox+poly", color: [0.72, 0.2, 0.3] },
  { key: "S04 LDD",          label: "LDD/halo",     color: [0.95, 0.62, 0.3] },
  { key: "S05 spacer+SD",    label: "spacer + S/D", color: [0.5, 0.36, 0.62] },
  { key: "S06 silicide/CT",  label: "silicide+CT",  color: [0.92, 0.94, 0.98] },
  { key: "S07 M1",           label: "M1",           color: [0.3, 0.55, 0.95] },
  { key: "S08 via/M2",       label: "via1 + M2",    color: [0.95, 0.4, 0.4] },
  { key: "S09 top metal",    label: "M3-M6 mesh",   color: [0.3, 0.85, 0.55] },
  { key: "S10 passivation",  label: "passivation",  color: [0.36, 0.42, 0.58] },
  { key: "S11 pad/seal/PCM", label: "pad+seal+PCM", color: [0.96, 0.78, 0.31] },
];

export function buildProcessScene(report: SynthResult, projectTitle: string): EdaScene {
  const rng = mulberry32(strSeed(`proc-${projectTitle}`));
  const boxes: EdaBox[] = [];
  const stepCount = new Map<string, number>();
  const put = (step: ProcStep, name: string, pos: [number, number, number], size: [number, number, number], color: RGB, extra: Partial<EdaBox> = {}) => {
    boxes.push({ name: `${step.key}_${name}`, layer: step.key, pos, size, color, ...extra });
    stepCount.set(step.key, (stepCount.get(step.key) ?? 0) + 1);
  };
  const stepOf = (k: string) => PROC_STEPS.find((s) => s.key === k)!;
  const gates = Math.max(60, report.gateCount || 60);
  // Standard-cell row count scales with the gate count (6..12 rows)
  const ROWS = Math.min(12, Math.max(6, Math.round(4 + Math.sqrt(gates) / 4)));
  const COLS = 10; // poly gate lines per row span
  // Die footprint follows the product chip (silProfileOf): the SNS-UART
  // die is a narrow strip, the AFE/SoC die is the largest, and the pad /
  // analog / memory placements below all hang off the same profile.
  const prof = silProfileOf(projectTitle);
  const W = prof.dieW;
  const D = prof.dieD;
  const rowZ = (r: number) => -D / 2 + 1.0 + ((r + 0.5) * (D - 2.0)) / ROWS;
  const colX = (c: number) => -W / 2 + 1.2 + ((c + 0.5) * (W - 2.4)) / COLS;

  // Mission-specific regions: analog AFE island + dense memory array.
  const anaRect = () => {
    const a = prof.analog;
    if (!a) return null;
    const w = Math.min(a.w, W * 0.3);
    const d = Math.min(a.d, D * 0.36);
    const cx = Math.max(-(W - w) / 2 + 0.4, Math.min((W - w) / 2 - 0.4, a.fx * W));
    const cz = Math.max(-(D - d) / 2 + 0.4, Math.min((D - d) / 2 - 0.4, a.fz * D));
    return { a, cx, cz, w, d };
  };
  const memRect = () => {
    const m = prof.mem;
    if (!m) return null;
    const w = Math.min(m.cols * 0.24 + 0.4, W * 0.3);
    const d = Math.min(m.rows * 0.24 + 0.4, D * 0.36);
    const cx = Math.max(-(W - w) / 2 + 0.4, Math.min((W - w) / 2 - 0.4, m.fx * W));
    const cz = Math.max(-(D - d) / 2 + 0.4, Math.min((D - d) / 2 - 0.4, m.fz * D));
    return { m, cx, cz, w, d };
  };

  // corner alignment keys (photo-lithography step detail, reused twice)
  const alignmentKeys = (s: ProcStep, y: number, size: number) => {
    for (const [cx, cz] of [[-W / 2 + 0.55, -D / 2 + 0.55], [W / 2 - 0.55, -D / 2 + 0.55], [-W / 2 + 0.55, D / 2 - 0.55], [W / 2 - 0.55, D / 2 - 0.55]] as const) {
      put(s, "aln_h", [cx, y, cz], [size, 0.04, size * 0.14], [0.95, 0.97, 1], { emissive: 0.55 });
      put(s, "aln_v", [cx, y, cz], [size * 0.14, 0.04, size], [0.95, 0.97, 1], { emissive: 0.55 });
    }
  };
  // stepper reticle frame: translucent frame + field-split cross above the die
  const reticleFrame = (s: ProcStep, y: number) => {
    const t = 0.16;
    for (const [px, pz, sx, sz] of [
      [0, -D / 2 - 0.25, W + 1.0, t], [0, D / 2 + 0.25, W + 1.0, t],
      [-W / 2 - 0.25, 0, t, D + 1.0], [W / 2 + 0.25, 0, t, D + 1.0],
    ] as const)
      put(s, "reticle", [px, y, pz], [sx, 0.05, sz], [0.95, 0.95, 0.6], { opacity: 0.32, emissive: 0.25 });
    put(s, "reticle_div_h", [0, y, 0], [W + 1.0, 0.04, 0.06], [0.95, 0.95, 0.6], { opacity: 0.25 });
    put(s, "reticle_div_v", [0, y, 0], [0.06, 0.04, D + 1.0], [0.95, 0.95, 0.6], { opacity: 0.25 });
  };

  // ── S00 wafer: substrate + notch + orientation flat + laser-scribe ID ──
  {
    const s = stepOf("S00 wafer");
    put(s, "substrate", [0, -0.25, 0], [W, 0.5, D], s.color, { metalness: 0.35, roughness: 0.6 });
    put(s, "notch", [-W / 2 + 0.3, -0.25, D / 2 - 0.3], [0.5, 0.5, 0.5], [0.3, 0.33, 0.38], { cyl: true });
    put(s, "flat", [W / 2 - 0.12, -0.1, 0], [0.24, 0.3, D - 0.6], [0.3, 0.33, 0.38], { metalness: 0.4 });
    for (let i = 0; i < 10; i++)
      put(s, `scribe${i}`, [-3.6 + i * 0.42, 0.005, D / 2 - 0.5], [0.2, 0.02, 0.1], [0.08, 0.09, 0.12]); // laser-scribe serial digits
    // stepper reticle field: this product's die repeats in a 2×2 field grid
    for (const [ffx, ffz] of [[-0.25, -0.25], [0.25, -0.25], [-0.25, 0.25], [0.25, 0.25]] as const)
      put(s, `field_${ffx > 0 ? "e" : "w"}${ffz > 0 ? "s" : "n"}`, [ffx * W, -0.02, ffz * D], [W * 0.42, 0.02, D * 0.42], [0.95, 0.95, 0.6], { opacity: 0.22, emissive: 0.2 });
  }

  // ── S01 STI: shallow-trench isolation fill + CMP planarity check bar ──
  {
    const s = stepOf("S01 STI");
    for (let r = 0; r < ROWS; r++)
      for (let c = 0; c < COLS; c++) {
        const h = 0.1 + (rng() - 0.5) * 0.012; // post-CMP dishing jitter
        put(s, `sti_${r}_${c}`, [colX(c), 0.05 + h / 2, rowZ(r)], [0.92, h, 0.62], s.color, { roughness: 0.7 });
      }
    put(s, "cmp_check", [0, 0.14, -D / 2 + 0.28], [W - 1.0, 0.06, 0.16], [0.13, 0.83, 0.93], { emissive: 0.5 });
  }

  // ── S02 wells: n/p-well slabs + ion beam + first alignment keys ──
  {
    const s = stepOf("S02 well");
    put(s, "nwell_top", [0, 0.16, -D / 2 + 1.6], [W - 1.6, 0.16, 2.4], s.color, { opacity: 0.4 });
    put(s, "nwell_bot", [0, 0.16, D / 2 - 1.6], [W - 1.6, 0.16, 2.4], s.color, { opacity: 0.4 });
    put(s, "pwell", [0, 0.16, 0], [W - 1.6, 0.16, D - 5.4], [0.85, 0.5, 0.2], { opacity: 0.4 });
    const ar = anaRect();
    if (ar) put(s, "dnwell", [ar.cx, 0.16, ar.cz], [ar.w + 0.5, 0.18, ar.d + 0.5], [0.16, 0.5, 0.5], { opacity: 0.45 }); // deep n-well: the AFE's isolated island
    put(s, "ion_beam", [0, 1.3, 0], [0.14, 2.0, 0.14], [0.9, 0.95, 1], { cyl: true, opacity: 0.5, emissive: 0.9 }); // implanter beam
    put(s, "beamline", [-W / 2 - 0.8, 1.3, 0], [0.5, 0.2, 0.2], [0.7, 0.75, 0.85], { emissive: 0.3 }); // beamline stub
    alignmentKeys(s, 0.26, 0.5);
  }

  // ── S03 gate stack: gate oxide + poly lines + stepper reticle frame ──
  {
    const s = stepOf("S03 gate");
    for (let r = 0; r < ROWS; r++)
      put(s, `gox_${r}`, [0, 0.26, rowZ(r)], [W - 1.6, 0.03, 0.56], [0.1, 0.75, 0.75], { emissive: 0.3 });
    for (let c = 0; c < COLS; c++)
      put(s, `poly_${c}`, [colX(c), 0.32, 0], [0.34, 0.1, D - 2.0], s.color, { metalness: 0.3, roughness: 0.5 });
    const ar = anaRect();
    if (ar) {
      // analog FEOL: island outline + MIM cap pairs + poly resistor serpentine
      put(s, "ana_frame", [ar.cx, 0.3, ar.cz], [ar.w + 0.3, 0.03, ar.d + 0.3], [0.85, 0.85, 0.85], { opacity: 0.3 });
      for (let i = 0; i < Math.min(ar.a.caps, 8); i++) {
        const cx = ar.cx - ar.w / 2 + 0.42 + (i % 4) * ((ar.w - 0.7) / 3);
        const cz = ar.cz - ar.d / 2 + 0.35 + Math.floor(i / 4) * ((ar.d - 0.6) / 1.2);
        put(s, `mim${i}a`, [cx, 0.3, cz], [0.3, 0.03, 0.2], [0.3, 0.85, 0.75], { emissive: 0.2 });
        put(s, `mim${i}b`, [cx, 0.34, cz], [0.24, 0.03, 0.16], [0.13, 0.83, 0.93], { emissive: 0.3 });
      }
      for (let i = 0; i < ar.a.res; i++)
        put(s, `ares${i}`, [ar.cx + ar.w / 2 - 0.35, 0.3, ar.cz - ar.d / 2 + 0.3 + i * 0.16], [0.3, 0.03, 0.1], [0.55, 0.32, 0.18], { emissive: 0.15 });
    }
    reticleFrame(s, 1.7);
  }

  // ── S04 LDD/halo: shallow implants flanking every gate line ──
  {
    const s = stepOf("S04 LDD");
    for (let r = 0; r < ROWS; r++) {
      const n = r % 2 === 0; // even rows NMOS, odd rows PMOS
      const col: RGB = n ? [0.95, 0.62, 0.3] : [0.55, 0.6, 0.95];
      for (let c = 0; c < COLS; c++)
        for (const side of [-1, 1])
          put(s, `ldd_${r}_${c}_${side}`, [colX(c) + side * 0.42, 0.28, rowZ(r)], [0.34, 0.05, 0.5], col, { emissive: 0.15 });
    }
  }

  // ── S05 sidewall spacers + S/D implants ──
  {
    const s = stepOf("S05 spacer+SD");
    for (let c = 0; c < COLS; c++)
      for (const side of [-1, 1])
        put(s, `spacer_${c}_${side}`, [colX(c) + side * 0.26, 0.34, 0], [0.1, 0.16, D - 2.0], s.color, { roughness: 0.55 });
    for (let r = 0; r < ROWS; r++) {
      const n = r % 2 === 0;
      const col: RGB = n ? [0.85, 0.15, 0.25] : [0.3, 0.3, 0.85];
      for (let c = 0; c < COLS - 1; c++)
        put(s, `sd_${r}_${c}`, [(colX(c) + colX(c + 1)) / 2, 0.3, rowZ(r)], [0.62, 0.07, 0.56], col);
    }
  }

  // ── S06 silicide caps + contact etch → W plugs ──
  {
    const s = stepOf("S06 silicide/CT");
    const metal: Partial<EdaBox> = { metalness: 0.9, roughness: 0.25, emissive: 0.12 };
    for (let c = 0; c < COLS; c++) put(s, `sil_poly_${c}`, [colX(c), 0.4, 0], [0.24, 0.04, D - 2.0], s.color, metal);
    for (let r = 0; r < ROWS; r++)
      for (let c = 0; c < COLS - 1; c++) {
        const x = (colX(c) + colX(c + 1)) / 2;
        const z = rowZ(r);
        put(s, `sil_sd_${r}_${c}`, [x, 0.36, z], [0.5, 0.04, 0.44], s.color, metal);
        put(s, `plug_${r}_${c}`, [x, 0.55, z], [0.2, 0.3, 0.2], [0.55, 0.58, 0.62], { cyl: true, metalness: 0.85, roughness: 0.3 }); // tungsten plug
      }
    const mr = memRect();
    if (mr) {
      // dense memory array: the mission's RAM/ROM core, pitch-tight cells
      for (let r = 0; r < mr.m.rows; r++)
        for (let c = 0; c < mr.m.cols; c++)
          put(s, `mcell_${r}_${c}`, [mr.cx - (mr.w - 0.3) / 2 + c * 0.24, 0.42, mr.cz - (mr.d - 0.3) / 2 + r * 0.24], [0.16, 0.12, 0.16], [0.2, 0.55, 0.78], { emissive: 0.18, roughness: 0.45 });
    }
  }

  // ── S07 M1: cell rails + stubs, M1 mask reticle ──
  {
    const s = stepOf("S07 M1");
    for (let r = 0; r <= ROWS; r++)
      put(s, `rail_${r}`, [0, 0.78, rowZ(r) - (D - 2.0) / ROWS / 2], [W - 1.2, 0.13, 0.26], s.color, { metalness: 0.8, roughness: 0.35 });
    for (let r = 0; r < ROWS; r++)
      for (let c = 0; c < COLS - 1; c++)
        put(s, `m1_${r}_${c}`, [(colX(c) + colX(c + 1)) / 2, 0.78, rowZ(r)], [0.22, 0.13, 0.22], s.color, { metalness: 0.8, roughness: 0.35 });
    const ar = anaRect();
    if (ar) {
      // guard/shield ring closing the analog island off from the digital sea
      for (const [px, pz, sx, sz] of [
        [ar.cx, ar.cz - ar.d / 2 - 0.1, ar.w + 0.5, 0.1],
        [ar.cx, ar.cz + ar.d / 2 + 0.1, ar.w + 0.5, 0.1],
        [ar.cx - ar.w / 2 - 0.1, ar.cz, 0.1, ar.d + 0.5],
        [ar.cx + ar.w / 2 + 0.1, ar.cz, 0.1, ar.d + 0.5],
      ] as const)
        put(s, "ana_shield", [px, 0.78, pz], [sx, 0.13, sz], [0.3, 0.85, 0.75], { metalness: 0.8, roughness: 0.35, emissive: 0.15 });
    }
    const mr = memRect();
    if (mr)
      for (let c = 0; c < Math.min(mr.m.cols, 10); c++)
        put(s, `membit${c}`, [mr.cx - (mr.w - 0.3) / 2 + c * 0.24, 0.78, mr.cz], [0.06, 0.13, mr.d + 0.2], [0.3, 0.55, 0.95], { metalness: 0.8, roughness: 0.35 }); // bitlines
    reticleFrame(s, 1.9);
  }

  // ── S08 via1 + M2 ──
  {
    const s = stepOf("S08 via/M2");
    for (let r = 0; r < ROWS; r += 2)
      for (let c = 0; c < COLS - 1; c += 2)
        put(s, `via1_${r}_${c}`, [(colX(c) + colX(c + 1)) / 2, 0.98, rowZ(r)], [0.16, 0.22, 0.16], [0.96, 0.85, 0.32], { cyl: true, metalness: 0.85 });
    for (let c = 0; c < 8; c++)
      put(s, `m2_${c}`, [-W / 2 + 1.6 + (c * (W - 3.2)) / 7, 1.1, 0], [0.38, 0.13, D - 1.6], s.color, { metalness: 0.8, roughness: 0.35 });
    reticleFrame(s, 2.05);
  }

  // ── S09 upper metals: M3/M4 + M5/M6 coarse power mesh ──
  {
    const s = stepOf("S09 top metal");
    for (let r = 0; r < 5; r++)
      put(s, `m3_${r}`, [0, 1.34, -D / 2 + 1.2 + (r * (D - 2.4)) / 4], [W - 1.0, 0.15, 0.42], [0.3, 0.85, 0.55], { metalness: 0.8, roughness: 0.35 });
    for (let c = 0; c < 5; c++)
      put(s, `m4_${c}`, [-W / 2 + 1.8 + (c * (W - 3.6)) / 4, 1.58, 0], [0.5, 0.17, D - 1.2], [0.95, 0.65, 0.25], { metalness: 0.8, roughness: 0.35 });
    for (const [zz, sx, sz] of [[-D / 2 + 0.7, W - 0.4, 0.75], [D / 2 - 0.7, W - 0.4, 0.75]] as const)
      put(s, `m5_vdd${zz > 0 ? "p" : "n"}`, [0, 1.84, zz], [sx, 0.2, sz], [0.55, 0.3, 0.85], { metalness: 0.85, roughness: 0.3 });
    for (const xx of [-W / 2 + 0.8, 0, W / 2 - 0.8])
      put(s, `m6_${xx < 0 ? "n" : xx > 0 ? "p" : "m"}`, [xx, 2.08, 0], [0.8, 0.22, D - 0.4], [0.85, 0.85, 0.3], { metalness: 0.85, roughness: 0.3 });
    const ar = anaRect();
    if (ar && ar.a.electrodes > 0) {
      // touch front-end: electrode comb array over the AFE island (top metal)
      for (let i = 0; i < ar.a.electrodes; i++)
        put(s, `electrode${i}`, [ar.cx - ar.w / 2 + 0.35 + (i * (ar.w - 0.6)) / Math.max(1, ar.a.electrodes - 1), 2.2, ar.cz], [0.14, 0.06, ar.d - 0.3], [0.3, 0.85, 0.75], { metalness: 0.7, roughness: 0.3, emissive: 0.25 });
    }
  }

  // ── S10 passivation + die-ID dot matrix (traceability) ──
  {
    const s = stepOf("S10 passivation");
    put(s, "passivation", [0, 2.28, 0], [W - 0.3, 0.08, D - 0.3], s.color, { opacity: 0.45, roughness: 0.4 });
    for (let iy = 0; iy < 7; iy++)
      for (let ix = 0; ix < 5; ix++)
        if (rng() > 0.35)
          put(s, `dieid_${ix}_${iy}`, [-W / 2 + 0.75 + ix * 0.16, 2.34, D / 2 - 1.15 + iy * 0.16], [0.08, 0.02, 0.08], [0.85, 0.88, 0.95], { emissive: 0.2 });
  }

  // ── S11 bond pads + seal ring + scribe street + PCM test structures ──
  {
    const s = stepOf("S11 pad/seal/PCM");
    const pad: Partial<EdaBox> = { metalness: 1.0, roughness: 0.28, emissive: 0.08 };
    // periphery bond pads — count from the product's pad ring (profile)
    for (let i = 0; i < prof.pads.tb; i++) {
      const x = -W / 2 + 1.4 + (i * (W - 2.8)) / Math.max(1, prof.pads.tb - 1);
      put(s, `pad_b${i}`, [x, 2.42, D / 2 - 0.55], [0.55, 0.1, 0.55], s.color, pad);
      put(s, `pad_t${i}`, [x, 2.42, -D / 2 + 0.55], [0.55, 0.1, 0.55], s.color, pad);
    }
    for (let i = 0; i < prof.pads.side; i++) {
      const zz = prof.pads.side === 1 ? 0 : -1.6 + (3.2 * i) / (prof.pads.side - 1);
      put(s, `pad_s${i}`, [-W / 2 + 0.55, 2.42, zz], [0.55, 0.1, 0.55], s.color, pad);
    }
    // seal ring
    const seal = stepOf("S11 pad/seal/PCM");
    for (const [px, pz, sx, sz] of [
      [0, -D / 2 + 0.12, W - 0.1, 0.22], [0, D / 2 - 0.12, W - 0.1, 0.22],
      [-W / 2 + 0.12, 0, 0.22, D - 0.1], [W / 2 - 0.12, 0, 0.22, D - 0.1],
    ] as const)
      put(seal, "seal", [px, 2.36, pz], [sx, 0.16, sz], [0.66, 0.55, 0.22], { metalness: 0.7, roughness: 0.4 });
    // scribe street crosses between seal and pad ring
    for (const xx of [-3, 0, 3]) put(s, `street_${xx}`, [xx, 2.37, -D / 2 + 0.32], [0.18, 0.02, 0.18], [0.75, 0.78, 0.82], { emissive: 0.15 });
    // PCM (process control monitor) test structures in the street corner:
    // serpentine resistor + comb fingers + cross-bridge + label bar
    const pcm: Partial<EdaBox> = { emissive: 0.35 };
    const px0 = W / 2 - 1.9;
    const pz0 = -D / 2 + 0.75;
    for (let i = 0; i < 10; i++)
      put(s, `pcm_serp${i}`, [px0 + (i % 2) * 0.34, 2.4, pz0 + i * 0.13], [i % 2 ? 0.34 : 0.08, 0.03, 0.09], [0.13, 0.83, 0.93], pcm);
    for (let i = 0; i < 8; i++)
      put(s, `pcm_comb${i}`, [px0 + 0.9, 2.4, pz0 + i * 0.11], [0.55, 0.03, 0.05], [0.13, 0.83, 0.93], pcm);
    for (let i = 0; i < 4; i++)
      put(s, `pcm_xbr${i}`, [px0 + 1.62, 2.4, pz0 + i * 0.15], [0.3 + i * 0.08, 0.03, 0.05], [0.13, 0.83, 0.93], pcm);
    put(s, "pcm_label", [px0 + 0.85, 2.42, pz0 - 0.28], [1.9, 0.05, 0.12], [0.13, 0.83, 0.93], { emissive: 0.6 });
    alignmentKeys(s, 2.4, 0.6);
  }

  const legend: EdaLegendEntry[] = PROC_STEPS.filter((s) => stepCount.get(s.key)).map((s) => ({
    key: s.key,
    label: s.label,
    color: s.color,
    count: stepCount.get(s.key) ?? 0,
  }));

  return {
    mode: "process",
    boxes,
    legend,
    steps: PROC_STEPS.map((s) => s.key),
    target: [0, 1.2, 0],
    distance: Math.max(W, D) * 1.75 + 3,
  };
}
