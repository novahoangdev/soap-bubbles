import { useMemo } from "react";
import * as THREE from "three/webgpu";
import {
  attribute, vec3, vec4, float, sin, cos, mix, smoothstep, max, dot, pow, normalize, cameraPosition, Fn, uniform, mx_noise_float,
} from "three/tsl";
import { TIME, cloudLight, HAZE } from "./cards";
import { groundAt, SUN_DIR } from "./World";

/**
 * Real 3D grass (no painted cards, so no soft halos): tens of thousands of tapered blades, each its own little curved
 * strip, coloured like a painted lawn — deep cool green at the root, fresh green in the middle, a warm sunlit yellow-green
 * at the tip — with a backlit glow toward the sun, leaning a little, and swaying in coherent waves of wind that sweep
 * across the meadow (the Ghibli grass look).
 *
 * One mesh, InstancedBufferGeometry. Per instance: iRoot (x, y, z, yaw), iShape (height, width, lean, colour variation).
 */
export const WIND = { strength: uniform(1.0), dir: new THREE.Vector3(0.85, 0, 0.35).normalize() };

const blade = () => {
  // 5 levels × 3 vertices + a tip: a tapered strip, widest a little above the root, folded along its midrib (the middle
  // column sits forward of the edges, z in units of the blade width). (g32: flat ribbons read as cut green paper.)
  const pos: number[] = [], idx: number[] = [];
  const L = 5;
  for (let i = 0; i < L; i++) {
    const y = i / L;
    const w = 0.5 * (1 - Math.pow(y, 1.4)) * (0.75 + 0.25 * Math.sin(Math.PI * Math.min(1, y * 2.2)));
    pos.push(-w, y, 0, 0, y, w * 0.45, w, y, 0);
  }
  pos.push(0, 1, 0);
  for (let i = 0; i < L - 1; i++) {
    const a = i * 3, b = a + 3;
    idx.push(a, a + 1, b, a + 1, b + 1, b, a + 1, a + 2, b + 1, a + 2, b + 2, b + 1);
  }
  const a = (L - 1) * 3, t = L * 3;
  idx.push(a, a + 1, t, a + 1, a + 2, t);
  const g = new THREE.InstancedBufferGeometry();
  g.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
  g.setIndex(idx);
  return g;
};

const rng = (seed: number) => () => ((seed = (seed * 16807) % 2147483647) / 2147483647);

