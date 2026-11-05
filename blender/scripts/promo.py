# Soap Bubbles demo clip for X (4:3 1920×1440, 60 fps): a titanium iPhone 17 Pro Max mockup playing the app recording.
# Ported from ../neon-sign/blender/scripts/promo.py (v12 rules): the PHONE STAYS STILL in the centre for the whole demo
# (no pan / zoom / shake / tilt), then ONE straight cut to the end card (big phone on the right, text on the left).
# Frame 1 = the app's first frame (never black). No status bar overlay.
#
# Background: soft golden-hour gradient (peach / amber / sage) that shifts gently per beat-sheet section, a warm sun glow
# drifting in the upper left, soft out-of-focus bokeh discs and a few blurry iridescent soap bubbles floating up behind
# the phone (all intrinsically soft sprites, no DOF needed). Soft contact shadow behind the phone.
# End card: "Soap Bubbles" title (letters pop in one by one like bubbles, iridescent sheen drifting, gentle bob), tagline,
# stack line, author, studio.
#
# All timings live in the beat sheet JSON (blender/scripts/beats/v1.json…).
#
# Run: Blender -b --factory-startup -P blender/scripts/promo.py -- --beats blender/scripts/beats/v1.json \
#         --screen render/promo/v1/screen.mp4 --film-start 0.85 --out render/promo/frames [--pct 100] [--stills 0,8,16]
#   --film-start: second in screen.mp4 showing app t = 0 (promo.sh detects it from the first garden frame)
import bpy, bmesh, json, math, os, random, sys
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
arg = lambda k, d: argv[argv.index(k) + 1] if k in argv else d
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
BEATS_PATH = os.path.abspath(arg("--beats", os.path.join(HERE, "beats", "v1.json")))
BEATS = json.load(open(BEATS_PATH))
SCREEN = os.path.abspath(arg("--screen", "render/promo/v1/screen.mp4"))
FILM0 = float(arg("--film-start", "0"))        # second in the recording at app t = 0
OUT = os.path.abspath(arg("--out", "render/promo/frames"))
PCT = int(arg("--pct", "100"))
LABEL = arg("--label", "")                     # small bottom-left label (e.g. "v2") to compare versions
FPS = 60
APP0 = float(BEATS["app_start"])               # app second on the first clip frame
APP_END = float(BEATS["app_end"])              # app second of the cut to the end card
CARD = float(BEATS.get("card", 3.0))           # end card length
DUR = APP_END - APP0 + CARD
FR = lambda sec: round(sec * FPS)              # clip second → frame
A = lambda t: FR(t - APP0)                     # app second → clip frame
rad = math.radians
rng = random.Random(BEATS.get("seed", 31))
C_CARD = APP_END - APP0                        # clip second of the cut
F_CARD = FR(C_CARD)
NF = FR(DUR)


def TT(v):
    """Beat sheet timing → clip frame: number = app second; "start"; "card" / "card+0.9"; "end"."""
    if isinstance(v, (int, float)):
        return A(v)
    if v == "start":
        return 0
    if v == "end":
        return NF
    if v.startswith("card"):
        return F_CARD + FR(float(v[4:] or 0))
    raise ValueError(f"unknown timing: {v}")


bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
sc.render.engine = "BLENDER_EEVEE"
sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = 1920, 1440, PCT
sc.render.fps = FPS
sc.frame_start, sc.frame_end = 0, NF - 1
sc.view_settings.view_transform = "Standard"
sc.eevee.taa_render_samples = 16
sc.eevee.use_fast_gi = False
sc.render.film_transparent = False
sc.render.use_motion_blur = False              # the phone is still; the sprites drift slowly


def hexc(h):
    h = h.lstrip("#")
    lin = lambda c: c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    return tuple(lin(int(h[i:i + 2], 16) / 255) for i in (0, 2, 4)) + (1.0,)


def link(ob):
    sc.collection.objects.link(ob)
    return ob


def fcurves(idb):
    # Blender 5.x: layered/slotted Actions → go through the slot's channelbag
    ad = idb.animation_data
    if ad is None or ad.action is None:
        return []
    if hasattr(ad.action, "fcurves"):
        return ad.action.fcurves
    from bpy_extras.anim_utils import action_get_channelbag_for_slot
    cb = action_get_channelbag_for_slot(ad.action, ad.action_slot)
    return cb.fcurves if cb else []


def key(idb, path, f, value):
    setattr(idb, path, value)
    idb.keyframe_insert(path, frame=f)


def key_sock(sock, f, value):
    sock.default_value = value
    sock.keyframe_insert("default_value", frame=f)


def sock_in(node, name, typ):
    return [s for s in node.inputs if s.name == name and s.type == typ][0]


def sock_out(node, typ):
    return [s for s in node.outputs if s.type == typ][0]


def interp(idb, kind):
    for fc in fcurves(idb):
        for k in fc.keyframe_points:
            k.interpolation = kind


def math_node(N, op, a=None, b=None, L=None, clamp=False):
    m = N.new("ShaderNodeMath"); m.operation = op; m.use_clamp = clamp
    for i, v in enumerate((a, b)):
        if v is None:
            continue
        if isinstance(v, (int, float)):
            m.inputs[i].default_value = v
        else:
            L.new(v, m.inputs[i])
    return m


def mat_emit(name, color, strength=1.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    n = m.node_tree.nodes
    n.clear()
    e = n.new("ShaderNodeEmission"); e.inputs["Color"].default_value = hexc(color); e.inputs["Strength"].default_value = strength
    o = n.new("ShaderNodeOutputMaterial")
    m.node_tree.links.new(e.outputs[0], o.inputs[0])
    return m, e


def blended(m):
    if hasattr(m, "surface_render_method"):
        m.surface_render_method = "BLENDED"
    if hasattr(m, "use_transparency_overlap"):
        m.use_transparency_overlap = True


def quad(name, uv=True):
    me = bpy.data.meshes.new(name); bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=1)
    if uv:
        uvl = bm.loops.layers.uv.new()
        for face in bm.faces:
            for l in face.loops:
                l[uvl].uv = (l.vert.co.x / 2 + 0.5, l.vert.co.y / 2 + 0.5)
    bm.to_mesh(me); bm.free()
    return me


