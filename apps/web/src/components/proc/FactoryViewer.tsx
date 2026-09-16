import { useMemo, useRef } from "react";
import { Canvas, useFrame } from "@react-three/fiber";
import { ContactShadows, OrbitControls } from "@react-three/drei";
import type { FactoryLotDot, FactoryStation, StationStatus } from "./factoryScene";
import * as THREE from "three";
import { useTranslation } from "react-i18next";
import { buildFactoryScene, stationX } from "./factoryScene";
import { canvasTextTexture } from "../../ui/canvasText";
import { HudChip, HudPanel, StatusBadge, btn, type KitStatus } from "../../ui/kit";
import { rawAccent, rawStatus, status as S } from "../../ui/tokens";
import { ViewerEnvironment } from "../ThreeViewer";

// Production-line 3D twin — photoreal rendering pass: real machine
// silhouettes (press frame, injection molder, robot assembly cell), andon
// signal towers for the chart-driven health status, a concrete floor with
// safety lane markings under industrial ceiling fixtures, and totes (not
// marbles) riding the conveyor. All geometry is procedural; every status
// still comes from factoryScene.ts over API data — the render invents
// nothing about the process.

export function stationToKitStatus(s: StationStatus): KitStatus {
  return s === "in_control" ? "ok" : s === "rule_hit" ? "attention" : s === "excluded" ? "violation" : "idle";
}

const DISP_COLOR: Record<string, string> = {
  ok: rawStatus.okAlt,
  quarantine: rawStatus.attention,
  reject: rawStatus.violation,
};

// Shared machine materials — one idiom per surface type keeps the line
// reading as one shop floor instead of a box pile.
const MACHINE = { body: "#2e3542", dark: "#20242e", steel: "#787f8c", accent: "#3d4657" };

/* ----------------------------- andon tower ------------------------------ */

// Red over amber over green — the standard signal-stack order. Lit segment
// follows the station's chart status; attention states blink like a real
// andon, in-control holds a steady green, idle stays dark.
function Lamp({ color, lit, blink, position }: { color: string; lit: boolean; blink: boolean; position: [number, number, number] }) {
  const mat = useRef<THREE.MeshStandardMaterial>(null);
  useFrame(({ clock }) => {
    if (!mat.current) return;
    mat.current.emissiveIntensity = lit ? (blink ? 0.5 + 0.7 * Math.abs(Math.sin(clock.elapsedTime * 3.2)) : 1.5) : 0.03;
  });
  return (
    <mesh position={position}>
      <cylinderGeometry args={[0.115, 0.115, 0.24, 16]} />
      <meshStandardMaterial ref={mat} color={lit ? color : "#222734"} emissive={color} emissiveIntensity={lit ? 1.2 : 0.03} roughness={0.35} />
    </mesh>
  );
}

function StackLight({ status, position }: { status: StationStatus; position: [number, number, number] }) {
  const [x, y, z] = position;
  return (
    <group>
      <mesh position={[x, y + 0.24, z]}>
        <cylinderGeometry args={[0.035, 0.035, 0.48, 10]} />
        <meshStandardMaterial color="#3a4150" metalness={0.7} roughness={0.4} />
      </mesh>
      <Lamp color={rawStatus.violation} lit={status === "excluded"} blink position={[x, y + 0.6, z]} />
      <Lamp color={rawStatus.attention} lit={status === "rule_hit"} blink position={[x, y + 0.36, z]} />
      <Lamp color={rawStatus.okAlt} lit={status === "in_control"} blink={false} position={[x, y + 0.12, z]} />
    </group>
  );
}

/* ------------------------------ nameplate ------------------------------- */

