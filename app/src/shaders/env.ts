/**
 * Shared SkSL: what a soap film mirrors (v26). Needs FILM_SKSL (PI, srgbDec) before it.
 *
 * env is a three-level atlas (tools/env_atlas.sh): sharp / mid / soft equirect maps stacked top to bottom, each envSize.
 * envAt(d, fp) picks the level from the reflection footprint fp (radians the mirrored direction sweeps across one device
 * pixel): a big in-focus bubble mirrors crisp little images of the light strings, while small bubbles and rims (wide footprint)
 * read the blurred levels and don't alias into sparkle.
 *
 * win / winCol: a lit window behind the photographer (night: warm porch window with four panes), analytic so it stays sharp
 * at any size. Mirrored upright upper-left on the front of every bubble and inverted lower-right from the back surface —
 * the classic double reflection of real bubble photos, and where the film shows its strongest colours.
 */
export const ENV_SKSL = `
uniform shader env;
uniform float2 envSize;     // one level of the atlas (px)
uniform float envU0;        // u of the camera's forward direction (−z) in the equirect map
uniform float envGain;      // LDR env → linear radiance
uniform float3 sunDir;      // camera space, toward the sun / key lantern
uniform float sunGain;
uniform float4 win;         // window centre (azimuth around +z, elevation) and half size (rad)
uniform float3 winCol;      // window radiance (0 = no window)
uniform float4 lookK;       // per look (v37): bulb lift, film colour amount, black-film veil scale, back-surface gain

float3 envLevel(float3 d, float lvl) {
  float u = envU0 + atan(d.x, -d.z) / (2.0 * PI);
  float v = clamp(0.5 - asin(clamp(d.y, -1.0, 1.0)) / PI, 0.002, 0.998);
  return env.eval(float2(fract(u) * envSize.x, (v + lvl) * envSize.y)).rgb;
}

float3 windowAt(float3 d, float fp) {
  float az = atan(d.x, d.z) - win.x;
  float el = asin(clamp(d.y, -1.0, 1.0)) - win.y;
  float e = fp + 0.004;
  // a soft glow just outside the frame (the room light spilling round it), so it isn't a flat sticker
  float2 out2 = max(abs(float2(az, el)) - win.zw, float2(0.0));
  float glow = exp(-dot(out2, out2) / 0.004) * 0.05;
  float box = smoothstep(win.z + e, win.z - e, abs(az)) * smoothstep(win.w + e, win.w - e, abs(el));
  if (box <= 0.0) return winCol * glow;
  // mullion + transom (four panes), a little warmer and brighter toward the lamp at the bottom of the room
  float bw = 0.011;
  float bar = max(smoothstep(bw + e, bw, abs(az)), smoothstep(bw + e, bw, abs(el + win.w * 0.12)));
  float grad = 0.8 + 0.35 * smoothstep(win.w, -win.w, el);
  return winCol * (box * (1.0 - 0.94 * bar) * grad + glow * (1.0 - box));
}

float3 envAt(float3 d, float fp) {
  float ft = fp / (2.0 * PI / (envSize.x));            // footprint in texels
  float lvl = smoothstep(1.5, 4.0, ft) + smoothstep(5.0, 14.0, ft);
  // (v37) the horizon band (tree line, lawn edge) is never sharp: every bubble's equator mirrored the same crisp strip, which
  // read as a row of chrome balls
  lvl = max(lvl, 1.15 * (1.0 - smoothstep(0.03, 0.16, abs(d.y))));
  float l0 = floor(min(lvl, 1.999));
  float3 c = mix(envLevel(d, l0), envLevel(d, l0 + 1.0), lvl - l0);
  float3 l = srgbDec(c) * envGain;
  // the LDR map clips the bulbs at white: lift what clipped so a bulb is the hottest point on the film and burns through its
  // tint (with the roll-off in the bubble shader)
  // (v37: per look; night 14: bulbs clip to points, the strings of catchlights arcing over each bubble's top)
  // only above the horizon: the strings sagging low between the trees burned a dotted line across every equator
  // (v39) a negative lift only takes the very core (studio: the softbox, not the broad diffuser around it)
  float lt = lookK.x < 0.0 ? 0.95 : 0.78;
  l *= 1.0 + abs(lookK.x) * smoothstep(lt, lt + 0.04 + 0.14 * step(0.0, lookK.x), max(c.r, max(c.g, c.b))) * smoothstep(0.08, 0.22, d.y);
  // the sun / key lantern (LDR maps clip it): a hot core and a faint halo
  float sd = dot(d, sunDir);
  l += float3(1.0, 0.86, 0.62) * sunGain * (pow(max(sd, 0.0), 900.0) * 18.0 + pow(max(sd, 0.0), 40.0) * 0.25);
  return l + windowAt(d, fp);
}
`;
