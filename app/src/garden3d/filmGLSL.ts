 
import { wgslFn as wgslFn0 } from "three/tsl";

// @types/three types wgslFn results too narrowly to pass them as includes or call them with nodes
const wgslFn = (code: string, includes?: any[]): any => (wgslFn0 as any)(code, includes);

/**
 * Soap-film physics for the 3D garden, in WGSL (three.js WebGPU, called from TSL), ported from the Skia shaders
 * (src/shaders/film.ts): spectral thin-film interference at 10 wavelengths through CIE matching, film thickness from
 * gravity drainage + Marangoni swirl + fine filaments, thinning to a black film with age.
 */
const hash31 = wgslFn(`
fn hash31(p0: vec3f) -> f32 {
  var p = fract(p0 * vec3f(0.1031, 0.1030, 0.0973));
  p += dot(p, p.yxz + 33.33);
  return fract((p.x + p.y) * p.z);
}`);

export const vnoise3 = wgslFn(`
fn vnoise3(p: vec3f) -> f32 {
  let i = floor(p);
  var f = fract(p);
  f = f * f * (3.0 - 2.0 * f);
  let a = hash31(i);
  let b = hash31(i + vec3f(1.0, 0.0, 0.0));
  let c = hash31(i + vec3f(0.0, 1.0, 0.0));
  let d = hash31(i + vec3f(1.0, 1.0, 0.0));
  let e = hash31(i + vec3f(0.0, 0.0, 1.0));
  let g = hash31(i + vec3f(1.0, 0.0, 1.0));
  let h = hash31(i + vec3f(0.0, 1.0, 1.0));
  let k = hash31(i + vec3f(1.0, 1.0, 1.0));
  return mix(mix(mix(a, b, f.x), mix(c, d, f.x), f.y), mix(mix(e, g, f.x), mix(h, k, f.x), f.y), f.z);
}`, [hash31]);

const fterm = wgslFn(`
fn fterm(opd: f32, g: f32, lam: f32) -> f32 {
  let k = g / lam;
  return 1.0 - exp(-0.5 * k * k) * cos(opd / lam);
}`);

/** interference colour (linear sRGB reflectance) of a film d nm thick seen at cos(theta) = c, thickness spread sd nm/px */
export const filmRGB = wgslFn(`
fn filmRGB(d: f32, c: f32, sd: f32) -> vec3f {
  let s2 = 1.0 - c * c;
  let ct = sqrt(max(1.0 - s2 / (1.33 * 1.33), 0.0));
  let m = 1.0 - c;
  let F = 0.02 + 0.98 * m * m * m * m * m;
  let opd = 4.0 * 3.14159265 * 1.33 * max(d, 0.0) * ct;
  let g = 4.0 * 3.14159265 * 1.33 * ct * sd;
  var acc = vec3f(0.0);
  acc += vec3f( 0.0206, -0.0183,  0.1295) * fterm(opd, g, 415.0);
  acc += vec3f( 0.0549, -0.0671,  0.6094) * fterm(opd, g, 445.0);
  acc += vec3f(-0.0519,  0.0336,  0.3509) * fterm(opd, g, 475.0);
  acc += vec3f(-0.1652,  0.2274,  0.0439) * fterm(opd, g, 505.0);
  acc += vec3f(-0.1664,  0.4478, -0.0461) * fterm(opd, g, 535.0);
  acc += vec3f( 0.1699,  0.3444, -0.0509) * fterm(opd, g, 565.0);
  acc += vec3f( 0.5364,  0.0885, -0.0272) * fterm(opd, g, 595.0);
  acc += vec3f( 0.4565, -0.0420, -0.0072) * fterm(opd, g, 625.0);
  acc += vec3f( 0.1319, -0.0147, -0.0017) * fterm(opd, g, 655.0);
  acc += vec3f( 0.0134,  0.0005, -0.0004) * fterm(opd, g, 685.0);
  return max(acc, vec3f(0.0)) * 2.0 * F;
}`, [fterm]);

const rotY = wgslFn(`
fn rotY(v: vec3f, a: f32) -> vec3f {
  let c = cos(a);
  let s = sin(a);
  return vec3f(c * v.x + s * v.z, v.y, -s * v.x + c * v.z);
}`);

/** film thickness (nm) at unit-sphere point s (bubble frame, y up), age a (0 fresh … 1 pops), time t, seed, thickness scale */
export const filmThickness = wgslFn(`
fn filmThickness(s: vec3f, a: f32, t: f32, seed: f32, th: f32) -> f32 {
  let lat = s.y;
  let spin = t * (0.35 + 0.25 * fract(seed * 7.13)) + 0.8 * sin(0.25 * t + seed * 6.0) * lat * lat + seed * 10.0;
  let q = rotY(s, spin);
  let w = vec3f(vnoise3(q * 2.1 + seed * 3.0 + t * 0.11), vnoise3(q * 2.1 + 17.0 - t * 0.09), vnoise3(q * 2.1 + 41.0));
  let n1 = vnoise3(q * 2.6 + w * 1.8 + vec3f(0.0, t * 0.25, seed));
  let n2 = vnoise3(q * 6.0 + w * 2.5 - vec3f(t * 0.2, 0.0, 0.0));
  let latW = lat + (n1 - 0.5) * 0.55 + (n2 - 0.5) * 0.12;
  let u = clamp(0.5 - 0.5 * latW, 0.0, 1.0);
  let drain = mix(0.16, 1.0, pow(u, 0.8));
  let young = 1.0 - smoothstep(0.0, 0.35, a);
  let base = mix(520.0, 1150.0, young) * th;
  var d = base * drain * (1.0 + (n2 - 0.5) * 0.18);
  let n4 = vnoise3(q * 13.0 + w * 3.2 + vec3f(0.0, t * 0.4, seed * 2.0));
  d += (n4 - 0.5) * 70.0 * th;
  let zone = smoothstep(0.35, 1.0, a) * smoothstep(-0.35, 0.9, lat);
  d = mix(d, 150.0 + 140.0 * n1, smoothstep(0.0, 0.55, zone));
  let uc = clamp((a - 0.85) / 0.1, 0.0, 1.0);
  let late = smoothstep(0.85, 0.87, a);
  let sr = rotY(s, t * 0.12 + seed * 4.0);
  let n5 = vnoise3(sr * 9.0 + vec3f(-seed * 3.0, t * 0.08, 7.0));
  let capL = 1.0 - 0.36 * pow(max(uc - 0.15, 0.0) / 0.85, 1.4) + (n5 - 0.5) * 0.03;
  let f = lat - capL;
  let cap = smoothstep(0.0, 0.01, f) * late;
  d = mix(d, 165.0 + 40.0 * n1, smoothstep(-0.09, 0.0, f) * (1.0 - cap) * late);
  d = mix(d, 10.0, cap);
  return d;
}`, [rotY, vnoise3]);
