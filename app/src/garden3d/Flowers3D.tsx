import { useEffect, useState } from "react";
import { Image } from "react-native";
import * as THREE from "three/webgpu";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { attribute, positionLocal, vertexColor, normalWorld, normalize, dot, max, min, vec2, vec3, float, sin, mix, smoothstep, pow, cameraPosition, positionWorld, texture, uv, step, floor, clamp, fwidth } from "three/tsl";
import { TIME, cloudLight, HAZE } from "./cards";
import { loadTexture } from "./FiberCanvas";
import { groundAt, SUN_DIR, LANDING, GARDEN } from "./World";

/**
 * Real 3D flowers near the camera (Blender props, assets/garden3d/models/*.glb: vertex colours with baked soft occlusion):
 * single daisies and daisy clumps rising above the grass, a few tulip clumps, little mushrooms and stones. Instanced,
 * gently nodding in the same wind as the grass. Painted sprites only stay for the far meadow, where they are tiny.
 */
const MODELS = {
  daisy: require("../../assets/garden3d/models/daisy_single.glb"),
  clump: require("../../assets/garden3d/models/daisy_clump.glb"),
  buttercup: require("../../assets/garden3d/models/buttercup_clump.glb"),
  forget: require("../../assets/garden3d/models/forget_me_not.glb"),
  tulip: require("../../assets/garden3d/models/tulip_clump.glb"),
  mushroom: require("../../assets/garden3d/models/mushroom_red.glb"),
  mushrooms: require("../../assets/garden3d/models/mushroom_pair.glb"),
  stoneA: require("../../assets/garden3d/models/stone_a.glb"),
  stoneC: require("../../assets/garden3d/models/stone_c.glb"),
  poppy: require("../../assets/garden3d/models/poppy_clump.glb"),
  cornflower: require("../../assets/garden3d/models/cornflower.glb"),
  clover: require("../../assets/garden3d/models/clover_clump.glb"),
  parsley: require("../../assets/garden3d/models/cow_parsley.glb"),
};
type Key = keyof typeof MODELS;
const HEADS = require("../../assets/garden3d/tex/daisy_petals.png");

const loadGeo = async (mod: number) => {
  // fetch the bytes ourselves: three's FileLoader needs ProgressEvent, which React Native doesn't have
  const url = Image.resolveAssetSource(mod)!.uri;
  const buf = await (await fetch(url)).arrayBuffer();
  const gltf = await new GLTFLoader().parseAsync(buf, "");
  let geo: THREE.BufferGeometry | null = null;
  gltf.scene.traverse((o) => {
    const m = o as THREE.Mesh;
    if (!geo && m.isMesh) {
      m.updateWorldMatrix(true, false);
      geo = m.geometry.clone().applyMatrix4(m.matrixWorld);
    }
  });
  return geo!;
};