function Nameplate({ title, sub, position, rotation }: { title: string; sub: string; position: [number, number, number]; rotation?: [number, number, number] }) {
  const titleTex = useMemo(() => canvasTextTexture(title, "#dbe3ee", { width: 512, height: 96, font: "bold 46px system-ui, sans-serif" }), [title]);
  const subTex = useMemo(() => canvasTextTexture(sub, "#7dd3fc", { width: 512, height: 64, font: "bold 34px ui-monospace, monospace" }), [sub]);
  return (
    <group position={position} rotation={rotation}>
      <mesh>
        <boxGeometry args={[1.72, 0.54, 0.05]} />
        <meshStandardMaterial color="#0d1117" roughness={0.45} metalness={0.4} />
      </mesh>
      <mesh position={[0, 0.09, 0.031]}>
        <planeGeometry args={[1.58, 0.28]} />
        <meshBasicMaterial map={titleTex} transparent />
      </mesh>
      <mesh position={[0, -0.13, 0.031]}>
        <planeGeometry args={[1.58, 0.185]} />
        <meshBasicMaterial map={subTex} transparent />
      </mesh>
    </group>
  );
}

/* ------------------------------- machines ------------------------------- */

// Mechanical press: bolster bed, uprights, crown with motor, ram over die.
function PressMachine() {
  return (
    <group>
      <mesh position={[0, 0.28, 0]}>
        <boxGeometry args={[2.8, 0.56, 1.9]} />
        <meshStandardMaterial color={MACHINE.body} metalness={0.55} roughness={0.5} />
      </mesh>
      <mesh position={[0, 0.72, 0]}>
        <boxGeometry args={[1.5, 0.36, 1.15]} />
        <meshStandardMaterial color={MACHINE.dark} metalness={0.5} roughness={0.55} />
      </mesh>
      {[-1.05, 1.05].map((x) => (
        <mesh key={x} position={[x, 1.56, 0]}>
          <boxGeometry args={[0.42, 2.0, 0.62]} />
          <meshStandardMaterial color={MACHINE.body} metalness={0.55} roughness={0.5} />
        </mesh>
      ))}
      <mesh position={[0, 2.84, 0]}>
        <boxGeometry args={[2.95, 0.56, 1.3]} />
        <meshStandardMaterial color={MACHINE.body} metalness={0.55} roughness={0.5} />
      </mesh>
      {/* motor + gearbox lump on the crown */}
      <mesh position={[0.85, 3.3, 0.25]} rotation={[0, 0, Math.PI / 2]}>
        <cylinderGeometry args={[0.22, 0.22, 0.55, 20]} />
        <meshStandardMaterial color={MACHINE.accent} metalness={0.7} roughness={0.35} />
      </mesh>
      <mesh position={[-0.5, 3.24, 0.2]}>
        <boxGeometry args={[0.7, 0.3, 0.6]} />
        <meshStandardMaterial color={MACHINE.accent} metalness={0.6} roughness={0.4} />
      </mesh>
      {/* ram hanging between the uprights */}
      <mesh position={[0, 1.95, 0]}>
        <boxGeometry args={[1.55, 0.6, 1.05]} />
        <meshStandardMaterial color={MACHINE.dark} metalness={0.6} roughness={0.42} />
      </mesh>
      <mesh position={[0, 1.5, 0]}>
        <boxGeometry args={[1.15, 0.34, 0.95]} />
        <meshStandardMaterial color="#565f70" metalness={0.75} roughness={0.3} />
      </mesh>
    </group>
  );
}

