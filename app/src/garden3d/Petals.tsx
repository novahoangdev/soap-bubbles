import { useMemo } from "react";
import * as THREE from "three/webgpu";
import { TIMESCALE } from "../scene/clock";
import { useFrame, useThree } from "@react-three/fiber";
import { makeCards } from "./cards";
import { WIND } from "./Grass";

/**
 * Drifting daisy petals and little leaves in the air around the camera (as in painted films, where a few leaves always
 * float through the light): they ride the breeze, sink slowly, flutter (the card narrows and widens as it spins) and wrap
 * around a box that follows the camera, so there are always a few in view, near and far.
 */
const N = 90;

export function Petals({ petal, leaf }: { petal: THREE.Texture; leaf: THREE.Texture }) {
  const { camera } = useThree();
  const sets = useMemo(() => {
    const a = makeCards(petal, N, 0.5), b = makeCards(leaf, N / 3, 0.5);
    const p = new THREE.Vector3();
    for (let i = 0; i < N; i++) a.add(p, 0.03, 0.03, [0, 0, 1, 1], { face: true });
    for (let i = 0; i < 0; i++) b.add(p, 0.04, 0.04, [0, 0, 1, 1], { face: true, tint: [0.8, 0.9, 0.7] });
    a.done();
    b.done();
    const st = (n: number) =>
      Array.from({ length: n }, () => ({
        p: new THREE.Vector3((Math.random() - 0.5) * 14, 0.12 + Math.random() * 0.75, -Math.random() * 16 + 2),
        ph: Math.random() * 6.28, sp: 0.6 + Math.random() * 0.8, fall: 0.08 + Math.random() * 0.12,
      }));
    return [
      { set: a, st: st(N), size: 0.03 },
      { set: b, st: st(0), size: 0.045 },
    ];
  }, [petal, leaf]);
  useFrame(({ clock }, dtRaw) => {
    const dt = Math.min(dtRaw, 1 / 30) * TIMESCALE;
    const t = clock.elapsedTime * TIMESCALE;
    const cx = camera.position.x, cz = camera.position.z;
    for (const { set, st, size } of sets) {
      const g = set.mesh.geometry as THREE.InstancedBufferGeometry;
      const P = (g.attributes.iPos as THREE.BufferAttribute).array as Float32Array;
      const S = (g.attributes.iSize as THREE.BufferAttribute).array as Float32Array;
      st.forEach((q, i) => {
        q.p.x += (WIND.dir.x * 0.35 + Math.sin(t * 0.9 + q.ph) * 0.15) * dt;
        q.p.z += (WIND.dir.z * 0.35 + Math.cos(t * 0.7 + q.ph) * 0.12) * dt;
        q.p.y += (-q.fall + Math.sin(t * 1.3 + q.ph) * 0.08) * dt;
        // wrap inside a box around the camera (ahead of it mostly)
        if (q.p.y < 0.05) q.p.y += 0.85; // (low: against the open sky they read as white specks)
        if (q.p.x - cx > 7) q.p.x -= 14;
        if (q.p.x - cx < -7) q.p.x += 14;
        if (q.p.z - cz > 2) q.p.z -= 16;
        if (q.p.z - cz < -14) q.p.z += 16;
        const spin = Math.cos(t * q.sp * 3 + q.ph);
        P[i * 4] = q.p.x;
        P[i * 4 + 1] = q.p.y;
        P[i * 4 + 2] = q.p.z;
        // none right at the lens (round 13: a petal 20 cm away read as a white blob)
        const near = Math.hypot(q.p.x - cx, q.p.y - camera.position.y, q.p.z - cz);
        const k = near < 0.6 ? 0 : Math.min(1, (near - 0.6) / 0.4);
        S[i * 4] = size * (0.25 + 0.75 * Math.abs(spin)) * k;
        S[i * 4 + 1] = size * k;
      });
      (g.attributes.iPos as THREE.BufferAttribute).needsUpdate = true;
      (g.attributes.iSize as THREE.BufferAttribute).needsUpdate = true;
    }
  });
  return (
    <>
      {sets.map((s, i) => (
        <primitive key={i} object={s.set.mesh} />
      ))}
    </>
  );
}
