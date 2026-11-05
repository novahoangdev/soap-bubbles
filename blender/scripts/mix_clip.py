# Audio for the Soap Bubbles X clip: light, playful synthesised music with a hook + diegetic SFX on the demo events,
# mastered for X (−14 LUFS integrated, true peak ≤ −1 dBTP, 48 kHz stereo 24-bit). numpy only, no samples.
#
#   Music: ~110–120 BPM (tempo derived so the end-card chord lands on a bar line: BAR = (app_end − t0) / bars_to_card),
#     C – Am – F – G. Marimba hook from the very first frame, kalimba counter-line, round plucked bass, soft kick, finger
#     snaps, shaker. Last bar before the card is a breakdown; the music stops dead on the big pop (reverb tail only),
#     then the end card lands on a sustained C add9 with a glockenspiel run, and the title letters "pop" in on a rising arpeggio.
#   SFX (times from the beat sheet "events", app seconds): breath whoosh following the scripted breath envelope (long soft
#     breath + three sharp puffs), quiet film shimmer while the giant bubble grows, wobbly bloop at pinch-off, bubble burbles
#     after each puff, soft ticks when bubbles stick, crisp tiny pops + droplet sparkle on taps, the big delicate pop,
#     droplets landing on the bottom edge, a very quiet garden bed (breeze + two distant birds).
#   Times are app seconds (t = 0 = demo clock start); promo.sh trims the first app_start seconds to match the picture.
#
#   /Applications/Blender.app/Contents/Resources/5.2/python/bin/python3.13 blender/scripts/mix_clip.py \
#       --beats blender/scripts/beats/v1.json [--out render/audio/mix_v1.wav]
#   (or: Blender -b --factory-startup -P blender/scripts/mix_clip.py -- --beats …)
# Writes the WAV named by the beat sheet "audio" (default) + a .json next to it with tempo and measured loudness.
import json, math, os, re, shutil, subprocess, sys, wave

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import synth_audio as sa  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
arg = lambda k, d=None: argv[argv.index(k) + 1] if k in argv else d
ROOT = sa.ROOT
BEATS_PATH = os.path.join(ROOT, arg("--beats", "blender/scripts/beats/v1.json"))
BEATS = json.load(open(BEATS_PATH))
OUT = os.path.join(ROOT, arg("--out", BEATS.get("audio", "render/audio/mix_v1.wav")))
EV = BEATS["events"]
SR = 48000
CARD_AT = float(BEATS["app_end"])
CARD = float(BEATS.get("card", 3.0))
DUR = CARD_AT + CARD + 0.4
N = int(DUR * SR)
rng = np.random.default_rng(7)
db = lambda x: 10 ** (x / 20)
ns = lambda sec: int(round(sec * SR))
tm = np.arange(N) / SR
hz = lambda m: 440.0 * 2 ** ((m - 69) / 12)

MUS = BEATS.get("music", {})
T0 = float(MUS.get("t0", 0.0))
BARS = int(MUS.get("bars_to_card", 7))
BAR = (CARD_AT - T0) / BARS
BEAT = BAR / 4
BPM = 60 / BEAT
BIG = float(EV["big_pop"])
print(f"MIX tempo {BPM:.1f} BPM (bar {BAR:.3f}s), card at {CARD_AT}s, big pop {BIG}s")


# ───────────── stereo bus ─────────────
class Bus:
    def __init__(self):
        self.x = np.zeros((N, 2))

    def put(self, sig, at, gain=1.0, pan=0.0):
        i = ns(at)
        if i >= N or i + len(sig) <= 0:
            return
        s = sig * gain
        if i < 0:
            s, i = s[-i:], 0
        s = s[:N - i]
        if s.ndim == 1:
            self.x[i:i + len(s), 0] += s * math.sqrt((1 - pan) / 2) * 1.414
            self.x[i:i + len(s), 1] += s * math.sqrt((1 + pan) / 2) * 1.414
        else:
            self.x[i:i + len(s)] += s


band = lambda x, lo, hi: sa.band(x, lo, hi, SR)
fades = lambda x, a=0.002, r=0.01: sa.fades(x, SR, a, r)