# ── background: emissive plane, 3-stop vertical gradient + drifting warm sun glow; colours per beat-sheet section ──
# section = (timing, top, mid, bottom, sun glow colour, glow strength, transition frames)
SECTIONS = [(TT(t), *rest) for t, *rest in BEATS["bg"]]
bg = link(bpy.data.objects.new("bg", quad("bg")))
bg.scale = (5.4, 4.05, 1)                     # covers the end-card view (camera further back); demo view sees the middle 75 %
bg.rotation_euler = (rad(90), 0, 0)
bg.location = (0, 7, 0)
bgm = bpy.data.materials.new("bg"); bgm.use_nodes = True
N, Lk = bgm.node_tree.nodes, bgm.node_tree.links
N.clear()
tc = N.new("ShaderNodeTexCoord"); sep = N.new("ShaderNodeSeparateXYZ"); Lk.new(tc.outputs["UV"], sep.inputs[0])
c_top, c_mid, c_bot, c_sun = (N.new("ShaderNodeRGB") for _ in range(4))
r1 = N.new("ShaderNodeMapRange"); r1.interpolation_type = "SMOOTHSTEP"; r1.inputs["From Min"].default_value = 0.08; r1.inputs["From Max"].default_value = 0.55
r2 = N.new("ShaderNodeMapRange"); r2.interpolation_type = "SMOOTHSTEP"; r2.inputs["From Min"].default_value = 0.5; r2.inputs["From Max"].default_value = 0.95
Lk.new(sep.outputs["Y"], r1.inputs["Value"]); Lk.new(sep.outputs["Y"], r2.inputs["Value"])
m1 = N.new("ShaderNodeMix"); m1.data_type = "RGBA"
Lk.new(r1.outputs[0], m1.inputs["Factor"]); Lk.new(c_bot.outputs[0], sock_in(m1, "A", "RGBA")); Lk.new(c_mid.outputs[0], sock_in(m1, "B", "RGBA"))
m2 = N.new("ShaderNodeMix"); m2.data_type = "RGBA"
Lk.new(r2.outputs[0], m2.inputs["Factor"]); Lk.new(sock_out(m1, "RGBA"), sock_in(m2, "A", "RGBA")); Lk.new(c_top.outputs[0], sock_in(m2, "B", "RGBA"))
# sun glow: radial falloff around a drifting point (aspect-corrected), screen-blended on top
sun_p = N.new("ShaderNodeCombineXYZ")
d_sub = N.new("ShaderNodeVectorMath"); d_sub.operation = "SUBTRACT"
Lk.new(tc.outputs["UV"], d_sub.inputs[0]); Lk.new(sun_p.outputs[0], d_sub.inputs[1])
d_sc = N.new("ShaderNodeVectorMath"); d_sc.operation = "MULTIPLY"; d_sc.inputs[1].default_value = (1.33, 1.0, 0)
Lk.new(d_sub.outputs[0], d_sc.inputs[0])
d_len = N.new("ShaderNodeVectorMath"); d_len.operation = "LENGTH"; Lk.new(d_sc.outputs[0], d_len.inputs[0])
fall = N.new("ShaderNodeMapRange"); fall.interpolation_type = "SMOOTHSTEP"
fall.inputs["From Min"].default_value = 0.62; fall.inputs["From Max"].default_value = 0.0
Lk.new(d_len.outputs["Value"], fall.inputs["Value"])
g_pow = math_node(N, "POWER", fall.outputs[0], 1.6, Lk)
g_amt = math_node(N, "MULTIPLY", g_pow.outputs[0], 0.5, Lk)
m3 = N.new("ShaderNodeMix"); m3.data_type = "RGBA"; m3.blend_type = "SCREEN"
Lk.new(g_amt.outputs[0], m3.inputs["Factor"]); Lk.new(sock_out(m2, "RGBA"), sock_in(m3, "A", "RGBA")); Lk.new(c_sun.outputs[0], sock_in(m3, "B", "RGBA"))
# beats "bg_image" (v32): a photo plate instead of the gradient (e.g. the app's own night garden, heavily defocused), so the
# backdrop around the phone is the same world as its screen; the section colours then only tint it (multiply) and the glow
if BEATS.get("bg_image"):
    timg = N.new("ShaderNodeTexImage")
    timg.image = bpy.data.images.load(os.path.abspath(BEATS["bg_image"]))
    Lk.new(tc.outputs["UV"], timg.inputs["Vector"])
    mt = N.new("ShaderNodeMix"); mt.data_type = "RGBA"; mt.blend_type = "MULTIPLY"; mt.inputs["Factor"].default_value = 1.0
    Lk.new(timg.outputs["Color"], sock_in(mt, "A", "RGBA")); Lk.new(sock_out(m2, "RGBA"), sock_in(mt, "B", "RGBA"))
    Lk.new(sock_out(mt, "RGBA"), sock_in(m3, "A", "RGBA"))
em = N.new("ShaderNodeEmission"); Lk.new(sock_out(m3, "RGBA"), em.inputs["Color"])
out = N.new("ShaderNodeOutputMaterial"); Lk.new(em.outputs[0], out.inputs[0])
bg.data.materials.append(bgm)


def key_bg(f, sec):
    _, ct, cm, cb, cs, g, _ = sec
    for sock, v in ((c_top.outputs[0], hexc(ct)), (c_mid.outputs[0], hexc(cm)), (c_bot.outputs[0], hexc(cb)),
                    (c_sun.outputs[0], hexc(cs)), (g_amt.inputs[1], g)):
        key_sock(sock, f, v)


for i, s in enumerate(SECTIONS):
    if i:                                      # hold the old colours until the timing, then cross-fade over s[6] frames
        key_bg(s[0] - 1, SECTIONS[i - 1])      # (0 frames = hard change, used at the cut to the end card)
    key_bg(s[0] + s[6], s)
# the sun drifts slowly to the right and down, and "breathes" a little
for f, x, y in ((0, 0.2, 0.86), (F_CARD - 1, 0.31, 0.8), (F_CARD, 0.16, 0.84), (NF, 0.2, 0.82)):
    key_sock(sun_p.inputs["X"], f, x); key_sock(sun_p.inputs["Y"], f, y)
interp(bgm.node_tree, "BEZIER")

# ── world: warm reflections on the titanium frame ──
w = bpy.data.worlds.new("w"); sc.world = w; w.use_nodes = True
wbg = w.node_tree.nodes["Background"]
wbg.inputs["Color"].default_value = hexc(BEATS.get("world", "#f2d2b2"))
wbg.inputs["Strength"].default_value = 0.6


# ── iPhone 17 Pro Max (same model as Neon Sign) ──
def rounded_rect(bm, w, h, r, z, segs=14):
    pts = []
    for cx, cy, a0 in ((w / 2 - r, h / 2 - r, 0), (-w / 2 + r, h / 2 - r, 90), (-w / 2 + r, -h / 2 + r, 180), (w / 2 - r, -h / 2 + r, 270)):
        for k in range(segs + 1):
            a = rad(a0 + 90 * k / segs)
            pts.append(bm.verts.new((cx + r * math.cos(a), cy + r * math.sin(a), z)))
    return bm.faces.new(pts)


