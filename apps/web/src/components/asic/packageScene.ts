import type { EdaBox, EdaLegendEntry, EdaScene, RGB } from "../eda/edaScene";
import type { AsicTemplate } from "./asicModel";

// Package/3D Twin for the ASIC workbench (지시서 §4.4): the model is driven by
// the stage-② selected option's pkg string, so every template/option shows its
// own package — QFN land grid + exposed pad, WLCSP bump array with RDL (no
// bond wires — wafer-level), LGA lands, SOIC/SOP/TSSOP gull-wing leads on two
// sides, LQFP leads on four — with family-appropriate body proportions. The
// internal construction follows industrial lead-frame/substrate practice: the
// die sits on the paddle, the bond fingers ring the die in the moat, and each
// wire arcs from one die pad to the nearest same-edge finger (a fan-out that
// never crosses the die or the sensor footprint). The sensor element follows
// the template: monolithic MEMS-on-CMOS (WLCSP/QFN), a separate wire-bonded
// MEMS die (LGA), or a co-integrated GMR bridge on the die (narrow SOIC/SOP/
// TSSOP current sensors). Assembled from the same EdaBox primitives the EDA
// scenes use, so the shared Eda3DViewer (explode + layer chips) renders it
// unchanged. Geometry is an educational schematic, not a sign-off model
// (§9.3: dims come from real CAD in the enterprise flow).

const GOLD: RGB = [0.96, 0.78, 0.31];
const PCB: RGB = [0.08, 0.28, 0.16];
const SUB: RGB = [0.12, 0.1, 0.09];
const DIE: RGB = [0.35, 0.42, 0.58];
const MOLD: RGB = [0.16, 0.15, 0.14];
const LEAD: RGB = [0.88, 0.89, 0.92];

type PkgFamily = "qfn" | "wlcsp" | "lga" | "soic" | "sop" | "tssop" | "lqfp" | "generic";

const parsePkg = (pkg: string): { family: PkgFamily; pins: number } => {
  const m = /^(QFN|WLCSP|LQFP|SOIC|SOP|TSSOP|LGA)-(\d+)$/.exec(pkg.trim().toUpperCase());
  return m ? { family: m[1].toLowerCase() as PkgFamily, pins: Number(m[2]) } : { family: "generic", pins: 24 };
};

// Most-square factor pair — bump/land grid shape for a given pin count
// (24 → 6×4, 16 → 4×4, 12 → 4×3).
function gridFor(pins: number): [number, number] {
  let best: [number, number] = [pins, 1];
  let score = Infinity;
  for (let c = 1; c * c <= pins; c++)
    if (pins % c === 0 && Math.abs(pins / c - c) < score) {
      score = Math.abs(pins / c - c);
      best = [pins / c, c];
    }
  return best;
}

// Stepped bond-wire arc: short cylinder segments between consecutive samples
// of a parabola from die pad (yTop) to substrate finger (yEnd). Each segment
// spans only its own arc slice — drawing whole columns from the PCB instead
// made the wires read as pins sticking out of the package. The arc peak
// (≈ yEnd + 0.35 + (yTop−yEnd)) stays under the mold cap (y 2.1), so the
// wires are fully encapsulated: a normal molded product, with the internals
// visible only through the layer chips (mold off) or the explode slider.
function bondWire(x1: number, z1: number, x2: number, z2: number, yTop: number, yEnd: number): EdaBox[] {
  const out: EdaBox[] = [];
  const N = 7;
  const at = (t: number) => ({
    x: x1 + (x2 - x1) * t,
    z: z1 + (z2 - z1) * t,
    y: yEnd + Math.sin(Math.PI * t) * 0.35 + (yTop - yEnd) * (1 - t),
  });
  let prev = at(0);
  for (let k = 1; k <= N; k++) {
    const cur = at(k / N);
    out.push({
      name: `bond${k}`,
      layer: "bond",
      pos: [(prev.x + cur.x) / 2, (prev.y + cur.y) / 2, (prev.z + cur.z) / 2],
      size: [0.16, Math.max(0.08, Math.abs(cur.y - prev.y)), 0.16],
      color: GOLD,
      cyl: true,
      metalness: 0.9,
      roughness: 0.25,
    });
    prev = cur;
  }
  return out;
}

