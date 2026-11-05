"""Calm piano music for the 3D garden (beat sheet music.style "piano"; user, 04/11 night: "clone a version with different
sound, more balanced and nicer"). numpy only, used by mix_clip.py. No drums, no vinyl: a felt piano, warm strings, the
real birdsong of blender/audio/birds/ around it.

  ~65 BPM in C (the bar is derived from the clip so the end card lands on a downbeat). An eight-bar progression,
  Fmaj7 – C/E – Dm7 – Gsus4 | Am7 – Fmaj7 – C/G – Gsus4, resolving to Cadd9 on the card.
  - felt piano: additive strings (slightly inharmonic partials, three detuned unisons that beat slowly, two-stage
    decay, higher partials dying first), a soft hammer, brightness and level by velocity; the left hand rolls a slow
    broken chord under the sustain pedal, the right hand sings a short, simple tune that comes and goes
  - strings: a warm detuned ensemble pad, slow swells: they open when the big bubble flies off and breathe out after
    the pop
  - a celesta: three notes when the big bubble lets go, three when it pops (on the beat)
"""
import math

import numpy as np

# (name, bass root, left-hand broken-chord notes, strings voicing)
PROG = [
    ("Fmaj7", 41, [53, 60, 64, 69], [57, 60, 64, 69]),
    ("C/E", 40, [52, 60, 64, 67], [55, 60, 64, 67]),
    ("Dm7", 38, [50, 57, 60, 65], [57, 60, 62, 65]),
    ("Gsus4", 43, [55, 62, 65, 67], [55, 60, 62, 67]),
    ("Am7", 45, [52, 57, 60, 64], [57, 60, 64, 67]),
    ("Fmaj7", 41, [53, 57, 60, 64], [57, 60, 64, 69]),
    ("C/G", 43, [55, 60, 64, 67], [55, 60, 64, 67]),
    ("Gsus4", 43, [55, 62, 65, 67], [55, 60, 62, 67]),
]
CARD = (36, [48, 55, 62, 64, 67, 72, 74, 76])  # Cadd9, wide

# right-hand tune: (bar in phrase, beat, midi, beats long, velocity)
TUNE_A = [
    (0, 0.0, 72, 1.5, 0.5), (0, 1.5, 74, 0.5, 0.42), (0, 2.0, 76, 2.0, 0.5),
    (1, 0.0, 79, 1.5, 0.52), (1, 1.5, 76, 0.5, 0.42), (1, 2.0, 72, 2.0, 0.46),
    (2, 0.0, 74, 1.0, 0.48), (2, 1.0, 72, 1.0, 0.44), (2, 2.0, 69, 2.0, 0.46),
    (3, 0.0, 67, 3.0, 0.44),
]
TUNE_B = [
    (0, 0.0, 76, 1.5, 0.5), (0, 1.5, 79, 0.5, 0.44), (0, 2.0, 81, 2.0, 0.52),
    (1, 0.0, 79, 1.0, 0.48), (1, 1.0, 76, 1.0, 0.44), (1, 2.0, 72, 2.0, 0.46),
    (2, 0.0, 74, 1.5, 0.46), (2, 1.5, 76, 0.5, 0.42), (2, 2.0, 74, 2.0, 0.44),
    (3, 0.0, 72, 1.0, 0.44), (3, 1.0, 74, 3.0, 0.42),
]


def hz(m):
    return 440.0 * 2 ** ((m - 69) / 12)


