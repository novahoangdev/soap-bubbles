/**
 * Bubble pool: a fixed number of slots, every field in one flat number array (mutated in place on the UI thread, no allocation
 * per frame). Coordinates in design pt (440×956 frame, y down); time in scene seconds (already scaled by TIMESCALE).
 */
export const MAXB = 32;
/** fields per bubble */
export const BF = 26;
export const X = 0,
  Y = 1,
  VX = 2,
  VY = 3,
  R = 4,
  /** 0 = empty slot, 1 = free bubble, 2 = attached to the wand (still being blown) */
  ALIVE = 5,
  AGE = 6,
  LIFE = 7,
  SEED = 8,
  /** wobble: ellipse mode amplitude, velocity, angle; trefoil mode amplitude, velocity, angle */
  A2 = 9,
  V2 = 10,
  P2 = 11,
  A3 = 12,
  V3 = 13,
  P3 = 14,
  /** pop hole angle (rad); < 0 = intact */
  POP = 15,
  /** pop origin on the unit sphere (y up, z toward viewer) */
  PX = 16,
  PY = 17,
  PZ = 18,
  /** cluster id (0 = alone) */
  CL = 19,
  /** film thickness scale */
  TH = 20,
  BORN = 21,
  /** number of bonds */
  NB = 22,
  /** demo: scene time at which this bubble must pop by itself (0 = use LIFE) */
  DUE = 23,
  /** defocus blur radius (pt) for depth-of-field bubbles */
  BLUR = 24,
  /** depth layer: 0 = in focus (interactive), −1 = far background, +1 = near foreground (decorative, no contacts) */
  LAYER = 25;

/** droplets: x, y, vx, vy, size, age, life */
export const MAXD = 520;
export const DF = 7;

/** wand state: attached slot, bulge, bulge velocity, film form (≤ 0 gone, 1 settled), flap, quiet time, spray accumulator, peak breath, grow time */
export const W_ATT = 0,
  W_BULGE = 1,
  W_BULGEV = 2,
  W_FORM = 3,
  W_FLAP = 4,
  W_QUIET = 5,
  W_SPRAY = 6,
  W_PEAK = 7,
  W_GROW = 8;
export const WF = 9;

/** events for the JS side (haptics / sounds): pops this frame, pinch-offs, spray bubbles, sticks */
export const E_POP = 0,
  E_PINCH = 1,
  E_SPRAY = 2,
  E_STICK = 3,
  E_BIGPOP = 4;
export const EF = 5;

export type Sim = {
  b: number[];
  bonds: number[];
  d: number[];
  dNext: number;
  w: number[];
  ev: number[];
  rng: number;
  tick: number;
};

export const makeSim = (seed = 1234567): Sim => {
  const w = new Array(WF).fill(0);
  w[W_ATT] = -1;
  w[W_FORM] = 1;
  return {
    b: new Array(MAXB * BF).fill(0),
    bonds: new Array(MAXB * MAXB).fill(0),
    d: new Array(MAXD * DF).fill(0),
    dNext: 0,
    w,
    ev: new Array(EF).fill(0),
    rng: seed,
    tick: 0,
  };
};

/** deterministic random (mulberry32) so demo recordings repeat exactly */
export const rnd = (s: Sim) => {
  "worklet";
  s.rng = (s.rng + 0x6d2b79f5) | 0;
  let t = s.rng;
  t = Math.imul(t ^ (t >>> 15), t | 1);
  t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
  return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
};

export const spawn = (s: Sim, x: number, y: number, r: number, vx: number, vy: number, th: number, t: number) => {
  "worklet";
  const b = s.b;
  let slot = -1;
  for (let i = 0; i < MAXB; i++) {
    if (b[i * BF + ALIVE] === 0) {
      slot = i;
      break;
    }
  }
  if (slot < 0) return -1;
  const o = slot * BF;
  for (let k = 0; k < BF; k++) b[o + k] = 0;
  b[o + X] = x;
  b[o + Y] = y;
  b[o + VX] = vx;
  b[o + VY] = vy;
  b[o + R] = r;
  b[o + ALIVE] = 1;
  b[o + LIFE] = 9 + rnd(s) * 11;
  b[o + SEED] = rnd(s) * 10;
  b[o + P2] = rnd(s) * Math.PI;
  b[o + P3] = rnd(s) * Math.PI;
  b[o + POP] = -1;
  b[o + TH] = th;
  b[o + BORN] = t;
  for (let j = 0; j < MAXB; j++) {
    s.bonds[slot * MAXB + j] = 0;
    s.bonds[j * MAXB + slot] = 0;
  }
  return slot;
};

export const bond = (s: Sim, i: number, j: number) => {
  "worklet";
  if (s.bonds[i * MAXB + j]) return;
  s.bonds[i * MAXB + j] = 1;
  s.bonds[j * MAXB + i] = 1;
  s.b[i * BF + NB] += 1;
  s.b[j * BF + NB] += 1;
};