PW, PH, PR, THICK = 1.0, 2.13, 0.16, 0.09
SW = PW - 0.06
LAYOUT = json.load(open(os.path.join(ROOT, "app", "assets", "scene", "layout.json")))
VW, VH = LAYOUT.get("view", (LAYOUT.get("w", 440), LAYOUT.get("h", 956)))
SH = SW * VH / VW
SCR_Y = -THICK / 2 - 0.006
phone = link(bpy.data.objects.new("PHONE", None))
me = bpy.data.meshes.new("body"); bm = bmesh.new()
f0 = rounded_rect(bm, PW, PH, PR, -THICK / 2)
ext = bmesh.ops.extrude_face_region(bm, geom=[f0])
bmesh.ops.translate(bm, vec=(0, 0, THICK), verts=[v for v in ext["geom"] if isinstance(v, bmesh.types.BMVert)])
bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
bm.to_mesh(me); bm.free()
body = link(bpy.data.objects.new("body", me))
bev = body.modifiers.new("bevel", "BEVEL"); bev.width, bev.segments, bev.limit_method = 0.025, 5, "ANGLE"
me.shade_smooth() if hasattr(me, "shade_smooth") else None
ti = bpy.data.materials.new("titanium"); ti.use_nodes = True
bsdf = next(n for n in ti.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
bsdf.inputs["Base Color"].default_value = hexc("#9a938a"); bsdf.inputs["Metallic"].default_value = 1.0; bsdf.inputs["Roughness"].default_value = 0.3
me.materials.append(ti)
body.parent = phone
body.rotation_euler = (rad(90), 0, 0)
GAIN = float(BEATS.get("screen_gain", 1.0))


def screen_material(name, app_t0):
    """Emission material playing the recording so that clip frame f shows app second app_t0 + (f − f_first) / 60."""
    sm = bpy.data.materials.new(name); sm.use_nodes = True
    n = sm.node_tree.nodes; n.clear()
    tex = n.new("ShaderNodeTexImage")
    img = bpy.data.images.load(SCREEN, check_existing=True); img.source = "MOVIE"
    tex.image = img
    tex.interpolation = "Cubic"
    iu = tex.image_user
    iu.frame_duration = 100000
    iu.use_auto_refresh = True
    iu.use_cyclic = False
    e = n.new("ShaderNodeEmission"); e.inputs["Strength"].default_value = GAIN
    o = n.new("ShaderNodeOutputMaterial")
    sm.node_tree.links.new(tex.outputs["Color"], e.inputs["Color"]); sm.node_tree.links.new(e.outputs[0], o.inputs[0])
    return sm, iu


screens = []
for name, wdt, hgt, r, yoff, kind in (("glass", PW - 0.012, PH - 0.012, PR - 0.006, -THICK / 2 - 0.004, "black"),
                                      ("screen", SW, SH, PR - 0.035, SCR_Y, "screen"),
                                      ("screen_card", SW, SH, PR - 0.035, SCR_Y - 0.0004, "card")):
    if kind == "card" and BEATS.get("card_screen") is None:
        continue
    me = bpy.data.meshes.new(name); bm = bmesh.new()
    rounded_rect(bm, wdt, hgt, r, 0)
    uv = bm.loops.layers.uv.new()
    for face in bm.faces:
        for l in face.loops:
            l[uv].uv = (l.vert.co.x / wdt + 0.5, l.vert.co.y / hgt + 0.5)
    bm.to_mesh(me); bm.free()
    ob = link(bpy.data.objects.new(name, me))
    ob.parent = phone
    ob.rotation_euler = (rad(90), 0, 0)
    ob.location = (0, yoff, 0)
    if kind == "black":
        me.materials.append(mat_emit("glass", "#050505")[0])
    elif kind == "screen":
        sm, iu = screen_material("screen", APP0)
        # clip frame f shows recording frame (f − frame_start) → clip frame 0 = recording second FILM0 + APP0
        iu.frame_start = -round((FILM0 + APP0) * FPS)
        me.materials.append(sm)
    else:
        # optional: on the end card the screen restarts from app second card_screen (e.g. the opening cluster again)
        sm, iu = screen_material("screen_card", float(BEATS["card_screen"]))
        iu.frame_start = F_CARD - round((FILM0 + float(BEATS["card_screen"])) * FPS)
        me.materials.append(sm)
        key(ob, "hide_render", 0, True); key(ob, "hide_render", F_CARD, False)
        interp(ob, "CONSTANT")
me = bpy.data.meshes.new("island"); bm = bmesh.new()
rounded_rect(bm, 0.3, 0.085, 0.0425, 0)
bm.to_mesh(me); bm.free()
isl = link(bpy.data.objects.new("island", me))
isl.parent = phone; isl.rotation_euler = (rad(90), 0, 0); isl.location = (0, -THICK / 2 - 0.009, SH / 2 - 0.075)
me.materials.append(mat_emit("island", "#000000")[0])
for i, (x, z, hh) in enumerate(((PW / 2 + 0.006, 0.45, 0.22), (-PW / 2 - 0.006, 0.55, 0.12), (-PW / 2 - 0.006, 0.3, 0.16), (-PW / 2 - 0.006, 0.08, 0.16))):
    me = bpy.data.meshes.new(f"btn{i}"); bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1); bmesh.ops.scale(bm, vec=(0.02, 0.04, hh), verts=bm.verts)
    bm.to_mesh(me); bm.free()
    b = link(bpy.data.objects.new(f"btn{i}", me)); b.parent = phone; b.location = (x, 0, z); me.materials.append(ti)

