import type { ReactElement } from "react";
import type { FingerPose } from "../../lib/air";
import { RoundedBox } from "@react-three/drei";

// Stylized pointing hand (tap gesture). An earlier bare sphere+cylinder
// fingertip read ambiguously, so the hand now shows the index finger
// extended with the other fingers folded — the pose is unmistakable while
// the PHYSICAL contract is unchanged: the group origin stays at the
// fingertip pad center, gap_mm above the cover, at (x_mm, −y_mm) — exactly
// the pose the solver/surrogate evaluate (field_model constants). Glove
// renders the hand in fabric gray plus a translucent shell (porous-knit
// ε 1.3, disclosed). OOD turns the whole hand red: an out-of-envelope
// surrogate prediction must never read as a normal result (지시서 — 유효범위
// 밖 예측 정상 표시 금지).

const SKIN = "#e8a97e";
const NAIL = "#f4dcc8";
const GLOVE = "#cbd5e1";

type Part = {
  kind: "capsule" | "sphere" | "box";
  // capsule: [radius, length, capSeg, radialSeg] · sphere: [r, w, h] · box: [w, h, d]
  args: number[];
  pos: [number, number, number];
  rot?: [number, number, number];
  scale?: [number, number, number];
  nail?: boolean;
};

// All coordinates are mm in group space: y up from the fingertip pad (y=0),
// +z toward the camera. The index capsule radius mirrors field_model's
// FINGER_R = 5 mm (the radius the solver simulates); it is flattened
// (scale z 0.85) because real fingertips are oval. Geometry tuned via
// three-view preview against the app camera [38, 30, 42].
const PARTS: Part[] = [
  // index finger — extended, pad facing the sensor
  { kind: "capsule", args: [5.0, 16, 8, 20], pos: [0, 13, 0], scale: [1, 1, 0.85] },
  // fingernail on the pad
  { kind: "sphere", args: [3.4, 20, 14], pos: [0, 1.0, 0], scale: [0.8, 0.4, 0.64], nail: true },
  // folded middle / ring / pinky — knuckle row curling under the fist
  { kind: "capsule", args: [3.5, 6.5, 8, 14], pos: [-7.0, 13.5, 3.5], rot: [2.05, 0, -0.08] },
  { kind: "capsule", args: [3.4, 6.0, 8, 14], pos: [-13.0, 13.8, 3.2], rot: [2.05, 0, -0.08] },
  { kind: "capsule", args: [2.9, 5.0, 8, 12], pos: [-18.2, 14.1, 2.9], rot: [2.05, 0, -0.08] },
  // back of hand, sloping up toward the wrist
  { kind: "box", args: [21, 11, 12.5], pos: [-6.5, 23.5, 0.5], rot: [0.22, 0, 0] },
  // no thumb: at this scale it read as a cut-off stub glued to the index
  // (user feedback) — the folded-fingers silhouette alone reads as a hand
  // without the ambiguity.
  // wrist stub receding toward the camera (kept compact for the framing)
  { kind: "capsule", args: [5.0, 7, 8, 16], pos: [-7, 29, 8.5], rot: [0.7, 0, 0] },
];

function handMeshes(mat: ReactElement, nail: boolean) {
  return PARTS.filter((p) => (nail ? p.nail === true : p.nail !== true)).map((p, i) =>
    p.kind === "box" ? (
      <RoundedBox key={i} args={[p.args[0], p.args[1], p.args[2]]} radius={3.5} smoothness={4} position={p.pos} rotation={p.rot} scale={p.scale}>
        {mat}
      </RoundedBox>
    ) : (
      <mesh key={i} position={p.pos} rotation={p.rot} scale={p.scale}>
        {p.kind === "capsule" ? (
          <capsuleGeometry args={p.args as [number, number, number, number]} />
        ) : (
          <sphereGeometry args={p.args as [number, number, number]} />
        )}
        {mat}
      </mesh>
    )
  );
}

export function AirFinger({ pose, ood, surfaceZ }: { pose: FingerPose; ood: boolean; surfaceZ: number }) {
  const tipZ = surfaceZ + pose.gap_mm;
  const x = pose.x_mm;
  const z = -pose.y_mm;
  const solidColor = ood ? "#ef4444" : pose.is_glove ? GLOVE : SKIN;
  const solidMat = <meshStandardMaterial color={solidColor} roughness={0.65} />;
  const nailMat = <meshStandardMaterial color={ood ? "#ef4444" : NAIL} roughness={0.5} />;
  const shellMat = <meshStandardMaterial color="#e2e8f0" transparent opacity={0.35} depthWrite={false} />;
  return (
    <group position={[x, tipZ, z]}>
      {pose.is_glove && (
        // fabric shell: the same hand inflated about the pad, nailless
        <group position={[0, 0.4, 0]} scale={[1.24, 1.06, 1.24]}>
          {handMeshes(shellMat, false)}
        </group>
      )}
      {handMeshes(solidMat, false)}
      {!pose.is_glove && handMeshes(nailMat, true)}
    </group>
  );
}
