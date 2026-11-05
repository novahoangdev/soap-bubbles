 
import * as THREE from "three/webgpu";
import {
  attribute, uniform, cubeTexture, positionGeometry, positionWorld, normalWorld, cameraPosition, normalize, dot, clamp, max, min,
  float, vec3, vec4, mix, smoothstep, reflect, fwidth, pow, exp, acos, abs, Fn, If, varying, normalView, positionView,
} from "three/tsl";
import { filmRGB, filmThickness, vnoise3 } from "./filmGLSL";
import { TIME } from "./cards";

/**
 * Soap bubbles in the painted garden (one InstancedMesh per surface: back faces first, then the front).
 * The film is the real spectral thin-film model (filmGLSL.ts) mirroring a cube map of the garden; on top, to sit in a
 * painted world, an anime-style highlight: a soft-edged white window and a small dot, like the bubbles in hand-painted
 * backgrounds. Mostly clear: colour gathers at the rim (Fresnel) and in the thinning top.
 *
 * Per instance: instanceMatrix (position, radius, wobble stretch),
 *   iData = (age 0…1, seed, thickness scale, pop progress: < 0 intact, else the hole's angular radius in rad)
 *   iPop  = where the film tore (unit vector, bubble frame)
 * Output premultiplied: rgb = reflected light, alpha = what the film takes from the scene behind.
 */
export const ENV = { map: null as THREE.CubeTexture | null };
export const ENV_GAIN = uniform(0.48);
/** 0 at home, 1 while the camera follows a bubble: the hero then shows more film colour and a firmer rim (round 10: it
 *  almost vanished against the bright mist, the main character missing from the best shot) */
export const FOLLOW = uniform(0);
export const SUN = uniform(new THREE.Vector3(0.45, 0.62, -0.64).normalize());

export const makeBubbleMaterial = (env: THREE.Texture, side: "front" | "back") => {
  const m = new THREE.MeshBasicNodeMaterial({
    transparent: true,
    depthWrite: false,
    side: side === "front" ? THREE.FrontSide : THREE.BackSide,
    blending: THREE.CustomBlending,
    blendSrc: THREE.OneFactor,
    blendDst: THREE.OneMinusSrcAlphaFactor,
    blendSrcAlpha: THREE.OneFactor,
    blendDstAlpha: THREE.OneMinusSrcAlphaFactor,
    fog: false,
  });
  const sgn = side === "front" ? 1 : -1;
  const iData = attribute<"vec4">("iData", "vec4");
  const iPop = attribute<"vec3">("iPop", "vec3");
  const vData = varying(iData);
  const vPop = varying(iPop);
  const vObj = varying(positionGeometry);
   
  const shade: any = Fn(() => {
    const V = normalize(positionWorld.sub(cameraPosition));
    const N = normalize(normalWorld).mul(sgn);
    const c = clamp(dot(N, V.negate()), 0.0, 1.0);
    const s = normalize(vObj);
    const age = vData.x, seed = vData.y, th = vData.z, popA = vData.w;
    const d: any = filmThickness({ s, a: age, t: TIME.mul(1.3), seed, th });
    const sd = min(fwidth(d).mul(1.2).add(4.0), 600.0);
    const rf: any = filmRGB({ d, c: max(c, 0.03), sd }).toVar();
    const R = reflect(V, N);
    const E = cubeTexture(env as THREE.CubeTexture, vec3(R.x, R.y.negate(), R.z)).bias(float(1.2)).rgb.mul(ENV_GAIN).toVar();
    const lE = dot(E, vec3(0.2126, 0.7152, 0.0722));
    const grey = rf.r.add(rf.g).add(rf.b).div(3.0);
    // a delicate film: the colours a touch softer than the physics (they read as neon against the painted garden)
    const rfw = mix(rf, vec3(grey), smoothstep(0.8, 4.0, lE).mul(0.5).add(0.5).mul(float(1.0).sub(FOLLOW.mul(0.45))));
    // (art director round 1) about 90 % clear: the film shows mostly toward the rim (Fresnel), the middle is a faint veil
    const edge = mix(float(0.2), float(1.0), pow(float(1.0).sub(c), 1.6));
    // (following: the swirl in the top third shows more, the lower half stays clear)
    const L = rfw.mul(E).mul(edge).mul(float(1.0).add(FOLLOW.mul(0.8)).add(FOLLOW.mul(1.2).mul(smoothstep(0.2, 0.7, s.y)))).toVar();
    // the body barely darkens what is behind it (small bubbles read as dirty smudges at 0.6)
    // (0.35 at home: the little bubbles vanished against the white daisies)
    const a = grey.mul(float(0.45).add(FOLLOW.mul(0.1))).mul(edge).toVar();
    if (side === "back") {
      // (round 5: the inside of the lower film mirrored the sky as a dark blue blotch)
      L.mulAssign(0.12);
      a.mulAssign(0.12);
    } else {
      // painted highlight (front only): one soft round sun glint up-right toward the sun, a faint echo low left
      // (the window highlights of rounds 1–2 read as a studio softbox / an app icon in a sunny meadow)
      const nv = normalize(normalView);
      const wx = nv.x.sub(0.3), wy = nv.y.sub(0.4);
      const win = smoothstep(0.075, 0.0, wx.mul(wx).add(wy.mul(wy)).sqrt()).pow(1.5);
      const wx2 = nv.x.add(0.32), wy2 = nv.y.add(0.38);
      const win2 = smoothstep(0.06, 0.0, wx2.mul(wx2).add(wy2.mul(wy2)).sqrt()).mul(0.18);
      // a thin bright crescent along the rim, brightest on the sun side
      const rim = smoothstep(0.22, 0.0, c).mul(0.4).mul(dot(nv.xy, vec3(0.6, 0.8, 0).xy).mul(0.5).add(0.5));
      const hi = win.mul(float(0.75).add(FOLLOW.mul(0.25))).add(win2).add(rim.mul(float(1.6).add(FOLLOW.mul(0.5))));
      L.addAssign(vec3(1.0, 0.99, 0.95).mul(hi));
      a.assign(max(a, hi.mul(0.9)));
    }
    // black film is transparent, only a faint veil
    a.assign(max(a, float(0.04).mul(float(1.0).sub(smoothstep(25.0, 70.0, d)))));
    // popping: film only beyond the torn hole, a thin beaded rim at its edge
    If(popA.greaterThanEqual(0.0), () => {
      const ang = acos(clamp(dot(s, normalize(vPop)), -1.0, 1.0));
      const e = popA.add(vnoise3({ p: s.mul(4.5).add(seed.mul(7.0)) }).sub(0.5).mul(0.12));
      const keep = smoothstep(e.sub(0.02), e.add(0.05), ang);
      const bead = smoothstep(0.45, 0.75, vnoise3({ p: s.mul(24.0).add(seed) })).mul(0.95).add(0.35);
      const rimP = exp(pow(ang.sub(e).div(0.035), 2.0).negate()).mul(bead);
      L.assign(L.mul(keep).add(E.mul(0.08).add(0.12).mul(rimP)));
      a.assign(a.mul(keep).add(rimP.mul(0.12)));
    });
    // gentle roll-off of what clips (keeps the painted highlight white, not neon)
    const mx = max(L.r, max(L.g, L.b));
    L.assign(mix(L, vec3(mx), smoothstep(0.75, 2.4, mx)));
    return vec4(L, clamp(a, 0.0, 1.0));
  })();
  m.colorNode = shade.rgb;
  m.opacityNode = shade.a;
  void abs; void positionView;
  return m;
};
