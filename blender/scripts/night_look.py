# Night look ("twilight with fairy lights") for build_scene.py: called with SB_LOOK=night once the golden garden is built.
# Same garden, camera and wand; what changes:
#   - world: a blue-hour sky (deep indigo zenith -> blue-violet -> a faint mauve afterglow low in front), no sun;
#     faint stars that only the env pass switches on (value node "stars_on")
#   - a weak cool moon (sun lamp, not visible) for the faint rims on the foliage silhouettes
#   - fairy lights: catenary strings of small emissive bulbs (warm white / amber, a few pink / teal) across the upper half of
#     the frame at 2-8 m, swags along the hedge, spirals wrapped through the hero / right / ring trees, a web of strings
#     overhead and behind the camera (for the env map and the wand's reflections), a few bigger frosted globe lanterns,
#     one of them on the lawn bottom-left (warm glow pool); thin dark wires between the bulbs
#   - the golden glints are removed; the wand's light-linked lights become a cool sky fill + warm lantern key / rim
#   - (v2 "photo") a world behind the lights: a house with warm lit windows far behind the hedge (and one behind the camera for
#     the env), pale hydrangea shrubs in front of the hedge, mostly warm-white bulbs (2400-3000 K) with a wide brightness spread,
#     a string of micro fairy lights just behind the focus plane (small discs), sparser hedge swags
#   - (v2) the lens: a 9-blade aperture, an aperture filter right on the lens (brighter rims + faint onion rings in every disc,
#     like a real fast lens) and a mechanical-vignetting stop 10 cm in front of it (cat-eye discs towards the frame edges).
#     All three are camera-ray-only objects parented to the camera ("lens_only"; render_passes.py hides them in the env pass)
# Knobs (env vars): SB_EXPOSURE SB_WB SB_SKY (sky gain) SB_BULBS (fairy-light gain) SB_BULB_DIFFUSE SB_MOON SB_LANTERN SB_WAND_KEY
#   wet wand: SB_WAND_WET (0 = dry) SB_WAND_GLINT SB_WAND_MENISCUS SB_WAND_WINDOW
#   v2: SB_BULB_COLOR (share of coloured bulbs) SB_HEDGE_LIGHTS (hedge swag gain) SB_MICRO (micro string gain, 0 = none)
#       SB_HOUSE SB_HOUSE_BACK (window gains, 0 = no house) SB_HYDRANGEA (0 = none) SB_KEY (key lantern gain)
#       lens: SB_BLADES (0 = round) SB_BLADE_ROT (deg) SB_CATEYE (stop radius / aperture radius, 0 = off) SB_RIM SB_ONION
import bpy, bmesh, math, os, random
from mathutils import Vector

rad = math.radians


