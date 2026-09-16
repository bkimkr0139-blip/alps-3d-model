import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import * as THREE from "three";
import { Canvas, useFrame } from "@react-three/fiber";
import { OrbitControls } from "@react-three/drei";
import type { ComponentDto, Product, SimulationRun } from "../lib/api";
import { useTwinStore, useBenchStore } from "../store";
import { ViewerEnvironment } from "./ThreeViewer";
import { FSOverlay } from "./FSOverlay";
import { canvasTextTexture } from "../ui/canvasText";
import { HudChip } from "../ui/kit";
import { accent, border, bg, status as S } from "../ui/tokens";
import { AIR_STATE_COLOR } from "../lib/air";

// Virtual dev/test board (S04 second tab): an industry-standard-parts board —
// FR4 PCB, the DUT (the selected product's part), 0603 pull-up/decoupling, an
// MCU, a pin header and an indicator LED — whose operating state drives a
// two-channel oscilloscope and a circuit-test table. The circuit-test rows
// anchor to the variant's REAL latest SPICE run (v_out_rc_* worst case vs the
// 1.0 V logic-low limit); the waveforms themselves are demo visualization.

export type BenchFamily = "tact" | "encoder" | "mems" | "air";

function benchFamilyOf(product: Product | null): BenchFamily {
  const n = `${product?.name ?? ""} ${product?.business_id ?? ""}`.toLowerCase();
  // airinput BEFORE the generic "sensor"→mems catch: "AirInput Proximity
  // Sensor" must bench its own module, not the MEMS pressure board.
  if (n.includes("airinput") || n.includes("proximity")) return "air";
  if (n.includes("encoder")) return "encoder";
  if (n.includes("mems") || n.includes("pressure") || n.includes("sensor")) return "mems";
  return "tact";
}

// Which 3D-component names ARE this bench's part family — the L187 selection
// sync only lights the DUT when the selected component really is the part on
// the bench, never when an unrelated part happens to be selected. The air
// module benches as a whole (housing/electrode/ASIC/cover are one potted
// puck), so any of its BOM names counts as "the benched part".
const FAMILY_KIND: Record<BenchFamily, RegExp> = {
  tact: /switch|tact|dome|plunger/i,
  encoder: /encoder|rotary|shaft|detent/i,
  mems: /pressure|sensor|mems|bridge|diaphragm/i,
  air: /airinput|electrode|cover|housing|capacitive|proximity/i,
};

// Bench-local controls (encoder rotation) live in the shared store module so
// both the board overlay and the F–S cursor overlay read the same state
// without a component-module cycle.

/* ------------------------------ board parts ------------------------------ */

// Silkscreen labels without a font CDN: rasterize text into a local canvas
// and use it as an alpha-mapped plane lying flat on the PCB. (The rasterizer
// itself now lives in ui/canvasText.ts, shared with the factory station signs.)
function silkTexture(text: string): THREE.CanvasTexture {
  return canvasTextTexture(text);
}

function SilkLabel({ text, position, width = 6 }: { text: string; position: [number, number, number]; width?: number }) {
  const map = useMemo(() => silkTexture(text), [text]);
  return (
    <mesh position={position} rotation={[-Math.PI / 2, 0, 0]}>
      <planeGeometry args={[width, width / 4]} />
      <meshBasicMaterial map={map} transparent depthWrite={false} />
    </mesh>
  );
}

/* ------------------------------ pcb artwork ------------------------------- */
// Industry-standard routing: traces run Manhattan with 45° mitered corners
// (real etch practice — no arbitrary diagonals, no 90° corners) and always
// terminate on a copper pad at a part terminal, never mid-air. Signal and
// power nets use different trace widths, like a real stackup.

type XY = [number, number];

const TRACE_W_SIGNAL = 0.5;
const TRACE_W_POWER = 0.8;
const MITER = 0.9; // 45° miter leg — clamped per route so short hops stay valid

/** Manhattan route A→B with one 45° mitered corner. `orientation` picks the
 * long-run axis first ("h": run along x then turn; "v": run along z first). */
function routeMitered(a: XY, b: XY, orientation: "h" | "v" = "h"): XY[] {
  const [x1, z1] = a;
  const [x2, z2] = b;
  const dx = x2 - x1;
  const dz = z2 - z1;
  if (dx === 0 || dz === 0) return [a, b];
  const sx = Math.sign(dx);
  const sz = Math.sign(dz);
  const m = Math.min(MITER, Math.abs(dx) / 2, Math.abs(dz) / 2);
  if (orientation === "h") {
    // horizontal run into a corner at (x2, z1), 45° miter, vertical into B
    return [a, [x2 - sx * m, z1], [x2, z1 + sz * m], b];
  }
  // vertical run into a corner at (x1, z2), 45° miter, horizontal into B
  return [a, [x1, z2 - sz * m], [x1 + sx * m, z2], b];
}

function TracePath({ points, width = TRACE_W_SIGNAL, z = 0.03 }: { points: XY[]; width?: number; z?: number }) {
  const segs = useMemo(() => {
    const out: { cx: number; cz: number; len: number; angle: number }[] = [];
    for (let i = 0; i < points.length - 1; i++) {
      const [x1, z1] = points[i];
      const [x2, z2] = points[i + 1];
      const len = Math.hypot(x2 - x1, z2 - z1);
      if (len < 1e-6) continue;
      // extend by the trace width so mitered joints close without gaps
      out.push({ cx: (x1 + x2) / 2, cz: (z1 + z2) / 2, len: len + width, angle: Math.atan2(z2 - z1, x2 - x1) });
    }
    return out;
  }, [points, width]);
  return (
    <group>
      {segs.map((s, i) => (
        <mesh key={i} position={[s.cx, z, s.cz]} rotation={[0, -s.angle, 0]}>
          <boxGeometry args={[s.len, 0.04, width]} />
          <meshStandardMaterial color="#0f9d49" roughness={0.55} />
        </mesh>
      ))}
    </group>
  );
}

function SmdPad({ x, z, w = 1.0, d = 0.7 }: { x: number; z: number; w?: number; d?: number }) {
  return (
    <mesh position={[x, 0.035, z]}>
      <boxGeometry args={[w, 0.05, d]} />
      <meshStandardMaterial color="#cfd4da" metalness={0.9} roughness={0.25} />
    </mesh>
  );
}

