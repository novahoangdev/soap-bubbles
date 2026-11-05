import { useEffect, useRef } from "react";
import { AppState } from "react-native";
import { requestRecordingPermissionsAsync, setAudioModeAsync, useAudioStream } from "expo-audio";
import type { SharedValue } from "react-native-reanimated";

/**
 * Microphone → breath envelope 0…1 (PLAN section 0).
 * Blowing on a phone mic is loud broadband "wind noise" dominated by low frequencies, so a level meter with a fast attack and
 * a slower release is enough: RMS of each float32 PCM buffer (iOS delivers ~100 ms) → dBFS → mapped −46…−8 dBFS onto 0…1, then a one-pole
 * low-frequency share (energy of a 1-pole low-pass vs the whole signal) gates out speech and taps, which are much brighter.
 */
const DB_LO = -46;
const DB_HI = -8;
const MICLOG = process.env.EXPO_PUBLIC_MICLOG === "1";

/** Mounted only in the interactive app: creating the native stream already triggers the microphone prompt. */
export function BreathMic({ out }: { out: SharedValue<number> }) {
  useBreath(out, true);
  return null;
}

export function useBreath(out: SharedValue<number>, enabled: boolean) {
  const env = useRef(0);
  const lp = useRef(0);
  /** room noise floor (dBFS): drops instantly to quieter levels, creeps up slowly, so a fan or traffic doesn't blow bubbles */
  const floor = useRef(-60);
  const dbg = useRef(0);
  const { stream } = useAudioStream({
    sampleRate: 48000,
    channels: 1,
    encoding: "float32",
    onBuffer: (buf) => {
      const x = new Float32Array(buf.data);
      const n = x.length;
      if (!n) return;
      let e = 0, el = 0;
      let l = lp.current;
      // ~400 Hz one-pole low-pass at 48 kHz
      const k = 0.05;
      for (let i = 0; i < n; i++) {
        const v = x[i];
        e += v * v;
        l += (v - l) * k;
        el += l * l;
      }
      lp.current = l;
      const rms = Math.sqrt(e / n);
      const low = e > 1e-12 ? el / e : 0;
      const db = 20 * Math.log10(rms + 1e-9);
      const dt = n / buf.sampleRate;
      floor.current = db < floor.current ? db : floor.current + dt * 0.6;
      const lo = Math.max(DB_LO, floor.current + 8);
      let lvl = Math.min(1, Math.max(0, (db - lo) / (DB_HI - lo)));
      // breath noise keeps most energy low; speech / clicks are brighter
      lvl *= Math.min(1, Math.max(0, (low - 0.3) / 0.35));
      const a = lvl > env.current ? 1 - Math.exp(-dt / 0.04) : 1 - Math.exp(-dt / 0.16);
      env.current += (lvl - env.current) * a;
      out.set(env.current);
      if (MICLOG && (dbg.current = (dbg.current + 1) % 25) === 0) console.log(`MIC db=${db.toFixed(1)} floor=${floor.current.toFixed(1)} low=${low.toFixed(2)} env=${env.current.toFixed(2)}`);
    },
  });

  useEffect(() => {
    if (!enabled) return;
    let alive = true;
    let granted = false;
    (async () => {
      try {
        const p = await requestRecordingPermissionsAsync();
        if (MICLOG) console.log("MIC permission", p.granted);
        if (!p.granted || !alive) return;
        await setAudioModeAsync({ allowsRecording: true, playsInSilentMode: true, interruptionMode: "mixWithOthers" });
        if (!alive) return;
        await stream.start();
        granted = true;
        if (MICLOG) console.log("MIC started");
      } catch (e) {
        console.warn("mic unavailable", e);
      }
    })();
    // the mic only runs in the foreground (no orange dot in the background); stop + start on return also recovers
    // from an interruption (call, Siri) after which the native stream still believes it is running
    const sub = AppState.addEventListener("change", (st) => {
      if (!granted) return;
      try {
        stream.stop();
        if (st === "active") {
          env.current = 0;
          stream.start().catch((e: unknown) => console.warn("mic restart failed", e));
        } else out.set(0);
      } catch {}
    });
    return () => {
      alive = false;
      sub.remove();
      try {
        stream.stop();
      } catch {}
    };
  }, [enabled, stream, out]);
}
