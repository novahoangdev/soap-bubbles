"""Lofi music for the 3D garden (beat sheet music.style "lofi"; user, 04/11 evening: "make the music nice, lofi or
something peaceful, with natural birdsong"). numpy only, used by mix_clip.py.

  Key of C, ~70–75 BPM (the bar is derived from the clip so the end card lands on a downbeat), a four-bar loop of
  warm jazz chords: Fmaj9 – Em7 – Dm9 – G13sus, resolving to Cmaj9 on the end card.
  - electric piano (two-operator FM, a soft tine, slow stereo tremolo), comped lazily: the chord on 1, a short
    re-strike on the swung "and" of 2, sometimes an anticipation into the next bar; strummed low → high
  - a round, muted bass (root on 1, a passing note late in the bar)
  - soft boom-bap drums: a felt kick, a brushy snare on 2 and 4, swung hats; enter after two bars, drop out for the bar
    of the big pop and the last half bar before the card
  - a sparse electric-piano melody, a 4-bar phrase that comes and goes
  - tape: slow wow and flutter, gentle saturation, a darker top; vinyl dust and crackle under it all
"""
import math

import numpy as np

# MIDI voicings (no root: the bass has it)
CHORDS = [
    ("Fmaj9", 41, [57, 60, 64, 67]),   # A C E G over F
    ("Em7", 40, [55, 59, 62, 67]),     # G B D G over E
    ("Dm9", 38, [53, 57, 60, 64]),     # F A C E over D
    ("G13sus", 43, [53, 57, 60, 64]),  # F A C E over G (G11 / G13sus colour) → C
]
CARD_CHORD = (36, [52, 55, 59, 62, 67])  # Cmaj9: E G B D G over C

# melody: (bar in phrase, beat, midi, beats long), C major pentatonic-ish over the loop
PHRASE = [
    (0, 0.5, 76, 0.9), (0, 1.5, 74, 0.5), (0, 2.0, 72, 1.6),
    (1, 2.5, 71, 0.5), (1, 3.0, 74, 1.4),
    (2, 0.5, 77, 0.9), (2, 1.5, 76, 0.5), (2, 2.0, 74, 1.2), (2, 3.5, 72, 0.4),
    (3, 1.5, 72, 0.5), (3, 2.0, 74, 0.5), (3, 2.5, 76, 1.8),
]
PHRASE2 = [
    (0, 0.5, 79, 0.9), (0, 1.5, 76, 0.5), (0, 2.0, 74, 1.4),
    (1, 2.0, 72, 0.5), (1, 2.5, 71, 0.5), (1, 3.0, 67, 1.4),
    (2, 0.5, 69, 0.5), (2, 1.0, 72, 0.9), (2, 2.5, 74, 1.2),
    (3, 1.0, 76, 0.5), (3, 1.5, 74, 0.5), (3, 2.0, 72, 2.0),
]


def hz(m):
    return 440.0 * 2 ** ((m - 69) / 12)