# soft contact shadow behind the phone: superellipse falloff (rounded-rect look), warm dark brown, low alpha
sh = link(bpy.data.objects.new("shadow", quad("shadow")))
sh.parent = phone
sh.rotation_euler = (rad(90), 0, 0)
sh.location = (0.07, 0.35, -0.11)
sh.scale = (PW * 0.5 + 0.22, PH * 0.5 + 0.22, 1)
shm = bpy.data.materials.new("shadow"); shm.use_nodes = True; blended(shm)
N, Lk = shm.node_tree.nodes, shm.node_tree.links
N.clear()
uvn = N.new("ShaderNodeUVMap")
c0 = N.new("ShaderNodeVectorMath"); c0.operation = "SUBTRACT"; c0.inputs[1].default_value = (0.5, 0.5, 0)
Lk.new(uvn.outputs[0], c0.inputs[0])
c1 = N.new("ShaderNodeVectorMath"); c1.operation = "MULTIPLY"; c1.inputs[1].default_value = (2.0, 2.0, 0)
Lk.new(c0.outputs[0], c1.inputs[0])
c2 = N.new("ShaderNodeVectorMath"); c2.operation = "ABSOLUTE"; Lk.new(c1.outputs[0], c2.inputs[0])
sx = N.new("ShaderNodeSeparateXYZ"); Lk.new(c2.outputs[0], sx.inputs[0])
px = math_node(N, "POWER", sx.outputs["X"], 5.0, Lk); py = math_node(N, "POWER", sx.outputs["Y"], 5.0, Lk)
ad = math_node(N, "ADD", px.outputs[0], py.outputs[0], Lk)
rt = math_node(N, "POWER", ad.outputs[0], 0.2, Lk)
fo = N.new("ShaderNodeMapRange"); fo.interpolation_type = "SMOOTHSTEP"
fo.inputs["From Min"].default_value = 1.0; fo.inputs["From Max"].default_value = 0.55
Lk.new(rt.outputs[0], fo.inputs["Value"])
al = math_node(N, "MULTIPLY", fo.outputs[0], 0.34, Lk)
tr = N.new("ShaderNodeBsdfTransparent")
se = N.new("ShaderNodeEmission"); se.inputs["Color"].default_value = hexc("#5a3320")
mx = N.new("ShaderNodeMixShader")
Lk.new(al.outputs[0], mx.inputs[0]); Lk.new(tr.outputs[0], mx.inputs[1]); Lk.new(se.outputs[0], mx.inputs[2])
so = N.new("ShaderNodeOutputMaterial"); Lk.new(mx.outputs[0], so.inputs[0])
sh.data.materials.append(shm)

# ── lights: warm key from the sun side (upper left), peach rim from the right ──
key_l = bpy.data.lights.new("key", "AREA"); key_l.size = 6; key_l.energy = 650; key_l.color = hexc("#ffe2c2")[:3]
kl = link(bpy.data.objects.new("key", key_l)); kl.location = (-4, -5, 5); kl.rotation_euler = (rad(50), 0, rad(-40))
rim_d = bpy.data.lights.new("rim", "AREA"); rim_d.size = 4; rim_d.energy = 520; rim_d.color = hexc("#ffc39a")[:3]
rim = link(bpy.data.objects.new("rim", rim_d)); rim.location = (4.5, -1.5, 1.5); rim.rotation_euler = (rad(90), 0, rad(70))


# ── soft sprites: bokeh discs and out-of-focus soap bubbles (colour + opacity from the object colour) ──
def sprite_material(name, ring):
    """ring=False: bokeh disc (flat, slightly brighter soft rim). ring=True: blurry soap bubble (thin iridescent rim,
    hue running around the rim and drifting over time, small highlight upper left, faint fill)."""
    m = bpy.data.materials.new(name); m.use_nodes = True; blended(m)
    N, Lk = m.node_tree.nodes, m.node_tree.links
    N.clear()
    uvn = N.new("ShaderNodeUVMap")
    c0 = N.new("ShaderNodeVectorMath"); c0.operation = "SUBTRACT"; c0.inputs[1].default_value = (0.5, 0.5, 0)
    Lk.new(uvn.outputs[0], c0.inputs[0])
    dl = N.new("ShaderNodeVectorMath"); dl.operation = "LENGTH"; Lk.new(c0.outputs[0], dl.inputs[0])
    d = dl.outputs["Value"]
    oi = N.new("ShaderNodeObjectInfo")
    if not ring:
        edge = N.new("ShaderNodeMapRange"); edge.interpolation_type = "SMOOTHSTEP"
        edge.inputs["From Min"].default_value = 0.5; edge.inputs["From Max"].default_value = 0.36
        Lk.new(d, edge.inputs["Value"])
        rimr = N.new("ShaderNodeMapRange"); rimr.interpolation_type = "SMOOTHSTEP"
        rimr.inputs["From Min"].default_value = 0.2; rimr.inputs["From Max"].default_value = 0.44
        rimr.inputs["To Min"].default_value = 0.72; rimr.inputs["To Max"].default_value = 1.0
        Lk.new(d, rimr.inputs["Value"])
        a0 = math_node(N, "MULTIPLY", edge.outputs[0], rimr.outputs[0], Lk)
        alpha = math_node(N, "MULTIPLY", a0.outputs[0], oi.outputs["Alpha"], Lk)
        col = oi.outputs["Color"]
    else:
        # rim: bump around d ≈ 0.43, soft (out of focus)
        rd = math_node(N, "SUBTRACT", d, 0.43, Lk)
        ra = math_node(N, "ABSOLUTE", rd.outputs[0], None, Lk)
        rb = N.new("ShaderNodeMapRange"); rb.interpolation_type = "SMOOTHSTEP"
        rb.inputs["From Min"].default_value = 0.075; rb.inputs["From Max"].default_value = 0.0
        Lk.new(ra.outputs[0], rb.inputs["Value"])
        fill = N.new("ShaderNodeMapRange"); fill.interpolation_type = "SMOOTHSTEP"
        fill.inputs["From Min"].default_value = 0.5; fill.inputs["From Max"].default_value = 0.4
        fill.inputs["To Max"].default_value = 0.1
        Lk.new(d, fill.inputs["Value"])
        # highlight spot upper left
        hs = N.new("ShaderNodeVectorMath"); hs.operation = "SUBTRACT"; hs.inputs[1].default_value = (0.33, 0.68, 0)
        Lk.new(uvn.outputs[0], hs.inputs[0])
        hl = N.new("ShaderNodeVectorMath"); hl.operation = "LENGTH"; Lk.new(hs.outputs[0], hl.inputs[0])
        hr = N.new("ShaderNodeMapRange"); hr.interpolation_type = "SMOOTHSTEP"
        hr.inputs["From Min"].default_value = 0.11; hr.inputs["From Max"].default_value = 0.0
        hr.inputs["To Max"].default_value = 0.8
        Lk.new(hl.outputs["Value"], hr.inputs["Value"])
        s1 = math_node(N, "ADD", rb.outputs[0], fill.outputs[0], Lk)
        s2 = math_node(N, "ADD", s1.outputs[0], hr.outputs[0], Lk)
        alpha = math_node(N, "MULTIPLY", s2.outputs[0], oi.outputs["Alpha"], Lk)
        # iridescent hue around the rim: angle/2π + object random + time drift (keyed on a value node)
        sx = N.new("ShaderNodeSeparateXYZ"); Lk.new(c0.outputs[0], sx.inputs[0])
        at = math_node(N, "ARCTAN2", sx.outputs["Y"], sx.outputs["X"], Lk)
        h0 = math_node(N, "MULTIPLY", at.outputs[0], 1 / (2 * math.pi), Lk)
        h1 = math_node(N, "ADD", h0.outputs[0], oi.outputs["Random"], Lk)
        drift = N.new("ShaderNodeValue"); drift.name = "drift"
        h2 = math_node(N, "ADD", h1.outputs[0], drift.outputs[0], Lk)
        h3 = math_node(N, "FRACT", h2.outputs[0], None, Lk)
        hsv = N.new("ShaderNodeCombineColor"); hsv.mode = "HSV"
        Lk.new(h3.outputs[0], hsv.inputs[0]); hsv.inputs[1].default_value = 0.42; hsv.inputs[2].default_value = 1.0
        tint = N.new("ShaderNodeMix"); tint.data_type = "RGBA"; tint.blend_type = "MULTIPLY"; tint.inputs["Factor"].default_value = 1.0
        Lk.new(hsv.outputs[0], sock_in(tint, "A", "RGBA")); Lk.new(oi.outputs["Color"], sock_in(tint, "B", "RGBA"))
        col = sock_out(tint, "RGBA")
        for f, v in ((0, 0.0), (NF, 0.35)):
            key_sock(drift.outputs[0], f, v)
        interp(m.node_tree, "LINEAR")
    e = N.new("ShaderNodeEmission"); Lk.new(col, e.inputs["Color"])
    tr = N.new("ShaderNodeBsdfTransparent")
    mx = N.new("ShaderNodeMixShader")
    Lk.new(alpha.outputs[0], mx.inputs[0]); Lk.new(tr.outputs[0], mx.inputs[1]); Lk.new(e.outputs[0], mx.inputs[2])
    o = N.new("ShaderNodeOutputMaterial"); Lk.new(mx.outputs[0], o.inputs[0])
    return m