def apply(g):
    sc = g["sc"]
    M, hexc, obj, coll = g["M"], g["hexc"], g["obj"], g["coll"]
    CAM_H, TAN_HX, TAN_HY = g["CAM_H"], g["TAN_HX"], g["TAN_HY"]
    HEDGE_Y, HEDGE_H = g["HEDGE_Y"], g["HEDGE_H"]
    rng = random.Random(23)                      # own stream: the golden garden's rng sequence stays untouched
    env = lambda k, d: float(os.environ.get(k, d))
    SKY = env("SB_SKY", "1.0")
    BULBS = env("SB_BULBS", "1.0")
    LANTERN = env("SB_LANTERN", "1.0")
    DIFFUSE = env("SB_BULB_DIFFUSE", "0.025")     # share of the bulbs' radiance that lights the scene (vs. seen directly)
    COLORED = env("SB_BULB_COLOR", "0.03")
    HEDGE_L = env("SB_HEDGE_LIGHTS", "0.4")
    MID_L = env("SB_MID_LIGHTS", "0")            # the two festoon strings crossing the upper middle (str_b, str_d; 0 = none)
    MICRO = env("SB_MICRO", "1.0")
    HOUSE, HOUSE_BACK = env("SB_HOUSE", "0.45"), env("SB_HOUSE_BACK", "0")   # (v3) back house off: crisp glyphs in the bubbles
    HYDRANGEA = env("SB_HYDRANGEA", "1.0")
    LIFT = env("SB_HYD_LIFT", "0.3")              # (v3) raise the hydrangea heads (m) so they clear the dark hedge base
    KEYG = env("SB_KEY", "0.22")
    rng2 = random.Random(57)                     # v2 additions draw from their own stream: the v1 layout stays where it was

    # ───────── colour management ─────────
    sc.view_settings.exposure = env("SB_EXPOSURE", "0.0")
    if hasattr(sc.view_settings, "use_white_balance"):
        sc.view_settings.use_white_balance = True
        sc.view_settings.white_balance_temperature = env("SB_WB", "6500")
    cy = sc.cycles
    cy.sample_clamp_indirect = 4.0

    # ───────── remove the golden-hour extras ─────────
    for ob in [o for o in bpy.data.objects if o.name.startswith("glint_") or o.name == "haze"]:
        bpy.data.objects.remove(ob)
    # the cosmos clump next to the ground lantern would glow red in the dark lower third; the leaf screen at 14 m and the
    # near branches only existed to break up the golden sun: without them the blue-hour sky opens up above the hedge
    for ob in [o for o in bpy.data.objects if o.name in ("flowers_7", "flowers_8") or o.name.startswith(("screen_", "hero_low_", "near", "right_", "trunk_right"))]:
        bpy.data.objects.remove(ob)
    # (the right tree goes too) and a thinner hero canopy: the sky dapples through it in blue-violet patches
    for ob in [o for o in bpy.data.objects if o.name.startswith("hero_")]:
        if rng.random() < 0.5:
            bpy.data.objects.remove(ob)

    # leaves at night: the backlight through them is the cool sky and moon, not the golden sun
    for mat in bpy.data.materials:
        if mat.name.startswith("leaf_") or mat.name == "hedge":
            for nd in mat.node_tree.nodes:
                if nd.type == "MIX" and getattr(nd, "blend_type", "") == "MULTIPLY":
                    ins = [s_ for s_ in nd.inputs if s_.type == "RGBA"]
                    if not ins[1].is_linked and ins[1].default_value[2] < 0.5:
                        ins[1].default_value = (0.55, 0.85, 0.75, 1)

    # ───────── world: blue-hour sky ─────────
    world = bpy.data.worlds.new("night_sky")
    sc.world = world
    nt = world.node_tree
    N, link = nt.nodes, nt.links.new
    bg = next(n for n in N if n.type == "BACKGROUND")

    def node(t, **kw):
        nd = N.new(t)
        for k, v in kw.items():
            if k in nd.inputs:
                nd.inputs[k].default_value = v
            else:
                setattr(nd, k, v)
        return nd

    def math_(op, a, b=None, c=None):
        n = node("ShaderNodeMath", operation=op)
        for i, x in enumerate((a, b, c)):
            if x is None:
                continue
            if isinstance(x, (int, float)):
                n.inputs[i].default_value = x
            else:
                link(x, n.inputs[i])
        return n.outputs[0]

    def mixc(fac, a, b, blend="MIX"):
        n = node("ShaderNodeMix", data_type="RGBA", blend_type=blend)
        ins = [s for s in n.inputs if s.type == "RGBA"]
        for sock, x in ((n.inputs["Factor"], fac), (ins[0], a), (ins[1], b)):
            if isinstance(x, (int, float, tuple)):
                sock.default_value = x
            else:
                link(x, sock)
        return [s for s in n.outputs if s.type == "RGBA"][0]

    tc = node("ShaderNodeTexCoord")
    nrm = node("ShaderNodeVectorMath", operation="NORMALIZE")
    link(tc.outputs["Generated"], nrm.inputs[0])
    sep = node("ShaderNodeSeparateXYZ")
    link(nrm.outputs["Vector"], sep.inputs[0])
    z = sep.outputs["Z"]
    # gradient over elevation (z = sin(elevation)); most of the change is in the lowest 15 deg, which the frame sees
    ramp = node("ShaderNodeValToRGB")
    stops = [(0.0, "#8a72b0"), (0.04, "#6a5ea8"), (0.09, "#4a4c9c"), (0.16, "#2c357c"), (0.25, "#1c2562"),
             (0.45, "#121a4a"), (1.0, "#080d2c")]
    if env("SB_SKY_BLUE", "1.0") > 0:            # (v2) a photographic blue hour: azure-cobalt, the afterglow only near the horizon
        stops = [(0.0, "#7a86c0"), (0.03, "#5a74bc"), (0.08, "#3d5cae"), (0.15, "#2a4592"), (0.25, "#1d3274"),
                 (0.45, "#132256"), (1.0, "#0a1236")]
    el = ramp.color_ramp.elements
    for i, (p, c) in enumerate(stops):
        e = el[i] if i < len(el) else el.new(p)
        e.position, e.color = p, hexc(c)
    link(z, ramp.inputs["Fac"])
    sky = ramp.outputs["Color"]
    # afterglow where the sun went down (in front of the camera, +y): a mauve-pink band hugging the horizon
    fwd = math_("POWER", math_("MAXIMUM", sep.outputs["Y"], 0.0), 3.0)
    low = math_("EXPONENT", math_("MULTIPLY", math_("MAXIMUM", z, 0.0), -1 / 0.05))
    glow = math_("MULTIPLY", math_("MULTIPLY", fwd, low), 0.55)
    sky = mixc(glow, sky, hexc("#d48aa8"), blend="ADD")
    # stars (env pass only): sparse Voronoi cells, fade near the horizon
    vor = node("ShaderNodeTexVoronoi", feature="F1")
    vor.inputs["Scale"].default_value = 420.0
    link(nrm.outputs["Vector"], vor.inputs["Vector"])
    cell = node("ShaderNodeSeparateColor")
    link(vor.outputs["Color"], cell.inputs[0])
    pick = math_("GREATER_THAN", cell.outputs[0], 0.955)
    core = math_("MAXIMUM", math_("SUBTRACT", 1.0, math_("DIVIDE", vor.outputs["Distance"], 0.11)), 0.0)
    tw = math_("MULTIPLY_ADD", cell.outputs[1], 1.6, 0.2)                      # brightness variety
    hor = math_("MINIMUM", math_("MULTIPLY", math_("MAXIMUM", z, 0.0), 5.0), 1.0)
    stars_on = node("ShaderNodeValue", name="stars_on", label="stars_on")
    stars_on.outputs[0].default_value = 0.0
    star = math_("MULTIPLY", math_("MULTIPLY", math_("MULTIPLY", pick, core), math_("MULTIPLY", tw, hor)), stars_on.outputs[0])
    star = math_("MULTIPLY", star, 0.35)
    sky = mixc(star, sky, (0.85, 0.9, 1.0, 1), blend="ADD")
    link(sky, bg.inputs["Color"])
    bg.inputs["Strength"].default_value = 0.8 * SKY

    # ───────── moon: weak cool key from front-right, for rims ─────────
    md = bpy.data.lights.new("moon", "SUN")
    md.energy = 0.12 * env("SB_MOON", "1.0")
    md.color = (0.62, 0.72, 1.0)
    md.angle = rad(0.6)
    moon = obj("moon", md, g["C_FX"])
    mdir = Vector((math.sin(rad(28)) * math.cos(rad(24)), math.cos(rad(28)) * math.cos(rad(24)), math.sin(rad(24))))
    moon.rotation_euler = (-mdir).to_track_quat("-Z", "Y").to_euler()

    # ───────── fairy lights ─────────
    C_LIGHTS = coll("fairy")
    # incandescent / warm-white LED fairy lights: 2400-3000 K (blackbody sRGB), a few deeper amber bulbs; coloured bulbs
    # (a party string's red / green / blue / amber) are rare (SB_BULB_COLOR)
    PAL = {"warm": hexc("#ffb46b"), "amber": hexc("#ff9c45"), "deep": hexc("#ff8a2a"), "champ": hexc("#ffc890"),
           "w30": hexc("#ffc28a"), "pink": hexc("#ff5a6e"), "teal": hexc("#3ab0ff")}

    def pick_col(mix="std"):
        x = rng.random()
        c = COLORED
        if mix == "std":
            table = (("warm", 0.42 - c / 2), ("amber", 0.2 - c / 2), ("champ", 0.16), ("w30", 0.16), ("deep", 0.06),
                     ("pink", c * 0.55), ("teal", c * 0.45))
        else:                                    # "warm": only the warm ones
            table = (("warm", 0.45), ("amber", 0.2), ("champ", 0.17), ("w30", 0.13), ("deep", 0.05))
        for k, w in table:
            if x < w:
                return k
            x -= w
        return table[0][0]

    def flicker():
        """Per-bulb brightness spread of a real string: most within +-35 %, some dim (aged / loose), a few hot."""
        x = rng2.random()
        return rng2.uniform(0.25, 0.5) if x < 0.12 else rng2.uniform(1.4, 2.0) if x > 0.95 else rng2.uniform(0.65, 1.35)

    m = M("fairy_bulb")
    m.n.remove(m.bsdf)
    at = m.node("ShaderNodeAttribute", attribute_name="glow", attribute_type="GEOMETRY")
    em = m.node("ShaderNodeEmission")
    m.link(at.outputs["Color"], em.inputs["Color"])
    # full radiance for what the camera (bokeh) and glossy rays (wand / env sparkle) see; the diffuse light the bulbs throw
    # on the foliage is scaled down, otherwise four thousand bulbs flood the garden and kill the blue hour
    lpb = m.node("ShaderNodeLightPath")
    seen = m.math("MAXIMUM", lpb.outputs["Is Camera Ray"], lpb.outputs["Is Glossy Ray"])
    # (v2) "bulb_cam": what the main camera sees of the bulbs (SB_BULB_CAM), so the discs sit below clipping and keep their
    # rims and onion rings; render_passes.py sets it to 1 for the env pass (the env keeps the full radiance)
    bcam = m.node("ShaderNodeValue")
    bcam.name = bcam.label = "bulb_cam"
    bcam.outputs[0].default_value = env("SB_BULB_CAM", "0.6")
    camg = m.math("MULTIPLY_ADD", lpb.outputs["Is Camera Ray"], m.math("SUBTRACT", bcam.outputs[0], 1.0), 1.0)
    m.link(m.math("MULTIPLY", m.math("MULTIPLY", m.math("MULTIPLY_ADD", seen, 1 - DIFFUSE, DIFFUSE), BULBS), camg), em.inputs["Strength"])
    m.to_out(em.outputs[0])
    BULB_MAT = m.m

    wm = M("fairy_wire")
    wm.bsdf.inputs["Base Color"].default_value = hexc("#17130f")
    wm.bsdf.inputs["Roughness"].default_value = 0.45
    WIRE_MAT = wm.m

    bm = bmesh.new()
    try:
        bmesh.ops.create_icosphere(bm, subdivisions=1, radius=1.0)
    except TypeError:
        bmesh.ops.create_icosphere(bm, subdivisions=1, diameter=1.0)
    ICO_V = [v.co.copy() for v in bm.verts]
    ICO_F = [[v.index for v in f.verts] for f in bm.faces]
    bm.free()

    stats = {"bulbs": 0}

    def bulbs(name, items):
        """items: (pos, radius, colour key, strength) -> one mesh object, per-vertex 'glow' colour = colour x strength."""
        verts, faces, cols = [], [], []
        for p, r, ck, s in items:
            base = len(verts)
            verts += [Vector(p) + v * r for v in ICO_V]
            faces += [[base + i for i in f] for f in ICO_F]
            c = PAL[ck]
            s = s * flicker()
            cols += [(c[0] * s, c[1] * s, c[2] * s, 1.0)] * len(ICO_V)
        me = bpy.data.meshes.new(name)
        me.from_pydata([tuple(v) for v in verts], [], faces)
        ca = me.color_attributes.new("glow", "FLOAT_COLOR", "POINT")
        ca.data.foreach_set("color", [x for c in cols for x in c])
        me.materials.append(BULB_MAT)
        for poly in me.polygons:
            poly.use_smooth = True
        ob = obj(name, me, C_LIGHTS)
        ob.visible_shadow = False                # emitters: they don't block light (or the strings next to them)
        stats["bulbs"] += len(items)
        return ob

    def wire(name, pts, thick=0.0016):
        cu = bpy.data.curves.new(name, "CURVE")
        cu.dimensions = "3D"
        cu.bevel_depth = thick
        cu.bevel_resolution = 1
        sp = cu.splines.new("POLY")
        sp.points.add(len(pts) - 1)
        for i, p in enumerate(pts):
            sp.points[i].co = (p[0], p[1], p[2], 1.0)
        cu.materials.append(WIRE_MAT)
        ob = obj(name, cu, C_LIGHTS)
        ob.visible_shadow = False
        ob["string_wire"] = 1                    # (v3) render_passes.py hides these in the env pass (SB_ENV_WIRES=0)
        return ob

    def swag(p0, p1, sag, n):
        p0, p1 = Vector(p0), Vector(p1)
        return [p0.lerp(p1, t) - Vector((0, 0, 4 * sag * t * (1 - t))) for t in (i / (n - 1) for i in range(n))]

    THIN = env("SB_ENV_THIN", "1.0")              # (v3) min. angular bulb spacing (deg) seen from the bubble, out-of-frame strings

    def thin(items, deg):
        """Drop bulbs closer than `deg` to the last kept one as seen from the bubble position: strings running away from
        it otherwise pile their bulbs into short bright dashes near the horizon (the 'scratches' in the bubbles)."""
        if deg <= 0:
            return items
        eye, kept, last = g["BUBBLE_POS"], [], None
        for it in items:
            d = (Vector(it[0]) - eye).normalized()
            if last is None or math.degrees(d.angle(last)) >= deg:
                kept.append(it)
                last = d
        return kept

    def string(name, p0, p1, sag, spacing, r=0.007, s=(40, 90), mix="std", drop=0.012, with_wire=True, gain=1.0, gaps=0.0,
               thin_deg=0.0):
        p0, p1 = Vector(p0), Vector(p1)
        fine = swag(p0, p1, sag, 64)
        length = sum((fine[i + 1] - fine[i]).length for i in range(63))
        n = max(2, int(length / spacing))
        pts = swag(p0, p1, sag, n)
        items = []
        for p in pts[1:-1]:
            q = p + Vector((rng.uniform(-0.01, 0.01), rng.uniform(-0.01, 0.01), -drop))
            items.append((q, r * rng.uniform(0.85, 1.15), pick_col(mix), rng.uniform(*s) * gain))
        items = [it for it in items if rng2.random() >= gaps]       # dead bulbs / gaps: breaks the even rhythm of a row
        items = thin(items, thin_deg)
        bulbs(name, items)
        if with_wire:
            wire(name + "_wire", fine)
        return items

    def spiral(name, centre, radii, turns, n, r=0.008, s=(40, 90), mix="std", shell=(0.75, 1.0)):
        """A string wound through a canopy: a spiral from bottom to top following the ellipsoid, bulbs jittered into the shell."""
        cx, cy_, cz = centre
        items = []
        a0 = rng.uniform(0, 2 * math.pi)
        for i in range(n):
            t = (i + 0.5) / n
            h = -0.9 + 1.8 * t
            ring = math.sqrt(max(0.0, 1 - h * h))
            a = a0 + 2 * math.pi * turns * t + rng.uniform(-0.15, 0.15)
            k = rng.uniform(*shell)
            p = Vector((cx + math.cos(a) * ring * radii[0] * k, cy_ + math.sin(a) * ring * radii[1] * k, cz + h * radii[2]))
            items.append((p, r * rng.uniform(0.85, 1.2), pick_col(mix), rng.uniform(*s)))
        bulbs(name, items)
        return items

    # in-frame strings across the upper half (camera at (0, 0, 1) looking +y; frame half-width 0.0975 d, half-height 0.212 d)
    string("str_near", (-0.95, 1.9, 1.70), (0.85, 2.9, 1.62), 0.26, 0.10, r=0.006, s=(18, 40), mix="warm")
    # bulb spacing grows with distance so that each defocused bulb stays a separate disc: fairy lights up close,
    # festoon strings (bigger bulbs, ~0.3-0.5 m apart) further out
    string("str_a", (-1.3, 3.3, 2.05), (1.25, 5.0, 1.75), 0.42, 0.16, r=0.008, s=(22, 48))
    if MID_L > 0:
        string("str_b", (-2.2, 5.6, 2.15), (2.0, 7.6, 1.95), 0.55, 0.30, r=0.016, s=(10, 22), drop=0.03, gain=MID_L, gaps=0.2)
    string("str_c", (-2.8, 10.5, 3.3), (2.6, 12.5, 3.6), 0.85, 0.45, r=0.022, s=(9, 20), drop=0.04)
    if MID_L > 0:
        string("str_d", (1.8, 3.8, 2.3), (-0.6, 9.5, 2.9), 0.6, 0.26, r=0.012, s=(14, 32), drop=0.025, gain=MID_L, gaps=0.35)
    # swags along the hedge front and through its ragged top
    for i, x0 in enumerate(range(-6, 6)):
        x0 = x0 + 0.0
        string(f"str_hedge{i}", (x0, HEDGE_Y - 0.12, HEDGE_H - 0.02 + rng.uniform(-0.05, 0.05)),
               (x0 + 1.0, HEDGE_Y - 0.12, HEDGE_H - 0.02 + rng.uniform(-0.05, 0.05)), rng.uniform(0.25, 0.4), 0.24,
               r=0.012, s=(20, 45), gain=HEDGE_L, gaps=0.4)
    hedge_top = []
    for i in range(50):
        p = Vector((rng.uniform(-6, 6), HEDGE_Y + rng.uniform(0.0, 0.9), HEDGE_H + rng.uniform(-0.1, 0.12)))
        hedge_top.append((p, 0.009, pick_col(), rng.uniform(25, 60)))
    bulbs("hedge_top", hedge_top)
    # trees wrapped in lights (the hero tree and the screen of leaves are in frame, the ring trees feed the env map)
    spiral("wrap_hero", (-2.4, 22.0, 6.6), (2.6, 1.9, 2.1), 6, 170, r=0.016, s=(50, 110))
    string("str_e", (-3.0, 15.0, 3.0), (2.5, 16.5, 2.7), 0.9, 0.6, r=0.028, s=(8, 18), drop=0.05)
    for ob in [o for o in bpy.data.objects if o.name.startswith("trunk_ring")]:
        if rng.random() < 0.6:
            x, y = ob.location.x, ob.location.y
            hgt = ob.dimensions.z / 0.6
            spiral(f"wrap_{ob.name}", (x, y, hgt), (4.0, 4.0, 3.2), 9, 260, r=0.02, s=(50, 110))
    # far tree line: a few loose strings between the trees
    for i in range(10):
        x = rng.uniform(-30, 30)
        y = rng.uniform(45, 60)
        string(f"str_far{i}", (x, y, rng.uniform(2.5, 4)), (x + rng.uniform(4, 8), y + rng.uniform(-3, 3), rng.uniform(2.5, 4)),
               rng.uniform(0.4, 0.9), 0.35, r=0.03, s=(50, 100), with_wire=False)
    # overhead web and strings behind the camera: the env map (and the glossy wand) see these as little bright points
    for i in range(9):
        a = rng.uniform(0, 2 * math.pi)
        b = a + math.pi + rng.uniform(-0.8, 0.8)
        r0, r1 = rng.uniform(4.5, 8), rng.uniform(4.5, 8)
        c = Vector((rng.uniform(-1.0, 1.0), rng.uniform(-0.5, 2.0), 0))
        p0 = c + Vector((math.sin(a) * r0, math.cos(a) * r0, rng.uniform(2.6, 3.3)))
        p1 = c + Vector((math.sin(b) * r1, math.cos(b) * r1, rng.uniform(2.6, 3.3)))
        string(f"str_web{i}", p0, p1, rng.uniform(0.35, 0.7), 0.16, r=0.008, s=(40, 90), thin_deg=THIN)
    for i, (y, z) in enumerate(((-1.4, 2.25), (-3.0, 2.5), (-5.0, 2.7))):
        string(f"str_back{i}", (-4.0, y + rng.uniform(-0.4, 0.4), z), (4.0, y + rng.uniform(-0.4, 0.4), z), 0.4, 0.15, r=0.008, s=(40, 90),
               thin_deg=THIN)
    # close above the wand (out of frame): real warm light + highlight dots on the glossy ring
    string("str_over", (-1.2, 0.3, 1.95), (1.1, 2.2, 1.9), 0.18, 0.11, r=0.006, s=(30, 55), mix="warm")

    # ───────── globe lanterns ─────────
    def lantern(name, pos, rad_, col, strength, power, hang=0.0):
        pos = Vector(pos)
        lm = M(name)
        lm.n.remove(lm.bsdf)
        lw = lm.node("ShaderNodeLayerWeight", Blend=0.35)
        f = lm.math("MULTIPLY_ADD", lw.outputs["Facing"], -0.45, 1.0)          # frosted globe: a touch dimmer at the edge
        e = lm.node("ShaderNodeEmission")
        e.inputs["Color"].default_value = col
        lm.link(lm.math("MULTIPLY", f, strength * LANTERN), e.inputs["Strength"])
        lm.to_out(e.outputs[0])
        bpy.ops.mesh.primitive_uv_sphere_add(segments=32, ring_count=16, radius=rad_, location=pos)
        gl = bpy.context.object
        gl.name = name
        for cl in gl.users_collection:
            cl.objects.unlink(gl)
        C_LIGHTS.objects.link(gl)
        gl.data.materials.append(lm.m)
        for poly in gl.data.polygons:
            poly.use_smooth = True
        gl.visible_shadow = False
        # dark cap on top
        bpy.ops.mesh.primitive_cylinder_add(vertices=16, radius=rad_ * 0.32, depth=rad_ * 0.3, location=pos + Vector((0, 0, rad_ * 1.02)))
        cap = bpy.context.object
        cap.name = name + "_cap"
        for cl in cap.users_collection:
            cl.objects.unlink(cap)
        C_LIGHTS.objects.link(cap)
        cap.data.materials.append(WIRE_MAT)
        if hang > 0:
            wire(name + "_hang", [pos + Vector((0, 0, rad_)), pos + Vector((0, 0, rad_ + hang))], thick=0.0015)
        # the light it casts (point light inside, invisible to the camera; the globe mesh is what is seen)
        ld = bpy.data.lights.new(name + "_light", "POINT")
        ld.energy = power * LANTERN
        ld.color = col[:3]
        ld.shadow_soft_size = rad_ * 0.8
        lo = obj(name + "_light", ld, C_LIGHTS)
        lo.location = pos
        lo.visible_camera = False
        lo.visible_glossy = False
        return pos

    # (v2) every globe is warm (frosted incandescent); the key keeps its position (layout.json "sun") but is dimmed (SB_KEY)
    # so it reads as a warm disc instead of a blown white blob; the old pink / teal globes keep their names and places
    KEY = lantern("lantern_key", (-0.32, 6.5, 1.90), 0.075, hexc("#ffa850"), 40.0 * KEYG, 10.0, hang=0.28)
    lantern("lantern_pink", (0.62, 11.0, 2.35), 0.08, hexc("#ffbe7a"), 6.0, 8.0, hang=0.35)
    lantern("lantern_teal", (-1.0, 16.5, 3.3), 0.1, hexc("#ffd0a0"), 4.0, 8.0, hang=0.4)
    lantern("lantern_far", (1.3, 19.0, 3.0), 0.1, hexc("#ffb060"), 6.0, 8.0, hang=0.4)
    lantern("lantern_ground", (-0.47, 5.4, 0.085), 0.075, hexc("#ffa850"), 26.0 * KEYG * 0.5, 18.0 * env("SB_GROUND_POOL", "0.5"))
    lantern("lantern_back", (-1.5, -1.8, 1.9), 0.07, hexc("#ffa850"), 30.0, 15.0, hang=0.3)

    # ───────── (v2) micro fairy lights just behind the focus plane ─────────
    # copper-wire LED string sagging across the top of the frame at 1.5-2.3 m: the only lights close to the focus plane,
    # so the only small discs (70-110 px vs. 150-260 px for everything from 3 m to infinity), crisper and denser
    if MICRO > 0:
        string("str_micro", (-0.5, 1.5, 1.50), (0.6, 2.35, 1.56), 0.27, 0.05, r=0.003, s=(30 * MICRO, 70 * MICRO), mix="warm",
               drop=0.004, gaps=0.04)

    # ───────── (v2) the house far behind the hedge, and one behind the camera ─────────
    # a Codex facade (textures/raw/house_night.png -> house_night.jpg, 3 sash windows per floor, porch lamp) on a 10.8 x 7.2 m
    # plane with a gable roof; the warm interior light is emitted where the texture is warm (r > b), the clapboard is a dark
    # diffuse lit by the sky. Through f/2 at 45 m every window becomes a soft warm rounded rectangle
    C_HOUSE = coll("house")

    def house_mat(gain):
        hm = M(f"house_facade_{len(bpy.data.materials)}")
        t = hm.tex("house_night.jpg", ext="EXTEND")
        b = hm.bsdf
        hm.link(t.outputs["Color"], b.inputs["Base Color"])
        b.inputs["Roughness"].default_value = 0.7
        sep_ = hm.node("ShaderNodeSeparateColor")
        hm.link(t.outputs["Color"], sep_.inputs[0])
        warm = hm.math("MAXIMUM", hm.math("SUBTRACT", sep_.outputs[0], hm.math("MULTIPLY", sep_.outputs[2], 1.6)), 0.0)
        mask = hm.math("MINIMUM", hm.math("MULTIPLY", warm, 6.0), 1.0)
        hm.link(t.outputs["Color"], b.inputs["Emission Color"])
        hm.link(hm.math("MULTIPLY", mask, 9.0 * gain), b.inputs["Emission Strength"])
        return hm.m

    def roof_mat():
        rm = M("house_roof")
        rm.bsdf.inputs["Base Color"].default_value = hexc("#1a1c22")
        rm.bsdf.inputs["Roughness"].default_value = 0.6
        return rm.m

    ROOF = roof_mat()

    def house(name, centre, facing, gain, w=10.8, h=7.2, depth=8.0, pitch=34.0):
        """Facade quad (uv 0..1) at `centre` (bottom middle) facing `facing` (+1: towards -y / the camera, -1: towards +y),
        a box behind it and a gable roof on top."""
        cx, cy, cz = centre
        f = facing
        x0, x1 = cx - w / 2, cx + w / 2
        me = bpy.data.meshes.new(name)
        y = cy
        verts = [(x0, y, cz), (x1, y, cz), (x1, y, cz + h), (x0, y, cz + h)]
        if f < 0:                                  # facing +y (seen from the front, +x is on the left): mirror the quad
            verts = [(x1, y, cz), (x0, y, cz), (x0, y, cz + h), (x1, y, cz + h)]
        me.from_pydata(verts, [], [(0, 1, 2, 3)])
        uv = me.uv_layers.new()
        for i, c in enumerate(((0, 0), (1, 0), (1, 1), (0, 1))):
            uv.data[i].uv = c
        me.materials.append(house_mat(gain))
        obj(name, me, C_HOUSE)
        # body + roof (dark; only their silhouette against the sky matters)
        ridge = h + (depth / 2) * math.tan(rad(pitch))
        yb = cy + f * depth                        # back wall
        rv = [(x0, cy + f * 0.02, cz), (x1, cy + f * 0.02, cz), (x1, yb, cz), (x0, yb, cz),
              (x0, cy + f * 0.02, cz + h), (x1, cy + f * 0.02, cz + h), (x1, yb, cz + h), (x0, yb, cz + h),
              (x0, (cy + yb) / 2, cz + ridge), (x1, (cy + yb) / 2, cz + ridge)]
        rf = [(0, 1, 2, 3), (4, 5, 9, 8), (7, 6, 9, 8), (4, 8, 7), (5, 9, 6), (0, 1, 5, 4), (3, 2, 6, 7), (0, 3, 7, 4), (1, 2, 6, 5)]
        rme = bpy.data.meshes.new(name + "_roof")
        rme.from_pydata(rv, [], rf)
        rme.materials.append(ROOF)
        return obj(name + "_roof", rme, C_HOUSE)          # (the facade quad sits 2 cm in front of the body)

    if HOUSE > 0:
        house("house_far", (6.2, 46.0, 0.0), 1, HOUSE)
        # chimney
        bpy.ops.mesh.primitive_cube_add(size=1, location=(9.0, 50.0, 10.2))
        ch = bpy.context.object
        ch.name = "house_far_chimney"
        ch.scale = (0.7, 0.7, 2.2)
        for cl in ch.users_collection:
            cl.objects.unlink(ch)
        C_HOUSE.objects.link(ch)
        ch.data.materials.append(ROOF)
    if HOUSE_BACK > 0:                             # behind the camera, left: the bubbles mirror its windows (env pass)
        house("house_back", (-3.5, -17.0, 0.0), -1, HOUSE_BACK)

    # ───────── (v2) hydrangea shrubs in front of the hedge ─────────
    # pale mophead clusters (Codex card, magenta-keyed) catching the blue sky: the soft pale blobs of a real dusk garden.
    # They replace the cosmos border along the hedge (pink cosmos at dusk read as noise)
    if HYDRANGEA > 0:
        for ob in [o for o in bpy.data.objects if o.name.startswith("flowers_") and o.location.y > 6.0]:
            bpy.data.objects.remove(ob)
        HYD = g["card_mesh"]("card_hydrangea", g["leaf_mat"]("hydrangea", "hydrangea.png", value=0.8 * HYDRANGEA, trans=0.3, warm=0.6),
                             pivot_bottom=True)
        C_HYD = coll("hydrangea")
        k = 0
        # (x range, y range, count): a shrub at each side of the frame, half out of it; the middle stays the dark hedge
        # (the bubbles fly there), plus a few out of frame for the env
        for xr, yr, n in (((-1.0, -0.5), (6.6, 8.4), 5), ((0.55, 1.05), (6.8, 8.6), 5),
                          ((-2.8, -1.4), (4.0, 8.0), 6), ((1.4, 2.8), (4.0, 8.0), 6)):
            for _ in range(n):
                x, y = rng2.uniform(*xr), rng2.uniform(*yr)
                p = Vector((x, y, rng2.uniform(0.0, 0.6) + LIFT))  # tall old shrubs: flower heads up to ~1.4 m (+ SB_HYD_LIFT)
                nrm = Vector((rng2.uniform(-0.3, 0.3), -1.0, rng2.uniform(0.0, 0.35)))
                g["place"](f"hydrangea_{k}", HYD, p, g["look_rot"](nrm, rng2.uniform(-0.35, 0.35)), rng2.uniform(0.6, 0.85), C_HYD)
                k += 1
    # ───────── (v3) the lower half: path lights on the lawn, foreground foliage ─────────
    # low warm bollard lights along both sides of the lawn (frosted glass heads, out of focus discs at the frame sides) with
    # warm pools on the grass; the lawn behind the wand ring stays dark (the lights sit outside the ring's columns)
    PATH = env("SB_PATH_LIGHTS", "1.0")
    if PATH > 0:
        pm = M("path_glass")
        pm.n.remove(pm.bsdf)
        pe = pm.node("ShaderNodeEmission")
        pe.inputs["Color"].default_value = hexc("#ffb36a")
        pe.inputs["Strength"].default_value = 7.0 * PATH
        pm.to_out(pe.outputs[0])
        for i, (x, y, h, pw) in enumerate(((0.62, 6.3, 0.42, 16.0), (-0.70, 7.6, 0.42, 14.0), (0.46, 5.0, 0.36, 12.0),
                                           (-0.95, 10.8, 0.42, 8.0), (1.0, 11.6, 0.42, 8.0))):
            bpy.ops.mesh.primitive_cylinder_add(vertices=16, radius=0.035, depth=h, location=(x, y, h / 2))
            post_ = bpy.context.object
            post_.name = f"path_post{i}"
            for cl in post_.users_collection:
                cl.objects.unlink(post_)
            C_LIGHTS.objects.link(post_)
            post_.data.materials.append(WIRE_MAT)
            bpy.ops.mesh.primitive_cylinder_add(vertices=16, radius=0.045, depth=0.09, location=(x, y, h + 0.045))
            head = bpy.context.object
            head.name = f"path_head{i}"
            for cl in head.users_collection:
                cl.objects.unlink(head)
            C_LIGHTS.objects.link(head)
            head.data.materials.append(pm.m)
            head.visible_shadow = False
            ld = bpy.data.lights.new(f"path_light{i}", "SPOT")      # shielded bollard: a pool around its foot only
            ld.energy = pw * PATH
            ld.color = (1.0, 0.68, 0.4)
            ld.shadow_soft_size = 0.04
            ld.spot_size = rad(110)
            ld.spot_blend = 0.6
            lo = obj(f"path_light{i}", ld, C_LIGHTS)
            lo.location = (x, y, h + 0.03)                            # (a spot points down its -z: the default)
            lo.visible_camera = lo.visible_glossy = False

    # foreground: a few leaves of a shrub right in front of the lens (0.6-0.9 m, the bottom corners), far out of focus:
    # big soft dark-green blobs with a cool sheen at the bottom edge, depth in front of the bubbles' plane
    FG = env("SB_FOREGROUND", "1.0")
    C_FG = coll("foreground")
    if FG > 0:
        # (frame at 0.8 m: 0.156 m wide, bottom edge at z 0.83; the cards only reach in from the two bottom corners)
        for i, (x, y, z, s_) in enumerate(((0.082, 0.72, 0.835, 0.08), (0.10, 0.85, 0.83, 0.09), (0.07, 0.66, 0.85, 0.05),
                                           (-0.095, 0.9, 0.835, 0.09), (-0.085, 0.8, 0.845, 0.07))):
            p = Vector((x, y, z))
            nrm = Vector((rng2.uniform(-0.4, 0.4), -1.0, rng2.uniform(0.1, 0.6)))
            g["place"](f"fg_leaf{i}", g["CARDS"]["maple"], p, g["look_rot"](nrm, rng2.uniform(-math.pi, math.pi)), s_, C_FG)

    # one fairy bulb right in front of the lens (0.55 m, bottom-right corner): a big, dim, soft foreground disc
    if FG > 0:
        bulbs("fg_bulb", [(Vector((0.05, 0.55, 0.885)), 0.006, "warm", 70.0 * FG)])

    # hydrangea rim light: the hedge swags right behind the shrubs light the petal edges (a warm area light behind them,
    # light-linked to the hydrangeas only)
    if HYDRANGEA > 0:
        rd = bpy.data.lights.new("hydrangea_rim", "AREA")
        rd.shape = "RECTANGLE"
        rd.size, rd.size_y = 4.0, 0.4
        rd.energy = 60.0 * env("SB_HYD_RIM", "0.6")
        rd.color = (1.0, 0.7, 0.42)
        rl = obj("hydrangea_rim", rd, g["C_FX"])
        rl.location = (0.0, 9.0, 1.25)
        rl.rotation_euler = (Vector((0, -0.6, -0.45))).to_track_quat("-Z", "Y").to_euler()
        rl.visible_camera = rl.visible_glossy = False
        rl.light_linking.receiver_collection = C_HYD

    # ───────── (v2) blue-hour fill on the garden ─────────
    # a soft cool "sky dome" key from above / behind the camera, light-linked to the garden and the hydrangeas (not the
    # wand): the eye (and a long exposure) reads foliage and pale flowers at blue hour, the bare world light leaves them black
    SKYFILL = env("SB_SKYFILL", "1.0")
    if SKYFILL > 0:
        fd = bpy.data.lights.new("sky_fill", "SUN")
        fd.energy = 1.0 * SKYFILL                                    # (v3: 1.6 -> 1.0, the mid band read as an olive haze)
        fd.color = (0.55, 0.68, 1.0)
        fd.angle = rad(70)
        fl = obj("sky_fill", fd, g["C_FX"])
        fdir = Vector((0.25, -0.55, 0.8)).normalized()               # towards the light: up, behind the camera, a bit right
        fl.rotation_euler = (-fdir).to_track_quat("-Z", "Y").to_euler()
        # receivers: the hydrangeas and the garden within 14 m (hedge, its leaves, flowers), not the lawn (it stays the dark
        # floor of the frame and of the env) and not the trees (they stay silhouettes against the sky)
        rc_ = bpy.data.collections.new("sky_fill_receivers")
        if HYDRANGEA > 0:
            rc_.children.link(C_HYD)
        for ob in list(g["C_GARDEN"].all_objects) + list(C_FG.all_objects):
            if ob.name != "lawn" and ob.location.length < 14.0:
                rc_.objects.link(ob)
        fl.light_linking.receiver_collection = rc_

    # ───────── (v2) the lens: aperture blades, aperture filter (rims, onion rings), mechanical vignetting (cat-eye) ─────────
    cam = sc.camera
    cdat = cam.data
    BLADES = int(env("SB_BLADES", "11"))
    cdat.dof.aperture_blades = BLADES if BLADES >= 3 else 0
    cdat.dof.aperture_rotation = rad(env("SB_BLADE_ROT", "12"))
    cdat.clip_start = 0.001
    A = cdat.lens / 1000.0 / (2 * cdat.dof.aperture_fstop)      # aperture radius (m)
    RIM, ONION = env("SB_RIM", "0.45"), env("SB_ONION", "0.16")
    CATEYE = env("SB_CATEYE", "1.41")

    def lens_part(name, me, mat):
        me.materials.append(mat)
        ob = obj(name, me, g["C_FX"])
        ob.parent = cam
        ob["lens_only"] = 1
        for v in ("visible_diffuse", "visible_glossy", "visible_transmission", "visible_volume_scatter", "visible_shadow"):
            setattr(ob, v, False)
        return ob

    def disc_mesh(name, r_in, r_out, z, seg=128):
        bm_ = bmesh.new()
        ring_in, ring_out = [], []
        for i in range(seg):
            a = 2 * math.pi * i / seg
            if r_in > 0:
                ring_in.append(bm_.verts.new((r_in * math.cos(a), r_in * math.sin(a), z)))
            ring_out.append(bm_.verts.new((r_out * math.cos(a), r_out * math.sin(a), z)))
        if r_in > 0:
            for i in range(seg):
                j = (i + 1) % seg
                bm_.faces.new((ring_in[i], ring_in[j], ring_out[j], ring_out[i]))
        else:
            bm_.faces.new(ring_out)
        me = bpy.data.meshes.new(name)
        bm_.to_mesh(me)
        bm_.free()
        return me

    if RIM > 0 or ONION > 0:
        # a filter right on the lens (2 mm in front of it, inside the 1 mm clip start): every camera ray crosses it at
        # (almost) its own sample point on the aperture, so its transmission is the bokeh disc's brightness profile:
        # brighter towards the rim (under-corrected spherical aberration of a fast lens) and faint concentric "onion rings"
        # (aspherical element polishing marks), with a slight irregularity so the rings are not machine-perfect
        fm = M("lens_filter")
        fm.n.remove(fm.bsdf)
        oc = fm.node("ShaderNodeTexCoord")
        sepo = fm.node("ShaderNodeSeparateXYZ")
        fm.link(oc.outputs["Object"], sepo.inputs[0])
        rr = fm.math("DIVIDE", fm.math("SQRT", fm.math("ADD", fm.math("MULTIPLY", sepo.outputs[0], sepo.outputs[0]),
                                                           fm.math("MULTIPLY", sepo.outputs[1], sepo.outputs[1]))), A)
        rim = fm.node("ShaderNodeMapRange", interpolation_type="SMOOTHSTEP")
        rim.inputs["From Min"].default_value, rim.inputs["From Max"].default_value = 0.45, 1.0
        fm.link(rr, rim.inputs["Value"])
        nz = fm.noise(900.0, 2.0, oc.outputs["Object"])
        wob = fm.math("MULTIPLY_ADD", nz.outputs["Fac"], 0.08, rr)
        onion = fm.math("SINE", fm.math("MULTIPLY", fm.math("MULTIPLY", wob, wob), 2 * math.pi * 7.0))
        t_ = fm.math("ADD", fm.math("MULTIPLY_ADD", rim.outputs[0], RIM, 1.0 - RIM), fm.math("MULTIPLY", onion, ONION / 2))
        t_ = fm.math("DIVIDE", t_, 1.0 + ONION / 2)
        tr_ = fm.node("ShaderNodeBsdfTransparent")
        cc = fm.node("ShaderNodeCombineColor")
        for i in range(3):
            fm.link(t_, cc.inputs[i])
        fm.link(cc.outputs[0], tr_.inputs["Color"])
        fm.to_out(tr_.outputs[0])
        lens_part("lens_filter", disc_mesh("lens_filter", 0, A * 1.6, -0.002), fm.m)
    if CATEYE > 0:
        # the front of the barrel 10 cm ahead of the aperture: off-axis ray bundles are clipped by it, so discs towards the
        # frame edges (mostly the top, the long side of a portrait frame) become cat's eyes, as on any fast portrait lens
        sm = M("lens_stop")
        sm.n.remove(sm.bsdf)
        e_ = sm.node("ShaderNodeEmission")
        e_.inputs["Strength"].default_value = 0.0
        sm.to_out(e_.outputs[0])
        lens_part("lens_stop", disc_mesh("lens_stop", A * CATEYE, 0.3, -0.10), sm.m)

    # ───────── the wand: cool sky fill + warm lantern key / rim (light-linked to the wand only) ─────────
    # (name, colour, power, size, position or None to keep): a weak cool fill from the sky, a small warm key up-left (a nearby
    # lantern: the crisp highlight on the clear coat), a warm rim from the strings behind, a cool sky kicker on the right
    ring_c = g["RING_C"]
    WK = env("SB_WAND_KEY", "1.0")
    for name, col, energy, size, loc in (("wand_fill", (0.50, 0.62, 1.0), 0.5, 0.9, None),
                                         ("wand_key", (1.0, 0.68, 0.38), 6.0 * WK, 0.05, (-0.36, 0.66, 1.46)),
                                         ("wand_rim", (1.0, 0.60, 0.30), 16.0, 0.2, None),
                                         ("wand_kick", (0.45, 0.70, 1.0), 10.0, 0.3, (0.55, 1.85, 1.30))):
        lo = bpy.data.objects.get(name)
        if lo:
            lo.data.color = col
            lo.data.energy = energy
            lo.data.size = size
            if loc:
                lo.location = loc
                lo.rotation_euler = (ring_c - Vector(loc)).normalized().to_track_quat("-Z", "Y").to_euler()

    # ───────── the wand, wet: a glossier clear coat, a soap-film meniscus on the ring's inner edge, a porch window ─────────
    # SB_WAND_WET=0 keeps the dry plastic. Only the wand is touched (materials, a light linked to the wand, a glossy-only
    # bulb gain that render_passes.py switches on in the wand pass alone), so bg.jpg / env.jpg renders stay the same.
    WET = env("SB_WAND_WET", "1.0") > 0
    GLINT = env("SB_WAND_GLINT", "1")            # bulbs' radiance as seen in the wand's own reflections (wand pass only;
    #                                              v3: 400 -> 1 = physical; boosted, the bulbs lit the ridged base in square patches)
    COAT_SMOOTH = env("SB_WAND_COAT_SMOOTH", "1") > 0   # (v3) a mirror-smooth wet coat: no noise / bump drives the coat normal
    # (v3) the rough, ridged base reflecting the boosted bulbs made the square patches: with the smooth coat it barely reflects
    BASE_SPEC = env("SB_WAND_BASE_SPEC", "0.03" if COAT_SMOOTH else "0.15")
    MENISCUS = env("SB_WAND_MENISCUS", "0.6")    # how far the inner-edge film bends the coat normal towards the camera
    if WET:
        for mat in [bpy.data.materials.get(n) for n in ("plastic_pink", "plastic_pink_ring", "plastic_mint")]:
            if not mat:
                continue
            nt_, ln = mat.node_tree, mat.node_tree.links.new
            b = next(n for n in nt_.nodes if n.type == "BSDF_PRINCIPLED")
            b.inputs["Coat Weight"].default_value = 1.0
            b.inputs["Coat Roughness"].default_value = 0.05
            b.inputs["Specular IOR Level"].default_value = BASE_SPEC            # the coat does the reflecting, not a milky base
            worn = next(n for n in nt_.nodes if n.type == "MAP_RANGE")      # base roughness ~0.25 (0.20-0.30 wear)
            worn.inputs["To Min"].default_value, worn.inputs["To Max"].default_value = 0.20, 0.30
            if COAT_SMOOTH:
                # the liquid film is smooth: the coat takes the plain shading normal; the base keeps the moulded ridges but
                # loses the fine speckle bump (it read as blotchy, pixel-sized highlight patches)
                if mat.name != "plastic_pink_ring":         # (the ring's coat normal is rewired below)
                    for lk in list(b.inputs["Coat Normal"].links):
                        nt_.links.remove(lk)
                for bn in [n for n in nt_.nodes if n.type == "BUMP" and abs(n.inputs["Strength"].default_value - 0.08) < 1e-6]:
                    bn.inputs["Strength"].default_value = 0.0
            if mat.name != "plastic_pink_ring":
                continue
            ridged = b.inputs["Coat Normal"].links[0].from_node                # bump(ridges) <- bump(fine noise)
            fine_n = ridged.inputs["Normal"].links[0].from_socket
            # meniscus: a thin band on the inner edge of the tube (object space: the torus lies in local xy) where the
            # soap solution pools: smooth (it fills the ridges), very low roughness, a stronger specular
            tco = nt_.nodes.new("ShaderNodeTexCoord")
            sep_ = nt_.nodes.new("ShaderNodeSeparateXYZ")
            ln(tco.outputs["Object"], sep_.inputs[0])
            rho = nt_.nodes.new("ShaderNodeVectorMath")
            rho.operation = "LENGTH"
            cxy = nt_.nodes.new("ShaderNodeCombineXYZ")
            ln(sep_.outputs["X"], cxy.inputs["X"])
            ln(sep_.outputs["Y"], cxy.inputs["Y"])
            ln(cxy.outputs[0], rho.inputs[0])
            band = nt_.nodes.new("ShaderNodeMapRange")                       # 1 at the inner rim -> 0 at 0.6 tube radius out
            band.interpolation_type = "SMOOTHSTEP"
            rin, tube = g["RING_RIN"], g["RING_TUBE"]
            band.inputs["From Min"].default_value = rin + 0.6 * tube
            band.inputs["From Max"].default_value = rin + 0.08 * tube
            ln(rho.outputs["Value"], band.inputs["Value"])
            wet = band.outputs[0]

            def lerp(a, x, y):
                mr = nt_.nodes.new("ShaderNodeMapRange")
                mr.inputs["To Min"].default_value, mr.inputs["To Max"].default_value = x, y
                ln(a, mr.inputs["Value"])
                return mr.outputs[0]
            ln(lerp(wet, 0.05, 0.02), b.inputs["Coat Roughness"])
            mixr = nt_.nodes.new("ShaderNodeMix")                           # base roughness: worn -> 0.12 in the film
            mixr.data_type = "FLOAT"
            ln(wet, mixr.inputs["Factor"])
            ln(worn.outputs[0], mixr.inputs["A"])
            mixr.inputs["B"].default_value = 0.12
            ln(mixr.outputs[0], b.inputs["Roughness"])
            ln(lerp(wet, BASE_SPEC, 0.7 if not COAT_SMOOTH else 0.35), b.inputs["Specular IOR Level"])
            # meniscus normal: the liquid fillet meets the film tangentially, so across the band the coat normal bends from
            # the tube's normal towards the film plane's (local +-z, the side facing the camera): the band then catches the
            # window and the bulbs behind the camera as a thin bright crescent on the inner edge
            geo = nt_.nodes.new("ShaderNodeNewGeometry")
            to_obj = nt_.nodes.new("ShaderNodeVectorTransform")
            to_obj.vector_type, to_obj.convert_from, to_obj.convert_to = "NORMAL", "WORLD", "OBJECT"
            ln(geo.outputs["Normal"], to_obj.inputs[0])
            sn = nt_.nodes.new("ShaderNodeSeparateXYZ")
            ln(to_obj.outputs[0], sn.inputs[0])
            sgn = nt_.nodes.new("ShaderNodeMath")
            sgn.operation = "SIGN"
            ln(sn.outputs["Z"], sgn.inputs[0])
            film_n = nt_.nodes.new("ShaderNodeCombineXYZ")
            ln(sgn.outputs[0], film_n.inputs["Z"])
            mixn = nt_.nodes.new("ShaderNodeMix")
            mixn.data_type = "VECTOR"
            ln(lerp(wet, 0.0, MENISCUS), mixn.inputs["Factor"])
            ln(to_obj.outputs[0], mixn.inputs[4])
            ln(film_n.outputs[0], mixn.inputs[5])
            nn = nt_.nodes.new("ShaderNodeVectorMath")
            nn.operation = "NORMALIZE"
            ln(mixn.outputs[1], nn.inputs[0])
            to_w = nt_.nodes.new("ShaderNodeVectorTransform")
            to_w.vector_type, to_w.convert_from, to_w.convert_to = "NORMAL", "OBJECT", "WORLD"
            ln(nn.outputs["Vector"], to_w.inputs[0])
            # outside the band: the coat's normal skips the moulded ridges (the liquid film levels them), the base keeps them
            smooth = nt_.nodes.new("ShaderNodeMix")
            smooth.data_type = "VECTOR"
            ln(wet, smooth.inputs["Factor"])
            ln(fine_n, smooth.inputs[4])
            ln(to_w.outputs[0], smooth.inputs[5])
            nn2 = nt_.nodes.new("ShaderNodeVectorMath")
            nn2.operation = "NORMALIZE"
            ln(smooth.outputs[1], nn2.inputs[0])
            # (v3 smooth coat: only the meniscus bend, no fine noise anywhere on the coat)
            ln(to_w.outputs[0] if COAT_SMOOTH else nn2.outputs["Vector"], b.inputs["Coat Normal"])
        # the warm porch window behind the camera, up-left: seen only in the wand's reflections (no diffuse light, linked to it)
        wd = bpy.data.lights.new("wand_window", "AREA")
        wd.shape = "RECTANGLE"
        # (v3) sized like the shader's analytic porch window (~0.32 x 0.44 rad from the bubble): one continuous streak along
        # the smooth wet coat instead of scattered glints
        WSZ = env("SB_WAND_WINDOW_SIZE", "1.6")
        wd.size, wd.size_y = 0.45 * WSZ, 0.65 * WSZ
        wd.energy = 160.0 * WSZ * WSZ * env("SB_WAND_WINDOW", "2.0")
        wd.color = (1.0, 0.66, 0.36)
        wl = obj("wand_window", wd, g["C_FX"])
        wl.location = (-1.1, -1.9, 1.85)
        wl.rotation_euler = (ring_c - wl.location).normalized().to_track_quat("-Z", "Y").to_euler()
        wl.visible_camera = wl.visible_diffuse = wl.visible_transmission = wl.visible_volume_scatter = False
        wl.light_linking.receiver_collection = g["C_WAND"]
        # bulbs' gain for glossy rays straight off the wand, 1 everywhere except the wand pass (render_passes.py sets it)
        nb = BULB_MAT.node_tree
        glint = nb.nodes.new("ShaderNodeValue")
        glint.name = glint.label = "wand_glint"
        glint.outputs[0].default_value = 1.0
        em_ = next(n for n in nb.nodes if n.type == "EMISSION")
        lp = next(n for n in nb.nodes if n.type == "LIGHT_PATH")
        first = m.math("LESS_THAN", lp.outputs["Ray Depth"], 1.5)
        gl_on = m.math("MULTIPLY", m.math("MULTIPLY", lp.outputs["Is Glossy Ray"], first), m.math("SUBTRACT", glint.outputs[0], 1.0))
        m.link(m.math("MULTIPLY", em_.inputs["Strength"].links[0].from_socket, m.math("ADD", gl_on, 1.0)), em_.inputs["Strength"])

    print("NIGHT bulbs", stats["bulbs"])
    return {"look": "night", "key_pos": list(KEY), "key_name": "lantern_key", **({"wand_glint": GLINT} if WET else {}),
            "lens": int(RIM > 0 or ONION > 0 or CATEYE > 0)}
