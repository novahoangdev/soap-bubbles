# Builds the backlit golden-hour garden in code and saves blender/garden.blend.
#   - physical sky (multiple scattering) with the sun low (~7 deg) in front of the camera, upper-left in frame, glowing through tree canopies
#   - layered foliage cards (Codex textures, alpha-keyed): near branches (~3 m), a clipped hedge (~9 m), trees (18-70 m) all around
#     (the 360 deg ring of trees is for the env map), translucent leaves that glow yellow-green when backlit
#   - cosmos / daisy clumps, lawn, emissive glints for bokeh (optional haze volume, off by default: the glow is added in post)
#   - the bubble wand (pink torus ring facing the camera exactly + mint handle), in focus at FOCUS_D, light-linked fill so it reads in the shade
#   - portrait camera 1320x2868 (iPhone 17 Pro Max, 440x956 pt @3x), 85 mm, shallow DOF focused on the wand plane
#   - a panoramic camera at the bubble position for env.jpg
# Units are metres. The camera sits at (0, 0, CAM_H), level, looking along +y; x is right, z is up.
# Layout data used by render_passes.py is stored in scene["sb"].
#
# Looks: SB_LOOK=golden (default, the garden above, saved to blender/garden.blend) or SB_LOOK=night (the same garden at
# blue hour with fairy lights, built on top of it by night_look.py and saved to blender/garden_night.blend).
#
# Run: [SB_LOOK=night] Blender -b --factory-startup -P blender/scripts/build_scene.py
import bpy, math, os, random
from mathutils import Vector, Matrix

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
TEX = os.path.join(ROOT, "blender", "textures")
LOOK = os.environ.get("SB_LOOK", "golden")
BLEND = os.environ.get("SB_BLEND", os.path.join(ROOT, "blender", "garden.blend" if LOOK == "golden" else f"garden_{LOOK}.blend"))
rng = random.Random(11)
rad = math.radians

# ── camera / frame ──
SCREEN_PX = (1320, 2868)
VIEW_PT = (440, 956)
CAM_H = 1.0
LENS = 85.0
SENSOR_H = 36.0                                    # vertical sensor fit: 85 mm on the long side of a full-frame sensor
SENSOR_W = SENSOR_H * SCREEN_PX[0] / SCREEN_PX[1]
TAN_HX = SENSOR_W / 2 / LENS                       # tan(half horizontal fov)
TAN_HY = SENSOR_H / 2 / LENS
FOCUS_D = 1.2                                      # focus plane = wand plane (the app's bubbles live here)
FSTOP = float(os.environ.get("SB_FSTOP", "2.0"))

# ── sun: elevation above the horizon, azimuth from +y towards +x (negative = left in frame) ──
SUN_EL, SUN_AZ = 7.0, -2.0
SUN_DIR = Vector((math.sin(rad(SUN_AZ)) * math.cos(rad(SUN_EL)), math.cos(rad(SUN_AZ)) * math.cos(rad(SUN_EL)), math.sin(rad(SUN_EL))))
SKY_STRENGTH = float(os.environ.get("SB_SKY", "0.16"))

# ── wand: ring centre at (50 %, 80 %) of the frame, inner radius 70 pt ──
RING_UV = (0.5, 0.80)
M_PER_PT = 2 * FOCUS_D * TAN_HX / VIEW_PT[0]       # metres per pt on the focus plane
RING_RIN = 70 * M_PER_PT
RING_TUBE = 8.5 * M_PER_PT                         # tube radius
RING_RMAJ = RING_RIN + RING_TUBE
RING_C = Vector(((RING_UV[0] - 0.5) * 2 * FOCUS_D * TAN_HX, FOCUS_D, CAM_H + (0.5 - RING_UV[1]) * 2 * FOCUS_D * TAN_HY))
BUBBLE_POS = Vector((0.0, FOCUS_D, CAM_H + 0.12))  # env map viewpoint

HEDGE_Y, HEDGE_H = 9.0, 1.15

bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene


def hexc(h, a=1.0):
    h = h.lstrip("#")
    lin = lambda c: c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    return tuple(lin(int(h[i:i + 2], 16) / 255) for i in (0, 2, 4)) + (a,)


def coll(name, parent=None):
    c = bpy.data.collections.new(name)
    (parent or sc.collection).children.link(c)
    return c


def obj(name, data, c=None):
    ob = bpy.data.objects.new(name, data)
    (c or sc.collection).objects.link(ob)
    return ob


def img(name, colorspace="sRGB"):
    im = bpy.data.images.load(os.path.join(TEX, name), check_existing=True)
    im.colorspace_settings.name = colorspace
    return im


