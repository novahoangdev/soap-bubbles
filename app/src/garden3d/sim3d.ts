import * as THREE from "three";

/**
 * Bubbles in a 3D garden (metres, y up, the player looks along −z). Plain JS on the JS thread (a few dozen bubbles).
 *  - blowing: breath 0…1 inflates a film on the wand ring; when the breath eases (or the bubble is big enough) it pinches
 *    off and flies away along the breath, then drifts with the breeze, slowly sinking, swaying, wobbling
 *  - a sharp strong puff sprays a stream of small bubbles
 *  - bubbles age, thin to black film from the top and pop; they also pop on the ground, on plants, or on a tap
 */
export const MAXB = 96;

export type Bubble = {
  alive: boolean;
  p: THREE.Vector3;
  v: THREE.Vector3;
  r: number;
  age: number;
  life: number;
  seed: number;
  th: number;
  /** < 0 intact; ≥ 0 seconds since it tore */
  pop: number;
  popDir: THREE.Vector3;
  /** wobble: amplitude, phase, axis */
  wa: number;
  wp: number;
  wAxis: THREE.Vector3;
  /** still on the ring */
  attached: boolean;
  big: boolean;
  /** while on the ring: the radius it leaves at (a quick bubble of a breath's start or a strong blow), 0 = grows with the breath */
  goal: number;
};

export type Sim3D = {
  b: Bubble[];
  t: number;
  /** the bubble being blown on the ring (index) or −1 */
  growing: number;
  breathPeak: number;
  lastBreath: number;
  puffCool: number;
  /** seconds of the current unbroken breath */
  breathOn: number;
  /** quick little bubbles still to come off the ring after a sharp puff, and the time to the next */
  trail: number;
  trailT: number;
  /** the wand's ring plane (point, normal = the blowing direction): free bubbles never come back in front of it */
  planeP: THREE.Vector3;
  planeN: THREE.Vector3;
  rng: () => number;
  /** latest big bubble released (camera follows it) */
  hero: number;
  heroT: number;
  events: { pops: number; big: number; release: number; spray: number };
};

const mulberry = (seed: number) => () => {
  seed |= 0;
  seed = (seed + 0x6d2b79f5) | 0;
  let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
  t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
  return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
};

export const makeSim3D = (seed = 7): Sim3D => {
  const b: Bubble[] = [];
  for (let i = 0; i < MAXB; i++)
    b.push({
      alive: false, p: new THREE.Vector3(), v: new THREE.Vector3(), r: 0, age: 0, life: 1, seed: 0, th: 1, pop: -1,
      popDir: new THREE.Vector3(0, 1, 0), wa: 0, wp: 0, wAxis: new THREE.Vector3(0, 1, 0), attached: false, big: false, goal: 0,
    });
  return { b, t: 0, growing: -1, breathPeak: 0, lastBreath: 0, puffCool: 0, breathOn: 0, trail: 0, trailT: 0, planeP: new THREE.Vector3(), planeN: new THREE.Vector3(0, 0, -1), rng: mulberry(seed), hero: -1, heroT: 0, events: { pops: 0, big: 0, release: 0, spray: 0 } };
};

const spawn = (s: Sim3D, p: THREE.Vector3, r: number) => {
  let i = s.b.findIndex((x) => !x.alive);
  if (i < 0) {
    // recycle the oldest free-flying one
    let best = -1, ba = -1;
    s.b.forEach((x, k) => { if (!x.attached && k !== s.hero && x.age > ba) { ba = x.age; best = k; } });
    i = best;
    if (i < 0) return -1;
  }
  const x = s.b[i];
  x.alive = true; x.p.copy(p); x.v.set(0, 0, 0); x.r = r; x.age = 0; x.seed = s.rng() * 10; x.th = 0.85 + s.rng() * 0.3;
  x.life = 9 + s.rng() * 9; x.pop = -1; x.wa = 0; x.wp = s.rng() * 6; x.attached = false; x.big = false; x.goal = 0;
  x.wAxis.set(s.rng() - 0.5, s.rng() - 0.5, s.rng() - 0.5).normalize();
  return i;
};

