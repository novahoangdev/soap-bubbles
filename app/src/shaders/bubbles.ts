import { Skia } from "react-native-skia";
import { FILM_SKSL } from "./film";
import { ENV_SKSL } from "./env";
import { MAXB } from "../sim/pool";

/**
 * All bubbles in one full-screen pass, drawn over the garden + wand (PLAN section 4).
 *
 * Per bubble i (back to front by slot index):
 *  - bA[i] = (x, y, r, alive)     centre / radius in design pt; alive 0 = empty slot
 *  - bW[i] = (a2, φ2, a3, φ3)     wobble: ellipse (l = 2) and trefoil (l = 3) radial modes
 *  - bF[i] = (age01, seed, cluster, popA)  normalised age, random seed, cluster id (0 = alone), pop hole angle (rad, < 0 = intact)
 *  - bP[i] = (px, py, pz, th)     pop origin on the sphere (unit, y up, z toward the viewer), film thickness scale
 *
 * Shading (orthographic camera, view toward −z): front surface (convex) reflects the garden environment upright, the back
 * surface seen from inside (concave) reflects it inverted and dimmer; both through the thin-film reflectance of their own
 * point on the sphere. Output is premultiplied: colour = reflected light, alpha = mean reflectance (light the film takes
 * away from the background), so the garden shows through the clear middle and the rim glows.
 *
 * Clusters: pixels inside two bubbles of the same cluster belong to the one with the smaller power distance
 * |p − c|² − r² (the radical line through both junction points); the shared wall is drawn as a thin bright film there.
 * Pops: the film exists only farther than popA from the pop origin; a thick bright rim rides the edge of the hole.
 */