class M:
    """Tiny node-building helper."""

    def __init__(self, name):
        self.m = bpy.data.materials.new(name)
        self.nt = self.m.node_tree
        self.n = self.nt.nodes
        self.bsdf = next(n for n in self.n if n.type == "BSDF_PRINCIPLED")
        self.out = next(n for n in self.n if n.type == "OUTPUT_MATERIAL")

    def node(self, t, **kw):
        nd = self.n.new(t)
        for k, v in kw.items():
            if k in nd.inputs:
                nd.inputs[k].default_value = v
            else:
                setattr(nd, k, v)
        return nd

    def link(self, a, b):
        self.nt.links.new(a, b)

    def set(self, sock, x):
        if isinstance(x, (int, float, tuple)):
            sock.default_value = x
        else:
            self.link(x, sock)

    def math(self, op, a, b=None, c=None):
        n = self.node("ShaderNodeMath", operation=op)
        for i, x in enumerate((a, b, c)):
            if x is not None:
                self.set(n.inputs[i], x)
        return n.outputs[0]

    def mix(self, fac, a, b, blend="MIX"):
        n = self.node("ShaderNodeMix", data_type="RGBA", blend_type=blend)
        ins = [s for s in n.inputs if s.type == "RGBA"]
        self.set(n.inputs["Factor"], fac)
        self.set(ins[0], a)
        self.set(ins[1], b)
        return [s for s in n.outputs if s.type == "RGBA"][0]

    def mixsh(self, fac, a, b):
        n = self.node("ShaderNodeMixShader")
        self.set(n.inputs[0], fac)
        self.link(a, n.inputs[1])
        self.link(b, n.inputs[2])
        return n.outputs[0]

    def ramp(self, fac, stops):
        r = self.node("ShaderNodeValToRGB")
        el = r.color_ramp.elements
        for i, (p, c) in enumerate(stops):
            e = el[i] if i < len(el) else el.new(p)
            e.position, e.color = p, c
        self.link(fac, r.inputs["Fac"])
        return r.outputs["Color"]

    def noise(self, scale, detail=3.0, vec=None):
        n = self.node("ShaderNodeTexNoise", **{"Scale": scale, "Detail": detail})
        if vec is not None:
            self.link(vec, n.inputs["Vector"])
        return n

    def coords(self, kind="Object", scale=(1, 1, 1)):
        tc = self.node("ShaderNodeTexCoord")
        mp = self.node("ShaderNodeMapping")
        mp.inputs["Scale"].default_value = scale
        self.link(tc.outputs[kind], mp.inputs["Vector"])
        return mp.outputs["Vector"]

    def tex(self, image, vec=None, colorspace="sRGB", ext="REPEAT"):
        t = self.node("ShaderNodeTexImage")
        t.image = img(image, colorspace)
        t.extension = ext
        if vec is not None:
            self.link(vec, t.inputs["Vector"])
        return t

    def to_out(self, shader):
        self.link(shader, self.out.inputs["Surface"])


# ───────────────────────── render settings ─────────────────────────
r = sc.render
r.engine = "CYCLES"
r.resolution_x, r.resolution_y = SCREEN_PX
r.resolution_percentage = 100
cy = sc.cycles
try:
    prefs = bpy.context.preferences.addons["cycles"].preferences
    prefs.compute_device_type = "METAL"
    prefs.get_devices()
    for d in prefs.devices:
        d.use = d.type == "METAL"
    cy.device = "GPU"
except Exception as e:  # noqa: BLE001
    print("GPU setup failed:", e)
cy.samples = 128
cy.use_adaptive_sampling = True
cy.adaptive_threshold = 0.02
cy.use_denoising = True
cy.max_bounces = 8
cy.diffuse_bounces = 3
cy.glossy_bounces = 3
cy.transmission_bounces = 6
cy.volume_bounces = 0
cy.transparent_max_bounces = 48
cy.sample_clamp_indirect = 6.0
cy.blur_glossy = 1.0
cy.caustics_reflective = False
cy.caustics_refractive = False
cy.volume_step_rate = 4.0
for vt, look in (("AgX", "AgX - Medium High Contrast"), ("AgX", "None"), ("Filmic", "Medium High Contrast")):
    try:
        sc.view_settings.view_transform = vt
        sc.view_settings.look = look
        break
    except TypeError:
        continue
sc.view_settings.exposure = float(os.environ.get("SB_EXPOSURE", "0.8"))
if hasattr(sc.view_settings, "use_white_balance"):           # Blender >= 4.3: warm golden-hour grade
    sc.view_settings.use_white_balance = True
    sc.view_settings.white_balance_temperature = float(os.environ.get("SB_WB", "7000"))

# ───────────────────────── world: physical sky ─────────────────────────
world = bpy.data.worlds.new("sky")
sc.world = world
wn = world.node_tree
bg = next(n for n in wn.nodes if n.type == "BACKGROUND")
sky = wn.nodes.new("ShaderNodeTexSky")
sky.sky_type = "MULTIPLE_SCATTERING"
sky.sun_disc = True
sky.sun_size = rad(0.6)
sky.sun_intensity = float(os.environ.get("SB_SUN", "0.35"))
sky.sun_elevation = rad(SUN_EL)
sky.sun_rotation = rad(SUN_AZ)                    # verified: sun dir = (sin rot * cos el, cos rot * cos el, sin el)
sky.altitude = 50.0
sky.air_density = 1.2
sky.aerosol_density = 1.5                          # hazy summer evening: warmer, softer sun
# warm the sky a little (golden hour grade) and keep the sun bright
grade = wn.nodes.new("ShaderNodeMix")
grade.data_type = "RGBA"
grade.blend_type = "MULTIPLY"
grade.inputs["Factor"].default_value = 1.0
ins = [s for s in grade.inputs if s.type == "RGBA"]
wn.links.new(sky.outputs[0], ins[0])
ins[1].default_value = (1.0, 0.86, 0.62, 1)
# camera rays see a copy of the sky with a dimmer sun disc: the defocused sun stays a hot glow without
# fireflies (a near-point light through f/2 DOF is the noisiest thing Cycles can sample); lighting keeps the full sun
sky_cam = wn.nodes.new("ShaderNodeTexSky")
for prop in ("sky_type", "sun_disc", "sun_size", "sun_elevation", "sun_rotation", "altitude", "air_density", "aerosol_density"):
    setattr(sky_cam, prop, getattr(sky, prop))