class Piano:
    def __init__(self, N, SR, T0, BAR, BARS, CARD_AT, BIG, PINCH, band, reverb, seed=11):
        self.N, self.SR, self.T0, self.BAR, self.BARS = N, SR, T0, BAR, BARS
        self.BEAT = BAR / 4
        self.CARD_AT, self.BIG, self.PINCH = CARD_AT, BIG, PINCH
        self.band, self.reverb = band, reverb
        self.rng = np.random.default_rng(seed)

    def at(self, bar, beat):
        return self.T0 + bar * self.BAR + beat * self.BEAT + float(self.rng.normal(0, 0.008))

    def ns(self, sec):
        return int(round(sec * self.SR))

    def put(self, buf, sig, t, gain=1.0, pan=0.0):
        i = self.ns(t)
        if i >= len(buf):
            return
        if i < 0:
            sig, i = sig[-i:], 0
        sig = sig[:len(buf) - i] * gain
        if sig.ndim == 1:
            buf[i:i + len(sig), 0] += sig * math.sqrt((1 - pan) / 2) * 1.414
            buf[i:i + len(sig), 1] += sig * math.sqrt((1 + pan) / 2) * 1.414
        else:
            buf[i:i + len(sig)] += sig

    # ── instruments ──
    def piano(self, m, held, vel=0.5):
        """One felt-piano note held for `held` s (key / pedal), then damped."""
        SR, rng = self.SR, self.rng
        f0 = hz(m)
        ring = min(held + 0.35, 7.0)
        t = np.arange(self.ns(ring)) / SR
        B = 0.00018 * (f0 / 261.6) ** 0.5             # inharmonicity
        T1 = 0.5 * (261.6 / f0) ** 0.45                # prompt decay
        T2 = 5.5 * (261.6 / f0) ** 0.55                # after-sound
        tilt = 1.9 - 0.9 * vel                         # softer = darker
        x = np.zeros(len(t))
        for n in range(1, 18):
            fn = n * f0 * math.sqrt(1 + B * n * n)
            if fn > 9000:
                break
            a = (1.0 / n ** tilt) * (0.3 + abs(math.sin(math.pi * n * 0.13)))  # hammer strikes 1/8 along
            env = 0.55 * np.exp(-t / (T1 / n ** 0.5)) + 0.45 * np.exp(-t / (T2 / n ** 0.7))
            det = fn * 0.0007 * (1 + 0.3 * float(rng.random()))  # three unisons, beating slowly
            ph = float(rng.random()) * 6.28
            x += a * env * (np.sin(2 * np.pi * fn * t + ph) * 0.5 + np.sin(2 * np.pi * (fn + det) * t + ph + 1.1) * 0.3
                            + np.sin(2 * np.pi * (fn - det * 0.8) * t + ph + 2.3) * 0.2)
        # the hammer: a soft felt knock
        knock = self.band(rng.standard_normal(min(len(t), self.ns(0.03))), 200, 1800 + 2500 * vel)
        knock *= np.exp(-np.arange(len(knock)) / SR / 0.006) * 0.06 * vel
        x[:len(knock)] += knock
        x *= np.minimum(t / 0.002, 1)
        damp = np.where(t < held, 1.0, np.exp(-(t - held) / 0.12))
        return x * damp * vel * 0.16

    def strings(self, ms, sec, att=1.6, rel=1.8):
        SR, rng = self.SR, self.rng
        n = self.ns(sec)
        t = np.arange(n) / SR
        out = np.zeros((n, 2))
        for k, m in enumerate(ms):
            for v in range(4):
                f = hz(m) * (1 + (v - 1.5) * 0.0018)
                vib = 1 + 0.0016 * np.sin(2 * np.pi * (4.6 + 0.3 * v) * t + float(rng.random()) * 6)
                ph = 2 * np.pi * np.cumsum(f * vib) / SR + float(rng.random()) * 6
                x = sum(np.sin(h * ph) / h ** 1.25 for h in range(1, 9))
                pan = -0.6 + 1.2 * ((k * 4 + v) / max(1, len(ms) * 4 - 1))
                out[:, 0] += x * math.sqrt((1 - pan) / 2)
                out[:, 1] += x * math.sqrt((1 + pan) / 2)
        env = np.minimum(t / att, 1) ** 1.5 * np.clip((sec - t) / rel, 0, 1) ** 1.2
        out *= env[:, None] / (len(ms) * 4)
        return np.stack([self.band(out[:, c], 150, 2600) for c in range(2)], 1)

    def celesta(self, m, vel=0.5):
        t = np.arange(self.ns(2.0)) / self.SR
        f = hz(m)
        x = sum(a * np.sin(2 * np.pi * f * r * t) * np.exp(-t / d) for r, a, d in ((1, 1, 0.9), (2.0, 0.25, 0.3), (4.0, 0.1, 0.12), (6.8, 0.04, 0.05)))
        return x * np.minimum(t / 0.002, 1) * 0.12 * vel

    # ── arrangement ──
    def render(self):
        N, BAR, BEAT = self.N, self.BAR, self.BEAT
        pf, st, ce = (np.zeros((N, 2)) for _ in range(3))
        pinch_bar = int((self.PINCH - self.T0) // BAR)
        pop_bar = int((self.BIG - self.T0) // BAR)
        last = self.BARS - 1
        for bar in range(self.BARS):
            name, root, lh, sv = PROG[bar % 8]
            # the dynamic arc: quiet start, fuller while it flies, hush after the pop, warm again for the last round
            dyn = 0.52 if bar < pinch_bar else 0.58 if bar < pop_bar else 0.48 if bar < pop_bar + 2 else 0.52
            # left hand: the bass note, then the chord broken slowly upward under the pedal (pedal changes each bar)
            hold_end = self.at(bar + 1, 0.0) - 0.05
            t0 = self.at(bar, 0.0)
            self.put(pf, self.piano(root, hold_end - t0, dyn * 0.95), t0, 1.0, -0.35)
            pattern = (0.5, 1.0, 1.5, 2.0, 2.5, 3.0)  # (the last bar too: it went quiet before the card)
            for k, beat in enumerate(pattern):
                m = lh[k % 4] if k < 4 else lh[3 - (k - 4) * 2]
                tt = self.at(bar, beat)
                self.put(pf, self.piano(m, max(0.3, hold_end - tt), dyn * (0.72 if k % 2 else 0.82)), tt, 1.0,
                         -0.2 + 0.08 * (m - 50) / 4)
            # strings: one long swell per two bars, soft at first, fuller while it flies, lighter after the pop
            if bar >= 1 and bar % 2 == 1:
                g = 0.5 if bar < pinch_bar else 1.0 if bar < pop_bar else 0.6
                t0 = self.at(bar, 0.0)
                self.put(st, self.strings(sv, min(2 * BAR + 1.2, self.CARD_AT - t0 + 0.4)), t0, g)
        # the tune: once while the first bubbles drift (from bar 1), once again for the last round
        for start, tune in ((1, TUNE_A), (pop_bar + 2, TUNE_B)):
            for b_, beat, m, length, v in tune:
                bar = start + b_
                if bar >= last:
                    continue
                tt = self.at(bar, beat)
                self.put(pf, self.piano(m, length * BEAT, v), tt, 1.0, 0.25)
        # celesta on the two moments, on the beat after them
        for when, notes in ((self.PINCH, (79, 84, 88)), (self.BIG, (88, 84, 79))):
            b = math.ceil((when - self.T0) / BEAT + 0.05)
            for k, m in enumerate(notes):
                self.put(ce, self.celesta(m, 0.6 - 0.1 * k), self.T0 + (b + k * 0.5) * BEAT, 1.0, 0.3 - 0.3 * k)
        dry = pf + st * 0.9 + ce
        return dry + self.reverb(pf * 0.8 + st + ce, 3.0) * 0.32

    def card(self, at, ring):
        out = np.zeros((self.ns(at + ring + 4.0), 2))
        root, notes = CARD
        self.put(out, self.piano(root, ring, 0.5), at, 1.0, -0.3)
        for k, m in enumerate(notes):
            self.put(out, self.piano(m, ring - 0.06 * k, 0.42 + 0.02 * k), at + 0.07 * k, 1.0, -0.4 + 0.1 * k)
        self.put(out, self.strings([55, 60, 64, 67], ring + 1.0, att=0.8, rel=1.4), at, 0.6)
        return out + self.reverb(out, 3.0) * 0.32
