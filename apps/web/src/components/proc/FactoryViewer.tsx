import { useMemo, useRef } from "react";
import { Canvas, useFrame } from "@react-three/fiber";
import { ContactShadows, OrbitControls } from "@react-three/drei";
import * as THREE from "three";
import { useTranslation } from "react-i18next";
import type { LotCard } from "../../lib/api";
import type { FactoryLotDot, FactoryStation, StationStatus } from "./factoryScene";
import { buildFactoryScene, stationX } from "./factoryScene";
import { canvasTextTexture } from "../../ui/canvasText";
import { HudChip, HudPanel, StatusBadge, btn, type KitStatus } from "../../ui/kit";
import { accent, status as S } from "../../ui/tokens";

// Production-line 3D twin: stations on a floor in seq order (real process
// operations), health stripes lit from real control-chart state, and a
// conveyor of lot dots in production order colored by disposition. Same
// idiom as the rest of the twin's canvases: DOM overlays for HUD, useFrame +
// refs for animation, and three.js renders only — every status was computed
// in factoryScene.ts from API data before it got here.

const STATUS_3D: Record<StationStatus, string> = {
  in_control: S.okAlt,
  rule_hit: S.attention,
  excluded: S.violation,
  idle: S.idle,
};

export function stationToKitStatus(s: StationStatus): KitStatus {
  return s === "in_control" ? "ok" : s === "rule_hit" ? "attention" : s === "excluded" ? "violation" : "idle";
}

const DISPOSITION_3D: Record<FactoryLotDot["disposition"], string> = {
  ok: S.okAlt,
  quarantine: S.attention,
  reject: S.violation,
};

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
  const stripe = useRef<THREE.MeshStandardMaterial>(null);
  const pulse = st.status === "rule_hit" || st.status === "excluded";
  const color = STATUS_3D[st.status];
  // Station signage straight from backend data — operation name + equipment id.
  const equipSign = useMemo(() => canvasTextTexture(st.equipment ?? st.key, "#7dd3fc"), [st.equipment, st.key]);
  const nameSign = useMemo(() => canvasTextTexture(st.name), [st.name]);

  useFrame(({ clock }) => {
    // Health stripes breathe when attention is needed; in-control/idle hold.
    if (stripe.current) {
      stripe.current.emissiveIntensity = pulse
        ? 0.75 + 0.5 * Math.sin(clock.elapsedTime * 4)
        : selected
          ? 1.3
          : 0.55;
    }
  });

  return (
    <group
      position={[x, 0, 0]}
      onClick={(e) => {
        e.stopPropagation();
        onSelect(st.key);
      }}
    >
      <mesh position={[0, 0.9, 0]}>
        <boxGeometry args={[3, 1.8, 2.2]} />
        <meshStandardMaterial color="#1e293b" metalness={0.35} roughness={0.55} />
      </mesh>
      {/* health stripe — the equipment status light, driven by chart state */}
      <mesh position={[0, 1.62, 1.12]}>
        <boxGeometry args={[3.04, 0.22, 0.06]} />
        <meshStandardMaterial ref={stripe} color={color} emissive={color} emissiveIntensity={0.55} />
      </mesh>
      <mesh position={[0, 2.35, 0]}>
        <planeGeometry args={[2.6, 0.65]} />
        <meshBasicMaterial map={equipSign} transparent />
      </mesh>
      <mesh position={[0, 2.95, 0]}>
        <planeGeometry args={[3.6, 0.56]} />
        <meshBasicMaterial map={nameSign} transparent />
      </mesh>
      {selected && (
        <mesh position={[0, 0.02, 0]} rotation={[-Math.PI / 2, 0, 0]}>
          <ringGeometry args={[2.1, 2.35, 48]} />
          <meshBasicMaterial color={accent.primary} transparent opacity={0.85} />
        </mesh>
      )}
    </group>
  );
}

function LotDots({ lots, span }: { lots: FactoryLotDot[]; span: number }) {
  const group = useRef<THREE.Group>(null);
  const SLOT = 0.7;
  // Constant belt speed, wrapped by one slot so the flow never pops.
  useFrame((_, dt) => {
    if (!group.current) return;
    group.current.position.x -= dt * 0.35;
    if (group.current.position.x < -SLOT) group.current.position.x += SLOT;
  });
  return (
    <group ref={group}>
      {lots.map((lot, i) => (
        <mesh key={lot.businessId} position={[-span / 2 + 2 + i * SLOT, 0.44, 2.6]}>
          <sphereGeometry args={[0.17, 12, 12]} />
          <meshStandardMaterial color={DISPOSITION_3D[lot.disposition]} emissive={DISPOSITION_3D[lot.disposition]} emissiveIntensity={0.35} />
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
  lots: LotCard[];
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
        <ambientLight intensity={0.5} />
        <directionalLight position={[4, 9, 5]} intensity={1.3} />
        <directionalLight position={[-6, 4, -4]} intensity={0.3} />
        <gridHelper args={[44, 44, "#1e293b", "#141c2e"]} position={[0, 0, 0]} />
        <OrbitControls makeDefault target={[0, 1, 0]} />
        {scene.stations.map((st, i) => (
          <Station key={st.key} st={st} x={stationX(i, scene.stations.length, scene.spacing)} selected={st.key === selectedKey} onSelect={onSelect} />
        ))}
        {/* conveyor spine in front of the stations */}
        <mesh position={[0, 0.12, 2.6]}>
          <boxGeometry args={[span + 4, 0.24, 1.3]} />
          <meshStandardMaterial color="#0f172a" metalness={0.2} roughness={0.7} />
        </mesh>
        <LotDots lots={scene.lots} span={span + 4} />
        <ContactShadows position={[0, 0.01, 0]} scale={34} blur={2.2} opacity={0.4} far={4} resolution={256} />
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