// Injection molder: clamp unit with guarded platen, injection barrel +
// hopper, control cabinet on the skid.
function MoldingMachine() {
  return (
    <group>
      <mesh position={[0, 0.16, 0]}>
        <boxGeometry args={[3.5, 0.32, 1.7]} />
        <meshStandardMaterial color={MACHINE.dark} metalness={0.4} roughness={0.6} />
      </mesh>
      <mesh position={[-0.85, 1.0, 0]}>
        <boxGeometry args={[1.55, 1.36, 1.4]} />
        <meshStandardMaterial color={MACHINE.body} metalness={0.55} roughness={0.5} />
      </mesh>
      {/* safety guard window over the mold area */}
      <mesh position={[-0.85, 1.05, 0.71]}>
        <boxGeometry args={[1.15, 0.85, 0.03]} />
        <meshStandardMaterial color="#8ab6d6" transparent opacity={0.22} metalness={0.3} roughness={0.1} />
      </mesh>
      {/* tie bars + injection barrel */}
      {[0.95, 0.55].map((y) =>
        [-0.38, 0.38].map((z) => (
          <mesh key={`${y}${z}`} position={[0.35, y, z]} rotation={[0, 0, Math.PI / 2]}>
            <cylinderGeometry args={[0.055, 0.055, 1.6, 12]} />
            <meshStandardMaterial color={MACHINE.steel} metalness={0.85} roughness={0.28} />
          </mesh>
        ))
      )}
      <mesh position={[0.85, 0.85, 0]} rotation={[0, 0, Math.PI / 2]}>
        <cylinderGeometry args={[0.27, 0.27, 1.5, 20]} />
        <meshStandardMaterial color={MACHINE.accent} metalness={0.7} roughness={0.35} />
      </mesh>
      <mesh position={[1.62, 0.85, 0]} rotation={[0, 0, -Math.PI / 2]}>
        <cylinderGeometry args={[0.09, 0.2, 0.25, 16]} />
        <meshStandardMaterial color={MACHINE.steel} metalness={0.8} roughness={0.3} />
      </mesh>
      {/* hopper feeding the barrel */}
      <mesh position={[1.05, 1.5, 0]}>
        <cylinderGeometry args={[0.4, 0.14, 0.62, 20]} />
        <meshStandardMaterial color={MACHINE.body} metalness={0.6} roughness={0.4} />
      </mesh>
      {/* operator cabinet */}
      <mesh position={[-1.85, 0.9, 0.3]}>
        <boxGeometry args={[0.5, 1.16, 0.68]} />
        <meshStandardMaterial color={MACHINE.dark} metalness={0.5} roughness={0.5} />
      </mesh>
      <mesh position={[-1.585, 1.15, 0.3]} rotation={[0, Math.PI / 2, 0]}>
        <planeGeometry args={[0.4, 0.3]} />
        <meshStandardMaterial color="#0e1a2b" emissive="#1d3557" emissiveIntensity={0.5} />
      </mesh>
    </group>
  );
}

// Assembly cell: workbench with parts bins and a small articulated robot.
function AssemblyCell() {
  return (
    <group>
      <mesh position={[0, 0.92, 0]}>
        <boxGeometry args={[2.9, 0.12, 1.8]} />
        <meshStandardMaterial color="#3a4150" metalness={0.5} roughness={0.45} />
      </mesh>
      <mesh position={[0, 0.6, 0.92]}>
        <boxGeometry args={[2.9, 0.56, 0.05]} />
        <meshStandardMaterial color={MACHINE.dark} metalness={0.4} roughness={0.6} />
      </mesh>
      {[
        [-1.32, -0.78],
        [1.32, -0.78],
        [-1.32, 0.78],
        [1.32, 0.78],
      ].map(([x, z]) => (
        <mesh key={`${x}${z}`} position={[x, 0.44, z]}>
          <boxGeometry args={[0.12, 0.88, 0.12]} />
          <meshStandardMaterial color={MACHINE.steel} metalness={0.75} roughness={0.35} />
        </mesh>
      ))}
      {/* parts bins on the bench */}
      {[-0.95, -0.5, -0.05].map((x, i) => (
        <mesh key={x} position={[x, 1.06, -0.45 - (i % 2) * 0.3]}>
          <boxGeometry args={[0.36, 0.16, 0.28]} />
          <meshStandardMaterial color={i === 1 ? "#4a5364" : MACHINE.body} metalness={0.3} roughness={0.6} />
        </mesh>
      ))}
      {/* articulated robot: base, shoulder, two links, wrist */}
      <mesh position={[0.75, 1.1, 0.25]}>
        <cylinderGeometry args={[0.28, 0.32, 0.24, 20]} />
        <meshStandardMaterial color={MACHINE.body} metalness={0.6} roughness={0.4} />
      </mesh>
      <mesh position={[0.75, 1.36, 0.25]}>
        <cylinderGeometry args={[0.17, 0.2, 0.34, 16]} />
        <meshStandardMaterial color={rawAccent.primary} metalness={0.5} roughness={0.45} />
      </mesh>
      <mesh position={[0.62, 1.72, 0.2]} rotation={[0, 0, 0.5]}>
        <boxGeometry args={[0.17, 0.95, 0.17]} />
        <meshStandardMaterial color="#e8eaee" metalness={0.4} roughness={0.4} />
      </mesh>
      <mesh position={[0.38, 1.9, 0.12]} rotation={[0, 0, -0.7]}>
        <boxGeometry args={[0.14, 0.72, 0.14]} />
        <meshStandardMaterial color="#e8eaee" metalness={0.4} roughness={0.4} />
      </mesh>
      <mesh position={[0.19, 1.72, 0.05]}>
        <cylinderGeometry args={[0.06, 0.06, 0.18, 12]} />
        <meshStandardMaterial color={MACHINE.dark} metalness={0.7} roughness={0.35} />
      </mesh>
    </group>
  );
}

