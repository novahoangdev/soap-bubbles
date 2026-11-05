"""Paint the 3D daisies' head texture: app/assets/garden3d/tex/daisy_petals.png, a 2 × 2 atlas of four different
lawn-daisy heads seen from above (RGBA, transparent around the petals), mapped onto the cupped head disc of the Blender
props (blender/scripts/garden3d_props.py: uv = centre + local xy / radius × 0.5, cell radius 1 = the disc's rim).

Why painted and not modelled: the modelled petals (a lathe with a petal-shaped radius) were flat-ended plastic strips
with a flat orange button in the middle. A real daisy head is ~20 strap-shaped petals in two loose layers, uneven,
slightly notched at the tip, with a fine crease and a creamy-green base (~30 narrow petals:
wider, fewer ones read as tongue depressors), around a domed disc of tiny yellow florets
(greener and still closed in the middle). That detail is cheap as a texture and the disc keeps its 3D cup.

Run with any Python that has numpy (Blender's works):
  /Applications/Blender.app/Contents/Resources/5.2/python/bin/python3.13 tools/paint_daisy.py
"""
import math
import os
import struct
import sys
import zlib

import numpy as np

CELL = 1024      # output cell size (px); the atlas is 2 × 2 cells
SS = 2           # supersampling
OUT = os.path.join(os.path.dirname(__file__), "..", "app", "assets", "garden3d", "tex", "daisy_petals.png")


def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def over(dst_rgb, dst_a, src_rgb, src_a):
    """Porter-Duff source-over, straight alpha."""
    a = src_a + dst_a * (1.0 - src_a)
    w = np.where(a > 1e-6, src_a / np.maximum(a, 1e-6), 0.0)[..., None]
    rgb = src_rgb * w + dst_rgb * (1.0 - w)
    return rgb, a


def blur(img, r):
    """Separable box blur ×3 (≈ gaussian), edges clamped."""
    out = img.copy()
    for _ in range(3):
        for ax in (0, 1):
            pad = [(0, 0)] * out.ndim
            pad[ax] = (r, r)
            p = np.pad(out, pad, mode="edge")
            c = np.cumsum(p, axis=ax, dtype=np.float64)
            c = np.concatenate([np.zeros_like(np.take(c, [0], axis=ax)), c], axis=ax)
            n = out.shape[ax]
            out = (np.take(c, np.arange(2 * r + 1, 2 * r + 1 + n), axis=ax) - np.take(c, np.arange(0, n), axis=ax)) / (2 * r + 1)
    return out.astype(np.float32)