/** soft painted shading on top of the baked vertex colours, a sunlit warm side and a nod in the wind */
const flowerMaterial = (sway: number, keepColour = false, petalTint?: [number, number, number], heads?: THREE.Texture) => {
  const m = new THREE.MeshBasicNodeMaterial();
  const iPhase = attribute<"float">("iPhase", "float");
  const y = positionLocal.y;
  const w = sin(TIME.mul(1.9).add(iPhase)).mul(0.6).add(sin(TIME.mul(3.4).add(iPhase.mul(1.7))).mul(0.4));
  m.positionNode = positionLocal.add(vec3(w.mul(sway).mul(y).mul(y).mul(14.0), 0, w.mul(sway * 0.4).mul(y).mul(y).mul(14.0)));
  const L = vec3(SUN_DIR.x, SUN_DIR.y, SUN_DIR.z);
  const N = normalize(normalWorld);
  const ndl = dot(N, L);
  const lit = smoothstep(-0.3, 0.6, ndl);
  const V = normalize(cameraPosition.sub(positionWorld));
  const rim = pow(max(float(1.0).sub(dot(N, V).abs()), 0.0), 3.0).mul(0.18);
  const vc = vertexColor().rgb;
  // white petals: cream in the light, a soft grey-violet in shade; the orange centres pushed to a warm yellow (#F2C230)
  const lum = dot(vc, vec3(0.2126, 0.7152, 0.0722));
  const sat = max(vc.r, max(vc.g, vc.b)).sub(min(vc.r, min(vc.g, vc.b)));
  // (wildflowers keep their own painted colours: only the daisies are remapped)
  const petal = keepColour ? float(0) : smoothstep(0.3, 0.55, lum).mul(smoothstep(0.32, 0.14, sat));
  const orange = keepColour ? float(0) : smoothstep(0.35, 0.6, vc.r.sub(vc.b)).mul(smoothstep(0.15, 0.35, vc.r.sub(vc.g)));
  // green parts (stems, leaves): a deep lawn green that darkens toward the root, so stems sink into the grass instead of
  // reading as bright mint straws
  const green = smoothstep(0.02, 0.1, vc.g.sub(max(vc.r, vc.b))).mul(float(1.0).sub(petal));
  const stemC = mix(vec3(0.02, 0.07, 0.015), vec3(0.11, 0.24, 0.04), smoothstep(0.0, 0.12, y));
  let base = mix(vc, stemC, green.mul(0.9));
  base = mix(base, vec3(0.64, 0.4, 0.06), orange.mul(0.85));
  // petals keep the baked base-to-tip shading (#D8D1BF at the heart → #F7F3EA at the tips), lit warm, shaded lavender
  base = mix(base, vc.mul(mix(vec3(0.8, 0.78, 0.82), vec3(1.06, 1.03, 0.95), lit)).mul(petalTint ? vec3(...petalTint) : vec3(1.0)), petal.mul(0.9));
  const shadeC = mix(vec3(0.8, 0.86, 0.94), vec3(1.06, 1.03, 0.97), lit);
  // aerial haze: the far flowers melt into the painted wood's air instead of ending in a crisp white band
  const dist = positionWorld.sub(cameraPosition).length();
  const hz = smoothstep(5.0, 24.0, dist).mul(0.66);
  // each flower its own petal white (0.88–1.0, round 12: a stamped field), dimmer far out (a white wall at the bushes)
  const pv = mix(float(0.86), float(0.98), iPhase.mul(7.31).fract());
  const far = float(1.0).sub(smoothstep(12.0, 28.0, dist).mul(0.38));
  let col = base.mul(mix(float(1.0), pv, petal)).mul(mix(shadeC, vec3(1.0), petal.mul(0.85)));
  if (heads) {
    // the daisy heads: painted petals and florets (tools/paint_daisy.py, a 2 × 2 atlas of four heads, one per flower),
    // cut out by their alpha; stems and leaves carry uv (−1, −1). (glTF uv is v-down; the atlas is loaded flipY.)
    const hv = uv();
    const isHead = step(-0.5, hv.x);
    const cellI = floor(iPhase.mul(3.17).fract().mul(4.0));
    const cx = cellI.mod(2.0), cy = floor(cellI.mul(0.5));
    const auv = vec2(cx.add(clamp(hv.x, 0.0, 1.0)).mul(0.5), float(1.0).sub(cy.add(1.0).mul(0.5)).add(float(1.0).sub(clamp(hv.y, 0.0, 1.0)).mul(0.5)));
    const tx = texture(heads, auv);
    // baked occlusion (heads in a clump shade each other) from the vertex colour, the painted light kept, the sun on
    // the cup's side and a cool shade on the underside
    const ao = dot(vc, vec3(0.2126, 0.7152, 0.0722)).div(0.96).min(1.0);
    const sunC = mix(vec3(0.8, 0.8, 0.88), vec3(1.05, 1.03, 0.97), lit);
    const headC = tx.rgb.mul(sunC).mul(ao).mul(pv.add(0.06).min(1.0)).mul(petalTint ? mix(vec3(1.0), vec3(...petalTint), smoothstep(0.25, 0.5, uv().sub(0.5).length())) : vec3(1.0));
    col = mix(col, headC, isHead);
    m.opacityNode = mix(float(1.0), clamp(tx.a.sub(0.5).div(max(fwidth(tx.a).mul(2.0), 1e-4)).add(0.5), 0.0, 1.0), isHead);
    m.alphaToCoverage = true;
  }
  m.colorNode = mix(col.mul(cloudLight(positionWorld.x, positionWorld.z)).mul(far).add(vec3(1.0, 0.97, 0.9).mul(rim)), HAZE, hz);
  return m;
};

