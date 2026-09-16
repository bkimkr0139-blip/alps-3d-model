import { create } from "zustand";

export type UiTheme = "dark" | "light";

const THEME_KEY = "alps.ui-theme";

// Restored before the first paint so the stylesheet's data-theme block
// applies without a dark flash. Unset/broken storage falls back to dark —
// the instrument look the app was designed around.
function initialTheme(): UiTheme {
  try {
    return localStorage.getItem(THEME_KEY) === "light" ? "light" : "dark";
  } catch {
    return "dark";
  }
}

// Module init: reflect the restored preference on <html> before React
// mounts so there is no dark flash on a light-theme reload.
applyTheme(initialTheme());

function applyTheme(theme: UiTheme) {
  try {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem(THEME_KEY, theme);
  } catch {
    // Private window / cleared site data: the in-memory theme still works.
  }
}

interface TwinStore {
  variantId: string | null;
  selectedComponentId: string | null;
  selectedRequirementId: string | null;
  // Digital-twin interaction state shared by the 3D viewer (S04) and the
  // test bench: clicking the DUT actuates it, vibration toggles the vehicle-
  // vibration mode, cycles drives the stress time-lapse slider.
  actuated: boolean;
  vibration: boolean;
  cycles: number;
  // 0..1 opacity applied to the outer body/housing mesh only (an "X-ray"
  // control for seeing the parts mated inside it) — a viewer display
  // preference, not twin state, so it deliberately survives a variant
  // switch instead of resetting with the rest of the block below.
  bodyOpacity: number;
  // App-wide chrome theme ("dark" | "light"). Drives the --alps-* CSS
  // variables via [data-theme] on <html> and the chart palettes through
  // useChartTheme()/svgPalette. Same class of preference as bodyOpacity —
  // survives a variant switch (and a reload, via localStorage).
  uiTheme: UiTheme;
  // Backdrop brightness for the S04 3D viewer ("dark" | "light"). Dark
  // housings on the dark studio backdrop used to melt into the background;
  // a light photo-set backdrop separates them. Same class of preference as
  // bodyOpacity — survives a variant switch.
  viewerBg: "dark" | "light";
  // Exploded-view: 0 = assembled, 1 = fully separated. Manual scrub value
  // (used whenever explodePlaying is false); the animated play/reassemble
  // loop itself runs off a local ref inside TwinAnimator, not through the
  // store, to avoid a React re-render every frame. Unlike bodyOpacity this
  // DOES reset on variant switch — a mid-explosion view carried over to a
  // newly-loaded product reads as broken, not as a kept preference.
  explodeAmount: number;
  explodePlaying: boolean;
  setVariantId: (id: string) => void;
  setSelectedComponentId: (id: string | null) => void;
  setSelectedRequirementId: (id: string | null) => void;
  setActuated: (on: boolean) => void;
  setVibration: (on: boolean) => void;
  setCycles: (n: number) => void;
  setBodyOpacity: (v: number) => void;
  setViewerBg: (bg: "dark" | "light") => void;
  setUiTheme: (theme: UiTheme) => void;
  setExplodeAmount: (v: number) => void;
  setExplodePlaying: (on: boolean) => void;
}

// Cross-panel sync per §6.2: selecting a part in any panel highlights it in
// the others. One shared store, not per-panel local state.
export const useTwinStore = create<TwinStore>((set) => ({
  variantId: null,
  selectedComponentId: null,
  selectedRequirementId: null,
  actuated: false,
  vibration: false,
  cycles: 0,
  bodyOpacity: 1,
  viewerBg: "dark",
  uiTheme: initialTheme(),
  explodeAmount: 0,
  explodePlaying: false,
  // Switching variant swaps in a different physical product — its twin state
  // (a pressed switch, accumulated cycles) must not leak into the new one.
  setVariantId: (id) =>
    set({
      variantId: id,
      selectedComponentId: null,
      selectedRequirementId: null,
      actuated: false,
      vibration: false,
      cycles: 0,
      explodeAmount: 0,
      explodePlaying: false,
    }),
  setSelectedComponentId: (id) => set({ selectedComponentId: id }),
  setSelectedRequirementId: (id) => set({ selectedRequirementId: id }),
  setActuated: (on) => set({ actuated: on }),
  setVibration: (on) => set({ vibration: on }),
  setCycles: (n) => set({ cycles: n }),
  setBodyOpacity: (v) => set({ bodyOpacity: v }),
  setViewerBg: (bg) => set({ viewerBg: bg }),
  setUiTheme: (theme) => {
    applyTheme(theme);
    set({ uiTheme: theme });
  },
  setExplodeAmount: (v) => set({ explodeAmount: v }),
  setExplodePlaying: (on) => set({ explodePlaying: on }),
}));

// Bench-local DUT state (encoder rotation). Lives here rather than in
// TestBench.tsx so FSOverlay can share it without a component-module cycle.
interface BenchStore {
  rotating: boolean;
  setRotating: (v: boolean) => void;
}
export const useBenchStore = create<BenchStore>((set) => ({
  rotating: false,
  setRotating: (v) => set({ rotating: v }),
}));