export const popBubble = (s: Sim3D, i: number, dir?: THREE.Vector3) => {
  const x = s.b[i];
  if (!x.alive || x.pop >= 0) return;
  x.pop = 0;
  if (dir) x.popDir.copy(dir).normalize();
  else x.popDir.set(s.rng() - 0.5, 0.8, s.rng() - 0.5).normalize();
  s.events.pops++;
  if (x.r > 0.09) s.events.big++;
  if (s.growing === i) s.growing = -1;
};

/** gentle breeze: a slow drift across the garden with lazy gusts and curls (m/s) */
const breeze = (t: number, p: THREE.Vector3, out: THREE.Vector3) =>
  out.set(
    0.05 + 0.12 * Math.sin(t * 0.21 + p.z * 0.15) + 0.08 * Math.sin(t * 0.7 + p.y * 1.3),
    0.04 * Math.sin(t * 0.33 + p.x * 0.4),
    -0.1 + 0.08 * Math.cos(t * 0.17 + p.x * 0.2),
  );

const tmp = new THREE.Vector3();
const tmp2 = new THREE.Vector3();

/** a perpendicular to the blowing direction (random), for a little sideways scatter */
const side = (s: Sim3D, fwd: THREE.Vector3, out: THREE.Vector3, amt: number) => {
  out.set(s.rng() - 0.5, s.rng() - 0.5, s.rng() - 0.5);
  out.addScaledVector(fwd, -out.dot(fwd));
  return out.multiplyScalar(amt * 2);
};

/** a little quick bubble off the ring (a puff's trail): from somewhere across the film, along the breath */
const blowOne = (s: Sim3D, ring: THREE.Vector3, fwd: THREE.Vector3, up: THREE.Vector3, breath: number) => {
  const r = 0.012 + 0.026 * Math.pow(s.rng(), 1.4);
  const i = spawn(s, ring, r);
  if (i < 0) return;
  const x = s.b[i];
  x.p.add(side(s, fwd, tmp, 0.012)).addScaledVector(fwd, r + 0.006);
  x.v.copy(fwd).multiplyScalar(0.45 + s.rng() * 0.4 * (0.5 + breath)).add(side(s, fwd, tmp, 0.1)).addScaledVector(up, 0.05 + s.rng() * 0.08);
  x.life = 7 + s.rng() * 9;
  x.wa = 0.1 + s.rng() * 0.06;
};

/** free bubbles stay beyond the wand (user: "the bubbles must be behind the wand"; one drifting back past the ring,
 * right in front of the lens, filled the frame) */
const keepBeyond = (s: Sim3D, x: Bubble) => {
  const d = tmp2.copy(x.p).sub(s.planeP).dot(s.planeN), m = x.r + 0.012;
  if (d < m) {
    x.p.addScaledVector(s.planeN, m - d);
    const vn = x.v.dot(s.planeN);
    if (vn < 0.05) x.v.addScaledVector(s.planeN, 0.05 - vn);
  }
};

/**
 * One step. ring: world position of the wand ring centre, fwd: the direction the breath blows (the camera forward),
 * breath 0…1, groundAt(x, z): ground height.
 */
