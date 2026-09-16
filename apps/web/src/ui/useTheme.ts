import { useTwinStore, type UiTheme } from "../store";
import { svgPalette, type SvgMode } from "./tokens";

// Current app chrome theme ("dark" | "light"). Subscribing components
// re-render when the header toggle flips — that is what makes canvas/SVG
// charts (which cannot read CSS variables) repaint in the new palette.
export function useUiTheme(): UiTheme {
  return useTwinStore((s) => s.uiTheme);
}

// Palette of concrete hexes for SVG presentation attributes and hand-rolled
// SVG charts (fill="…" cannot take var()). Pair with useUiTheme().
export function useSvgPalette() {
  return svgPalette[useUiTheme() as SvgMode];
}