class Lofi:
    def __init__(self, N, SR, T0, BAR, BARS, CARD_AT, BIG, band, reverb, seed=5):
        self.N, self.SR, self.T0, self.BAR, self.BARS = N, SR, T0, BAR, BARS
        self.BEAT = BAR / 4
        self.CARD_AT, self.BIG = CARD_AT, BIG
        self.band, self.reverb = band, reverb
        self.rng = np.random.default_rng(seed)

    # ── timing ──
    def at(self, bar, beat):
        """bar / beat → app second; swung 8ths (the off-beat pushed to 0.6 of the beat), a touch of human looseness."""
        frac = beat - math.floor(beat)
        if abs(frac - 0.5) < 1e-6:
            beat = math.floor(beat) + 0.6
        return self.T0 + bar * self.BAR + beat * self.BEAT + float(self.rng.normal(0, 0.006))

    def ns(self, sec):
        return int(round(sec * self.SR))

    def put(self, buf, sig, t, gain=1.0, pan=0.0):
        i = self.ns(t)
        if i >= self.N:
            return
        if i < 0:
            sig, i = sig[-i:], 0
        sig = sig[:self.N - i] * gain
        if sig.ndim == 1:
            buf[i:i + len(sig), 0] += sig * math.sqrt((1 - pan) / 2) * 1.414
            buf[i:i + len(sig), 1] += sig * math.sqrt((1 + pan) / 2) * 1.414
        else:
            buf[i:i + len(sig)] += sig

    # ── instruments ──
    def epiano(self, m, sec, vel=0.8):
        """Two-operator FM electric piano: 1:1 modulator whose index falls after the hammer, a soft 14× tine ping,
        a bark that grows with velocity, a slow decay into a long tail, stereo tremolo."""
        SR = self.SR
        f = hz(m)
        n = self.ns(sec + 0.6)
        t = np.arange(n) / SR
        idx = (0.5 + 1.6 * vel) * np.exp(-t / 0.22) + 0.18
        x = np.sin(2 * np.pi * f * t + idx * np.sin(2 * np.pi * f * t))
        x += 0.08 * vel * np.sin(2 * np.pi * f * 14.0 * t) * np.exp(-t / 0.018)
        x += 0.05 * np.sin(2 * np.pi * f * 2.0 * t) * np.exp(-t / 0.5)
        dec = 1.6 * (440 / f) ** 0.35
        env = np.minimum(t / 0.004, 1) * (0.35 * np.exp(-t / 0.35) + 0.65 * np.exp(-t / dec))
        env *= np.clip((sec + 0.6 - t) / 0.6, 0, 1) ** 1.5  # damper: a soft release after the note's length
        y = x * env * vel * 0.3
        trem = 0.13 * np.sin(2 * np.pi * 4.2 * t + self.rng.random() * 6)
        return np.stack([y * (1 - trem), y * (1 + trem)], 1)

    def bass(self, m, sec, vel=0.8):
        SR = self.SR
        f = hz(m)
        n = self.ns(sec + 0.15)
        t = np.arange(n) / SR
        x = np.sin(2 * np.pi * f * t) + 0.25 * np.sin(4 * np.pi * f * t) + 0.08 * np.sin(6 * np.pi * f * t)
        x = np.tanh(1.3 * x)
        env = np.minimum(t / 0.012, 1) * (0.55 + 0.45 * np.exp(-t / 0.25)) * np.clip((sec + 0.15 - t) / 0.15, 0, 1)
        return self.band(x * env * vel * 0.5, 30, 900)

    def kick(self, vel=1.0):
        t = np.arange(self.ns(0.4)) / self.SR
        f = 48 + 62 * np.exp(-t / 0.035)
        x = np.sin(2 * np.pi * np.cumsum(f) / self.SR) * np.exp(-t / 0.16)
        x += self.band(self.rng.standard_normal(len(t)), 800, 3000) * np.exp(-t / 0.002) * 0.04
        return self.band(np.tanh(1.4 * x), 45, 4000) * 0.6 * vel

    def snare(self, vel=1.0):
        """A brushy, dusty snare: a short tuned body under band-limited noise with a slow tail."""
        t = np.arange(self.ns(0.35)) / self.SR
        body = np.sin(2 * np.pi * 185 * t) * np.exp(-t / 0.03) * 0.35
        nz = self.band(self.rng.standard_normal(len(t)), 400, 5200) * (0.55 * np.exp(-t / 0.05) + 0.12 * np.exp(-t / 0.16))
        return (body + nz) * np.minimum(t / 0.002, 1) * 0.4 * vel

    def hat(self, vel=1.0):
        t = np.arange(self.ns(0.08)) / self.SR
        return self.band(self.rng.standard_normal(len(t)), 6000, 11000) * np.exp(-t / 0.014) * 0.16 * vel

    # ── the arrangement ──
    def render(self):
        N, SR, BAR, BEAT = self.N, self.SR, self.BAR, self.BEAT
        keys, low, drums, mel = (np.zeros((N, 2)) for _ in range(4))
        rng = self.rng
        pop_bar = int((self.BIG - self.T0) // BAR)
        last = self.BARS - 1
        for bar in range(self.BARS):
            name, root, voic = CHORDS[bar % 4]
            # comp: the chord on 1 (strummed up), a short re-strike on the "and" of 2, every other bar an anticipation
            for beat, length, vel in ((0.0, 1.9, 0.72), (1.5, 0.7, 0.5)):
                if bar == last and beat > 0:
                    continue
                t0 = self.at(bar, beat)
                for k, m in enumerate(voic):
                    v = vel * float(rng.uniform(0.85, 1.05)) * (0.8 if k == 0 else 1.0)
                    self.put(keys, self.epiano(m, length * BEAT, v), t0 + 0.014 * k, 1.0, -0.15 + 0.1 * k)
            if bar % 2 == 1 and bar != last:
                nxt = CHORDS[(bar + 1) % 4][2]
                t0 = self.at(bar, 3.5)
                for k, m in enumerate(nxt[1:]):
                    self.put(keys, self.epiano(m, 0.45 * BEAT, 0.42), t0 + 0.012 * k, 1.0, 0.1 * k)
            # bass: root, a passing note on the "and" of 3 toward the next root
            if bar >= 1:
                self.put(low, self.bass(root, 1.6 * BEAT, 0.8), self.at(bar, 0.0))
                nroot = CHORDS[(bar + 1) % 4][1]
                if bar != last:
                    step = -2 if nroot < root else 2
                    self.put(low, self.bass(nroot - step, 0.8 * BEAT, 0.55), self.at(bar, 2.5))
                    self.put(low, self.bass(root + 7 if root + 7 < 50 else root - 5, 0.6 * BEAT, 0.5), self.at(bar, 3.5))
            # drums from bar 2, out for the bar of the big pop, half a bar of silence before the card
            if 2 <= bar and bar != pop_bar:
                for beat in (0.0, 2.5) if bar % 2 == 0 else (0.0, 1.75, 2.5):
                    if bar == last and beat > 1.5:
                        continue
                    self.put(drums, self.kick(1.0 if beat == 0 else 0.75), self.at(bar, beat))
                for beat in (1.0, 3.0):
                    if bar == last and beat > 1.5:
                        continue
                    self.put(drums, self.snare(float(rng.uniform(0.85, 1.0))), self.at(bar, beat) + 0.012, 1.0, 0.08)
                for k in range(8):
                    beat = k * 0.5
                    if bar == last and beat > 1.5:
                        continue
                    v = (0.9 if k % 2 == 0 else 0.55) * float(rng.uniform(0.75, 1.05))
                    self.put(drums, self.hat(v), self.at(bar, beat), 1.0, 0.3)
            # melody: a phrase over bars 2–5, rests, a second phrase from the bar after the pop
            for start, ph in ((2, PHRASE), (pop_bar + 1, PHRASE2)):
                pb = bar - start
                if 0 <= pb < 4 and bar != last:
                    for b_, beat, m, length in ph:
                        if b_ == pb:
                            self.put(mel, self.epiano(m, length * BEAT, 0.62), self.at(bar, beat), 1.0, 0.2)
        # a slow stereo echo on the melody (dotted 8th), then everything through a warm room
        d = self.ns(BEAT * 0.75)
        echo = np.zeros_like(mel)
        echo[d:, 0] = mel[:-d, 1] * 0.32
        echo[2 * d:, 1] = mel[:-2 * d, 0] * 0.18
        mel = mel + echo
        # kick ducks the rest a little (the lofi "breathing")
        kenv = np.abs(drums[:, 0])
        kenv = np.convolve(kenv, np.ones(self.ns(0.06)) / self.ns(0.06), mode="same")
        duck = 1 - 0.25 * np.clip(kenv / (kenv.max() + 1e-9) * 3, 0, 1)
        music = (keys * 0.9 + mel * 0.85 + low * 0.42) * duck[:, None] + drums * 0.42 + \
            self.reverb(keys * 0.9 + mel, 2.2) * 0.28
        return self.tape(music)

    def card(self, at, ring):
        """The end card: Cmaj9 rolled slowly on the electric piano, the bass C under it."""
        out = np.zeros((self.N, 2))
        root, voic = CARD_CHORD
        for k, m in enumerate(voic):
            self.put(out, self.epiano(m, ring, 0.6), at + 0.05 * k, 1.0, -0.2 + 0.1 * k)
        self.put(out, self.bass(root, ring * 0.8, 0.35), at)
        self.put(out, self.epiano(79, ring * 0.7, 0.45), at + 0.6, 1.0, 0.3)
        out = out + self.reverb(out, 2.6) * 0.3
        return self.tape(out)

    def tape(self, x):
        """Wow and flutter (a slowly varying delay), soft saturation, a darker top."""
        N, SR = len(x), self.SR
        t = np.arange(N) / SR
        dl = 0.003 + 0.0011 * np.sin(2 * np.pi * 0.42 * t) + 0.00025 * np.sin(2 * np.pi * 5.3 * t + 1.0)
        src = np.clip(np.arange(N) - dl * SR, 0, N - 1)
        y = np.stack([np.interp(src, np.arange(N), x[:, c]) for c in range(2)], 1)
        y = np.tanh(y * 1.6) / 1.6
        return np.stack([self.band(y[:, c], 35, 7800) for c in range(2)], 1)

    def vinyl(self):
        """Dust: a low, warm hiss and sparse crackle (soft clicks, a few louder pops)."""
        N, SR, rng = self.N, self.SR, self.rng
        hiss = np.stack([self.band(rng.standard_normal(N), 900, 6500) for _ in range(2)], 1) * 0.004
        cr = np.zeros((N, 2))
        n = int(N / SR * 9)
        for _ in range(n):
            i = int(rng.integers(0, N - 200))
            a = float(rng.choice([0.02, 0.04, 0.12], p=[0.75, 0.2, 0.05])) * float(rng.uniform(0.5, 1.0))
            L = int(rng.integers(8, 40))
            click = rng.standard_normal(L) * np.exp(-np.arange(L) / (L / 4))
            c = int(rng.integers(0, 2))
            cr[i:i + L, c] += click * a
            cr[i:i + L, 1 - c] += click * a * 0.5
        cr = np.stack([self.band(cr[:, c], 1200, 9000) for c in range(2)], 1)
        return hiss + cr