def paint_head(seed):
    rng = np.random.default_rng(seed)
    n = CELL * SS
    # coordinates: x right, y up, radius 1 = cell edge
    ys, xs = np.mgrid[0:n, 0:n].astype(np.float32)
    x = (xs + 0.5) / n * 2.0 - 1.0
    y = 1.0 - (ys + 0.5) / n * 2.0
    r = np.sqrt(x * x + y * y)
    th = np.arctan2(y, x)

    rgb = np.zeros((n, n, 3), np.float32)
    a = np.zeros((n, n), np.float32)
    shadow = np.zeros((n, n), np.float32)  # front petals' soft shadow on the back layer

    rc = 0.2 + rng.uniform(-0.012, 0.012)  # the yellow disc
    count = int(rng.integers(28, 35))
    base_ang = rng.uniform(0, math.tau)
    petals = []
    for k in range(count):
        ang = base_ang + math.tau * k / count + rng.normal(0, 0.05)
        layer = k % 2  # alternate petals sit in the back layer, a little lower and greyer
        L = rng.uniform(0.82, 0.98) if layer else rng.uniform(0.76, 0.94)
        if rng.random() < 0.12:
            L *= rng.uniform(0.72, 0.85)  # a short, still-growing or nibbled petal
        W = (math.tau * 0.5 / count) * rng.uniform(1.15, 1.45)  # half-width at the widest, as an angle at r = 0.5
        bend = rng.normal(0, 0.09)
        petals.append((layer, ang, L, W, bend, rng.uniform(0.96, 1.03), rng.random()))

    def petal_field(ang, L, W, bend):
        """(mask 0..1, across −1..1, along 0..1) of one petal."""
        # angular offset from the petal axis, the axis curving a little toward the tip
        u = np.clip((r - rc * 0.55) / (L - rc * 0.55), 0.0, 1.2)
        d = np.angle(np.exp(1j * (th - ang - bend * u * u)))
        t = d * np.maximum(r, 1e-3)  # arc distance from the axis
        hw = W * 0.5  # half-width (in radius units at r = 0.5)
        # strap shape: narrow stalk at the base, nearly parallel sides, a round tip with two shallow notches
        prof = hw * (0.38 + 0.62 * smoothstep(0.0, 0.32, u)) * (1.0 + 0.08 * np.sin(u * 3.1))
        tip = np.sqrt(np.clip(1.0 - ((u - 0.86) / 0.14) ** 2, 0.0, 1.0))
        prof = np.where(u > 0.86, prof * tip, prof)
        across = t / np.maximum(prof, 1e-5)
        # a slightly ragged, toothed tip (real petals end in two or three tiny teeth, not a clean round)
        notch = 0.012 * np.exp(-((np.abs(across) - 0.35) / 0.12) ** 2) * smoothstep(0.92, 1.0, u)
        px = 2.0 / n
        edge = np.minimum((prof - np.abs(t)) / px, (L - notch * L - r) / px)
        m = np.clip(edge * 0.5 + 0.5, 0.0, 1.0) * (r > rc * 0.6)
        return m, np.clip(across, -1.0, 1.0), np.clip(u, 0.0, 1.0)

    white = np.array([0.975, 0.965, 0.935], np.float32)
    cream = np.array([0.86, 0.84, 0.66], np.float32)
    for layer in (1, 0):
        for (ly, ang, L, W, bend, bright, pink) in petals:
            if ly != layer:
                continue
            m, ac, u = petal_field(ang, L, W, bend)
            if not m.any():
                continue
            # creamy-green at the base, white along the blade, a touch warmer at the very tip
            c = cream[None, None, :] * (1 - smoothstep(0.05, 0.38, u))[..., None] + white[None, None, :] * smoothstep(0.05, 0.38, u)[..., None]
            # form: the blade is a shallow trough, lit from the upper left; a fine crease down the middle,
            # two faint veins, edges a little darker where the petal curls
            light = math.cos(ang - 2.3) * 0.5 + 0.5
            sh = 1.0 - 0.07 * np.abs(ac) ** 2.5 + 0.035 * (ac * (light - 0.5) * 2.0)
            sh -= 0.05 * np.exp(-(ac / 0.09) ** 2) * smoothstep(0.1, 0.4, u)
            sh -= 0.018 * np.exp(-((np.abs(ac) - 0.5) / 0.08) ** 2) * smoothstep(0.2, 0.5, u)
            sh *= bright
            if layer:
                sh *= 0.9  # the back layer sits lower, in the front petals' shade
            # pinkish undersides peeking at the tip on a few heads (lawn daisies often have rosy tips)
            tipk = smoothstep(0.82, 1.0, u) * (0.35 if pink < 0.25 else 0.0)
            col = c * sh[..., None]
            col = col * (1 - tipk[..., None]) + np.array([0.95, 0.78, 0.8], np.float32) * sh[..., None] * tipk[..., None]
            rgb, a = over(rgb, a, col, m)
            if layer == 0:
                shadow = np.maximum(shadow, m)
    # soft shadow of the front layer onto the back layer (offset down-right, away from the light)
    sb = blur(np.roll(np.roll(shadow, int(0.012 * n), axis=0), int(0.008 * n), axis=1), max(2, int(0.008 * n)))
    back_only = np.clip(sb - shadow, 0.0, 1.0)
    rgb *= (1.0 - 0.18 * back_only)[..., None]
    # shade on the petals right around the disc (the domed centre stands up out of them)
    ring = np.exp(-((r - rc * 1.05) / (rc * 0.35)) ** 2) * (r > rc)
    rgb *= (1.0 - 0.2 * ring)[..., None]

    # the disc: a dome of tiny florets on a golden-angle spiral, open (deep yellow) at the rim and closed (green-gold) inside
    cm = np.clip((rc - r) / (2.0 / n) * 0.5 + 0.5, 0.0, 1.0)
    rr = r / rc
    dome = np.sqrt(np.clip(1.0 - rr * rr, 0.0, 1.0))
    florets = np.zeros((n, n), np.float32)
    nf = 420
    gold = math.pi * (3.0 - math.sqrt(5.0))
    fr = rc * 0.5 / math.sqrt(nf) * 1.9
    cx = cy = n / 2.0
    for i in range(nf):
        q = rc * math.sqrt((i + 0.5) / nf) * 0.98
        ph = i * gold
        fx, fy = q * math.cos(ph), q * math.sin(ph)
        px0, py0 = int(cx + fx / 2 * n), int(cy - fy / 2 * n)
        rad = int(fr / 2 * n * 1.6) + 2
        x0, x1 = max(0, px0 - rad), min(n, px0 + rad)
        y0, y1 = max(0, py0 - rad), min(n, py0 + rad)
        dd = np.sqrt((x[y0:y1, x0:x1] - fx) ** 2 + (y[y0:y1, x0:x1] - fy) ** 2) / fr
        bump = np.clip(1.0 - dd * dd, 0.0, 1.0)
        florets[y0:y1, x0:x1] = np.maximum(florets[y0:y1, x0:x1], bump)
    inner = smoothstep(0.42, 0.04, rr) * 0.8
    deep = np.array([1.0, 0.78, 0.16], np.float32)
    green = np.array([0.84, 0.78, 0.26], np.float32)
    dc = deep[None, None, :] * (1 - inner)[..., None] + green[None, None, :] * inner[..., None]
    # dome lighting from the upper left, the florets' little bumps catching it, crevices between them dark
    lit = 0.78 + 0.3 * (x * -0.6 + y * 0.8) / rc * 0.5 * (1.0 - rr * 0.3) + 0.12 * dome
    fl = 0.8 + 0.28 * florets ** 0.7
    pollen = (florets > 0.75) * (1 - inner) * 0.06
    dcol = dc * (lit * fl)[..., None] + pollen[..., None]
    dcol *= (1.0 - 0.28 * smoothstep(0.8, 1.0, rr))[..., None]  # the rim of the dome turns away from the light
    rgb, a = over(rgb, a, np.clip(dcol, 0, 1), cm)

    # downsample, then bleed colour into the transparent margin (mip-maps would pull in black fringes otherwise)
    rgb = rgb.reshape(CELL, SS, CELL, SS, 3).mean(axis=(1, 3))
    a = a.reshape(CELL, SS, CELL, SS).mean(axis=(1, 3))
    prem = rgb * a[..., None]
    fill_rgb = rgb.copy()
    done = a > 0.5
    for rad in (2, 6, 16, 40, 100):
        ba = blur(a, rad)
        est = blur(prem, rad) / np.maximum(ba, 1e-6)[..., None]
        take = (~done) & (ba > 1e-3)
        fill_rgb[take] = est[take]
        done |= take
    out_rgb = np.where(a[..., None] > 0.5, rgb, fill_rgb)
    return np.clip(out_rgb, 0, 1), np.clip(a, 0, 1)


def write_png(path, rgba):
    h, w, _ = rgba.shape
    raw = b"".join(b"\x00" + rgba[i].tobytes() for i in range(h))
    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0)) \
        + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")
    with open(path, "wb") as fh:
        fh.write(png)


def main():
    atlas = np.zeros((CELL * 2, CELL * 2, 4), np.float32)
    for i, seed in enumerate((11, 23, 37, 58)):
        rgb, a = paint_head(seed)
        cy, cx = divmod(i, 2)
        atlas[cy * CELL:(cy + 1) * CELL, cx * CELL:(cx + 1) * CELL, :3] = rgb
        atlas[cy * CELL:(cy + 1) * CELL, cx * CELL:(cx + 1) * CELL, 3] = a
        print(f"[daisy] head {i} (seed {seed}) painted", flush=True)
    # sRGB-ish already (painted values are display values)
    out = (np.clip(atlas, 0, 1) * 255 + 0.5).astype(np.uint8)
    path = sys.argv[1] if len(sys.argv) > 1 else OUT
    write_png(path, out)
    print("[daisy] wrote", os.path.abspath(path))


if __name__ == "__main__":
    main()
