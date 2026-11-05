import { useEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three/webgpu";
import { texture, positionGeometry, normalize, vec2, vec3, clamp, pow, mix, smoothstep, max, dot, uv, vertexColor, positionWorld, cameraPosition, mx_noise_float, exp, float, sin, attribute } from "three/tsl";
import { TIMESCALE } from "../scene/clock";
import { useFrame, useThree } from "@react-three/fiber";
import { cell, makeCards, HAZE, TIME, cloudLight } from "./cards";
import { loadTexture } from "./FiberCanvas";
import { Grass } from "./Grass";
import { Flowers3D } from "./Flowers3D";
import { Petals } from "./Petals";

/**
 * The garden (metres, y up; the player stands near the origin looking along −z), painted-anime look: hand-painted Codex
 * sprites and textures placed in real 3D, so depth and parallax are true. Inspired by painted forest films: a sunlit
 * clearing full of daisies, layers of trees fading into warm haze, soft light.
 *  - sky: the painted gradient, softened toward a warm cream haze at the horizon; fluffy cumulus cards
 *  - meadow: leafy grass clumps + daisies (other flowers sprinkled), denser along the bubbles' flight corridor
 *  - trees: tall trunks with wide painted canopies, a few framing the shot up close, then rows that melt into the haze
 *  - low ground mist between the rows; butterflies that wander and land on flowers
 */
export const GARDEN: { ready: boolean; flowers: boolean; onStart?: () => void } = { ready: false, flowers: false };
// the sun high behind the right shoulder: the meadow is front-lit and the daisies turn their faces toward the viewer
export const SUN_DIR = new THREE.Vector3(0.5, 0.68, 0.53).normalize();
export const FOG_COL = "#e6ecdc";
export const FOG_DENSITY = 0.0105;

/** ground height (m): flat around the player, gentle swells further out */
export const groundAt = (x: number, z: number) =>
  0.16 * Math.sin(x * 0.11 + 1.3) * Math.sin(z * 0.09 + 0.4) + 0.1 * Math.sin(x * 0.27 - z * 0.19) + Math.max(0, Math.abs(x) - 30) * 0.04;

const rng = (seed: number) => () => ((seed = (seed * 16807) % 2147483647) / 2147483647);

const TEX = {
  grass: require("../../assets/garden3d/tex/ground_grass.jpg"),
  tufts: require("../../assets/garden3d/tex/grass_tufts.png"),
  flowers: require("../../assets/garden3d/tex/flowers.png"),
  daisy: require("../../assets/garden3d/tex/daisy_head.png"),
  sky: require("../../assets/garden3d/tex/sky_gradient.jpg"),
  cloudA: require("../../assets/garden3d/tex/cloud_a.png"),
  cloudB: require("../../assets/garden3d/tex/cloud_b.png"),
  cloudC: require("../../assets/garden3d/tex/cloud_c.png"),
  butterfly: require("../../assets/garden3d/tex/butterfly_soft.png"),
  treeA: require("../../assets/garden3d/tex/tree_a.png"),
  treeB: require("../../assets/garden3d/tex/tree_b.png"),
  treeC: require("../../assets/garden3d/tex/tree_c.png"),
  treeline: require("../../assets/garden3d/tex/treeline.png"),
  bushA: require("../../assets/garden3d/tex/bush_a.png"),
  bushB: require("../../assets/garden3d/tex/bush_b.png"),
  petal: require("../../assets/garden3d/tex/petal.png"),
  leaf: require("../../assets/garden3d/tex/leaf_card.png"),
  daisyBlur: require("../../assets/garden3d/tex/daisy_blur.png"),
};
type Tex = Record<keyof typeof TEX, THREE.Texture>;

/** soft round mist puff (procedural) */
const mistTex = () => {
  const n = 64, d = new Uint8Array(n * n * 4);
  for (let y = 0; y < n; y++)
    for (let x = 0; x < n; x++) {
      const u = (x / (n - 1)) * 2 - 1, v = (y / (n - 1)) * 2 - 1;
      const a = Math.max(0, 1 - (u * u + v * v * 3.5));
      const o = (y * n + x) * 4;
      d[o] = d[o + 1] = d[o + 2] = 255;
      d[o + 3] = Math.round(255 * a * a);
    }
  const t = new THREE.DataTexture(d, n, n);
  t.needsUpdate = true;
  return t;
};

function Sky({ map }: { map: THREE.Texture }) {
  const mat = useMemo(() => {
    const m = new THREE.MeshBasicNodeMaterial({ side: THREE.BackSide, depthWrite: false, fog: false });
    const dir = normalize(positionGeometry);
    const h = clamp(dir.y, 0.0, 1.0);
    const c = texture(map, vec2(0.5, clamp(pow(h, 0.7).mul(1.1), 0.01, 0.99))).rgb;
    // calmer than the painted gradient: a little less saturated, melting into the warm haze at the horizon
    const l = dot(c, vec3(0.2126, 0.7152, 0.0722));
    const soft = mix(mix(vec3(l), c, 0.7), vec3(0.78, 0.86, 0.95), 0.12);
    const sun = pow(max(dot(dir, vec3(SUN_DIR.x, SUN_DIR.y, SUN_DIR.z)), 0.0), 10.0).mul(0.25);
    const warm = mix(soft, vec3(0.62, 0.68, 0.74), float(1.0).sub(smoothstep(0.08, 0.45, h)).mul(0.45));
    m.colorNode = mix(HAZE, warm, smoothstep(0.0, 0.32, h)).add(vec3(1.0, 0.95, 0.85).mul(sun));
    return m;
  }, [map]);
  return (
    <mesh material={mat} renderOrder={-10}>
      <sphereGeometry args={[700, 32, 16]} />
    </mesh>
  );
}

function Clouds({ maps }: { maps: THREE.Texture[] }) {
  const items = useMemo(() => {
    const r = rng(77);
    const out: { m: THREE.Texture; p: [number, number, number]; s: [number, number, number] }[] = [];
    const spots = [-1.1, -0.7, -0.35, 0.1, 0.45, 0.8, 1.15, -0.5, 0.3, 0.95];
    spots.forEach((az, k) => {
      const d = 420 + r() * 120;
      const high = k >= 7;
      const w = (high ? 140 : 200) + r() * 120;
      const y = high ? 150 + r() * 80 : 50 + r() * 50;
      out.push({ m: maps[k % 3], p: [Math.sin(az) * d, y + w * 0.2, -Math.cos(az) * d], s: [w, w * 0.5, 1] });
    });
    return out;
  }, [maps]);
  const g = useRef<THREE.Group>(null);
  useFrame(({ clock }) => {
    if (g.current) g.current.rotation.y = clock.elapsedTime * TIMESCALE * 0.0016;
  });
  return (
    <group ref={g}>
      {items.map((c, i) => (
        <sprite key={i} position={c.p} scale={c.s} renderOrder={-9}>
          <spriteMaterial map={c.m} transparent depthWrite={false} fog={false} opacity={0.92} color="#fffaf0" />
        </sprite>
      ))}
    </group>
  );
}

function Ground({ map }: { map: THREE.Texture }) {
  const geo = useMemo(() => {
    const g = new THREE.PlaneGeometry(800, 800, 220, 220);
    g.rotateX(-Math.PI / 2);
    const p = g.attributes.position as THREE.BufferAttribute;
    const uv = g.attributes.uv as THREE.BufferAttribute;
    const col: number[] = [];
    for (let i = 0; i < p.count; i++) {
      const x = p.getX(i), z = p.getZ(i);
      p.setY(i, groundAt(x, z));
      // soft patches of light and tree shade so the lawn isn't one wallpaper; a little darker under the side rows
      const n = 0.5 + 0.25 * Math.sin(x * 0.13 + z * 0.07) + 0.25 * Math.sin(x * 0.05 - z * 0.11 + 2);
      const shade = 1 - 0.28 * Math.exp(-Math.pow((Math.abs(x) - 11) / 5, 2)) * (z < -2 ? 1 : 0);
      const k = (0.74 + 0.2 * n) * shade;
      col.push(k * 0.97, k, k * 0.86);
      uv.setXY(i, x / 3.2, z / 3.2);
    }
    g.setAttribute("color", new THREE.Float32BufferAttribute(col, 3));
    return g;
  }, []);
  const mat = useMemo(() => {
    const m = new THREE.MeshBasicNodeMaterial();
    // painterly variation in the lawn (round 6: the far lawn read as a flat green slab): two octaves of slow noise in
    // brightness, a little less saturated far out
    const nz = mx_noise_float(vec3(positionWorld.x.mul(0.09), positionWorld.z.mul(0.09), 3.0)).mul(0.6).add(mx_noise_float(vec3(positionWorld.x.mul(0.31), positionWorld.z.mul(0.31), 7.0)).mul(0.4));
    const lawn0 = texture(map, uv()).rgb.mul(vertexColor().rgb).mul(float(0.9).add(nz.mul(0.22)));
    const lawn = mix(lawn0, vec3(dot(lawn0, vec3(0.2126, 0.7152, 0.0722))), smoothstep(10.0, 40.0, positionWorld.sub(cameraPosition).length()).mul(0.35));
    const far = smoothstep(10.0, 50.0, positionWorld.sub(cameraPosition).length()).mul(0.45);
    m.colorNode = mix(mix(lawn, vec3(0.085, 0.14, 0.04), 0.5).mul(cloudLight(positionWorld.x, positionWorld.z)), mix(HAZE, vec3(0.16, 0.22, 0.14), 0.55), far);
    return m;
  }, [map]);
  return <mesh geometry={geo} material={mat} />;
}

/** tree trunks (x, z, radius): the follow camera steers around them */
export const TRUNKS: [number, number, number][] = [];
/** daisy heads near the flight corridor (butterflies land on them; filled by Flowers3D) */
export const LANDING: THREE.Vector3[] = [];

function Meadow({ t }: { t: Tex }) {
  const sets = useMemo(() => {
    const r = rng(4242);
    const grass = makeCards(t.tufts, 30000, 0.45);
    const fl = makeCards(t.flowers, 5000, 0.45);
    const far = makeCards(t.daisy, 9000, 0.4);
    const p = new THREE.Vector3();
    const lush = (x: number, z: number) => 0.45 + 0.55 * Math.exp(-(x * x) / 300) * (z > -60 ? 1 : 0.5);
    // grass clumps: a little cooler and less saturated than the raw paintings (they were lime-bright)
    const tint = (): [number, number, number] => {
      const w = r();
      // (round 4: deeper, the far lawn read as a flat lime strip behind the oak in the follow shot)
      return [0.6 + 0.1 * w, 0.68 + 0.08 * r(), 0.56 + 0.08 * w];
    };
    for (let i = 0; i < 26000; i++) {
      const z = -9 - Math.pow(r(), 1.3) * 75;
      const x = (r() - 0.5) * (16 + -z * 1.3);
      if (r() > lush(x, z)) continue;
      // nearer the camera the clumps are smaller (they filled the frame as giant leaves)
      const near = Math.min(1, Math.max(0, (2.6 - z) / 6));
      const s = (0.3 + r() * 0.3) * (1 - 0.35 * near);
      p.set(x, groundAt(x, z) - 0.03, z);
      grass.add(p, s, s * 0.42, cell(4, 2, Math.floor(r() * 4), Math.floor(r() * 2)), { sway: 0.03 * s, tint: tint(), lift: Math.min(0.35, (-9 - z) / 90) });
    }
    grass.done();
    const patches: [number, number, number][] = [];
    for (let i = 0; i < 200; i++) {
      const z = 3 - Math.pow(r(), 1.3) * 70;
      patches.push([(r() - 0.5) * (12 + -z * 1.2), z, 0.8 + r() * 2.4]);
    }
    for (let i = 0; i < 4200; i++) {
      const pc = patches[Math.floor(r() * patches.length)];
      const a = r() * Math.PI * 2, rr = Math.sqrt(r()) * pc[2];
      const x = pc[0] + Math.cos(a) * rr, z = pc[1] + Math.sin(a) * rr;
      const daisy = r() < 0.88;
      // other flowers: every cell of the bottom two rows except the white clover globe (it read as a cotton ball)
      const other = [[0, 2], [1, 2], [2, 2], [3, 2], [0, 3], [1, 3], [3, 3]][Math.floor(r() * 7)];
      const c = daisy ? cell(4, 4, Math.floor(r() * 4), Math.floor(r() * 2)) : cell(4, 4, other[0], other[1]);
      // near and mid flowers are real 3D (Flowers3D): painted ones only far out, where they are small
      if (z > -18) continue;
      const s = 0.2 + r() * 0.13;
      p.set(x, groundAt(x, z) - 0.02, z);
      fl.add(p, s, s, c, { sway: 0.1 * s, tint: [0.9, 0.9, 0.86], lift: Math.min(0.55, 0.2 + (-18 - z) / 60) });
    }
    fl.done();
    for (let i = 0; i < 4000; i++) {
      const z = -12 - Math.pow(r(), 1.4) * 48;
      const x = (r() - 0.5) * (26 + -z * 1.3);
      const s = 0.07 + r() * 0.05;
      // past ~25 m only in loose drifts with grass between (round 16: a white stripe along the treeline)
      if (z < -25 && Math.sin(x * 0.21 + 1.3) * Math.sin(z * 0.17 + 0.4) < 0.1) continue;
      p.set(x, groundAt(x, z) + 0.12 + r() * 0.12, z);
      far.add(p, s, s, [0, 0, 1, 1], { face: true, sway: 0.01, tint: [0.86, 0.87, 0.82], lift: Math.min(0.75, 0.3 + (-10 - z) / 60) });
    }
    far.done();
    return [grass, fl, far];
  }, [t]);
  return (
    <>
      {sets.map((s, i) => (
        <primitive key={i} object={s.mesh} />
      ))}
    </>
  );
}

/**
 * Painted trees (Codex, Ghibli-style whole trees: tree_a tall, tree_b broad, tree_c medium) standing as cards that turn
 * about their trunk toward the camera; bushes at their feet; and behind the clearing, layered strips of painted forest edge
 * (treeline.png) at growing distances, each fainter in the haze: the layered depth of a painted film background.
 */
function Trees({ t }: { t: Tex }) {
  const { sets, strips } = useMemo(() => {
    const r = rng(9001);
    const A = makeCards(t.treeA, 200, 0.5), B = makeCards(t.treeB, 200, 0.5), C = makeCards(t.treeC, 200, 0.5);
    const bushes = [makeCards(t.bushA, 400, 0.5), makeCards(t.bushB, 400, 0.5)];
    const p = new THREE.Vector3();
    const full: [number, number, number, number] = [0, 0, 1, 1];
    // tree card sizes (w, h) per texture at scale 1: the painted trees fill their 1024² canvas differently
    const kinds = [
      { set: A, w: 5.2, h: 10.5 },
      { set: B, w: 10.5, h: 8.8 },
      { set: C, w: 9.0, h: 9.8 },
    ];
    const tree = (x: number, z: number, s: number, kind0 = Math.floor(r() * 3)) => {
      // no poplar right behind the centre of the clearing (round 18: two of them stood there like the same card twice);
      // decided from the position, so the random sequence of every later placement stays the same
      const kind = kind0 === 0 && Math.abs(x) < 9 && z < -30 ? 1 + (Math.abs(Math.round(x * 3.7)) % 2) : kind0;
      const k = kinds[kind];
      const y0 = groundAt(x, z) - 0.15 * s;
      p.set(x, y0, z);
      const sh = 0.9 + r() * 0.15;
      // every tree its own: mirrored at random and ±15 % in height (round 16: two side-by-side poplars read as clones)
      // (hashed from the position, not drawn from r(): extra draws would shift every later placement)
      const hsh = Math.abs(Math.sin(x * 12.9898 + z * 78.233) * 43758.5453) % 1;
      // (poplars, kind 0, vary more: 0.65–1.1)
      // (the two framing trees by the camera keep their painted side: mirrored, the right one showed a dark column)
      const framing = Math.abs(x) < 6 && z > -8;
      const flip = framing || hsh < 0.5 ? 1 : -1, hj = kind === 0 ? 0.65 + ((hsh * 7.31) % 1) * 0.45 : 0.85 + ((hsh * 7.31) % 1) * 0.3;
      // (round 12: the sunlit canopy read a little lime up close: a touch less green, warmer)
      k.set.add(p, flip * k.w * s, k.h * s * hj, full, { sway: 0.06 * s, tint: [sh, sh * 0.95, sh * 0.88], phase: x * 0.3 + z * 0.2 });
      TRUNKS.push([x, z, 0.45 * s]);
    };
    const bush = (x: number, z: number, s0: number) => {
      // sizes 0.55–1.5× and ~25 % left out, sunk a little into the grass (round 19: a row of identical topiary balls);
      // from a position hash so the random sequence of later placements doesn't move
      const hb = Math.abs(Math.sin(x * 37.719 + z * 11.137) * 24634.6345) % 1;
      if (z < -12 && hb < 0.25) {
        r(); // (the two draws a placed bush makes)
        r();
        return;
      }
      const s = s0 * (0.55 + ((hb * 5.13) % 1) * 0.95);
      p.set(x, groundAt(x, z) - 0.05 - 0.25 * s, z);
      const sh = 0.86 + r() * 0.16;
      bushes[r() < 0.5 ? 0 : 1].add(p, 1.6 * s, 1.6 * s, full, { sway: 0.03, tint: [sh, sh, sh * 0.95] });
    };
    // framing trees close by on both sides (their crowns over the top corners of the frame)
    tree(-5.2, -4.2, 0.7, 1);
    tree(5.0, -7.0, 0.75, 2);
    // the edge of the wood along both sides of the clearing, irregular, with bushes at their feet
    for (let k = 0; k < 22; k++) {
      const side = k % 2 ? 1 : -1;
      const z = -8 - k * 2.6 - r() * 3;
      const x = side * (7 + r() * 5 + Math.max(0, -z - 20) * 0.25);
      tree(x, z, 0.75 + r() * 0.45);
      if (r() < 0.8) bush(x - side * (1.5 + r() * 2), z + 1 + r() * 1.5, 0.7 + r() * 0.5);
    }
    // a looser ring of trees all around (seen when the camera turns, and mirrored in the bubbles)
    for (let k = 0; k < 30; k++) {
      const a = 0.9 + (k / 30) * (Math.PI * 2 - 1.8) + (r() - 0.5) * 0.12;
      const d = 18 + r() * 20;
      tree(Math.sin(a) * d, -Math.cos(a) * d, 0.9 + r() * 0.4);
    }
    // the far side of the clearing: trees standing in front of the forest strips
    for (let k = 0; k < 16; k++) {
      const x = -34 + k * 4.4 + (r() - 0.5) * 3, z = -42 - r() * 8;
      tree(x, z, 0.85 + r() * 0.4);
      if (r() < 0.6) bush(x + (r() - 0.5) * 3, z + 2 + r() * 2, 0.8 + r() * 0.5);
    }
    // a mid-ground of bushes 14–30 m out, so the flower field doesn't end in a ruler-straight line at the wood
    for (let k = 0; k < 26; k++) {
      const z = -14 - r() * 16;
      const x = (r() < 0.5 ? -1 : 1) * (2.5 + r() * 12);
      bush(x, z, 0.6 + r() * 0.7);
    }
    // a few small bushes beside the follow path (the camera flies x ≈ 0 … −0.9, z 2 → −5): they slide past the frame
    // edges as it goes, so the flight reads as moving through the garden (round 11: no parallax)
    bush(-1.75, -3.2, 0.42);
    bush(2.05, -5.4, 0.5); // (just outside the home view: x 1.45 sat in it as a dark blob)
    bush(-2.5, -9.5, 0.55); // (round 12: at −7.6 the bubble came to rest right in front of it)
    for (const s of [A, B, C, ...bushes]) s.done();
    // forest-edge strips: arcs of the painted treeline at 55, 80 and 115 m, the farther ones taller and hazier
    const strips: THREE.Mesh[] = [];
    const rows = [
      { R: 55, H: 15, rep: 7, y: -1.5, lift: 0.0 },
      { R: 80, H: 21, rep: 8, y: -2, lift: 0.12 },
      { R: 115, H: 30, rep: 9, y: -2, lift: 0.25 },
    ];
    // each strip shifted along the painting (round 17: the same two poplars stood dead centre in every row)
    const offs = [0.13, 0.41, 0.77];
    for (const [ri, row] of rows.entries()) {
      const tex = t.treeline.clone();
      tex.wrapS = THREE.RepeatWrapping;
      tex.repeat.set(row.rep, 1);
      tex.offset.x = offs[ri];
      tex.needsUpdate = true;
      const m = new THREE.MeshBasicMaterial({ map: tex, side: THREE.DoubleSide, alphaTest: 0.5, color: new THREE.Color(1, 1, 1).lerp(new THREE.Color("#e6ecdc"), row.lift) });
      const g = new THREE.CylinderGeometry(row.R, row.R, row.H, 96, 1, true);
      const mesh = new THREE.Mesh(g, m);
      mesh.position.set(0, groundAt(0, -row.R) + row.y + row.H / 2, 2);
      strips.push(mesh);
    }
    return { sets: [A, B, C, ...bushes], strips };
  }, [t]);
  return (
    <>
      {strips.map((m, i) => (
        <primitive key={`s${i}`} object={m} />
      ))}
      {sets.map((s, i) => (
        <primitive key={i} object={s.mesh} />
      ))}
    </>
  );
}

/** two or three big out-of-focus daisies right in front of the lens, cropped by the bottom edge (as in the reference) */
function Bokeh({ map }: { map: THREE.Texture }) {
  const set = useMemo(() => {
    const s = makeCards(map, 6, 0.5, true);
    const p = new THREE.Vector3();
    const spots: [number, number, number, number][] = [
      // (portrait: at 0.3 m the frame is only ±7 cm wide)
      [-0.04, 0.245, 2.1, 0.068],
    ];
    for (const [x, y, z, w] of spots) {
      p.set(x, y - w / 2, z);
      s.add(p, w, w, [0, 0, 1, 1], { face: true, sway: 0.01, tint: [0.92, 0.89, 0.82] });
    }
    s.done();
    // nearest thing in the frame (bar the wand, off to the right): drawn over the dense near grass
    (s.mesh.material as THREE.Material).depthTest = false;
    s.mesh.renderOrder = 5;
    return s;
  }, [map]);
  return <primitive object={set.mesh} />;
}

/**
 * Sunbeams slanting down through the wood (the sun is high behind-right, so they fall toward the front-left): soft
 * additive planes, a Gaussian across, fading in at the canopy and out at the ground, gently breathing.
 */
function Shafts() {
  const mesh = useMemo(() => {
    const r = rng(91);
    const N = 9;
    const quad = new THREE.PlaneGeometry(1, 1);
    quad.translate(0, -0.5, 0);
    const g = new THREE.InstancedBufferGeometry();
    g.index = quad.index;
    g.setAttribute("position", quad.attributes.position);
    g.setAttribute("uv", quad.attributes.uv);
    g.instanceCount = N;
    const ph = new Float32Array(N);
    const im = new THREE.InstancedMesh(g, undefined as unknown as THREE.Material, N);
    const m = new THREE.Matrix4(), q = new THREE.Quaternion(), e = new THREE.Euler();
    for (let k = 0; k < N; k++) {
      const z = -22 - r() * 26;
      const x = (r() - 0.5) * 34;
      const h = 6 + r() * 3.5;
      e.set(0, (r() - 0.5) * 0.3, -0.42 - r() * 0.12);
      q.setFromEuler(e);
      // (thinner and fainter: a single broad one read as a smudge at phone size)
      m.compose(new THREE.Vector3(x, groundAt(x, z) + h * 0.92, z), q, new THREE.Vector3((1.2 + r() * 2.6) * 0.6, h, 1));
      im.setMatrixAt(k, m);
      ph[k] = r() * 6.28;
    }
    g.setAttribute("iPh", new THREE.InstancedBufferAttribute(ph, 1));
    const mat = new THREE.MeshBasicNodeMaterial({ transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, side: THREE.DoubleSide });
    const u = uv().x.sub(0.5), v = uv().y;
    const across = exp(u.mul(u).mul(-22.0));
    const along = smoothstep(0.0, 0.4, v).mul(smoothstep(1.0, 0.55, v));
    const breathe = sin(TIME.mul(0.35).add(attribute<"float">("iPh", "float"))).mul(0.3).add(0.7);
    mat.colorNode = vec3(1.0, 0.9, 0.68);
    // fading out as the camera comes near (round 15: flying toward the wood the shafts washed the frame milky)
    const near = smoothstep(6.0, 16.0, positionWorld.sub(cameraPosition).length());
    mat.opacityNode = across.mul(along).mul(breathe).mul(float(0.12)).mul(near);
    im.material = mat;
    im.frustumCulled = false;
    im.renderOrder = 2;
    return im;
  }, []);
  return <primitive object={mesh} />;
}

/** low mist lying between the tree rows: big soft transparent puffs */
function Mist() {
  const items = useMemo(() => {
    const r = rng(55);
    const out: { p: [number, number, number]; s: [number, number, number]; o: number; c?: string }[] = [];
    for (let k = 0; k < 22; k++) {
      const z = -46 - r() * 80;
      const x = (r() - 0.5) * 130;
      out.push({ p: [x, groundAt(x, z) + 0.8 + r() * 3, z], s: [10 + r() * 20, 2 + r() * 3, 1], o: 0.18 + r() * 0.3 });
    }
    // a low band of ground haze where the meadow meets the wood (the follow shot showed a hard seam of bare lawn there)
    for (let k = 0; k < 34; k++) {
      const z = -15 - r() * 32;
      const x = (r() - 0.5) * (30 + -z * 0.8);
      out.push({ p: [x, groundAt(x, z) + 0.35 + r() * 0.6, z], s: [6 + r() * 8, 2.2 + r() * 1.6, 1], o: 0.06 + r() * 0.09, c: "#efe8d4" });
    }
    // and a ring of it at the foot of the painted wood, so the lawn melts into the trees instead of meeting them on a line
    for (let k = 0; k < 40; k++) {
      const a = (r() - 0.5) * 3.6, R = 36 + r() * 22;
      const x = Math.sin(a) * R, z = 2.4 - Math.cos(a) * R;
      out.push({ p: [x, groundAt(x, z) + 0.6 + r() * 1.2, z], s: [14 + r() * 14, 4 + r() * 3, 1], o: 0.08 + r() * 0.1, c: "#efe9da" });
    }
    return out;
  }, []);
  const tex = useMemo(() => mistTex(), []);
  return (
    <>
      {items.map((m, i) => (
        <sprite key={i} position={m.p} scale={m.s}>
          <spriteMaterial map={tex} transparent depthWrite={false} opacity={m.o} color={m.c ?? FOG_COL} />
        </sprite>
      ))}
    </>
  );
}

/**
 * Butterflies: they wander over the meadow on lazy curves, and every so often glide down onto a daisy, sit with their wings
 * slowly opening and closing, then flutter off again.
 */
/** a wing: half of the painted top-view butterfly on a quad hinged at the body (x = 0), lying flat, nose toward −z */
const wingGeo = (side: -1 | 1) => {
  const g = new THREE.PlaneGeometry(0.5, 1, 1, 1);
  g.translate(side * 0.25, 0, 0);
  g.rotateX(-Math.PI / 2);
  const uv = g.attributes.uv as THREE.BufferAttribute;
  for (let i = 0; i < uv.count; i++) uv.setX(i, side < 0 ? uv.getX(i) * 0.5 : 0.5 + uv.getX(i) * 0.5);
  return g;
};

/**
 * Butterflies (real 3D: two painted wings hinged at the body, beating fast in flight, slowly opening and closing while
 * they sit): they wander over the daisies in front of the camera, pick a daisy head (LANDING, from Flowers3D) and settle
 * on it for a few seconds, then lift off again.
 */
function Butterflies({ map }: { map: THREE.Texture }) {
  const refs = useRef<{ g: THREE.Group; l: THREE.Mesh; r: THREE.Mesh }[]>([]);
  const { camera } = useThree();
  const geo = useMemo(() => ({ l: wingGeo(-1), r: wingGeo(1) }), []);
  const st = useMemo(() => {
    const r = rng(31);
    // pale per-butterfly tints over a desaturated wing painting: cream, pale lemon, lilac-grey, blush (round 11: identical
    // blue-and-yellow sprites read as stickers)
    const tints = ["#f6e2c0", "#f7e28c", "#cfc2e6", "#f6c9d2", "#e8e2c8", "#f6d9a0", "#c6d4ea"];
    return Array.from({ length: 7 }, (_, i) => ({
      p: new THREE.Vector3((r() - 0.5) * 0.6, 0.3 + r() * 0.2, 0.6 - r() * 3),
      v: new THREE.Vector3(), mode: "fly" as "fly" | "land" | "sit", t: r() * 3, target: new THREE.Vector3(), seed: i * 1.7 + r(),
      yaw: r() * 6.28, size: 0.12 + r() * 0.03, placed: i !== 0,
      mat: new THREE.MeshBasicMaterial({ map, alphaTest: 0.35, side: THREE.DoubleSide, color: tints[i % tints.length] }),
    }));
  }, [map]);
  const tmp = useMemo(() => new THREE.Vector3(), []);
  useFrame(({ clock }, dtRaw) => {
    const dt = Math.min(dtRaw, 1 / 30) * TIMESCALE;
    const tt = clock.elapsedTime * TIMESCALE;
    st.forEach((b, i) => {
      const o = refs.current[i];
      if (!o) return;
      b.t += dt;
      // the first one is already sitting on a daisy close to the lens when the scene opens, and stays a while (user: the
      // butterflies went by before you could look at them)
      if (!b.placed && LANDING.length) {
        let best = 0, bd = 1e9;
        for (let k = 0; k < LANDING.length; k++) {
          const d = LANDING[k].distanceToSquared(tmp.set(0.1, LANDING[k].y, 0.75));
          if (d < bd) { bd = d; best = k; }
        }
        b.target.copy(LANDING[best]);
        b.p.copy(b.target);
        b.mode = "sit";
        b.t = -7;
        b.placed = true;
      }
      let open: number;
      // shy of the lens: when the follow camera sweeps low through the clearing they dart aside (a 15 cm butterfly
      // half a metre from the lens filled the frame)
      tmp.subVectors(b.p, camera.position);
      const near = tmp.length();
      if (near < 1.3) {
        if (b.mode !== "fly") { b.mode = "fly"; b.t = 0; }
        tmp.y = Math.abs(tmp.y) * 0.3;
        b.v.addScaledVector(tmp.normalize(), dt * 9 * (1.3 - near));
      }
      if (b.mode === "fly") {
        // a wandering heading + a bobbing flight, low over the flowers
        const hx = Math.sin(tt * 0.6 + b.seed) + 0.6 * Math.sin(tt * 1.7 + b.seed * 3);
        const hz = Math.cos(tt * 0.5 + b.seed * 2) + 0.6 * Math.sin(tt * 1.3 + b.seed);
        tmp.set(hx, 0, hz).normalize().multiplyScalar(0.55);
        b.v.lerp(tmp, 1 - Math.exp(-dt * 2));
        b.p.addScaledVector(b.v, dt);
        b.p.y += (0.26 + 0.12 * Math.sin(tt * 1.1 + b.seed) - (b.p.y - groundAt(b.p.x, b.p.z))) * dt * 1.5 + Math.sin(tt * 8 + b.seed) * 0.003;
        // stay in the narrow portrait view from home (half-width ≈ 0.22 × distance)
        const half = 0.2 * (2.4 - b.p.z);
        if (Math.abs(b.p.x) > half) b.v.x -= Math.sign(b.p.x) * dt * 3;
        if (b.p.z > 1.0 || b.p.z < -2.2) b.v.z -= Math.sign(b.p.z + 0.6) * dt * 2.5;
        b.yaw = Math.atan2(-b.v.x, -b.v.z);
        open = 0.15 + 1.1 * (0.5 + 0.5 * Math.sin(tt * 17 + b.seed * 5));
        if (b.t > 4 + (b.seed % 3) && LANDING.length) {
          // pick a daisy head nearby to settle on
          let best = 0, bd = 1e9;
          for (let k = 0; k < LANDING.length; k++) {
            const L = LANDING[k];
            // only daisies in view, 1.4–3.4 m from the lens (close enough to read as butterflies on a flower)
            if (Math.abs(L.x) > 0.18 * (2.4 - L.z) || L.z > 1.0 || L.z < -1.0) continue;
            const d = L.distanceToSquared(b.p);
            if (d < bd && d > 0.15) { bd = d; best = k; }
          }
          b.target.copy(LANDING[best]);
          b.mode = "land";
          b.t = 0;
        }
      } else if (b.mode === "land") {
        tmp.subVectors(b.target, b.p);
        const d = tmp.length();
        b.p.addScaledVector(tmp, Math.min(1, dt * (1.2 + 1.5 / Math.max(d, 0.2))));
        if (d > 0.02) b.yaw = Math.atan2(-tmp.x, -tmp.z);
        open = 0.3 + 0.9 * (0.5 + 0.5 * Math.sin(tt * 12 + b.seed));
        if (d < 0.006) { b.mode = "sit"; b.t = 0; }
      } else {
        b.p.copy(b.target);
        // sitting: wings slowly open and close (sunning), now and then a tiny turn
        // wings held up in a V (flat on the flower they read as stickers), slowly opening and closing
        open = 0.75 + 0.6 * Math.pow(0.5 + 0.5 * Math.sin(tt * 1.6 + b.seed), 2);
        b.yaw += Math.sin(tt * 0.7 + b.seed) * dt * 0.3;
        if (b.t > 3 + (b.seed % 3)) { b.mode = "fly"; b.t = 0; b.v.set(Math.sin(b.seed), 0.5, Math.cos(b.seed)).multiplyScalar(0.5); }
      }
      // hard bounds: never off over the meadow toward the wood (round 10: one hovered at the tree line, as big as a near one)
      b.p.x = THREE.MathUtils.clamp(b.p.x, -2.2, 2.2);
      b.p.z = THREE.MathUtils.clamp(b.p.z, -3.2, 1.4);
      o.g.position.copy(b.p);
      // the follow camera moves faster than they can dodge: one that is still right at the lens isn't drawn
      o.g.visible = near > 1.2;
      o.g.rotation.set(b.mode === "fly" ? -0.25 : 0, b.yaw, 0, "YXZ");
      o.g.scale.setScalar(b.size);
      o.l.rotation.z = -open;
      o.r.rotation.z = open;
    });
  });
  return (
    <>
      {st.map((b, i) => (
        <group
          key={i}
          ref={(g) => {
            if (g) refs.current[i] = { g, l: g.children[0] as THREE.Mesh, r: g.children[1] as THREE.Mesh };
          }}
        >
          <mesh geometry={geo.l} material={b.mat} />
          <mesh geometry={geo.r} material={b.mat} />
        </group>
      ))}
    </>
  );
}

export function World() {
  const [t, setT] = useState<Tex | null>(null);
  const { scene } = useThree();
  useEffect(() => {
    let live = true;
    (async () => {
      const keys = Object.keys(TEX) as (keyof typeof TEX)[];
      const list = await Promise.all(keys.map((k) => loadTexture(TEX[k], { repeat: k === "grass" })));
      if (!live) return;
      const out = {} as Tex;
      keys.forEach((k, i) => (out[k] = list[i]));
      setT(out);
    })().catch((e) => console.error("GARDEN3D_TEX_FAIL", e));
    return () => {
      live = false;
    };
  }, []);
  useEffect(() => {
    scene.fog = new THREE.FogExp2(FOG_COL, FOG_DENSITY);
    scene.background = new THREE.Color(FOG_COL);
  }, [scene]);
  useEffect(() => {
    if (!t) return;
    GARDEN.ready = true;
    console.log("GARDEN3D_TEX");
  }, [t]);
  useFrame((_, dt) => {
    TIME.value += Math.min(dt, 1 / 30) * TIMESCALE;
  });
  if (!t) return null;
  return (
    <>
      <Sky map={t.sky} />
      <Clouds maps={[t.cloudA, t.cloudB, t.cloudC]} />
      {/* only the wand is lit (everything else is painted) */}
      <hemisphereLight args={["#fff6e6", "#9cc27e", 1.6]} />
      <directionalLight position={[SUN_DIR.x * 50, SUN_DIR.y * 50, SUN_DIR.z * 50]} intensity={2.0} color="#fff0d6" />
      <Ground map={t.grass} />
      <Mist />
      <Shafts />
      <Trees t={t} />
      <Grass />
      <Flowers3D />
      <Meadow t={t} />
      <Butterflies map={t.butterfly} />
      <Petals petal={t.petal} leaf={t.leaf} />
      <Bokeh map={t.daisyBlur} />
    </>
  );
}