def reverb(x, sec=1.6, damp=5000, seed=1, pre=0.012):
    r = np.random.default_rng(seed)
    n = ns(sec)
    t = np.arange(n) / SR
    out = np.zeros_like(x)
    for ch in range(2):
        ir = r.standard_normal(n) * np.exp(-t * 6.9 / sec)
        ir = band(ir, 200, damp)
        ir[:ns(pre)] = 0
        ir[ns(pre):ns(pre) + ns(0.01)] *= np.linspace(0, 1, ns(0.01))
        ir /= np.sqrt((ir ** 2).sum())
        L = len(x) + n
        out[:, ch] = np.fft.irfft(np.fft.rfft(x[:, ch], L) * np.fft.rfft(ir, L), L)[:len(x)]
    return out


# ═════════════ 1. MUSIC ═════════════
def at_(bar, beat=0.0):
    """bar/beat → app second (swing: off-beat 8ths pushed a little late)."""
    b = beat + (0.06 if abs(beat * 2 - round(beat * 2)) < 1e-6 and round(beat * 2) % 2 == 1 else 0.0)
    return T0 + bar * BAR + b * BEAT


def marimba(m, vel=1.0):
    """Marimba bar: fundamental + tuned 4th/10th partials that die fast, soft mallet knock. Low notes ring longer."""
    f = hz(m)
    dec = 0.55 * (440 / f) ** 0.45
    t = sa.tt(min(1.6, dec * 4), SR)
    x = np.sin(2 * np.pi * f * t) * np.exp(-t / dec)
    x += 0.32 * np.sin(2 * np.pi * f * 3.93 * t + 0.3) * np.exp(-t / (dec * 0.16))
    if f * 9.2 < 16000:
        x += 0.1 * np.sin(2 * np.pi * f * 9.2 * t + 0.9) * np.exp(-t / (dec * 0.05))
    knock = band(rng.standard_normal(len(t)), 600, 3500) * np.exp(-t / 0.0025) * 0.18
    return fades((x + knock) * np.minimum(t / 0.0012, 1) * 0.42 * vel, 0.0, 0.03)


def kalimba(m, vel=1.0):
    """Kalimba tine: sine with a soft inharmonic overtone and a tiny metallic tick."""
    f = hz(m)
    t = sa.tt(1.3, SR)
    x = np.sin(2 * np.pi * f * t) * np.exp(-t / 0.42)
    x += 0.18 * np.sin(2 * np.pi * f * 5.95 * t) * np.exp(-t / 0.045)
    x += 0.08 * np.sin(2 * np.pi * f * 2.0 * t) * np.exp(-t / 0.2)
    tick = band(rng.standard_normal(len(t)), 2500, 8000) * np.exp(-t / 0.0015) * 0.12
    return fades((x + tick) * np.minimum(t / 0.0015, 1) * 0.35 * vel, 0.0, 0.05)


def glock(m, vel=1.0, sec=1.8):
    f = hz(m)
    t = sa.tt(sec, SR)
    x = sum(a * np.sin(2 * np.pi * f * r * t + r) * np.exp(-t / d) for r, a, d in ((1, 1, 0.9), (2.76, 0.3, 0.25), (5.4, 0.12, 0.08), (8.93, 0.05, 0.04)))
    return fades(x * np.minimum(t / 0.0008, 1) * 0.3 * vel, 0.0, 0.08)


def pad(ms, sec, att=0.4, rel=0.8, cut=2400, vel=1.0):
    n = ns(sec)
    t = np.arange(n) / SR
    x = np.zeros(n)
    for m in ms:
        for d in (-0.004, 0.0, 0.005):
            ph = 2 * np.pi * hz(m) * (1 + d) * t + rng.random() * 6
            x += np.sin(ph) + 0.25 * np.sin(2 * ph) + 0.08 * np.sin(3 * ph)
    e = np.minimum(t / att, 1) * np.clip((sec - t) / rel, 0, 1)
    return band(x * e / (len(ms) * 3), 120, cut) * vel


