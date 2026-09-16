import { Component, useEffect, useLayoutEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import * as THREE from "three";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { Bounds, ContactShadows, OrbitControls } from "@react-three/drei";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import type { Group, Mesh } from "three";
import type { ComponentDto } from "../lib/api";
import { api } from "../lib/api";
import { stressHsl, stressOf } from "../lib/stress";
import { useTwinStore } from "../store";
import { TwinControls } from "./TwinControls";
import { HudChip, btn } from "../ui/kit";
import { accent, bg, border, status as S, text as T } from "../ui/tokens";

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
  // AirInput module — internal mechanism kinds, deliberately NOT in
  // BODY_KINDS: the "case" a user X-rays or explodes parts out of is the
  // housing shell alone, not the whole PCB assembly riding inside it.
  if (n.includes("pcb")) return "pcb";
  if (n.includes("electrode")) return "electrode";
  if (n.includes("asic")) return "asic";
  if (n.includes("resistor") || n.includes("capacitor")) return "passive";
  if (n.includes("connector")) return "connector";
  if (n.includes("lens")) return "lens";
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

// FR-03 design-review modes. "off" is the clean default experience; the rest
// reroute part clicks away from selection/actuation (measuring must never
// press the switch).
export type ReviewMode = "off" | "section" | "measure" | "annotate";

function AssemblyModel({ scene, mode, onPoint }: { scene: Group; mode: ReviewMode; onPoint: (p: [number, number, number]) => void }) {
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
        // Review tools consume the click: pick a point, not a part.
        if (mode === "measure" || mode === "annotate") {
          onPoint([e.point.x, e.point.y, e.point.z]);
          return;
        }
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
      onPointerOver={(e: any) => (e.object.cursor = mode === "off" ? "pointer" : "crosshair")}
    />
  );
}

// Per-frame digital-twin driver: actuation travel, vehicle-vibration jitter,
// and the stress time-lapse tint. Reads the shared twin store every frame, so
// the TwinControls overlay (outside the Canvas) and mesh clicks both drive it.
const PLUNGER_TRAVEL_MM = 0.25;
const DOME_TRAVEL_MM = 0.12;
// Vertical-only layer separation for the exploded view (x/y stay 0 — parts
// never drift sideways). Parts are clustered into horizontal LAYERS by their
// center z and each layer is offset by (rank − pivot) × gap: an evenly
// spaced fan in stack order, the way a real exploded diagram reads. RAW z
// offsets from the bbox center can't do this — on a thin stack like the
// AirInput module (8 parts across ~5 mm of z, most of them within 1 mm of
// the center) nearly every raw offset rounds to ~0 and only the topmost
// part visibly separates.
const EXPLODE_LAYER_TOL_MM = 0.15; // co-located parts (same mounting plane) share a layer
const EXPLODE_MAX_SPREAD = 3.2; // total fan ≤ this × assembly height…
// …and ≤ this fraction of the mount-time visible height. The camera is
// fitted ONCE to the assembled bbox (<Bounds> at mount — the explode mutates
// meshes per-frame, so there is no refit), and the fitted view measures
// ≈ 10 mm + 1.7 × largest bbox dimension (empirical: a 4.5 mm TACT fan of
// ~19 mm fit with margin while a 25 mm encoder fan of ~55 mm clipped).
const EXPLODE_VISIBLE_MIN_MM = 10;
const EXPLODE_VISIBLE_PER_MM = 1.7;
const EXPLODE_VISIBLE_SAFETY = 0.85;
// Full assemble → explode → reassemble cycle when playing, seconds. Smooth
// sinusoidal easing (not a linear triangle wave) so the direction reversal
// at each end doesn't read as a jolt.
const EXPLODE_PERIOD_S = 6;