def drift_sprite(name, me, x, y, z, size, color, alpha, rise, sway):
    ob = link(bpy.data.objects.new(name, me))
    ob.rotation_euler = (rad(90), 0, 0)
    ob.scale = (size, size, 1)
    ob.color = hexc(color)[:3] + (alpha,)
    key(ob, "location", 0, (x, y, z)); key(ob, "location", NF, (x + rng.uniform(-0.3, 0.3), y, z + rise))
    for fc in fcurves(ob):
        for k in fc.keyframe_points:
            k.interpolation = "LINEAR"
        if fc.array_index in (0, 2):
            mo = fc.modifiers.new("NOISE"); mo.scale, mo.strength, mo.phase = rng.uniform(90, 160), sway, rng.uniform(0, 100)
    return ob


bokeh_m = sprite_material("bokeh", False)
bokeh_me = quad("bokeh"); bokeh_me.materials.append(bokeh_m)
BOKEH_COLS = BEATS.get("bokeh_cols", ["#fff1d6", "#ffe0b0", "#ffd2a6", "#ffcfb8", "#fff6e6", "#ffe7c4", "#d9ecff", "#e6f2d8"])
BOKEH_A = float(BEATS.get("bokeh_alpha", 1.0))   # per-look opacity scale
for i in range(int(BEATS.get("bokeh_n", 26))):
    y = rng.uniform(1.5, 6.0)
    side = rng.choice((-1, 1))
    x = side * rng.uniform(0.6, 4.6) if rng.random() < 0.8 else rng.uniform(-4.5, 4.5)
    z = rng.uniform(-3.2, 3.4)
    size = rng.uniform(0.1, 0.42) * (1 + y * 0.12)
    col = BOKEH_COLS[i % len(BOKEH_COLS)]
    drift_sprite(f"bokeh{i}", bokeh_me, x, y, z, size, col, rng.uniform(0.1, 0.3) * BOKEH_A, rng.uniform(0.15, 0.45), rng.uniform(0.04, 0.12))
bub_m = sprite_material("softbubble", True)
bub_me = quad("softbubble"); bub_me.materials.append(bub_m)
for i in range(int(BEATS.get("bubbles_n", 9))):
    front = i < 2                              # two big, very soft ones in front, far at the edges
    if front:
        # left one kept low and wide of the end-card text column
        x, y, z, size = (-3.3 if i == 0 else 2.05), -1.6, (-1.9 if i == 0 else 0.75), rng.uniform(0.32, 0.4)
        a = 0.32
    else:
        # keep clear of the end-card text column (x ≈ card_x, rising bubbles at their end-card height)
        cx = float(BEATS.get("card_x", -1.3))
        for _try in range(30):
            y = rng.uniform(1.0, 4.5)
            x = rng.choice((-1, 1)) * rng.uniform(0.9, 4.0)
            z = rng.uniform(-3.0, 2.6)
            rise = rng.uniform(0.5, 1.1)
            if not (abs(x - cx) < 1.9 and -2.0 < z + rise * 0.85 < 1.6):
                break
        size, a = rng.uniform(0.14, 0.38) * (1 + y * 0.1), rng.uniform(0.45, 0.75)
        drift_sprite(f"softbubble{i}", bub_me, x, y, z, size, "#ffffff", a, rise, rng.uniform(0.05, 0.12))
        continue
    drift_sprite(f"softbubble{i}", bub_me, x, y, z, size, "#ffffff", a, rng.uniform(0.5, 1.1), rng.uniform(0.05, 0.12))

# hand-placed rings, e.g. to give the panel opposite the words some weight: beats "side_rings": [[x, y, z, size, alpha, rise], …]
for i, (x, y, z, size, a, rise) in enumerate(BEATS.get("side_rings", [])):
    drift_sprite(f"sidering{i}", bub_me, x, y, z, size, "#ffffff", a, rise, rng.uniform(0.04, 0.09))

# ── end card: title (letters pop in), tagline, stack, author, studio ──
def font(*paths):
    for p in paths:
        p = os.path.expanduser(p)
        if os.path.exists(p):
            try:
                return bpy.data.fonts.load(p, check_existing=True)
            except RuntimeError:
                pass
    return None


# beats "title_font": a font file for the end-card title (v26: a plain sans instead of the script)
TITLE_FONT = font(*([BEATS["title_font"]] if BEATS.get("title_font") else []), "~/Library/Fonts/NVN GrandHotel VH.ttf",
                  "/System/Library/Fonts/Supplemental/SnellRoundhand.ttc", "/System/Library/Fonts/Supplemental/SignPainter.ttc")
BODY_FONT = font("~/Library/Fonts/SFProRounded-Semibold.otf", "/System/Library/Fonts/Supplemental/Arial Rounded Bold.ttf",
                 "/System/Library/Fonts/Supplemental/Arial Bold.ttf")