export function Grass({ count = 380000 }: { count?: number }) {
  const mesh = useMemo(() => {
    const g = blade();
    const R = new Float32Array(count * 4), S = new Float32Array(count * 4);
    const r = rng(777);
    let n = 0;
    for (let i = 0; i < count * 3 && n < count; i++) {
      // dense around the player and along the flight corridor, thinning with distance (the painted lawn carries the rest)
      // a third of the blades go within ~3 m of the camera, so no bare ground shows between them up close
      // a third near the lens, a third over the meadow, a third spread evenly over the far lawn 12–45 m out (the follow
      // shot looked across a bare, flat strip there)
      // band 3: the follow corridor, where the camera flies ~7 m down the meadow after the bubble
      const band = i % 4;
      const z = band === 0 ? 2.4 - Math.pow(r(), 0.8) * 4 : band === 1 ? 3.5 - Math.pow(r(), 1.9) * 46 : band === 2 ? -5 - r() * 53 : 0.5 - r() * 12;
      // the far band also reaches out sideways (the follow camera may look ~70° to the side, over bare lawn)
      const span = band === 2 ? 10 + -z * 0.9 : band === 3 ? 3 + -z * 0.35 : 4 + Math.max(0, -z) * 1.25;
      const x = (r() - 0.5) * 2 * span;
      const dist = Math.hypot(x, z - 2.4);
      if (band !== 3 && r() > (band === 2 ? 1.3 - dist / 70 : 1.15 - dist / 45)) continue;
      const corridor = Math.exp(-(x * x) / 40);
      R.set([x, groundAt(x, z) - 0.01, z, r() * Math.PI * 2], n * 4);
      // a short lush lawn under the daisies (v2 0.1–0.21 m read as tall reeds hiding the flowers)
      // the far band shortens toward its outer edge (round 9: it ended on a hard line of blades)
      const edge = band === 2 ? Math.max(Math.abs(x) / span, (-5 - z) / 53) : 0;
      const fadeH = 1 - 0.7 * Math.max(0, (edge - 0.7) / 0.3);
      const h = (0.04 + 0.1 * r() * r() + 0.03 * r()) * (0.9 + 0.3 * corridor) * (1 + Math.min(0.8, dist / 30)) * fadeH;
      // far blades a little wider: sub-pixel blades stair-stepped in the follow shot
      S.set([h, (0.01 + 0.008 * r()) * (1 + Math.min(1.5, dist / 14)), (r() - 0.3) * 0.9, r()], n * 4);
      n++;
    }
    g.setAttribute("iRoot", new THREE.InstancedBufferAttribute(R, 4));
    g.setAttribute("iShape", new THREE.InstancedBufferAttribute(S, 4));
    g.instanceCount = n;

    const iRoot = attribute<"vec4">("iRoot", "vec4");
    const iShape = attribute<"vec4">("iShape", "vec4");
    const p = attribute<"vec3">("position", "vec3");
    const m = new THREE.MeshBasicNodeMaterial({ side: THREE.DoubleSide });
    const y = p.y;
    // each blade twists a little about its own axis on the way up (±0.6 rad: real blades are never flat planes)
    const yaw = iRoot.w.add(iShape.w.mul(7.13).fract().sub(0.5).mul(1.2).mul(y));
    const side = vec3(cos(yaw), 0.0, sin(yaw));
    const fwd = vec3(sin(yaw).negate(), 0.0, cos(yaw));
    const h = iShape.x;
    // wind: waves travelling across the meadow + slower gusts
    const ph = TIME.mul(1.7).sub(iRoot.x.mul(0.33)).sub(iRoot.z.mul(0.21));
    const gust = sin(TIME.mul(0.45).add(iRoot.x.mul(0.06)).add(iRoot.z.mul(0.04))).mul(0.5).add(0.5);
    const wave = sin(ph).mul(0.5).add(0.5);
    const bend = y.mul(y);
    const windAmt = float(0.025).add(wave.mul(0.1).mul(gust.mul(0.7).add(0.3))).mul(WIND.strength).mul(h).mul(bend).mul(1.6);
    // each blade arches over its own way (g32: everything combed one way by the wind read as a hairbrush)
    const lean = fwd.mul(iShape.z.mul(0.55).mul(h).mul(bend));
    const windV = vec3(WIND.dir.x, 0, WIND.dir.z).mul(windAmt);
    const off = lean.add(windV);
    const world = Fn(() => {
      const base = iRoot.xyz.add(side.mul(p.x.mul(iShape.y))).add(fwd.mul(p.z.mul(iShape.y))).add(vec3(0, y.mul(h), 0)).add(off);
      // bending shortens the blade a little
      return base.sub(vec3(0, dot(off, off).sqrt().mul(0.35).mul(y), 0));
    })();
    m.positionNode = world;
    // painted lawn colours
    const v = iShape.w;
    // (linear values: the node colours are linear, sRGB-looking numbers came out pale grey-green)
    // (round 6: lifted; the near-black roots read as holes between the clumps in the follow shot)
    const root = mix(vec3(0.03, 0.065, 0.02), vec3(0.04, 0.075, 0.018), v);
    // (round 13: a touch warmer and less saturated, toward the painted trees)
    const midC = mix(vec3(0.055, 0.15, 0.032), vec3(0.08, 0.175, 0.03), v);
    const tip = mix(vec3(0.4, 0.5, 0.14), vec3(0.5, 0.56, 0.16), v);
    // a few blades drying to straw, a few a cooler blue-green (a lawn is never one green)
    const kind = v.mul(29.1).fract();
    const dry = smoothstep(0.93, 0.95, kind);
    const cool = smoothstep(0.75, 0.77, kind).mul(float(1.0).sub(dry));
    const midK = mix(mix(midC, midC.mul(vec3(0.82, 1.0, 1.25)), cool), vec3(0.2, 0.19, 0.06), dry);
    const tipK = mix(mix(tip, tip.mul(vec3(0.78, 0.95, 1.1)), cool), vec3(0.55, 0.47, 0.2), dry);
    const c1 = mix(root, midK, smoothstep(0.0, 0.55, y));
    const col0 = mix(c1, tipK, smoothstep(0.45, 1.0, y));
    // less saturated with distance (~15 % per 10 m), so the meadow doesn't read as one saturated carpet
    const dsat = smoothstep(4.0, 30.0, iRoot.xyz.sub(cameraPosition).length()).mul(0.25);
    const col = mix(col0, vec3(dot(col0, vec3(0.2126, 0.7152, 0.0722))), dsat);
    // light: blades turned toward the sun are a touch brighter; looking toward the sun the tips glow (backlight)
    const L = vec3(SUN_DIR.x, SUN_DIR.y, SUN_DIR.z);
    const facing = dot(normalize(fwd), normalize(vec3(L.x, 0, L.z))).abs();
    const V = normalize(world.sub(cameraPosition));
    const back = pow(max(dot(V, L), 0.0), 3.0).mul(y).mul(0.35);
    const hz = smoothstep(6.0, 30.0, world.sub(cameraPosition).length()).mul(0.4);
    // per-blade brightness ±8 % (a uniform carpet in the follow shot)
    const jit = float(0.92).add(iShape.w.mul(13.7).fract().mul(0.16));
    // large soft patches of warm ochre and cooler deeper green across the field (±12 %, round 11: one flat green)
    const pn = mx_noise_float(vec3(iRoot.x.mul(0.16), iRoot.z.mul(0.16), 11.0));
    const patch = mix(vec3(0.86, 0.93, 0.95), vec3(1.13, 1.05, 0.82), smoothstep(-0.35, 0.35, pn));
    // the fold: the half of the blade turned toward the sun lighter, the other half in its own shade
    const sunSide = dot(side, normalize(vec3(L.x, 0, L.z)));
    const fold = float(1.0).add(p.x.mul(4.0).clamp(-1.0, 1.0).mul(sunSide).mul(0.14)).add(p.z.mul(0.25));
    m.colorNode = vec4(col.mul(jit).mul(fold).mul(patch).mul(float(0.88).add(facing.mul(0.18))).mul(cloudLight(iRoot.x, iRoot.z)).add(vec3(0.9, 0.85, 0.5).mul(back)), 1.0).rgb;
    // far blades melt into a warm sunlit lawn green, then the haze (pure haze turned them grey-lavender)
    m.colorNode = mix(m.colorNode, mix(vec3(0.2, 0.27, 0.11), HAZE, 0.55), hz);
    const mesh = new THREE.Mesh(g, m);
    mesh.frustumCulled = false;
    return mesh;
  }, [count]);
  return <primitive object={mesh} />;
}
