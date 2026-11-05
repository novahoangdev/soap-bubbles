# Soap Bubbles sound effects, synthesised with numpy (no samples, no copyrighted material).
#
# Used two ways:
#   1. imported by mix_clip.py (the X clip mix): every generator takes the sample rate and a seed and returns mono float arrays.
#   2. run directly: writes the in-app one-shots to app/assets/sfx/ (mono 44.1 kHz 16-bit WAV, peak-normalised, < 60 KB each)
#        pop_1..pop_6   soft musical pop: water-drop plip + kalimba note on C major pentatonic (v33; was a click + glints)
#        pop_big        the giant: round low bloop opening into a soft bell chord (v33)
#        music.wav      calm ambient background loop in C major, no bass (v33)
#        bloop          wobbly "bloop" when a bubble pinches off the wand
#        puff           a short sharp breath puff with little bubble burbles (spray of small bubbles)
#        stick          soft "tick" when two bubbles touch and stick together
#
# Run with Blender's bundled Python (has numpy), either of:
#   /Applications/Blender.app/Contents/Resources/5.2/python/bin/python3.13 blender/scripts/synth_audio.py
#   /Applications/Blender.app/Contents/MacOS/Blender -b --factory-startup -P blender/scripts/synth_audio.py
import math, os, sys, wave

import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
APP_OUT = os.path.join(ROOT, "app", "assets", "sfx")


# ───────────────────────── basic DSP ─────────────────────────
def tt(sec, sr):
    return np.arange(int(round(sec * sr))) / sr


def band(x, lo, hi, sr):
    """FFT band-pass with soft (4th order-ish) edges; lo or hi may be None."""
    if len(x) < 4:
        return x
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(len(x), 1 / sr)
    m = np.ones_like(f)
    if lo:
        m /= 1 + (lo / np.maximum(f, 1)) ** 4
    if hi:
        m /= 1 + (f / hi) ** 4
    return np.fft.irfft(X * m, len(x))


def peak_eq(x, f0, gain_db, q, sr):
    """Gentle FFT bell boost/cut (formants, presence)."""
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(len(x), 1 / sr)
    g = 10 ** (gain_db / 20)
    bw = f0 / q
    m = 1 + (g - 1) / (1 + ((f - f0) / (bw / 2)) ** 2)
    return np.fft.irfft(X * m, len(x))


def fades(x, sr, a=0.001, r=0.01):
    x = x.copy()
    na, nr = max(1, int(a * sr)), max(1, int(r * sr))
    na, nr = min(na, len(x)), min(nr, len(x))
    x[:na] *= np.linspace(0, 1, na)
    x[-nr:] *= np.linspace(1, 0, nr)
    return x


def glide(f, sr):
    """Phase of a sine with per-sample frequency f (Hz)."""
    return 2 * np.pi * np.cumsum(f) / sr


def place(dst, src, at, sr, gain=1.0):
    i = int(round(at * sr))
    if i >= len(dst):
        return
    s = src[: len(dst) - i] * gain
    dst[i:i + len(s)] += s


# ───────────────────────── sound generators ─────────────────────────
def tinkle(sr, rng, f=None, dur=None, amp=1.0):
    """One droplet glint: a tiny glassy ping (two inharmonic partials), very short."""
    f = f or float(rng.uniform(3200, 7200))
    dur = dur or float(rng.uniform(0.035, 0.09))
    t = tt(dur * 1.6, sr)
    x = np.sin(2 * np.pi * f * t) * np.exp(-t / (dur * 0.35))
    x += 0.35 * np.sin(2 * np.pi * f * 2.71 * t) * np.exp(-t / (dur * 0.15))
    return fades(x * np.minimum(t / 0.0015, 1) * amp, sr, 0.0, 0.004)


def sparkle(sr, seed, n=7, spread=0.32, lo=3200, hi=7400, amp=0.35):
    """Droplet sparkle: n glints scattered over `spread` seconds, getting quieter (droplets flying away)."""
    rng = np.random.default_rng(seed)
    out = np.zeros(int((spread + 0.2) * sr))
    times = np.sort(rng.uniform(0.008, spread, n) ** 1.4 / spread ** 0.4)
    for k, t0 in enumerate(times):
        a = amp * (1 - 0.65 * k / max(1, n - 1)) * float(rng.uniform(0.6, 1.0))
        place(out, tinkle(sr, rng, float(rng.uniform(lo, hi)), amp=a), t0, sr)
    return out


