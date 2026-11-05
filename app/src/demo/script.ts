/**
 * Demo storyboard (PLAN section 2), scene seconds. EXPO_PUBLIC_DEMO=1 plays it with a seeded random generator, so every
 * recording is identical.
 */
export type PreBubble = { x: number; y: number; r: number; vx: number; vy: number; th: number; bondTo?: number[] };

export const DEMO = {
  seed: 20261103,
  /** seconds simulated before frame 1 so the opening cluster has settled and is drifting */
  prewarm: 1.2,
  /** frame 1 = the most beautiful moment: a big five-bubble cluster up in the fairy-light band + a few loose bubbles */
  pre: [
    { x: 200, y: 380, r: 104, vx: 4, vy: -2, th: 1.1 },
    { x: 299, y: 422, r: 75, vx: 0, vy: -1, th: 0.95, bondTo: [0] },
    { x: 236, y: 492, r: 57, vx: 0, vy: 0, th: 0.85, bondTo: [0, 1] },
    { x: 112, y: 450, r: 49, vx: 2, vy: -1, th: 0.9, bondTo: [0] },
    { x: 286, y: 315, r: 44, vx: 0, vy: -2, th: 0.8, bondTo: [0, 1] },
    { x: 380, y: 230, r: 26, vx: -4, vy: 3, th: 0.8 },
    { x: 380, y: 590, r: 22, vx: -6, vy: -2, th: 0.7 },
    { x: 50, y: 300, r: 24, vx: 5, vy: -3, th: 0.75 },
    { x: 70, y: 640, r: 30, vx: 3, vy: -4, th: 0.9 },
    { x: 335, y: 690, r: 17, vx: -3, vy: -4, th: 0.65 },
  ] as PreBubble[],
  /** breath envelope keyframes [t, level]: a long soft breath (giant bubble, 2.3 s since v18), then three sharp puffs (sprays) */
  breath: [
    [0, 0], [0.8, 0], [1.0, 0.32], [1.35, 0.5], [2.5, 0.52], [2.95, 0.42], [3.1, 0],
    [3.8, 0], [3.9, 0.92], [4.25, 0.9], [4.35, 0],
    [4.7, 0], [4.8, 0.96], [5.15, 0.92], [5.25, 0],
    [5.6, 0], [5.7, 0.86], [5.95, 0.85], [6.05, 0],
    // a second soft breath at night: a fresh bubble full of fairy lights before the giant's finale
    [11, 0], [11.2, 0.3], [11.75, 0.36], [12.2, 0.3], [12.3, 0],
  ] as [number, number][],
  /** gentle herding so bubbles meet and stick while the camera holds */
  herd: [{ from: 5.55, to: 11.35, x: 215, y: 480, k: 95 }],
  /** taps: aim at a bubble near (x, y) with minR ≤ radius ≤ maxR, preferring cluster members, never one cut by the screen
   *  edge (the giant is kept for its own ending); points around the herded cluster so every pop reads */
  taps: [
    { at: 8.45, x: 165, y: 445, minR: 22, maxR: 66 },
    { at: 9, x: 335, y: 440, minR: 30, maxR: 66 },
    { at: 9.45, x: 190, y: 545, minR: 20, maxR: 66 },
    { at: 9.85, x: 325, y: 370, minR: 28, maxR: 66 },
    { at: 10.2, x: 235, y: 590, minR: 18, maxR: 66 },
    { at: 10.55, x: 140, y: 500, minR: 18, maxR: 66 },
    { at: 10.9, x: 300, y: 560, minR: 16, maxR: 66 },
  ],
  /** the giant bubble from the long breath drains to a black film and pops by itself here */
  bigDue: 12.75,
  /** keeps the giant in the middle of the frame for its finale (spring constant 1/s²) */
  keeper: { from: 3.35, x: 225, y: 455, k: 1.6 },
  end: 13.95,
};

/** breath level at scene time t (linear between keyframes) */
export const demoBreath = (t: number) => {
  "worklet";
  const k = DEMO.breath;
  if (t <= k[0][0]) return k[0][1];
  for (let i = 1; i < k.length; i++) {
    if (t <= k[i][0]) {
      const a = k[i - 1], b = k[i];
      const u = (t - a[0]) / Math.max(1e-4, b[0] - a[0]);
      return a[1] + (b[1] - a[1]) * u;
    }
  }
  return k[k.length - 1][1];
};