function ThroughHolePad({ x, z }: { x: number; z: number }) {
  // annular ring: copper disc with a darker drilled hole through it
  return (
    <group position={[x, 0.035, z]}>
      <mesh>
        <cylinderGeometry args={[0.62, 0.62, 0.05, 20]} />
        <meshStandardMaterial color="#cfd4da" metalness={0.9} roughness={0.25} />
      </mesh>
      <mesh position={[0, 0.01, 0]}>
        <cylinderGeometry args={[0.28, 0.28, 0.08, 14]} />
        <meshStandardMaterial color="#334155" roughness={0.6} />
      </mesh>
    </group>
  );
}

// Exact copper geometry per part (board-local x/z). Traces are wired to these
// constants — a route may only start/end at one of these pads, and every pad
// is centered under its part's terminal (verified against each part group's
// position + terminal offsets).
const MCU_PIN_Z = [-2.4, -0.8, 0.8, 2.4];
const MCU_LEFT_X = 3.4; // input-side pins (Mcu group x=7, pins at local ±3.6)
const MCU_RIGHT_X = 10.6; // output-side pins
// PinHeader group sits at [14, 0, 2] with pins at local z ∈ {-2.6, 0, 2.6}
// → world z = {-0.6, 2.0, 4.6} for SW / GND / VCC.
const J1_PIN_Z = [-0.6, 2.0, 4.6];
// ChipResistor body 2.4 long, end caps centered at local x=±1.25 → pads at
// -2±1.25.
const R1_PADS: [XY, XY] = [[-3.25, -7], [-0.75, -7]];
const C1_PADS: [XY, XY] = [[-3.25, -3.5], [-0.75, -3.5]];
// LED body 3.2×1.6 centered (8, -6.5) → pads just outside each end.
const LED_PADS: [XY, XY] = [[6.0, -6.5], [10.0, -6.5]];

// DUT terminal pads differ per package — routes must follow the actual part.
// Pad sizes match each package's terminal footprint; left terminals land on
// the ground side (no routed trace — via the plane).
const DUT_PADS: Record<BenchFamily, { right: XY[]; left: XY[]; pad: [number, number] }> = {
  tact: { right: [[-6.4, 2.6], [-6.4, -2.6]], left: [[-11.6, 2.6], [-11.6, -2.6]], pad: [1.9, 1.5] },
  encoder: { right: [[-4.4, 0]], left: [[-13.6, 0]], pad: [1.8, 6.4] },
  mems: { right: [[-6.6, 2.4], [-6.6, -2.4]], left: [[-11.4, 2.4], [-11.4, -2.4]], pad: [1.6, 1.6] },
  // AirInput module's four castellated terminals at the scaled puck's edges
  // (body spans x −15.1…−2.9 — pads tuck half under the edge like tact's).
  air: { right: [[-3.5, 2], [-3.5, -2]], left: [[-14.5, 2], [-14.5, -2]], pad: [1.6, 1.6] },
};
// Which MCU input pin each DUT terminal lands on (SW node shares a pin with
// the C1 decoupling route — a real junction, covered by the pin's pad).
const DUT_TO_PIN: Record<BenchFamily, XY[]> = {
  tact: [[3.4, 2.4], [3.4, -0.8]],
  encoder: [[3.4, -0.8]],
  mems: [[3.4, 2.4], [3.4, -2.4]],
  air: [[3.4, 2.4], [3.4, -2.4]],
};

function ChipResistor({ position, bodyColor = "#3f3f46" }: { position: [number, number, number]; bodyColor?: string }) {
  // 0603-style two-terminal chip: ceramic body + metallic end caps.
  return (
    <group position={position}>
      <mesh>
        <boxGeometry args={[2.4, 0.6, 1.2]} />
        <meshStandardMaterial color={bodyColor} roughness={0.5} />
      </mesh>
      {[-1.25, 1.25].map((x) => (
        <mesh key={x} position={[x, 0, 0]}>
          <boxGeometry args={[0.5, 0.62, 1.24]} />
          <meshStandardMaterial color="#d1d5db" metalness={0.8} roughness={0.3} />
        </mesh>
      ))}
    </group>
  );
}

// Tact DUT: black 6×6 body, silver cap. Click toggles the shared actuated
// state — the same store the S04 3D viewer uses, so both views stay in sync.
// The bench DUT lights (accent-orange pulse) only while the selected 3D
// component belongs to this bench's part family.
function useDutHighlight(matched: boolean) {
  const body = useRef<THREE.MeshStandardMaterial>(null);
  useFrame(({ clock }) => {
    if (body.current) body.current.emissiveIntensity = matched ? 0.5 + 0.25 * Math.sin(clock.elapsedTime * 3.2) : 0;
  });
  return body;
}

function TactDut({ matched }: { matched: boolean }) {
  const actuated = useTwinStore((s) => s.actuated);
  const setActuated = useTwinStore((s) => s.setActuated);
  const cap = useRef<THREE.Mesh>(null);
  const act = useRef(0);
  const bodyMat = useDutHighlight(matched);

  useFrame((_, dt) => {
    act.current += ((actuated ? 1 : 0) - act.current) * Math.min(1, dt * 22);
    if (cap.current) cap.current.position.y = 4.6 - 0.3 * act.current;
  });

  return (
    <group
      position={[-9, 0, 0]}
      onClick={(e) => {
        e.stopPropagation();
        setActuated(!actuated);
      }}
      onPointerOver={(e: any) => (e.object.cursor = "pointer")}
    >
      <mesh position={[0, 2.15, 0]}>
        <boxGeometry args={[6, 4.3, 6]} />
        <meshStandardMaterial ref={bodyMat} color="#111114" emissive="#f97316" emissiveIntensity={0} roughness={0.55} />
      </mesh>
      <mesh ref={cap} position={[0, 4.6, 0]}>
        <cylinderGeometry args={[1.6, 1.6, 0.7, 24]} />
        <meshStandardMaterial color="#9ca3af" metalness={0.85} roughness={0.3} />
      </mesh>
      {[[-2.6, -2.6], [2.6, -2.6], [-2.6, 2.6], [2.6, 2.6]].map(([x, z]) => (
        <mesh key={`${x}${z}`} position={[x, 0.2, z]}>
          <boxGeometry args={[1.6, 0.4, 1.2]} />
          <meshStandardMaterial color="#d1d5db" metalness={0.8} roughness={0.35} />
        </mesh>
      ))}
    </group>
  );
}