def pop_core(sr, seed, size=1.0):
    """Crisp tiny bubble pop: film tear click + a quick downward 'pip' (pitch ∝ 1/size) + a breath of air."""
    rng = np.random.default_rng(seed)
    dur = 0.09 + 0.05 * size
    t = tt(dur, sr)
    n = len(t)
    # tear click: 1–2 ms of bright noise
    click = band(rng.standard_normal(n), 2500, 11000, sr) * np.exp(-t / 0.0011)
    # 'pip': the film snapping back, a fast pitch drop
    f0 = float(rng.uniform(1500, 1900)) / size ** 0.5
    f = f0 * (0.42 + 0.58 * np.exp(-t / 0.012))
    pip = np.sin(glide(f, sr)) * np.exp(-t / (0.011 + 0.006 * size)) * np.minimum(t / 0.0005, 1)
    # body: a soft low 'puck' (the air inside), gives the pop some roundness
    fb = 520 / size ** 0.4
    body = np.sin(glide(fb * (0.6 + 0.4 * np.exp(-t / 0.02)), sr)) * np.exp(-t / (0.014 + 0.01 * size))
    air = band(rng.standard_normal(n), 1200, 7000, sr) * np.exp(-t / 0.018) * 0.12
    x = click * 0.55 + pip * 0.6 + body * 0.32 * min(1.3, size) + air
    return fades(x, sr, 0.0, 0.01)


def pop_small(sr, seed, size=1.0, sparkle_n=7):
    """Pop + droplet sparkle in one mono file (in-app version)."""
    core = pop_core(sr, seed, size)
    sp = sparkle(sr, seed + 100, n=sparkle_n, spread=0.26 + 0.08 * size, amp=0.32)
    out = np.zeros(max(len(core), len(sp) + int(0.01 * sr)))
    place(out, core, 0, sr)
    place(out, sp, 0.012, sr)
    return out