def bass(m, sec, vel=1.0):
    """Round plucked bass: sine + a little 2nd/3rd harmonic (audible on phone speakers), soft saturation, plucky decay."""
    t = sa.tt(sec, SR)
    f = hz(m)
    x = np.sin(2 * np.pi * f * t) + 0.35 * np.sin(4 * np.pi * f * t) + 0.12 * np.sin(6 * np.pi * f * t)
    x = np.tanh(x * 1.4) / np.tanh(1.4)
    e = np.minimum(t / 0.004, 1) * (0.35 + 0.65 * np.exp(-t / 0.12)) * np.clip((sec - t) / 0.03, 0, 1)
    return fades(x * e * vel, 0.0, 0.02)


def kick(vel=1.0, f0=115, f1=50):
    t = sa.tt(0.35, SR)
    f = f1 + (f0 - f1) * np.exp(-t / 0.03)
    x = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 9)
    x += band(rng.standard_normal(len(t)), 1500, 5000) * np.exp(-t / 0.0015) * 0.05
    return fades(x * vel, 0.0005, 0.02)


def snap(vel=1.0):
    """Finger snap: bright noise crack + short resonant body."""
    t = sa.tt(0.12, SR)
    x = band(rng.standard_normal(len(t)), 1800, 7000) * np.exp(-t / 0.008) * 0.55
    x += np.sin(2 * np.pi * 1450 * t) * np.exp(-t / 0.006) * 0.25
    x += band(rng.standard_normal(len(t)), 900, 2500) * np.exp(-t / 0.02) * 0.12
    return fades(x * vel, 0.0002, 0.02)


def shaker(vel=1.0):
    t = sa.tt(0.09, SR)
    e = np.minimum(t / 0.006, 1) * np.exp(-t / 0.022)
    return fades(band(rng.standard_normal(len(t)), 5500, 11000) * e * 0.3 * vel, 0.0, 0.01)


# chords + hook (C major, MIDI). Hook: a bouncy 2-bar question/answer phrase, syncopated on the "and" of 1.
CH = {"C": [60, 64, 67], "Am": [57, 60, 64], "F": [57, 60, 65], "G": [59, 62, 67]}
ROOTN = {"C": 48, "Am": 45, "F": 41, "G": 43}
HOOK = {
    "C": [(0, 79), (0.5, 76), (1, 79), (1.5, 84), (2.5, 83), (3, 79), (3.5, 76)],
    "Am": [(0, 81), (0.5, 76), (1, 81), (1.5, 84), (2.5, 83), (3, 81), (3.5, 79)],
    "F": [(0, 77), (0.5, 81), (1, 84), (1.5, 81), (2.5, 77), (3, 79), (3.5, 81)],
    "G": [(0, 83), (0.5, 79), (1, 74), (1.5, 79), (2, 83), (2.5, 86), (3.5, 84)],
}
PROG = ["C", "Am", "F", "G", "C", "Am", "F", "G", "C", "Am"]
mel, perc, low, padb = Bus(), Bus(), Bus(), Bus()
# music "style": "chill" (the 3D garden, user: gentle, longer, calmer): no drums, no bouncing bass, the hook every other
# bar on a soft kalimba, a warm pad and long low roots, and the music keeps flowing through the big pop
CHILL = MUS.get("style") == "chill"
# "lofi" (user, 04/11 evening: "lofi or something peaceful, natural birdsong"): lofi_garden.py, and real birdsong
LOFI = MUS.get("style") == "lofi"
# "piano" (user, 04/11 night: a second version with different, more balanced and nicer sound): calm_piano.py, real
# birdsong, and the music / birds / effects balanced by measured level instead of fixed gains
PIANO = MUS.get("style") == "piano"
SOFT = LOFI or PIANO
for bar in range(BARS if CHILL else 0):
    c = PROG[bar % 4]
    padb.put(pad(CH[c] + [ROOTN[c] + 12, CH[c][1] + 12], BAR + 1.2, att=0.9, rel=1.4, cut=2000, vel=1.0), at_(bar), 1.0)
    low.put(pad([ROOTN[c] - 12, ROOTN[c]], BAR + 0.8, att=0.6, rel=1.0, cut=500, vel=0.9), at_(bar), 0.7)
    if bar % 2 == 0 and bar < BARS - 1:
        for b_, m in HOOK[c][::2]:
            mel.put(kalimba(m - 12 if m > 80 else m, 0.42), at_(bar, b_ * 1.0), 1.0, 0.3 * (((m % 7) - 3) / 3))
    else:
        for k, b_ in enumerate((0.0, 1.0, 2.0, 3.0)):
            m = CH[c][k % 3] + 12
            mel.put(marimba(m, 0.22), at_(bar, b_ + 0.03), 1.0, 0.4 if k % 2 else -0.4)