function EncoderDut({ matched }: { matched: boolean }) {
  const rotating = useBenchStore((s) => s.rotating);
  const setRotating = useBenchStore((s) => s.setRotating);
  const shaft = useRef<THREE.Mesh>(null);
  const bodyMat = useDutHighlight(matched);
  useFrame((_, dt) => {
    if (shaft.current && rotating) shaft.current.rotation.y += dt * 5;
  });
  return (
    <group
      position={[-9, 0, 0]}
      onClick={(e) => {
        e.stopPropagation();
        setRotating(!rotating);
      }}
      onPointerOver={(e: any) => (e.object.cursor = "pointer")}
    >
      <mesh position={[0, 6.5, 0]}>
        <boxGeometry args={[10, 13, 10]} />
        <meshStandardMaterial ref={bodyMat} color="#52525b" emissive="#f97316" emissiveIntensity={0} metalness={0.85} roughness={0.4} />
      </mesh>
      <mesh ref={shaft} position={[0, 15.5, 0]}>
        <cylinderGeometry args={[3.4, 3.4, 6.5, 12]} />
        <meshStandardMaterial color="#3f3f46" metalness={0.7} roughness={0.45} flatShading />
      </mesh>
      {[-4.6, 4.6].map((x) => (
        <mesh key={x} position={[x, 0.2, 0]}>
          <boxGeometry args={[1.4, 0.4, 6]} />
          <meshStandardMaterial color="#d1d5db" metalness={0.8} roughness={0.35} />
        </mesh>
      ))}
    </group>
  );
}

function MemsDut({ pressure, matched }: { pressure: number; matched: boolean }) {
  const port = useRef<THREE.Mesh>(null);
  const bodyMat = useDutHighlight(matched);
  // Port "pressurizes": the tiny port insert darkens as drive pressure rises.
  useFrame(() => {
    if (port.current) {
      const mat = port.current.material as THREE.MeshStandardMaterial;
      mat.color.setRGB(0.15 + 0.55 * (pressure / 400), 0.15, 0.15);
    }
  });
  return (
    <group position={[-9, 0, 0]}>
      <mesh position={[0, 0.85, 0]}>
        <boxGeometry args={[6, 1.7, 6]} />
        <meshStandardMaterial ref={bodyMat} color="#111114" emissive="#f97316" emissiveIntensity={0} roughness={0.5} />
      </mesh>
      <mesh position={[0, 1.95, 0]}>
        <boxGeometry args={[5.4, 0.5, 5.4]} />
        <meshStandardMaterial color="#9ca3af" metalness={0.9} roughness={0.25} />
      </mesh>
      <mesh ref={port} position={[0, 2.3, 0]}>
        <cylinderGeometry args={[0.8, 0.8, 0.25, 16]} />
        <meshStandardMaterial color="#333" roughness={0.6} />
      </mesh>
      {[[-2.4, -2.4], [2.4, -2.4], [-2.4, 2.4], [2.4, 2.4]].map(([x, z]) => (
        <mesh key={`${x}${z}`} position={[x, 0.2, z]}>
          <boxGeometry args={[1.2, 0.4, 1.2]} />
          <meshStandardMaterial color="#d1d5db" metalness={0.8} roughness={0.35} />
        </mesh>
      ))}
    </group>
  );
}

// AirInput DUT: the puck-style capacitive proximity module — housing shell,
// PCB, electrode, ASIC paddle and cover glass — with the same materials and
// proportions as the air tab's field twin (AirScene) and the CAD GLB, so the
// dev view and this test view read as the same physical part. The real module
// is 34×28×6.5 mm; the demo bench board is 32×22 units, so the puck renders
// at bench scale 0.36. Electrode follows the variant: Layout B shows the
// split ring (the name in the seed carries "Layout B / split-ring").
const AIR_SCALE = 0.36;
const AIR_ELEC_X = 5 * AIR_SCALE;
const AIR_PAD_R = Math.sqrt(100 / Math.PI) * AIR_SCALE; // solid 100 mm² pad
const AIR_RING_OUTER = 8.5 * AIR_SCALE; // LAYOUT_B_OUTER_R_MM
const AIR_RING_INNER = Math.sqrt(8.5 ** 2 - 160 / Math.PI) * AIR_SCALE; // 160 mm² annulus
const AIR_PCB_TOP = 2.8 * AIR_SCALE;
const AIR_HOUSE_TOP = 6.5 * AIR_SCALE;