def pop_big_core(sr, seed=5):
    """The giant bubble: a bigger but delicate pop — soft low thump, airy tear sweeping down, faint film 'shimmer' snap."""
    rng = np.random.default_rng(seed)
    t = tt(0.42, sr)
    n = len(t)
    click = band(rng.standard_normal(n), 2000, 10000, sr) * np.exp(-t / 0.0016)
    f = 980 * (0.3 + 0.7 * np.exp(-t / 0.022))
    pip = np.sin(glide(f, sr)) * np.exp(-t / 0.028) * np.minimum(t / 0.0006, 1)
    body = np.sin(glide(190 * (0.65 + 0.35 * np.exp(-t / 0.05)), sr)) * np.exp(-t / 0.06) * np.minimum(t / 0.002, 1)
    # tear: rim racing around the sphere = a quick downward noise sweep
    nz = rng.standard_normal(n)
    tear = np.zeros(n)
    seg = 512
    for i in range(0, n - seg, seg // 2):
        u = i / n
        fc = 7000 * (0.25 + 0.75 * (1 - u) ** 2)
        tear[i:i + seg] += band(nz[i:i + seg], fc * 0.5, fc * 1.4, sr) * np.hanning(seg)
    tear *= np.exp(-t / 0.07) * np.minimum(t / 0.003, 1)
    x = click * 0.5 + pip * 0.55 + body * 0.55 + tear * 0.4
    return fades(x, sr, 0.0, 0.03)


def pop_big(sr, seed=5):
    core = pop_big_core(sr, seed)
    sp = sparkle(sr, seed + 7, n=16, spread=0.48, lo=2600, hi=7800, amp=0.3)
    out = np.zeros(int(0.66 * sr))
    place(out, core, 0, sr)
    place(out, sp, 0.015, sr)
    return fades(out, sr, 0.0, 0.05)


def bloop(sr, seed=3, base=260.0, dur=0.32):
    """Wobbly 'bloop' of a pinch-off: rising rounded tone with a decaying wobble (the bubble jiggling), soft neck 'snap'."""
    rng = np.random.default_rng(seed)
    t = tt(dur, sr)
    u = np.clip(t / 0.09, 0, 1)
    wob = 1 + 0.085 * np.sin(2 * np.pi * 13 * t) * np.exp(-t / 0.12)
    f = base * (1 + 1.1 * (1 - (1 - u) ** 2)) * wob
    ph = glide(f, sr)
    x = np.sin(ph) + 0.22 * np.sin(2 * ph + 0.4) + 0.06 * np.sin(3 * ph)
    e = np.minimum(t / 0.006, 1) * np.exp(-t / 0.085) * (1 + 0.25 * np.sin(2 * np.pi * 13 * t + 1) * np.exp(-t / 0.1))
    snap = band(rng.standard_normal(len(t)), 1800, 7000, sr) * np.exp(-t / 0.002) * 0.25
    return fades(x * e * 0.8 + snap, sr, 0.0, 0.02)


def burble(sr, rng, f=None):
    """Tiny bubble 'blip': a very short upward chirp (like a bubble rising in water, but light)."""
    f = f or float(rng.uniform(900, 2100))
    d = float(rng.uniform(0.02, 0.04))
    t = tt(d * 1.5, sr)
    ph = glide(f * (1 + 0.9 * np.clip(t / d, 0, 1)), sr)
    return fades(np.sin(ph) * np.sin(np.pi * np.clip(t / (d * 1.5), 0, 1)) ** 1.5, sr, 0.0, 0.003)


def burbles(sr, seed, n=8, spread=0.42, amp=0.22):
    rng = np.random.default_rng(seed)
    out = np.zeros(int((spread + 0.1) * sr))
    for k in range(n):
        t0 = float(rng.uniform(0.04, spread)) * (0.4 + 0.6 * k / n)
        place(out, burble(sr, rng), t0, sr, amp * float(rng.uniform(0.5, 1.0)))
    return out


def breath_noise(sr, seed, level, bright=1.0):
    """Breath/whoosh following an envelope `level` (0..1 per sample): airy 'hhh' band + soft wind rumble on the mic.
    The band opens up and brightens with the level (soft breath = dark and gentle, sharp puff = brighter)."""
    rng = np.random.default_rng(seed)
    n = len(level)
    nz = rng.standard_normal(n)
    out = np.zeros(n)
    seg = 2048
    win = np.hanning(seg)
    for i in range(0, n - seg, seg // 4):
        lv = float(level[i:i + seg].mean())
        if lv < 1e-3:
            continue
        fc = (700 + 1500 * lv) * bright
        air = band(nz[i:i + seg], fc * 0.45, fc * 2.4, sr)
        rum = band(nz[i:i + seg], 90, 380, sr) * 0.55
        out[i:i + seg] += (air + rum) * win * 0.5
    out = peak_eq(out, 1200, 3, 1.2, sr)          # breathy "h" formant
    return out * level ** 1.25


def puff(sr, seed=11):
    """Short sharp puff (in-app): fast attack breath burst + little bubble burbles."""
    n = int(0.6 * sr)
    t = np.arange(n) / sr
    lv = np.minimum(t / 0.02, 1) * np.exp(-np.maximum(t - 0.05, 0) / 0.11)
    x = breath_noise(sr, seed, lv, 1.35) * 0.9
    place(x, burbles(sr, seed + 1, n=7, spread=0.38, amp=0.2), 0.05, sr)
    return fades(x, sr, 0.002, 0.04)


def stick(sr, seed=21):
    """Soft 'tick' of two films touching: muted glassy tick + tiny low 'thup', gentle, not harsh."""
    rng = np.random.default_rng(seed)
    t = tt(0.12, sr)
    f = float(rng.uniform(1500, 1750))
    tick = (np.sin(2 * np.pi * f * t) + 0.3 * np.sin(2 * np.pi * f * 2.92 * t)) * np.exp(-t / 0.009)
    thup = np.sin(glide(330 * (0.7 + 0.3 * np.exp(-t / 0.015)), sr)) * np.exp(-t / 0.022)
    nz = band(rng.standard_normal(len(t)), 2000, 6000, sr) * np.exp(-t / 0.0015) * 0.2
    return fades((tick * 0.45 + thup * 0.5 + nz) * np.minimum(t / 0.0007, 1), sr, 0.0, 0.01)


def shimmer(sr, seed, dur, level=None):
    """Quiet glassy shimmer (the film colours rushing while the giant bubble grows): a few high partials with slow tremolo."""
    rng = np.random.default_rng(seed)
    t = tt(dur, sr)
    x = np.zeros(len(t))
    for k in range(6):
        f = float(rng.uniform(2200, 5200))
        x += np.sin(2 * np.pi * f * t + rng.uniform(0, 6)) * (0.5 + 0.5 * np.sin(2 * np.pi * rng.uniform(1.5, 4.5) * t + rng.uniform(0, 6)))
    x /= 6
    e = np.ones(len(t)) if level is None else level
    return fades(x * e, sr, 0.15, 0.25)


def drip(sr, rng):
    """A droplet landing on the bottom edge: tiny high 'plip'."""
    t = tt(0.05, sr)
    f = float(rng.uniform(1800, 3200))
    ph = glide(f * (1 + 0.5 * np.clip(t / 0.01, 0, 1)), sr)
    return fades(np.sin(ph) * np.exp(-t / 0.008), sr, 0.0, 0.004)


def bird(sr, seed):
    """Distant garden bird: two or three quick FM chirps (very quiet in the mix)."""
    rng = np.random.default_rng(seed)
    out = np.zeros(int(0.7 * sr))
    t0 = 0.0
    for _ in range(int(rng.integers(2, 4))):
        d = float(rng.uniform(0.06, 0.11))
        t = tt(d, sr)
        u = t / d
        f = float(rng.uniform(2600, 3600)) * (1 + 0.35 * np.sin(np.pi * u)) * (1 + 0.04 * np.sin(2 * np.pi * 45 * t))
        place(out, np.sin(glide(f, sr)) * np.sin(np.pi * u) ** 2, t0, sr)
        t0 += d + float(rng.uniform(0.04, 0.09))
    return out


# ───────────────────────── v33: soft, musical pops ─────────────────────────
# The first pops (noise click 2.5–11 kHz + glassy 3–7 kHz glints) read as harsh. A real small bubble pop is barely audible;
# for an app that you play with for minutes it should be pleasant: a rounded water-drop "plip" with no click, carrying a soft
# kalimba-like note. The notes come from C major pentatonic (the key of the clip music and the in-app loop), so a run of pops
# sounds like wind chimes instead of noise.
def reverb(x, sr, decay=2.4, mix=0.32, seed=9):
    """Cheap convolution reverb: exponentially decaying filtered noise IR (stereo-ish smear, here mono)."""
    rng = np.random.default_rng(seed)
    n = int(decay * sr)
    ir = band(rng.standard_normal(n), 300, 7000, sr) * np.exp(-np.arange(n) / sr / (decay / 6.9))
    ir /= np.sqrt(np.sum(ir ** 2))
    L = len(x) + n
    y = np.fft.irfft(np.fft.rfft(x, L) * np.fft.rfft(ir, L), L)[:len(x)]
    return x * (1 - mix) + y * mix



PENTA = [392.0, 440.0, 523.25, 587.33, 659.26, 783.99]   # G4 A4 C5 D5 E5 G5 (v33b: an octave lower, warmer)


def pluck(sr, f, dur=0.6, bright=0.25):
    """Soft kalimba-ish pluck: fundamental + a quiet octave + a faint inharmonic tine partial that dies fast."""
    t = tt(dur, sr)
    x = np.sin(2 * np.pi * f * t) * np.exp(-t / (dur * 0.32))
    x += 0.18 * np.sin(2 * np.pi * f * 2.0 * t) * np.exp(-t / (dur * 0.16))
    x += bright * 0.12 * np.sin(2 * np.pi * f * 5.4 * t) * np.exp(-t / 0.02)
    return fades(x * np.minimum(t / 0.004, 1), sr, 0.0, 0.03)


def plip(sr, f, dur=0.07):
    """Water-drop 'plip': a sine gliding up into the note, rounded attack (no click)."""
    t = tt(dur * 1.8, sr)
    fr = f * (0.62 + 0.38 * np.clip(t / 0.012, 0, 1) ** 0.6)
    return fades(np.sin(glide(fr, sr)) * np.minimum(t / 0.002, 1) * np.exp(-t / (dur * 0.45)), sr, 0.0, 0.01)


def felt(sr, f, dur=0.9):
    """Felt-hammer music-box note (v33b, softer than pluck): sine + a whisper of 2nd/3rd harmonic, 9 ms attack, slow bloom,
    a touch of slow vibrato; no metallic tine partial."""
    t = tt(dur, sr)
    vib = 1 + 0.0025 * np.sin(2 * np.pi * 5.0 * t) * np.minimum(t / 0.25, 1)
    ph = glide(f * vib, sr)
    x = np.sin(ph) + 0.08 * np.sin(2 * ph + 0.3) * np.exp(-t / 0.15) + 0.025 * np.sin(3 * ph) * np.exp(-t / 0.08)
    env = (1 - np.exp(-t / 0.009)) * np.exp(-t / (dur * 0.3))
    return fades(x * env, sr, 0.0, 0.05)


def pop_soft(sr, seed, f):
    """In-app / clip pop (v33b): a felt note with a very quiet low 'bloop' glide underneath and a soft room tail."""
    rng = np.random.default_rng(seed)
    out = np.zeros(int(1.3 * sr))
    t = tt(0.09, sr)
    fr = f * 0.5 * (0.8 + 0.2 * np.clip(t / 0.03, 0, 1) ** 0.6)
    place(out, fades(np.sin(glide(fr, sr)) * (1 - np.exp(-t / 0.006)) * np.exp(-t / 0.03), sr, 0.0, 0.02), 0.0, sr, 0.18)
    place(out, felt(sr, f, 0.95), 0.003, sr, 0.75)
    place(out, felt(sr, f * 2.0, 0.4), 0.003 + float(rng.uniform(0.0, 0.01)), sr, 0.07)
    out = reverb(out, sr, 1.4, 0.22, seed=seed)
    return fades(band(out, 120, 5000, sr), sr, 0.0, 0.15)


def pop_big_soft(sr, seed=5):
    """The giant: a round low 'bloop' opening into a soft bell chord (C5 E5 G5 + C6) and a slow airy shimmer."""
    rng = np.random.default_rng(seed)
    out = np.zeros(int(2.2 * sr))
    t = tt(0.16, sr)
    fr = 330 * (0.7 + 0.3 * np.clip(t / 0.03, 0, 1) ** 0.5)
    place(out, fades(np.sin(glide(fr, sr)) * np.minimum(t / 0.004, 1) * np.exp(-t / 0.05), sr, 0.0, 0.02), 0.0, sr, 0.5)
    for k, f in enumerate((261.63, 392.0, 523.25, 659.26)):
        place(out, felt(sr, f, 2.0), 0.012 + 0.035 * k, sr, 0.34 - 0.04 * k)
    n = int(0.9 * sr)
    sh = band(rng.standard_normal(n), 2000, 4500, sr) * np.hanning(n) * 0.012
    place(out, sh, 0.02, sr)
    out = reverb(out, sr, 2.0, 0.25, seed=seed)
    return fades(band(out, 100, 5000, sr), sr, 0.0, 0.2)


# ───────────────────────── v33: in-app background music ─────────────────────────
def music_loop(sr, seed=33, bpm=72.0, bars=8):
    """Calm ambient loop in C major, no bass (nothing below ~250 Hz: the breath detector listens to the low band, and the loop
    plays from the same phone): airy pad chords Cmaj9 – Am9 – Fmaj9 – G6/9, two bars each, a sparse kalimba line from the
    pentatonic, a rare glockenspiel glint. Rendered three times over and the middle pass kept, so the reverb tail wraps and the
    loop is seamless."""
    rng = np.random.default_rng(seed)
    beat = 60.0 / bpm
    L = bars * 4 * beat
    n = int(round(L * sr))
    total = np.zeros(3 * n)
    chords = [[261.63, 329.63, 392.0, 493.88, 587.33], [261.63, 329.63, 392.0, 440.0, 493.88],
              [261.63, 349.23, 440.0, 523.25, 659.26], [293.66, 392.0, 440.0, 493.88, 659.26]]
    melody_rng = np.random.default_rng(seed + 1)
    pattern = []
    for bar in range(bars):
        for step in range(8):
            if melody_rng.random() < (0.42 if step % 2 == 0 else 0.18):
                pattern.append((bar * 4 * beat + step * beat / 2, float(melody_rng.choice(PENTA[:5])),
                                float(melody_rng.uniform(0.5, 1.0))))
    for rep in range(3):
        off = rep * n
        rng = np.random.default_rng(seed)        # same pad phases every pass: the kept middle pass is exactly periodic
        for ci in range(bars // 2):
            ch = chords[ci % 4]
            seg_n = int(2 * 4 * beat * sr)
            t = np.arange(int(seg_n * 1.25)) / sr
            env = np.minimum(t / 1.6, 1) * np.clip((seg_n * 1.25 / sr - t) / 1.4, 0, 1)
            pad = np.zeros(len(t))
            for f in ch:
                for det in (-0.004, 0.0, 0.0045):
                    ph = 2 * np.pi * f * (1 + det) * t + rng.uniform(0, 6)
                    pad += np.sin(ph) + 0.25 * np.sin(2 * ph) + 0.08 * np.sin(3 * ph)
            pad *= env * (1 + 0.12 * np.sin(2 * np.pi * 0.18 * t)) / (len(ch) * 3)
            place(total, pad, (off / sr) + ci * 2 * 4 * beat, sr, 0.22)
        for (t0, f, v) in pattern:
            place(total, pluck(sr, f, 1.1, 0.2), off / sr + t0, sr, 0.16 * v)
            if v > 0.93:
                place(total, pluck(sr, f * 2, 0.9, 0.0), off / sr + t0 + beat / 4, sr, 0.05)
    total = band(total, 240, 9000, sr)
    total = reverb(total, sr, 2.8, 0.38)
    return total[n:2 * n]


# ───────────────────────── in-app export ─────────────────────────
def save_wav(x, path, sr=44100, peak_db=-1.0):
    x = x / (np.max(np.abs(x)) or 1) * 10 ** (peak_db / 20)
    a = np.round(np.clip(x, -1, 1) * 32767).astype("<i2")
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(a.tobytes())
    return os.path.getsize(path)


def trim(x, sr, floor_db=-60):
    """Cut the silent tail (keeps files small), with a short fade."""
    thr = np.max(np.abs(x)) * 10 ** (floor_db / 20)
    idx = np.where(np.abs(x) > thr)[0]
    end = min(len(x), (idx[-1] if len(idx) else len(x)) + int(0.01 * sr))
    return fades(x[:end], sr, 0.0, 0.01)


def export_app_sfx():
    sr = 44100
    os.makedirs(APP_OUT, exist_ok=True)
    sounds = {
        # v33: soft musical pops on C major pentatonic (pop_small / pop_big stay for reference)
        # (22.05 kHz: nothing above 5 kHz, half the size with the reverb tail)
        **{f"pop_{k + 1}.wav": (pop_soft(22050, 100 + k, f), 22050) for k, f in enumerate(PENTA)},
        "pop_big.wav": (pop_big_soft(22050, 5), 22050),
        "bloop.wav": bloop(sr, 3),
        "puff.wav": puff(sr, 11),
        "stick.wav": stick(sr, 21),
    }
    for name, x in sounds.items():
        x, r = x if isinstance(x, tuple) else (x, sr)
        x = trim(x, r)
        size = save_wav(x, os.path.join(APP_OUT, name), r)
        print(f"SFX {name:12s} {len(x) / r:5.2f}s {size / 1024:5.1f} KB")
        assert size < (200 if name == "pop_big.wav" else 70) * 1024, name
    # background music: a seamless loop. WAV, not AAC: AAC's encoder priming adds a gap at every loop; at 22.05 kHz (the loop
    # has nothing above 9 kHz) it is ~1.2 MB
    m = music_loop(22050)
    out = os.path.join(APP_OUT, "music.wav")
    save_wav(m, out, 22050, peak_db=-3.0)
    print(f"MUSIC music.wav {len(m) / 22050:5.2f}s {os.path.getsize(out) / 1024:5.1f} KB")


if __name__ == "__main__":
    export_app_sfx()
