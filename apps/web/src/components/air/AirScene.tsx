import { Canvas } from "@react-three/fiber";
import { OrbitControls } from "@react-three/drei";
import { useMemo } from "react";
import type { VolumePayload, FingerPose, AirState } from "../../lib/air";
import { AIR_STATE_COLOR, volumeIndex } from "../../lib/air";
import { AirFinger } from "./AirFinger";
import { AirTrajectoryLine } from "./AirTrajectoryLine";

// Geometry mirrors apps/workers/mech-model/field_model.py's disclosed
// constants (HOUSE 34×28×6.5, PCB 30×24×1.6 at z 1.2–2.8, electrode on top,
// cover 30.6×27.6×1.0, ASIC paddle 5×5 at (−9,4)). Worker (x, y, z-up) maps
// to three.js (x, z_up, −y). The scene is a VISUALIZATION of the idealized
// model the solver discretizes — three.js never computes field physics
// (지시서: Three.js field computation 금지).
const HOUSE_W = 34;
const HOUSE_D = 28;
const HOUSE_TOP = 6.5;
const PCB_TOP = 2.8;
const COVER_T = 1.0;
const PAD_R_A = Math.sqrt(100 / Math.PI); // solid 100 mm² pad
const RING_OUTER_R = 8.5; // LAYOUT_B_OUTER_R_MM
const RING_INNER_R = Math.sqrt(RING_OUTER_R ** 2 - 160 / Math.PI); // 160 mm² annulus
const ELEC_X = 5;

function Electrode({ splitRing, state }: { splitRing: boolean; state: AirState | null }) {
  // Board response display: the live ASIC judgment (computed by the worker
  // surrogate + signal chain in the studio) tints the electrodes — three.js
  // only renders the color, it computes no field (지시서).
  const glow = state === "NEAR" || state === "TOUCH" ? AIR_STATE_COLOR[state] : null;
  const intensity = state === "TOUCH" ? 0.95 : 0.45;
  if (!splitRing) {
    return (
      <mesh position={[ELEC_X, PCB_TOP + 0.04, 0]} rotation={[-Math.PI / 2, 0, 0]}>
        <circleGeometry args={[PAD_R_A, 48]} />
        <meshStandardMaterial
          color="#facc15"
          emissive={glow ?? "#000000"}
          emissiveIntensity={glow ? intensity : 0}
          metalness={0.8}
          roughness={0.3}
        />
      </mesh>
    );
  }
  // Layout B: half-ring split at y = 0 (E1 y ≥ 0 → z_three ≤ 0).
  const half = (flip: boolean, key: string) => (
    <mesh
      key={key}
      position={[0, PCB_TOP + 0.04, flip ? 0.05 : -0.05]}
      rotation={[-Math.PI / 2, 0, flip ? Math.PI : 0]}
    >
      <ringGeometry args={[RING_INNER_R, RING_OUTER_R, 48, 1, 0, Math.PI]} />
      <meshStandardMaterial
        color={flip ? "#fbbf24" : "#f59e0b"}
        emissive={glow ?? "#000000"}
        emissiveIntensity={glow ? intensity : 0}
        metalness={0.8}
        roughness={0.3}
      />
    </mesh>
  );
  return [half(false, "e2"), half(true, "e1")];
}

/** Cover-surface halo under the fingertip — the "board lights up" cue for
 * NEAR/TOUCH. Rendered ONLY when the live signal chain has a judgment; an
 * OOD pose shows no halo and no state color (예측 범위 밖은 정상 표시 금지). */
function TouchHalo({ pose, state }: { pose: FingerPose; state: AirState | null }) {
  if (state !== "NEAR" && state !== "TOUCH") return null;
  return (
    <mesh position={[pose.x_mm, HOUSE_TOP + 0.03, -pose.y_mm]} rotation={[-Math.PI / 2, 0, 0]}>
      <circleGeometry args={[7.5, 40]} />
      <meshStandardMaterial
        color={AIR_STATE_COLOR[state]}
        transparent
        opacity={state === "TOUCH" ? 0.5 : 0.26}
        depthWrite={false}
      />
    </mesh>
  );
}