function AirDut({ near, matched, splitRing }: { near: boolean; matched: boolean; splitRing: boolean }) {
  const bodyMat = useDutHighlight(matched);
  const tip = useRef<THREE.Mesh>(null);
  const elec = useRef<THREE.MeshStandardMaterial>(null);
  useFrame(({ clock }, dt) => {
    // fingertip stimulus lowers onto the cover; electrode pulses the live
    // TOUCH color while near (same palette as the air tab's state legend)
    if (tip.current) tip.current.position.y += ((near ? AIR_HOUSE_TOP + 1.6 : 6.2) - tip.current.position.y) * Math.min(1, dt * 14);
    if (elec.current) elec.current.emissiveIntensity = near ? 0.55 + 0.25 * Math.sin(clock.elapsedTime * 3.2) : 0;
  });

  const electrodeMats = {
    color: "#facc15",
    metalness: 0.8,
    roughness: 0.3,
  } as const;

  return (
    <group position={[-9, 0, 0]}>
      <mesh ref={tip} position={[AIR_ELEC_X, 6.2, 0]}>
        <sphereGeometry args={[1.5, 20, 16]} />
        <meshStandardMaterial color="#e8b08c" roughness={0.65} />
      </mesh>
      {/* translucent housing shell (same X-ray read as AirScene) */}
      <mesh position={[0, AIR_HOUSE_TOP / 2, 0]}>
        <boxGeometry args={[34 * AIR_SCALE, AIR_HOUSE_TOP, 28 * AIR_SCALE]} />
        <meshStandardMaterial ref={bodyMat} color="#334155" transparent opacity={0.5} roughness={0.5} emissive="#f97316" emissiveIntensity={0} depthWrite={false} />
      </mesh>
      {/* PCB */}
      <mesh position={[0, 2 * AIR_SCALE, 0]}>
        <boxGeometry args={[30 * AIR_SCALE, 1.6 * AIR_SCALE, 24 * AIR_SCALE]} />
        <meshStandardMaterial color="#14532d" roughness={0.7} />
      </mesh>
      {splitRing ? (
        // Layout B: two half-rings split at z = 0 (AirScene's E1/E2 read)
        ([false, true] as const).map((flip) => (
          <mesh key={flip ? "e1" : "e2"} position={[0, AIR_PCB_TOP + 0.02, flip ? 0.02 : -0.02]} rotation={[-Math.PI / 2, 0, flip ? Math.PI : 0]}>
            <ringGeometry args={[AIR_RING_INNER, AIR_RING_OUTER, 40, 1, 0, Math.PI]} />
            <meshStandardMaterial ref={flip ? elec : undefined} {...electrodeMats} emissive={AIR_STATE_COLOR.TOUCH} emissiveIntensity={0} />
          </mesh>
        ))
      ) : (
        <mesh position={[AIR_ELEC_X, AIR_PCB_TOP + 0.02, 0]} rotation={[-Math.PI / 2, 0, 0]}>
          <circleGeometry args={[AIR_PAD_R, 40]} />
          <meshStandardMaterial ref={elec} {...electrodeMats} emissive={AIR_STATE_COLOR.TOUCH} emissiveIntensity={0} />
        </mesh>
      )}
      {/* ASIC QFN paddle (grounded shield mass, at the worker's (−9, 4)) */}
      <mesh position={[-9 * AIR_SCALE, AIR_PCB_TOP + 0.02, -4 * AIR_SCALE]}>
        <boxGeometry args={[5 * AIR_SCALE, 0.05, 5 * AIR_SCALE]} />
        <meshStandardMaterial color="#94a3b8" metalness={0.9} roughness={0.2} />
      </mesh>
      {/* cover glass (touch surface) */}
      <mesh position={[0, AIR_HOUSE_TOP - 0.5 * AIR_SCALE, 0]}>
        <boxGeometry args={[30.6 * AIR_SCALE, 1.0 * AIR_SCALE, 27.6 * AIR_SCALE]} />
        <meshStandardMaterial color="#7dd3fc" transparent opacity={0.25} depthWrite={false} />
      </mesh>
      {/* castellated corner terminals */}
      {[[-5, -3.9], [5, -3.9], [-5, 3.9], [5, 3.9]].map(([x, z]) => (
        <mesh key={`${x}${z}`} position={[x, 0.2, z]}>
          <boxGeometry args={[1.3, 0.4, 1.3]} />
          <meshStandardMaterial color="#d1d5db" metalness={0.8} roughness={0.35} />
        </mesh>
      ))}
    </group>
  );
}

function IndicatorLed({ level }: { level: number }) {
  const led = useRef<THREE.MeshStandardMaterial>(null);
  useFrame(() => {
    if (led.current) led.current.emissiveIntensity = 0.15 + level * 2.2;
  });
  return (
    <mesh position={[8, 0.5, -6.5]}>
      <boxGeometry args={[3.2, 1, 1.6]} />
      <meshStandardMaterial ref={led} color="#7f1d1d" emissive="#ef4444" emissiveIntensity={0.15} roughness={0.4} />
    </mesh>
  );
}

function Mcu() {
  return (
    <group position={[7, 0, 0]}>
      <mesh position={[0, 0.7, 0]}>
        <boxGeometry args={[7, 1.4, 7]} />
        <meshStandardMaterial color="#18181b" roughness={0.5} />
      </mesh>
      {[-3.6, 3.6].map((x) =>
        [-2.4, -0.8, 0.8, 2.4].map((z) => (
          <mesh key={`${x}${z}`} position={[x, 0.35, z]}>
            <boxGeometry args={[0.6, 0.2, 0.5]} />
            <meshStandardMaterial color="#d1d5db" metalness={0.8} roughness={0.3} />
          </mesh>
        ))
      )}
    </group>
  );
}

function PinHeader() {
  return (
    <group position={[14, 0, 2]}>
      <mesh position={[0, 2, 0]}>
        <boxGeometry args={[2.6, 4, 8]} />
        <meshStandardMaterial color="#18181b" roughness={0.5} />
      </mesh>
      {[-2.6, 0, 2.6].map((z) => (
        <mesh key={z} position={[0, 5, z]}>
          <cylinderGeometry args={[0.35, 0.35, 2.5, 10]} />
          <meshStandardMaterial color="#e5e7eb" metalness={0.9} roughness={0.2} />
        </mesh>
      ))}
    </group>
  );
}

// Scope probe wires: tubes arcing off the board toward the instrument. They
// exist to show WHICH node each scope channel measures — so every wire must
// START on a real connection point, never mid-air, and carry a visible probe
// clip at that joint. Nets match the scope legend exactly: CH1 = raw SW node
// = the MCU input pin (DUT + R1 + C1 net); CH2 = debounced output = the MCU
// output pin. Module-level point lists keep geometry memoization stable.
const PROBE_CH1: [number, number, number][] = [[3.4, 0.55, -0.8], [5.5, 5.5, -3.5], [8.5, 10.5, -7.5], [12, 13.5, -10.5]];
const PROBE_CH2: [number, number, number][] = [[10.6, 0.55, 0.8], [12.5, 5, -4], [15, 9.5, -9], [17, 13, -11]];
function ProbeWire({ color, points, clipAt }: { color: string; points: [number, number, number][]; clipAt: [number, number, number] }) {
  const geometry = useMemo(() => {
    const curve = new THREE.CatmullRomCurve3(points.map((p) => new THREE.Vector3(...p)));
    return new THREE.TubeGeometry(curve, 40, 0.28, 8, false);
  }, [points]);
  return (
    <group>
      <mesh geometry={geometry}>
        <meshStandardMaterial color={color} roughness={0.6} />
      </mesh>
      {/* probe clip body + tip hugging the measured pin */}
      <mesh position={[clipAt[0], clipAt[1] + 0.55, clipAt[2]]}>
        <cylinderGeometry args={[0.55, 0.55, 1.1, 12]} />
        <meshStandardMaterial color="#27272a" roughness={0.45} />
      </mesh>
      <mesh position={clipAt}>
        <cylinderGeometry args={[0.22, 0.22, 0.7, 10]} />
        <meshStandardMaterial color="#e5e7eb" metalness={0.9} roughness={0.2} />
      </mesh>
    </group>
  );
}

