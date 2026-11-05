import * as THREE from "three/webgpu";
import {
  attribute, uniform, texture, uv, cameraPosition, cameraViewMatrix, vec2, vec3, vec4, float, sin, normalize, cross, abs, clamp,
  log2, max, mix, smoothstep, varying, Fn, If, Discard, select, fwidth, mx_noise_float,
} from "three/tsl";

/**
 * Painted cards: the meadow's grass clumps, flowers, tree foliage are hand-painted sprites (Codex, assets/garden3d/tex/)
 * standing in the 3D garden, turned toward the camera: the look of a painted anime background with real depth and
 * parallax. Unlit (the paintings carry their own light), fogged into the haze by the scene fog.
 *
 * One mesh (InstancedBufferGeometry, a unit quad rooted at its bottom edge) per atlas. Per instance:
 *   iPos  (xyz root position, w = sway phase)
 *   iSize (width, height, sway amplitude, mode: 0 = turns about y only (plants), 1 = faces the camera (foliage))
 *   iUv   (atlas cell: offset u, v, size u, v; v up)
 *   iTint (rgb multiplier, w = lift toward the haze colour)
 * A lens: cards far nearer (or farther) than the focus distance sample a blurrier mip, so the foreground melts like a
 * shallow depth of field (cheap, but it reads as a real lens in a painted frame).
 */
export const LENS = { focus: uniform(3.2), aperture: uniform(5.0) };
export const TIME = uniform(0);
export const HAZE = uniform(new THREE.Color("#e8eedf"));

export type CardSet = {
  mesh: THREE.Mesh;
  add: (p: THREE.Vector3, w: number, h: number, cell: [number, number, number, number], opts?: { sway?: number; face?: boolean; tint?: [number, number, number]; lift?: number; phase?: number }) => void;
  done: () => void;
};

/**
 * Cloud shadows: soft patches of shade drifting slowly across the meadow (shared by the lawn, the grass, the flowers and
 * the plant cards), so the field has light and shade like a sunny day with cumulus. Returns a light multiplier.
 */
 
export const cloudLight = (x: any, z: any) => {
  const n = mx_noise_float(vec3(x.mul(0.035).add(TIME.mul(0.018)), z.mul(0.035).add(TIME.mul(0.008)), 0.0));
  return mix(float(0.78), float(1.04), smoothstep(-0.1, 0.25, n));
};

export const makeCards = (map: THREE.Texture, max_: number, alphaCut = 0.5, soft = false): CardSet => {
  const g = new THREE.InstancedBufferGeometry();
  const quad = new THREE.PlaneGeometry(1, 1);
  quad.translate(0, 0.5, 0);
  g.index = quad.index;
  g.setAttribute("position", quad.attributes.position);
  g.setAttribute("uv", quad.attributes.uv);
  const P = new Float32Array(max_ * 4), S = new Float32Array(max_ * 4), U = new Float32Array(max_ * 4), T = new Float32Array(max_ * 4);
  g.setAttribute("iPos", new THREE.InstancedBufferAttribute(P, 4));
  g.setAttribute("iSize", new THREE.InstancedBufferAttribute(S, 4));
  g.setAttribute("iUv", new THREE.InstancedBufferAttribute(U, 4));
  g.setAttribute("iTint", new THREE.InstancedBufferAttribute(T, 4));

  const iPos = attribute<"vec4">("iPos", "vec4");
  const iSize = attribute<"vec4">("iSize", "vec4");
  const iUv = attribute<"vec4">("iUv", "vec4");
  const iTint = attribute<"vec4">("iTint", "vec4");

  const mat = new THREE.MeshBasicNodeMaterial({ side: THREE.DoubleSide });
  // vertex: billboard around the root, the top sways in the breeze
  const worldPos = Fn(() => {
    const root = iPos.xyz;
    const toCam = cameraPosition.sub(root);
    const face = iSize.w.greaterThan(0.5);
    const fFull = normalize(toCam);
    const fFlat = normalize(vec3(toCam.x, 0.0, toCam.z).add(vec3(1e-4, 0, 0)));
    const f = select(face, fFull, fFlat);
    const right = normalize(cross(vec3(0, 1, 0), f));
    const up = select(face, cross(f, right), vec3(0, 1, 0));
    const h = uv().y;
    const sway = sin(TIME.mul(1.5).add(iPos.w)).add(sin(TIME.mul(3.3).add(iPos.w.mul(2.1))).mul(0.45)).mul(iSize.z).mul(h).mul(h);
    const local = attribute<"vec3">("position", "vec3");
    return root.add(right.mul(local.x.mul(iSize.x).add(sway))).add(up.mul(local.y.mul(iSize.y))).add(vec3(0, 0, sway.mul(0.3)));
  })();
  mat.positionNode = worldPos;
  const viewZ = cameraViewMatrix.mul(vec4(worldPos, 1.0)).z.negate();
  const blur = varying(clamp(log2(abs(float(1.0).div(max(viewZ, 0.05)).sub(float(1.0).div(LENS.focus))).mul(LENS.aperture).add(1.0)), 0.0, 5.0));
  const cuv = varying(iUv.xy.add(uv().mul(iUv.zw)));
  const tint = varying(iTint);
  // crisp painted edges: alpha-to-coverage with the alpha sharpened to about one pixel (MSAA smooths it), no mip-bias blur
  // (v2: the lens blur through mip bias gave haloed fringes and blocky far daisies)
  const c = texture(map, cuv);
  mat.colorNode = mix(c.rgb.mul(tint.rgb), HAZE, tint.w);
  if (soft) {
    // pre-blurred, out-of-focus cards (foreground bokeh daisies): plain alpha blending, no depth writes
    mat.opacityNode = c.a;
    mat.transparent = true;
    mat.depthWrite = false;
  } else {
    mat.opacityNode = clamp(c.a.sub(alphaCut).div(max(fwidth(c.a).mul(2.0), 1e-4)).add(0.5), 0.0, 1.0);
    mat.alphaToCoverage = true;
  }
  void blur; void Fn; void If; void Discard; void smoothstep;
  const mesh = new THREE.Mesh(g, mat);
  mesh.frustumCulled = false;
  let n = 0;
  return {
    mesh,
    add: (p, w, h, c, o = {}) => {
      if (n >= max_) return;
      const t = o.tint ?? [1, 1, 1];
      P.set([p.x, p.y, p.z, o.phase ?? Math.random() * 6.28], n * 4);
      S.set([w, h, o.sway ?? 0, o.face ? 1 : 0], n * 4);
      U.set(c, n * 4);
      T.set([t[0], t[1], t[2], o.lift ?? 0], n * 4);
      n++;
    },
    done: () => {
      g.instanceCount = n;
      for (const k of ["iPos", "iSize", "iUv", "iTint"]) (g.attributes[k] as THREE.BufferAttribute).needsUpdate = true;
    },
  };
};

/** atlas cell (cols × rows, column c, row r counted from the TOP of the image) as a uv rect (v up) */
export const cell = (cols: number, rows: number, c: number, r: number, inset = 0.004): [number, number, number, number] => [
  c / cols + inset,
  1 - (r + 1) / rows + inset,
  1 / cols - 2 * inset,
  1 / rows - 2 * inset,
];

export { vec2 };