// Fallback for any equipment id without a dedicated silhouette: an
// instrument cabinet — still honest, still labeled.
function GenericMachine() {
  return (
    <group>
      <mesh position={[0, 0.9, 0]}>
        <boxGeometry args={[2.4, 1.8, 1.5]} />
        <meshStandardMaterial color={MACHINE.body} metalness={0.55} roughness={0.5} />
      </mesh>
      <mesh position={[0, 1.9, 0]}>
        <boxGeometry args={[2.5, 0.16, 1.6]} />
        <meshStandardMaterial color={MACHINE.dark} metalness={0.5} roughness={0.55} />
      </mesh>
      <mesh position={[0, 1.1, 0.76]}>
        <planeGeometry args={[0.9, 0.65]} />
        <meshStandardMaterial color="#0e1a2b" emissive="#1d3557" emissiveIntensity={0.45} />
      </mesh>
    </group>
  );
}

function machineFor(equipment: string | null) {
  const eq = (equipment ?? "").toLowerCase();
  if (/press/.test(eq)) return <PressMachine />;
  if (/mold/.test(eq)) return <MoldingMachine />;
  if (/asm|cell/.test(eq)) return <AssemblyCell />;
  return <GenericMachine />;
}

// Machine anchor points for tower + plate, per silhouette.
function fixturePoints(equipment: string | null): { light: [number, number, number]; plate: [number, number, number] } {
  const eq = (equipment ?? "").toLowerCase();
  if (/press/.test(eq)) return { light: [-1.1, 3.12, -0.4], plate: [0, 0.32, 0.98] };
  if (/mold/.test(eq)) return { light: [-0.85, 1.68, -0.55], plate: [-0.85, 0.45, 0.86] };
  if (/asm|cell/.test(eq)) return { light: [-1.36, 1.0, -0.82], plate: [0, 0.62, 0.97] };
  return { light: [-0.95, 1.98, -0.55], plate: [0, 0.5, 0.78] };
}

function Station({
  st,
  x,
  selected,
  onSelect,
}: {
  st: FactoryStation;
  x: number;
  selected: boolean;
  onSelect: (key: string) => void;
}) {
  const fixtures = fixturePoints(st.equipment);
  return (
    <group
      position={[x, 0, 0]}
      onClick={(e) => {
        e.stopPropagation();
        onSelect(st.key);
      }}
      onPointerOver={() => (document.body.style.cursor = "pointer")}
      onPointerOut={() => (document.body.style.cursor = "auto")}
    >
      {machineFor(st.equipment)}
      <StackLight status={st.status} position={fixtures.light} />
      <Nameplate title={st.name} sub={st.equipment ?? st.key} position={fixtures.plate} />
      {selected && (
        <mesh position={[0, 0.02, 0]} rotation={[-Math.PI / 2, 0, 0]}>
          <ringGeometry args={[2.3, 2.55, 48]} />
          <meshBasicMaterial color={rawAccent.primary} transparent opacity={0.85} />
        </mesh>
      )}
    </group>
  );
}