sky_cam.sun_intensity = float(os.environ.get("SB_SUN_CAM", "0.35"))
lp = wn.nodes.new("ShaderNodeLightPath")
pick = wn.nodes.new("ShaderNodeMix")
pick.data_type = "RGBA"
pins = [s for s in pick.inputs if s.type == "RGBA"]
wn.links.new(lp.outputs["Is Camera Ray"], pick.inputs["Factor"])
wn.links.new(sky.outputs[0], pins[0])
# soft-clip what the camera sees of the sky: c / (1 + c / K). The sky right around the sun is thousands of times brighter
# than the leaves, so every lens sample that slips between two leaves is a firefly; this keeps it blown but sampleable
K = float(os.environ.get("SB_SKY_CLIP", "400"))
vdiv = wn.nodes.new("ShaderNodeVectorMath"); vdiv.operation = "SCALE"
wn.links.new(sky_cam.outputs[0], vdiv.inputs[0]); vdiv.inputs["Scale"].default_value = 1.0 / K
vadd = wn.nodes.new("ShaderNodeVectorMath"); vadd.operation = "ADD"
wn.links.new(vdiv.outputs[0], vadd.inputs[0]); vadd.inputs[1].default_value = (1, 1, 1)
vq = wn.nodes.new("ShaderNodeVectorMath"); vq.operation = "DIVIDE"
wn.links.new(sky_cam.outputs[0], vq.inputs[0]); wn.links.new(vadd.outputs[0], vq.inputs[1])
wn.links.new(vq.outputs[0], pins[1])
wn.links.new([s for s in pick.outputs if s.type == "RGBA"][0], ins[0])
wn.links.new([s for s in grade.outputs if s.type == "RGBA"][0], bg.inputs["Color"])
bg.inputs["Strength"].default_value = SKY_STRENGTH

# ───────────────────────── collections ─────────────────────────
C_GARDEN = coll("garden")
C_WAND = coll("wand")
C_FX = coll("fx")

# ───────────────────────── materials ─────────────────────────


def leaf_mat(name, image, value=1.0, trans=1.0, warm=1.0):
    """Alpha card: waxy diffuse + strong translucency (backlit glow), per-object random hue/value jitter."""
    m = M(name)
    t = m.tex(image, ext="CLIP")
    info = m.node("ShaderNodeObjectInfo")
    jit = m.math("MULTIPLY_ADD", info.outputs["Random"], 0.5, value * 0.75)          # value 0.75..1.25 x value
    hsv = m.node("ShaderNodeHueSaturation")
    m.link(t.outputs["Color"], hsv.inputs["Color"])
    hue = m.math("MULTIPLY_ADD", info.outputs["Random"], 0.05, 0.475)                 # hue jitter +-0.025
    m.link(hue, hsv.inputs["Hue"])
    m.link(jit, hsv.inputs["Value"])
    col = hsv.outputs["Color"]
    b = m.bsdf
    m.link(col, b.inputs["Base Color"])
    b.inputs["Roughness"].default_value = 0.42
    b.inputs["Specular IOR Level"].default_value = 0.35
    b.inputs["Sheen Weight"].default_value = 0.15
    tl = m.node("ShaderNodeBsdfTranslucent")
    tcol = m.mix(1.0, col, (1.25 * warm, 1.18, 0.38, 1), blend="MULTIPLY")
    m.link(tcol, tl.inputs["Color"])
    sh = m.mixsh(0.55 * trans, b.outputs[0], tl.outputs[0])
    tr = m.node("ShaderNodeBsdfTransparent")
    a = m.math("POWER", t.outputs["Alpha"], 1.5)
    m.to_out(m.mixsh(a, tr.outputs[0], sh))
    return m.m


def flower_mat(name, image):
    m = M(name)
    t = m.tex(image, ext="CLIP")
    b = m.bsdf
    m.link(t.outputs["Color"], b.inputs["Base Color"])
    b.inputs["Roughness"].default_value = 0.5
    b.inputs["Specular IOR Level"].default_value = 0.25
    b.inputs["Sheen Weight"].default_value = 0.3
    tl = m.node("ShaderNodeBsdfTranslucent")
    tcol = m.mix(1.0, t.outputs["Color"], (1.1, 0.95, 0.75, 1), blend="MULTIPLY")
    m.link(tcol, tl.inputs["Color"])
    sh = m.mixsh(0.45, b.outputs[0], tl.outputs[0])
    tr = m.node("ShaderNodeBsdfTransparent")
    m.to_out(m.mixsh(t.outputs["Alpha"], tr.outputs[0], sh))
    return m.m