export const stepSim3D = (s: Sim3D, dt: number, ring: THREE.Vector3, fwd: THREE.Vector3, up: THREE.Vector3, breath: number, groundAt: (x: number, z: number) => number) => {
  s.t += dt;
  s.puffCool = Math.max(0, s.puffCool - dt);
  const db = (breath - s.lastBreath) / Math.max(dt, 1e-3);
  s.lastBreath = breath;
  // ── blowing ── (like a real wand: bubbles come off the ring one after another, a few small quick ones as a breath
  // starts and all through a strong blow, while a long steady breath grows one big one; g34 threw a cloud of 20+ at once)
  if (breath > 0.12) {
    s.breathOn += dt;
    s.planeP.copy(ring);
    s.planeN.copy(fwd);
    if (s.growing < 0 || !s.b[s.growing].alive) {
      const quick = s.breathOn < 2.4 || breath > 0.55;
      const i = spawn(s, ring, quick ? 0.012 : 0.03);
      if (i >= 0) {
        s.growing = i;
        s.b[i].attached = true;
        // (quick ones: mostly 2–4 cm, now and then a 5 cm one)
        s.b[i].goal = quick ? 0.017 + 0.036 * Math.pow(s.rng(), 1.4) : 0;
        if (!quick) s.breathPeak = 0;
      }
    }
    s.breathPeak = Math.max(s.breathPeak, breath);
    // a sharp puff: a short trail of little ones right after the one on the ring
    if (db > 6 && breath > 0.55 && s.puffCool <= 0) {
      s.puffCool = 0.25;
      s.events.spray++;
      s.trail = 5 + Math.floor(s.rng() * 4);
      s.trailT = 0.04;
    }
  } else s.breathOn = 0;
  if (s.trail > 0) {
    s.trailT -= dt;
    if (s.trailT <= 0) {
      blowOne(s, ring, fwd, up, Math.max(breath, 0.5));
      s.trail--;
      s.trailT = 0.05 + s.rng() * 0.05;
    }
  }
  if (s.growing >= 0) {
    const g = s.b[s.growing];
    if (!g.alive) s.growing = -1;
    else {
      g.p.copy(ring).addScaledVector(fwd, g.r * 0.85);
      if (g.goal > 0) {
        // a quick one swells fast and lets go at its size, along the breath with a little wander
        // (a gentle breath lets one go every ~0.35 s, a strong one ~7 a second)
        g.r += dt * (0.035 + 0.32 * breath * breath);
        if (g.r >= g.goal || breath < 0.1) {
          if (g.r < 0.012) { g.alive = false; s.growing = -1; }
          else {
            g.attached = false;
            g.goal = 0;
            g.v.copy(fwd).multiplyScalar(0.35 + 0.6 * breath + s.rng() * 0.15).add(side(s, fwd, tmp, 0.08)).addScaledVector(up, 0.06 + s.rng() * 0.06);
            g.wa = 0.14;
            g.life = 8 + s.rng() * 9;
            s.growing = -1;
            s.events.release++;
          }
        }
      }
    }
  }
  if (s.growing >= 0 && s.b[s.growing].goal === 0) {
    const g = s.b[s.growing];
    {
      // inflates with the breath; big ones need a long steady breath
      g.r += dt * breath * 0.09 * (1.2 - Math.min(1, g.r / 0.22));
      g.wa = Math.min(0.18, g.wa + dt * breath * 0.4);
      // (a strong blow never grows a big one: g34's long strong blow grew a second big one and the camera flew off)
      const strong = breath > 0.55;
      const release = (breath < 0.1 && g.r > 0.045) || g.r > 0.2 || (breath < s.breathPeak - 0.35 && g.r > 0.06) || (strong && g.r > 0.04);
      if (breath < 0.1 && g.r <= 0.045) {
        // too small to leave the ring: the film just collapses back
        g.alive = false;
        s.growing = -1;
      } else if (release) {
        g.attached = false;
        g.big = g.r > 0.075 && !strong;
        g.v.copy(fwd).multiplyScalar(0.5 + 1.3 * s.breathPeak).addScaledVector(up, 0.15);
        g.wa = 0.16;
        s.growing = -1;
        s.events.release++;
        if (g.big) {
          s.hero = s.b.indexOf(g);
          s.heroT = s.t;
          g.life = Math.max(g.life, 34); // the camera follows it for a long, slow while
        }
      }
    }
  }
  // ── flight ──
  for (let i = 0; i < MAXB; i++) {
    const x = s.b[i];
    if (!x.alive) continue;
    if (x.pop >= 0) {
      x.pop += dt;
      if (x.pop > 0.09 * Math.min(2, Math.max(1, Math.sqrt(x.r / 0.05)))) { x.alive = false; if (s.hero === i) s.hero = -1; }
      continue;
    }
    x.wp += dt * (9 + 0.35 / Math.max(x.r, 0.02));
    x.wa *= Math.exp(-dt * 1.4);
    if (x.attached) continue;
    x.age += dt / x.life;
    if (x.age >= 1) { popBubble(s, i); continue; }
    const hero = i === s.hero && x.big;
    if (hero) {
      // the big one rides a steady breeze down the meadow, far into the garden (the camera follows it): little drag, a
      // lazy side-to-side sway, and it floats up to ~1 m and bobs there instead of sinking into the flowers
      // (before, it stopped ~1.5 m from the wand and the "follow" barely moved)
      // (round 13: drawn back to the middle of the meadow, so the camera looks down the clearing to the hazy far wood
      // instead of into the side row of trees)
      tmp.set(0.2 * Math.sin(s.t * 0.3 + x.seed) - 0.18 * x.p.x, 0, -0.2);
      // (~0.8 m: the camera, level with it, then sees the flowers come by in the foreground)
      const hy = 0.78 + 0.1 * Math.sin(s.t * 0.7 + x.seed) - x.p.y;
      tmp.y = hy * 0.6;
    } else breeze(s.t, x.p, tmp);
    // drag toward the air's motion (small bubbles follow it closely), a slight net sink (the film is heavier than air)
    const k = hero ? 0.32 : 1.2 + 0.03 / Math.max(x.r, 0.01);
    tmp2.copy(tmp).sub(x.v).multiplyScalar(1 - Math.exp(-k * dt));
    x.v.add(tmp2);
    if (!hero) x.v.y -= dt * (0.05 + 0.25 * x.r);
    x.p.addScaledVector(x.v, dt);
    keepBeyond(s, x);
    const gy = groundAt(x.p.x, x.p.z) + 0.12;
    // (not in its first 1.5 s: a big one leaves the low wand with its bottom already in the grass tips, and rises)
    if (x.age * x.life > 1.5 && x.p.y - x.r < gy) popBubble(s, i, tmp.set(0, -1, 0));
  }
  // ── bubbles touching: bounce softly (sticking is the 2D app's job; in the open air they mostly glance off) ──
  for (let i = 0; i < MAXB; i++) {
    const a = s.b[i];
    if (!a.alive || a.pop >= 0 || a.attached) continue;
    for (let j = i + 1; j < MAXB; j++) {
      const c = s.b[j];
      if (!c.alive || c.pop >= 0 || c.attached) continue;
      tmp.subVectors(c.p, a.p);
      const d = tmp.length(), sum = a.r + c.r;
      if (d >= sum || d < 1e-5) continue;
      tmp.multiplyScalar(1 / d);
      const o = (sum - d) * 0.5;
      a.p.addScaledVector(tmp, -o);
      c.p.addScaledVector(tmp, o);
      const vr = tmp2.subVectors(c.v, a.v).dot(tmp);
      if (vr < 0) { a.v.addScaledVector(tmp, vr * 0.5); c.v.addScaledVector(tmp, -vr * 0.5); }
      a.wa = Math.min(0.15, a.wa + 0.05);
      c.wa = Math.min(0.15, c.wa + 0.05);
      keepBeyond(s, a);
      keepBeyond(s, c);
    }
  }
};

const m4 = new THREE.Matrix4();
const q = new THREE.Quaternion();
const sc = new THREE.Vector3();
const yAxis = new THREE.Vector3(0, 1, 0);

/** instance matrix of bubble x: position, radius and a wobble stretch along its wobble axis */
export const bubbleMatrix = (x: Bubble, out: THREE.Matrix4) => {
  const w = x.wa * Math.sin(x.wp);
  q.setFromUnitVectors(yAxis, x.wAxis);
  sc.set(x.r * (1 - w * 0.5), x.r * (1 + w), x.r * (1 - w * 0.5));
  m4.compose(x.p, q, sc);
  // the film pattern must stay in the bubble's upright frame: undo the rotation for the pattern by keeping the stretch
  // only (rotate → scale → rotate back)
  const r = new THREE.Matrix4().makeRotationFromQuaternion(q);
  const ri = new THREE.Matrix4().makeRotationFromQuaternion(q.clone().invert());
  const s = new THREE.Matrix4().makeScale(sc.x, sc.y, sc.z);
  out.makeTranslation(x.p.x, x.p.y, x.p.z).multiply(r).multiply(s).multiply(ri);
  return out;
};
