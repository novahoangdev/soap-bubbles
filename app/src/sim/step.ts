import {
  BLUR, LAYER, A2, A3, AGE, ALIVE, BF, CL, DF, DUE, E_PINCH, E_SPRAY, E_STICK, LIFE, MAXB, MAXD, NB, P2, POP, PX, PY, PZ, R, SEED, V2, V3, VX, VY, W_ATT, W_BULGE, W_BULGEV, W_FLAP, W_FORM, W_GROW, W_PEAK, W_QUIET, W_SPRAY, X, Y, pop, rnd, spawn, bond, unbondAll, type Sim,
} from "./pool";

/** Inputs of one physics step (all in design pt / scene seconds). */
export type StepIn = {
  /** breath envelope 0…1 */
  breath: number;
  /** wand ring centre / inner radius */
  rx: number;
  ry: number;
  rr: number;
  /** finger wind: position, velocity (pt/s), active 0/1 */
  fx: number;
  fy: number;
  fvx: number;
  fvy: number;
  fa: number;
  /** slot carried by a "wet finger" (−1 = none): it follows the finger on a spring instead of popping */
  grab: number;
  /** tilt gravity offset (−1…1) */
  gx: number;
  gy: number;
  /** demo: soft attractor that herds bubbles together (strength 0 = off) */
  hx: number;
  hy: number;
  hk: number;
  /** demo: soft attractor for the giant bubble only (keeps its finale in the middle of the frame) */
  kx: number;
  ky: number;
  kk: number;
  /** demo: scene time the next released giant bubble must pop by itself (0 = natural) */
  bigDue: number;
  w: number;
  h: number;
};

const G = 7; // net sinking (gravity − buoyancy), pt/s²
const DRAG = 0.42; // linear air drag 1/s
const STICK_V = 85; // contacts slower than this stick together
const RMAX = 122; // largest bubble the wand can blow
const POP_DUR = 0.05; // seconds for the hole to sweep a small sphere: three frames, fast like a real bubble yet readable (big ones × up to 2)
const DG = 1100; // droplet gravity pt/s²

const emitDrop = (s: Sim, x: number, y: number, vx: number, vy: number, size: number, life: number) => {
  "worklet";
  const o = s.dNext * DF;
  s.dNext = (s.dNext + 1) % MAXD;
  const d = s.d;
  d[o] = x;
  d[o + 1] = y;
  d[o + 2] = vx;
  d[o + 3] = vy;
  d[o + 4] = size;
  d[o + 5] = 0;
  d[o + 6] = life;
};

const wobble = (b: number[], o: number, dt: number) => {
  "worklet";
  const r = b[o + R];
  const f = Math.min(12, Math.max(1.8, 5.2 * Math.pow(60 / Math.max(r, 4), 1.15)));
  const w2 = 2 * Math.PI * f, w3 = w2 * 1.62;
  const z = 0.1;
  b[o + V2] += (-w2 * w2 * b[o + A2] - 2 * z * w2 * b[o + V2]) * dt;
  b[o + A2] += b[o + V2] * dt;
  b[o + V3] += (-w3 * w3 * b[o + A3] - 2 * z * w3 * b[o + V3]) * dt;
  b[o + A3] += b[o + V3] * dt;
  b[o + A2] = Math.max(-0.12, Math.min(0.12, b[o + A2]));
  b[o + A3] = Math.max(-0.1, Math.min(0.1, b[o + A3]));
};

const kick = (b: number[], o: number, amt: number, ang: number) => {
  "worklet";
  // never snap the axis of a visible wobble (the outline would jump in one frame)
  if (Math.abs(b[o + A2]) < 0.015) {
    b[o + V2] += amt;
    b[o + P2] = ang;
  } else b[o + V2] += amt * Math.cos(2 * (ang - b[o + P2]));
  b[o + V3] += amt * 0.45;
};