BOLD_FONT = font("~/Library/Fonts/SFProRounded-Bold.otf", "/System/Library/Fonts/Supplemental/Arial Rounded Bold.ttf",
                 "/System/Library/Fonts/Supplemental/Arial Bold.ttf")
LABEL_FONT = font("/System/Library/Fonts/Supplemental/DIN Alternate Bold.ttf", "/System/Library/Fonts/Supplemental/Arial Bold.ttf")


def text(name, body, fnt, size, mat, loc, align="CENTER", parent=None):
    cu = bpy.data.curves.new(name, "FONT")
    cu.body, cu.size, cu.align_x, cu.align_y = body, size, align, "CENTER"
    if fnt:
        cu.font = fnt
    ob = link(bpy.data.objects.new(name, cu))
    ob.rotation_euler = (rad(90), 0, 0)
    ob.location = loc
    ob.parent = parent
    cu.materials.append(mat)
    return ob


def alpha_mat(name, color, alpha, strength=1.0):
    m = bpy.data.materials.new(name); m.use_nodes = True; blended(m)
    N, Lk = m.node_tree.nodes, m.node_tree.links
    N.clear()
    e = N.new("ShaderNodeEmission"); e.inputs["Color"].default_value = hexc(color); e.inputs["Strength"].default_value = strength
    tr = N.new("ShaderNodeBsdfTransparent")
    mx = N.new("ShaderNodeMixShader"); mx.inputs[0].default_value = alpha
    Lk.new(tr.outputs[0], mx.inputs[1]); Lk.new(e.outputs[0], mx.inputs[2])
    o = N.new("ShaderNodeOutputMaterial"); Lk.new(mx.outputs[0], o.inputs[0])
    return m


def title_material():
    """Pearly cream with a soap-film sheen: hue from world position drifting over the card, mixed lightly over cream."""
    m = bpy.data.materials.new("title"); m.use_nodes = True
    N, Lk = m.node_tree.nodes, m.node_tree.links
    N.clear()
    geo = N.new("ShaderNodeNewGeometry")
    sx = N.new("ShaderNodeSeparateXYZ"); Lk.new(geo.outputs["Position"], sx.inputs[0])
    hx = math_node(N, "MULTIPLY", sx.outputs["X"], 0.28, Lk)
    hz_ = math_node(N, "MULTIPLY", sx.outputs["Z"], 0.9, Lk)
    h1 = math_node(N, "ADD", hx.outputs[0], hz_.outputs[0], Lk)
    drift = N.new("ShaderNodeValue")
    h2 = math_node(N, "ADD", h1.outputs[0], drift.outputs[0], Lk)
    h3 = math_node(N, "FRACT", h2.outputs[0], None, Lk)
    hsv = N.new("ShaderNodeCombineColor"); hsv.mode = "HSV"
    Lk.new(h3.outputs[0], hsv.inputs[0]); hsv.inputs[1].default_value = 0.5; hsv.inputs[2].default_value = 1.0
    mx = N.new("ShaderNodeMix"); mx.data_type = "RGBA"; mx.inputs["Factor"].default_value = float(BEATS.get("title_mix", 0.3))  # sheen amount
    # beats "title_col" (v36d: a deep rose on the light dawn backdrop; default pearly cream)
    sock_in(mx, "A", "RGBA").default_value = hexc(BEATS.get("title_col", "#fffaf0")); Lk.new(hsv.outputs[0], sock_in(mx, "B", "RGBA"))
    e = N.new("ShaderNodeEmission"); Lk.new(sock_out(mx, "RGBA"), e.inputs["Color"]); e.inputs["Strength"].default_value = 1.08
    o = N.new("ShaderNodeOutputMaterial"); Lk.new(e.outputs[0], o.inputs[0])
    for f, v in ((F_CARD, 0.0), (NF, 0.45)):
        key_sock(drift.outputs[0], f, v)
    interp(m.node_tree, "LINEAR")
    return m


# ── big words beside the phone (as in neon-sign): BLOW / STICK / POP name each act; letters pop in staggered, the group
#    slides and grows slightly through its act, hard cut at the end. beats "words": [[word, t0, t1, color, alpha, size, x, stack], …]
#    x = centre of the word at the words' depth (±1.96 = middle of the empty panel left / right of the phone, 0 = behind it),
#    stack = letters top to bottom (cut in on the beat);
#    t0 < 0 → the word is already in on frame 1
WORD_FONT = font("~/Library/Fonts/SFProRounded-Heavy.otf", "~/Library/Fonts/SFProRounded-Black.otf",
                 "~/Library/Fonts/SFProRounded-Bold.otf", "/System/Library/Fonts/Supplemental/Arial Rounded Bold.ttf")


def big_word(word, f0, f1, color, alpha, size=2.4, cx=0.0, stack=False):
    rig = link(bpy.data.objects.new("rig_" + word, None))
    m = alpha_mat("word_" + word, color, alpha, 1.0)
    letters = [text(f"big_{word}_{i}", ch, WORD_FONT, size, m, (0, 0, 0), parent=rig) for i, ch in enumerate(word)]
    bpy.context.view_layer.update()
    if stack:
        # letters stacked top to bottom (signage), the column centred on the panel; cut in on the beat with a quick settle
        step_z = size * 0.62
        pos = [(0.0, (len(word) - 1) / 2 * step_z - i * step_z) for i in range(len(word))]
        stagger, pop_in = 1, ((0, 1.08, 0.0), (5, 1.0, 0.0))
    else:
        gap = 0.05 * size
        widths = [ob.dimensions.x for ob in letters]
        x = -(sum(widths) + gap * (len(word) - 1)) / 2
        pos = []
        for wd in widths:
            pos.append((x + wd / 2, 0.0)); x += wd + gap
        stagger, pop_in = 3, ((0, 0.2, -0.9), (9, 1.12, 0.08), (18, 1.0, 0.0))   # pop in with overshoot
    for i, (ob, (lx, lz)) in enumerate(zip(letters, pos)):
        fi = f0 + stagger * i
        for f, vis in (((min(0, fi) - 1), False), (fi, True), (f1, False)):
            key(ob, "hide_render", f, not vis)
        for df, sc_, dz in pop_in:
            key(ob, "scale", fi + df, (sc_, sc_, sc_)); key(ob, "location", fi + df, (lx, 0, lz + dz))
        for fc in fcurves(ob):
            if fc.data_path == "hide_render":
                for k in fc.keyframe_points:
                    k.interpolation = "CONSTANT"
    drift = 0.7 if cx == 0 else 0.06
    for f, x_, s_ in ((f0, cx + drift, 0.97), (f1, cx - drift, 1.03)):
        key(rig, "location", f, (x_, 4.2, 0.05 if stack else 0.1)); key(rig, "scale", f, (s_, s_, s_))
    return rig


