import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { OrbitControls } from "@react-three/drei";
import type * as THREE from "three";
import type { EdaScene } from "./edaScene";

// Chip 3D browser — the Unity-MCP scene pipeline replaced by react-three-fiber.
// Boxes are grouped per layer; the explode slider separates the layer-cake by
// animating each layer GROUP's y (cheap: ~20 groups, meshes stay static).

const EXPLODE_K = 4.0; // separation multiplier at explode = 1

// Camera rig: frame the scene once per scene change; the user orbits after.
function Fit({ distance, target }: { distance: number; target: [number, number, number] }) {
  const { camera } = useThree();
  useEffect(() => {
    camera.position.set(target[0] + distance * 0.72, distance * 0.62, target[2] + distance * 0.72);
    camera.lookAt(target[0], target[1], target[2]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [camera, distance, target.join(",")]);
  return null;
}

// Per-layer y-offset animator. Reads the shared explode target and eases the
// current value toward it — no React re-render per frame.
function LayerGroup({
  anchor,
  explodeRef,
  children,
}: {
  anchor: number;
  explodeRef: React.MutableRefObject<{ current: number; target: number }>;
  children: React.ReactNode;
}) {
  const ref = useRef<THREE.Group>(null);
  useFrame((_, dt) => {
    const st = explodeRef.current;
    if (Math.abs(st.current - st.target) > 0.001) {
      st.current += (st.target - st.current) * Math.min(1, dt * 6);
      // Group y = anchor × separation; meshes sit at (naturalY − anchor) locally
      if (ref.current) ref.current.position.y = anchor * (1 + st.current * EXPLODE_K);
    }
  });
  return (
    <group ref={ref} position={[0, anchor, 0]}>
      {children}
    </group>
  );
}

const rgbCss = (c: [number, number, number]) =>
  `rgb(${Math.round(c[0] * 255)},${Math.round(c[1] * 255)},${Math.round(c[2] * 255)})`;

export function Eda3DViewer({ scene }: { scene: EdaScene | null }) {
  const { t } = useTranslation();
  const [explode, setExplode] = useState(0);
  const [hidden, setHidden] = useState<Set<string>>(new Set());
  const explodeRef = useRef({ current: 0, target: 0 });
  // Process-mode build-up: step k shows fab steps 0..k (index into scene.steps)
  const [step, setStep] = useState(0);
  const [playing, setPlaying] = useState(false);

  // New scene → reset view state (a layout's layers don't carry over)
  useEffect(() => {
    setExplode(0);
    setHidden(new Set());
    explodeRef.current = { current: 0, target: 0 };
    setPlaying(false);
    setStep(Math.max(0, (scene?.steps?.length ?? 1) - 1));
  }, [scene]);

  // Auto-play the fab flow: advance a step every 900 ms until the top.
  const nSteps = scene?.steps?.length ?? 0;
  useEffect(() => {
    if (!playing) return;
    if (step >= nSteps - 1) {
      setPlaying(false);
      return;
    }
    const id = setTimeout(() => applyStep(step + 1), 900);
    return () => clearTimeout(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [playing, step, nSteps]);

  const applyStep = (k: number) => {
    const clamped = Math.max(0, Math.min(nSteps - 1, k));
    setStep(clamped);
    if (scene?.steps) setHidden(new Set(scene.steps.slice(clamped + 1)));
  };

  const layers = useMemo(() => {
    if (!scene) return [];
    const groups = new Map<string, { anchor: number; boxes: typeof scene.boxes }>();
    for (const b of scene.boxes) {
      let g = groups.get(b.layer);
      if (!g) {
        g = { anchor: b.pos[1], boxes: [] };
        groups.set(b.layer, g);
      }
      g.anchor = Math.min(g.anchor, b.pos[1]);
      g.boxes.push(b);
    }
    return [...groups.entries()].map(([key, g]) => ({ key, ...g, anchor: scene.explodeAnchors?.[key] ?? g.anchor }));
  }, [scene]);

  useEffect(() => {
    explodeRef.current.target = explode;
  }, [explode]);

  if (!scene) {
    return (
      <div style={{ height: "100%", display: "grid", placeItems: "center", color: "#64748b", fontSize: 13 }}>
        {t("eda.view3d.empty")}
      </div>
    );
  }

  const toggleLayer = (key: string) =>
    setHidden((h) => {
      const n = new Set(h);
      if (n.has(key)) n.delete(key);
      else n.add(key);
      return n;
    });

  return (
    <div style={{ position: "relative", height: "100%", minHeight: 380, borderRadius: 8, overflow: "hidden", border: "1px solid #1e293b" }}>
      <Canvas dpr={[1, 2]} camera={{ fov: 42, near: 0.05, far: 500 }}>
        <color attach="background" args={["#0b1220"]} />
        <ambientLight intensity={0.35} />
        <directionalLight position={[18, 26, 12]} intensity={1.7} />
        <directionalLight position={[-14, 8, -10]} intensity={0.4} />
        <Fit distance={scene.distance} target={scene.target} />
        <group key={`${scene.mode}-${scene.boxes.length}`}>
          {layers.map(({ key, anchor, boxes }) =>
            hidden.has(key) ? null : (
              <LayerGroup key={key} anchor={anchor} explodeRef={explodeRef}>
                {boxes.map((b, i) => (
                  <mesh key={i} position={[b.pos[0], b.pos[1] - anchor, b.pos[2]]}>
                    {b.cyl ? (
                      <cylinderGeometry args={[b.size[0] / 2, b.size[0] / 2, b.size[1], 12]} />
                    ) : (
                      <boxGeometry args={b.size} />
                    )}
                    <meshStandardMaterial
                      color={rgbCss(b.color)}
                      metalness={b.metalness ?? 0.2}
                      roughness={b.roughness ?? 0.55}
                      emissive={rgbCss(b.color)}
                      emissiveIntensity={b.emissive ?? 0}
                      transparent={b.opacity !== undefined && b.opacity < 1}
                      opacity={b.opacity ?? 1}
                    />
                  </mesh>
                ))}
              </LayerGroup>
            ),
          )}
        </group>
        <gridHelper args={[Math.ceil(scene.distance * 1.6), 20, "#1e293b", "#141c2e"]} position={[0, -0.35, 0]} />
        <OrbitControls makeDefault enableDamping dampingFactor={0.08} />
      </Canvas>

      {/* Overlay: explode slider + layer visibility chips */}
      <div style={{ position: "absolute", left: 10, top: 10, display: "flex", alignItems: "center", gap: 8, background: "rgba(2,6,23,0.72)", borderRadius: 6, padding: "4px 10px" }}>
        <span style={{ fontSize: 11, color: "#94a3b8" }}>{t("twin.explode")}</span>
        <input
          type="range"
          aria-label="explode"
          min={0}
          max={1}
          step={0.01}
          value={explode}
          onChange={(e) => setExplode(parseFloat(e.target.value))}
          style={{ width: 130 }}
        />
      </div>
      {/* Process mode: fab-flow build-up slider + play */}
      {scene.mode === "process" && scene.steps && (
        <div style={{ position: "absolute", right: 10, top: 10, display: "flex", alignItems: "center", gap: 8, background: "rgba(2,6,23,0.72)", borderRadius: 6, padding: "4px 10px" }}>
          <button
            aria-label="process-play"
            onClick={() => {
              if (step >= nSteps - 1) applyStep(0);
              setPlaying((p) => !p);
            }}
            style={{ fontSize: 11, padding: "2px 8px", borderRadius: 5, border: "1px solid #334155", background: playing ? "#164e63" : "#0f172a", color: "#a5f3fc", cursor: "pointer" }}
          >
            {playing ? `⏸ ${t("eda.processStop")}` : `▶ ${t("eda.processPlay")}`}
          </button>
          <input
            type="range"
            aria-label="process-step"
            min={0}
            max={Math.max(0, nSteps - 1)}
            step={1}
            value={step}
            onChange={(e) => {
              setPlaying(false);
              applyStep(parseInt(e.target.value, 10));
            }}
            style={{ width: 150 }}
          />
          <span style={{ fontSize: 11, color: "#94a3b8", fontFamily: "monospace", minWidth: 130 }}>
            {scene.steps[step]} · {step + 1}/{nSteps}
          </span>
        </div>
      )}
      <div data-eda-layers style={{ position: "absolute", left: 10, bottom: 10, right: 10, display: "flex", flexWrap: "wrap", gap: 4 }}>
        {scene.legend.map((l) => {
          const off = hidden.has(l.key);
          return (
            <button
              key={l.key}
              onClick={() => toggleLayer(l.key)}
              title={off ? t("eda.layerShow") : t("eda.layerHide")}
              style={{
                fontSize: 10,
                fontFamily: "monospace",
                display: "flex",
                alignItems: "center",
                gap: 4,
                padding: "2px 7px",
                borderRadius: 10,
                border: "1px solid #334155",
                background: "rgba(2,6,23,0.72)",
                color: off ? "#475569" : "#cbd5e1",
                cursor: "pointer",
                textDecoration: off ? "line-through" : "none",
              }}
            >
              <span style={{ width: 8, height: 8, borderRadius: 2, background: rgbCss(l.color), display: "inline-block" }} />
              {l.key}
              {scene.mode === "synthesis" ? "" : ` (${l.count})`}
            </button>
          );
        })}
      </div>
    </div>
  );
}