for bar in range(0 if (CHILL or SOFT) else BARS):
    c = PROG[bar % 4]
    last = bar == BARS - 1                       # breakdown bar before the card (the giant bubble ages and pops)
    lift = 12 if bar in (4, 5) else 0            # second half: hook an octave up on glock + marimba below
    # hook
    for b_, m in HOOK[c]:
        if last and b_ > 2.0:
            continue
        vel = 1.0 if b_ == 0 else 0.82
        if last:
            vel *= 0.75
        mel.put(marimba(m, vel), at_(bar, b_), 1.0, 0.18 * (((m % 7) - 3) / 3))
        if lift:
            mel.put(glock(m + 12 if m < 82 else m, 0.45), at_(bar, b_), 1.0, -0.25)
    # kalimba counter-line on the off-beats (bars 2–5), chord tones a sixth below the hook
    if 2 <= bar <= 5:
        for k, b_ in enumerate((0.5, 1.5, 2.5, 3.5)):
            m = CH[c][(k + bar) % 3]
            mel.put(kalimba(m, 0.55), at_(bar, b_ + 0.02), 1.0, 0.45 if k % 2 else -0.45)
    # pad underneath
    padb.put(pad(CH[c] + [ROOTN[c] + 12], BAR + 0.6, att=0.3 if bar else 0.01, rel=0.7, vel=0.9 if not last else 1.1), at_(bar), 1.0)
    # bass (from bar 1): root – root – fifth – octave, bouncing
    if 1 <= bar and not last:
        r = ROOTN[c]
        for b_, m, l in ((0, r, 0.9), (1.5, r, 0.45), (2, r + 7, 0.9), (3.5, r + 12, 0.4)):
            low.put(bass(m - 12 if m >= 48 else m, BEAT * l), at_(bar, b_), 0.55 if bar > 1 else 0.4)
    elif last:
        low.put(bass(ROOTN[c] - 12 if ROOTN[c] >= 48 else ROOTN[c], BEAT * 2.2), at_(bar), 0.45)
    # drums
    if 1 <= bar and not last:
        k_amt = 0.55 if bar == 1 else 0.8
        for b_ in (0, 2):
            perc.put(kick(), at_(bar, b_), k_amt)
        if bar in (3, 5):
            perc.put(kick(0.7), at_(bar, 2.5), k_amt)
        for b_ in (1, 3):
            perc.put(snap(), at_(bar, b_), 0.55 if bar > 1 else 0.4, 0.15)
    for k in range(16):
        if (bar == 0 and k < 8) or (last and k > 9):   # shaker enters halfway through bar 0, thins out before the big pop
            continue
        v = (0.9 if k % 4 == 2 else 0.5 if k % 2 else 0.35) * (0.7 if last else 1.0)
        perc.put(shaker(v), T0 + bar * BAR + k * BEAT / 4 + (0.012 if k % 2 else 0), 0.75, 0.35)

# little rising "bubble" fill on the last beat before the taps section (bar 4) and before the breakdown
for b_, m in ((3.0, 72), (3.25, 76), (3.5, 79), (3.75, 84)) if not SOFT else ():
    mel.put(kalimba(m, 0.5), at_(3, b_), 1.0, 0.3)

music = mel.x + perc.x * 0.95 + low.x + padb.x * 0.8
music = music + reverb(music, 2.4 if CHILL else 1.6) * (0.32 if CHILL else 0.22)
if LOFI:
    import lofi_garden  # noqa: E402
    LF = lofi_garden.Lofi(N, SR, T0, BAR, BARS, CARD_AT, BIG, band, reverb)
    music = LF.render()
if PIANO:
    import calm_piano  # noqa: E402
    PF = calm_piano.Piano(N, SR, T0, BAR, BARS, CARD_AT, BIG, float(EV["pinch"]), band, reverb)
    music = PF.render()