def lawn_mat():
    m = M("lawn")
    v = m.coords("Object", (1 / 0.9, 1 / 0.9, 1))
    t = m.tex("grass_tile.jpg", v)
    big = m.noise(0.15, 3.0)
    var = m.ramp(big.outputs["Fac"], [(0.3, (0.55, 0.62, 0.35, 1)), (0.7, (1.05, 1.0, 0.75, 1))])
    col = m.mix(1.0, t.outputs["Color"], var, blend="MULTIPLY")
    col = m.mix(1.0, col, (0.62, 0.6, 0.26, 1), blend="MULTIPLY")
    b = m.bsdf
    m.link(col, b.inputs["Base Color"])
    b.inputs["Roughness"].default_value = 0.6
    b.inputs["Specular IOR Level"].default_value = 0.4
    b.inputs["Sheen Weight"].default_value = 0.6
    b.inputs["Sheen Tint"].default_value = (0.9, 1.0, 0.5, 1)
    bump = m.node("ShaderNodeBump", Strength=0.6, Distance=0.01)
    m.link(t.outputs["Color"], bump.inputs["Height"])
    m.link(bump.outputs[0], b.inputs["Normal"])
    return m.m


def hedge_mat():
    m = M("hedge")
    v = m.coords("Object", (1 / 0.8, 1 / 0.8, 1 / 0.8))
    tc = m.node("ShaderNodeTexImage")
    tc.image = img("hedge_tile.jpg")
    tc.projection = "BOX"
    tc.projection_blend = 0.3
    m.link(v, tc.inputs["Vector"])
    big = m.noise(0.6, 4.0)
    var = m.ramp(big.outputs["Fac"], [(0.35, (0.6, 0.62, 0.45, 1)), (0.65, (1.0, 1.0, 0.8, 1))])
    col = m.mix(1.0, tc.outputs["Color"], var, blend="MULTIPLY")
    b = m.bsdf
    m.link(col, b.inputs["Base Color"])
    b.inputs["Roughness"].default_value = 0.45
    b.inputs["Specular IOR Level"].default_value = 0.4
    bump = m.node("ShaderNodeBump", Strength=0.9, Distance=0.03)
    m.link(tc.outputs["Color"], bump.inputs["Height"])
    m.link(bump.outputs[0], b.inputs["Normal"])
    tl = m.node("ShaderNodeBsdfTranslucent")
    m.link(m.mix(1.0, col, (1.2, 1.1, 0.4, 1), blend="MULTIPLY"), tl.inputs["Color"])
    m.to_out(m.mixsh(0.25, b.outputs[0], tl.outputs[0]))
    return m.m


def bark_mat():
    m = M("bark")
    n = m.noise(8.0, 6.0, m.coords("Object", (1, 1, 0.2)))
    col = m.ramp(n.outputs["Fac"], [(0.3, hexc("#1e1a14")), (0.7, hexc("#4a4034"))])
    m.link(col, m.bsdf.inputs["Base Color"])
    m.bsdf.inputs["Roughness"].default_value = 0.85
    return m.m


def emit_mat(name, color, strength):
    m = M(name)
    e = m.node("ShaderNodeEmission")
    e.inputs["Color"].default_value = color
    e.inputs["Strength"].default_value = strength
    m.to_out(e.outputs[0])
    return m.m


def plastic_mat(name, base, sss_col, ridges=0):
    """Glossy pastel plastic, slightly worn (roughness varies), wet clear coat; optional moulded ridges around a ring
    (bands across the tube, `ridges` of them around the object's local z axis)."""
    m = M(name)
    b = m.bsdf
    b.inputs["Base Color"].default_value = base
    n = m.noise(140.0, 4.0, m.coords("Object"))
    worn = m.node("ShaderNodeMapRange", **{"From Min": 0.35, "From Max": 0.75, "To Min": 0.16, "To Max": 0.42})
    m.link(n.outputs["Fac"], worn.inputs["Value"])
    m.link(worn.outputs[0], b.inputs["Roughness"])
    b.inputs["Specular IOR Level"].default_value = 0.6
    b.inputs["Subsurface Weight"].default_value = 0.35
    b.inputs["Subsurface Radius"].default_value = sss_col
    b.inputs["Subsurface Scale"].default_value = 0.004
    b.inputs["Coat Weight"].default_value = 0.85
    b.inputs["Coat Roughness"].default_value = 0.03
    b.inputs["Coat IOR"].default_value = 1.5
    fine = m.noise(900.0, 2.0, m.coords("Object"))
    bump = m.node("ShaderNodeBump", Strength=0.08, Distance=0.0003)
    m.link(fine.outputs["Fac"], bump.inputs["Height"])
    nrm = bump.outputs[0]
    if ridges:
        grad = m.node("ShaderNodeTexGradient", gradient_type="RADIAL")
        m.link(m.coords("Object"), grad.inputs["Vector"])
        wave = m.math("SINE", m.math("MULTIPLY", grad.outputs["Fac"], 2 * math.pi * ridges))
        soft = m.math("POWER", m.math("ABSOLUTE", wave), 0.6)
        rb = m.node("ShaderNodeBump", Strength=0.2, Distance=0.0005)
        m.link(soft, rb.inputs["Height"])
        m.link(nrm, rb.inputs["Normal"])
        nrm = rb.outputs[0]
    m.link(nrm, b.inputs["Normal"])
    m.link(nrm, b.inputs["Coat Normal"])
    return m.m