for wd in BEATS.get("words", []):
    w_, t0, t1, col, al, size = wd[:6]
    big_word(w_, TT(t0), min(TT(t1), F_CARD), col, al, size, float(wd[6]) if len(wd) > 6 else 0.0,
             bool(wd[7]) if len(wd) > 7 else False)


EX = float(BEATS.get("card_x", -1.3))
TITLE = BEATS.get("title", "Soap Bubbles")
T_SIZE, T_Z, T_MAXW = 1.2, 0.86, 2.85
t_mat = title_material()
sh_mat = alpha_mat("title_shadow", BEATS.get("title_shadow", "#6a3a22"), float(BEATS.get("title_shadow_a", 0.26)))


def measure(body, size):
    cu = bpy.data.curves.new("m", "FONT"); cu.body, cu.size, cu.align_x = body, size, "LEFT"
    if TITLE_FONT:
        cu.font = TITLE_FONT
    ob = link(bpy.data.objects.new("m", cu))
    bpy.context.view_layer.update()
    xs = [v[0] for v in ob.bound_box]
    r = (min(xs), max(xs))
    bpy.data.objects.remove(ob); bpy.data.curves.remove(cu)
    return r


full = measure(TITLE, T_SIZE)
T_SIZE *= min(1.0, T_MAXW / (full[1] - full[0]))
full = measure(TITLE, T_SIZE)
x_left = EX - (full[0] + full[1]) / 2                 # origin of the left-aligned title so it is centred on EX
f_title = F_CARD + FR(float(BEATS.get("title_in", 0.12)))
step = float(BEATS.get("title_step", 0.055))
k_letter = 0
for i, ch in enumerate(TITLE):
    if ch == " ":
        continue
    pre = measure(TITLE[:i + 1], T_SIZE)
    one = measure(ch, T_SIZE)
    # letter ink right edge must match the prefix ink right edge (exact kerning/joins)
    cx = x_left + pre[1] - one[1] + (one[0] + one[1]) / 2
    rig = link(bpy.data.objects.new(f"title_rig{i}", None))
    for idx, (mat, off) in enumerate(((t_mat, (0, 0, 0)), (sh_mat, (0.03, 0.05, -0.045)))):
        cu = bpy.data.curves.new(f"title{i}_{idx}", "FONT")
        cu.body, cu.size, cu.align_x, cu.align_y = ch, T_SIZE, "LEFT", "CENTER"
        cu.offset_x = -(one[0] + one[1]) / 2
        if TITLE_FONT:
            cu.font = TITLE_FONT
        cu.materials.append(mat)
        ob = link(bpy.data.objects.new(f"title{i}_{idx}", cu))
        ob.rotation_euler = (rad(90), 0, 0)
        ob.location = off
        ob.parent = rig
    fi = f_title + FR(step * k_letter)
    k_letter += 1
    key(rig, "hide_render", 0, True); key(rig, "hide_render", fi, False)
    for c in rig.children:
        key(c, "hide_render", 0, True); key(c, "hide_render", fi, False)
        interp(c, "CONSTANT")
    # bubble pop-in: tiny → overshoot → settle, rising from below
    for f, s, dz in ((fi, 0.15, -0.22), (fi + 7, 1.16, 0.035), (fi + 13, 0.96, -0.01), (fi + 19, 1.0, 0.0)):
        key(rig, "scale", f, (s, s, s)); key(rig, "location", f, (cx, 0, T_Z + dz))
    key(rig, "location", NF, (cx, 0, T_Z))
    for fc in fcurves(rig):
        if fc.data_path == "hide_render":
            for k in fc.keyframe_points:
                k.interpolation = "CONSTANT"
        if fc.data_path == "location" and fc.array_index == 2:
            # gentle bob afterwards, each letter its own phase
            mo = fc.modifiers.new("NOISE"); mo.scale, mo.strength, mo.phase = 26, 0.035, rng.uniform(0, 100)
            mo.use_restricted_range = True; mo.frame_start, mo.frame_end = fi + 19, NF + 10; mo.blend_in = 12

TXT = {"tagline": "#5b2a3c", "stack": "#6a4033", "by": "#8c3f63", "love": "#6a4033", **BEATS.get("text_col", {})}  # per-look overrides
BODY = [("tagline", BEATS.get("tagline", "Blow. Watch it shimmer. Pop."), BOLD_FONT, 0.22, TXT["tagline"], 0.06, 0.0),
        ("stack", BEATS.get("stack", "Expo · React Native · Skia · Reanimated · Blender"), BODY_FONT, 0.148, TXT["stack"], -0.46, 0.45),
        ("by", "by Hoa Hoang · @novahoangdev", BOLD_FONT, 0.19, TXT["by"], -0.88, 0.55),
        ("love", "From @vgangstudio with love", BODY_FONT, 0.165, TXT["love"], -1.28, 0.62)]
# beats "body_layout" {name: [size, z, strength]} and "body_align" "LEFT" (lines flush with the title's left edge)
BL = BEATS.get("body_layout", {})
B_ALIGN = BEATS.get("body_align", "CENTER")
BX = x_left if B_ALIGN == "LEFT" else EX
for name, body_, fnt, size, col, z, dt in BODY:
    if name in BL and not BL[name]:
        continue                                # [] drops the line
    size, z, stren = (BL[name] + [1.0])[:3] if name in BL else (size, z, 1.0)
    ob = text(name, body_, fnt, size, mat_emit(name + "_m", col, stren)[0], (BX, 0, z), align=B_ALIGN)
    f_in = F_CARD + FR(float(BEATS.get("body_in", 0.62)) + dt * 0.5)   # body lines pop in after the title
    key(ob, "hide_render", 0, True); key(ob, "hide_render", f_in, False)
    for f, s_, dz in ((f_in, 0.4, -0.12), (f_in + 9, 1.06, 0.01), (f_in + 18, 1.0, 0.0)):
        key(ob, "scale", f, (s_, s_, s_)); key(ob, "location", f, (BX, 0, z + dz))
    for fc in fcurves(ob):
        if fc.data_path == "hide_render":
            for k in fc.keyframe_points:
                k.interpolation = "CONSTANT"