# the music stops dead on the big pop (only the reverb tail rings), then the card lands (chill: it flows on to the card)
i_stop = ns(CARD_AT if (CHILL or SOFT) else BIG)
dry_tail = music.copy()
music[i_stop:] = 0
tail = reverb(np.concatenate([dry_tail[:i_stop], np.zeros((N - i_stop, 2))]), 1.4) * 0.5
music[i_stop:] += tail[i_stop:] * np.linspace(1, 0, N - i_stop)[:, None] ** 2

# end card: sustained C add9 (pad + marimba roll), soft kick + bass, glockenspiel run up; title letters pop in on an arpeggio
card = Bus()
ring = CARD + 0.35
if LOFI:
    card.put(LF.card(0.0, ring)[:ns(ring + 3.0)], CARD_AT, 1.0)
elif PIANO:
    card.put(PF.card(0.0, ring), CARD_AT, 1.0)
else:
    card.put(pad([48, 55, 60, 64, 67, 74], ring, att=0.02, rel=1.5, cut=3400), CARD_AT, 0.85)
if not (CHILL or SOFT):  # (lofi / piano: their own card chord; this kick and bass thumped under it)
    card.put(bass(36, 1.4), CARD_AT, 0.55)
    card.put(kick(1.0, 120, 48), CARD_AT, 0.85)
for k, m in enumerate((60, 64, 67, 72, 76, 79) if not SOFT else ()):
    card.put(marimba(m, 0.7), CARD_AT + k * 0.035, 1.0, -0.4 + 0.16 * k)
for k, m in enumerate((79, 84, 88, 91) if not PIANO else ()):
    card.put(glock(m, 0.55 if not LOFI else 0.3, 2.2), CARD_AT + 0.6 + k * BEAT / 2, 1.0, 0.4 - 0.2 * k)
title = BEATS.get("title", "Soap Bubbles")
letters = [i for i, ch in enumerate(title) if ch != " "]
ti, ts = float(BEATS.get("title_in", 0.12)), float(BEATS.get("title_step", 0.055))
arp = [72, 74, 76, 79, 81, 84, 86, 88, 91, 93, 96]
for k, _ in enumerate(letters):
    # a bubbly little "pip" tuned to the arpeggio — promo.py makes letter k pop in at card + title_in + k * title_step
    m = arp[min(k, len(arp) - 1)]
    t = sa.tt(0.08, SR)
    f = hz(m) * (0.75 + 0.25 * np.clip(t / 0.012, 0, 1))
    pip = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / 0.025) * np.minimum(t / 0.001, 1)
    card.put(fades(pip, 0, 0.005) * 0.16, CARD_AT + ti + k * ts, 1.0, -0.5 + k / max(1, len(letters) - 1))
cx = card.x + reverb(card.x, 2.2, seed=4) * 0.3
music = music + cx

# per-section levels: the music sits back under the breath and the pops, a little forward at the start and on the card
lvl = np.interp(tm, [0, 1.2, 1.5, 4.4, 5.0, 9.5, 12.6, BIG, CARD_AT, DUR],
                [0.9, 0.9, 0.72, 0.72, 0.8, 0.74, 0.78, 0.8, 1.0, 1.0]) if not (CHILL or SOFT) else np.full_like(tm, 0.9)
music *= lvl[:, None]

# ═════════════ 2. SOUND EFFECTS ═════════════
fx = Bus()
# breath: whoosh following the scripted envelope (long soft breath + three sharp puffs, which are brighter)
kf = np.array(EV["breath"], dtype=float)
level = np.interp(tm, kf[:, 0], kf[:, 1], left=0, right=0)
level = np.convolve(level, np.ones(ns(0.03)) / ns(0.03), mode="same")
SPLIT = float(EV.get("puff_split", 4.8))  # long breath before, sharp puffs after
SPLIT2 = float(EV.get("breath2_from", 1e9))  # a second soft breath late in the clip (night bubble)
long_ = level * ((tm < SPLIT) | (tm >= SPLIT2))
puffs = level * ((tm >= SPLIT) & (tm < SPLIT2))
if "puff_windows" in EV:
    # (3D chill: sharp puffs wherever they are in the clip, everything else is the long soft breath)
    inwin = np.zeros_like(tm, dtype=bool)
    for a, b_ in EV["puff_windows"]:
        inwin |= (tm >= a - 0.05) & (tm < b_ + 0.1)
    long_, puffs = level * ~inwin, level * inwin