def water_mat():
    m = M("water")
    g = m.node("ShaderNodeBsdfGlass", IOR=1.33, Roughness=0.0)
    g.inputs["Color"].default_value = (1, 1, 1, 1)
    m.to_out(g.outputs[0])
    return m.m


MAT = {
    "maple": leaf_mat("leaf_maple", "leaves_maple.png"),
    "linden": leaf_mat("leaf_linden", "leaves_linden.png"),
    "maple_dark": leaf_mat("leaf_maple_dark", "leaves_maple.png", value=0.45, trans=0.8),
    "linden_dark": leaf_mat("leaf_linden_dark", "leaves_linden.png", value=0.4, trans=0.8),
    "hedgeleaf": leaf_mat("leaf_hedge", "leaves_linden.png", value=0.35, trans=0.7),
    "flowers": flower_mat("flowers", "flowers_cosmos.png"),
}

# ───────────────────────── card meshes ─────────────────────────


def card_mesh(name, mat, w=1.0, h=1.0, pivot_bottom=False):
    me = bpy.data.meshes.new(name)
    z0 = 0.0 if pivot_bottom else -h / 2
    me.from_pydata([(-w / 2, z0, 0), (w / 2, z0, 0), (w / 2, z0 + h, 0), (-w / 2, z0 + h, 0)], [], [(0, 1, 2, 3)])
    uv = me.uv_layers.new()
    for i, c in enumerate(((0, 0), (1, 0), (1, 1), (0, 1))):
        uv.data[i].uv = c
    me.materials.append(mat)
    return me


CARDS = {k: card_mesh("card_" + k, MAT[k]) for k in ("maple", "linden", "maple_dark", "linden_dark", "hedgeleaf")}
FLOWER_CARD = card_mesh("card_flowers", MAT["flowers"], pivot_bottom=True)


def look_rot(normal, spin=0.0):
    """Rotation matrix that maps the card's +z normal to `normal` and its +y up roughly to world up, plus a spin about the normal."""
    n = Vector(normal).normalized()
    up = Vector((0, 0, 1))
    if abs(n.dot(up)) > 0.97:
        up = Vector((0, 1, 0))
    x = up.cross(n).normalized()
    y = n.cross(x)
    m = Matrix((x, y, n)).transposed()
    return m @ Matrix.Rotation(spin, 3, "Z")


def place(name, mesh, loc, rot3, scale, c):
    ob = obj(name, mesh, c)
    ob.matrix_world = Matrix.Translation(loc) @ rot3.to_4x4() @ Matrix.Diagonal((scale, scale, scale, 1))
    return ob


def toward_cam(p, jitter=0.6):
    """Card normal pointing roughly at the camera / env viewpoint, with random tilt."""
    d = (Vector((0, 0.6, CAM_H)) - Vector(p)).normalized()
    d += Vector((rng.uniform(-1, 1), rng.uniform(-1, 1), rng.uniform(-1, 1))) * jitter
    return d.normalized()


SUN_EYE = Vector((0, 0, CAM_H))


def sun_blocked(loc, s, clear_deg=0.9):
    """True when a card of size s at loc would cover the sun disc (keeps a small clear window around the sun, leaf edges may overlap)."""
    v = loc - SUN_EYE
    t = v.dot(SUN_DIR)
    if t <= 0:
        return False
    perp = (v - SUN_DIR * t).length
    return perp < s * 0.32 + t * math.tan(rad(clear_deg))


def canopy(name, centre, radii, n, size, kinds, c=C_GARDEN, jitter=0.7, hollow=0.0):
    cx, cy, cz = centre
    for i in range(n):
        while True:
            p = Vector((rng.uniform(-1, 1), rng.uniform(-1, 1), rng.uniform(-1, 1)))
            if hollow <= p.length <= 1.0:
                break
        loc = Vector((cx + p.x * radii[0], cy + p.y * radii[1], cz + p.z * radii[2]))
        k = rng.choice(kinds)
        s = rng.uniform(*size)
        if sun_blocked(loc, s):
            continue
        place(f"{name}_{i}", CARDS[k], loc, look_rot(toward_cam(loc, jitter), rng.uniform(-math.pi, math.pi)), s, c)


def trunk(name, x, y, h, r0, lean=(0, 0)):
    bpy.ops.mesh.primitive_cone_add(vertices=16, radius1=r0, radius2=r0 * 0.55, depth=h, location=(x + lean[0] * h / 2, y + lean[1] * h / 2, h / 2))
    ob = bpy.context.object
    ob.name = name
    ob.rotation_euler = (math.atan2(lean[1], 1) * -1, math.atan2(lean[0], 1), 0)
    ob.data.materials.append(MAT_BARK)
    for cl in ob.users_collection:
        cl.objects.unlink(ob)
    C_GARDEN.objects.link(ob)
    bpy.ops.object.shade_smooth()
    return ob


MAT_BARK = bark_mat()

