// Illustrative fatigue model behind the S04 stress time-lapse overlay.
//
// §10.2 forbids invented compliance/judgment numbers, so this is explicitly a
// VISUALIZATION aid, not an engineering prediction: each damage-prone part has
// a hand-picked "cycles to first visible stress" scale, and the overlay shows
// a normalized 0–100% index with a caption saying it is illustrative. Real
// fatigue life stays the mech-model/SPICE runs' job.

// partKind (set by the GLB node-name match in ThreeViewer) → cycles at which
// the part reaches full red. Lower = fatigues sooner.
export const CYCLES_TO_SATURATION: Record<string, number> = {
  dome: 60_000, // snap fatigue → loss of click feel
  contact: 80_000, // contact wear → resistance rise
  solder: 90_000, // solder-joint fatigue under vibration
  terminal: 120_000,
  detent: 150_000,
  plunger: 150_000,
  epoxy: 200_000,
  shaft: 200_000,
  package: 300_000,
  housing: 500_000, // snap-fit ribs are the last to go
};

// Vehicle vibration accelerates fatigue where mass × leverage concentrates:
// solder joints and terminals first (classic vibration failure mode).
const VIBRATION_MULTIPLIER: Record<string, number> = {
  solder: 4,
  terminal: 4,
  detent: 2,
  shaft: 2,
};

export function stressOf(kind: string, cycles: number, vibration: boolean): number {
  const sat = CYCLES_TO_SATURATION[kind];
  if (!sat) return 0;
  const mult = vibration ? (VIBRATION_MULTIPLIER[kind] ?? 1.3) : 1;
  return Math.min(1, (cycles / sat) * mult);
}

// Shared gradient (green → yellow → orange → red) for both the 3D tint and
// the legend bars. Hue 0.33 = green, 0 = red.
export function stressHsl(stress: number): [number, number, number] {
  const s = Math.min(1, Math.max(0, stress));
  const t = Math.min(1, Math.max(0, (s - 0.15) / 0.75));
  return [0.33 * (1 - t), 0.85, 0.5];
}

export function stressCss(stress: number): string {
  const [h, s, l] = stressHsl(stress);
  return `hsl(${Math.round(h * 360)} ${Math.round(s * 100)}% ${Math.round(l * 100)}%)`;
}

// Top stressed kinds for the legend, descending, only those actually under load.
export function rankedStress(
  kinds: Iterable<string>,
  cycles: number,
  vibration: boolean
): { kind: string; stress: number }[] {
  return [...new Set(kinds)]
    .map((kind) => ({ kind, stress: stressOf(kind, cycles, vibration) }))
    .filter((e) => e.stress > 0.001)
    .sort((a, b) => b.stress - a.stress);
}