function SensorStack({
  splitRing,
  hasGroundPlate,
  liveState,
}: {
  splitRing: boolean;
  hasGroundPlate: boolean;
  liveState: AirState | null;
}) {
  return (
    <group>
      {/* housing shell (translucent so the stack reads as an X-ray view) */}
      <mesh position={[0, HOUSE_TOP / 2, 0]}>
        <boxGeometry args={[HOUSE_W, HOUSE_TOP, HOUSE_D]} />
        <meshStandardMaterial color="#334155" transparent opacity={0.12} depthWrite={false} />
      </mesh>
      {/* PCB */}
      <mesh position={[0, 1.2 + 0.8, 0]}>
        <boxGeometry args={[30, 1.6, 24]} />
        <meshStandardMaterial color="#14532d" roughness={0.7} />
      </mesh>
      <Electrode splitRing={splitRing} state={liveState} />
      {/* ASIC QFN paddle (grounded shield mass) */}
      <mesh position={[-9, PCB_TOP + 0.04, -4]}>
        <boxGeometry args={[5, 0.08, 5]} />
        <meshStandardMaterial color="#94a3b8" metalness={0.9} roughness={0.2} />
      </mesh>
      {/* cover glass (touch surface) */}
      <mesh position={[0, HOUSE_TOP - COVER_T / 2, 0]}>
        <boxGeometry args={[30.6, COVER_T, 27.6]} />
        <meshStandardMaterial color="#7dd3fc" transparent opacity={0.22} depthWrite={false} />
      </mesh>
      {/* variant-B external grounded plate (§11.2 금속/접지) */}
      {hasGroundPlate && (
        <mesh position={[0, 12.5, 0]}>
          <boxGeometry args={[24, 0.3, 20]} />
          <meshStandardMaterial color="#475569" metalness={0.9} roughness={0.35} />
        </mesh>
      )}
    </group>
  );
}

/** 감지영역/Dead Zone point cloud over the surrogate-tier volume grid:
 * orange = TOUCH band, blue = NEAR band, dim = in-envelope DEAD ZONE. */
function AirVolume({ volume, visible }: { volume: VolumePayload | null; visible: boolean }) {
  const { positions, colors } = useMemo(() => {
    const positions: number[] = [];
    const colors: number[] = [];
    if (volume) {
      const { x_mm: xs, y_mm: ys, gap_mm: gaps } = volume.axes;
      for (let gi = 0; gi < gaps.length; gi++) {
        for (let yi = 0; yi < ys.length; yi++) {
          for (let xi = 0; xi < xs.length; xi++) {
            const i = volumeIndex(volume, gi, yi, xi);
            if (volume.detect_touch[i]) colors.push(0.98, 0.45, 0.1);
            else if (volume.detect_near[i]) colors.push(0.22, 0.74, 0.98);
            else colors.push(0.35, 0.25, 0.28); // dead zone (dim)
            positions.push(xs[xi], HOUSE_TOP + gaps[gi], -ys[yi]);
          }
        }
      }
    }
    return { positions: new Float32Array(positions), colors: new Float32Array(colors) };
  }, [volume]);

  if (!volume || !visible) return null;
  return (
    <points>
      <bufferGeometry>
        <bufferAttribute attach="attributes-position" args={[positions, 3]} />
        <bufferAttribute attach="attributes-color" args={[colors, 3]} />
      </bufferGeometry>
      <pointsMaterial size={0.9} vertexColors transparent opacity={0.55} sizeAttenuation />
    </points>
  );
}

export function AirScene(props: {
  pose: FingerPose;
  ood: boolean;
  splitRing: boolean;
  hasGroundPlate: boolean;
  liveState: AirState | null;
  volume: VolumePayload | null;
  showVolume: boolean;
  trajectory: { x_mm: number; y_mm: number; gap_mm: number }[] | null;
  showTrajectory: boolean;
}) {
  const { showVolume, showTrajectory, volume, trajectory } = props;
  return (
    <Canvas camera={{ position: [38, 30, 42], fov: 40 }} style={{ width: "100%", height: "100%" }}>
      <color attach="background" args={["#0b1220"]} />
      <ambientLight intensity={0.7} />
      <directionalLight position={[25, 40, 20]} intensity={1.1} />
      <SensorStack splitRing={props.splitRing} hasGroundPlate={props.hasGroundPlate} liveState={props.liveState} />
      <AirFinger pose={props.pose} ood={props.ood} surfaceZ={HOUSE_TOP} />
      <TouchHalo pose={props.pose} state={props.liveState} />
      <AirVolume volume={volume} visible={showVolume} />
      {showTrajectory && trajectory && <AirTrajectoryLine points={trajectory} surfaceZ={HOUSE_TOP} />}
      <OrbitControls target={[0, 8, 0]} />
    </Canvas>
  );
}
