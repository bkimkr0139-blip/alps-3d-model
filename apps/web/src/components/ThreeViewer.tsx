import { Component, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import * as THREE from "three";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { Bounds, ContactShadows, OrbitControls } from "@react-three/drei";
import { RoomEnvironment } from "three/examples/jsm/environments/RoomEnvironment.js";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import type { Group, Mesh } from "three";
import type { ComponentDto } from "../lib/api";
import { api } from "../lib/api";
import { stressHsl, stressOf } from "../lib/stress";
import { useTwinStore } from "../store";
import { TwinControls } from "./TwinControls";

// GLB node name → digital-twin part kind. Drives both actuation (which meshes
// move when the switch is pressed) and the stress overlay (which meshes tint
// toward red as cycles accumulate). Names come from the STEP XCAF labels.
function partKindOf(name: string): string | null {
  const n = name.toLowerCase();
  if (n.includes("plunger")) return "plunger";
  if (n.includes("epoxy")) return "epoxy";
  if (n.includes("dome")) return "dome";
  if (n.includes("contact")) return "contact";
  if (n.includes("terminal")) return "terminal";
  if (n.includes("solder")) return "solder";
  if (n.includes("shaft")) return "shaft";
  if (n.includes("detent")) return "detent";
  if (n.includes("housing") || n.includes("frame")) return "housing";
  if (n.includes("base") || n.includes("substrate") || n.includes("die") || n.includes("lid") || n.includes("port"))
    return "package";
  return null;
}

// Artifacts are fetched as bytes through the API (authenticated, same-origin)
// and parsed client-side with GLTFLoader.parse. The previous approach — a
// presigned MinIO URL handed to useGLTF — broke the moment the app was
// served from anywhere but this Mac (the URL points at localhost:9000, and
// cross-origin fetches to it are blocked), and the unhandled failure
// unmounted the whole React tree: "screen appears briefly, then blank".

// All components of a variant link the SAME assembly artifact version, so
// fetch+parse each distinct version once. trimesh dedupes identical PBR
// materials in the GLB, so three.js would share one Material instance across
// every part — clone per mesh here, otherwise the selection highlight's
// emissive tint would light up unrelated parts. GLTF node names come from the
// STEP part names (XCAF labels); matching them to Component names is what
// makes click→selection and the requirement↔3D sync work on assemblies.
function prepareAssemblyScene(scene: Group, components: ComponentDto[]): Set<string> {
  const matched = new Set<string>();
  const norm = (s: string) => s.toLowerCase().replace(/[^a-z0-9]+/g, "");
  scene.traverse((obj) => {
    const mesh = obj as THREE.Mesh;
    if (!mesh.isMesh) return;
    mesh.material = Array.isArray(mesh.material)
      ? mesh.material.map((m) => m.clone())
      : mesh.material.clone();
    // BLEND materials (e.g. the epoxy cap) ghost through the body at angles
    // where three's transparent sorting flips: force single-sided rendering
    // and depth writes so a transparent part can never punch see-through
    // holes in the opaque parts behind it.
    const mats = Array.isArray(mesh.material) ? mesh.material : [mesh.material];
    for (const m of mats) {
      const std = m as THREE.MeshStandardMaterial;
      if (std.transparent) {
        std.depthWrite = true;
        std.side = THREE.FrontSide;
      }
    }
    const kind = partKindOf(mesh.name || "");
    if (kind) mesh.userData.partKind = kind;
    const component = components.find((c) => {
      const a = norm(c.name);
      const b = norm(mesh.name || "");
      return b !== "" && (a === b || a.includes(b) || b.includes(a));
    });
    if (component) {
      mesh.userData.componentId = component.id;
      matched.add(component.id);
    }
  });
  return matched;
}

type AssemblyEntry = { scene: Group; matched: Set<string> };

// null entry = the artifact exists but failed to parse (placeholder fallback)
function useAssemblyModels(components: ComponentDto[]): Record<string, AssemblyEntry | null> {
  const [entries, setEntries] = useState<Record<string, AssemblyEntry | null>>({});

  useEffect(() => {
    let cancelled = false;
    const versionIds = [
      ...new Set(components.map((c) => c.artifact_version_id).filter((v): v is string => !!v)),
    ];
    (async () => {
      const results: [string, AssemblyEntry | null][] = [];
      for (const versionId of versionIds) {
        try {
          const buf = await api.artifactContent(versionId);
          const scene = await new Promise<Group | null>((resolve) => {
            new GLTFLoader().parse(
              buf,
              "",
              (gltf) => resolve(gltf.scene),
              () => resolve(null)
            );
          });
          results.push([versionId, scene ? { scene, matched: prepareAssemblyScene(scene, components) } : null]);
        } catch {
          results.push([versionId, null]);
        }
      }
      if (!cancelled) setEntries(Object.fromEntries(results));
    })();
    return () => {
      cancelled = true;
    };
  }, [components]);

  return entries;
}

// Body/housing-only "X-ray" opacity — an outer-shell part kind per
// partKindOf(), never the internal mechanism (dome, plunger, contact, …).
const BODY_KINDS = new Set(["housing", "package"]);

function AssemblyModel({ scene }: { scene: Group }) {
  const selectedComponentId = useTwinStore((s) => s.selectedComponentId);
  const setSelected = useTwinStore((s) => s.setSelectedComponentId);
  const actuated = useTwinStore((s) => s.actuated);
  const setActuated = useTwinStore((s) => s.setActuated);
  const bodyOpacity = useTwinStore((s) => s.bodyOpacity);

  // Safe precisely because prepareAssemblyScene cloned every material: only
  // the clicked part's own material instance gets the emissive tint.
  useEffect(() => {
    scene.traverse((obj) => {
      const mesh = obj as THREE.Mesh;
      if (!mesh.isMesh || !mesh.userData.componentId) return;
      const materials = Array.isArray(mesh.material) ? mesh.material : [mesh.material];
      for (const material of materials) {
        const std = material as THREE.MeshStandardMaterial;
        const on = mesh.userData.componentId === selectedComponentId;
        std.emissive.set(on ? "#ff6b35" : "#000000");
        std.emissiveIntensity = on ? 0.6 : 1.0;
      }
    });
  }, [selectedComponentId, scene]);

  // Slide the body below 1.0 and it goes translucent so the mechanism
  // mated inside it is visible — the same depthWrite/FrontSide guard as
  // the epoxy cap's BLEND fix, applied dynamically instead of baked into
  // the GLB, since here transparency is a viewer choice, not fixed data.
  useEffect(() => {
    scene.traverse((obj) => {
      const mesh = obj as THREE.Mesh;
      if (!mesh.isMesh || !BODY_KINDS.has(mesh.userData.partKind)) return;
      const materials = Array.isArray(mesh.material) ? mesh.material : [mesh.material];
      for (const material of materials) {
        const std = material as THREE.MeshStandardMaterial;
        const wantsTransparent = bodyOpacity < 0.999;
        std.transparent = wantsTransparent;
        std.opacity = bodyOpacity;
        std.depthWrite = true;
        std.side = THREE.FrontSide;
        std.needsUpdate = true;
      }
    });
  }, [bodyOpacity, scene]);

  return (
    <primitive
      object={scene}
      onClick={(e: any) => {
        e.stopPropagation();
        // Clicking the actuator IS the interaction: pressing the plunger (or
        // its epoxy cap) toggles the switch, alongside the usual selection.
        const kind = e.object.userData?.partKind;
        if (kind === "plunger" || kind === "epoxy") {
          setActuated(!actuated);
        }
        let o: any = e.object;
        while (o && !o.userData?.componentId) o = o.parent;
        setSelected(o?.userData?.componentId ?? null);
      }}
      onPointerOver={(e: any) => (e.object.cursor = "pointer")}
    />
  );
}

// Per-frame digital-twin driver: actuation travel, vehicle-vibration jitter,
// and the stress time-lapse tint. Reads the shared twin store every frame, so
// the TwinControls overlay (outside the Canvas) and mesh clicks both drive it.
const PLUNGER_TRAVEL_MM = 0.25;
const DOME_TRAVEL_MM = 0.12;
function TwinAnimator({ scenes }: { scenes: Group[] }) {
  const actuated = useTwinStore((s) => s.actuated);
  const vibration = useTwinStore((s) => s.vibration);
  const cycles = useTwinStore((s) => s.cycles);
  const actRef = useRef(0);

  const parts = useMemo(() => {
    const map: { mesh: Mesh; kind: string; baseZ: number; baseColor: THREE.Color }[] = [];
    for (const scene of scenes) {
      scene.traverse((obj) => {
        const mesh = obj as Mesh;
        if (!mesh.isMesh || !mesh.userData.partKind) return;
        const material = (Array.isArray(mesh.material) ? mesh.material[0] : mesh.material) as THREE.MeshStandardMaterial;
        map.push({
          mesh,
          kind: mesh.userData.partKind as string,
          baseZ: mesh.position.z,
          baseColor: material.color.clone(),
        });
      });
    }
    return map;
  }, [scenes]);

  // Per-frame scene-graph mutation is the point of an animator — the linter's
  // immutability rule doesn't apply to three.js objects.
  // oxlint-disable-next-line react/immutability
  useFrame((_, dt) => {
    // Exponential approach gives a soft press and a quick release without a
    // full spring solver; ~60 fps dt≈16 ms → reaches 95% in ~140 ms.
    const target = actuated ? 1 : 0;
    actRef.current += (target - actRef.current) * Math.min(1, dt * 22);
    const act = actRef.current;

    const t = performance.now() / 1000;
    for (const scene of scenes) {
      if (vibration) {
        // STEP frame inside the rotated group: x/y are horizontal, z is up.
        scene.position.set(
          (Math.sin(t * 91) + Math.sin(t * 47.3)) * 0.012,
          (Math.sin(t * 73.7) + Math.cos(t * 39.1)) * 0.012,
          Math.sin(t * 121) * 0.006
        );
      } else if (scene.position.lengthSq() > 0) {
        scene.position.set(0, 0, 0);
      }
    }

    // Per-frame scene-graph mutation is the point of an animator — the
    // immutability rule targets React state, not three.js objects.
    // oxlint-disable react/immutability
    for (const part of parts) {
      if (part.kind === "plunger" || part.kind === "epoxy") {
        part.mesh.position.z = part.baseZ - PLUNGER_TRAVEL_MM * act;
      } else if (part.kind === "dome") {
        part.mesh.position.z = part.baseZ - DOME_TRAVEL_MM * act;
      }
      const stress = stressOf(part.kind, cycles, vibration);
      const material = (Array.isArray(part.mesh.material) ? part.mesh.material[0] : part.mesh.material) as THREE.MeshStandardMaterial;
      if (stress > 0.001) {
        const [h, s, l] = stressHsl(stress);
        material.color.setHSL(h, s, l);
      } else {
        material.color.copy(part.baseColor);
      }
    }
    // oxlint-enable react/immutability
  });

  return null;
}

function PlaceholderPart({ component, index }: { component: ComponentDto; index: number }) {
  const selected = useTwinStore((s) => s.selectedComponentId === component.id);
  const setSelected = useTwinStore((s) => s.setSelectedComponentId);
  return (
    <mesh
      position={[index * 2.5 - 2.5, 0, 0]}
      onClick={(e) => {
        e.stopPropagation();
        setSelected(component.id);
      }}
    >
      <boxGeometry args={[1.5, 1.5, 1.5]} />
      <meshStandardMaterial color={selected ? "#ff6b35" : "#94a3b8"} />
    </mesh>
  );
}

// Image-based lighting from three's built-in RoomEnvironment — photoreal
// reflections with zero external assets (drei's Environment presets fetch
// remote HDRIs, which this deployment can't reach).
// Exported for the Test Bench board — its metallic parts need the same
// image-based lighting or metalness=1 renders black.
export function ViewerEnvironment() {
  const gl = useThree((s) => s.gl);
  const scene = useThree((s) => s.scene);

  useEffect(() => {
    const pmrem = new THREE.PMREMGenerator(gl);
    const room = new RoomEnvironment();
    const target = pmrem.fromScene(room, 0.04);
    // Assigning the env map to the R3F-managed scene is the documented
    // pattern (drei's own Environment does exactly this inside an effect).
    // oxlint-disable-next-line react/immutability
    scene.environment = target.texture;
    // oxlint-disable-next-line react/immutability
    scene.environmentIntensity = 0.9;
    return () => {
      scene.environment = null;
      target.dispose();
      room.dispose();
      pmrem.dispose();
    };
  }, [gl, scene]);

  return null;
}

// A render error inside the Canvas must never take the whole workbench down
// again — degrade to a message, keep the rest of the app interactive.
class ViewerErrorBoundary extends Component<{ children: ReactNode }, { error: boolean }> {
  state = { error: false };
  static getDerivedStateFromError() {
    return { error: true };
  }
  render() {
    if (this.state.error) {
      return (
        <ViewerErrorText />
      );
    }
    return this.props.children;
  }
}

// The boundary is a class (no hooks allowed) — the localized message comes
// from this tiny functional child.
function ViewerErrorText() {
  const { t } = useTranslation();
  return (
    <div
      style={{
        height: "100%",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        color: "#f87171",
        background: "#0f172a",
        borderRadius: 8,
        fontSize: 14,
      }}
    >
      {t("viewer.renderError")}
    </div>
  );
}

export function ThreeViewer({ components }: { components: ComponentDto[] }) {
  const setSelected = useTwinStore((s) => s.setSelectedComponentId);
  const entries = useAssemblyModels(components);

  const loaded = Object.entries(entries).filter((e): e is [string, AssemblyEntry] => e[1] !== null);
  const failed = new Set(
    Object.entries(entries).filter(([, entry]) => entry === null).map(([versionId]) => versionId)
  );
  // Key Bounds by the loaded version SET, not a loaded/empty flag: switching
  // product swaps in a completely different model, and without the remount
  // the new model inherits the previous product's fitted camera (a 5 mm
  // sensor rendered as a speck after a tall encoder).
  const sceneKey = loaded.map(([versionId]) => versionId).sort().join("|") || "empty";

  return (
    <div style={{ position: "relative", height: "100%" }}>
    <ViewerErrorBoundary>
      <Canvas
        dpr={[1, 2]}
        // Elevation matters more than it looks: [8,6,8] sits at only ~28°
        // above the horizon, so a switch's top-facing button (or an
        // encoder's top shaft) reads mostly as a sliver on the side of the
        // body instead of the recognizable face. [6,11,8] raises that to
        // ~50° — enough to read the top face clearly on first load while
        // still keeping a 3D perspective (not a flat top-down orthographic
        // look). Bounds `fit` only rescales distance along this direction,
        // it never changes the angle, so this is the actual default view.
        camera={{ position: [6, 11, 8], fov: 40 }}
        onPointerMissed={() => setSelected(null)}
        gl={{ antialias: true }}
        style={{ background: "#0f172a", borderRadius: 8 }}
      >
        <ViewerEnvironment />
        {/* env map supplies the fill; keep direct lights for shape definition */}
        <ambientLight intensity={0.2} />
        <directionalLight position={[5, 10, 5]} intensity={1.6} />
        <directionalLight position={[-6, 4, -4]} intensity={0.35} />
        <Bounds fit clip observe margin={2.0} key={sceneKey}>
          {/* STEP geometry is Z-up, glTF/three is Y-up. No <Center>: Bounds
              fit already targets the measured box center, and Center's
              late-applied offset raced the fit (camera aimed at the
              pre-center position → bottom of the model cropped). */}
          <group rotation={[-Math.PI / 2, 0, 0]}>
            {loaded.map(([versionId, entry]) => (
              <AssemblyModel key={versionId} scene={entry.scene} />
            ))}
            {components.map((c, i) =>
              !c.artifact_version_id || failed.has(c.artifact_version_id) ? (
                <PlaceholderPart key={c.id} component={c} index={i} />
              ) : null
            )}
          </group>
        </Bounds>
        {/* model rests on y=0 after the rotation (was z=0 in STEP coords) */}
        <ContactShadows
          position={[0, -0.02, 0]}
          scale={14}
          blur={2.5}
          opacity={0.55}
          far={5}
          resolution={512}
        />
        <OrbitControls makeDefault />
        <TwinAnimator scenes={loaded.map(([, entry]) => entry.scene)} />
      </Canvas>
      <TwinControls />
    </ViewerErrorBoundary>
    </div>
  );
}
