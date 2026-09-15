import type { EdaBox, EdaLegendEntry, EdaScene, RGB } from "../eda/edaScene";
import type { AsicTemplate } from "./asicModel";

// Package/3D Twin for the ASIC workbench (지시서 §4.4): die outline + pad
// ring, bond wires, mold, package body, PCB footprint + solder joints, and
// the sensor element — assembled from the same EdaBox primitives the EDA
// scenes use, so the existing Eda3DViewer (explode + layer chips) renders it
// unchanged. Geometry is an educational schematic, not a sign-off model
// (§9.3: dims come from real CAD in the enterprise flow).

const GOLD: RGB = [0.96, 0.78, 0.31];
const PCB: RGB = [0.08, 0.28, 0.16];
const SUB: RGB = [0.12, 0.1, 0.09];
const DIE: RGB = [0.35, 0.42, 0.58];
const MOLD: RGB = [0.16, 0.15, 0.14];

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

export function buildPackageScene(tpl: AsicTemplate): EdaScene {
  const boxes: EdaBox[] = [];
  const put = (b: EdaBox) => boxes.push(b);

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

  // ── Package body (y 0.5..1.9) + per-template termination ──
  const bodyW = 11;
  const bodyD = 8;
  put({ name: "substrate", layer: "package", pos: [0, 0.8, 0], size: [bodyW, 0.6, bodyD], color: SUB, roughness: 0.6 });
  // QFN-type exposed pad + perimeter lands; BGA-type ball grid (educational)
  if (tpl.id === "cap_afe") {
    for (let i = 0; i < 8; i++) {
      const x = -4.9 + i * 1.4;
      put({ name: `land${i}`, layer: "solder", pos: [x, 0.62, bodyD / 2 - 0.2], size: [0.7, 0.24, 0.7], color: [0.9, 0.9, 0.92], metalness: 0.85, roughness: 0.35 });
      put({ name: `landb${i}`, layer: "solder", pos: [x, 0.62, -bodyD / 2 + 0.2], size: [0.7, 0.24, 0.7], color: [0.9, 0.9, 0.92], metalness: 0.85, roughness: 0.35 });
    }
    put({ name: "epad", layer: "solder", pos: [0, 0.62, 0], size: [5.5, 0.24, 4.5], color: [0.75, 0.76, 0.8], metalness: 0.85 });
  } else {
    // ball / land grid (WLCSP·LGA·SOIC all shown as grid for the schematic)
    for (let i = 0; i < 6; i++)
      for (let j = 0; j < 4; j++)
        put({ name: `ball${i}-${j}`, layer: "solder", pos: [-3.75 + i * 1.5, 0.55, -2.25 + j * 1.5], size: [0.55, 0.35, 0.55], color: [0.9, 0.9, 0.92], cyl: true, metalness: 0.85, roughness: 0.3 });
  }
  // mold cap: real molding compound is opaque — the assembled product shows
  // only the black body, like an actual packaged chip. The die/bond/MEMS
  // internals stay inspectable via the layer chips (toggle "mold" off) and
  // the explode slider. Sits flush on the substrate (y 1.1..2.1), no gap.
  put({ name: "mold", layer: "mold", pos: [0, 1.6, 0], size: [bodyW, 1.0, bodyD], color: MOLD, roughness: 0.75 });
  // laser mark: die-ID dot matrix on the mold top
  for (let i = 0; i < 5; i++)
    for (let j = 0; j < 3; j++)
      put({ name: `mark${i}${j}`, layer: "mark", pos: [bodyW / 2 - 2.4 + i * 0.5, 2.12, -bodyD / 2 + 1.0 + j * 0.5], size: [0.16, 0.04, 0.16], color: [0.9, 0.9, 0.85] });
  // pin-1 chamfer dot
  put({ name: "pin1", layer: "mark", pos: [-bodyW / 2 + 0.7, 2.12, -bodyD / 2 + 0.7], size: [0.5, 0.05, 0.5], color: [0.95, 0.95, 0.9], cyl: true });

  // ── Die (y 1.1..1.5) + pad ring + tiny routing strips ──
  const dieW = 4.2;
  const dieD = 3.2;
  put({ name: "die-attach", layer: "die", pos: [0, 1.16, 0], size: [dieW + 0.4, 0.12, dieD + 0.4], color: [0.55, 0.3, 0.2] });
  put({ name: "die", layer: "die", pos: [-0.8, 1.42, 0], size: [dieW, 0.4, dieD], color: DIE, metalness: 0.35, roughness: 0.4 });
  // pad ring around the die edge
  const pads: [number, number][] = [];
  for (let i = 0; i < 10; i++) {
    pads.push([-0.8 - dieW / 2 + 0.25 + (i * (dieW - 0.5)) / 9, -dieD / 2]);
    pads.push([-0.8 - dieW / 2 + 0.25 + (i * (dieW - 0.5)) / 9, dieD / 2]);
  }
  for (let i = 0; i < 6; i++) {
    pads.push([-0.8 - dieW / 2, -dieD / 2 + 0.3 + (i * (dieD - 0.6)) / 5]);
    pads.push([-0.8 + dieW / 2, -dieD / 2 + 0.3 + (i * (dieD - 0.6)) / 5]);
  }
  for (const [px, pz] of pads)
    put({ name: "pad", layer: "die", pos: [px, 1.64, pz], size: [0.28, 0.05, 0.28], color: GOLD, metalness: 0.95, roughness: 0.2 });
  // micro routing strips on the die (educational hint of the metal stack)
  for (let i = 0; i < 5; i++)
    put({ name: `metal${i}`, layer: "die", pos: [-0.8, 1.63, -0.9 + i * 0.45], size: [dieW - 0.8, 0.03, 0.1], color: [0.7, 0.75, 0.9], metalness: 0.6 });

  // ── Sensor element (adjacent die for multi-die / MEMS templates) ──
  if (tpl.id === "cap_afe" || tpl.id === "env_sensor") {
    put({ name: "mems-sub", layer: "sensor", pos: [3.4, 1.2, 0], size: [2.4, 0.2, 2.4], color: [0.2, 0.24, 0.34] });
    // diaphragm over a cavity (capacitive MEMS)
    put({ name: "mems-cavity", layer: "sensor", pos: [3.4, 1.35, 0], size: [1.6, 0.2, 1.6], color: [0.05, 0.06, 0.1] });
    put({ name: "mems-membrane", layer: "sensor", pos: [3.4, 1.5, 0], size: [1.9, 0.08, 1.9], color: [0.62, 0.68, 0.8], metalness: 0.5, opacity: 0.9 });
    // electrodes around the membrane
    for (const [ex, ez] of [[2.5, -0.9], [4.3, -0.9], [2.5, 0.9], [4.3, 0.9]] as const)
      put({ name: "el", layer: "sensor", pos: [ex, 1.34, ez], size: [0.3, 0.08, 0.3], color: GOLD, metalness: 0.9 });
    for (const [bx, bz] of [[2.5, 0], [4.3, 0]] as const)
      boxes.push(...bondWire(bx, bz, bx * 0.55, bz, 1.5, 1.1));
  } else {
    // GMR element on a lead frame (current sensor) / sense pair (motor)
    put({ name: "gmr", layer: "sensor", pos: [3.2, 1.3, 0], size: [1.4, 0.3, 1.0], color: [0.45, 0.3, 0.55], metalness: 0.6 });
    put({ name: "coil", layer: "sensor", pos: [3.2, 1.55, 0], size: [1.0, 0.12, 0.7], color: GOLD, metalness: 0.9 });
    boxes.push(...bondWire(3.9, 0.3, 3.2, 0.2, 1.5, 1.1));
    boxes.push(...bondWire(3.9, -0.3, 3.2, -0.2, 1.5, 1.1));
  }

  // ── Bond wires: die pad ring → substrate fingers ──
  const fingers: [number, number][] = [];
  for (let i = 0; i < 10; i++) {
    fingers.push([-0.8 - dieW / 2 + 0.25 + (i * (dieW - 0.5)) / 9, -3.4]);
    fingers.push([-0.8 - dieW / 2 + 0.25 + (i * (dieW - 0.5)) / 9, 3.4]);
  }
  for (const [fx, fz] of fingers) {
    boxes.push(...bondWire(fx, fz * 0.62, fx, fz, 1.66, 1.1));
    put({ name: "finger", layer: "package", pos: [fx, 1.12, fz], size: [0.3, 0.04, 0.5], color: [0.8, 0.68, 0.35], metalness: 0.8 });
  }
  for (const [px, pz] of pads.slice(0, 8)) boxes.push(...bondWire(px, pz, px, pz * 1.9, 1.66, 1.1));

  const legend: EdaLegendEntry[] = [
    { key: "PCB", label: "PCB", color: PCB, count: boxes.filter((b) => b.layer === "PCB").length },
    { key: "solder", label: "solder/ball", color: [0.9, 0.9, 0.92], count: boxes.filter((b) => b.layer === "solder").length },
    { key: "package", label: "package", color: SUB, count: boxes.filter((b) => b.layer === "package").length },
    { key: "die", label: "die", color: DIE, count: boxes.filter((b) => b.layer === "die").length },
    { key: "bond", label: "bond wire", color: GOLD, count: boxes.filter((b) => b.layer === "bond").length },
    { key: "sensor", label: "sensor element", color: [0.62, 0.68, 0.8], count: boxes.filter((b) => b.layer === "sensor").length },
    { key: "mold", label: "mold", color: MOLD, count: boxes.filter((b) => b.layer === "mold").length },
    { key: "mark", label: "mark", color: [0.9, 0.9, 0.85], count: boxes.filter((b) => b.layer === "mark").length },
  ];

  return { mode: "package", boxes, legend, target: [0, 1.4, 0], distance: 26 };
}