fx.put(sa.breath_noise(SR, 31, long_, 0.85) * (0.45 if SOFT else 0.7), 0, 1.0, -0.05)
fx.put(sa.breath_noise(SR, 32, puffs, 1.3) * (0.12 if SOFT else 0.26), 0, 1.0, 0.05)
# quiet glassy shimmer while the giant bubble grows (colours rushing)
g0, g1 = EV.get("grow", [1.5, EV["pinch"]])
glen = g1 - g0 + 0.4
gl = np.clip(np.arange(ns(glen)) / SR / (g1 - g0), 0, 1) ** 1.5
gl *= np.clip((glen - np.arange(ns(glen)) / SR) / 0.4, 0, 1)
fx.put(sa.shimmer(SR, 41, glen, gl) * 0.05, g0, 1.0, 0.0)
# day → night: a soft magical swell (glassy shimmer + a low airy whoosh) while the light changes
if EV.get("look_switch"):
    ts = float(EV["look_switch"])
    sl = 2.2
    env_ = np.sin(np.pi * np.clip(np.arange(ns(sl)) / SR / sl, 0, 1)) ** 1.5
    fx.put(sa.shimmer(SR, 97, sl, env_) * 0.16, ts - 0.3, 1.0, 0.0)
    fx.put(sa.breath_noise(SR, 98, env_ * 0.5, 0.6) * 0.18, ts - 0.3, 1.0, 0.0)
# pinch-off: wobbly bloop
fx.put(sa.bloop(SR, 3), EV["pinch"], 0.7, -0.05)
if EV.get("pinch2"):
    fx.put(sa.bloop(SR, 4), float(EV["pinch2"]), 0.55, 0.05)
# puffs: burbles of little bubbles tumbling out
for k, t_ in enumerate(EV["puffs"]):
    fx.put(sa.burbles(SR, 50 + k, n=9, spread=0.5, amp=0.2), t_ + 0.04, 1.0, -0.3 + 0.3 * k)
# sticks: soft ticks
for k, t_ in enumerate(EV.get("sticks", [])):
    fx.put(sa.stick(SR, 60 + k), t_, 0.32, 0.25 * (-1) ** k)
# taps (v33): soft musical pops, a rising-then-falling run on C major pentatonic (they land on the music's key, like chimes)
NOTES = [0, 1, 2, 3, 4, 3, 5, 2, 4, 1]
for k, t_ in enumerate(EV["taps"]):
    pan = float(rng.uniform(-0.35, 0.35))
    fx.put(sa.pop_soft(SR, 200 + k, sa.PENTA[NOTES[k % len(NOTES)]]), t_, 0.62, pan)
# the giant: a round bloop opening into a soft bell chord
fx.put(sa.pop_big_soft(SR, 5), BIG, 0.8, 0.0)
for k, t_ in enumerate(EV.get("drips", [])):
    fx.put(sa.drip(SR, rng), t_, 0.12 * (1 - 0.1 * k), float(rng.uniform(-0.5, 0.5)))
fx.x = fx.x + reverb(fx.x, 0.9, damp=7000, seed=9) * 0.18

# ═════════════ 3. GARDEN BED ═════════════
amb = Bus()
br = band(rng.standard_normal(N), 150, 1200)
br2 = band(rng.standard_normal(N), 150, 1200)
sway = 0.012 * (1 + 0.4 * np.sin(2 * np.pi * 0.09 * tm) + 0.2 * np.sin(2 * np.pi * 0.23 * tm + 1))
amb.x[:, 0] += br / (br.std() + 1e-9) * sway
amb.x[:, 1] += br2 / (br2.std() + 1e-9) * sway
BIRDS = ((0.6, -0.7), (8.0, 0.65), (12.9, -0.5))
if CHILL:  # a quiet meadow all the way through: a distant bird every ~6 s
    BIRDS = tuple((0.8 + 6.1 * k + 1.3 * ((k * 7) % 3), (-0.7, 0.6, -0.3, 0.5)[k % 4]) for k in range(int(DUR / 6.1)))
if SOFT:
    BIRDS = ()