# ── camera: fixed during the demo, fixed (further back) on the end card; one straight cut ──
cam_d = bpy.data.cameras.new("cam"); cam_d.lens = 50; cam_d.sensor_fit = "VERTICAL"; cam_d.sensor_height = 24
cam_d.clip_start = 0.05
cam = link(bpy.data.objects.new("cam", cam_d)); sc.camera = cam
cam.rotation_euler = (rad(90), 0, 0)
D0, D1 = float(BEATS.get("camera_d", 5.0)), float(BEATS.get("card_d", 8.6))
CP = BEATS.get("card_phone", {"loc": [1.22, -2.7, 0.05], "rot": [0, 0, -8]})
key(cam, "location", 0, (0, -D0, 0)); key(cam, "location", F_CARD, (0, -D1, 0))
# beats "phone_x": the phone off-centre during the demo (the act words get the wider panel)
key(phone, "location", 0, (float(BEATS.get("phone_x", 0.0)), 0, 0)); key(phone, "rotation_euler", 0, (0, 0, 0))
key(phone, "location", F_CARD, tuple(CP["loc"])); key(phone, "rotation_euler", F_CARD, tuple(rad(a) for a in CP["rot"]))
for idb in (cam, phone):
    interp(idb, "CONSTANT")
if LABEL:                                       # parented to the camera so it stays in a screen corner
    lb = text("label", LABEL, LABEL_FONT, 0.032, mat_emit("label_m", "#FFFFFF", 0.75)[0], (0, 0, 0), align="LEFT")
    lb.parent = cam
    lb.location, lb.rotation_euler = (-0.6, -0.43, -2.0), (0, 0, 0)

# ── compositor: soft bloom, warm vignette, golden light leak drifting in the top-left corner ──
tree = bpy.data.node_groups.new("promo_comp", "CompositorNodeTree")
tree.interface.new_socket("Image", in_out="OUTPUT", socket_type="NodeSocketColor")
sc.compositing_node_group = tree
T, TL = tree.nodes, tree.links
rl = T.new("CompositorNodeRLayers"); rl.scene = sc
gl = T.new("CompositorNodeGlare")
gl.inputs["Type"].default_value = "Bloom"
gl.inputs["Threshold"].default_value = 0.92
gl.inputs["Size"].default_value = 0.6
gl.inputs["Strength"].default_value = 0.18
TL.new(rl.outputs["Image"], gl.inputs["Image"])
vg = T.new("CompositorNodeEllipseMask")
vg.inputs["Mask"].default_value = 0.78; vg.inputs["Value"].default_value = 0.22
vg.inputs["Size"].default_value = (1.1, 1.05)
try:
    vg.inputs["Operation"].default_value = "Add"
except TypeError as ex:
    print("ellipse op", ex)
vb = T.new("CompositorNodeBlur"); vb.inputs["Size"].default_value = (300 * PCT / 100, 300 * PCT / 100)
TL.new(vg.outputs[0], vb.inputs["Image"])
vt = T.new("ShaderNodeMix"); vt.data_type = "RGBA"; vt.blend_type = "MIX"; vt.inputs["Factor"].default_value = 1.0
sock_in(vt, "A", "RGBA").default_value = hexc(BEATS.get("vignette", "#d9a37c"))   # vignette tinted warm, not grey
TL.new(vb.outputs["Image"], vt.inputs["Factor"])
sock_in(vt, "B", "RGBA").default_value = (1, 1, 1, 1)
mul = T.new("ShaderNodeMix"); mul.data_type = "RGBA"; mul.blend_type = "MULTIPLY"; mul.inputs["Factor"].default_value = 1.0
TL.new(gl.outputs["Image"], sock_in(mul, "A", "RGBA")); TL.new(sock_out(vt, "RGBA"), sock_in(mul, "B", "RGBA"))
lk = T.new("CompositorNodeEllipseMask")
lk.inputs["Mask"].default_value = 0.0; lk.inputs["Value"].default_value = 1.0
lk.inputs["Size"].default_value = (0.6, 0.45); lk.inputs["Rotation"].default_value = rad(-30)
try:
    lk.inputs["Operation"].default_value = "Add"
except TypeError:
    pass
for f, p in ((0, (-0.04, 1.04)), (NF, (0.22, 1.08))):
    key_sock(lk.inputs["Position"], f, p)
lb_ = T.new("CompositorNodeBlur"); lb_.inputs["Size"].default_value = (320 * PCT / 100, 320 * PCT / 100)
TL.new(lk.outputs[0], lb_.inputs["Image"])
lc = T.new("ShaderNodeMix"); lc.data_type = "RGBA"; lc.blend_type = "MULTIPLY"; lc.inputs["Factor"].default_value = 1.0
sock_in(lc, "A", "RGBA").default_value = hexc(BEATS.get("leak", "#ffc773"))
TL.new(lb_.outputs["Image"], sock_in(lc, "B", "RGBA"))
scr = T.new("ShaderNodeMix"); scr.data_type = "RGBA"; scr.blend_type = "SCREEN"
TL.new(sock_out(mul, "RGBA"), sock_in(scr, "A", "RGBA")); TL.new(sock_out(lc, "RGBA"), sock_in(scr, "B", "RGBA"))
for f, s in ((0, 0.12), (F_CARD // 2, 0.16), (F_CARD, 0.12), (NF, 0.14)):
    key_sock(scr.inputs["Factor"], f, s)
go = T.new("NodeGroupOutput")
TL.new(sock_out(scr, "RGBA"), go.inputs[0])

os.makedirs(OUT, exist_ok=True)
sc.render.image_settings.file_format = "PNG"
print(f"PROMO beats {os.path.basename(BEATS_PATH)} | dur {DUR:.2f}s ({NF} frames), app {APP0}..{APP_END} "
      f"(recording {FILM0 + APP0:.3f}s..{FILM0 + APP_END:.3f}s), end card @ {C_CARD:.2f}s, title font {TITLE_FONT and TITLE_FONT.name}")
STILLS = arg("--stills", "")
if STILLS:                                     # quick look at a few moments (seconds in the promo clip)
    for sec in (float(x) for x in STILLS.split(",")):
        sc.frame_set(FR(sec))
        sc.render.filepath = os.path.join(OUT, f"still_{sec:06.3f}.png")
        bpy.ops.render.render(write_still=True)
    sys.exit(0)
RANGE = arg("--range", "")                     # "a,b": render only frames a..b (parallel rendering across processes)
if RANGE:
    sc.frame_start, sc.frame_end = (int(x) for x in RANGE.split(","))
if os.environ.get("PROMO_FAST") == "1":
    sc.eevee.taa_render_samples = 8
sc.render.filepath = os.path.join(OUT, "####")
print("PROMO frames", sc.frame_end - sc.frame_start + 1)
bpy.ops.render.render(animation=True)
print("PROMO DONE", OUT)
