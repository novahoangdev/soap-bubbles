import { useMemo } from "react";
import { useFrame } from "@react-three/fiber";
import * as THREE from "three/webgpu";
import { TIMESCALE } from "../scene/clock";
import { MAXB, type Sim3D } from "./sim3d";
import { GARDEN } from "./World";

/**
 * The mist of a pop: when a film tears, its rim flings a spray of tiny droplets outward (most of them along the tear
 * direction), which glint, slow in the air and fall. A few for a small bubble, a shower for a big one. One instanced
 * mesh of little spheres, unlit and slightly transparent.
 */
const MAXD = 260;

export function Droplets({ sim }: { sim: Sim3D }) {
  const st = useMemo(() => {
    const geo = new THREE.IcosahedronGeometry(1, 1);
    const mat = new THREE.MeshBasicMaterial({ color: "#f6fbff", transparent: true, opacity: 0.6, depthWrite: false });
    const mesh = new THREE.InstancedMesh(geo, mat, MAXD);
    mesh.frustumCulled = false;
    mesh.renderOrder = 7;
    mesh.count = 0;
    const d = Array.from({ length: MAXD }, () => ({ p: new THREE.Vector3(), v: new THREE.Vector3(), age: 1, life: 1, s: 0 }));
    return { mesh, d, prev: new Float32Array(MAXB).fill(-1), next: 0, m: new THREE.Matrix4(), q: new THREE.Quaternion(), sc: new THREE.Vector3(), dir: new THREE.Vector3() };
  }, []);
  useFrame((_, dtRaw) => {
    if (!GARDEN.ready) return;
    const dt = Math.min(dtRaw, 1 / 30) * TIMESCALE;
    // new pops this frame
    for (let i = 0; i < MAXB; i++) {
      const x = sim.b[i];
      const pop = x.alive ? x.pop : -1;
      if (pop >= 0 && st.prev[i] < 0) {
        const n = Math.round(Math.min(40, 4 + x.r * 260));
        for (let k = 0; k < n; k++) {
          const q = st.d[st.next];
          st.next = (st.next + 1) % MAXD;
          // a point on the sphere, biased toward the tear (the rim retracts away from it and throws its liquid outward)
          st.dir.set(Math.random() - 0.5, Math.random() - 0.5, Math.random() - 0.5).normalize().addScaledVector(x.popDir, 0.6).normalize();
          q.p.copy(x.p).addScaledVector(st.dir, x.r);
          q.v.copy(st.dir).multiplyScalar(0.35 + Math.random() * 0.9).addScaledVector(x.v, 0.6);
          q.age = 0;
          q.life = 0.45 + Math.random() * 0.5;
          q.s = (0.0007 + Math.random() * 0.0012) * (0.8 + Math.min(1.2, x.r * 5));
        }
      }
      st.prev[i] = pop;
    }
    let c = 0;
    for (const q of st.d) {
      if (q.age >= q.life) continue;
      q.age += dt;
      q.v.multiplyScalar(Math.exp(-dt * 2.2));
      q.v.y -= 2.4 * dt;
      q.p.addScaledVector(q.v, dt);
      const k = 1 - q.age / q.life;
      st.sc.setScalar(q.s * (0.4 + 0.6 * k));
      st.m.compose(q.p, st.q, st.sc);
      st.mesh.setMatrixAt(c++, st.m);
    }
    st.mesh.count = c;
    st.mesh.instanceMatrix.needsUpdate = true;
  });
  return <primitive object={st.mesh} />;
}