# ───────────────────────── ground ─────────────────────────
bpy.ops.mesh.primitive_plane_add(size=400, location=(0, 0, 0))
lawn = bpy.context.object
lawn.name = "lawn"
lawn.data.materials.append(lawn_mat())
for cl in lawn.users_collection:
    cl.objects.unlink(lawn)
C_GARDEN.objects.link(lawn)

# ───────────────────────── hedge ─────────────────────────
bpy.ops.mesh.primitive_cube_add(size=1, location=(0, HEDGE_Y + 0.6, HEDGE_H / 2))
hedge = bpy.context.object
hedge.name = "hedge"
hedge.scale = (26, 1.2, HEDGE_H)
bpy.ops.object.transform_apply(scale=True)
bev = hedge.modifiers.new("bevel", "BEVEL")
bev.width = 0.25
bev.segments = 4
sub = hedge.modifiers.new("sub", "SUBSURF")
sub.levels = sub.render_levels = 2
disp_tex = bpy.data.textures.new("hedge_lumps", "CLOUDS")
disp_tex.noise_scale = 0.45
disp = hedge.modifiers.new("lumps", "DISPLACE")
disp.texture = disp_tex
disp.strength = 0.16
disp.mid_level = 0.5
hedge.data.materials.append(hedge_mat())
for cl in hedge.users_collection:
    cl.objects.unlink(hedge)
C_GARDEN.objects.link(hedge)
bpy.ops.object.shade_smooth()
# ragged backlit leaves along the hedge top + a few on the front face
for i in range(260):
    x = rng.uniform(-6.0, 6.0)
    on_top = rng.random() < 0.75
    loc = Vector((x, HEDGE_Y + rng.uniform(0.0, 1.0), HEDGE_H + rng.uniform(-0.12, 0.12))) if on_top else \
        Vector((x, HEDGE_Y - 0.05, rng.uniform(0.15, HEDGE_H - 0.1)))
    nrm = Vector((rng.uniform(-0.6, 0.6), -1.0, rng.uniform(-0.2, 0.9) if on_top else rng.uniform(-0.3, 0.3)))
    place(f"hedgeleaf_{i}", CARDS["hedgeleaf"], loc, look_rot(nrm, rng.uniform(-math.pi, math.pi)), rng.uniform(0.35, 0.6), C_GARDEN)

# ───────────────────────── trees ─────────────────────────
# hero tree in front of the sun (left of centre); the sun glows through its gaps
trunk("trunk_hero", -1.9, 22.0, 6.0, 0.28, lean=(0.05, 0))
canopy("hero", (-2.4, 22.0, 6.6), (3.0, 2.2, 2.4), 120, (1.2, 2.0), ["maple", "maple", "linden_dark"], hollow=0.35)
canopy("hero_low", (-1.5, 20.5, 3.9), (1.1, 0.8, 0.6), 14, (0.8, 1.2), ["maple", "linden"], hollow=0.1)
# a loose screen of leaves at ~14 m right in front of the sun: the bright sky breaks into bokeh discs between the leaves
canopy("screen", (-0.4, 14.0, 3.0), (1.9, 1.4, 1.4), 46, (0.7, 1.1), ["maple", "linden", "maple"], jitter=0.5)
# right tree, further, darker
trunk("trunk_right", 3.2, 30.0, 7.0, 0.34)
canopy("right", (2.6, 30.0, 6.2), (3.6, 2.6, 3.6), 170, (1.5, 2.4), ["linden", "linden_dark", "maple_dark"], hollow=0.3)
# distant tree line (sunlit tops behind the hedge)
for i in range(26):
    x = -40 + i * 3.2 + rng.uniform(-1, 1)
    y = rng.uniform(52, 72)
    canopy(f"far{i}", (x, y, rng.uniform(2.6, 3.6)), (3.0, 2.0, rng.uniform(1.4, 2.0)), 30, (2.0, 3.0),
           ["linden_dark", "maple_dark", "linden"], jitter=0.5, hollow=0.3)
# a ring of trees all around (mostly for the env map; behind the camera they are front-lit)
for i in range(16):
    a = rad(i * 22.5 + rng.uniform(-6, 6))
    if abs(math.degrees(a) % 360) < 25 or abs(math.degrees(a) % 360) > 335:
        continue                                          # the frame direction is handled above
    d = rng.uniform(16, 28)
    x, y = math.sin(a) * d, math.cos(a) * d
    hgt = rng.uniform(5, 8)
    trunk(f"trunk_ring{i}", x, y, hgt * 0.6, 0.35)
    canopy(f"ring{i}", (x, y, hgt), (4.5, 4.5, 3.6), 120, (1.8, 2.8), ["maple", "linden", "linden_dark", "maple_dark"], hollow=0.3)

# near branches (blurred framing, upper corners, ~2.5-3.5 m)
for i, (cx, cy, cz, n) in enumerate(((-0.42, 3.2, 1.62, 9), (0.40, 2.8, 1.58, 8), (-0.30, 4.5, 1.92, 7))):
    canopy(f"near{i}", (cx, cy, cz), (0.22, 0.25, 0.14), n, (0.42, 0.62), ["maple", "linden", "maple_dark"], jitter=0.4)

# ───────────────────────── flowers ─────────────────────────