function Board({ family, pressure, near, splitRing, dutMatched }: { family: BenchFamily; pressure: number; near: boolean; splitRing: boolean; dutMatched: boolean }) {
  const actuated = useTwinStore((s) => s.actuated);
  const rotating = useBenchStore((s) => s.rotating);
  const ledLevel =
    family === "tact" ? (actuated ? 1 : 0) : family === "encoder" ? (rotating ? 1 : 0) : family === "air" ? (near ? 1 : 0) : pressure / 400;

  return (
    <group>
      <mesh position={[0, -0.8, 0]}>
        <boxGeometry args={[32, 1.6, 22]} />
        <meshStandardMaterial color="#0a5c2e" roughness={0.7} />
      </mesh>
      {[[-14.5, -9.5], [14.5, -9.5], [-14.5, 9.5], [14.5, 9.5]].map(([x, z]) => (
        <mesh key={`${x}${z}`} position={[x, 0, z]}>
          <cylinderGeometry args={[1, 1, 2, 12]} />
          <meshStandardMaterial color="#e5e7eb" metalness={0.9} roughness={0.25} />
        </mesh>
      ))}

      {family === "tact" && <TactDut matched={dutMatched} />}
      {family === "encoder" && <EncoderDut matched={dutMatched} />}
      {family === "mems" && <MemsDut pressure={pressure} matched={dutMatched} />}
      {family === "air" && <AirDut near={near} matched={dutMatched} splitRing={splitRing} />}

      <Mcu />
      <PinHeader />
      <IndicatorLed level={ledLevel} />
      <ChipResistor position={[-2, 0.5, -7]} />
      <ChipResistor position={[-2, 0.5, -3.5]} bodyColor="#b45309" />

      {/* copper pads under every soldered terminal — exact terminal centers */}
      {[...DUT_PADS[family].right, ...DUT_PADS[family].left].map(([x, z]) => (
        <SmdPad key={`dut${x}${z}`} x={x} z={z} w={DUT_PADS[family].pad[0]} d={DUT_PADS[family].pad[1]} />
      ))}
      {MCU_PIN_Z.map((z) => (
        <SmdPad key={`mcul${z}`} x={MCU_LEFT_X} z={z} w={1.0} d={0.8} />
      ))}
      {MCU_PIN_Z.map((z) => (
        <SmdPad key={`mcur${z}`} x={MCU_RIGHT_X} z={z} w={1.0} d={0.8} />
      ))}
      {R1_PADS.map(([x, z]) => (
        <SmdPad key={`r1${x}${z}`} x={x} z={z} w={0.9} d={1.4} />
      ))}
      {C1_PADS.map(([x, z]) => (
        <SmdPad key={`c1${x}${z}`} x={x} z={z} w={0.9} d={1.4} />
      ))}
      {LED_PADS.map(([x, z]) => (
        <SmdPad key={`led${x}${z}`} x={x} z={z} w={1.0} d={1.4} />
      ))}
      {J1_PIN_Z.map((z) => (
        <ThroughHolePad key={`j1${z}`} x={14} z={z} />
      ))}

      {/* routed nets — every endpoint is a pad constant above */}
      {DUT_PADS[family].right.map((p, i) => (
        <TracePath key={`dut-trace-${i}`} points={routeMitered(p, DUT_TO_PIN[family][i], "h")} />
      ))}
      {/* MCU output pin (the CH2 net) → J1 SW (through-hole) */}
      <TracePath points={routeMitered([MCU_RIGHT_X, 0.8], [14, J1_PIN_Z[0]], "h")} />
      {/* R1 pull-up rail → LED anode (power width) */}
      <TracePath points={routeMitered(R1_PADS[1], LED_PADS[0], "h")} width={TRACE_W_POWER} />
      {/* C1 decoupling onto the SW-node MCU pin (vertical-first, so the final
          approach doesn't cross the z=-2.4 pin pad) */}
      <TracePath points={routeMitered(C1_PADS[1], [MCU_LEFT_X, -0.8], "v")} />
      {/* VCC in from the header (power width) */}
      <TracePath points={routeMitered([14, J1_PIN_Z[2]], [MCU_RIGHT_X, 2.4], "h")} width={TRACE_W_POWER} />

      <SilkLabel text={family === "air" ? "U1 PROX" : "SW1"} position={[-9, 0.03, family === "air" ? 6.8 : 4.6]} />
      <SilkLabel text="MCU" position={[7, 0.03, 5]} />
      <SilkLabel text="R1 10k" position={[-2, 0.03, -8.4]} width={4} />
      <SilkLabel text="C1 100n" position={[-2, 0.03, -4.9]} width={4.4} />
      <SilkLabel text="J1" position={[14, 0.03, 6.4]} width={3} />
      <SilkLabel text="SW" position={[16.4, 0.03, J1_PIN_Z[0]]} width={3} />
      <SilkLabel text="GND" position={[16.4, 0.03, J1_PIN_Z[1]]} width={3.4} />
      <SilkLabel text="VCC" position={[16.4, 0.03, J1_PIN_Z[2]]} width={3.4} />

      {/* CH1 clips the raw SW node (MCU input pin), CH2 the debounced output */}
      <ProbeWire color="#facc15" points={PROBE_CH1} clipAt={[MCU_LEFT_X, 0.55, -0.8]} />
      <ProbeWire color="#38bdf8" points={PROBE_CH2} clipAt={[MCU_RIGHT_X, 0.55, 0.8]} />
    </group>
  );
}

/* ------------------------------ oscilloscope ----------------------------- */

const SAMPLE_DT = 0.0005; // 0.5 ms of simulated time per sample
const WINDOW = 1200; // samples shown → 600 ms → 60 ms/div
const VCC = 3.3;
const LOGIC_LOW_LIMIT_V = 1.0;

