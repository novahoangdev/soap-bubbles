# Codex images (blender/textures/raw/*.png) -> compact textures for Blender (blender/textures/):
#   leaves_maple.png, leaves_linden.png   magenta (#ff00ff) background keyed to alpha, magenta spill removed, 1024 px
#   flowers_cosmos.png                    blue (#0000ff) background keyed to alpha, blue spill removed, 1024 px
#   grass_tile.jpg, hedge_tile.jpg        1024 px tiling textures
#   hydrangea.png                         (night look) magenta key like the leaves, 1024 px
#   blossom_branch.png                    (dawn look) cherry blossom branch, blue key like the cosmos, 1024 px
#   house_night.jpg                       (night look) house facade at blue hour with lit windows, 1536 px
# Run: Blender -b --factory-startup -P blender/scripts/prep_textures.py
import os
import numpy as np
import OpenImageIO as oiio

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
RAW = os.path.join(ROOT, "blender", "textures", "raw")
OUT = os.path.join(ROOT, "blender", "textures")
SIZE = 1024


def load(name, long_side=SIZE):
    buf = oiio.ImageBuf(os.path.join(RAW, name))
    s = buf.spec()
    k = long_side / max(s.width, s.height)
    w, h = round(s.width * k), round(s.height * k)
    buf = oiio.ImageBufAlgo.resize(buf, roi=oiio.ROI(0, w, 0, h, 0, 1, 0, s.nchannels))
    return np.asarray(buf.get_pixels(oiio.FLOAT))[..., :3].copy()


def save(arr, name, quality=88):
    h, w, c = arr.shape
    spec = oiio.ImageSpec(w, h, c, "uint8")
    if name.endswith(".jpg"):
        spec.attribute("Compression", f"jpeg:{quality}")
    else:
        spec.attribute("png:compressionLevel", 9)
    out = oiio.ImageOutput.create(os.path.join(OUT, name))
    out.open(os.path.join(OUT, name), spec)
    out.write_image(np.ascontiguousarray(np.clip(arr * 255 + 0.5, 0, 255).astype(np.uint8)))
    out.close()
    print("TEX", name, w, h)


def erode(alpha, n=1):
    """Shrink the matte by n px (min filter) to kill the coloured fringe."""
    a = alpha
    for _ in range(n):
        p = np.pad(a, 1, mode="edge")
        a = np.minimum.reduce([p[1:-1, 1:-1], p[:-2, 1:-1], p[2:, 1:-1], p[1:-1, :-2], p[1:-1, 2:]])
    return a


def bleed(rgb, alpha, n=8):
    """Push opaque colours into transparent pixels so mip-mapping/filtering never pulls in the key colour."""
    rgb = rgb.copy()
    known = alpha > 0.5
    for _ in range(n):
        p = np.pad(rgb, ((1, 1), (1, 1), (0, 0)), mode="edge")
        pk = np.pad(known, 1, mode="constant")
        acc = np.zeros_like(rgb)
        cnt = np.zeros(alpha.shape, np.float32)
        for dy, dx in ((0, 1), (2, 1), (1, 0), (1, 2)):
            kk = pk[dy:dy + alpha.shape[0], dx:dx + alpha.shape[1]]
            acc += p[dy:dy + alpha.shape[0], dx:dx + alpha.shape[1]] * kk[..., None]
            cnt += kk
        fill = (~known) & (cnt > 0)
        rgb[fill] = acc[fill] / cnt[fill][:, None]
        known = known | fill
    return rgb


# magenta key: leaves are green/yellow, so min(r, b) - g is a clean key signal
for name in ("leaves_maple", "leaves_linden", "hydrangea"):
    a = load(name + ".png")
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    key = np.minimum(r, b) - g
    alpha = 1.0 - np.clip((key - 0.10) / 0.30, 0, 1)
    alpha = erode(alpha, 1)
    # despill: a pixel may not be more magenta than green allows
    lim = g + 0.04
    a[..., 0] = np.minimum(r, np.maximum(lim, g * 1.15))
    a[..., 2] = np.minimum(b, lim)
    save(np.dstack([bleed(a, alpha), alpha]), name + ".png")

# blue key: pink/white/peach flowers, green stems
for name in ("flowers_cosmos", "blossom_branch"):
    if not os.path.exists(os.path.join(RAW, name + ".png")):
        continue
    a = load(name + ".png")
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    key = b - np.maximum(r, g)
    alpha = 1.0 - np.clip((key - 0.12) / 0.35, 0, 1)
    alpha = erode(alpha, 1)
    a[..., 2] = np.minimum(b, np.maximum(r, g) + 0.03)
    save(np.dstack([bleed(a, alpha), alpha]), name + ".png")

for name in ("grass", "hedge"):
    save(load(name + ".png"), name + "_tile.jpg")
save(load("house_night.png", 1536), "house_night.jpg")
