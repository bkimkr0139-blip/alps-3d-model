import * as THREE from "three";

// Text-in-3D without a font CDN: rasterize a short label into a local canvas
// and use it as an alpha-mapped plane. Shared by the TestBench silkscreen and
// the production-line station signs (extracted from TestBench.silkTexture).

export function canvasTextTexture(
  text: string,
  color = "#e2e8f0",
  opts: { width?: number; height?: number; font?: string } = {}
): THREE.CanvasTexture {
  const { width = 256, height = 64, font = "bold 38px system-ui, sans-serif" } = opts;
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext("2d")!;
  ctx.font = font;
  ctx.fillStyle = color;
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText(text, width / 2, height / 2 + 2);
  return new THREE.CanvasTexture(canvas);
}