function TwinAnimator({ scenes }: { scenes: Group[] }) {
  const actuated = useTwinStore((s) => s.actuated);
  const vibration = useTwinStore((s) => s.vibration);
  const cycles = useTwinStore((s) => s.cycles);
  const explodeAmount = useTwinStore((s) => s.explodeAmount);
  const explodePlaying = useTwinStore((s) => s.explodePlaying);
  const actRef = useRef(0);

  const parts = useMemo(() => {
    type PartEntry = {
      mesh: Mesh;
      kind: string;
      basePosition: THREE.Vector3;
      explodeDir: THREE.Vector3;
      baseColor: THREE.Color;
    };
    const map: PartEntry[] = [];
    for (const scene of scenes) {
      // BODY_KINDS parts (the housing/package shell) are the exploded
      // view's fixed reference frame — real exploded diagrams keep the
      // enclosure in place and fly the internals out around it, and it
      // pairs naturally with the body-opacity X-ray control right above.
      const bbox = new THREE.Box3().setFromObject(scene);
      const size = bbox.getSize(new THREE.Vector3());
      const height = Math.max(1e-6, size.z);

      const movable: { part: PartEntry; z: number }[] = [];
      scene.traverse((obj) => {
        const mesh = obj as Mesh;
        if (!mesh.isMesh) return;
        const kind = (mesh.userData.partKind as string | undefined) ?? "";
        const material = (Array.isArray(mesh.material) ? mesh.material[0] : mesh.material) as THREE.MeshStandardMaterial;
        const part: PartEntry = {
          mesh,
          kind,
          basePosition: mesh.position.clone(),
          explodeDir: new THREE.Vector3(),
          baseColor: material.color.clone(),
        };
        map.push(part);
        if (!BODY_KINDS.has(kind)) {
          const z = new THREE.Box3().setFromObject(mesh).getCenter(new THREE.Vector3()).z;
          movable.push({ part, z });
        }
      });

      // Cluster the movable parts into horizontal layers by center z
      // (z-sorted here): parts mounted on the same plane — the TACT's two
      // terminals, the encoder's three — share a layer and move together,
      // so symmetric hardware never fans apart from itself.
      movable.sort((a, b) => a.z - b.z);
      const tol = Math.max(EXPLODE_LAYER_TOL_MM, height * 0.02);
      const layerZ: number[] = [];
      const layerOf = new Map<{ part: PartEntry; z: number }, number>();
      for (const m of movable) {
        const last = layerZ.length - 1;
        layerOf.set(m, last >= 0 && m.z - layerZ[last] <= tol ? last : layerZ.push(m.z) - 1);
      }
      // Even fan in stack order, centered on the assembly's mid-height so
      // the exploded stack stays framed like the assembled one. The total
      // fan is capped twice: proportionally to the assembly's own height,
      // and to the mount-time visible height (see the constants above) —
      // an over-eager fan on a tall part stack flies clean out of frame.
      const layers = Math.max(1, layerZ.length);
      const visible =
        (EXPLODE_VISIBLE_MIN_MM + EXPLODE_VISIBLE_PER_MM * Math.max(size.x, size.y, size.z)) *
        EXPLODE_VISIBLE_SAFETY;
      const spread = Math.min(height * EXPLODE_MAX_SPREAD, Math.max(0, visible - height));
      const gap = spread / Math.max(1, layers - 1);
      for (const m of movable) m.part.explodeDir.set(0, 0, (layerOf.get(m)! - (layers - 1) / 2) * gap);
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
    // The play loop drives its own phase off wall-clock time rather than a
    // React state value — round-tripping an animated number through Zustand
    // every frame would re-render the whole panel tree 60x/sec for no
    // reason. The manual slider (store.explodeAmount) only takes over when
    // not playing.
    const ex = explodePlaying
      ? (Math.sin((t * 2 * Math.PI) / EXPLODE_PERIOD_S - Math.PI / 2) + 1) / 2
      : explodeAmount;

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
      let z = part.basePosition.z + part.explodeDir.z * ex;
      if (part.kind === "plunger" || part.kind === "epoxy") {
        z = part.basePosition.z - PLUNGER_TRAVEL_MM * act + part.explodeDir.z * ex;
      } else if (part.kind === "dome") {
        z = part.basePosition.z - DOME_TRAVEL_MM * act + part.explodeDir.z * ex;
      }
      part.mesh.position.set(
        part.basePosition.x + part.explodeDir.x * ex,
        part.basePosition.y + part.explodeDir.y * ex,
        z
      );
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

// Image-based lighting from a generated studio — the same recipe as the EDA
// scenes' drei <Environment>: a few bright area panels on a shell, PMREM'd
// into an env map. RoomEnvironment (a uniformly white room) was tried first
// and washed dark plastics into a milky mid-gray — an LCP housing at 4%
// albedo still picked up so much white-room irradiance that it rendered like
// untextured clay. Area lights on a controlled backdrop keep molded black
// black (dark mode) and give metals crisp, believable highlights, with zero
// external assets (drei's Environment presets fetch remote HDRIs, which this
// deployment can't reach). The light mode is the same set with brighter
// panels and a bright floor — a "product photo on white" look that separates
// dark-cased parts from the backdrop.
// Exported for the Test Bench board — its metallic parts need the same
// image-based lighting or metalness=1 renders black.
const BG_THEMES = {
  dark: {
    canvas: "#0f172a",
    shell: "#05070d",
    panels: [
      { color: "#eaf1ff", intensity: 2.6, size: [16, 16] as const, pos: [0, 8, 0] as const },
      // Side panels run TALL (studio strip lights): a curved metal part — the
      // encoder's stainless shaft — picks up a long vertical highlight, the
      // way product photography lights a turned surface.
      { color: "#cfe0ff", intensity: 1.3, size: [10, 9] as const, pos: [9, 4, 6] as const },
      { color: "#ffe7c4", intensity: 0.9, size: [10, 7] as const, pos: [-9, 3, -5] as const },
      // Back fill: without it, faces angled away from the strips mirror pure
      // black and polished metal reads as black plastic.
      { color: "#aac4e8", intensity: 0.6, size: [12, 8] as const, pos: [0, 3, -9] as const },
      { color: "#2c3d58", intensity: 0.55, size: [16, 16] as const, pos: [0, -8, 0] as const },
    ],
  },
  light: {
    canvas: "#e8ecf2",
    shell: "#dfe5ee",
    panels: [
      { color: "#ffffff", intensity: 3.1, size: [16, 16] as const, pos: [0, 8, 0] as const },
      { color: "#eaf1ff", intensity: 1.7, size: [10, 9] as const, pos: [9, 4, 6] as const },
      { color: "#fff1da", intensity: 1.2, size: [10, 7] as const, pos: [-9, 3, -5] as const },
      { color: "#e6edf6", intensity: 1.0, size: [12, 8] as const, pos: [0, 3, -9] as const },
      { color: "#f2f5f9", intensity: 0.95, size: [16, 16] as const, pos: [0, -8, 0] as const },
    ],
  },
} as const;

export function ViewerEnvironment() {
  const gl = useThree((s) => s.gl);
  const scene = useThree((s) => s.scene);
  const viewerBg = useTwinStore((s) => s.viewerBg);

  useEffect(() => {
    const theme = BG_THEMES[viewerBg];
    const pmrem = new THREE.PMREMGenerator(gl);
    const studio = new THREE.Scene();
    studio.background = new THREE.Color(theme.shell);
    // MeshBasicMaterial color channels exceed 1.0 on purpose — PMREM captures
    // that as HDR area lights, no texture needed.
    for (const p of theme.panels) {
      const mesh = new THREE.Mesh(
        new THREE.PlaneGeometry(p.size[0], p.size[1]),
        new THREE.MeshBasicMaterial({ color: new THREE.Color(p.color).multiplyScalar(p.intensity) })
      );
      mesh.position.set(p.pos[0], p.pos[1], p.pos[2]);
      mesh.lookAt(0, 0, 0);
      studio.add(mesh);
    }
    const target = pmrem.fromScene(studio, 0.04);
    // Assigning the env map to the R3F-managed scene is the documented
    // pattern (drei's own Environment does exactly this inside an effect).
    // oxlint-disable-next-line react/immutability
    scene.environment = target.texture;
    // oxlint-disable-next-line react/immutability
    scene.environmentIntensity = 1.0;
    return () => {
      scene.environment = null;
      target.dispose();
      studio.traverse((obj) => {
        const mesh = obj as THREE.Mesh;
        if (mesh.isMesh) {
          mesh.geometry.dispose();
          (mesh.material as THREE.Material).dispose();
        }
      });
      pmrem.dispose();
    };
  }, [gl, scene, viewerBg]);

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

// FR-03 section plane: cuts every assembly mesh with one world-space plane
// (axis + fractional position across the model bbox). DoubleSide while
// active so the cut interior renders instead of caving in hollow.
function SectionPlane({ scenes, bbox, axis, frac }: { scenes: Group[]; bbox: THREE.Box3 | null; axis: "x" | "y" | "z"; frac: number }) {
  const gl = useThree((s) => s.gl);
  useEffect(() => {
    if (!bbox) return;
    // oxlint-disable-next-line react/immutability -- renderer flag, same idiom as ViewerEnvironment
    gl.localClippingEnabled = true;
    const min = bbox.min[axis];
    const max = bbox.max[axis];
    const pos = min + (max - min) * frac;
    const normals: Record<"x" | "y" | "z", THREE.Vector3> = {
      x: new THREE.Vector3(-1, 0, 0),
      y: new THREE.Vector3(0, -1, 0),
      z: new THREE.Vector3(0, 0, -1),
    };
    const plane = new THREE.Plane(normals[axis], pos); // keeps p ≤ pos on the axis
    const touched: THREE.MeshStandardMaterial[] = [];
    for (const scene of scenes) {
      scene.traverse((obj) => {
        const mesh = obj as THREE.Mesh;
        if (!mesh.isMesh) return;
        const materials = Array.isArray(mesh.material) ? mesh.material : [mesh.material];
        for (const material of materials) {
          const std = material as THREE.MeshStandardMaterial;
          std.clippingPlanes = [plane];
          std.side = THREE.DoubleSide;
          std.needsUpdate = true;
          touched.push(std);
        }
      });
    }
    return () => {
      for (const std of touched) {
        std.clippingPlanes = null;
        std.side = THREE.FrontSide;
        std.needsUpdate = true;
      }
      gl.localClippingEnabled = false;
    };
  }, [gl, scenes, bbox, axis, frac]);
  return null;
}

// FR-03 review toolbar (DOM overlay, top-right): section / measure /
// annotation. Hidden behind a toggle — the default experience stays clean.
// Annotations are client-local and marked ◈ accordingly; persistence is
// explicitly deferred, not silently pretended.
function ReviewToolbar({
  mode,
  setMode,
  axis,
  setAxis,
  frac,
  setFrac,
  measure,
  annotations,
  onClearMeasure,
  onClearAnnotations,
  onDeleteAnnotation,
}: {
  mode: ReviewMode;
  setMode: (m: ReviewMode) => void;
  axis: "x" | "y" | "z";
  setAxis: (a: "x" | "y" | "z") => void;
  frac: number;
  setFrac: (f: number) => void;
  measure: { a: [number, number, number] | null; b: [number, number, number] | null; mm: number | null };
  annotations: { id: number; p: [number, number, number] }[];
  onClearMeasure: () => void;
  onClearAnnotations: () => void;
  onDeleteAnnotation: (id: number) => void;
}) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const mm = measure.mm;
  // Bottom-right: TwinControls owns the top-right corner, and the canvas
  // bottom stays free in both the cockpit and grid layouts.
  return (
    <div style={{ position: "absolute", bottom: 10, right: 10, display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 6, zIndex: 5 }}>
      {open && (
        <div
          style={{
            background: bg.hud,
            border: `1px solid ${border.strong}`,
            borderRadius: 8,
            backdropFilter: "blur(6px)",
            padding: 10,
            display: "flex",
            flexDirection: "column",
            gap: 8,
            width: 240,
          }}
        >
          <div style={{ display: "flex", gap: 6 }}>
            {(["section", "measure", "annotate"] as const).map((m) => (
              <button key={m} style={{ ...btn(mode === m, accent.primary), flex: 1 }} onClick={() => setMode(mode === m ? "off" : m)} aria-pressed={mode === m}>
                {t(`viewer.${m}`)}
              </button>
            ))}
          </div>

          {mode === "section" && (
            <div style={{ display: "flex", flexDirection: "column", gap: 6, fontSize: 11, color: T.muted }}>
              <div style={{ display: "flex", gap: 6 }}>
                {(["x", "y", "z"] as const).map((a) => (
                  <button key={a} style={{ ...btn(axis === a, accent.kpi), flex: 1, textTransform: "uppercase" }} onClick={() => setAxis(a)} aria-pressed={axis === a}>
                    {a}
                  </button>
                ))}
              </div>
              <input type="range" min={0} max={1} step={0.01} value={frac} onChange={(e) => setFrac(Number(e.target.value))} style={{ accentColor: accent.kpi }} aria-label={t("viewer.section")} />
              <span>{t("viewer.sectionHint")}</span>
            </div>
          )}

          {mode === "measure" && (
            <div style={{ display: "flex", flexDirection: "column", gap: 6, fontSize: 11, color: T.muted }}>
              <HudChip color={S.info}>{t("viewer.measureHint")}</HudChip>
              {mm !== null && (
                <div style={{ fontSize: 15, fontFamily: "monospace", color: T.bright, textAlign: "center" }}>
                  {mm.toFixed(2)} mm
                </div>
              )}
              <button style={btn(false, S.idle)} onClick={onClearMeasure}>
                {t("viewer.clear")}
              </button>
            </div>
          )}

          {mode === "annotate" && (
            <div style={{ display: "flex", flexDirection: "column", gap: 6, fontSize: 11, color: T.muted }}>
              <HudChip color={S.info}>{t("viewer.annotateHint")}</HudChip>
              <span>◈ {t("viewer.annotateLocal")}</span>
              {annotations.length > 0 && (
                <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
                  {annotations.map((a, i) => (
                    <div key={a.id} style={{ display: "flex", alignItems: "center", gap: 6 }}>
                      <span style={{ fontFamily: "monospace", color: T.body }}>#{i + 1}</span>
                      <button
                        aria-label={`${t("viewer.clear")} #${i + 1}`}
                        onClick={() => onDeleteAnnotation(a.id)}
                        style={{ marginLeft: "auto", padding: "1px 7px", borderRadius: 6, border: `1px solid ${border.base}`, background: bg.raise, color: T.body, cursor: "pointer" }}
                      >
                        ✕
                      </button>
                    </div>
                  ))}
                  <button style={btn(false, S.idle)} onClick={onClearAnnotations}>
                    {t("viewer.clear")}
                  </button>
                </div>
              )}
            </div>
          )}
        </div>
      )}
      <button
        style={btn(open, S.info)}
        onClick={() => {
          // Closing the panel also stands the tool down — a leftover active
          // section/measure/annotate mode would silently eat part clicks.
          if (open) setMode("off");
          setOpen(!open);
        }}
        aria-expanded={open}
      >
        {t("viewer.review")}
      </button>
    </div>
  );
}

export function ThreeViewer({ components, controlsTop = 10 }: { components: ComponentDto[]; controlsTop?: number }) {
  const setSelected = useTwinStore((s) => s.setSelectedComponentId);
  const viewerBg = useTwinStore((s) => s.viewerBg);
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

  // FR-03 review-tool state (all client-local; default mode "off" = clean).
  const [mode, setMode] = useState<ReviewMode>("off");
  const [axis, setAxis] = useState<"x" | "y" | "z">("y");
  const [frac, setFrac] = useState(0.5);
  const [measure, setMeasure] = useState<{ a: [number, number, number] | null; b: [number, number, number] | null; mm: number | null }>({ a: null, b: null, mm: null });
  const [annotations, setAnnotations] = useState<{ id: number; p: [number, number, number] }[]>([]);
  const scenes = useMemo(() => loaded.map(([, entry]) => entry.scene), [loaded]);
  const nextAnnotationId = useRef(1);

  // World bbox of the assembled model — anchors the section slider range,
  // the pin size, and keeps measurements in STEP mm (world unit = mm).
  const groupRef = useRef<Group>(null);
  const [bbox, setBbox] = useState<THREE.Box3 | null>(null);
  useLayoutEffect(() => {
    const g = groupRef.current;
    if (!g) return;
    g.updateWorldMatrix(true, true);
    setBbox(new THREE.Box3().setFromObject(g));
  }, [sceneKey]);

  const onReviewPoint = (p: [number, number, number]) => {
    if (mode === "measure") {
      setMeasure((m) => {
        if (!m.a || m.b) return { a: p, b: null, mm: null };
        const mm = Math.hypot(p[0] - m.a[0], p[1] - m.a[1], p[2] - m.a[2]);
        return { a: m.a, b: p, mm };
      });
    } else if (mode === "annotate") {
      setAnnotations((list) => [...list, { id: nextAnnotationId.current++, p }]);
    }
  };
  const pinScale = bbox ? Math.max(bbox.getSize(new THREE.Vector3()).length() * 0.014, 0.06) : 0.1;

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
        style={{ background: BG_THEMES[viewerBg].canvas, borderRadius: 8, transition: "background 0.25s" }}
      >
        <ViewerEnvironment />
        {/* env map supplies the fill; keep direct lights for shape definition.
            Kept dim — the earlier 0.2/1.6 pair plus the old white-room env map
            lifted even 4%-albedo black plastic into washed-out mid-gray. */}
        <ambientLight intensity={0.1} />
        <directionalLight position={[5, 10, 5]} intensity={1.35} />
        <directionalLight position={[-6, 4, -4]} intensity={0.35} />
        <Bounds fit clip observe margin={2.0} key={sceneKey}>
          {/* STEP geometry is Z-up, glTF/three is Y-up. No <Center>: Bounds
              fit already targets the measured box center, and Center's
              late-applied offset raced the fit (camera aimed at the
              pre-center position → bottom of the model cropped). */}
          <group rotation={[-Math.PI / 2, 0, 0]} ref={groupRef}>
            {loaded.map(([versionId, entry]) => (
              <AssemblyModel key={versionId} scene={entry.scene} mode={mode} onPoint={onReviewPoint} />
            ))}
            {components.map((c, i) =>
              !c.artifact_version_id || failed.has(c.artifact_version_id) ? (
                <PlaceholderPart key={c.id} component={c} index={i} />
              ) : null
            )}
          </group>
        </Bounds>
        {mode === "section" && <SectionPlane scenes={scenes} bbox={bbox} axis={axis} frac={frac} />}
        {/* measurement endpoints + annotation pins, sized off the model bbox */}
        {measure.a && (
          <mesh position={measure.a}>
            <sphereGeometry args={[pinScale, 12, 12]} />
            <meshBasicMaterial color={accent.kpi} />
          </mesh>
        )}
        {measure.b && (
          <mesh position={measure.b}>
            <sphereGeometry args={[pinScale, 12, 12]} />
            <meshBasicMaterial color={accent.kpi} />
          </mesh>
        )}
        {annotations.map((a) => (
          <mesh key={a.id} position={a.p}>
            <sphereGeometry args={[pinScale, 12, 12]} />
            <meshBasicMaterial color={accent.primary} />
          </mesh>
        ))}
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
      <TwinControls top={controlsTop} />
      <ReviewToolbar
        mode={mode}
        setMode={setMode}
        axis={axis}
        setAxis={setAxis}
        frac={frac}
        setFrac={setFrac}
        measure={measure}
        annotations={annotations}
        onClearMeasure={() => setMeasure({ a: null, b: null, mm: null })}
        onClearAnnotations={() => setAnnotations([])}
        onDeleteAnnotation={(id) => setAnnotations((list) => list.filter((x) => x.id !== id))}
      />
    </ViewerErrorBoundary>
    </div>
  );
}