export function buildPackageScene(tpl: AsicTemplate, pkg = tpl.options[0]?.pkg ?? ""): EdaScene {
  const boxes: EdaBox[] = [];
  const put = (b: EdaBox) => boxes.push(b);
  const { family, pins } = parsePkg(pkg);
  const gullWing = family === "soic" || family === "sop" || family === "tssop" || family === "lqfp";

  // ── PCB + footprint (y 0..0.5) ──
  put({ name: "pcb", layer: "PCB", pos: [0, 0.25, 0], size: [24, 0.5, 17], color: PCB, roughness: 0.7 });
  // copper traces running out of the footprint
  for (let i = 0; i < 6; i++) {
    const z = -5 + i * 2;
    put({ name: `trace${i}`, layer: "PCB", pos: [-14.5, 0.52, z], size: [5, 0.06, 0.35], color: [0.85, 0.72, 0.4], metalness: 0.7 });
    put({ name: `traceb${i}`, layer: "PCB", pos: [14.5, 0.52, z], size: [5, 0.06, 0.35], color: [0.85, 0.72, 0.4], metalness: 0.7 });
  }
  // via stitching around the footprint
  for (let i = 0; i < 10; i++) {
    put({ name: `via${i}`, layer: "PCB", pos: [-10 + i * 2.2, 0.3, -7.2], size: [0.5, 0.52, 0.5], color: [0.96, 0.85, 0.32], cyl: true, metalness: 0.8 });
  }

  // ── Body proportions per package family (scene units ≈ 1.4× mm) ──
  let bodyW = 11;
  let bodyD = 8;
  let perSide = Math.max(2, Math.round(pins / 4));
  let grid: [number, number] = [6, 4];
  switch (family) {
    case "qfn":
      perSide = Math.max(2, Math.round(pins / 4));
      bodyW = bodyD = Math.min(9.5, 4.5 + perSide * 0.5);
      break;
    case "lqfp":
      perSide = Math.max(2, Math.round(pins / 4));
      bodyW = bodyD = Math.min(10, 5 + perSide * 0.4);
      break;
    case "soic":
    case "sop":
      perSide = Math.max(2, Math.round(pins / 2));
      bodyW = 5.6;
      bodyD = Math.max(6.2, perSide * 0.95 + 1.8);
      break;
    case "tssop":
      perSide = Math.max(2, Math.round(pins / 2));
      bodyW = 4.9;
      bodyD = Math.max(6, perSide * 0.8 + 1.8);
      break;
    case "wlcsp":
      grid = gridFor(pins);
      bodyW = grid[0] * 1.15 + 1.0;
      bodyD = grid[1] * 1.15 + 1.0;
      break;
    case "lga":
      grid = gridFor(pins);
      bodyW = grid[0] * 1.3 + 1.7;
      bodyD = grid[1] * 1.3 + 1.7;
      break;
    default:
      break; // generic: schematic 11×8 ball grid
  }

  const hasMems = tpl.id === "cap_afe" || tpl.id === "env_sensor";

  // ── Die footprint (WLCSP: the die IS the body; else on the substrate) ──
  // QFN centres the die on the paddle (exposed-pad construction); LGA pulls
  // the die west so the separate MEMS die fits east with a moat between.
  const dieW = family === "wlcsp" ? bodyW - 1.2 : family === "lga" ? 3.0 : 4.2;
  const dieD = family === "wlcsp" ? bodyD - 1.2 : family === "lga" ? 2.8 : 3.2;
  const dieX = family === "wlcsp" || family === "qfn" ? 0 : -bodyW * (family === "lga" ? 0.18 : 0.14);
  const dieY = family === "wlcsp" ? 1.3 : 1.42;
  const dieTop = dieY + (family === "wlcsp" ? 0.3 : 0.2);

  // Shared lead-frame pitch — lead, bond finger and wire stay on one line.
  const leadPitch = Math.min(0.95, (dieW - 0.6) / (perSide - 1));
  const leadX0 = dieX - ((perSide - 1) * leadPitch) / 2;
  const leadZ0 = -((perSide - 1) * leadPitch) / 2;

  // ── Package body: substrate (lead-frame packages) + termination ──
  if (family !== "wlcsp")
    put({ name: "substrate", layer: "package", pos: [0, 0.8, 0], size: [bodyW, 0.6, bodyD], color: SUB, roughness: 0.6 });

  if (family === "qfn") {
    // leadless: perimeter lands + central exposed pad
    const pitchW = (bodyW - 1.6) / (perSide - 1);
    const pitchD = (bodyD - 1.6) / (perSide - 1);
    for (let i = 0; i < perSide; i++) {
      const x = -(perSide - 1) * pitchW * 0.5 + i * pitchW;
      const z = -(perSide - 1) * pitchD * 0.5 + i * pitchD;
      for (const s of [-1, 1] as const) {
        put({ name: `land_z${s}${i}`, layer: "solder", pos: [x, 0.62, s * (bodyD / 2 - 0.2)], size: [0.7, 0.24, 0.7], color: LEAD, metalness: 0.85, roughness: 0.35 });
        put({ name: `land_x${s}${i}`, layer: "solder", pos: [s * (bodyW / 2 - 0.2), 0.62, z], size: [0.7, 0.24, 0.7], color: LEAD, metalness: 0.85, roughness: 0.35 });
      }
    }
    put({ name: "epad", layer: "solder", pos: [0, 0.62, 0], size: [bodyW * 0.55, 0.24, bodyD * 0.5], color: [0.75, 0.76, 0.8], metalness: 0.85 });
  } else if (family === "lga") {
    // leadless land grid on the bottom face
    for (let i = 0; i < grid[0]; i++)
      for (let j = 0; j < grid[1]; j++)
        put({
          name: `land${i}-${j}`, layer: "solder",
          pos: [(i - (grid[0] - 1) / 2) * 1.3, 0.62, (j - (grid[1] - 1) / 2) * 1.3],
          size: [0.8, 0.24, 0.8], color: LEAD, metalness: 0.85, roughness: 0.35,
        });
  } else if (family === "wlcsp") {
    // wafer-level: bump array directly under the die (no substrate, no leads)
    for (let i = 0; i < grid[0]; i++)
      for (let j = 0; j < grid[1]; j++)
        put({
          name: `bump${i}-${j}`, layer: "solder",
          pos: [(i - (grid[0] - 1) / 2) * 1.15, 0.75, (j - (grid[1] - 1) / 2) * 1.15],
          size: [0.5, 0.5, 0.5], color: LEAD, cyl: true, metalness: 0.85, roughness: 0.3,
        });
  } else if (gullWing) {
    // gull-wing leads: PCB foot pad → sloped shoulder → lead finger under the
    // body edge; drawn on the two long sides (SOIC/SOP/TSSOP) or all four
    // (LQFP). Lead + finger go to the package layer; the PCB pads are solder.
    // The shared leadPitch/leadX0 above keep lead, finger and wire in one line.
    const side = (axis: "z" | "x", s: number) => {
      const edge = axis === "z" ? bodyD / 2 : bodyW / 2;
      for (let i = 0; i < perSide; i++) {
        const a = axis === "z" ? leadX0 + i * leadPitch : leadZ0 + i * leadPitch;
        const pts: [number, number][] =
          axis === "z"
            ? [[a, s * (edge + 1.15)], [a, s * (edge + 0.45)], [a, s * (edge - 0.1)]]
            : [[s * (edge + 1.15), a], [s * (edge + 0.45), a], [s * (edge - 0.1), a]];
        const [[f1, f2], [m1, m2], [h1, h2]] = pts;
        const [sx, sz] = axis === "z" ? [0.42, 1.1] : [1.1, 0.42];
        const [mx, mz] = axis === "z" ? [0.34, 0.45] : [0.45, 0.34];
        const [hx, hz] = axis === "z" ? [0.3, 0.6] : [0.6, 0.3];
        const [gx, gz] = axis === "z" ? [0.6, 1.0] : [1.0, 0.6];
        put({ name: `lead_${axis}${s}${i}a`, layer: "package", pos: [f1, 0.66, f2], size: [sx, 0.1, sz], color: LEAD, metalness: 0.85, roughness: 0.3 });
        put({ name: `lead_${axis}${s}${i}b`, layer: "package", pos: [m1, 0.95, m2], size: [mx, 0.55, mz], color: LEAD, metalness: 0.85, roughness: 0.3 });
        put({ name: `lead_${axis}${s}${i}c`, layer: "package", pos: [h1, 1.18, h2], size: [hx, 0.1, hz], color: LEAD, metalness: 0.85, roughness: 0.3 });
        put({ name: `pad_${axis}${s}${i}`, layer: "solder", pos: [f1, 0.56, f2], size: [gx, 0.1, gz], color: LEAD, metalness: 0.7, roughness: 0.4 });
      }
    };
    side("z", 1);
    side("z", -1);
    if (family === "lqfp") {
      side("x", 1);
      side("x", -1);
    }
  } else {
    // generic fallback: schematic ball grid
    for (let i = 0; i < 6; i++)
      for (let j = 0; j < 4; j++)
        put({ name: `ball${i}-${j}`, layer: "solder", pos: [-3.75 + i * 1.5, 0.55, -2.25 + j * 1.5], size: [0.55, 0.35, 0.55], color: LEAD, cyl: true, metalness: 0.85, roughness: 0.3 });
  }

  // mold cap: real molding compound is opaque — the assembled product shows
  // only the black body (or the thin WLCSP passivation), like an actual
  // packaged chip. Internals stay inspectable via the layer chips (toggle
  // "mold" off) and the explode slider.
  if (family === "wlcsp") {
    const capLift = hasMems ? 0.78 : 0.18;
    put({ name: "mold", layer: "mold", pos: [0, dieTop + capLift, 0], size: [dieW + 0.3, 0.28, dieD + 0.3], color: MOLD, roughness: 0.75 });
  } else {
    put({ name: "mold", layer: "mold", pos: [0, 1.6, 0], size: [bodyW, 1.0, bodyD], color: MOLD, roughness: 0.75 });
    // index notch on the short edge — SOIC/SOP/TSSOP family convention
    if (family === "soic" || family === "sop" || family === "tssop")
      put({ name: "notch", layer: "mark", pos: [0, 2.04, -bodyD / 2 + 0.14], size: [0.6, 0.3, 0.36], color: [0.06, 0.06, 0.06], cyl: true });
  }
  // laser mark: die-ID dot matrix on the top face + pin-1 chamfer dot
  for (let i = 0; i < 5; i++)
    for (let j = 0; j < 3; j++)
      put({
        name: `mark${i}${j}`, layer: "mark",
        pos: [bodyW / 2 - 2.4 + i * 0.5, family === "wlcsp" ? dieTop + (hasMems ? 0.94 : 0.34) : 2.12, -bodyD / 2 + 1.0 + j * 0.5],
        size: [0.16, 0.04, 0.16], color: [0.9, 0.9, 0.85],
      });
  put({
    name: "pin1", layer: "mark",
    pos: [-bodyW / 2 + 0.7, family === "wlcsp" ? dieTop + (hasMems ? 0.94 : 0.34) : 2.12, -bodyD / 2 + 0.7],
    size: [0.5, 0.05, 0.5], color: [0.95, 0.95, 0.9], cyl: true,
  });

  // ── Die + metal stack (bond pads are drawn by the bond map below — one
  // pad per wire, exactly like an assembled & molded unit) ──
  put({ name: "die-attach", layer: "die", pos: [dieX, dieY - 0.26, 0], size: [dieW + 0.4, 0.12, dieD + 0.4], color: [0.55, 0.3, 0.2] });
  put({ name: "die", layer: "die", pos: [dieX, dieY, 0], size: [dieW, family === "wlcsp" ? 0.6 : 0.4, dieD], color: DIE, metalness: 0.35, roughness: 0.4 });
  if (family !== "wlcsp") {
    for (let i = 0; i < 5; i++)
      put({ name: `metal${i}`, layer: "die", pos: [dieX, dieY + 0.21, -0.9 + i * 0.45], size: [dieW - 0.8, 0.03, 0.1], color: [0.7, 0.75, 0.9], metalness: 0.6 });
  } else {
    // WLCSP has no bond wires — the fan-out is redistribution traces on the
    // die surface running to the peripheral bumps
    for (let i = 0; i < 6; i++)
      put({ name: `rdl${i}`, layer: "die", pos: [dieX, dieTop + 0.02, -dieD / 2 + 0.5 + (i * (dieD - 1.0)) / 5], size: [dieW - 0.5, 0.04, 0.14], color: [0.7, 0.75, 0.9], metalness: 0.6 });
  }

  // ── Sensor element (the template's own ASIC silicon) ──
  // Industrial constructions differ by package room: WLCSP/QFN integrate the
  // MEMS monolithically on the CMOS die (one stacked silicon); LGA carries it
  // as a separate wire-bonded MEMS die beside the ASIC (multi-die laminate,
  // BME280 style); the narrow gull-wing current sensors co-integrate the GMR
  // bridge on the die itself — no second die fits a 5 mm body.
  const memsScale = family === "lga" ? 0.8 : Math.min(1, dieW / 4.5);
  const stacked = family === "wlcsp" || family === "qfn";
  const sDY = stacked ? dieTop - 1.1 : 0;
  const sm = (v: number) => v * memsScale;
  const sensX = hasMems ? (stacked ? dieX + dieW * 0.05 : bodyW / 2 - 1.95) : dieX + dieW * 0.15;
  if (hasMems) {
    put({ name: "mems-sub", layer: "sensor", pos: [sensX, 1.2 + sDY, 0], size: [sm(2.4), 0.2, sm(2.4)], color: [0.2, 0.24, 0.34] });
    // diaphragm over a cavity (capacitive MEMS)
    put({ name: "mems-cavity", layer: "sensor", pos: [sensX, 1.35 + sDY, 0], size: [sm(1.6), 0.2, sm(1.6)], color: [0.05, 0.06, 0.1] });
    put({ name: "mems-membrane", layer: "sensor", pos: [sensX, 1.5 + sDY, 0], size: [sm(1.9), 0.08, sm(1.9)], color: [0.62, 0.68, 0.8], metalness: 0.5, opacity: 0.9 });
    // electrodes around the membrane
    for (const [ex, ez] of [[-sm(0.9), -sm(0.9)], [sm(0.9), -sm(0.9)], [-sm(0.9), sm(0.9)], [sm(0.9), sm(0.9)]] as const)
      put({ name: "el", layer: "sensor", pos: [sensX + ex, 1.34 + sDY, ez], size: [0.3, 0.08, 0.3], color: GOLD, metalness: 0.9 });
    if (!stacked) {
      // separate MEMS die: two bond wires out to dedicated substrate pads
      for (const s of [-1, 1] as const) {
        const [px, pz] = [sensX + sm(0.9) + 0.53, s * sm(0.55)];
        put({ name: "sens-pad", layer: "package", pos: [px, 1.14, pz], size: [0.26, 0.05, 0.3], color: GOLD, metalness: 0.9 });
        boxes.push(...bondWire(sensX + sm(0.9), s * sm(0.9), px, pz, 1.42, 1.12));
      }
    }
    // monolithic MEMS needs no wires — the electrodes route into the die metal
  } else {
    // GMR bridge + field coil, co-integrated on the die top (current sensor)
    put({ name: "gmr", layer: "sensor", pos: [sensX, dieTop + 0.15, 0], size: [1.4, 0.3, 1.0], color: [0.45, 0.3, 0.55], metalness: 0.6 });
    put({ name: "coil", layer: "sensor", pos: [sensX, dieTop + 0.4, 0], size: [1.0, 0.12, 0.7], color: GOLD, metalness: 0.9 });
    for (const s of [-1, 1] as const)
      put({ name: `gmr-trace${s}`, layer: "die", pos: [sensX + s * 1.0, dieTop + 0.01, s * 0.1], size: [0.6, 0.03, 0.1], color: [0.7, 0.75, 0.9], metalness: 0.6 });
  }
  // east footprint of the sensor element — the bond ring must clear it
  const sensFootR = hasMems ? sensX + sm(1.2) : dieX + dieW / 2;

  // ── Bond map: one die pad ⇄ one lead-frame finger per wire, same edge ──
  // Industrial lead-frame cross-sections (SOIC/QFN/LQFP) and substrate
  // layouts (LGA) share one rule: the inner fingers ring the die footprint
  // in the moat between die and body wall, and every wire arcs from a die
  // pad to the nearest finger on the SAME side — a fan-out, never a wire
  // crossing over the die, and no fingers over the die or sensor footprint.
  type BondSide = { axis: "z" | "x"; s: number; fingers: [number, number][] };
  const sides: BondSide[] = [];
  if (family === "lga") {
    // substrate fan-out ring around die + sensor; vias drop to the land grid
    const xL = dieX - dieW / 2 - 0.55;
    const xR = sensFootR + 0.55;
    const row = 5;
    for (const s of [-1, 1] as const)
      sides.push({
        axis: "z", s,
        fingers: Array.from({ length: row }, (_, i) => [xL + 0.5 + (i * (xR - xL - 1.0)) / (row - 1), s * (dieD / 2 + 0.55)] as [number, number]),
      });
    sides.push({ axis: "x", s: -1, fingers: [[xL, 0]] });
    sides.push({ axis: "x", s: 1, fingers: [[xR, 0]] });
  } else if (family === "qfn") {
    // inner lead tips ring the die, one row per edge, inside the lands
    const pitchW = (bodyW - 1.6) / (perSide - 1);
    const q0 = -((perSide - 1) * pitchW) / 2;
    for (const s of [-1, 1] as const) {
      sides.push({ axis: "z", s, fingers: Array.from({ length: perSide }, (_, i) => [q0 + i * pitchW, s * (bodyD / 2 - 0.55)] as [number, number]) });
      sides.push({ axis: "x", s, fingers: Array.from({ length: perSide }, (_, i) => [s * (bodyW / 2 - 0.55), q0 + i * pitchW] as [number, number]) });
    }
  } else if (gullWing) {
    // fingers share the lead pitch/origin, so wire, finger and lead read as
    // one continuous lead frame
    for (const s of [-1, 1] as const) {
      sides.push({ axis: "z", s, fingers: Array.from({ length: perSide }, (_, i) => [leadX0 + i * leadPitch, s * (bodyD / 2 - 0.5)] as [number, number]) });
      if (family === "lqfp")
        sides.push({ axis: "x", s, fingers: Array.from({ length: perSide }, (_, i) => [s * (bodyW / 2 - 0.5), leadZ0 + i * leadPitch] as [number, number]) });
    }
  } else {
    for (const s of [-1, 1] as const)
      sides.push({ axis: "z", s, fingers: Array.from({ length: 6 }, (_, i) => [-1.75 + i * 0.7, s * (bodyD / 2 - 0.5)] as [number, number]) });
  }
  for (const { axis, s, fingers } of sides) {
    // die pads: m evenly spaced on the facing die edge (≥0.3 pitch), paired
    // in row order with the fingers → a non-crossing trapezoid fan-out
    const spanHalf = (axis === "z" ? dieW : dieD) / 2 - 0.25;
    const n = fingers.length;
    const m = Math.min(n, Math.max(1, Math.floor((spanHalf * 2) / 0.3)));
    for (let i = 0; i < m; i++) {
      const t = m === 1 ? 0.5 : i / (m - 1);
      const a = -spanHalf + 2 * spanHalf * t;
      const [fx, fz] = fingers[m === 1 ? Math.floor(n / 2) : Math.round((i * (n - 1)) / (m - 1))];
      const [px, pz]: [number, number] = axis === "z" ? [dieX + a, s * dieD / 2] : [dieX + (s * dieW) / 2, a];
      put({ name: "pad", layer: "die", pos: [px, dieY + 0.22, pz], size: [0.26, 0.05, 0.26], color: GOLD, metalness: 0.95, roughness: 0.2 });
      boxes.push(...bondWire(px, pz, fx, fz, dieY + 0.24, 1.12));
      // gold inner-finger tip on the substrate, plus the connection down:
      // QFN wraps the lead tip to its land; LGA drops a via to the land grid
      put({ name: "finger", layer: "package", pos: [fx, 1.12, fz], size: axis === "z" ? [0.34, 0.04, 0.5] : [0.5, 0.04, 0.34], color: [0.8, 0.68, 0.35], metalness: 0.8 });
      if (family === "qfn")
        put({ name: "finger-drop", layer: "package", pos: [fx + (axis === "x" ? s * 0.22 : 0), 0.92, fz + (axis === "z" ? s * 0.22 : 0)], size: [0.14, 0.4, 0.14], color: [0.8, 0.68, 0.35], metalness: 0.8 });
      if (family === "lga")
        put({ name: "finger-via", layer: "package", pos: [fx, 1.1, fz], size: [0.16, 0.05, 0.16], color: [0.3, 0.26, 0.2], cyl: true, metalness: 0.6 });
    }
  }

  const solderLabel = family === "wlcsp" ? "solder/ball" : family === "qfn" || family === "lga" ? "solder/land" : gullWing ? "solder/lead" : "solder/ball";
  const legend: EdaLegendEntry[] = [
    { key: "PCB", label: "PCB", color: PCB, count: boxes.filter((b) => b.layer === "PCB").length },
    { key: "solder", label: solderLabel, color: LEAD, count: boxes.filter((b) => b.layer === "solder").length },
    { key: "package", label: "package", color: SUB, count: boxes.filter((b) => b.layer === "package").length },
    { key: "die", label: "die", color: DIE, count: boxes.filter((b) => b.layer === "die").length },
    { key: "bond", label: "bond wire", color: GOLD, count: boxes.filter((b) => b.layer === "bond").length },
    { key: "sensor", label: "sensor element", color: [0.62, 0.68, 0.8], count: boxes.filter((b) => b.layer === "sensor").length },
    { key: "mold", label: "mold", color: MOLD, count: boxes.filter((b) => b.layer === "mold").length },
    { key: "mark", label: "mark", color: [0.9, 0.9, 0.85], count: boxes.filter((b) => b.layer === "mark").length },
  ];

  // Explode anchors: keep the layer cake in cross-section order (PCB →
  // solder → package → die → bond → sensor → mold → mark) instead of the
  // box-min-y default, which interleaves bond wires under the die.
  return {
    mode: "package",
    boxes,
    legend,
    target: [0, 1.4, 0],
    distance: 26,
    explodeAnchors: { PCB: 0, solder: 0.45, package: 1.15, die: 2.2, bond: 3.4, sensor: 4.5, mold: 5.6, mark: 6.5 },
  };
}