/** Sub-step of the whole simulation. */
export const step = (s: Sim, inp: StepIn, dt: number, t: number) => {
  "worklet";
  const b = s.b;
  const w = s.w;
  const B = inp.breath;

  // ── wand: film, growth, pinch-off, spray ──
  if (w[W_FORM] < 1) w[W_FORM] = Math.min(1, w[W_FORM] + dt / 0.75);
  const att = w[W_ATT];
  const target = att >= 0 ? 1 : Math.min(1, B * 1.6);
  w[W_BULGEV] += (180 * (target - w[W_BULGE]) - 14 * w[W_BULGEV]) * dt;
  w[W_BULGE] = Math.max(0, w[W_BULGE] + w[W_BULGEV] * dt);
  w[W_FLAP] += ((B > 0.6 ? B : 0) - w[W_FLAP]) * Math.min(1, dt * 10);
  w[W_QUIET] = B < 0.06 ? w[W_QUIET] + dt : 0;
  if (B > 0.6 && att < 0 && w[W_FORM] > 0.4) {
    // sharp puff: a stream of little bubbles
    w[W_SPRAY] += dt * (16 + 40 * (B - 0.6));
    while (w[W_SPRAY] >= 1) {
      w[W_SPRAY] -= 1;
      const a = rnd(s) * Math.PI * 2, rr = Math.sqrt(rnd(s)) * 0.55 * inp.rr;
      const r = 11 + Math.pow(rnd(s), 1.4) * 30;
      const i = spawn(s, inp.rx + Math.cos(a) * rr, inp.ry + Math.sin(a) * rr * 0.6, r, (rnd(s) - 0.5) * 190, -(110 + 170 * B * (0.4 + rnd(s) * 0.6)), 0.55 + rnd(s) * 0.35, t);
      if (i >= 0) {
        kick(b, i * BF, 2.2, rnd(s) * Math.PI);
        b[i * BF + LIFE] = 6 + rnd(s) * 9;
        s.ev[E_SPRAY] += 1;
      }
    }
    w[W_FORM] = Math.max(0.55, w[W_FORM] - dt * 0.4);
  } else w[W_SPRAY] = Math.min(w[W_SPRAY], 0.6);

  if (att < 0 && B > 0.07 && B <= 0.6 && w[W_FORM] >= 0.98 && w[W_BULGE] > 0.35) {
    const i = spawn(s, inp.rx, inp.ry, inp.rr * 0.98, 0, 0, 1.15, t);
    if (i >= 0) {
      b[i * BF + ALIVE] = 2;
      b[i * BF + LIFE] = 1e9;
      w[W_ATT] = i;
      w[W_PEAK] = B;
      w[W_GROW] = 0;
    }
  } else if (att >= 0) {
    const o = att * BF;
    w[W_GROW] += dt;
    w[W_PEAK] = Math.max(w[W_PEAK], B);
    const r = b[o + R];
    b[o + R] = Math.min(RMAX, r + dt * (16 + 62 * B) * (1 - 0.45 * (r / RMAX)));
    // the bubble balloons upward out of the ring: its bottom stays near the ring's bottom edge
    const sway = Math.sin(t * 2.3) * 3 * (r / RMAX);
    b[o + X] += (inp.rx + sway - b[o + X]) * Math.min(1, dt * 12);
    b[o + Y] = inp.ry + inp.rr * 0.92 - b[o + R];
    b[o + VX] = 0;
    b[o + VY] = 0;
    // breath turbulence makes the film shiver
    if (B > 0.05) b[o + V2] += (rnd(s) - 0.5) * 6 * B * dt * 60 * 0.05;
    wobble(b, o, dt);
    b[o + AGE] = 0;
    const release = w[W_QUIET] > 0.12 || b[o + R] >= RMAX || B > 0.75;
    if (release) {
      if (b[o + R] < inp.rr * 1.12) {
        // barely blown: the dome sinks back into the ring
        b[o + ALIVE] = 0;
        w[W_ATT] = -1;
      } else {
        b[o + ALIVE] = 1;
        b[o + VY] = -(35 + 70 * w[W_PEAK]);
        b[o + VX] = (rnd(s) - 0.5) * 30;
        b[o + LIFE] = 12 + rnd(s) * 8;
        if (inp.bigDue > 0) b[o + DUE] = inp.bigDue;
        // pinch-off: the neck snaps, the bubble jiggles (stretched vertically then squashed)
        kick(b, o, 1.9, Math.PI / 2);
        w[W_ATT] = -1;
        w[W_FORM] = -0.3;
        s.ev[E_PINCH] += 1;
        // a few droplets fall from the neck
        for (let k = 0; k < 6; k++) emitDrop(s, inp.rx + (rnd(s) - 0.5) * 8, inp.ry - inp.rr * 0.1, (rnd(s) - 0.5) * 50, 40 + rnd(s) * 60, 0.4 + rnd(s) * 0.5, 0.6);
      }
    }
  }

  // ── forces, ageing, pops ──
  for (let i = 0; i < MAXB; i++) {
    const o = i * BF;
    const al = b[o + ALIVE];
    if (al === 0) continue;
    const r = b[o + R];
    if (b[o + POP] >= 0) {
      // popping: the hole sweeps the sphere, its rim sheds droplets
      const a0 = b[o + POP];
      const a1 = a0 + (dt * Math.PI) / (POP_DUR * Math.min(2, Math.max(1, Math.sqrt(r / 50)))) * (0.55 + 0.9 * Math.min(1, a0 / 1.2));
      b[o + POP] = a1;
      const px = b[o + PX], py = b[o + PY], pz = b[o + PZ];
      // orthonormal basis around the pop axis
      let ex = -py, ey = px, ez = 0;
      if (Math.abs(pz) > 0.9) {
        ex = 1;
        ey = 0;
        ez = 0;
      }
      let l = Math.hypot(ex, ey, ez);
      ex /= l;
      ey /= l;
      ez /= l;
      const fx = py * ez - pz * ey, fy = pz * ex - px * ez, fz = px * ey - py * ex;
      const n = Math.round(1.5 + r / 16); // a few dozen droplets in all, not a firework
      for (let k = 0; k < n; k++) {
        const al2 = a0 + (a1 - a0) * rnd(s);
        const ph = rnd(s) * Math.PI * 2;
        const ca = Math.cos(al2), sa = Math.sin(al2), cp = Math.cos(ph), sp = Math.sin(ph);
        const qx = ca * px + sa * (cp * ex + sp * fx);
        const qy = ca * py + sa * (cp * ey + sp * fy);
        const qz = ca * pz + sa * (cp * ez + sp * fz);
        if (qz < -0.35 && rnd(s) < 0.6) continue;
        // rim velocity: along the sphere, away from the hole
        const tx = -sa * px + ca * (cp * ex + sp * fx);
        const ty = -sa * py + ca * (cp * ey + sp * fy);
        const v = (180 + 380 * rnd(s)) * Math.sqrt(r / 60);
        emitDrop(s, b[o + X] + r * qx, b[o + Y] - r * qy, b[o + VX] + tx * v + (rnd(s) - 0.5) * 60, b[o + VY] - ty * v + (rnd(s) - 0.5) * 60, 0.45 + rnd(s) * 0.6 + r * 0.003, 0.18 + rnd(s) * 0.22);
      }
      if (a1 >= Math.PI) {
        unbondAll(s, i);
        b[o + ALIVE] = 0;
        // a couple of fine droplets where the bubble was
        for (let k = 0; k < 2; k++) emitDrop(s, b[o + X] + (rnd(s) - 0.5) * r, b[o + Y] + (rnd(s) - 0.5) * r, (rnd(s) - 0.5) * 80, (rnd(s) - 0.5) * 80, 0.3 + rnd(s) * 0.3, 0.4);
      }
      b[o + X] += b[o + VX] * dt;
      b[o + Y] += b[o + VY] * dt;
      continue;
    }
    if (al === 2) continue;
    if (b[o + LAYER] !== 0) {
      // depth-of-field bubbles: slow drift with the breeze (parallax: near ones move more), wrap around, never pop
      // (v37: near ones 0.5 → 1: they sat still for the whole demo, like smudges on the lens)
      const par = b[o + LAYER] > 0 ? 1.0 : 0.45;
      const sd0 = b[o + SEED];
      b[o + X] += (b[o + VX] + 8 * Math.sin(t * 0.21 + sd0)) * par * dt;
      b[o + Y] += (b[o + VY] + 6 * Math.cos(t * 0.17 + sd0 * 2)) * par * dt;
      const rr0 = b[o + R] + b[o + BLUR];
      if (b[o + X] < -rr0) b[o + X] = inp.w + rr0;
      if (b[o + X] > inp.w + rr0) b[o + X] = -rr0;
      if (b[o + Y] < -rr0) b[o + Y] = inp.h + rr0;
      if (b[o + Y] > inp.h + rr0) b[o + Y] = -rr0;
      wobble(b, o, dt);
      continue;
    }
    b[o + AGE] += dt;
    const due = b[o + DUE];
    if ((due > 0 && t >= due) || (due === 0 && b[o + AGE] > b[o + LIFE])) {
      // the thinnest point (top) gives way
      pop(s, i, (rnd(s) - 0.5) * 0.5, 0.82, 0.42);
      continue;
    }
    let ax = 0, ay = G;
    // slow breeze: smooth flowing field
    const x = b[o + X], y = b[o + Y], sd = b[o + SEED];
    ax += 9 * Math.sin(y * 0.011 + t * 0.23 + sd) + 5 * Math.sin(t * 0.17 + sd * 2);
    ay += 5 * Math.cos(x * 0.013 + t * 0.31 + sd * 3);
    ax += inp.gx * 40;
    ay += inp.gy * 40;
    // keep bubbles on screen: soft walls left / right
    const m = r * 1.05;
    if (x < m) ax += (m - x) * 6;
    if (x > inp.w - m) ax -= (x - (inp.w - m)) * 6;
    if (y < r + 24) ay += (r + 24 - y) * 5;
    // demo herding
    if (inp.hk > 0) {
      const hx = inp.hx - x, hy = inp.hy - y;
      const hl = Math.hypot(hx, hy) + 1;
      ax += (hx / hl) * inp.hk * Math.min(1, hl / 60);
      ay += (hy / hl) * inp.hk * Math.min(1, hl / 60);
    }
    // the breath itself is a jet of air out of the wand: it lifts and scatters bubbles above the ring
    if (B > 0.05) {
      const dx = x - inp.rx, dy = y - inp.ry;
      const dist = Math.hypot(dx, dy) + 1;
      if (dy < 40) {
        const k = B * B * 520 * Math.exp(-dist / 220) * Math.min(1.8, 60 / Math.max(r, 20));
        ax += (dx / dist) * k * 0.6;
        ay += (dy / dist) * k - k * 0.4;
      }
    }
    if (inp.kk > 0 && b[o + DUE] > 0) {
      ax += (inp.kx - x) * inp.kk - b[o + VX] * 2.2 * Math.sqrt(inp.kk);
      ay += (inp.ky - y) * inp.kk - b[o + VY] * 2.2 * Math.sqrt(inp.kk);
    }
    if (i === inp.grab) {
      ax += (inp.fx - x) * 160 - b[o + VX] * 18;
      ay += (inp.fy - y) * 160 - b[o + VY] * 18;
    }
    // finger wind
    else if (inp.fa > 0) {
      const dx = x - inp.fx, dy = y - inp.fy;
      const k = Math.exp(-(dx * dx + dy * dy) / (2 * 110 * 110)) * inp.fa;
      ax += (inp.fvx - b[o + VX]) * k * 5;
      ay += (inp.fvy - b[o + VY]) * k * 5;
    }
    const dr = Math.exp(-DRAG * dt);
    b[o + VX] = b[o + VX] * dr + ax * dt;
    b[o + VY] = b[o + VY] * dr + ay * dt;
    wobble(b, o, dt);
  }

  // ── contacts: bounce or stick ──
  for (let i = 0; i < MAXB; i++) {
    const oi = i * BF;
    if (b[oi + ALIVE] === 0 || b[oi + POP] >= 0 || b[oi + LAYER] !== 0) continue;
    for (let j = i + 1; j < MAXB; j++) {
      const oj = j * BF;
      if (b[oj + ALIVE] === 0 || b[oj + POP] >= 0 || b[oj + LAYER] !== 0) continue;
      const ri = b[oi + R], rj = b[oj + R];
      let dx = b[oj + X] - b[oi + X], dy = b[oj + Y] - b[oi + Y];
      let d = Math.hypot(dx, dy);
      const sum = ri + rj;
      const bonded = s.bonds[i * MAXB + j] === 1;
      if (!bonded && d >= sum) continue;
      if (d < 1e-3) {
        dx = 1;
        dy = 0;
        d = 1e-3;
      }
      const nx = dx / d, ny = dy / d;
      const fixI = b[oi + ALIVE] === 2, fixJ = b[oj + ALIVE] === 2;
      const mi = fixI ? 1e9 : ri * ri, mj = fixJ ? 1e9 : rj * rj;
      const wi = mj / (mi + mj), wj = mi / (mi + mj);
      const vrel = (b[oj + VX] - b[oi + VX]) * nx + (b[oj + VY] - b[oi + VY]) * ny;
      if (bonded) {
        // Plateau: centres settle where the films meet at 120°
        const d0 = Math.sqrt(ri * ri + rj * rj - ri * rj);
        if (d > sum * 1.08) {
          s.bonds[i * MAXB + j] = 0;
          s.bonds[j * MAXB + i] = 0;
          b[oi + NB] -= 1;
          b[oj + NB] -= 1;
          continue;
        }
        const f = (d - d0) * 22 + vrel * 3.2;
        b[oi + VX] += nx * f * wi * dt * 2;
        b[oi + VY] += ny * f * wi * dt * 2;
        b[oj + VX] -= nx * f * wj * dt * 2;
        b[oj + VY] -= ny * f * wj * dt * 2;
        continue;
      }
      const overlap = sum - d;
      const canStick = !fixI && !fixJ && b[oi + NB] < 3 && b[oj + NB] < 3 && Math.min(ri, rj) > 12;
      if (vrel < 0 && -vrel < STICK_V && canStick) {
        bond(s, i, j);
        kick(b, oi, 0.8, Math.atan2(ny, nx));
        kick(b, oj, 0.8, Math.atan2(ny, nx));
        s.ev[E_STICK] += 1;
        continue;
      }
      if (vrel < 0) {
        const e = 0.45;
        const jimp = -(1 + e) * vrel;
        b[oi + VX] -= nx * jimp * wi;
        b[oi + VY] -= ny * jimp * wi;
        b[oj + VX] += nx * jimp * wj;
        b[oj + VY] += ny * jimp * wj;
        const kk = Math.min(1.5, -vrel / 120);
        kick(b, oi, kk * (60 / ri), Math.atan2(ny, nx));
        kick(b, oj, kk * (60 / rj), Math.atan2(ny, nx));
      }
      // separate (soft)
      const c = Math.min(overlap, 6) * 0.5;
      b[oi + X] -= nx * c * wi * 2;
      b[oi + Y] -= ny * c * wi * 2;
      b[oj + X] += nx * c * wj * 2;
      b[oj + Y] += ny * c * wj * 2;
    }
  }

  // ── integrate, cull ──
  for (let i = 0; i < MAXB; i++) {
    const o = i * BF;
    if (b[o + ALIVE] !== 1 || b[o + POP] >= 0 || b[o + LAYER] !== 0) continue;
    b[o + X] += b[o + VX] * dt;
    b[o + Y] += b[o + VY] * dt;
    const r = b[o + R];
    // a bubble that sinks to the bottom edge touches the lawn and bursts
    if (b[o + Y] > inp.h - r * 0.25) pop(s, i, 0, -0.9, 0.4);
    else if (b[o + Y] < -r * 1.4 || (b[o + X] < -r * 1.6 && b[o + VX] < 0) || (b[o + X] > inp.w + r * 1.6 && b[o + VX] > 0)) {
      // drifted out of the frame: free the slot and its partners' bond counts
      unbondAll(s, i);
      b[o + ALIVE] = 0;
    }
  }

  // ── clusters: label connected components of the bond graph ──
  for (let i = 0; i < MAXB; i++) b[i * BF + CL] = b[i * BF + NB] > 0 && b[i * BF + ALIVE] > 0 ? i + 1 : 0;
  for (let pass = 0; pass < 3; pass++) {
    for (let i = 0; i < MAXB; i++) {
      if (b[i * BF + CL] === 0) continue;
      for (let j = 0; j < MAXB; j++) {
        if (s.bonds[i * MAXB + j] && b[j * BF + CL] > 0 && b[j * BF + CL] < b[i * BF + CL]) b[i * BF + CL] = b[j * BF + CL];
      }
    }
  }

  // ── droplets ──
  const d = s.d;
  const dd = Math.exp(-1.8 * dt);
  for (let k = 0; k < MAXD * DF; k += DF) {
    if (d[k + 5] >= d[k + 6]) continue;
    d[k + 5] += dt;
    d[k + 2] *= dd;
    d[k + 3] = d[k + 3] * dd + DG * dt;
    d[k] += d[k + 2] * dt;
    d[k + 1] += d[k + 3] * dt;
  }
  s.tick++;
};

export { RMAX };