def load_audio(rel):
    """a recording from the repo (FLAC etc.) as float stereo at SR, via ffmpeg"""
    r = subprocess.run([shutil.which("ffmpeg") or "/opt/homebrew/bin/ffmpeg", "-v", "error", "-i", os.path.join(ROOT, rel),
                        "-f", "f32le", "-ac", "2", "-ar", str(SR), "-"], capture_output=True, check=True)
    return np.frombuffer(r.stdout, np.float32).reshape(-1, 2).astype(np.float64)


for k, (t_, pan) in enumerate(BIRDS):
    amb.put(band(sa.bird(SR, 90 + k), 1800, 6000), t_, 0.035, pan)
if SOFT:
    # real birdsong (blender/audio/birds/README.md: public domain field recordings): a wide dawn-chorus bed (a different
    # stretch on each side), a blackbird singing close by at the start, a blackcap and a chaffinch deeper in the wood
    # during the follow, garden birds when the camera is home again
    B = "blender/audio/birds/"
    rms = lambda a: float(np.sqrt((a ** 2).mean()) + 1e-9)
    bed_a, bed_b = load_audio(B + "dawn_chorus_a.flac")[:, 0], load_audio(B + "dawn_chorus_b.flac")[:, 0]
    L = min(len(bed_a), len(bed_b), N)
    bed = np.stack([bed_a[:L], bed_b[:L]], 1) / rms(bed_a)
    fin = np.minimum(np.arange(L) / ns(2.5), 1.0)[:, None]
    amb.x[:L] += bed * fin * 0.013
    solo = [(B + "blackbird_forest.flac", 0.4, 0.0, -0.25), (B + "blackcap_chaffinch.flac", max(0.0, EV["pinch"] + 4.0), 0.0, 0.45),
            (B + "garden_birds.flac", max(0.0, BIG + 3.0), 0.0, -0.45)]
    for path, at, skip, pan in solo:
        a = load_audio(path)[ns(skip):]
        a = a / rms(a)
        L2 = min(len(a), N - ns(at))
        e = np.minimum(np.arange(L2) / ns(1.5), 1.0) * np.clip((L2 - np.arange(L2)) / ns(2.0), 0, 1)
        a = a[:L2] * e[:, None]
        mono = a.mean(1)
        amb.put(np.stack([mono * math.sqrt((1 - pan) / 2) * 1.414 * 0.6 + a[:, 0] * 0.4,
                          mono * math.sqrt((1 + pan) / 2) * 1.414 * 0.6 + a[:, 1] * 0.4], 1), at, 0.024)
    if LOFI:
        amb.x += LF.vinyl()
amb.x[ns(CARD_AT):] *= np.linspace(1, 0.4, N - ns(CARD_AT))[:, None]

if PIANO:
    # balance by measured level (over the clip, in the 200 Hz – 6 kHz band where the ear and a phone speaker live):
    # the birds ~11 dB under the music, the effects (breath, bloops, pops) ~7 dB under, so nothing pokes out
    def lvl_(x, a=1.0, b=CARD_AT):
        seg = x[ns(a):ns(b)].mean(1)
        return float(np.sqrt((band(seg, 200, 6000) ** 2).mean()) + 1e-12)
    ref = lvl_(music)
    # (the mix below takes music −3 dB, effects 0, ambience −2)
    amb.x *= ref * db(-3 - 11 + 2) / lvl_(amb.x)
    fx.x *= ref * db(-3 - 7) / lvl_(fx.x)
    print(f"MIX balance: music {20 * math.log10(ref):.1f} dB, birds −11, effects −7 (band RMS)")

# ═════════════ 4. MIX + MASTER ═════════════
mix = music * db(-3) + fx.x * db(0) + amb.x * db(-2)
for ch in range(2):
    mix[:, ch] = band(mix[:, ch], 40, None)          # nothing below 40 Hz (phone speakers), saves headroom
    mix[:, ch] += band(mix[:, ch], 1500, 5000) * 0.1  # a touch of presence for small speakers
mix[-ns(0.3):] *= np.linspace(1, 0, ns(0.3))[:, None]
FFMPEG = shutil.which("ffmpeg") or "/opt/homebrew/bin/ffmpeg"
LUFS, TP = -14.3, -1.0   # linear loudnorm lands ~0.3 LU above target → −14.3 so ebur128 reads −14.0


