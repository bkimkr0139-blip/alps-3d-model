import * as THREE from "three";

// Text-in-3D without a font CDN: rasterize a short label into a local canvas
// and use it as an alpha-mapped plane. Shared by the TestBench silkscreen and
// the production-line station signs (extracted from TestBench.silkTexture).

export function canvasTextTexture(text: string, color = "#e2e8f0"): THREE.CanvasTexture {
  const canvas = document.createElement("canvas");
  canvas.width = 256;
  canvas.height = 64;
  const ctx = canvas.getContext("2d")!;
  ctx.font = "bold 38px system-ui, sans-serif";
  ctx.fillStyle = color;
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText(text, 128, 34);
  return new THREE.CanvasTexture(canvas);
}