export const unbondAll = (s: Sim, i: number) => {
  "worklet";
  for (let j = 0; j < MAXB; j++) {
    if (s.bonds[i * MAXB + j]) {
      s.bonds[i * MAXB + j] = 0;
      s.bonds[j * MAXB + i] = 0;
      s.b[j * BF + NB] -= 1;
      // the neighbour springs back into a sphere: a gentle wobble (big bubbles less), along the old wall's axis when it is
      // still, otherwise projected onto its current wobble so the shape never jumps between frames (v26)
      const o = j * BF;
      const amt = 1.2 * Math.min(1, Math.sqrt(50 / Math.max(s.b[o + R], 1)));
      const ang = Math.atan2(s.b[i * BF + Y] - s.b[o + Y], s.b[i * BF + X] - s.b[o + X]);
      if (Math.abs(s.b[o + A2]) < 0.015) {
        s.b[o + P2] = ang;
        s.b[o + V2] += amt;
      } else s.b[o + V2] += amt * Math.cos(2 * (ang - s.b[o + P2]));
    }
  }
  s.b[i * BF + NB] = 0;
};

/** start popping bubble i from the sphere point (px, py, pz) (unit, y up, z toward the viewer) */
export const pop = (s: Sim, i: number, px: number, py: number, pz: number) => {
  "worklet";
  const o = i * BF;
  if (s.b[o + ALIVE] === 0 || s.b[o + POP] >= 0) return;
  if (s.b[o + ALIVE] === 2) {
    s.w[W_ATT] = -1;
    s.w[W_FORM] = -0.35;
    s.b[o + ALIVE] = 1;
  }
  const l = Math.hypot(px, py, pz) || 1;
  s.b[o + POP] = 0.15; // the first frame already shows a torn hole, not a clean ellipse
  s.b[o + PX] = px / l;
  s.b[o + PY] = py / l;
  s.b[o + PZ] = pz / l;
  // bonds stay while the hole sweeps (v28): the shared walls keep both bubbles' outlines until the film is gone, then the
  // neighbours spring round (step.ts unbonds at the end of the pop)
  s.ev[E_POP] += 1;
  if (s.b[o + R] > 70) s.ev[E_BIGPOP] += 1;
};

/** pop the top-most bubble under (x, y); returns its slot or −1 */
export const popAt = (s: Sim, x: number, y: number) => {
  "worklet";
  for (let i = MAXB - 1; i >= 0; i--) {
    const o = i * BF;
    if (s.b[o + ALIVE] === 0 || s.b[o + POP] >= 0 || s.b[o + LAYER] !== 0) continue;
    const r = s.b[o + R];
    const dx = (x - s.b[o + X]) / r, dy = (y - s.b[o + Y]) / r;
    const d2 = dx * dx + dy * dy;
    if (d2 > 1.12 * 1.12) continue;
    const k = d2 > 1 ? 1 / Math.sqrt(d2) : 1;
    const qx = dx * k, qy = dy * k;
    pop(s, i, qx, -qy, Math.sqrt(Math.max(0, 1 - qx * qx - qy * qy)));
    return i;
  }
  return -1;
};

/** top-most interactive bubble under (x, y), or −1 */
export const hitTest = (s: Sim, x: number, y: number) => {
  "worklet";
  for (let i = MAXB - 1; i >= 0; i--) {
    const o = i * BF;
    if (s.b[o + ALIVE] !== 1 || s.b[o + POP] >= 0 || s.b[o + LAYER] !== 0) continue;
    if (Math.hypot(x - s.b[o + X], y - s.b[o + Y]) < s.b[o + R]) return i;
  }
  return -1;
};

/** nearest live bubble to (x, y) (demo taps aim at bubbles, not at fixed points) */
/** a decorative out-of-focus bubble drifting at another depth */
export const spawnDecor = (s: Sim, x: number, y: number, r: number, vx: number, vy: number, layer: number, blur: number) => {
  "worklet";
  const i = spawn(s, x, y, r, vx, vy, 0.9, 0);
  if (i < 0) return -1;
  const o = i * BF;
  s.b[o + LAYER] = layer;
  s.b[o + BLUR] = blur;
  s.b[o + LIFE] = 1e9;
  s.b[o + AGE] = 2;
  return i;
};

export const nearest = (s: Sim, x: number, y: number, minR = 0) => {
  "worklet";
  let best = -1, bd = 1e9;
  for (let i = 0; i < MAXB; i++) {
    const o = i * BF;
    if (s.b[o + ALIVE] !== 1 || s.b[o + POP] >= 0 || s.b[o + R] < minR || s.b[o + LAYER] !== 0) continue;
    const d = Math.hypot(s.b[o + X] - x, s.b[o + Y] - y);
    if (d < bd) {
      bd = d;
      best = i;
    }
  }
  return best;
};