/* ------------------------------- conveyor ------------------------------- */

function Conveyor({ span }: { span: number }) {
  const length = span + 6;
  const legs = Math.max(3, Math.round(length / 4));
  return (
    <group position={[0, 0, 2.9]}>
      <mesh position={[0, 0.44, 0]}>
        <boxGeometry args={[length, 0.16, 0.95]} />
        <meshStandardMaterial color="#181c24" roughness={0.85} metalness={0.15} />
      </mesh>
      {[-0.55, 0.55].map((z) => (
        <mesh key={z} position={[0, 0.5, z]}>
          <boxGeometry args={[length, 0.09, 0.06]} />
          <meshStandardMaterial color={MACHINE.steel} metalness={0.8} roughness={0.3} />
        </mesh>
      ))}
      {[-length / 2 + 0.4, length / 2 - 0.4].map((x) => (
        <mesh key={x} position={[x, 0.44, 0]} rotation={[Math.PI / 2, 0, 0]}>
          <cylinderGeometry args={[0.14, 0.14, 1.0, 18]} />
          <meshStandardMaterial color={MACHINE.steel} metalness={0.8} roughness={0.3} />
        </mesh>
      ))}
      {Array.from({ length: legs }, (_, i) => -length / 2 + 1 + (i * (length - 2)) / (legs - 1)).map((x) => (
        <mesh key={x} position={[x, 0.2, 0]}>
          <boxGeometry args={[0.1, 0.4, 0.85]} />
          <meshStandardMaterial color={MACHINE.dark} metalness={0.6} roughness={0.45} />
        </mesh>
      ))}
    </group>
  );
}

// Lot totes in production order — a gray bin whose lid stripe carries the
// disposition colour. The conveyor is a timeline, not a station claim.
function Totes({ lots, span }: { lots: FactoryLotDot[]; span: number }) {
  const group = useRef<THREE.Group>(null);
  const SLOT = 1.05;
  useFrame((_, dt) => {
    if (!group.current) return;
    group.current.position.x -= dt * 0.3;
    if (group.current.position.x < -SLOT) group.current.position.x += SLOT;
  });
  return (
    <group ref={group}>
      {lots.map((lot, i) => {
        const color = DISP_COLOR[lot.disposition];
        return (
          <group key={lot.businessId} position={[-span / 2 + 2 + i * SLOT, 0, 2.9]}>
            <mesh position={[0, 0.72, 0]}>
              <boxGeometry args={[0.72, 0.36, 0.52]} />
              <meshStandardMaterial color="#363d4b" roughness={0.65} metalness={0.1} />
            </mesh>
            <mesh position={[0, 0.92, 0]}>
              <boxGeometry args={[0.74, 0.05, 0.54]} />
              <meshStandardMaterial color={color} emissive={color} emissiveIntensity={0.4} roughness={0.5} />
            </mesh>
          </group>
        );
      })}
    </group>
  );
}

/* --------------------------------- scene -------------------------------- */

function FactoryFloor() {
  return (
    <group>
      {/* concrete floor */}
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.01, 0]}>
        <planeGeometry args={[84, 46]} />
        <meshStandardMaterial color="#171c26" roughness={0.92} metalness={0.08} />
      </mesh>
      {/* safety lane markings flanking the conveyor walkway */}
      {[1.95, 3.9].map((z) => (
        <mesh key={z} rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.005, z]}>
          <planeGeometry args={[72, 0.13]} />
          <meshStandardMaterial color="#8a6d1d" roughness={0.8} />
        </mesh>
      ))}
      {/* ceiling light fixtures */}
      {[-6.5, 0, 6.5].map((x) => (
        <mesh key={x} position={[x, 7.4, 1]}>
          <boxGeometry args={[3.4, 0.1, 0.55]} />
          <meshStandardMaterial color="#10131a" emissive="#cfd8e3" emissiveIntensity={0.85} />
        </mesh>
      ))}
    </group>
  );
}