function Scope({ family, pressure, near, running }: { family: BenchFamily; pressure: number; near: boolean; running: boolean }) {
  const { t } = useTranslation();
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const buf = useRef({ v1: new Float32Array(WINDOW), v2: new Float32Array(WINDOW), head: 0, count: 0 });
  // Mutable latest inputs for the rAF loop (no re-subscribe on prop change).
  const inputRef = useRef({ family, pressure, near, running });
  useEffect(() => {
    inputRef.current = { family, pressure, near, running };
  }, [family, pressure, near, running]);
  // Channel state machine
  const sim = useRef({ phase: 0, bounceT: 0, v1: 1, v2: 1, lastAct: false, touch: false });

  useEffect(() => {
    const canvas = canvasRef.current!;
    const ctx = canvas.getContext("2d")!;
    let raf = 0;
    let last = performance.now();
    let acc = 0;

    const step = (dt: number) => {
      const s = sim.current;
      const { family: fam, pressure: pres } = inputRef.current;
      const store = useTwinStore.getState();
      if (fam === "tact") {
        // Arm the bounce train on the press EDGE only — re-arming every
        // sample made a held switch bounce forever.
        if (store.actuated && !s.lastAct && s.bounceT <= 0) s.bounceT = 0.012; // 12 ms of contact bounce per press
        s.lastAct = store.actuated;
        if (s.bounceT > 0) {
          s.bounceT -= dt;
          s.v1 = store.actuated ? (Math.random() < 0.5 ? 0 : 1) : 1;
        } else {
          s.v1 = store.actuated ? 0.006 : 1;
          if (store.vibration && !store.actuated) {
            // Vehicle vibration: tiny noise dips on the open line (no false
            // trigger — the debounced channel stays clean).
            if (Math.random() < 0.08) s.v1 = 1 - 0.25 * Math.random();
          }
        }
        s.v2 += (s.v1 - s.v2) * Math.min(1, dt / 0.004); // MCU debounce filter
      } else if (fam === "encoder") {
        if (useBenchStore.getState().rotating) s.phase += dt * 2 * Math.PI * 20; // 20 Hz quadrature
        const p = ((s.phase % (2 * Math.PI)) + 2 * Math.PI) % (2 * Math.PI);
        s.v1 = p < Math.PI ? 0.94 : 0.02;
        s.v2 = (p + Math.PI / 2) % (2 * Math.PI) < Math.PI ? 0.94 : 0.02;
      } else if (fam === "air") {
        // Capacitive proximity: CH1 = electrode sense level (charge-transfer
        // output rises as the fingertip nears the cover), CH2 = touch IC's
        // threshold comparator with hysteresis (asserts >0.62, releases <0.4).
        const targetV = inputRef.current.near ? 0.82 : 0.06;
        s.v1 += (targetV - s.v1) * Math.min(1, dt / 0.05);
        if (!s.touch && s.v1 > 0.62) s.touch = true;
        else if (s.touch && s.v1 < 0.4) s.touch = false;
        s.v2 = s.touch ? 0.94 : 0.02;
      } else {
        const target = 0.08 + 0.85 * (pres / 400);
        const amp = s.v2; // amplified channel carries the lag state
        const next = amp + (target - amp) * Math.min(1, dt / 0.03); // first-order response
        s.v2 = next;
        s.v1 = target * 0.06; // raw bridge: tens of mV on a 3.3 V scale
      }
      const b = buf.current;
      b.v1[b.head] = s.v1;
      b.v2[b.head] = s.v2;
      b.head = (b.head + 1) % WINDOW;
      b.count = Math.min(WINDOW, b.count + 1);
    };

    const draw = () => {
      const dpr = window.devicePixelRatio || 1;
      const w = canvas.clientWidth;
      const h = canvas.clientHeight;
      if (canvas.width !== Math.round(w * dpr) || canvas.height !== Math.round(h * dpr)) {
        canvas.width = Math.round(w * dpr);
        canvas.height = Math.round(h * dpr);
      }
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.fillStyle = "#0b1220";
      ctx.fillRect(0, 0, w, h);

      const mL = 40, mT = 24, mR = 10, mB = 20;
      const pw = w - mL - mR;
      const ph = h - mT - mB;
      const rows = 6, cols = 10;

      ctx.strokeStyle = "#1e3a5f";
      ctx.lineWidth = 1;
      for (let i = 0; i <= cols; i++) {
        const x = mL + (pw * i) / cols;
        ctx.beginPath();
        ctx.moveTo(x, mT);
        ctx.lineTo(x, mT + ph);
        ctx.stroke();
      }
      for (let i = 0; i <= rows; i++) {
        const y = mT + (ph * i) / rows;
        ctx.beginPath();
        ctx.moveTo(mL, y);
        ctx.lineTo(mL + pw, y);
        ctx.stroke();
      }
      ctx.strokeStyle = "#2d4a73";
      ctx.beginPath();
      ctx.moveTo(mL, mT + ph / 2);
      ctx.lineTo(mL + pw, mT + ph / 2);
      ctx.stroke();

      const b = buf.current;
      const trace = (arr: Float32Array, color: string) => {
        ctx.strokeStyle = color;
        ctx.lineWidth = 1.8;
        ctx.beginPath();
        for (let i = 0; i < b.count; i++) {
          const idx = (b.head - b.count + i + WINDOW * 2) % WINDOW;
          const x = mL + (pw * i) / (WINDOW - 1);
          const y = mT + ph - arr[idx] * ph;
          if (i === 0) ctx.moveTo(x, y);
          else ctx.lineTo(x, y);
        }
        ctx.stroke();
      };
      trace(b.v1, "#facc15");
      trace(b.v2, "#38bdf8");

      // Tact: dashed logic-low limit line for at-a-glance margin reading.
      if (inputRef.current.family === "tact") {
        const y = mT + ph - (LOGIC_LOW_LIMIT_V / VCC) * ph;
        ctx.save();
        ctx.setLineDash([5, 4]);
        ctx.strokeStyle = "#ef4444";
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(mL, y);
        ctx.lineTo(mL + pw, y);
        ctx.stroke();
        ctx.restore();
        ctx.fillStyle = "#ef4444";
        ctx.font = "10px system-ui, sans-serif";
        ctx.textAlign = "left";
        ctx.fillText("1.0 V limit", mL + 4, y - 4);
      }

      // Info bar + axis labels
      ctx.font = "11px system-ui, sans-serif";
      ctx.textAlign = "left";
      ctx.fillStyle = "#94a3b8";
      ctx.fillText("60 ms/div · 3.3 V full-scale", mL, 14);
      ctx.textAlign = "right";
      const s = sim.current;
      ctx.fillStyle = "#facc15";
      ctx.fillText(`CH1 ${(s.v1 * VCC).toFixed(2)} V`, mL + pw, 14);
      ctx.fillStyle = "#38bdf8";
      ctx.fillText(`CH2 ${(s.v2 * VCC).toFixed(2)} V`, mL + pw - 74, 14);
      ctx.fillStyle = "#8b99b5";
      ctx.textAlign = "center";
      for (let i = 0; i <= cols; i += 2) {
        ctx.fillText(`${((cols - i) * 60) / 10}ms`, mL + (pw * i) / cols, h - 6);
      }
      ctx.fillStyle = inputRef.current.running ? "#22c55e" : "#8b99b5";
      ctx.textAlign = "left";
      ctx.fillText(inputRef.current.running ? "● RUN" : "○ STOP", 6, 14);
    };

    const loop = () => {
      const now = performance.now();
      acc += Math.min(0.05, (now - last) / 1000); // clamp tab-switch jumps
      last = now;
      // STOP freezes acquisition like a bench scope: the last window stays
      // on screen (still redrawn — resize-safe) but time stops advancing.
      if (inputRef.current.running) {
        while (acc >= SAMPLE_DT) {
          acc -= SAMPLE_DT;
          step(SAMPLE_DT);
        }
      } else {
        acc = 0;
      }
      draw();
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  }, []);

  // Channel LEDs in the bezel — lit in the channel colour while acquiring,
  // dim when stopped; the CH1/CH2 labels carry the meaning, never colour alone.
  const led = (color: string, lit: boolean) => (
    <span
      aria-hidden
      style={{
        width: 8,
        height: 8,
        borderRadius: "50%",
        display: "inline-block",
        background: lit ? color : "var(--alps-border-strong)",
        boxShadow: lit ? `0 0 6px ${color}` : "none",
      }}
    />
  );

  return (
    <div style={{ border: "1px solid #334155", borderRadius: 8, padding: 8, background: "#0b1220", color: "#e2e8f0" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 6 }}>
        <span style={{ fontSize: 12, opacity: 0.7 }}>{t("bench.scopeTitle")}</span>
        <span style={{ display: "inline-flex", alignItems: "center", gap: 4, fontSize: 10.5, fontFamily: "monospace" }}>
          {led("#facc15", running)}
          <span style={{ color: "#facc15" }}>CH1</span>
        </span>
        <span style={{ display: "inline-flex", alignItems: "center", gap: 4, fontSize: 10.5, fontFamily: "monospace" }}>
          {led("#38bdf8", running)}
          <span style={{ color: "#38bdf8" }}>CH2</span>
        </span>
        <span style={{ marginLeft: "auto", fontSize: 10.5, fontFamily: "monospace", color: running ? "#22c55e" : "#8b99b5" }}>
          {running ? "● RUN" : "○ STOP"}
        </span>
      </div>
      <canvas ref={canvasRef} style={{ width: "100%", height: 200, display: "block", borderRadius: 6 }} />
      <div style={{ fontSize: 11, opacity: 0.6, marginTop: 4 }}>
        <span style={{ color: "#facc15" }}>■</span> CH1 ·{" "}
        <span style={{ color: "#38bdf8" }}>■</span> CH2 —{" "}
        {family === "tact"
          ? t("bench.scopeHintTact")
          : family === "encoder"
            ? t("bench.scopeHintEncoder")
            : family === "air"
              ? t("bench.scopeHintAir")
              : t("bench.scopeHintMems")}
      </div>
    </div>
  );
}

/* ------------------------------ circuit test ------------------------------ */

function CircuitTest({ spiceRun }: { spiceRun: SimulationRun | null }) {
  const { t } = useTranslation();
  const vouts = (spiceRun?.metrics ?? []).filter((m) => m.name.startsWith("v_out_rc_")).map((m) => m.value);
  const worst = vouts.length > 0 ? Math.max(...vouts) : null;
  const margin = spiceRun?.metrics.find((m) => m.name === "worst_case_logic_low_margin")?.value ?? null;
  const pass = worst !== null && worst < LOGIC_LOW_LIMIT_V;

  const pill = (ok: boolean | null) => ({
    color: ok === null ? "var(--alps-idle)" : ok ? "var(--alps-ok-alt)" : "var(--alps-violation)",
    fontWeight: 600 as const,
    textAlign: "right" as const,
  });

  return (
    <div style={{ border: "1px solid var(--alps-border-strong)", borderRadius: 8, padding: 10, fontSize: 12 }}>
      <div style={{ fontWeight: 600, marginBottom: 6 }}>{t("bench.circuitTest")}</div>
      <table style={{ width: "100%", borderCollapse: "collapse" }}>
        <tbody>
          <tr>
            <td style={{ opacity: 0.75, padding: "3px 0" }}>{t("bench.rowVcc")}</td>
            <td style={{ textAlign: "right" }}>3.30 V</td>
            <td style={pill(true)}>{t("bench.nominal")}</td>
          </tr>
          <tr>
            <td style={{ opacity: 0.75 }}>{t("bench.rowSwOpen")}</td>
            <td style={{ textAlign: "right" }}>3.30 V</td>
            <td style={pill(true)}>{t("bench.pass")}</td>
          </tr>
          <tr>
            <td style={{ opacity: 0.75 }}>{t("bench.rowSwPressed")}</td>
            <td style={{ textAlign: "right" }}>{worst !== null ? `${worst.toFixed(3)} V` : "—"}</td>
            <td style={pill(worst === null ? null : pass)}>
              {worst === null ? t("bench.na") : pass ? t("bench.pass") : t("bench.fail")}
            </td>
          </tr>
          <tr>
            <td style={{ opacity: 0.75 }}>{t("bench.rowMargin")}</td>
            <td style={{ textAlign: "right" }}>{margin !== null ? `${margin.toFixed(3)} V` : "—"}</td>
            <td />
          </tr>
        </tbody>
      </table>
      <div style={{ fontSize: 10, opacity: 0.55, marginTop: 6 }}>
        {spiceRun
          ? `${t("bench.spiceSource")} ${spiceRun.business_id} · ${spiceRun.tool_version ?? "—"} · ${t("bench.logicLowLimit")}`
          : t("bench.noSpice")}
      </div>
    </div>
  );
}

/* --------------------------------- panel --------------------------------- */

export function TestBench({ product, variantName, runs, components }: { product: Product | null; variantName?: string | null; runs: SimulationRun[]; components: ComponentDto[] }) {
  const { t } = useTranslation();
  const family = benchFamilyOf(product);
  const actuated = useTwinStore((s) => s.actuated);
  const setActuated = useTwinStore((s) => s.setActuated);
  const rotating = useBenchStore((s) => s.rotating);
  const setRotating = useBenchStore((s) => s.setRotating);
  const selectedComponentId = useTwinStore((s) => s.selectedComponentId);
  const [pressure, setPressure] = useState(200);
  // AirInput bench stimulus: a fingertip at the cover (see AirDut).
  const [near, setNear] = useState(false);
  // The electrode layout is a per-variant geometry (seed names carry
  // "Layout A/B"), so the benched puck matches the selected variant — the
  // same rule the air tab's field twin derives from its artifacts.
  const splitRing = /layout\s*b|split-ring/i.test(variantName ?? "");
  // Bench-scope RUN/STOP: STOP freezes the acquisition window (bezel LEDs dim).
  const [scopeRunning, setScopeRunning] = useState(true);
  // L187 sync, bench side: the DUT lights only when the selected component
  // IS the benched part; otherwise the chip says so instead of pretending.
  const selectedComponent = components.find((c) => c.id === selectedComponentId) ?? null;
  const dutMatched = !!selectedComponent && FAMILY_KIND[family].test(selectedComponent.name);

  // Switching product swaps the DUT — never carry a pressed/rotating state
  // from one physical part into the next.
  useEffect(() => {
    setActuated(false);
    setRotating(false);
    setNear(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [family]);

  const spiceRun = runs.find((r) => r.run_type === "spice_analysis" && r.status === "succeeded") ?? null;

  const hint =
    family === "tact"
      ? t("bench.hintTact")
      : family === "encoder"
        ? t("bench.hintEncoder")
        : family === "air"
          ? t("bench.hintAir")
          : t("bench.hintMems");

  return (
    <div style={{ height: "100%", display: "grid", gridTemplateColumns: "1fr 340px", gap: 12 }}>
      <div style={{ position: "relative", border: "1px solid #334155", borderRadius: 8, overflow: "hidden", background: "#0f172a", color: "#e2e8f0" }}>
        <Canvas dpr={[1, 2]} camera={{ position: [4, 34, 40], fov: 35 }} gl={{ antialias: true }}>
          <ViewerEnvironment />
          <ambientLight intensity={0.35} />
          <directionalLight position={[10, 24, 12]} intensity={1.3} />
          <directionalLight position={[-12, 10, -8]} intensity={0.3} />
          <Board family={family} pressure={pressure} near={near} splitRing={splitRing} dutMatched={dutMatched} />
          <OrbitControls makeDefault target={[0, 2, 0]} maxPolarAngle={Math.PI / 2.05} />
        </Canvas>
        <div
          style={{
            position: "absolute",
            top: 10,
            left: 10,
            background: "rgba(15, 23, 42, 0.88)",
            border: "1px solid #334155",
            borderRadius: 8,
            padding: 10,
            display: "flex",
            flexDirection: "column",
            gap: 8,
            fontSize: 12,
            maxWidth: 230,
          }}
        >
          <div style={{ opacity: 0.7 }}>{hint}</div>
          {/* equipment identity: which DUT is on the bench + the SPICE run
              the circuit-test verdicts are provenance-bound to */}
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center" }}>
            <HudChip color={accent.id}>
              {t("bench.equip.dut")} · {product?.name ?? family}
            </HudChip>
            <HudChip color={S.okAlt}>◈ SPICE · {spiceRun ? `${spiceRun.business_id} · ${spiceRun.tool_version ?? "—"}` : t("bench.noSpice")}</HudChip>
          </div>
          {selectedComponent &&
            (dutMatched ? (
              <HudChip color={accent.orange}>◆ {t("bench.dutMatched", { name: selectedComponent.name })}</HudChip>
            ) : (
              <HudChip color={S.idle}>{t("bench.dutWhole")}</HudChip>
            ))}
          <button
            onClick={() => setScopeRunning(!scopeRunning)}
            aria-pressed={scopeRunning}
            style={{
              padding: "5px 10px",
              borderRadius: 6,
              border: `1px solid ${scopeRunning ? border.base : accent.orange}`,
              background: scopeRunning ? bg.raise : "#7c2d12",
              color: scopeRunning ? "var(--alps-text)" : "white",
              cursor: "pointer",
              fontSize: 12,
              fontFamily: "monospace",
              textAlign: "left",
            }}
          >
            {scopeRunning ? `● ${t("bench.equip.stop")}` : `▶ ${t("bench.equip.run")}`}
          </button>
          {family === "encoder" && (
            <button
              onClick={() => setRotating(!rotating)}
              style={{
                padding: "5px 10px",
                borderRadius: 6,
                border: "1px solid",
                borderColor: rotating ? "#f97316" : "var(--alps-border-strong)",
                background: rotating ? "#7c2d12" : "var(--alps-bg-raise)",
                color: rotating ? "white" : "var(--alps-text)",
                cursor: "pointer",
              }}
            >
              {rotating ? t("bench.rotating") : t("bench.rotate")}
            </button>
          )}
          {family === "mems" && (
            <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
              <span style={{ opacity: 0.8 }}>
                {t("bench.pressure")}: {pressure} kPa
              </span>
              <input
                type="range"
                min={40}
                max={400}
                step={10}
                value={pressure}
                onChange={(e) => setPressure(Number(e.target.value))}
                style={{ accentColor: "#f97316" }}
              />
            </label>
          )}
          {family === "air" && (
            <button
              onClick={() => setNear(!near)}
              style={{
                padding: "5px 10px",
                borderRadius: 6,
                border: "1px solid",
                borderColor: near ? "#f97316" : "var(--alps-border-strong)",
                background: near ? "#7c2d12" : "var(--alps-bg-raise)",
                color: near ? "white" : "var(--alps-text)",
                cursor: "pointer",
              }}
            >
              {near ? t("bench.fingerAway") : t("bench.fingerNear")}
            </button>
          )}
          {family === "tact" && (
            <button
              onClick={() => setActuated(!actuated)}
              style={{
                padding: "5px 10px",
                borderRadius: 6,
                border: "1px solid",
                borderColor: actuated ? "#f97316" : "var(--alps-border-strong)",
                background: actuated ? "#7c2d12" : "var(--alps-bg-raise)",
                color: actuated ? "white" : "var(--alps-text)",
                cursor: "pointer",
              }}
            >
              {actuated ? t("twin.actuated") : t("twin.actuate")}
            </button>
          )}
        </div>
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 12, minHeight: 0, overflowY: "auto" }}>
        <Scope family={family} pressure={pressure} near={near} running={scopeRunning} />
        <FSOverlay mechRun={runs.find((r) => r.run_type === "mech_model") ?? null} family={family} pressure={pressure} near={near} />
        <CircuitTest spiceRun={spiceRun} />
      </div>
    </div>
  );
}