def write_wav24(path, x):
    a = np.round(np.clip(x, -1, 1) * 8388607).astype("<i4")
    with wave.open(path, "wb") as w_:
        w_.setnchannels(2)
        w_.setsampwidth(3)
        w_.setframerate(SR)
        w_.writeframes(a.view(np.uint8).reshape(-1, 4)[:, :3].tobytes())


def os_peaks(x, k=4):
    p = np.zeros(len(x))
    for c in range(2):
        y = np.fft.irfft(np.fft.rfft(x[:, c]), k * len(x)) * k
        p = np.maximum(p, np.abs(y).reshape(-1, k).max(1))
    return p


def limiter(x, ceil_db, look=0.002, rel=0.08):
    """Look-ahead true-peak-ish limiter (4x oversampled peaks), block release."""
    g = np.minimum(1, db(ceil_db) / np.maximum(os_peaks(x), 1e-9))
    w = ns(look)
    gm = np.lib.stride_tricks.sliding_window_view(np.concatenate([np.ones(w), g, np.ones(w)]), 2 * w + 1).min(1)
    h = w // 2
    box = np.convolve(np.concatenate([np.ones(h), gm, np.ones(h)]), np.ones(2 * h + 1) / (2 * h + 1), "valid")
    B = 48
    nb_ = len(gm) // B
    blk = gm[:nb_ * B].reshape(nb_, B).min(1)
    kr = 1 - math.exp(-B / SR / rel)
    y, out = 1.0, np.empty(nb_)
    for i, v in enumerate(blk):
        y = min(v, y + (1 - y) * kr)
        out[i] = y
    rc = np.interp(np.arange(len(gm)), np.arange(nb_) * B, out)
    gg = np.minimum(box, rc)
    return x * gg[:, None], 20 * np.log10(gg.min())


def loudnorm_measure(path):
    r = subprocess.run([FFMPEG, "-hide_banner", "-nostats", "-i", path, "-af",
                        f"loudnorm=I={LUFS}:TP={TP}:LRA=20:print_format=json", "-f", "null", "-"], capture_output=True, text=True)
    return json.loads(r.stderr[r.stderr.rindex("{"):r.stderr.rindex("}") + 1])


os.makedirs(os.path.dirname(OUT), exist_ok=True)
PRE = OUT[:-4] + "_premaster.wav"
base = mix * 0.5 / max(1e-6, np.abs(mix).max())
write_wav24(PRE, base)
m1 = loudnorm_measure(PRE)
x = base * db(LUFS - float(m1["input_i"]))
x, gr = limiter(x, TP - 0.6)
write_wav24(PRE, x)
m2 = loudnorm_measure(PRE)
subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", "-y", "-i", PRE, "-af",
                f"loudnorm=I={LUFS}:TP={TP}:LRA=20:measured_I={m2['input_i']}:measured_TP={m2['input_tp']}:"
                f"measured_LRA={m2['input_lra']}:measured_thresh={m2['input_thresh']}:offset={m2['target_offset']}:linear=true:"
                f"print_format=summary", "-ar", str(SR), "-ac", "2", "-c:a", "pcm_s24le", OUT], check=True)
os.remove(PRE)
r = subprocess.run([FFMPEG, "-hide_banner", "-nostats", "-i", OUT, "-af", "ebur128=peak=true", "-f", "null", "-"],
                   capture_output=True, text=True).stderr
summ = r[r.rindex("Summary:"):]
I_ = float(re.search(r"I:\s*(-?[\d.]+) LUFS", summ).group(1))
TP_ = float(re.search(r"Peak:\s*(-?[\d.]+) dBFS", summ).group(1))
json.dump({"bpm": round(BPM, 2), "bar": round(BAR, 4), "card_at": CARD_AT, "big_pop": BIG, "dur": round(DUR, 3),
           "limiter_gr_db": round(-gr, 2), "lufs": I_, "true_peak": TP_}, open(OUT[:-4] + ".json", "w"), indent=1)
print(f"MIX limiter GR {-gr:.1f} dB | AUDIO {os.path.relpath(OUT, ROOT)} {DUR:.1f}s | I {I_:.1f} LUFS, true peak {TP_:.1f} dBTP")