const rng = (seed: number) => () => ((seed = (seed * 16807) % 2147483647) / 2147483647);

export function Flowers3D() {
  const [geos, setGeos] = useState<{ g: Record<Key, THREE.BufferGeometry>; heads: THREE.Texture } | null>(null);
  useEffect(() => {
    let live = true;
    (async () => {
      const keys = Object.keys(MODELS) as Key[];
      const [list, heads] = await Promise.all([Promise.all(keys.map((k) => loadGeo(MODELS[k]))), loadTexture(HEADS)]);
      if (!live) return;
      const out = {} as Record<Key, THREE.BufferGeometry>;
      keys.forEach((k, i) => (out[k] = list[i]));
      setGeos({ g: out, heads });
      GARDEN.flowers = true;
      console.log("GARDEN3D_FLOWERS");
    })().catch((e) => console.error("GARDEN3D_GLB_FAIL", String(e)));
    return () => {
      live = false;
    };
  }, []);
  if (!geos) return null;
  return <FlowerField geos={geos.g} heads={geos.heads} />;
}

function FlowerField({ geos, heads }: { geos: Record<Key, THREE.BufferGeometry>; heads: THREE.Texture }) {
  const [meshes] = useState(() => {
    const r = rng(2024);
    const out: THREE.InstancedMesh[] = [];
    const place = (key: Key, n: number, pick: () => [number, number] | null, scale: [number, number], sway: number, tilt = 0.25, keep = false, tint?: [number, number, number]) => {
      const g = geos[key].clone();
      const ph = new Float32Array(n);
      const im = new THREE.InstancedMesh(g, flowerMaterial(sway, keep, tint, key === "daisy" || key === "clump" ? heads : undefined), n);
      const m = new THREE.Matrix4(), q = new THREE.Quaternion(), e = new THREE.Euler(), s = new THREE.Vector3(), p = new THREE.Vector3();
      let k = 0;
      for (let i = 0; i < n * 4 && k < n; i++) {
        const xz = pick();
        if (!xz) continue;
        const [x, z] = xz;
        let sc = scale[0] + r() * (scale[1] - scale[0]);
        // mid and far daisies a little smaller (tall stems poked above the mist at the horizon)
        if (z < -8) sc *= 0.6 + r() * 0.45;
        // near the lens a head at eye height is seen edge-on as a flat disc: keep the closest ones below ~0.27 m
        // heads stay below the lens (0.36 m): near ones well below, none at eye level within 12 m (one tall daisy clump
        // stood above the whole field into the bushes). Model heights: single daisy 0.138 m, clump 0.246 m.
        const H = key === "clump" ? 0.246 : key === "daisy" ? 0.138 : 0.17;
        const dh = Math.hypot(x, z - 2.4);
        if (dh < 3) sc = Math.min(sc, (0.2 + r() * 0.06) / H);
        else if (dh < 12) sc = Math.min(sc, 0.27 / H);
        // thinning out toward the far edge of the field
        if (z < -14 && r() < (-14 - z) / 18) continue;
        p.set(x, groundAt(x, z) - 0.01, z);
        e.set((r() - 0.5) * tilt, r() * Math.PI * 2, (r() - 0.5) * tilt);
        q.setFromEuler(e);
        if (key === "daisy" || key === "clump" || key === "buttercup" || key === "poppy" || key === "cornflower") {
          // turn toward the sun: tip the whole flower ~30° toward +z (the viewer), after its random spin
          const toward = new THREE.Quaternion().setFromEuler(new THREE.Euler(0.08 + r() * 0.4, 0, (r() - 0.5) * 0.6));
          q.premultiply(toward);
          // never more than ~55° from facing the home camera (edge-on heads read as white saucers)
          const n = new THREE.Vector3(0, 1, 0).applyQuaternion(q);
          const toCam = new THREE.Vector3(-x, 0.36 - p.y, 2.4 - z).normalize();
          const c = n.dot(toCam);
          // (about one in six keep their own tilt: an all-facing field read as wallpaper)
          if (c < 0.6) {
            const want = n.clone().lerp(toCam, 0.4 + r() * 0.3).normalize();
            q.premultiply(new THREE.Quaternion().setFromUnitVectors(n, want));
          }
        }
        s.set(sc, sc, sc);
        m.compose(p, q, s);
        im.setMatrixAt(k, m);
        ph[k] = r() * 6.28 + x * 0.4 + z * 0.25;
        if (key === "daisy" && z > -6 && z < 1.6 && Math.abs(x) < 2.5 && LANDING.length < 400) LANDING.push(new THREE.Vector3(0.012, 0.139, -0.004).applyMatrix4(m)); // the head, through the flower's tilt
        k++;
      }
      im.count = k;
      g.setAttribute("iPhase", new THREE.InstancedBufferAttribute(ph, 1));
      im.instanceMatrix.needsUpdate = true;
      im.frustumCulled = false;
      out.push(im);
    };
    // daisies grow in patches, most of them in the lush corridor ahead
    const patches: [number, number, number][] = [];
    // small clumps of daisies with bare grass between them (an even scatter read as wallpaper)
    for (let i = 0; i < 300; i++) {
      // out to ~38 m, so the follow shot crosses flowers all the way to the mist (they thin out with distance)
      const z = 2.6 - Math.pow(r(), 1.25) * 40;
      patches.push([(r() - 0.5) * (6 + -z * 1.5), z, 0.22 + r() * 0.75]);
    }
    const inPatch = (): [number, number] => {
      const pc = patches[Math.floor(r() * patches.length)];
      const a = r() * Math.PI * 2, rr = Math.sqrt(r()) * pc[2];
      return [pc[0] + Math.cos(a) * rr, pc[1] + Math.sin(a) * rr];
    };
    // not right under the camera's nose
    const away = (f: () => [number, number] | null) => () => {
      const xz = f();
      if (!xz) return null;
      return Math.hypot(xz[0], xz[1] - 2.4) < 0.7 ? null : xz;
    };
    // heads at least ~11 cm apart (three heads stacked into one white mush)
    const taken = new Set<string>();
    const spaced = (f: () => [number, number] | null) => (): [number, number] | null => {
      const xz = f();
      if (!xz) return null;
      const gx = Math.round(xz[0] / 0.11), gz = Math.round(xz[1] / 0.11);
      for (let i = -1; i <= 1; i++) for (let j = -1; j <= 1; j++) if ((i || j) && taken.has(`${gx + i},${gz + j}`) && Math.abs(i) + Math.abs(j) === 1) return null;
      if (taken.has(`${gx},${gz}`)) return null;
      taken.add(`${gx},${gz}`);
      return xz;
    };
    // (art director: tulips, rocks and dotted mushrooms read as toy props; dropped)
    place("daisy", 3000, away(spaced(inPatch)), [1.0, 2.6], 0.012, 0.38);
    place("clump", 300, away(inPatch), [1.0, 1.7], 0.01, 0.35);
    // and a loose scatter between the patches, so the meadow under a follow shot is never bare lawn
    const scatter = (): [number, number] => {
      const z = 2.2 - Math.pow(r(), 0.9) * 40;
      return [(r() - 0.5) * (5 + -z * 1.6), z];
    };
    place("daisy", 420, away(spaced(scatter)), [0.9, 2.0], 0.012, 0.5);
    // a few other wildflowers among the daisies, in their own small drifts: buttercups and forget-me-not sprigs
    const drift = (spots: [number, number, number][]) => (): [number, number] => {
      const pc = spots[Math.floor(r() * spots.length)];
      const a = r() * Math.PI * 2, rr = Math.sqrt(r()) * pc[2];
      return [pc[0] + Math.cos(a) * rr, pc[1] + Math.sin(a) * rr];
    };
    const spots = (n: number): [number, number, number][] =>
      Array.from({ length: n }, () => {
        const z = 2.0 - Math.pow(r(), 1.1) * 22;
        return [(r() - 0.5) * (5 + -z * 1.4), z, 0.2 + r() * 0.5];
      });
    // buttercups only within ~12 m (further out they were flat yellow specks hovering over the grass)
    const near12 = (f: () => [number, number] | null) => (): [number, number] | null => {
      const xz = f();
      return xz && xz[1] < -10 ? null : xz;
    };
    // (round 5: smaller, open, fewer near the lens)
    const fewNear = (f: () => [number, number] | null) => (): [number, number] | null => {
      const xz = f();
      return xz && Math.hypot(xz[0], xz[1] - 2.4) < 3 && r() < 0.5 ? null : xz;
    };
    // (round 16: bigger, in a few tight clumps, so the cupped shape reads)
    const tight = (n: number): [number, number, number][] => spots(n).map(([x, z]) => [x, z, 0.12 + r() * 0.14]);
    place("buttercup", 180, away(near12(fewNear(drift(tight(18))))), [1.45, 1.9], 0.012, 0.4, true);
    place("forget", 150, away(fewNear(drift(spots(24)))), [1.5, 2.0], 0.012, 0.25, true);
    // where the follow camera goes (the bubble drifts ahead on the breeze, the camera turns toward the oaks): extra drifts at ~60 % of the home
    // meadow's density, so the follow frames aren't mostly empty grass
    const trail: [number, number, number][] = Array.from({ length: 34 }, () => [-6 + r() * 16, -1 - r() * 12, 0.35 + r() * 0.75]);
    place("daisy", 1500, away(spaced(drift(trail))), [1.0, 2.2], 0.012, 0.5);
    place("daisy", 110, away(spaced(drift(trail))), [0.9, 1.8], 0.012, 0.5, false, [1.0, 0.7, 0.78]);
    // daisy clumps right beside the follow path (x ≈ 0 … −0.5, z 1 → −4): they sweep past the lower corners of the
    // frame as the camera flies (round 14: nothing passed close to the lens)
    let side = 1;
    place("clump", 10, () => {
      side = -side;
      return [-0.25 + side * (0.42 + r() * 0.2), 0.8 - r() * 5];
    }, [1.05, 1.2], 0.01, 0.3);
    place("buttercup", 140, away(drift(trail)), [0.85, 1.3], 0.012, 0.5, true);
    // pale pink daisies in a few drifts of their own (round 10: the meadow wanted ~12 % other flowers)
    // (not right at the lens: a pink one peeked out behind the out-of-focus corner daisy)
    const notNear = (f: () => [number, number] | null) => (): [number, number] | null => {
      const xz = f();
      return xz && Math.hypot(xz[0], xz[1] - 2.4) < 1.3 ? null : xz;
    };
    place("daisy", 380, notNear(spaced(drift(spots(22)))), [0.9, 2.0], 0.012, 0.4, false, [1.0, 0.7, 0.78]);
    // (user, 04/11 evening: "try mixing in a few more kinds of flowers") placed last, so everything above keeps its spot:
    // muted coral poppies and dusty-blue cornflowers in small drifts, low pink clover under the daisies near the lens,
    // and airy cow parsley lace standing at the sides and further back
    place("poppy", 90, notNear(drift(spots(12).map(([x, z]) => [x, z, 0.15 + r() * 0.3] as [number, number, number]))), [1.0, 1.35], 0.012, 0.35, true);
    place("cornflower", 170, notNear(drift(spots(16))), [1.1, 1.5], 0.014, 0.35, true);
    place("clover", 260, notNear(() => {
      const z = 2.0 - Math.pow(r(), 1.3) * 10;
      return [(r() - 0.5) * (4 + -z * 1.2), z];
    }), [0.9, 1.15], 0.006, 0.2, true);
    place("parsley", 70, () => {
      const z = 1.0 - Math.pow(r(), 0.9) * 18;
      const x = (r() < 0.5 ? -1 : 1) * (0.9 + r() * (2 + -z * 0.5));
      return [x, z];
    }, [0.9, 1.3], 0.018, 0.3, true);
    place("poppy", 50, away(drift(trail)), [0.9, 1.25], 0.012, 0.45, true);
    place("cornflower", 60, away(drift(trail)), [1.0, 1.4], 0.014, 0.45, true);
    return out;
  });
  return (
    <>
      {meshes.map((m, i) => (
        <primitive key={i} object={m} />
      ))}
    </>
  );
}
