import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Image as RNImage, StyleSheet, View, type LayoutChangeEvent } from "react-native";
import {
  Atlas, Canvas, FilterMode, Fill, Group, Image, ImageShader, MipmapMode, Rect, Shader, Skia, useRSXformBuffer,
  type SkImage,
} from "react-native-skia";
import { Gesture, GestureDetector } from "react-native-gesture-handler";
import { Easing, SensorType, useAnimatedSensor, useDerivedValue, useFrameCallback, useSharedValue, withTiming } from "react-native-reanimated";
import { scheduleOnRN } from "react-native-worklets";
import { bubblesFx } from "../shaders/bubbles";
import { wandFilmFx } from "../shaders/wandFilm";
import { postFx } from "../shaders/post";
import {
  A2, A3, AGE, ALIVE, BF, CL, DF, E_BIGPOP, E_PINCH, E_POP, E_SPRAY, E_STICK, EF, LIFE, MAXB, MAXD, P2, P3, POP, PX, PY, PZ, R,
  SEED, TH, BLUR, LAYER, V2, VX, VY, W_ATT, W_BULGE, W_FLAP, W_FORM, X, Y, DUE, bond, hitTest, makeSim, nearest, pop, popAt, rnd, spawn, spawnDecor, type Sim,
} from "../sim/pool";
import { step, type StepIn } from "../sim/step";
import { BreathMic } from "../audio/breath";
import { RING, VIEW, fitView } from "./layout";
import { LOOKS, START_LOOK } from "./looks";
import { TIMESCALE, ms } from "./clock";
import { DEMO as SCRIPT, demoBreath } from "../demo/script";
import { fireHaptic } from "../fx/haptics";
import { initSfx, sfx, startMusic } from "../fx/sfx";
import { MicHint } from "../ui/MicHint";

/** EXPO_PUBLIC_DEMO=1: the app plays the storyboard by itself for recording. */
const DEMO = process.env.EXPO_PUBLIC_DEMO === "1";
/** dev: log scene events with their times (to sync the clip's sound effects) */
const EVLOG = process.env.EXPO_PUBLIC_EVLOG === "1";
/** fixed physics step (s of scene time): the demo plays out identically on every run, whatever the frame timing */
const PH = 1 / 120;
/** dev / demo: EXPO_PUBLIC_LOOKSWITCH=7.4 crossfades to the other look at that scene time (golden hour → twilight) */
const LOOK_SWITCH = DEMO ? Number(process.env.EXPO_PUBLIC_LOOKSWITCH ?? "0") || 0 : 0;
const LOOK_FADE = 1.6;
/** dev: EXPO_PUBLIC_T0=9.5 fast-forwards the demo to that scene time on launch (inspect late beats with a slow clock) */
const START_T = DEMO ? Math.max(0, Number(process.env.EXPO_PUBLIC_T0 ?? "0") || 0) : 0;

const LINEAR = { filter: FilterMode.Linear, mipmap: MipmapMode.None };

/** droplet sprites (v26): a pin-head bead and the same bead smeared along its path by the shutter, neutral (they mirror the
 *  scene, not a warm glow), 32 px */
const DS = 32;
const makeDrop = (streak: boolean): SkImage => {
  const surf = Skia.Surface.MakeRaster(DS, DS)!;
  const c = surf.getCanvas();
  c.clear(Skia.Color("transparent"));
  const p = Skia.Paint();
  p.setAntiAlias(true);
  p.setShader(
    Skia.Shader.MakeRadialGradient(
      { x: DS / 2, y: DS / 2 },
      DS / 2,
      [Skia.Color("rgba(255,250,240,1)"), Skia.Color("rgba(240,240,245,0.6)"), Skia.Color("rgba(230,235,245,0.12)"), Skia.Color("rgba(230,235,245,0)")],
      [0, 0.25, 0.55, 1],
      0,
    ),
  );
  if (streak) {
    // 4:1 capsule: the bead's travel during one exposure
    c.save();
    c.scale(1, 0.25);
    c.translate(0, DS * 1.5);
  }
  c.drawCircle(DS / 2, DS / 2, DS / 2, p);
  if (streak) c.restore();
  return surf.makeImageSnapshot();
};
const DROP_RECT = Skia.XYWHRect(0, 0, DS, DS);
/** droplets faster than this (pt/s) are drawn as streaks */
const STREAK_V = 240;
type XfOut = { set: (scos: number, ssin: number, tx: number, ty: number) => void };
const dropXform = (d: number[], i: number, streak: boolean, val: XfOut) => {
  "worklet";
  const o = i * DF;
  const vx = d[o + 2], vy = d[o + 3];
  const v = Math.hypot(vx, vy);
  if (d[o + 5] >= d[o + 6] || v > STREAK_V !== streak) {
    val.set(0.001, 0, -1e4, -1e4);
    return;
  }
  const life = d[o + 5] / d[o + 6];
  const k = (d[o + 4] * 2 * (1 - 0.6 * life * life)) / DS;
  const c = streak ? (k * vx) / v : k, sn = streak ? (k * vy) / v : 0;
  // RSXform maps the sprite centre (DS/2, DS/2) onto the droplet
  val.set(c, sn, d[o] - (c * DS - sn * DS) / 2, d[o + 1] - (sn * DS + c * DS) / 2);
};

