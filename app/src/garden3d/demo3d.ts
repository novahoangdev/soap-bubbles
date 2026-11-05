/**
 * Scripted breath for recordings of the 3D garden (EXPO_PUBLIC_DEMO3D=1): two quick puffs (a spray of little bubbles
 * racing off over the daisies), then one long soft breath that grows a big bubble; it flies off, the camera follows it,
 * comes home, and a second round of puffs and a middle-sized bubble closes the take (~22 s).
 * v2 (chill, ~40 s): a quiet opening, slower puffs and flight, a long follow, a calm ending.
 * v3: puffs throw clouds of bubbles, big and small; the take ends on a long strong blow (a stream of them).
 */
export const DEMO3D = process.env.EXPO_PUBLIC_DEMO3D === "1";

const KEYS: [number, number][] = [
  // a quiet meadow first (butterflies, grass in the wind), then two puffs: clouds of bubbles, big and small, drift off
  [0, 0], [2.6, 0], [2.7, 0.75], [3.0, 0.68], [3.1, 0], [4.2, 0], [4.3, 0.74], [4.6, 0.66], [4.7, 0],
  // a long soft breath grows the big one; it floats off, the camera follows it (~14 s) and comes home
  [6.0, 0], [6.6, 0.3], [8.0, 0.42], [10.2, 0.45], [10.8, 0.4], [11.0, 0],
  // home again: puffs, then one long strong blow, a stream of bubbles drifting in front of the wood
  // (after the camera's slow glide home, ~8 s from the pop)
  [34.9, 0], [35.0, 0.74], [35.3, 0.66], [35.4, 0], [36.6, 0], [36.7, 0.72], [37.0, 0.64], [37.1, 0],
  [38.4, 0], [38.6, 0.7], [39.9, 0.66], [40.3, 0],
];

export const demoBreath3D = (t: number) => {
  for (let i = 1; i < KEYS.length; i++) {
    const [t1, v1] = KEYS[i];
    if (t <= t1) {
      const [t0, v0] = KEYS[i - 1];
      const u = (t - t0) / Math.max(t1 - t0, 1e-3);
      return v0 + (v1 - v0) * u;
    }
  }
  return 0;
};
