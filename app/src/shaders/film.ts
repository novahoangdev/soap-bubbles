/**
 * Shared SkSL for soap films (PLAN section 4).
 *
 * Thin-film interference, two-beam approximation: a film of thickness d (nm), index n = 1.33, seen at incidence cos θ, reflects
 *   R(λ) = 2F (1 − cos δ),  δ = 4π n d cos θₜ / λ
 * (the extra π phase flip on the outer surface is folded in, so d → 0 gives a black film). F is the single-interface Fresnel
 * reflectance (Schlick, F0 = 0.02). R(λ) is evaluated at 10 wavelengths and turned into linear sRGB with weights fitted from the
 * CIE 1931 colour matching functions (Wyman et al. 2013 analytic fit → XYZ → linear sRGB, each channel normalised so a flat
 * spectrum gives white). Thick films (> ~1.5 µm) wash out to a silvery 2F; 100–900 nm gives the classic magenta / green / gold bands.
 */
export const FILM_SKSL = `
const float PI = 3.14159265;
uniform float filmF;        // (v37) swirl scale per look: studio 2.2 (fine contour bands instead of blotches), else 1

float3 srgbEnc(float3 l) {
  l = max(l, float3(0.0));
  return mix(l * 12.92, 1.055 * pow(l, float3(1.0 / 2.4)) - 0.055, step(float3(0.0031308), l));
}
float3 srgbDec(float3 c) {
  return mix(c / 12.92, pow((c + 0.055) / 1.055, float3(2.4)), step(float3(0.04045), c));
}

float hash31(float3 p) {
  p = fract(p * float3(0.1031, 0.1030, 0.0973));
  p += dot(p, p.yxz + 33.33);
  return fract((p.x + p.y) * p.z);
}
float vnoise3(float3 p) {
  float3 i = floor(p);
  float3 f = fract(p);
  f = f * f * (3.0 - 2.0 * f);
  float a = hash31(i);
  float b = hash31(i + float3(1, 0, 0));
  float c = hash31(i + float3(0, 1, 0));
  float d = hash31(i + float3(1, 1, 0));
  float e = hash31(i + float3(0, 0, 1));
  float g = hash31(i + float3(1, 0, 1));
  float h = hash31(i + float3(0, 1, 1));
  float k = hash31(i + float3(1, 1, 1));
  return mix(mix(mix(a, b, f.x), mix(c, d, f.x), f.y), mix(mix(e, g, f.x), mix(h, k, f.x), f.y), f.z);
}

// one wavelength's interference term, averaged over a pixel whose film thickness spreads by sd nm (g = 4π n cos θₜ · sd):
// where the thickness changes faster than a pixel (rims, small bubbles, high orders) the fringes wash out to the mean
float fterm(float opd, float g, float lam) {
  float k = g / lam;
  return 1.0 - exp(-0.5 * k * k) * cos(opd / lam);
}

// interference colour (linear sRGB reflectance) of a film d nm thick seen at cos θ = c, thickness spread sd nm per pixel
float3 filmRGB(float d, float c, float sd) {
  float s2 = 1.0 - c * c;
  float ct = sqrt(max(1.0 - s2 / (1.33 * 1.33), 0.0));
  float m = 1.0 - c;
  float F = 0.02 + 0.98 * m * m * m * m * m;
  float opd = 4.0 * PI * 1.33 * max(d, 0.0) * ct;
  float g = 4.0 * PI * 1.33 * ct * sd;
  float3 acc = float3(0.0);
  acc += float3( 0.0206, -0.0183,  0.1295) * fterm(opd, g, 415.0);
  acc += float3( 0.0549, -0.0671,  0.6094) * fterm(opd, g, 445.0);
  acc += float3(-0.0519,  0.0336,  0.3509) * fterm(opd, g, 475.0);
  acc += float3(-0.1652,  0.2274,  0.0439) * fterm(opd, g, 505.0);
  acc += float3(-0.1664,  0.4478, -0.0461) * fterm(opd, g, 535.0);
  acc += float3( 0.1699,  0.3444, -0.0509) * fterm(opd, g, 565.0);
  acc += float3( 0.5364,  0.0885, -0.0272) * fterm(opd, g, 595.0);
  acc += float3( 0.4565, -0.0420, -0.0072) * fterm(opd, g, 625.0);
  acc += float3( 0.1319, -0.0147, -0.0017) * fterm(opd, g, 655.0);
  acc += float3( 0.0134,  0.0005, -0.0004) * fterm(opd, g, 685.0);
  return max(acc, float3(0.0)) * 2.0 * F;
}

// rotate around the vertical axis
float3 rotY(float3 v, float a) {
  float c = cos(a), s = sin(a);
  return float3(c * v.x + s * v.z, v.y, -s * v.x + c * v.z);
}

/**
 * Film thickness (nm) at unit-sphere point s (bubble frame, y up) for a bubble of normalised age a (0 = fresh, 1 = about to pop).
 *  - drainage: gravity pulls liquid down → thick at the bottom, thin at the top; the top thins with age to a black film
 *  - Marangoni eddies: differential rotation around the vertical axis (bands sliding past each other at different latitudes)
 *    plus warped noise, so colours swirl and stream instead of sitting still
 *  - th: per-bubble thickness scale (small spray bubbles are thinner, giant ones thicker)
 */
float filmThickness(float3 s, float a, float t, float seed, float th) {
  float lat = s.y;
  // (v31) a solid rotation plus a bounded, oscillating shear between latitudes: the old shear grew with time without limit
  // and combed every bubble into long parallel streaks after ~10 s
  float spin = t * (0.35 + 0.25 * fract(seed * 7.13)) + 0.8 * sin(0.25 * t + seed * 6.0) * lat * lat + seed * 10.0;
  float3 q = rotY(s, spin);
  float3 w = float3(vnoise3(q * 2.1 + seed * 3.0 + t * 0.11), vnoise3(q * 2.1 + 17.0 - t * 0.09), vnoise3(q * 2.1 + 41.0));
  float n1 = vnoise3(q * 2.6 * filmF + w * 1.8 + float3(0.0, t * 0.25, seed));
  float n2 = vnoise3(q * 6.0 * filmF + w * 2.5 - float3(t * 0.2, 0.0, 0.0));
  // drainage bands: thickness follows latitude, the bands are bent into swirls by the warped noise
  float latW = lat + (n1 - 0.5) * 0.55 + (n2 - 0.5) * 0.12;
  float u = clamp(0.5 - 0.5 * latW, 0.0, 1.0);    // 0 top … 1 bottom
  float drain = mix(0.16, 1.0, pow(u, 0.8));
  float young = 1.0 - smoothstep(0.0, 0.35, a);   // fresh films are thicker (paler, silvery-pastel)
  float base = mix(520.0, 1150.0, young) * th;
  float d = base * drain * (1.0 + (n2 - 0.5) * 0.18);
  // fine filaments dragged out by the flow (v26: the broad swirls alone read as an oil-slick wallpaper)
  float n4 = vnoise3(q * 13.0 + w * 3.2 + float3(0.0, t * 0.4, seed * 2.0));
  d += (n4 - 0.5) * 70.0 * th;
  // ageing, from the top down: the cap first thins into first-order colours (gold, magenta, blue: 120–300 nm),
  // then black-film spots (< 30 nm, no reflection at all) open up with sharp edges and spread until it pops
  float zone = smoothstep(0.35, 1.0, a) * smoothstep(-0.35, 0.9, lat);
  d = mix(d, 150.0 + 140.0 * n1, smoothstep(0.0, 0.55, zone));
  // spots: a low-frequency, lightly warped noise → rounded islands (the swirl noise n2 made thin "zebra" strokes)
  // (sampled in a rigid, slowly turning frame: the latitude-sheared swirl frame q would stretch them into streaks)
  float3 sr = rotY(s, t * 0.12 + seed * 4.0);
  float n3 = vnoise3(sr * 3.1 + float3(seed * 5.0, -t * 0.05, 0.0));
  float n5 = vnoise3(sr * 9.0 + float3(-seed * 3.0, t * 0.08, 7.0));
  float n6 = vnoise3(sr * 21.0 + float3(seed, -t * 0.1, 3.0));
  float sv = n3 * 0.8 + zone * 0.42;
  float late = smoothstep(0.85, 0.87, a);
  // last stretch of its life: the spots merge into a black cap that opens from the top (noisy edge with a bright rim)
  // (v26) the cap is centred a little toward the camera, so its edge curves round the sphere as an ellipse instead of a
  // straight "water line", and the edge is ragged with small plumes of thicker film
  float latC = dot(s, float3(0.0, 0.94, 0.34));
  // (v29) the black cap starts as a small spot at the top and grows (ease-in) to ~50° from the top over the last ~1.2 s;
  // its edge is smooth with a few soft lobes (a fractal edge read as a mountain ridge), and just below it sits a band of
  // first-order white film (~150–200 nm) with plumes rising into the black
  float uc = clamp((a - 0.85) / 0.1, 0.0, 1.0);
  float phi = atan(dot(s, float3(0.0, 0.34, -0.94)), s.x) + t * 0.04;
  // (v32) lobes with their own amplitude wander, only once the cap is big (a tiny cap drew a 7-petal daisy)
  float lobes = (0.022 * sin(7.0 * phi + seed * 3.0) + 0.014 * sin(11.0 * phi - seed * 5.0 + t * 0.2)) * (0.5 + n3)
    + (n3 - 0.5) * 0.03;
  float capL = 1.0 - 0.36 * pow(max(uc - 0.15, 0.0) / 0.85, 1.4) + lobes * smoothstep(0.3, 1.0, uc);
  // (v32) it opens as two or three irregular spots near the top that grow and merge into the cap
  float3 p1 = normalize(float3(sin(seed * 5.0) * 0.35, 0.94, 0.34 + cos(seed * 5.0) * 0.2));
  float3 p2 = normalize(float3(-sin(seed * 3.0 + 1.0) * 0.3, 0.92, 0.3 - cos(seed * 3.0) * 0.25));
  float3 p3 = normalize(float3(cos(seed * 7.0) * 0.25, 0.95, 0.2));
  float wob = (n5 - 0.5) * 0.012;
  float f = max(latC - capL, max(dot(s, p1) - (1.0 - 0.075 * smoothstep(0.0, 0.45, uc)) + wob,
    max(dot(s, p2) - (1.0 - 0.06 * smoothstep(0.08, 0.5, uc)) + wob, dot(s, p3) - (1.0 - 0.045 * smoothstep(0.15, 0.55, uc)) + wob)));
  float cap = smoothstep(0.0, 0.01, f) * late;
  // a few detached black islands only just below the cap's edge (v29: islands all over the top read as a jagged coastline)
  float near = smoothstep(-0.16, -0.04, f);
  float spot = smoothstep(0.72, 0.75, sv) * late * near * smoothstep(0.35, 0.5, uc);
  // the film just around a black spot is at the bright first-order white (~120 nm): outlines the dark islands
  d = mix(d, 120.0 + 40.0 * n1, smoothstep(0.63, 0.72, sv) * (1.0 - spot) * near * late);
  float plume = smoothstep(0.55, 0.8, n5) * 0.05;
  d = mix(d, 165.0 + 40.0 * n1, smoothstep(-0.09 - plume, 0.0, f) * (1.0 - cap) * late);
  d = mix(d, 10.0, max(spot, cap));
  return d;
}
`;
