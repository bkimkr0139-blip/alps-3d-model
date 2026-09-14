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
};

export type EdaLegendEntry = { key: string; label: string; color: RGB; count: number };

export type EdaScene = {
  mode: "synthesis" | "layout";
  boxes: EdaBox[];
  legend: EdaLegendEntry[];
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

  type Block = { type: string; count: number; tw: number; td: number; color: RGB; label: string };
  const blocks: Block[] = types.map(([type, n]) => ({
    type,
    count: n,
    tw: Math.max(1, Math.ceil(Math.sqrt(n))),
    td: 0,
    color: gateColor(type),
    label: shortGateLabel(type),
  }));
  for (const b of blocks) b.td = Math.max(1, Math.ceil(b.count / b.tw));

  // Strip-pack: left-to-right, wrap when the running width exceeds MAX.
  const spacing = 1.4;
  const INTRA = 2;
  const INTER = 2;
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
  const floorW = totalWCubes * spacing + 2.0;
  const floorD = totalDCubes * spacing + 1.5;

  const rng = mulberry32(strSeed(projectTitle));
  const boxes: EdaBox[] = [];
  const perCellArea = Math.max(0.4, area / Math.max(1, cells) / 60.0);

  boxes.push({
    name: "eda_die_Floor",
    layer: "die",
    pos: [0, -0.05, 0],
    size: [floorW, 0.1, floorD],
    color: [0.06, 0.1, 0.18],
    roughness: 0.95,
  });

  let cellIdx = 0;
  const zTop = -(totalDCubes / 2.0) * spacing;
  let zCursor = zTop;
  strips.forEach((strip, si) => {
    const stripLeftX = -(stripWidths[si] / 2.0) * spacing;
    let xCursor = stripLeftX;
    const stripD = stripDepths[si];
    for (const b of strip) {
      const color = b.color;
      // Silkscreen bar in front of the block (darker shade of the type color)
      boxes.push({
        name: `eda_gateLabel_${b.label}_${b.count}x`,
        layer: "label",
        pos: [xCursor + (b.tw / 2.0) * spacing, 0.25, zCursor - 0.7],
        size: [Math.min(3.0, b.tw * spacing * 0.8), 0.5, 0.4],
        color: [color[0] * 0.65, color[1] * 0.65, color[2] * 0.65],
        emissive: 0.25,
      });
      let placed = 0;
      for (let r = 0; r < b.td && placed < b.count; r++) {
        for (let c = 0; c < b.tw && placed < b.count; c++) {
          const h = 0.45 + perCellArea + rng() * 0.25;
          boxes.push({
            name: `eda_cell_${String(cellIdx).padStart(3, "0")}`,
            layer: "cell",
            pos: [xCursor + (c + 0.5) * spacing, h / 2, zCursor + (r + 0.5) * spacing],
            size: [0.85, h, 0.85],
            color,
            metalness: 0.25,
            roughness: 0.45,
            emissive: 0.18,
          });
          cellIdx++;
          placed++;
        }
      }
      xCursor += b.tw * spacing + INTRA * spacing;
    }
    zCursor += stripD * spacing + INTER * spacing;
  });

  // Title strip — green when timing is met, red otherwise
  boxes.push({
    name: "eda_drc_Title",
    layer: "drc",
    pos: [0, 3.5, -floorD / 2 - 1.0],
    size: [4.0, 0.6, 0.1],
    color: slack >= 0 ? [0.27, 0.86, 0.46] : [0.94, 0.3, 0.45],
    emissive: 0.6,
  });

  // KPI bars on the right edge (gates / area / slack)
  const bars: [RGB, number][] = [
    [[0.13, 0.83, 0.93], Math.min(8.0, gateCount / 30)],
    [[0.96, 0.62, 0.1], Math.min(8.0, area / 200)],
    [slack >= 0 ? [0.27, 0.86, 0.46] : [0.94, 0.3, 0.45], Math.min(8.0, Math.max(0.5, Math.abs(slack) * 2))],
  ];
  bars.forEach(([color, h], j) => {
    boxes.push({
      name: `eda_kpi_${j}`,
      layer: "kpi",
      pos: [floorW / 2 + 1.0, h / 2, (j - 1) * 1.5],
      size: [0.6, h, 0.6],
      color,
      emissive: 0.3,
    });
  });

  const legend: EdaLegendEntry[] = blocks.map((b) => ({
    key: b.type,
    label: `${b.label} ×${b.count}`,
    color: b.color,
    count: b.count,
  }));

  const radius = Math.max(floorW, floorD);
  return { mode: "synthesis", boxes, legend, target: [0, 1, 0], distance: radius * 1.6 + 4 };
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

  // 5. Macros (generic catalog, first numMacros of it)
  const macroCatalog: [string, number, number, number, number, RGB][] = [
    ["SRAM", -CORE_W / 2 + 1.55, CORE_D / 2 - 1.2, 2.8, 1.8, [0.2, 0.55, 0.78]],
    ["REGS", CORE_W / 2 - 1.3, -CORE_D / 2 + 1.0, 2.4, 1.6, [0.65, 0.3, 0.65]],
    ["PLL", -CORE_W / 2 + 1.1, -CORE_D / 2 + 0.85, 1.8, 1.3, [0.25, 0.7, 0.5]],
    ["DSP", CORE_W / 2 - 1.2, CORE_D / 2 - 0.95, 2.0, 1.4, [0.85, 0.45, 0.2]],
  ];
  const macros = macroCatalog.slice(0, fp.numMacros);
  const macroBboxes: [number, number, number, number][] = [];
  for (const [name, mx, mz, mw, md, color] of macros) {
    boxes.push({
      name: `eda_macro_${name}`, layer: "macro", pos: [mx, LAYER_Y.macro, mz],
      size: [mw, 0.2, md], color, metalness: 0.25, roughness: 0.55, emissive: 0.08,
    });
    macroBboxes.push([mx, mz, mw, md]);
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