def flower(i, x, y, s, c=C_GARDEN):
    n = Vector((rng.uniform(-0.25, 0.25), -1, 0)).normalized()
    ob = place(f"flowers_{i}", FLOWER_CARD, Vector((x, y, -0.02)), look_rot(n, 0), s, c)
    ob.matrix_world = ob.matrix_world @ Matrix.Rotation(rad(rng.uniform(-6, 6)), 4, "Z")


k = 0
for i in range(7):                                         # border along the hedge, mostly at the sides
    flower(k, rng.choice((-1, 1)) * rng.uniform(0.45, 1.6), rng.uniform(7.6, 8.8), rng.uniform(0.6, 0.95)); k += 1
for x, y, s in ((0.52, 3.9, 0.85), (-0.78, 4.8, 0.8)):
    flower(k, x, y, s); k += 1
for i in range(14):                                        # behind the camera / sides, for the env map
    a = rad(rng.uniform(45, 315))                          # never in front of the main camera
    d = rng.uniform(3, 7)
    flower(k, math.sin(a) * d, math.cos(a) * d, rng.uniform(0.6, 0.9)); k += 1

# ───────────────────────── glints / bokeh points ─────────────────────────
GLINTS = [hexc("#ffb85c"), hexc("#ff9e4a"), hexc("#ffd08a"), hexc("#ff9f7a"), hexc("#ffe2b0"), hexc("#bcdcff")]
gl_mats = [emit_mat(f"glint{i}", c, 1.0) for i, c in enumerate(GLINTS)]
bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2, radius=1.0)
gl_mesh = bpy.context.object.data
bpy.data.objects.remove(bpy.context.object)
for i in range(44):
    y = rng.uniform(12, 32)
    x = rng.uniform(-1.4, 1.4) * y * TAN_HX + y * math.tan(rad(SUN_AZ)) * 0.4
    z = CAM_H + rng.uniform(-0.05, 1.2) * y * TAN_HY
    ci = 5 if rng.random() < 0.15 else rng.randrange(5)
    m = gl_mats[ci].copy()
    e = next(n for n in m.node_tree.nodes if n.type == "EMISSION")
    # brighter close to the sun direction
    ang = math.degrees(Vector((x, y, z - CAM_H)).normalized().angle(SUN_DIR))
    e.inputs["Strength"].default_value = rng.uniform(5, 22) * (1.0 + 2.0 * math.exp(-ang / 4.0))
    me = gl_mesh.copy()
    me.materials.append(m)
    ob = obj(f"glint_{i}", me, C_FX)
    ob.location = (x, y, z)
    ob.scale = (rng.uniform(0.02, 0.05),) * 3
    ob.visible_shadow = False
    ob.visible_diffuse = False
    ob.visible_glossy = False

for i in range(14):
    x = rng.uniform(-0.9, 0.9)
    m = gl_mats[rng.randrange(5)].copy()
    next(n for n in m.node_tree.nodes if n.type == "EMISSION").inputs["Strength"].default_value = rng.uniform(15, 40)
    me = gl_mesh.copy()
    me.materials.append(m)
    ob = obj(f"glint_hedge{i}", me, C_FX)
    ob.location = (x, HEDGE_Y + rng.uniform(0.1, 0.8), HEDGE_H + rng.uniform(0.0, 0.12))
    ob.scale = (rng.uniform(0.012, 0.022),) * 3
    ob.visible_shadow = ob.visible_diffuse = ob.visible_glossy = False

# ───────────────────────── haze volume (optional, off by default) ─────────────────────────
# A forward-scattering volume lit by the low sun makes lovely shafts, but through f/2 DOF it is very noisy; the golden veil
# is added noise-free in render_passes.py instead (display-space bloom + sun glow). SB_HAZE=0.006 turns the volume back on.
HAZE = float(os.environ.get("SB_HAZE", "0"))
if HAZE > 0:
    bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 45, 7))     # only beyond the hedge
    haze = bpy.context.object
    haze.name = "haze"
    haze.scale = (90, 70, 14)
    mh = M("haze")
    mh.n.remove(mh.bsdf)
    pv = mh.node("ShaderNodeVolumePrincipled")
    pv.inputs["Color"].default_value = hexc("#ffe2b8")
    pv.inputs["Density"].default_value = HAZE
    pv.inputs["Anisotropy"].default_value = 0.88
    mh.link(pv.outputs[0], mh.out.inputs["Volume"])
    haze.data.materials.append(mh.m)
    for cl in haze.users_collection:
        cl.objects.unlink(haze)
    C_FX.objects.link(haze)

# ───────────────────────── wand ─────────────────────────
PINK = plastic_mat("plastic_pink", hexc("#ff7fb6"), (1.0, 0.35, 0.5))
MINT = plastic_mat("plastic_mint", hexc("#8fe8c4"), (0.5, 1.0, 0.75))


def to_wand(ob):
    for cl in ob.users_collection:
        cl.objects.unlink(ob)
    C_WAND.objects.link(ob)
    bpy.ops.object.shade_smooth()
    return ob


bpy.ops.mesh.primitive_torus_add(major_radius=RING_RMAJ, minor_radius=RING_TUBE, major_segments=160, minor_segments=32,
                                 location=RING_C, rotation=(rad(90), 0, 0))