export function FactoryViewer({
  stations,
  lots,
  selectedKey,
  onSelect,
  onJumpDoe,
}: {
  stations: FactoryStation[];
  lots: Parameters<typeof buildFactoryScene>[1];
  selectedKey: string | null;
  onSelect: (key: string | null) => void;
  onJumpDoe: () => void;
}) {
  const { t } = useTranslation();
  const scene = useMemo(() => buildFactoryScene(stations, lots), [stations, lots]);
  const span = scene.stations.length * scene.spacing;
  const counts = {
    ok: lots.filter((l) => l.disposition === "ok").length,
    quarantine: lots.filter((l) => l.disposition === "quarantine").length,
    reject: lots.filter((l) => l.disposition === "reject").length,
  };
  const legendRows: { s: StationStatus; label: string }[] = [
    { s: "in_control", label: t("proc.mon.legend.inControl") },
    { s: "rule_hit", label: t("proc.mon.legend.violation") },
    { s: "excluded", label: t("proc.mon.legend.excluded") },
    { s: "idle", label: t("factory.noParams") },
  ];

  return (
    <div style={{ position: "relative", width: "100%", height: "100%" }}>
      <Canvas
        dpr={[1, 2]}
        camera={{ position: [0, 11.5, 17.5], fov: 40 }}
        onPointerMissed={() => onSelect(null)}
        gl={{ antialias: true }}
        style={{ background: "#020617", borderRadius: 8 }}
      >
        <fog attach="fog" args={["#020617", 30, 85]} />
        <ViewerEnvironment />
        <ambientLight intensity={0.25} />
        <directionalLight position={[6, 12, 6]} intensity={1.15} />
        <directionalLight position={[-8, 6, -6]} intensity={0.3} />
        <FactoryFloor />
        {scene.stations.map((st, i) => (
          <Station key={st.key} st={st} x={stationX(i, scene.stations.length, scene.spacing)} selected={st.key === selectedKey} onSelect={onSelect} />
        ))}
        <Conveyor span={span} />
        <Totes lots={scene.lots} span={span + 4} />
        <ContactShadows position={[0, 0.01, 0]} scale={38} blur={2.4} opacity={0.5} far={5} resolution={512} />
        <OrbitControls target={[0, 1.2, 0]} maxPolarAngle={Math.PI / 2.08} minDistance={7} maxDistance={42} makeDefault />
      </Canvas>

      {/* status legend — icon + text together, never colour alone */}
      <HudPanel corner="top-left" width={190}>
        <div style={{ fontSize: 11, fontWeight: 600, marginBottom: 6 }}>{t("factory.legend")}</div>
        <div style={{ display: "flex", flexDirection: "column", gap: 4, alignItems: "flex-start" }}>
          {legendRows.map(({ s, label }) => (
            <StatusBadge key={s} status={stationToKitStatus(s)} label={label} />
          ))}
        </div>
      </HudPanel>

      {/* lot disposition summary over the conveyor */}
      <HudPanel corner="top-right">
        <div style={{ fontSize: 11, fontWeight: 600, marginBottom: 6 }}>{t("factory.lots")}</div>
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap", maxWidth: 240 }}>
          <HudChip color={S.okAlt}>● ok {counts.ok}</HudChip>
          <HudChip color={S.attention}>▲ quarantine {counts.quarantine}</HudChip>
          <HudChip color={S.violation}>✕ reject {counts.reject}</HudChip>
        </div>
      </HudPanel>

      <div style={{ position: "absolute", bottom: 10, left: 10, display: "flex", gap: 8, alignItems: "center", zIndex: 5 }}>
        <button style={btn(true, S.info)} onClick={onJumpDoe}>
          {t("factory.doeJump")}
        </button>
        <HudChip color={S.idle}>{t("factory.clickHint")}</HudChip>
      </div>
    </div>
  );
}
