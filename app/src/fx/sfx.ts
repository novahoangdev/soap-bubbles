/**
 * In-app sound effects (synthesised: blender/scripts/synth_audio.py → assets/sfx). Played with expo-audio from small player
 * pools (round robin, so rapid pops overlap instead of cutting each other off). Called on the JS thread from the scene's event
 * callback. Everything is wrapped in try/catch: no sound is never worth a crash.
 */
import { AppState } from "react-native";
import { createAudioPlayer, setAudioModeAsync } from "expo-audio";

type Player = { play(): void; pause(): void; seekTo(s: number): Promise<void>; volume: number; loop: boolean };
export type Sfx = "pop" | "pop_big" | "bloop" | "puff" | "stick";

const SRC = {
  pop_1: require("../../assets/sfx/pop_1.wav"),
  pop_2: require("../../assets/sfx/pop_2.wav"),
  pop_3: require("../../assets/sfx/pop_3.wav"),
  pop_4: require("../../assets/sfx/pop_4.wav"),
  pop_5: require("../../assets/sfx/pop_5.wav"),
  pop_6: require("../../assets/sfx/pop_6.wav"),
  pop_big: require("../../assets/sfx/pop_big.wav"),
  bloop: require("../../assets/sfx/bloop.wav"),
  puff: require("../../assets/sfx/puff.wav"),
  stick: require("../../assets/sfx/stick.wav"),
};
const GAIN: Record<Sfx, number> = { pop: 0.6, pop_big: 0.8, bloop: 0.7, puff: 0.45, stick: 0.35 };

let pools: Partial<Record<Sfx, Player[]>> = {};
const rr: Partial<Record<Sfx, number>> = {};
const last: Partial<Record<Sfx, number>> = {};
let ready = false;

export const initSfx = () => {
  if (ready) return;
  ready = true;
  try {
    // allowsRecording: the breath mic shares this session (play-and-record); a playback-only mode would cut it off
    setAudioModeAsync({ playsInSilentMode: true, interruptionMode: "mixWithOthers", allowsRecording: true }).catch(() => {});
    // keepAudioSessionActive: otherwise expo-audio deactivates the session ~100 ms after a sound ends, which also stops
    // the mic stream (its "still in use" check only knows players and recorders)
    const make = (src: number, n: number) =>
      Array.from({ length: n }, () => createAudioPlayer(src, { keepAudioSessionActive: true }) as unknown as Player);
    pools = {
      // six soft notes of C major pentatonic: a run of pops plays like wind chimes (synth_audio.py pop_soft)
      pop: [SRC.pop_1, SRC.pop_2, SRC.pop_3, SRC.pop_4, SRC.pop_5, SRC.pop_6].flatMap((src) => make(src, 2)),
      pop_big: make(SRC.pop_big, 1),
      bloop: make(SRC.bloop, 2),
      puff: make(SRC.puff, 2),
      stick: make(SRC.stick, 3),
    };
  } catch {
    pools = {};
  }
};

/** minimum gap between two plays of the same sound (ms), so a burst of events doesn't turn into noise */
const GAP: Record<Sfx, number> = { pop: 35, pop_big: 200, bloop: 150, puff: 260, stick: 90 };

export const sfx = (kind: Sfx, vol = 1) => {
  const pool = pools[kind];
  if (!pool?.length) return;
  const now = Date.now();
  if (now - (last[kind] ?? 0) < GAP[kind]) return;
  last[kind] = now;
  try {
    // pops: random variation, not strictly round robin
    const i = kind === "pop" ? Math.floor(Math.random() * pool.length) : ((rr[kind] ?? 0) + 1) % pool.length;
    rr[kind] = i;
    const p = pool[i];
    p.volume = Math.min(1, GAIN[kind] * vol);
    // seekTo is async: play only once the rewind has landed, or a finished player plays nothing
    p.seekTo(0)
      .then(() => p.play())
      .catch(() => p.play());
  } catch {}
};

/**
 * Background music (v33): a calm 27 s ambient loop in C major (synth_audio.py music_loop), quiet under the effects. It has no
 * bass, so what the mic picks up from the speaker stays out of the breath detector's low band. Paused in the background.
 */
const MUSIC_VOL = 0.32;
let music: Player | null = null;
export const startMusic = () => {
  if (music) return;
  try {
    music = createAudioPlayer(require("../../assets/sfx/music.wav"), { keepAudioSessionActive: true }) as unknown as Player;
    music.loop = true;
    music.volume = MUSIC_VOL;
    music.play();
    AppState.addEventListener("change", (st) => {
      if (!music) return;
      if (st === "active") music.play();
      else music.pause();
    });
  } catch {
    music = null;
  }
};
