import { Skia } from "react-native-skia";

/**
 * Photographic finish, drawn with softLight over everything (0.5 = no change): a gentle vignette, a warm lift toward the sun
 * corner, and fine animated film grain so the flat bokeh doesn't band.
 */
const src = `
uniform float time;
uniform float2 view;
uniform float2 sunUV;   // warm lift centre (uv), per look
uniform float warm;
float hash(float2 p) {
  p = fract(p * float2(443.897, 441.423));
  p += dot(p, p.yx + 19.19);
  return fract((p.x + p.y) * p.x);
}
half4 main(float2 p) {
  float2 uv = p / view;
  float2 c = uv - float2(0.5, 0.45);
  c.x *= view.x / view.y;
  float v = 1.0 - smoothstep(0.25, 0.75, length(c));
  float g = hash(p + fract(time * 23.0) * 91.0) - 0.5;
  float sun = exp(-dot(uv - sunUV, uv - sunUV) * 9.0);
  float k = 0.5 - (1.0 - v) * 0.22 + g * 0.085 + sun * warm;
  return half4(half3(k), 1.0);
}
`;
export const postFx = Skia.RuntimeEffect.Make(src)!;
if (!postFx) throw new Error("post shader failed to compile");