/** load several bundled images at once (useImage takes one; the number of looks is fixed at build time) */
const useImages = (srcs: number[]): SkImage[] | null => {
  const [imgs, setImgs] = useState<SkImage[] | null>(null);
  useEffect(() => {
    let live = true;
    Promise.all(srcs.map((src) => Skia.Data.fromURI(RNImage.resolveAssetSource(src)?.uri ?? "").then((d) => Skia.Image.MakeFromEncoded(d)!)))
      .then((r) => live && setImgs(r))
      .catch(() => {});
    return () => {
      live = false;
    };
    // the sources are module constants
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  return imgs;
};

const seedDemo = (s: Sim) => {
  const ids: number[] = [];
  for (const p of SCRIPT.pre) {
    const i = spawn(s, p.x, p.y, p.r, p.vx, p.vy, p.th, -SCRIPT.prewarm);
    ids.push(i);
    if (i < 0) continue;
    s.b[i * BF + LIFE] = 60;
    s.b[i * BF + AGE] = 1.5 + rnd(s) * 2;
    for (const j of p.bondTo ?? []) if (ids[j] >= 0) bond(s, ids[j], i);
  }
};

const RUN_SEED = Date.now() & 0x7fffffff;
/** depth of field: two big soft bubbles drifting close to the lens (v28: the three tiny far ones read as flat outlined
 *  circles next to the in-focus bubbles and were dropped; v37: they drift visibly, standing still they read as lens smudges; v38: along the frame edges, never across the wand) */
const DECOR = [
  { x: 14, y: 700, r: 104, vx: -2, vy: -3, layer: 1, blur: 30 },
  { x: 436, y: 92, r: 86, vx: 1.5, vy: -1, layer: 1, blur: 24 },
];
const initialSim = (): Sim => {
  const s = makeSim(DEMO ? SCRIPT.seed : RUN_SEED);
  for (const d of DECOR) spawnDecor(s, d.x, d.y, d.r, d.vx, d.vy, d.layer, d.blur);
  if (DEMO) seedDemo(s);
  else {
    // a few bubbles already in the air so the first look isn't empty
    for (const p of SCRIPT.pre.slice(0, 3)) {
      const i = spawn(s, p.x, p.y, p.r, p.vx, p.vy, p.th, 0);
      if (i >= 0) s.b[i * BF + AGE] = 1;
    }
  }
  return s;
};

type U = {
  envSize: number[];
  envU0: number;
  envGain: number;
  sunDir: number[];
  sunGain: number;
  win: number[];
  winCol: number[];
  lookK: number[];
  filmF: number;
  softSky: number[];
  softGround: number[];
  time: number;
  bA: number[];
  bW: number[];
  bF: number[];
  bP: number[];
  bD: number[];
  layer: number;
};

export function BubbleScene() {
  // every look stays loaded so switching is instant (a crossfade of the pictures; the reflections switch at the midpoint)
  const bgs = useImages(LOOKS.map((l) => l.bg));
  const envs = useImages(LOOKS.map((l) => l.env));
  const wands = useImages(LOOKS.map((l) => l.wand));
  const [lookI, setLookI] = useState(START_LOOK);
  const look = LOOKS[lookI];
  const envImg = envs?.[lookI] ?? null;
  const ready = !!(bgs && envs && wands);
  /**
   * Two crossfade layers (v35: any number of looks): layer A shows look layA at full opacity, layer B shows look layB on top
   * at opacity mixL. A switch loads the next look into whichever layer is hidden and fades toward it.
   */
  const [layA, setLayA] = useState(START_LOOK);
  const [layB, setLayB] = useState(START_LOOK);
  const mixL = useSharedValue(0);
  /** env gains of layers A and B (the exposure glides between them during a crossfade) */
  const layG = useSharedValue([LOOKS[START_LOOK].envGain, LOOKS[START_LOOK].envGain]);
  const op1 = useDerivedValue(() => mixL.value);
  const dropDot = useMemo(() => makeDrop(false), []);
  const dropStreak = useMemo(() => makeDrop(true), []);
  const dropSprites = useMemo(() => new Array(MAXD).fill(DROP_RECT), []);

  const [size, setSize] = useState({ w: VIEW.w, h: VIEW.h });
  const fit = useMemo(() => fitView(size.w, size.h), [size]);
  const fitS = useSharedValue(fit);
  useEffect(() => fitS.set(fit), [fit, fitS]);
  const sceneT = useMemo(() => [{ translateX: fit.ox }, { translateY: fit.oy }, { scale: fit.k }], [fit]);

  const [sim0] = useState(initialSim);
  const sim = useSharedValue<Sim>(sim0);
  const time = useSharedValue(DEMO ? -SCRIPT.prewarm : 0);
  const breath = useSharedValue(0);
  const fakeBreath = useSharedValue(0);
  const panBreath = useSharedValue(false);
  const grabbed = useSharedValue(-1);
  const downPt = useSharedValue([0, 0]);
  const hintBreath = useDerivedValue(() => Math.max(breath.value, fakeBreath.value));
  const finger = useSharedValue([0, 0, 0, 0, 0]); // x, y, vx, vy, active
  const gravity = useAnimatedSensor(SensorType.GRAVITY, { interval: 16 });
  /**
   * Handheld camera (v31): real phone footage is never perfectly still. The demo drifts a few points with a slow sway and a
   * tiny roll; the app follows the phone's tilt (like the iOS parallax wallpaper). Parallax: the far garden moves a third as
   * much as the bubbles and the wand, which sit near the focal plane.
   */
  const cam = useDerivedValue(() => {
    if (DEMO) {
      const t = Math.max(0, time.value), P2 = Math.PI * 2;
      return [
        1.4 * Math.sin(P2 * 0.27 * t + 0.4) + 0.65 * Math.sin(P2 * 0.61 * t + 1.9) + 0.2 * Math.sin(P2 * 1.37 * t + 0.3),
        // a slight vertical bob (breathing while holding the phone)
        1.1 * Math.sin(P2 * 0.23 * t + 2.2) + 0.6 * Math.sin(P2 * 0.67 * t + 0.8) + 0.5 * Math.sin(P2 * 0.3 * t + 4.0),
        0.0015 * Math.sin(P2 * 0.19 * t + 1.3),
      ];
    }
    const g = gravity.sensor.value;
    return [-Math.max(-1, Math.min(1, g.x / 9.81)) * 5, Math.max(-1, Math.min(1, g.z / 9.81)) * 3, 0];
  });
  const layerT = (k: number, zoom: number) => {
    "worklet";
    const c = cam.value;
    return [
      { translateX: VIEW.w / 2 + c[0] * k },
      { translateY: VIEW.h / 2 + c[1] * k },
      { rotate: c[2] * k },
      { scale: zoom },
      { translateX: -VIEW.w / 2 },
      { translateY: -VIEW.h / 2 },
    ];
  };
  // the garden is scaled up a little so its edges never show while it shifts
  const bgT = useDerivedValue(() => layerT(0.35, 1.02));
  const nearT = useDerivedValue(() => layerT(1, 1));

  const inp = useSharedValue<StepIn>({
    breath: 0, rx: RING.x, ry: RING.y, rr: RING.r, fx: 0, fy: 0, fvx: 0, fvy: 0, fa: 0, gx: 0, gy: 0,
    grab: -1, hx: 0, hy: 0, hk: 0, kx: 0, ky: 0, kk: 0, bigDue: 0, w: VIEW.w, h: VIEW.h,
  });
  const mkU = (layer: number): U => ({
    envSize: [2048, 1024], envU0: LOOKS[START_LOOK].envU0, envGain: LOOKS[START_LOOK].envGain, sunDir: LOOKS[START_LOOK].sunDir,
    sunGain: LOOKS[START_LOOK].sunGain, win: LOOKS[START_LOOK].win, winCol: LOOKS[START_LOOK].winCol, lookK: LOOKS[START_LOOK].lookK, filmF: LOOKS[START_LOOK].filmF, softSky: LOOKS[START_LOOK].softSky, softGround: LOOKS[START_LOOK].softGround, time: 0,
    bA: new Array(MAXB * 4).fill(0), bW: new Array(MAXB * 4).fill(0), bF: new Array(MAXB * 4).fill(0), bP: new Array(MAXB * 4).fill(0),
    bD: new Array(MAXB * 4).fill(0), layer,
  });
  const bu = useSharedValue<U>(mkU(0));
  const buF = useSharedValue<U>(mkU(1));
  const fgR = useSharedValue([0, 0, 0, 0, 0, 0, 0, 0]);
  const fg0x = useDerivedValue(() => fgR.value[0]);
  const fg0y = useDerivedValue(() => fgR.value[1]);
  const fg0w = useDerivedValue(() => fgR.value[2]);
  const fg0h = useDerivedValue(() => fgR.value[3]);
  const fg1x = useDerivedValue(() => fgR.value[4]);
  const fg1y = useDerivedValue(() => fgR.value[5]);
  const fg1w = useDerivedValue(() => fgR.value[6]);
  const fg1h = useDerivedValue(() => fgR.value[7]);
  const fu = useSharedValue({
    envSize: [2048, 1024], envU0: LOOKS[START_LOOK].envU0, envGain: LOOKS[START_LOOK].envGain, sunDir: LOOKS[START_LOOK].sunDir,
    sunGain: LOOKS[START_LOOK].sunGain, win: LOOKS[START_LOOK].win, winCol: LOOKS[START_LOOK].winCol, lookK: LOOKS[START_LOOK].lookK, filmF: LOOKS[START_LOOK].filmF, softSky: LOOKS[START_LOOK].softSky, softGround: LOOKS[START_LOOK].softGround, time: 0,
    ring: [RING.x, RING.y, RING.r + 2], bulge: 0, form: 1, flap: 0,
  });
  const pu = useSharedValue({ time: 0, view: [VIEW.w, VIEW.h], sunUV: LOOKS[START_LOOK].sunUV, warm: LOOKS[START_LOOK].warm });
  useEffect(() => {
    if (!envImg) return;
    const lk = {
      // the env image is a three-level atlas (tools/env_atlas.sh): one level is a third of its height
      envSize: [envImg.width(), envImg.height() / 3], envU0: look.envU0, envGain: look.envGain, sunDir: look.sunDir, sunGain: look.sunGain,
      win: look.win, winCol: look.winCol, lookK: look.lookK, filmF: look.filmF,
      softSky: look.softSky, softGround: look.softGround,
    };
    bu.set({ ...bu.get(), ...lk });
    buF.set({ ...buF.get(), ...lk });
    fu.set({ ...fu.get(), ...lk });
    pu.set({ ...pu.get(), sunUV: look.sunUV, warm: look.warm });
  }, [envImg, look, bu, buF, fu, pu]);
  const toggleLook = useCallback(() => {
    const to = (lookI + 1) % LOOKS.length;
    // durations in scene time (ms() stretches them when the demo runs on a slowed clock)
    const fade = { duration: ms(LOOK_FADE * 1000), easing: Easing.inOut(Easing.cubic) };
    if (mixL.value > 0.5) {
      // B is showing: put the next look under it in A and fade B out
      setLayA(to);
      layG.set([LOOKS[to].envGain, LOOKS[layB].envGain]);
      mixL.set(withTiming(0, fade));
    } else {
      setLayB(to);
      layG.set([LOOKS[layA].envGain, LOOKS[to].envGain]);
      mixL.set(withTiming(1, fade));
    }
    // the reflections follow at the midpoint of the crossfade
    setTimeout(() => setLookI(to), ms(LOOK_FADE * 500));
    fireHaptic("medium");
  }, [lookI, layA, layB, mixL, layG]);

  useEffect(() => {
    initSfx();
    // a quiet music loop (simulator screen recordings carry no sound, so the demo can play it too)
    startMusic();
  }, []);
  const onEvents = useCallback((pops: number, pinch: number, spray: number, stick: number, big: number, t: number) => {
    if (EVLOG) console.log(`EVT ${t.toFixed(3)} pops=${pops} pinch=${pinch} spray=${spray} stick=${stick} big=${big}`);
    if (big > 0) sfx("pop_big");
    if (pops > big) sfx("pop", 0.8 + Math.random() * 0.2);
    if (pinch > 0) sfx("bloop");
    if (spray > 0) sfx("puff");
    if (stick > 0) sfx("stick");
    if (big > 0) fireHaptic("heavy");
    else if (pops > 0) fireHaptic(pops > 1 ? "medium" : "light");
    if (pinch > 0) fireHaptic("medium");
    if (stick > 0 && pops === 0) fireHaptic("select");
    if (spray > 0 && pops === 0 && pinch === 0) fireHaptic("select");
  }, []);

  // ── per-frame: clock, inputs, physics, uniforms ──
  const lastTs = useSharedValue(-1);
  const demoTap = useSharedValue(0);
  const readyS = useSharedValue(false);
  useEffect(() => readyS.set(ready), [ready, readyS]);
  const prewarmed = useSharedValue(!DEMO);
  const physT = useSharedValue(0);
  const holdN = useSharedValue(DEMO ? 40 : 0);
  const switched = useSharedValue(false);
  const syncMark = useSharedValue(DEMO ? 1 : 0);

  const fillOne = (u: U, s: Sim, t: number) => {
    "worklet";
    const b = s.b;
    // physics runs in fixed 1/120 s steps; at other refresh rates (ProMotion 80 Hz, dropped frames) a frame lands between
    // two steps: draw each bubble where its velocity carries it by then, so the motion doesn't judder (0 in demo recordings)
    const lead = Math.min(PH, Math.max(0, t - physT.value));
    for (let i = 0; i < MAXB; i++) {
      const o = i * BF, k = i * 4;
      const al = b[o + ALIVE] > 0 ? 1 : 0;
      const mv = b[o + ALIVE] === 1 ? lead : 0;
      u.bA[k] = b[o + X] + b[o + VX] * mv;
      u.bA[k + 1] = b[o + Y] + b[o + VY] * mv;
      u.bA[k + 2] = b[o + R];
      u.bA[k + 3] = al;
      u.bW[k] = b[o + A2];
      u.bW[k + 1] = b[o + P2];
      u.bW[k + 2] = b[o + A3];
      u.bW[k + 3] = b[o + P3];
      const life = b[o + DUE] > 0 ? b[o + AGE] + Math.max(0.5, b[o + DUE] - t) : b[o + LIFE];
      // demo: only the giant (the one with a scripted end) drains to black film; the rest stay before the black stage
      u.bF[k] = Math.min(DEMO && b[o + DUE] === 0 ? 0.84 : 1, b[o + AGE] / Math.max(0.5, life));
      u.bF[k + 1] = b[o + SEED];
      u.bF[k + 2] = b[o + CL];
      u.bF[k + 3] = b[o + POP];
      u.bP[k] = b[o + PX];
      u.bP[k + 1] = b[o + PY];
      u.bP[k + 2] = b[o + PZ];
      u.bP[k + 3] = b[o + TH];
      u.bD[k] = b[o + BLUR];
      u.bD[k + 1] = b[o + LAYER] > 0 ? 1 : b[o + LAYER] < 0 ? -1 : 0;
    }
    u.time = t;
  };
  const fillUniforms = (s: Sim, t: number) => {
    "worklet";
    // during a look crossfade the exposure glides between the looks and dips at the midpoint, where the env map swaps
    const m = mixL.value;
    if (m > 0.001 && m < 0.999) {
      const lg = layG.value;
      const g = (lg[0] * (1 - m) + lg[1] * m) * (1 - 0.55 * Math.sin(Math.PI * m));
      bu.value.envGain = g;
      buF.value.envGain = g;
      fu.value.envGain = g;
    }
    fillOne(bu.value, s, t);
    bu.modify();
    fillOne(buF.value, s, t);
    buF.modify();
    // the foreground pass only runs over the near (blurred) bubbles' bounds, not the whole screen
    const fr = fgR.value;
    let n = 0;
    for (let q = 0; q < MAXB && n < 2; q++) {
      const o = q * BF;
      if (s.b[o + ALIVE] === 0 || s.b[o + LAYER] <= 0) continue;
      const e = s.b[o + R] * 1.35 + 4 + s.b[o + BLUR];
      fr[n * 4] = s.b[o + X] - e;
      fr[n * 4 + 1] = s.b[o + Y] - e;
      fr[n * 4 + 2] = 2 * e;
      fr[n * 4 + 3] = 2 * e;
      n++;
    }
    for (; n < 2; n++) fr[n * 4 + 2] = fr[n * 4 + 3] = 0;
    // each rect runs the shader for every near bubble, so overlapping rects drew the overlap twice (bright bands with hard
    // vertical edges when the two drifted together): merge them into one
    if (fr[6] > 0 && fr[2] > 0 && fr[0] < fr[4] + fr[6] && fr[4] < fr[0] + fr[2] && fr[1] < fr[5] + fr[7] && fr[5] < fr[1] + fr[3]) {
      const x0 = Math.min(fr[0], fr[4]), y0 = Math.min(fr[1], fr[5]);
      fr[2] = Math.max(fr[0] + fr[2], fr[4] + fr[6]) - x0;
      fr[3] = Math.max(fr[1] + fr[3], fr[5] + fr[7]) - y0;
      fr[0] = x0;
      fr[1] = y0;
      fr[6] = fr[7] = 0;
    }
    fgR.modify();
    const f = fu.value;
    f.time = t;
    f.bulge = s.w[W_BULGE];
    // while a bubble is being blown the ring's film *is* that bubble: no separate flat film
    f.form = s.w[W_ATT] >= 0 ? 0 : s.w[W_FORM];
    f.flap = s.w[W_FLAP];
    fu.modify();
    const p = pu.value;
    p.time = t;
    pu.modify();
  };

  /** demo taps: aim at the bubble nearest the scripted point (processed inside the physics loop so fast-forward works) */
  const demoTaps = (s: Sim, t: number) => {
    "worklet";
    const taps = SCRIPT.taps;
    while (demoTap.value < taps.length && t >= taps[demoTap.value].at) {
      const tp = taps[demoTap.value];
      demoTap.value += 1;
      const j = nearest(s, tp.x, tp.y, 0);
      let best = -1, bd = 1e9;
      for (let q = 0; q < MAXB; q++) {
        const o = q * BF;
        const r = s.b[o + R];
        if (s.b[o + ALIVE] !== 1 || s.b[o + POP] >= 0 || r > tp.maxR || r < tp.minR || s.b[o + DUE] > 0) continue;
        // never a bubble cut by the screen edge: the pop has to read whole
        if (s.b[o + X] - r < 6 || s.b[o + X] + r > VIEW.w - 6) continue;
        // prefer bigger bubbles near the point, and cluster members (their neighbours spring back into spheres)
        const d = Math.hypot(s.b[o + X] - tp.x, s.b[o + Y] - tp.y) - 1.6 * r - (s.b[o + CL] > 0 ? 35 : 0);
        if (d < bd) {
          bd = d;
          best = q;
        }
      }
      // fallback: the nearest bubble of any size, but never the giant (its finale is scripted)
      const k = best >= 0 ? best : j >= 0 && s.b[j * BF + DUE] === 0 ? j : -1;
      if (k >= 0) {
        // pop exactly the chosen bubble (popAt would take whichever bubble is on top at that point), a little off-centre
        // toward the upper left like a real fingertip
        pop(s, k, -0.25, 0.2, Math.sqrt(1 - 0.25 * 0.25 - 0.2 * 0.2));
      }
    }
  };

  /** interactive app: when the air is quiet, a stray bubble from someone else's wand drifts in from a side now and then */
  const nextStray = useSharedValue(6);
  const ambient = (s: Sim, dt: number, t: number) => {
    "worklet";
    if (t < nextStray.value) return;
    let live = 0;
    for (let q = 0; q < MAXB; q++) if (s.b[q * BF + ALIVE] === 1 && s.b[q * BF + LAYER] === 0) live++;
    nextStray.value = t + 5 + rnd(s) * 7;
    if (live >= 6) return;
    const left = rnd(s) < 0.5;
    const r = 16 + rnd(s) * 34;
    spawn(s, left ? -r : VIEW.w + r, 220 + rnd(s) * 360, r, (left ? 1 : -1) * (40 + rnd(s) * 40), -10 - rnd(s) * 25, 0.7 + rnd(s) * 0.4, t);
    void dt;
  };

  const advance = (s: Sim, dt: number, t: number) => {
    "worklet";
    const i = inp.value;
    if (DEMO) {
      i.breath = demoBreath(t);
      i.hk = 0;
      for (const h of SCRIPT.herd) {
        if (t >= h.from && t <= h.to) {
          const e = Math.min(1, (t - h.from) / 0.6, (h.to - t) / 0.6);
          i.hx = h.x;
          i.hy = h.y;
          i.hk = h.k * e;
        }
      }
      // only the first giant (blown before the light changes) has a scripted finale
      i.bigDue = t < 5 ? SCRIPT.bigDue : 0;
      const kp = SCRIPT.keeper;
      i.kx = kp.x;
      i.ky = kp.y;
      i.kk = t > kp.from ? kp.k * Math.min(1, (t - kp.from) / 1.5) : 0;
    } else {
      // the mic envelope arrives in ~100 ms steps (iOS buffer size): glide toward it every physics step
      const target = Math.max(breath.value, fakeBreath.value);
      i.breath += (target - i.breath) * (1 - Math.exp(-dt / (target > i.breath ? 0.035 : 0.08)));
      const g = gravity.sensor.value;
      i.gx = Math.max(-1, Math.min(1, g.x / 9.81)) * 0.6;
      i.gy = 0;
    }
    const f = finger.value;
    i.fx = f[0];
    i.fy = f[1];
    i.fvx = f[2];
    i.fvy = f[3];
    i.fa = f[4];
    // the carried bubble may have popped or drifted off while the finger held still (its slot can be reused): let go
    const g = grabbed.value;
    if (g >= 0 && (s.b[g * BF + ALIVE] !== 1 || s.b[g * BF + POP] >= 0)) grabbed.set(-1);
    i.grab = grabbed.value;
    step(s, i, dt, t);
    if (DEMO) demoTaps(s, t);
    else ambient(s, dt, t);
  };

  const frame = (ts: number) => {
    "worklet";
    if (!readyS.value) return;
    const s = sim.value;
    if (!prewarmed.value) {
      // settle the opening cluster before frame 1
      let t = time.value;
      while (t < START_T - 1e-6) {
        advance(s, PH, t);
        t += PH;
      }
      physT.value = START_T;
      time.value = START_T;
      prewarmed.value = true;
      lastTs.value = ts;
    }
    if (holdN.value > 0) {
      // demo: hold t = START_T while the first frames reach the screen; the corner sync marker vanishes on the very frame
      // the clock starts, so tools/filmstart.sh can find app t = 0 in the recording exactly
      // (v34) only smooth frames count: after a hitch the count starts over, so the clock never starts while the first
      // frames are still stuttering onto the screen (the marker then reached the recording 0.3 s late: v29, v30, v34)
      const hd = lastTs.value < 0 ? 0 : ts - lastTs.value;
      holdN.value = hd > 25 ? 40 : holdN.value - 1;
      lastTs.value = ts;
      fillUniforms(s, time.value);
      if (holdN.value === 0) syncMark.value = 0;
      else return;
    }
    const raw = lastTs.value < 0 ? 1 / 60 : (ts - lastTs.value) / 1000;
    lastTs.value = ts;
    const dt = Math.min(1 / 30, Math.max(0, raw)) * TIMESCALE;
    const t = time.value + dt;
    time.value = t;
    // catch the physics clock up in fixed steps (at most 8 per frame after a hitch)
    let n = 0;
    while (physT.value + PH <= t + 1e-6 && n < 8) {
      advance(s, PH, physT.value);
      physT.value += PH;
      n++;
    }
    if (n === 8) physT.value = t;
    if (LOOK_SWITCH > 0 && !switched.value && t >= LOOK_SWITCH) {
      switched.value = true;
      scheduleOnRN(toggleLook);
    }
    const ev = s.ev;
    if (ev[E_POP] + ev[E_PINCH] + ev[E_SPRAY] + ev[E_STICK] > 0) {
      scheduleOnRN(onEvents, ev[E_POP], ev[E_PINCH], ev[E_SPRAY], ev[E_STICK], ev[E_BIGPOP], t);
      for (let k = 0; k < EF; k++) ev[k] = 0;
    }
    fillUniforms(s, t);
    sim.modify();
  };
  useFrameCallback(({ timestamp }) => {
    "worklet";
    frame(timestamp);
  });

  // ── droplets ──
  // one buffer per sprite: slow droplets as beads, fast ones as streaks along their velocity
  const dropXf = useRSXformBuffer(MAXD, (val, i) => {
    "worklet";
    dropXform(sim.value.d, i, false, val);
  });
  const streakXf = useRSXformBuffer(MAXD, (val, i) => {
    "worklet";
    dropXform(sim.value.d, i, true, val);
  });

  /** screen position (pt) of the sun / key lantern of the current look (tap it to switch looks) */
  const keyLight = useSharedValue(LOOKS[START_LOOK].sunPt);
  useEffect(() => {
    keyLight.set(look.sunPt);
  }, [look, keyLight]);

  // ── gestures ──
  const toDesign = (x: number, y: number) => {
    "worklet";
    const f = fitS.value;
    return [(x - f.ox) / f.k, (y - f.oy) / f.k] as const;
  };
  // real fingertips roll a few points during a tap: the tap tolerates 10 pt, the pan needs 12 pt to take over,
  // and the long press (300 ms) only starts after the tap's window (250 ms) has closed
  const tap = Gesture.Tap()
    .maxDuration(250)
    .maxDistance(10)
    .enabled(!DEMO)
    .onEnd((e) => {
      const [x, y] = toDesign(e.x, e.y);
      const hit = popAt(sim.value, x, y);
      if (hit >= 0) return;
      // tap the sun to let it set (→ twilight), tap the big lantern to bring the sun back
      const k = keyLight.value;
      if (Math.hypot(x - k[0], y - k[1]) < 62) scheduleOnRN(toggleLook);
    });
  const pan = Gesture.Pan()
    .maxPointers(1)
    .minDistance(12)
    .enabled(!DEMO)
    .onBegin((e) => {
      const [x, y] = toDesign(e.x, e.y);
      downPt.set([x, y]);
    })
    .onStart((e) => {
      const [x, y] = toDesign(e.x, e.y);
      // press on the wand = fake breath (simulator), drag up to blow harder
      if (Math.hypot(x - RING.x, y - RING.y) < RING.ro * 1.3) {
        fakeBreath.set(0.35);
        panBreath.set(true);
        finger.set([x, y, 0, 0, 0]);
        return;
      }
      // press on a bubble = carry it with a wet finger (it wobbles but doesn't pop)
      // hit-test where the finger went down (the pan only activates after a few points of movement)
      const d0 = downPt.value;
      const g = hitTest(sim.value, d0[0], d0[1]);
      if (g >= 0) {
        grabbed.set(g);
        sim.value.b[g * BF + V2] += 1.2; // wobble kick
        finger.set([x, y, 0, 0, 0]);
        return;
      }
      finger.set([x, y, 0, 0, 1]);
    })
    .onUpdate((e) => {
      const [x, y] = toDesign(e.x, e.y);
      if (panBreath.value) {
        fakeBreath.set(Math.max(0.12, Math.min(1, 0.35 - e.translationY / 260)));
        return;
      }
      // the carried bubble may have aged out and popped (its slot can be reused): let go
      const g = grabbed.value;
      if (g >= 0 && (sim.value.b[g * BF + ALIVE] !== 1 || sim.value.b[g * BF + POP] >= 0)) grabbed.set(-1);
      finger.set([x, y, e.velocityX / fitS.value.k, e.velocityY / fitS.value.k, grabbed.value >= 0 ? 0 : 1]);
    })
    .onFinalize(() => {
      // a pan that never started (the long press won the race) must not cancel the long press's breath
      if (panBreath.value) {
        fakeBreath.set(0);
        panBreath.set(false);
      }
      grabbed.set(-1);
      finger.set([0, 0, 0, 0, 0]);
    });
  const hold = Gesture.LongPress()
    .minDuration(300)
    .maxDistance(30)
    .enabled(!DEMO)
    .onStart((e) => {
      const [x, y] = toDesign(e.x, e.y);
      if (Math.hypot(x - RING.x, y - RING.y) < RING.ro * 1.3) fakeBreath.set(0.35);
    })
    .onFinalize(() => {
      // the long press fails once the finger travels > 30 pt; a pan that is blowing (drag up = harder) keeps the breath
      if (!panBreath.value) fakeBreath.set(0);
    });
  // two-finger tap: switch between golden hour and twilight with fairy lights
  const twoTap = Gesture.Tap()
    .minPointers(2)
    .maxDuration(350)
    .enabled(!DEMO)
    .onEnd(() => {
      scheduleOnRN(toggleLook);
    });
  // tap (quick, < 250 ms) races the press gestures; hold (fake breath on the wand) and pan (wind / wet-finger drag) can run
  // together so a press that then moves still grabs a bubble
  const gesture = Gesture.Race(twoTap, Gesture.Simultaneous(hold, pan), tap);

  const onLayout = (e: LayoutChangeEvent) => {
    const { width, height } = e.nativeEvent.layout;
    setSize({ w: width, h: height });
  };

  return (
    <View style={styles.root} onLayout={onLayout}>
      {!DEMO && <BreathMic out={breath} />}
      <GestureDetector gesture={gesture}>
        <Canvas style={StyleSheet.absoluteFill}>
          {ready && (
            <Group transform={sceneT}>
              <Group transform={bgT}>
                <Image image={bgs![layA]} x={0} y={0} width={VIEW.w} height={VIEW.h} fit="fill" sampling={LINEAR} />
                <Image image={bgs![layB]} x={0} y={0} width={VIEW.w} height={VIEW.h} fit="fill" sampling={LINEAR} opacity={op1} />
              </Group>
              <Group transform={nearT}>
                <Fill>
                  <Shader source={bubblesFx} uniforms={bu}>
                    <ImageShader image={envImg} tx="repeat" ty="clamp" sampling={LINEAR} />
                  </Shader>
                </Fill>
                <Group blendMode="plus">
                  <Atlas image={dropDot} sprites={dropSprites} transforms={dropXf} />
                  <Atlas image={dropStreak} sprites={dropSprites} transforms={streakXf} />
                </Group>
                {/* the wand is the nearest thing to the lens: bubbles float away behind it (v33, user feedback); its film sits in
                    the ring plane, in front of a bubble that is being blown backwards out of it */}
                <Rect x={RING.x - RING.r - 4} y={RING.y - RING.r - 4} width={RING.r * 2 + 8} height={RING.r * 2 + 8}>
                  <Shader source={wandFilmFx} uniforms={fu}>
                    <ImageShader image={envImg} tx="repeat" ty="clamp" sampling={LINEAR} />
                  </Shader>
                </Rect>
                <Image image={wands![layA]} x={LOOKS[layA].wandRect.x} y={LOOKS[layA].wandRect.y} width={LOOKS[layA].wandRect.w} height={LOOKS[layA].wandRect.h} fit="fill" sampling={LINEAR} />
                <Image image={wands![layB]} x={LOOKS[layB].wandRect.x} y={LOOKS[layB].wandRect.y} width={LOOKS[layB].wandRect.w} height={LOOKS[layB].wandRect.h} fit="fill" sampling={LINEAR} opacity={op1} />
                <Rect x={fg0x} y={fg0y} width={fg0w} height={fg0h}>
                  <Shader source={bubblesFx} uniforms={buF}>
                    <ImageShader image={envImg} tx="repeat" ty="clamp" sampling={LINEAR} />
                  </Shader>
                </Rect>
                <Rect x={fg1x} y={fg1y} width={fg1w} height={fg1h}>
                  <Shader source={bubblesFx} uniforms={buF}>
                    <ImageShader image={envImg} tx="repeat" ty="clamp" sampling={LINEAR} />
                  </Shader>
                </Rect>
              </Group>
              <Fill blendMode="softLight">
                <Shader source={postFx} uniforms={pu} />
              </Fill>
              {/* demo sync marker in the top-left corner (hidden by the phone mockup's rounded corner) */}
              {DEMO && <Rect x={0} y={0} width={9} height={9} color="#ff00ff" opacity={syncMark} />}
            </Group>
          )}
        </Canvas>
      </GestureDetector>
      {!DEMO && <MicHint breath={hintBreath} top={(RING.y - RING.ro) * fit.k + fit.oy - 70} />}
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: "#120c08" },
});