ring = to_wand(bpy.context.object)
ring.name = "wand_ring"
ring.data.materials.append(plastic_mat("plastic_pink_ring", hexc("#ff7fb6"), (1.0, 0.35, 0.5), ridges=44))
# neck joining the ring to the handle
neck_z = RING_C.z - RING_RMAJ - RING_TUBE * 0.6
bpy.ops.mesh.primitive_uv_sphere_add(segments=48, ring_count=24, radius=RING_TUBE * 1.55, location=(RING_C.x, RING_C.y, neck_z))
neck = to_wand(bpy.context.object)
neck.name = "wand_neck"
neck.scale = (1.0, 1.0, 1.35)
neck.data.materials.append(PINK)
# handle: slightly flattened mint rod going down out of frame
h_top = neck_z - RING_TUBE * 1.2
h_len = 0.5
bpy.ops.mesh.primitive_cylinder_add(vertices=48, radius=RING_TUBE * 1.25, depth=h_len, location=(RING_C.x, RING_C.y, h_top - h_len / 2))
handle = to_wand(bpy.context.object)
handle.name = "wand_handle"
handle.scale = (1.0, 0.8, 1.0)
handle.data.materials.append(MINT)
bv = handle.modifiers.new("bevel", "BEVEL")
bv.width = RING_TUBE * 0.6
bv.segments = 6
# collar between neck and handle
bpy.ops.mesh.primitive_torus_add(major_radius=RING_TUBE * 1.25, minor_radius=RING_TUBE * 0.35, major_segments=48, minor_segments=16,
                                 location=(RING_C.x, RING_C.y, h_top - RING_TUBE * 0.2))
collar = to_wand(bpy.context.object)
collar.name = "wand_collar"
collar.data.materials.append(MINT)
# fill light for the wand only (it sits in the backlit shade): soft warm key from camera-left, plus a cool kicker from the right
for name, loc, power, col, size in (("wand_fill", (-0.55, 0.35, 1.35), 14.0, (1.0, 0.88, 0.80), 0.7),
                                     ("wand_key", (-0.30, 0.55, 1.20), 4.0, (1.0, 0.95, 0.88), 0.05),
                                     ("wand_rim", (-0.10, 1.75, 1.25), 7.0, (1.0, 0.80, 0.50), 0.2),
                                     ("wand_kick", (0.45, 1.9, 1.15), 4.0, (1.0, 0.82, 0.55), 0.25)):
    ld = bpy.data.lights.new(name, "AREA")
    ld.energy = power
    ld.color = col
    ld.size = size
    lo = obj(name, ld, C_FX)
    lo.location = loc
    d = (RING_C - Vector(loc)).normalized()
    lo.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
    lo.light_linking.receiver_collection = C_WAND
    lo.light_linking.blocker_collection = C_WAND

# ───────────────────────── cameras ─────────────────────────
cd = bpy.data.cameras.new("cam")
cd.lens = LENS
cd.sensor_fit = "VERTICAL"
cd.sensor_height = SENSOR_H
cd.sensor_width = SENSOR_W
cd.clip_start = 0.05
cd.clip_end = 500
cd.dof.use_dof = True
cd.dof.focus_distance = FOCUS_D
cd.dof.aperture_fstop = FSTOP
cd.dof.aperture_blades = 0                          # round, creamy discs
cam = obj("cam", cd)
cam.location = (0, 0, CAM_H)
cam.rotation_euler = (rad(90), 0, 0)
sc.camera = cam

pd = bpy.data.cameras.new("env_cam")
pd.type = "PANO"
pd.panorama_type = "EQUIRECTANGULAR"
pd.clip_start = 0.02
pd.clip_end = 500
envcam = obj("env_cam", pd)
envcam.location = BUBBLE_POS
envcam.rotation_euler = (rad(90), 0, 0)             # same orientation as the main camera: u = 0.5 is the camera's forward (+y)

# other looks rework the finished golden garden (same geometry, camera and wand) and add their own layout data
EXTRA = {}
if LOOK == "night":
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import night_look
    EXTRA = night_look.apply(globals())
elif LOOK != "golden":
    # any other look lives in blender/scripts/<look>_look.py with an apply(globals()) like night_look.py
    import importlib, sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    try:
        mod = importlib.import_module(f"{LOOK}_look")
    except ModuleNotFoundError:
        raise SystemExit(f"unknown SB_LOOK {LOOK!r} (no blender/scripts/{LOOK}_look.py)")
    EXTRA = mod.apply(globals())

sc["sb"] = {
    "view": list(VIEW_PT),
    "focus_d": FOCUS_D,
    "fstop": FSTOP,
    "m_per_pt": M_PER_PT,
    "ring_c": list(RING_C),
    "ring_rin": RING_RIN,
    "ring_rout": RING_RMAJ + RING_TUBE,
    "sun_dir": list(SUN_DIR),
    "sun_el": SUN_EL,
    "sun_az": SUN_AZ,
    "bubble_pos": list(BUBBLE_POS),
    **EXTRA,
}
os.makedirs(os.path.dirname(BLEND), exist_ok=True)
bpy.ops.wm.save_as_mainfile(filepath=BLEND)
print("SAVED", BLEND, "objects", len(bpy.data.objects), "ring", tuple(round(v, 4) for v in RING_C), "rin", round(RING_RIN, 4))
