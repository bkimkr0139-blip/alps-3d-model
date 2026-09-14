import { useMemo } from "react";
import * as THREE from "three";

// The active scenario's finger path (gap ramp → hold → retreat), drawn as a
// line in the scene so the replay playback has a visible trajectory.
export function AirTrajectoryLine({
  points,
  surfaceZ,
}: {
  points: { x_mm: number; y_mm: number; gap_mm: number }[];
  surfaceZ: number;
}) {
  const geometry = useMemo(() => {
    const verts = new Float32Array(points.length * 3);
    points.forEach((p, i) => {
      verts[i * 3] = p.x_mm;
      verts[i * 3 + 1] = surfaceZ + p.gap_mm;
      verts[i * 3 + 2] = -p.y_mm;
    });
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.BufferAttribute(verts, 3));
    return g;
  }, [points, surfaceZ]);

  return (
    <line>
      <primitive object={geometry} attach="geometry" />
      <lineBasicMaterial color="#38bdf8" transparent opacity={0.8} />
    </line>
  );
}
