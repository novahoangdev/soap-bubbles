# Renders the passes the app draws (Cycles) -> app/assets/scene/:
#   bg.jpg          1320x2868 garden + wand, no soap film in the ring (the hole shows the bokeh behind)
#   wand_front.png  the wand only (ring + neck + handle) with straight alpha, cropped to its bounding box (position in layout.json)
#   env.jpg         2048x1024 equirectangular panorama from the bubble position, no DOF (reflections on the bubbles)
#   layout.json     440x956 pt design frame: ring centre / radii, wand_front crop, sun screen position, env orientation, sun direction
# All images are display-referred sRGB (AgX view transform baked in).
# Quick look: render/preview/passes.jpg (bg | wand_front over grey | env).
# The look comes from the .blend (scene["sb"]["look"], set by build_scene.py with SB_LOOK): golden (default) writes to
# app/assets/scene/, night to app/assets/scene/night/ with its own grade, render/preview/passes_night.jpg and a "note" in
# layout.json ("sun" = the key lantern, the brightest light cluster in the frame).
#
# Run: Blender -b blender/garden.blend -P blender/scripts/render_passes.py -- [--pct 100] [--samples 192] [--env-samples 96]
#      [--only bg,wand,env] [--out DIR]
import bpy, json, os, sys, time
import numpy as np
import OpenImageIO as oiio
from mathutils import Vector
from bpy_extras.object_utils import world_to_camera_view

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
arg = lambda k, d: argv[argv.index(k) + 1] if k in argv else d
ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
LOOK = bpy.context.scene["sb"].to_dict().get("look", "golden")
NIGHT = LOOK == "night"
SUF = "" if LOOK == "golden" else "_" + LOOK                  # temp / preview file suffix
OUT = os.path.abspath(arg("--out", os.path.join(ROOT, "app", "assets", "scene", *([] if LOOK == "golden" else [LOOK]))))
TMP = os.path.join(ROOT, "render", "passes")
PREV = os.path.join(ROOT, "render", "preview")
PCT = int(arg("--pct", "100"))
SAMPLES = int(arg("--samples", "192"))
ENV_SAMPLES = int(arg("--env-samples", str(max(16, SAMPLES // 2))))
ONLY = set(arg("--only", "bg,wand,env").split(","))
for d in (OUT, TMP, PREV):
    os.makedirs(d, exist_ok=True)

sc = bpy.context.scene
r = sc.render
SB = sc["sb"].to_dict()
VW, VH = SB["view"]
cam = sc.camera
envcam = bpy.data.objects["env_cam"]
wand = bpy.data.collections["wand"]
WAND_OBJS = set(wand.all_objects)
LOG = {}

try:
    prefs = bpy.context.preferences.addons["cycles"].preferences
    prefs.compute_device_type = "METAL"
    prefs.get_devices()
    for d in prefs.devices:
        d.use = d.type == "METAL"
    sc.cycles.device = "GPU"
except Exception as e:  # noqa: BLE001
    print("GPU setup failed:", e)


def render(path, fmt, samples, quality=90, rgba=False, depth="8"):
    s = r.image_settings
    s.file_format = fmt
    s.color_mode = "RGBA" if rgba else "RGB"
    s.color_depth = depth
    if fmt == "JPEG":
        s.quality = quality
    else:
        s.compression = 90
    sc.cycles.samples = samples
    r.filepath = path
    t0 = time.time()
    bpy.ops.render.render(write_still=True)
    dt = time.time() - t0
    print(f"── render {os.path.basename(path)} {r.resolution_x * r.resolution_percentage // 100}x"
          f"{r.resolution_y * r.resolution_percentage // 100} {samples} spp {dt:.1f}s")
    LOG[os.path.basename(path)] = round(dt, 1)


def read(path):
    inp = oiio.ImageInput.open(path)
    px = np.asarray(inp.read_image(0, 0, 0, inp.spec().nchannels, "float"), np.float32)
    inp.close()
    return px


def write(arr, path, quality=90):
    h, w, c = arr.shape
    spec = oiio.ImageSpec(w, h, c, "uint8")
    if path.endswith(".jpg"):
        spec.attribute("Compression", f"jpeg:{quality}")
    else:
        spec.attribute("png:compressionLevel", 9)
    o = oiio.ImageOutput.create(path)
    o.open(path, spec)
    o.write_image(np.ascontiguousarray(np.clip(arr * 255 + 0.5, 0, 255).astype(np.uint8)))
    o.close()
    print("SAVE", os.path.relpath(path, ROOT), w, h, f"{os.path.getsize(path) / 1024:.0f} KB")


r.resolution_percentage = PCT
W = r.resolution_x * PCT // 100
H = r.resolution_y * PCT // 100
r.use_border = False
r.film_transparent = False


def pt(p):
    """World point -> design frame pt (origin top-left, y down)."""
    v = world_to_camera_view(sc, cam, Vector(p))
    return [round(v.x * VW, 2), round((1 - v.y) * VH, 2)]


sun_w = Vector(SB["sun_dir"])
sun_pt = pt(cam.matrix_world.translation + sun_w * 1000.0)
if "key_pos" in SB:                                         # night: the key lantern stands in for the sun (a near light:
    key = Vector(SB["key_pos"])                             # its direction is taken from the bubble position, not the lens)
    sun_pt = pt(key)
    sun_w = (key - Vector(SB["bubble_pos"])).normalized()


def gblur(a, sigma):
    """Gaussian blur of an HxWxC image (box-downsample, separable gaussian, bilinear upsample): fine for soft glows."""
    k = max(1, int(sigma / 3))
    h, w = a.shape[:2]
    h2, w2 = h // k, w // k
    small = a[:h2 * k, :w2 * k].reshape(h2, k, w2, k, -1).mean(axis=(1, 3))
    sg = sigma / k
    rr = int(3 * sg) + 1
    g = np.exp(-np.arange(-rr, rr + 1) ** 2 / (2 * sg * sg))
    g /= g.sum()
    p = np.pad(small, ((rr, rr), (0, 0), (0, 0)), mode="edge")
    small = sum(g[i] * p[i:i + h2] for i in range(2 * rr + 1))
    p = np.pad(small, ((0, 0), (rr, rr), (0, 0)), mode="edge")
    small = sum(g[i] * p[:, i:i + w2] for i in range(2 * rr + 1))
    buf = oiio.ImageBuf(oiio.ImageSpec(w2, h2, small.shape[2], "float"))
    buf.set_pixels(oiio.ROI(), np.ascontiguousarray(small, np.float32))
    up = oiio.ImageBufAlgo.resize(buf, roi=oiio.ROI(0, w, 0, h, 0, 1, 0, small.shape[2]))
    return np.asarray(up.get_pixels(oiio.FLOAT)).reshape(h, w, -1)


def glow_layer(img):
    """Noise-free golden veil (replaces a volumetric haze): warm bloom of the highlights + veiling flare around the sun.
    Display-space, combined with a screen blend."""
    lum = img[..., :3] @ np.array([0.2126, 0.7152, 0.0722], np.float32)
    hi = (np.clip((lum - 0.5) / 0.5, 0, 1) ** 2)[..., None] * img[..., :3]
    bloom = 0.5 * gblur(hi, 0.035 * W) + 0.45 * gblur(hi, 0.11 * W)
    bloom *= np.array([1.0, 0.8, 0.52], np.float32)
    sx, sy = sun_pt[0] * W / VW, sun_pt[1] * H / VH
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    d = np.hypot(xx - sx, (yy - sy) * 0.9) / W
    veil = (0.40 * np.exp(-(d / 0.24) ** 2) + 0.16 * np.exp(-(d / 0.7) ** 2))[..., None] * np.array([1.0, 0.70, 0.36], np.float32)
    return np.clip(bloom + veil, 0, 1).astype(np.float32)


def screen(a, b):
    return 1 - (1 - a) * (1 - b)


def mul_layer():
    """Photographic falloff: the lower third sinks into shade (so the wand and bubbles pop), soft corners."""
    yy = np.linspace(0, 1, H, dtype=np.float32)[:, None]
    xx = np.linspace(0, 1, W, dtype=np.float32)[None, :]
    bottom = 1 - 0.30 * np.clip((yy - 0.6) / 0.4, 0, 1) ** 1.4
    corner = 1 - 0.22 * np.clip((np.hypot((xx - 0.5) * 1.5, (yy - 0.5) * 0.9) - 0.42) / 0.5, 0, 1) ** 2
    return (bottom * corner)[..., None]


def post(img, glow, mul):
    """bg grade: falloff, warm deep-green shadows, then the golden veil (screen)."""
    out = img * mul
    lum = (out @ np.array([0.2126, 0.7152, 0.0722], np.float32))[..., None]
    out = np.clip(out * (1 + np.array([0.10, 0.03, -0.14], np.float32) * (1 - lum) ** 2), 0, 1)
    return screen(out, glow)


def glow_layer_night(img):
    """Night: a soft halo around the bokeh discs and lanterns (lens bloom + a little halation), no sun veil."""
    lum = img[..., :3] @ np.array([0.2126, 0.7152, 0.0722], np.float32)
    hi = (np.clip((lum - 0.35) / 0.65, 0, 1) ** 1.6)[..., None] * img[..., :3]
    bloom = 0.42 * gblur(hi, 0.02 * W) + 0.30 * gblur(hi, 0.07 * W) + BLOOM_WIDE * gblur(hi, 0.2 * W)
    bloom *= np.array([1.0, 0.86, 0.72], np.float32)
    # "soap-bubble" bokeh of an old fast lens (spherical aberration): each disc gets a slightly brighter rim. A small
    # band-pass of the disc layer, kept positive, only where the discs are (their edges are the only steps in it)
    # (night v2: the aperture filter in night_look.py already gives the discs real rims, so this is only a touch: SB_POST_RIM)
    disc = (np.clip((lum - 0.18) / 0.5, 0, 1) ** 1.2)[..., None] * img[..., :3]
    rim = np.clip(gblur(disc, 0.004 * W) - gblur(disc, 0.014 * W), 0, None) * POST_RIM
    return np.clip(bloom + rim, 0, 1).astype(np.float32)


POST_RIM = float(os.environ.get("SB_POST_RIM", "0.9" if SB.get("lens", 0) == 0 else "0.3"))
GRAIN = float(os.environ.get("SB_GRAIN", "0.0" if SB.get("lens", 0) == 0 else "0.010"))
# (v3) the widest bloom term spread a uniform grey veil over the dark lower half; dark areas should keep their texture
BLOOM_WIDE = float(os.environ.get("SB_BLOOM_WIDE", "0.16" if SB.get("lens", 0) == 0 else "0.04"))
ENV_WIRES = os.environ.get("SB_ENV_WIRES", "0") == "1"    # (v3) string wires read as dashes in the bubbles: hidden in the env


def mul_layer_night():
    """Night falloff: the lower third sinks into the dark lawn, heavier corners."""
    yy = np.linspace(0, 1, H, dtype=np.float32)[:, None]
    xx = np.linspace(0, 1, W, dtype=np.float32)[None, :]
    bottom = 1 - 0.38 * np.clip((yy - 0.58) / 0.42, 0, 1) ** 1.3
    corner = 1 - 0.30 * np.clip((np.hypot((xx - 0.5) * 1.5, (yy - 0.5) * 0.9) - 0.40) / 0.5, 0, 1) ** 2
    return (bottom * corner)[..., None]


def post_night(img, glow, mul):
    """Night grade: falloff, blue-violet shadows (the blacks lift a hair towards indigo), then the bokeh bloom (screen)."""
    out = img * mul
    lum = (out @ np.array([0.2126, 0.7152, 0.0722], np.float32))[..., None]
    # cool split-tone: the near-black foliage and lawn turn blue-green-violet instead of the warm brown the bulbs leave
    dark = np.clip(1 - lum / 0.22, 0, 1) ** 1.5
    cool = lum * np.array([0.72, 0.98, 1.45], np.float32)
    out = out + (cool - out) * 0.75 * dark
    out = out + np.array([0.008, 0.010, 0.024], np.float32) * (1 - lum) ** 4
    out = screen(np.clip(out, 0, 1), glow)
    if GRAIN > 0 and out.shape[:2] == (H, W):                 # (night v2) fine sensor grain, mostly luminance, strongest in the mid-darks
        g_rng = np.random.default_rng(7)
        n = g_rng.standard_normal((H, W, 1)).astype(np.float32) + 0.35 * g_rng.standard_normal((H, W, 3)).astype(np.float32)
        n = 0.6 * n + 0.4 * gblur(n, 1.2 * W / 1320) * 2.2       # a little clumping, like real grain
        l2 = (out @ np.array([0.2126, 0.7152, 0.0722], np.float32))[..., None]
        out = np.clip(out + n * GRAIN * (0.5 + 2.0 * l2 * (1 - l2)), 0, 1)
    return out


if NIGHT:
    glow_layer, mul_layer, post = glow_layer_night, mul_layer_night, post_night

if LOOK == "studio":
    # studio (studio_look.py): black velvet + one softbox behind the camera. The key is behind the lens, so 'sun' is the
    # softbox's mirrored highlight on a bubble at the bubble position (half vector between the softbox and the lens)
    _bub = Vector(SB["bubble_pos"])
    _h = ((Vector(SB["key_pos"]) - _bub).normalized() + (cam.matrix_world.translation - _bub).normalized()).normalized()
    sun_pt = pt(_bub + _h * 0.25)
    STUDIO_GRAIN = float(os.environ.get("SB_GRAIN", "0.012"))

    def glow_layer_studio(img):
        """Only a whisper of lens bloom around the wand's specular streaks."""
        lum = img[..., :3] @ np.array([0.2126, 0.7152, 0.0722], np.float32)
        hi = (np.clip((lum - 0.6) / 0.4, 0, 1) ** 2)[..., None] * img[..., :3]
        return np.clip(0.25 * gblur(hi, 0.012 * W) + 0.10 * gblur(hi, 0.05 * W), 0, 1).astype(np.float32)

    def mul_layer_studio():
        """Gentle vignette: the frame edges sink a little deeper into the velvet."""
        yy = np.linspace(0, 1, H, dtype=np.float32)[:, None]
        xx = np.linspace(0, 1, W, dtype=np.float32)[None, :]
        d = np.hypot((xx - 0.42) * 1.4, (yy - 0.38) * 0.75)
        return (1 - 0.55 * np.clip((d - 0.15) / 0.55, 0, 1) ** 1.5)[..., None]

    def post_studio(img, glow, mul):
        """Studio grade: vignette, a hair of lift so the blacks read as velvet not digital zero, bloom, fine grain."""
        out = img * mul
        out = out + np.array([0.010, 0.0095, 0.009], np.float32) * mul
        out = screen(np.clip(out, 0, 1), glow)
        if STUDIO_GRAIN > 0 and out.shape[:2] == (H, W):
            g_rng = np.random.default_rng(11)
            n = g_rng.standard_normal((H, W, 1)).astype(np.float32) + 0.3 * g_rng.standard_normal((H, W, 3)).astype(np.float32)
            n = 0.6 * n + 0.4 * gblur(n, 1.2 * W / 1320) * 2.2
            l2 = (out @ np.array([0.2126, 0.7152, 0.0722], np.float32))[..., None]
            out = np.clip(out + n * STUDIO_GRAIN * (0.45 + 2.0 * l2 * (1 - l2)), 0, 1)
        return out

    glow_layer, mul_layer, post = glow_layer_studio, mul_layer_studio, post_studio

if LOOK == "dawn":
    # dawn (dawn_look.py): misty pastel morning. A soft peach-pink veil around the hidden sun, a gentle bloom, the shadows
    # lifted towards lavender (mist, not black), a light vignette and a calmer lower third for the ring
    def glow_layer_dawn(img):
        lum = img[..., :3] @ np.array([0.2126, 0.7152, 0.0722], np.float32)
        hi = (np.clip((lum - 0.55) / 0.45, 0, 1) ** 2)[..., None] * img[..., :3]
        bloom = (0.35 * gblur(hi, 0.03 * W) + 0.25 * gblur(hi, 0.1 * W)) * np.array([1.0, 0.92, 0.9], np.float32)
        sx, sy = sun_pt[0] * W / VW, sun_pt[1] * H / VH
        yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
        d = np.hypot(xx - sx, (yy - sy) * 0.9) / W
        veil = (0.16 * np.exp(-(d / 0.3) ** 2) + 0.06 * np.exp(-(d / 0.8) ** 2))[..., None] * np.array([1.0, 0.84, 0.78], np.float32)
        return np.clip(bloom + veil, 0, 1).astype(np.float32)

    def mul_layer_dawn():
        yy = np.linspace(0, 1, H, dtype=np.float32)[:, None]
        xx = np.linspace(0, 1, W, dtype=np.float32)[None, :]
        bottom = 1 - 0.16 * np.clip((yy - 0.62) / 0.38, 0, 1) ** 1.3
        corner = 1 - 0.14 * np.clip((np.hypot((xx - 0.5) * 1.5, (yy - 0.5) * 0.9) - 0.45) / 0.5, 0, 1) ** 2
        return (bottom * corner)[..., None]

    def post_dawn(img, glow, mul):
        out = img * mul
        lum = (out @ np.array([0.2126, 0.7152, 0.0722], np.float32))[..., None]
        out = out + np.array([0.030, 0.022, 0.040], np.float32) * (1 - lum) ** 2  # lifted lavender shadows (mist)
        return screen(np.clip(out, 0, 1), glow)

    glow_layer, mul_layer, post = glow_layer_dawn, mul_layer_dawn, post_dawn

if LOOK == "golden2":
    # golden2 (golden2_look.py): backlit park at sunset. A peach-amber veil around the sun (much lighter than v1's),
    # a creamy bloom on the bokeh, rich (not muddy) shadows with a hint of teal, a deeper lower third, fine grain
    G2_GRAIN = float(os.environ.get("SB_GRAIN", "0.010"))

    def glow_layer_golden2(img):
        lum = img[..., :3] @ np.array([0.2126, 0.7152, 0.0722], np.float32)
        hi = (np.clip((lum - 0.6) / 0.4, 0, 1) ** 2)[..., None] * img[..., :3]
        bloom = (0.30 * gblur(hi, 0.025 * W) + 0.22 * gblur(hi, 0.09 * W)) * np.array([1.0, 0.86, 0.68], np.float32)
        sx, sy = sun_pt[0] * W / VW, sun_pt[1] * H / VH
        yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
        d = np.hypot(xx - sx, (yy - sy) * 0.9) / W
        veil = (0.22 * np.exp(-(d / 0.22) ** 2) + 0.08 * np.exp(-(d / 0.75) ** 2))[..., None] * np.array([1.0, 0.72, 0.46], np.float32)
        return np.clip(bloom + veil, 0, 1).astype(np.float32)

    def mul_layer_golden2():
        yy = np.linspace(0, 1, H, dtype=np.float32)[:, None]
        xx = np.linspace(0, 1, W, dtype=np.float32)[None, :]
        bottom = 1 - 0.32 * np.clip((yy - 0.55) / 0.45, 0, 1) ** 1.3
        corner = 1 - 0.25 * np.clip((np.hypot((xx - 0.5) * 1.5, (yy - 0.5) * 0.9) - 0.4) / 0.5, 0, 1) ** 2
        return (bottom * corner)[..., None]

    def post_golden2(img, glow, mul):
        out = img * mul
        lum = (out @ np.array([0.2126, 0.7152, 0.0722], np.float32))[..., None]
        # split tone: shadows a touch teal-blue, highlights a touch peach
        out = out * (1 + np.array([-0.06, 0.0, 0.08], np.float32) * (1 - lum) ** 3 + np.array([0.04, 0.0, -0.05], np.float32) * lum ** 2)
        out = np.clip(out, 0, 1)
        out = out + 0.35 * (out * out * (3 - 2 * out) - out)                    # gentle S-curve: deeper darks, no mud
        out = screen(out, glow)
        if G2_GRAIN > 0 and out.shape[:2] == (H, W):
            g_rng = np.random.default_rng(7)
            n = g_rng.standard_normal((H, W, 1)).astype(np.float32) + 0.3 * g_rng.standard_normal((H, W, 3)).astype(np.float32)
            n = 0.6 * n + 0.4 * gblur(n, 1.2 * W / 1320) * 2.2
            l2 = (out @ np.array([0.2126, 0.7152, 0.0722], np.float32))[..., None]
            out = np.clip(out + n * G2_GRAIN * (0.45 + 2.0 * l2 * (1 - l2)), 0, 1)
        return out

    glow_layer, mul_layer, post = glow_layer_golden2, mul_layer_golden2, post_golden2


old_layout = {}
if os.path.exists(os.path.join(OUT, "layout.json")):
    with open(os.path.join(OUT, "layout.json")) as f:
        old_layout = json.load(f)

# ── 1. bg.jpg: everything, then the golden glow in post ──
bg_path = os.path.join(OUT, "bg.jpg")
bg_raw = os.path.join(TMP, f"bg_raw{SUF}.png")
GLOW = None
if "bg" in ONLY:
    sc.camera = cam
    render(bg_raw, "PNG", SAMPLES, depth="16")
if os.path.exists(bg_raw) and ("bg" in ONLY or "wand" in ONLY):
    raw = read(bg_raw)[..., :3]
    if raw.shape[:2] == (H, W):
        GLOW = glow_layer(raw)
        MUL = mul_layer()
        if "bg" in ONLY:
            write(post(raw, GLOW, MUL), bg_path, quality=90)

# ── 2. wand_front.png: only the wand is visible to the camera; everything else still lights/shadows it ──
wand_box = None
if "wand" in ONLY:
    saved = {}
    for ob in sc.objects:
        if ob.type in ("MESH", "CURVE") and ob not in WAND_OBJS:
            saved[ob.name] = ob.visible_camera
            ob.visible_camera = False
    r.film_transparent = True
    # night (wet wand): the fairy bulbs are tiny, a physical radiance leaves their reflections sub-pixel and invisible;
    # boost what glossy rays straight off the wand see of them (night_look.py SB_WAND_GLINT), in this pass only
    glint = bpy.data.materials["fairy_bulb"].node_tree.nodes.get("wand_glint") if "fairy_bulb" in bpy.data.materials else None
    if glint and "wand_glint" in SB:
        glint.outputs[0].default_value = SB["wand_glint"]
    # render only the bottom part of the frame (the wand region) to save time
    r.use_border = True
    r.use_crop_to_border = False
    r.border_min_x, r.border_max_x = 0.25, 0.75
    r.border_min_y, r.border_max_y = 0.0, 0.36
    full = os.path.join(TMP, f"wand_full{SUF}.png")
    # supersampled (SB_WAND_SS x the frame, averaged down in premultiplied alpha), more samples and no denoiser by default:
    # at 1x the denoiser turned the boosted bulb glints on the wet coat into blocky patches
    WSS = max(1, int(os.environ.get("SB_WAND_SS", "2")))
    WSPP = int(os.environ.get("SB_WAND_SPP", str(max(64, SAMPLES // 2) if WSS == 1 else max(64, SAMPLES))))
    den = sc.cycles.use_denoising
    sc.cycles.use_denoising = os.environ.get("SB_WAND_DENOISE", "1") == "1"   # at 2x the denoiser's blotches fall below a pixel
    r.resolution_percentage = PCT * WSS
    render(full, "PNG", WSPP, rgba=True, depth="16")
    r.resolution_percentage = PCT
    sc.cycles.use_denoising = den
    r.use_border = False
    r.film_transparent = False
    if glint:
        glint.outputs[0].default_value = 1.0
    for n, v in saved.items():
        sc.objects[n].visible_camera = v
    px = read(full)
    if WSS > 1:                                              # box-average WSS x WSS blocks of premultiplied RGBA
        hh, ww = px.shape[0] // WSS, px.shape[1] // WSS
        pm = np.concatenate([px[..., :3] * px[..., 3:4], px[..., 3:4]], axis=2)[:hh * WSS, :ww * WSS]
        pm = pm.reshape(hh, WSS, ww, WSS, 4).mean(axis=(1, 3))
        al = pm[..., 3:4]
        px = np.concatenate([np.where(al > 1e-6, pm[..., :3] / np.maximum(al, 1e-6), 0.0), al], axis=2).astype(np.float32)
    a = px[..., 3]
    ys, xs = np.nonzero(a > 1 / 255)
    pad = 4
    x0, x1 = max(0, xs.min() - pad), min(W, xs.max() + 1 + pad)
    y0, y1 = max(0, ys.min() - pad), min(H, ys.max() + 1 + pad)
    ow = (old_layout.get("wand_front") or {}) if os.environ.get("SB_WAND_KEEP_RECT", "1") == "1" else {}
    if ow.get("px_frame") == [W, H]:                         # keep the app's sprite rect when it still holds the wand
        ox, oy, owd, oht = ow["px"]
        if ox <= x0 and oy <= y0 and ox + owd >= x1 and oy + oht >= y1:
            x0, y0, x1, y1 = ox, oy, ox + owd, oy + oht
    print("WAND rect", int(x0), int(y0), int(x1 - x0), int(y1 - y0))
    crop = px[y0:y1, x0:x1].copy()
    if GLOW is not None:                                     # same veil as bg.jpg so the wand matches pixel for pixel
        crop[..., :3] = post(crop[..., :3], GLOW[y0:y1, x0:x1], MUL[y0:y1, x0:x1])
    # Blender writes straight (un-premultiplied) alpha to PNG already; keep it straight
    write(crop, os.path.join(OUT, "wand_front.png"))
    k = VW / W
    wand_box = {"x": round(x0 * k, 2), "y": round(y0 * k, 2), "w": round((x1 - x0) * k, 2), "h": round((y1 - y0) * k, 2),
                "px": [int(x0), int(y0), int(x1 - x0), int(y1 - y0)], "px_frame": [W, H]}

# ── 3. env.jpg: equirectangular from the bubble position, wand hidden ──
env_path = os.path.join(OUT, "env.jpg")
ENV_HIDE = [ob for ob in sc.objects if "lens_only" in ob or ("string_wire" in ob and not ENV_WIRES)]  # night: lens parts, wires
if "env" in ONLY:
    for ob in list(WAND_OBJS) + ENV_HIDE:
        ob.hide_render = True
    sc.camera = envcam
    stars = sc.world.node_tree.nodes.get("stars_on")         # night: stars only in the env (the bubbles' sky)
    if stars:
        stars.outputs[0].default_value = 1.0
    bcam = bpy.data.materials["fairy_bulb"].node_tree.nodes.get("bulb_cam") if "fairy_bulb" in bpy.data.materials else None
    bcam_v = bcam.outputs[0].default_value if bcam else None  # night v2: camera-only bulb gain of the bg; the env keeps 1
    if bcam:
        bcam.outputs[0].default_value = 1.0
    rx, ry = r.resolution_x, r.resolution_y
    r.resolution_x, r.resolution_y = 2048, 1024
    render(env_path, "JPEG", ENV_SAMPLES, quality=86)
    r.resolution_x, r.resolution_y = rx, ry
    if stars:
        stars.outputs[0].default_value = 0.0
    if bcam:
        bcam.outputs[0].default_value = bcam_v
    sc.camera = cam
    for ob in list(WAND_OBJS) + ENV_HIDE:
        ob.hide_render = False


# ── layout.json (pt, 440x956 frame, origin top-left, y down) ──
rc = Vector(SB["ring_c"])
c_pt = pt(rc)
rin_pt = pt(rc + Vector((SB["ring_rin"], 0, 0)))[0] - c_pt[0]
rout_pt = pt(rc + Vector((SB["ring_rout"], 0, 0)))[0] - c_pt[0]
sun_cam = cam.matrix_world.to_3x3().inverted() @ sun_w      # Blender camera space: x right, y up, z towards the viewer
layout_path = os.path.join(OUT, "layout.json")
old = {}
if os.path.exists(layout_path):
    with open(layout_path) as f:
        old = json.load(f)
layout = {
    "w": VW, "h": VH,
    "ring": {"x": c_pt[0], "y": c_pt[1], "r_inner": round(rin_pt, 2), "r_outer": round(rout_pt, 2)},
    "wand_front": wand_box or old.get("wand_front"),
    "sun": {"x": sun_pt[0], "y": sun_pt[1]},
    "sun_dir": [round(v, 4) for v in sun_cam],
    "env": {
        "file": "env.jpg", "size": [2048 * PCT // 100, 1024 * PCT // 100], "projection": "equirectangular",
        "forward_u": 0.5, "right_u": 0.75, "left_u": 0.25, "back_u": 0.0,
        "up": "v=0 is up (zenith), v=0.5 horizon, v=1 nadir",
        "dir_to_uv": "camera space d (x right, y up, z towards viewer): u = 0.5 + atan2(d.x, -d.z) / (2*pi), v = 0.5 - asin(d.y) / pi",
        "origin": "bubble position, 1.2 m in front of the camera, 12 cm above the lens axis; same orientation as the main camera",
    },
    "focus": {"distance_m": SB["focus_d"], "fstop": SB["fstop"], "m_per_pt": round(SB["m_per_pt"], 7)},
    "color": "sRGB display-referred (Blender AgX view transform baked in)",
    "render_pct": PCT,
}
if NIGHT:
    layout["look"] = "night"
    layout["color"] = "sRGB display-referred (Blender AgX view transform baked in); blue-hour sky, no sun"
    layout["note"] = ("No sun at night. 'sun' is the screen position of the key lantern (warm amber globe, upper-left, 6.5 m from the lens, "
                      "the brightest single light in the frame) and 'sun_dir' points from the bubble position to it in camera space. "
                      "It is a small, warm, moderate source: use a weak, slightly broader highlight (about 0.3 of the golden sun). "
                      "The real sparkle comes from env.jpg: hundreds of fairy-light bulbs as sharp 1-3 px points all around.")
    layout["key_light"] = {"name": SB.get("key_name", "lantern_key"), "color_srgb": "#ffa850", "distance_m": round((Vector(SB["key_pos"]) - Vector(SB["bubble_pos"])).length, 2)}
if LOOK == "studio":
    sbx = SB.get("softbox", {})
    layout["look"] = "studio"
    layout["color"] = "sRGB display-referred (Blender AgX view transform baked in); black velvet studio, one softbox"
    layout["note"] = ("Studio: black velvet backdrop, no sun. The key is one large rectangular softbox (5000 K, warm-neutral) up-left "
                      "BEHIND the camera; 'sun_dir' points from the bubble position to its centre in camera space. 'sun' is not the "
                      "light itself (it is behind the lens) but where its mirrored highlight sits on a bubble at the bubble position "
                      "(upper-left). It is a big soft source: a broad, rounded-rectangle window highlight, not a point "
                      "(angular size in key_light.angular_rad, width x height). env.jpg is black except the softbox and a thin "
                      "strip light behind the camera on the right, so the thin-film colours carry the bubbles.")
    layout["key_light"] = {"name": "softbox", "color_srgb": "#fff1e4", "kelvin": 5000,
                           "distance_m": round((Vector(SB["key_pos"]) - Vector(SB["bubble_pos"])).length, 2),
                           "azimuth_deg": sbx.get("az_deg"), "elevation_deg": sbx.get("el_deg"),
                           "azimuth_convention": "0 = from the bubble towards the camera, negative = camera-left",
                           "size_m": sbx.get("size_m"), "angular_rad": sbx.get("angular_rad")}
if LOOK == "dawn":
    layout["look"] = "dawn"
    layout["color"] = "sRGB display-referred (Blender AgX view transform baked in); misty pastel spring morning"
    layout["note"] = ("Dawn: the low sun (8 deg up, 3 deg left of the lens axis) is hidden behind thin mist, so there is no hard disc: "
                      "'sun' is the centre of a soft creamy glow (peach-white) and 'sun_dir' points from the bubble towards it in camera "
                      "space. Use a soft, broad, warm-white highlight (about 0.5 of the golden sun, wider). The sky is pale peach-pink "
                      "at the horizon going to lavender overhead; env.jpg holds pastel sky, blossom trees and a dewy lawn with a few tiny glints.")
if LOOK == "golden2":
    layout["look"] = "golden2"
    layout["color"] = "sRGB display-referred (Blender AgX view transform baked in); backlit park at sunset"
    layout["note"] = ("Golden hour v2: the low sun (7 deg up, 2 deg left of the lens axis) glows through the trees, upper-left; "
                      "'sun_dir' points from the bubble towards it in camera space. In env.jpg the sun is only a small hot core "
                      "(~0.6 deg, a few clipped pixels) with a modest amber halo: use a small, tight, warm highlight. The sky "
                      "runs amber-peach at the horizon to cream and a soft dusty blue overhead; the tree ring fades into warm "
                      "haze towards the sun and blue-lilac haze behind the camera; the lawn is in shade.")
with open(layout_path, "w") as f:
    json.dump(layout, f, indent=1)
print("LAYOUT", json.dumps(layout))

# ── contact sheet: bg | wand_front over grey | env (all scaled to the bg preview height) ──
try:
    th = 900
    tiles = []
    if os.path.exists(bg_path):
        b = read(bg_path)[..., :3]
        s = max(1, round(b.shape[0] / th))
        tiles.append(b[::s, ::s])
    wf = os.path.join(OUT, "wand_front.png")
    if os.path.exists(wf) and tiles:
        w4 = read(wf)
        canvas = np.full_like(b, 0.32)
        bx = layout["wand_front"]["px"]
        sx = b.shape[1] / layout["wand_front"]["px_frame"][0]
        if abs(sx - 1) < 1e-3:
            x0, y0 = bx[0], bx[1]
            al = w4[..., 3:4]
            canvas[y0:y0 + w4.shape[0], x0:x0 + w4.shape[1]] = w4[..., :3] * al + canvas[y0:y0 + w4.shape[0], x0:x0 + w4.shape[1]] * (1 - al)
        tiles.append(canvas[::s, ::s])
    if os.path.exists(env_path) and tiles:
        e = read(env_path)[..., :3]
        hgt = tiles[0].shape[0]
        es = max(1, e.shape[1] // (hgt * 2))
        e = e[::es, ::es]
        pad = np.full((hgt, e.shape[1], 3), 0.1, np.float32)
        pad[:e.shape[0]] = e[:hgt]
        tiles.append(pad)
    if tiles:
        hgt = min(t.shape[0] for t in tiles)
        write(np.concatenate([t[:hgt] for t in tiles], axis=1), os.path.join(PREV, f"passes{SUF}.jpg"), quality=85)
except Exception as ex:  # noqa: BLE001
    print("sheet failed:", ex)
print("TIMES", json.dumps(LOG))
