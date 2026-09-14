import { create } from "zustand";

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
  setVariantId: (id: string) => void;
  setSelectedComponentId: (id: string | null) => void;
  setSelectedRequirementId: (id: string | null) => void;
  setActuated: (on: boolean) => void;
  setVibration: (on: boolean) => void;
  setCycles: (n: number) => void;
  setBodyOpacity: (v: number) => void;
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
    }),
  setSelectedComponentId: (id) => set({ selectedComponentId: id }),
  setSelectedRequirementId: (id) => set({ selectedRequirementId: id }),
  setActuated: (on) => set({ actuated: on }),
  setVibration: (on) => set({ vibration: on }),
  setCycles: (n) => set({ cycles: n }),
  setBodyOpacity: (v) => set({ bodyOpacity: v }),
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