const src = `
${FILM_SKSL}
${ENV_SKSL}
uniform float time;
uniform float4 bA[${MAXB}];
uniform float4 bW[${MAXB}];
uniform float4 bF[${MAXB}];
uniform float4 bP[${MAXB}];
uniform float4 bD[${MAXB}];   // (blur pt, layer, 0, 0)
uniform float layer;          // pass: 0 draws far + in-focus bubbles, 1 draws the near foreground ones
uniform float3 softSky;       // blurred world for defocused bubbles / wall glow: sky (upper) and ground colour, per look
uniform float3 softGround;

// defocused bubbles see a blurred world: warm bright above, dark green below, sun glow behind
float3 envSoft(float3 d) {
  float up = clamp(0.5 + 0.5 * d.y, 0.0, 1.0);
  float3 l = mix(softGround, softSky, smoothstep(0.35, 0.9, up)) * envGain;
  l += float3(1.0, 0.8, 0.5) * sunGain * pow(max(dot(d, sunDir), 0.0), 6.0) * 0.8;
  return l;
}
// smooth film for defocused bubbles: drainage bands only, gently swirled
float softThickness(float3 s, float t, float seed) {
  float lat = s.y + 0.18 * sin(s.x * 2.2 + t * 0.4 + seed) + 0.1 * sin(s.z * 3.1 - t * 0.3);
  float u = clamp(0.5 - 0.5 * lat, 0.0, 1.0);
  return 900.0 * mix(0.2, 1.0, pow(u, 0.8));
}

/**
 * Signed distance (pt) from p to the wall shared by bubbles i and j, > 0 on i's side. Plateau: the films meet at 120°,
 * the wall is a spherical cap of radius ri·rj / |ri − rj| bulging into the larger bubble, through the two junction points
 * (seen side-on: an arc). Nearly equal bubbles: the flat radical line.
 */
float wallSide(float2 p, float2 ci, float ri, float2 cj, float rj, float powI, float powJ) {
  float2 ax = cj - ci;
  float d = max(length(ax), 1e-3);
  float2 u = ax / d;
  if (abs(ri - rj) < 0.04 * max(ri, rj)) return (powJ - powI) / (2.0 * d);
  float x0 = (d * d + ri * ri - rj * rj) / (2.0 * d);
  float h2 = max(ri * ri - x0 * x0, 0.0);
  if (rj < ri) {
    float R3 = ri * rj / (ri - rj);
    float2 c3 = ci + u * (x0 + sqrt(max(R3 * R3 - h2, 0.0)));
    return length(p - c3) - R3;
  }
  float R3 = ri * rj / (rj - ri);
  float2 c3 = ci + u * (x0 - sqrt(max(R3 * R3 - h2, 0.0)));
  return R3 - length(p - c3);
}

float radiusScale(float2 dp, float4 w) {
  float th = atan(dp.y, dp.x);
  return 1.0 + w.x * cos(2.0 * (th - w.y)) + w.z * cos(3.0 * (th - w.w));
}

half4 main(float2 p) {
  float3 col = float3(0.0);
  float alpha = 0.0;
  for (int i = 0; i < ${MAXB}; i++) {
    float4 A = bA[i];
    if (A.w < 0.5) continue;
    float4 D = bD[i];
    if ((layer > 0.5) != (D.y > 0.5)) continue;
    float blur = max(D.x, 0.0);
    float2 dp = p - A.xy;
    float d2 = dot(dp, dp);
    float rMax = A.z * 1.35 + 2.0 + blur;
    if (d2 > rMax * rMax) continue;
    float4 W = bW[i];
    float rr = A.z * radiusScale(dp, W);
    float rhoE = sqrt(d2) / rr;
    float bl = max(1.2, blur) / rr;
    if (rhoE >= 1.0 + bl) continue;
    float rho = min(rhoE, 0.995);
    float4 F = bF[i];
    // cluster ownership + walls
    float wall = 0.0;
    bool owned = true;
    if (F.z > 0.5) {
      float powI = d2 - rr * rr;
      for (int j = 0; j < ${MAXB}; j++) {
        if (j == i) continue;
        float4 B = bA[j];
        // a popping neighbour keeps its wall until the last of its film is gone (v28: no full-sphere ghost, no instant snap;
        // v32: its leftover back film stays clipped too)
        if (B.w < 0.5 || abs(bF[j].z - F.z) > 0.1 || bF[j].w > 2.84) continue;
        // one disc wholly inside the other: the small one sits on the near or far face, not beside it, so no shared wall
        // in the picture (v29: those drew hollow rings inside the giant)
        if (length(B.xy - A.xy) + min(B.z, A.z) < max(B.z, A.z) * 0.98) continue;
        float2 dq = p - B.xy;
        float rj = B.z * radiusScale(dq, bW[j]);
        float powJ = dot(dq, dq) - rj * rj;
        if (powJ >= 0.0) continue;          // not inside j
        float dist = wallSide(p, A.xy, rr, B.xy, rj, powI, powJ); // > 0: this bubble's side of the shared wall (pt)
        if (dist < 0.0) { owned = false; break; }
        if (j > i) wall = max(wall, 1.0 - smoothstep(0.2, 0.7, dist));
      }
    }
    if (!owned) continue;
    float2 q = dp / rr * (rho / max(rhoE, 1e-4));
    float nz = sqrt(max(1.0 - rho * rho, 0.0));
    float3 nf = float3(q.x, -q.y, nz);       // front normal (y up)
    float3 nb = float3(q.x, -q.y, -nz);      // back surface point
    float4 P = bP[i];
    float age = F.x;
    float seed = F.y;
    float popA = F.w;
    // in-focus films flow faster (v28: real films never sit still; plumes and swirls move every frame)
    // (v29: big bubbles a little calmer, a fast colour cycle over the window read as a hologram)
    float t = blur > 0.0 ? time : time * mix(1.6, 1.1, smoothstep(60.0, 100.0, rr));
    // front surface
    bool soft = blur > 0.0;
    // per device pixel (3 px/pt): how far the mirrored direction sweeps (rad) and how much the film thickness spreads (nm)
    float nzc = max(nz, 0.06);
    float fp = 2.0 / (3.0 * rr * nzc);
    float sd = 900.0 / (3.0 * rr * nzc);
    float df = soft ? softThickness(nf, t, seed) : filmThickness(nf, age, t, seed, P.w);
    float3 rf = filmRGB(df, nz, sd);
    rf = mix(float3((rf.r + rf.g + rf.b) / 3.0), rf, lookK.y);
    float3 Rf = float3(0.0, 0.0, -1.0) + 2.0 * nz * nf;
    float3 Ef = soft ? envSoft(Rf) : envAt(Rf, fp);
    // a bright source reflected in the film saturates the camera: its core goes toward white, colour stays at its edges
    // (v29: the window panes were fully striped neon, a holographic sticker)
    // (v37: stronger, from a lower level: the mirrored windows were neon in every bubble)
    float3 rfw = mix(rf, float3((rf.r + rf.g + rf.b) / 3.0), 0.9 * smoothstep(0.25, 2.0, dot(Ef, float3(0.2126, 0.7152, 0.0722))));
    float3 L = rfw * Ef;
    float aF = (rf.r + rf.g + rf.b) / 3.0;
    // back surface (concave mirror from inside: inverted, dimmer, seen through the front film)
    float db = soft ? softThickness(nb, t, seed + 3.0) : filmThickness(nb, age, t, seed, P.w);
    float3 rb = filmRGB(db, nz, sd);
    rb = mix(float3((rb.r + rb.g + rb.b) / 3.0), rb, lookK.y);
    float3 inner = float3(-q.x, q.y, nz);
    float3 Rb = float3(0.0, 0.0, -1.0) + 2.0 * nz * inner;
    float3 Eb = soft ? envSoft(Rb) : envAt(Rb, fp);
    // (v37) per look, dimmer (night 0.42): the inverted second image doubled every reflection
    // (v38) bright sources shed the film tint on the back too, and the inverted image of a bright source stays dimmer
    float lEb = dot(Eb, float3(0.2126, 0.7152, 0.0722));
    rb = mix(rb, float3((rb.r + rb.g + rb.b) / 3.0), 0.6 * smoothstep(0.25, 2.0, lEb));
    float3 Lb = rb * Eb * lookK.w * mix(1.0, 0.7, smoothstep(0.5, 3.0, lEb));
    float aB = (rb.r + rb.g + rb.b) / 3.0 * lookK.w;
    // black film (< ~60 nm, no reflection) is transparent: it reads as a clean hole in the reflections, outlined by the bright
    // first-order band around it; only a faint veil so it still shows over the brightest bokeh (v26: was 0.62, a grey curtain)
    if (!soft) {
      aF = max(aF, 0.12 * lookK.z * (1.0 - smoothstep(25.0, 70.0, df)));
      aB = max(aB, 0.06 * lookK.z * (1.0 - smoothstep(25.0, 70.0, db)));
    }
    // popping: film only beyond the hole, bright rim at its edge
    if (popA >= 0.0) {
      float3 po = P.xyz;
      float angF = acos(clamp(dot(nf, po), -1.0, 1.0));
      float angB = acos(clamp(dot(nb, po), -1.0, 1.0));
      // torn, not a clean circle: the hole edge wanders with the film noise and the rim breaks into beads
      // (v29) big bubbles tear with a smoother edge and a thinner, brighter rim (the giant's rim read as a smoke ribbon)
      // (v31) every size: a gently wandering edge and a rim 1–2 device px wide, broken into beads (a fixed angular width
      // drew an even white rope on the giant)
      float big = smoothstep(50.0, 90.0, rr);
      float tear = 0.08 + 0.06 * (1.0 - big);
      float rw0 = max(1.3 / (3.0 * rr * nzc), 0.004);
      float bfq = mix(18.0, 30.0, big);
      // (v33) the hole opens ragged from its first frame: a finer second octave on top of the wandering edge
      float eF = popA + ((vnoise3(nf * 4.5 + seed * 7.0) - 0.5) + 0.5 * (vnoise3(nf * 11.0 - seed * 3.0) - 0.5)) * tear;
      float eB = popA + ((vnoise3(nb * 4.5 + seed * 7.0) - 0.5) + 0.5 * (vnoise3(nb * 11.0 - seed * 3.0) - 0.5)) * tear;
      float keepF = smoothstep(eF - 0.02, eF + 0.04, angF);
      float keepB = smoothstep(eB - 0.02, eB + 0.04, angB);
      float beadF = 0.35 + 0.95 * smoothstep(0.45, 0.75, vnoise3(nf * bfq + seed));
      float beadB = 0.35 + 0.95 * smoothstep(0.45, 0.75, vnoise3(nb * bfq + seed));
      // the rim is just the film's liquid gathered into a thick torus: silvery, mirroring the world (no white glow; v26)
      float rimF = exp(-pow((angF - eF) / rw0, 2.0)) * step(0.0, popA) * beadF;
      float rimB = exp(-pow((angB - eB) / rw0, 2.0)) * step(0.0, popA) * beadB;
      // (v28) plus a floor so the retracting edge reads even where it crosses transparent black film
      L = L * keepF + (Ef * 0.09 + float3(mix(0.04, 0.15, big)) * beadF) * rimF;
      Lb = Lb * keepB + (Eb * 0.05 + float3(mix(0.02, 0.07, big)) * beadB) * rimB;
      aF = aF * keepF + rimF * 0.12;
      aB = aB * keepB + rimB * 0.07;
    }
    float3 Lw = float3(0.0);
    float aW = 0.0;
    if (wall > 0.0) {
      // the shared wall is seen edge-on: grazing film, strong reflection, thin-film colour sliding along it
      float dw = filmThickness(float3(q.x, -q.y, 0.3), age, t, seed + 5.0, P.w);
      float3 rw = filmRGB(dw, 0.12, 40.0);
      // (v29: half as bright, thinner, no flat fill: with the highlight roll-off they had become drawn-on white bars)
      Lw = rw * envAt(normalize(float3(-q.y, q.x, 0.4)), 0.05) * wall * 0.7;
      // (v33) never brighter than a soft silver: at triple junctions the walls stacked into white ticks
      Lw = min(Lw, float3(0.32));
      aW = wall * 0.35;
    }
    // compose this bubble: back surface first, then the front film over it
    float3 bub = Lb * (1.0 - aF) + L + Lw;
    float ab = 1.0 - (1.0 - aB) * (1.0 - aF) * (1.0 - aW);
    // soft antialiased silhouette
    float edge = blur > 0.0 ? 1.0 - smoothstep(1.0 - bl, 1.0 + bl, rhoE) : 1.0 - smoothstep(1.0 - bl, 1.0, rhoE);
    // defocused bubbles: ghostlier, the bright rim spreads into a soft ring
    if (blur > 0.0) {
      float k = clamp(blur / 18.0, 0.0, 1.0);
      float lb = dot(bub, float3(0.2126, 0.7152, 0.0722));
      // (v33) a bubble near the lens is a faint large ghost with a hint of colour at its rim, not a neon ring
      bub = mix(bub, float3(lb), 0.85 * k) * mix(1.0, 0.18, k);
      ab *= mix(1.0, 0.13, k);
    }
    bub *= edge;
    ab *= edge;
    col = col * (1.0 - ab) + bub;
    alpha = 1.0 - (1.0 - alpha) * (1.0 - ab);
  }
  if (alpha <= 0.0 && col.r + col.g + col.b <= 0.0) return half4(0.0);
  // highlight roll-off like a camera sensor: what clips burns to white (bulbs and the window core shed the film tint)
  float m = max(col.r, max(col.g, col.b));
  col = mix(col, float3(m), smoothstep(0.75, 2.2, m));
  // premultiplied: encoded reflected light on top, alpha = what the films take from the garden behind
  return half4(half3(srgbEnc(col)), half(min(alpha, 1.0)));
}
`;

export const bubblesFx = Skia.RuntimeEffect.Make(src)!;
if (!bubblesFx) throw new Error("bubbles shader failed to compile");
