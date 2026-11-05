import { Skia } from "react-native-skia";
import { FILM_SKSL } from "./film";
import { ENV_SKSL } from "./env";

/**
 * The soap film stretched across the wand ring (drawn under the ring sprite).
 *  - bulge: 0 = flat, 1 = domed out toward the viewer by the breath (normals tilt outward → reflections slide to the rim)
 *  - form: 0 → 1 while a fresh film re-forms after a pinch-off (starts as a thin rainbow skin, settles to silver)
 *  - flap: fast flutter of a strong puff (ripples running across the film)
 * Same thin-film + environment code as the bubbles.
 */
const src = `
${FILM_SKSL}
${ENV_SKSL}
uniform float time;
uniform float3 ring;       // x, y, r (inner radius, pt)
uniform float bulge;
uniform float form;
uniform float flap;
uniform float3 softSky;
uniform float3 softGround;

// the ring film is nearly flat, so it would mirror the garden behind the camera like a photo; a real wand film shows
// mostly its own swirling colour over a soft glow, so reflect a blurred world instead (sky warm above, garden dark below)
float3 envSoft(float3 d) {
  float up = clamp(0.5 + 0.5 * d.y, 0.0, 1.0);
  float3 l = mix(softGround * 0.3, softSky * 1.05, smoothstep(0.3, 0.95, up)) * envGain;
  float3 e = srgbDec(envLevel(d, 2.0)) * envGain;
  // the porch window still mirrors sharp: a wet flat film is a good mirror for one bright thing
  return mix(l, e, 0.08) + windowAt(d, 0.004) * 0.7;
}

half4 main(float2 p) {
  float2 q = (p - ring.xy) / ring.z;
  float rho = length(q);
  if (rho > 1.0) return half4(0.0);
  // (v35) the wet meniscus hugging the inside of the tube is always there, also while a bubble is attached or the film is
  // re-forming: it joins the bubble to the wand
  float menLine = smoothstep(0.975, 0.99, rho) * (1.0 - smoothstep(0.994, 1.0, rho));
  half4 wet = half4(half3(srgbEnc(float3(0.95, 0.9, 0.85) * menLine * 0.15 * envGain)), half(menLine * 0.12));
  if (form <= 0.0) return wet;
  // the film reaches across the ring from the rim inward while it re-forms
  float cover = smoothstep(1.0 - form * 1.1 - 0.05, 1.0 - form * 1.1, 1.0 - rho);
  if (form < 1.0 && cover <= 0.0) return wet;
  // dome: slope grows with the bulge, plus flutter waves on a puff
  float wave = flap * sin(rho * 14.0 - time * 38.0) * 0.18;
  float2 slope = q * (0.15 + bulge * 1.4) + normalize(q + 1e-4) * wave;
  float3 n = normalize(float3(slope.x, -slope.y, 1.0));
  float c = n.z;
  float3 s = normalize(float3(q.x, -q.y, 1.6));
  // thin, rainbow while forming; thick and silvery once settled; thins at the top as liquid drains
  float d = filmThickness(s, mix(0.75, 0.15, form), time * 1.3, 3.7, mix(0.45, 1.0, form)) * mix(0.5, 1.0, form);
  float3 r = filmRGB(d, c, 0.0);
  // (v37) a fresh film on the ring is nearly invisible: pale, faint bands, one highlight (it read as a framed photo)
  r = mix(float3((r.r + r.g + r.b) / 3.0), r, 0.55);
  float3 R = float3(0.0, 0.0, -1.0) + 2.0 * c * n;
  // (v28) a flat wet film is a good mirror: mostly the sharp world (window, light strings) over the soft colour fill
  // (v32) at ~4 % reflectance only bright things show on a flat film at night (the window, bulbs); dim walls and
  // foliage vanish, so the film doesn't play the garden like a TV screen
  // (v38) capped: the night bulbs are lifted to hot points for the bubbles, which drew a dotted string across the ring
  float3 L = r * (envSoft(R) * 0.2 + min(max(envAt(R, 0.003) - 0.6, float3(0.0)), float3(2.5)) * 0.14);
  float a = (r.r + r.g + r.b) / 3.0;
  // the meniscus where the film meets the ring: a thicker, brighter band
  // (v28: a crisp 1–2 px line, not a hazy band)
  float men = smoothstep(0.972, 0.99, rho) * (1.0 - smoothstep(0.994, 1.0, rho));
  L += float3(0.95, 0.9, 0.85) * men * 0.3 * envGain;
  a += men * 0.15;
  float k = cover * 0.38;
  // (v31) the film barely dims the garden behind it: a clear film, not tinted glass
  return half4(half3(srgbEnc(L * k)), half(min(a * k * 0.42, 1.0)));
}
`;

export const wandFilmFx = Skia.RuntimeEffect.Make(src)!;
if (!wandFilmFx) throw new Error("wand film shader failed to compile");
