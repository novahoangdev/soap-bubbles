# Dawn look ("misty spring morning") for build_scene.py: called with SB_LOOK=dawn once the golden garden is built.
# Same garden, camera and wand; what changes:
#   - world: a pastel sky (pale peach-pink at the horizon -> rose -> lavender -> soft periwinkle zenith) with the low sun
#     hidden behind thin mist: no disc, only a creamy glow (a tight core, a wide halo); slightly left of centre, upper third
#   - a soft, wide sun lamp (10 deg) from the same direction: gentle backlight, no hard shadows
#   - aerial perspective: every garden material fades towards the mist colour with distance from the camera (an emission
#     mix driven by the camera distance, brighter towards the sun: forward scattering). Noise-free depth haze, unlike a volume
#   - cherry blossom: the leaf screen at 14 m, the near framing branches and the hero tree become blossom cards
#     (textures/raw/blossom_branch.png, Codex, blue-keyed by prep_textures.py), plus out-of-focus branches in the upper
#     corners (1.8-3 m, soft pink / white bokeh) and blossom trees in the ring around the garden (the bubbles see them)
#   - dewy lawn: a wet clear coat on the grass and a scatter of tiny dew glints (pale, off the ring's columns)
#   - the golden glints go; the leaves' backlight turns fresh spring green instead of golden yellow
#   - the wand: wet (like night_look.py SB_WAND_WET), lit by broad soft lights only (no small keys: no blocky highlights)
# Knobs (env vars): SB_EXPOSURE SB_WB SB_SKY (sky gain) SB_SUNGLOW (glow gain) SB_SUN (lamp gain) SB_MIST (haze density)
#   SB_DEW (glint gain, 0 = none) SB_BLOSSOM (near branch count scale) SB_WAND_WET (0 = dry) SB_WAND_KEY
#   SB_HALO (gain of the sun's halo + wide glow: the whole 11 deg frame sits inside them, so they milk the centre)
#   SB_GROUND (lawn albedo gain: < 1 = a darker ground) SB_MIDBRANCH (distance of the mid-focus branch from the top-left, 0 = none)
#   SB_MIDTREES (0 = no blossom masses in the centre band) SB_FWD (forward-scattering gain of the depth haze towards the
#   sun: the bright cream mist patch behind the bubbles' column)
import bpy, math, os, random
from mathutils import Vector

rad = math.radians

SUN_EL, SUN_AZ = 8.0, -3.0          # low sun, slightly left of centre (upper third of the frame), behind the hero tree's edge


def apply(g):
    sc = g["sc"]
    M, hexc, obj, coll = g["M"], g["hexc"], g["obj"], g["coll"]
    rng = random.Random(41)
    rng2 = random.Random(43)             # for the additions below (keeps rng's sequence: the near branches stay put)
    env = lambda k, d: float(os.environ.get(k, d))
    SKY = env("SB_SKY", "1.0")
    MIST = env("SB_MIST", "0.8")
    sun_dir = Vector((math.sin(rad(SUN_AZ)) * math.cos(rad(SUN_EL)), math.cos(rad(SUN_AZ)) * math.cos(rad(SUN_EL)), math.sin(rad(SUN_EL))))

    # ───────── colour management: soft, slightly cool-neutral morning ─────────
    sc.view_settings.exposure = env("SB_EXPOSURE", "0.25")
    for look in ("AgX - Base Contrast", "None"):
        try:
            sc.view_settings.look = look
            break
        except TypeError:
            continue
    if hasattr(sc.view_settings, "use_white_balance"):
        sc.view_settings.use_white_balance = True
        sc.view_settings.white_balance_temperature = env("SB_WB", "6300")
    sc.cycles.sample_clamp_indirect = 4.0
    # a touch less background blur than golden (f/2): the blossom shapes in the middle band read as shapes, not one wash
    sc.camera.data.dof.aperture_fstop = env("SB_FSTOP", "2.8")

    # ───────── remove the golden-hour extras ─────────
    for ob in [o for o in bpy.data.objects if o.name.startswith("glint_") or o.name == "haze"]:
        bpy.data.objects.remove(ob)
    # the two cosmos clumps near the lens read as loud magenta blobs next to the ring
    for ob in [o for o in bpy.data.objects if o.name in ("flowers_7", "flowers_8")]:
        bpy.data.objects.remove(ob)

    # ───────── world: pastel sky, hidden sun ─────────
    world = bpy.data.worlds.new("dawn_sky")
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
    z = math_("MAXIMUM", sep.outputs["Z"], 0.0)
    ramp = node("ShaderNodeValToRGB")
    # (most of the frame's sky is the lowest 12 deg: z 0..0.2 carries the whole peach -> pink -> lavender gradient)
    stops = [(0.0, "#ffd2bc"), (0.035, "#fcc4c4"), (0.08, "#f0b8d2"), (0.14, "#d9b2e4"), (0.22, "#c2b0ec"),
             (0.45, "#b2ade8"), (1.0, "#a3a6e2")]
    el = ramp.color_ramp.elements
    for i, (p, c) in enumerate(stops):
        e = el[i] if i < len(el) else el.new(p)
        e.position, e.color = p, hexc(c)
    link(z, ramp.inputs["Fac"])
    sky = ramp.outputs["Color"]
    # warmer (peach) on the sun's side of the sky, a touch cooler behind the camera
    dsun = node("ShaderNodeVectorMath", operation="DOT_PRODUCT")
    link(nrm.outputs["Vector"], dsun.inputs[0])
    dsun.inputs[1].default_value = tuple(sun_dir)
    cosg = dsun.outputs["Value"]
    side = math_("MULTIPLY", math_("ADD", cosg, 1.0), 0.5)                      # 0 behind .. 1 at the sun
    sky = mixc(math_("MULTIPLY", math_("POWER", side, 3.0), 0.3), sky, hexc("#ffcdb0"))
    # the sun behind thin mist: no disc, a soft creamy core and a wide warm halo
    GLOW = env("SB_SUNGLOW", "1.0")
    core = math_("EXPONENT", math_("DIVIDE", math_("SUBTRACT", cosg, 1.0), 0.0012))      # ~2.8 deg
    halo = math_("EXPONENT", math_("DIVIDE", math_("SUBTRACT", cosg, 1.0), 0.012))       # ~9 deg
    wide = math_("EXPONENT", math_("DIVIDE", math_("SUBTRACT", cosg, 1.0), 0.08))        # ~23 deg
    HALO = env("SB_HALO", "0.45")
    gl = math_("ADD", math_("ADD", math_("MULTIPLY", core, 1.1 * GLOW), math_("MULTIPLY", halo, 0.3 * GLOW * HALO)),
               math_("MULTIPLY", wide, 0.12 * GLOW * HALO))
    sky = mixc(gl, sky, hexc("#fff0de"), blend="ADD")
    link(sky, bg.inputs["Color"])
    bg.inputs["Strength"].default_value = 0.75 * SKY
    MIST_COL = hexc("#fac8c2")                   # the sky right at the horizon (what far things fade into)

    # ───────── soft sun lamp: gentle backlight through the mist ─────────
    sd = bpy.data.lights.new("dawn_sun", "SUN")
    sd.energy = 2.2 * env("SB_SUN", "1.0")
    sd.color = (1.0, 0.84, 0.74)
    sd.angle = rad(10)
    sun = obj("dawn_sun", sd, g["C_FX"])
    sun.rotation_euler = (-sun_dir).to_track_quat("-Z", "Y").to_euler()
    sun.visible_camera = sun.visible_glossy = False
    # a pale lavender sky dome from above / behind the camera for the faces turned towards us (light-linked to the garden)
    fd = bpy.data.lights.new("dawn_skyfill", "SUN")
    fd.energy = 1.6
    fd.color = (0.92, 0.88, 1.0)
    fd.angle = rad(80)
    fl = obj("dawn_skyfill", fd, g["C_FX"])
    fdir = Vector((0.2, -0.6, 0.78)).normalized()
    fl.rotation_euler = (-fdir).to_track_quat("-Z", "Y").to_euler()
    FILL_RC = bpy.data.collections.new("dawn_fill_receivers")
    FILL_RC.children.link(g["C_GARDEN"])
    fl.light_linking.receiver_collection = FILL_RC

    def tint(mat, rgb):
        """Multiply the base colour and the translucency colour of a material by rgb (inserted MULTIPLY mixes)."""
        t = mat.node_tree
        for nd in [n for n in t.nodes if n.type in ("BSDF_PRINCIPLED", "BSDF_TRANSLUCENT")]:
            sock = nd.inputs["Base Color" if nd.type == "BSDF_PRINCIPLED" else "Color"]
            if not sock.is_linked:
                continue
            src = sock.links[0].from_socket
            mul = t.nodes.new("ShaderNodeMix")
            mul.data_type, mul.blend_type = "RGBA", "MULTIPLY"
            mul.inputs["Factor"].default_value = 1.0
            ins = [s_ for s_ in mul.inputs if s_.type == "RGBA"]
            ins[1].default_value = tuple(rgb) + (1,)
            t.links.new(src, ins[0])
            t.links.new([s_ for s_ in mul.outputs if s_.type == "RGBA"][0], sock)

    # ───────── leaves: fresh spring backlight instead of golden yellow ─────────
    for mat in bpy.data.materials:
        if mat.name.startswith("leaf_") or mat.name == "hedge":
            for nd in mat.node_tree.nodes:
                if nd.type == "MIX" and getattr(nd, "blend_type", "") == "MULTIPLY":
                    ins = [s_ for s_ in nd.inputs if s_.type == "RGBA"]
                    if not ins[1].is_linked and ins[1].default_value[2] < 0.5:
                        ins[1].default_value = (0.78, 1.0, 0.72, 1)       # cooler: no yellow-beige under the mist

    # (after the backlight tint above: it would overwrite these MULTIPLY mixes)
    # the hedge (9 m) reads as the flat beige band behind the giant bubble: deeper and cooler, for contrast
    HG = env("SB_HEDGE", "0.45")
    for mn in ("hedge", "leaf_hedge"):
        if bpy.data.materials.get(mn):
            tint(bpy.data.materials[mn], (0.55 * HG, 0.72 * HG, 0.8 * HG))
    for mn in ("leaf_maple", "leaf_linden", "leaf_maple_dark", "leaf_linden_dark"):     # the hero tree's green leaves
        if bpy.data.materials.get(mn):
            tint(bpy.data.materials[mn], (0.7, 0.8, 0.8))

    # ───────── blossom cards ─────────
    BL_MAT = g["leaf_mat"]("leaf_blossom", "blossom_branch.png", value=1.25, trans=0.9)
    for nd in BL_MAT.node_tree.nodes:                                      # petals glow pink-white, not yellow, when backlit
        if nd.type == "MIX" and getattr(nd, "blend_type", "") == "MULTIPLY":
            ins = [s_ for s_ in nd.inputs if s_.type == "RGBA"]
            if not ins[1].is_linked:
                ins[1].default_value = (1.15, 0.98, 1.0, 1)
        if nd.type == "HUE_SAT":                                           # no hue jitter on the petals (it turns them salmon)
            for lk in list(nd.inputs["Hue"].links):
                BL_MAT.node_tree.links.remove(lk)
            nd.inputs["Hue"].default_value = 0.5
            nd.inputs["Saturation"].default_value = 0.75
    BL = g["card_mesh"]("card_blossom", BL_MAT)
    g["CARDS"]["blossom"] = BL
    # a deeper rose blossom for the far masses in the middle band (the pale petals there read as one flat cream patch)
    ROSE = BL_MAT.copy()
    ROSE.name = "leaf_blossom_rose"
    RV = env("SB_ROSE", "0.6")
    tint(ROSE, (0.95 * RV, 0.55 * RV, 0.72 * RV))
    BLR = g["card_mesh"]("card_blossom_rose", ROSE)
    g["CARDS"]["blossom_rose"] = BLR
    # the leaf screen in front of the sun, the near framing branches, the hero canopy and some ring trees bloom
    ring_ids = set()
    for ob in bpy.data.objects:
        if ob.type != "MESH" or ob.data is None or not ob.data.name.startswith("card_"):
            continue
        n = ob.name
        if n.startswith("screen_"):
            ob.data = BLR if rng2.random() < 0.6 else BL
        elif n.startswith("near"):
            ob.data = BL
        elif n.startswith(("hero_", "hero_low_")) and rng.random() < 0.75:
            ob.data = BL
        elif n.startswith("ring"):
            tid = n.split("_")[0]
            if tid[4:].isdigit() and int(tid[4:]) % 2 == 0 and rng.random() < 0.8:
                ob.data = BL
                ring_ids.add(tid)
    # out-of-focus blossom branches framing the top corners (1.8-3 m) and one low on the left (soft pink bokeh)
    C_BL = coll("blossom")
    FILL_RC.children.link(C_BL)
    NB = env("SB_BLOSSOM", "1.0")
    k = 0
    # (frame at 2.2 m: half-width 0.21 m, top edge z 1.47; the branches reach in from the corners)
    for (cx, cy, cz, rx, rz, n) in ((-0.26, 2.0, 1.40, 0.12, 0.10, 9), (0.27, 2.3, 1.44, 0.12, 0.10, 8),
                                    (-0.42, 3.2, 1.62, 0.18, 0.14, 7), (0.46, 3.5, 1.66, 0.2, 0.15, 6),
                                    (-0.30, 1.9, 1.00, 0.08, 0.10, 3), (0.34, 2.4, 0.95, 0.08, 0.10, 3)):
        for _ in range(max(1, int(n * NB))):
            p = Vector((cx + rng.uniform(-rx, rx), cy + rng.uniform(-0.25, 0.25), cz + rng.uniform(-rz, rz)))
            nr = Vector((rng.uniform(-0.5, 0.5), -1.0, rng.uniform(-0.3, 0.5)))
            g["place"](f"blossom_near{k}", BL, p, g["look_rot"](nr, rng.uniform(-math.pi, math.pi)), rng.uniform(0.32, 0.5), C_BL)
            k += 1
    # a pair of small blossom trees behind the hedge, right of centre (the frame's mid band: pink against the mist)
    for i, (x, y, zc) in enumerate(((3.0, 14.0, 3.2), (-4.2, 15.5, 3.0))):
        g["canopy"](f"bltree{i}", (x, y, zc), (1.6, 1.2, 1.3), 60, (0.7, 1.1), ["blossom", "blossom", "maple"], c=C_BL, hollow=0.2)
    # blossom masses across the centre band (frame at 14 m: x +-1.3, z -2..4): they hide the bright misty sky gap behind the
    # bubbles' column (which made them milky) and give the middle band shapes; darker maple between them for contrast.
    # The sky stays open only around the sun (upper left: canopy() keeps the sun window clear)
    if env("SB_MIDTREES", "1") > 0:
        for i, (x, y, zc, rx, rz, n) in enumerate(((0.3, 13.0, 2.9, 1.3, 1.0, 70), (1.5, 15.5, 2.0, 1.2, 1.1, 50),
                                                   (-1.2, 12.5, 1.8, 0.9, 0.8, 40), (-0.4, 16.5, 3.9, 1.4, 0.9, 50))):
            g["canopy"](f"blmid{i}", (x, y, zc), (rx, 0.8, rz), n, (0.6, 1.0),
                        ["blossom_rose", "blossom_rose", "blossom", "maple_dark", "linden_dark"], c=C_BL, hollow=0.15)
        # their dark trunks rising above the hedge: soft vertical darks behind the bubbles' column (contrast for the film)
        for i, (x, y, h, r0, ln) in enumerate(((-0.45, 11.5, 3.2, 0.16, 0.06), (0.75, 13.5, 3.4, 0.18, -0.05),
                                               (0.15, 16.0, 3.8, 0.15, 0.03))):
            g["trunk"](f"bltrunk{i}", x, y, h, r0, lean=(ln, 0))
    # one mid-focus blossom branch reaching in from the top-left corner (~1.45 m, just behind the wand's 1.2 m focus plane:
    # readable blossom shapes, backlit by the sun glow; it stays above the bubbles' column, y < 15 % of the frame).
    # Frame at distance d: half-width 0.0975 d, top edge z 1 + 0.212 d
    MBD = env("SB_MIDBRANCH", "1.45")                  # its distance from the camera (m); 0 = no branch
    if MBD > 0:
        for j in range(16):
            t = j / 15.0
            p = Vector((-0.19 + 0.15 * t + rng2.uniform(-0.015, 0.015), MBD + rng2.uniform(-0.06, 0.06),
                        1.0 + (MBD * 0.212) * (1.02 - 0.22 * t - 0.12 * t * t) + rng2.uniform(-0.02, 0.02)))
            nr = Vector((rng2.uniform(-0.4, 0.4), -1.0, rng2.uniform(-0.2, 0.4)))
            g["place"](f"blossom_mid{j}", BL, p, g["look_rot"](nr, rng2.uniform(-math.pi, math.pi)),
                       rng2.uniform(0.07, 0.11) * (1.0 - 0.35 * t), C_BL)

    # ───────── dewy lawn: wet coat + tiny glints ─────────
    lm = bpy.data.materials.get("lawn")
    if lm:
        b = next(n for n in lm.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
        b.inputs["Coat Weight"].default_value = 0.0
        b.inputs["Specular IOR Level"].default_value = 0.05      # grazing view: the sky's sheen made the lawn pale
        # a darker ground (about 2 stops): the lawn under the ring read as pale beige mist
        bc = b.inputs["Base Color"]
        if bc.is_linked:
            src = bc.links[0].from_socket
            mul = lm.node_tree.nodes.new("ShaderNodeMix")
            mul.data_type, mul.blend_type = "RGBA", "MULTIPLY"
            mul.inputs["Factor"].default_value = 1.0
            ins = [s_ for s_ in mul.inputs if s_.type == "RGBA"]
            ins[1].default_value = (env("SB_GROUND", "0.12"),) * 3 + (1,)
            lm.node_tree.links.new(src, ins[0])
            lm.node_tree.links.new([s_ for s_ in mul.outputs if s_.type == "RGBA"][0], bc)
        b.inputs["Sheen Weight"].default_value = 0.1
        b.inputs["Coat Roughness"].default_value = 0.12
        b.inputs["Sheen Tint"].default_value = (1.0, 0.92, 0.95, 1)
    DEW = env("SB_DEW", "0.75")
    if DEW > 0:
        dm = M("dew")
        dm.n.remove(dm.bsdf)
        de = dm.node("ShaderNodeEmission")
        de.inputs["Color"].default_value = hexc("#fff4ec")
        at = dm.node("ShaderNodeObjectInfo")
        dew_cam = dm.node("ShaderNodeAttribute", attribute_name="dew_gain", attribute_type="OBJECT")
        dm.link(dm.math("MULTIPLY", dm.math("MULTIPLY_ADD", at.outputs["Random"], 6.0 * DEW, 2.0 * DEW),
                        dm.math("MAXIMUM", dew_cam.outputs["Fac"], 1.0)), de.inputs["Strength"])
        dm.to_out(de.outputs[0])
        bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=1, radius=1.0)
        dmesh = bpy.context.object.data
        bpy.data.objects.remove(bpy.context.object)
        dmesh.materials.append(dm.m)
        C_DEW = coll("dew")
        k = 0
        while k < 90:
            y = rng.uniform(2.2, 9.0)
            x = rng.uniform(-0.75, 0.75) * y * 0.16 if rng.random() < 0.3 else rng.choice((-1, 1)) * rng.uniform(0.6, 4.0) * y * 0.1
            if abs(x) < 0.055 * y:               # the ring's column stays calm
                continue
            ob = obj(f"dew_{k}", dmesh, C_DEW)
            ob.location = (x, y, rng.uniform(0.01, 0.05))
            ob.scale = (rng.uniform(0.003, 0.006),) * 3
            ob["dew_gain"] = 6.0                 # in frame they become wide defocused discs: more energy to read at all
            ob.visible_shadow = ob.visible_diffuse = False
            k += 1
        # behind and around the camera too, for the bubbles' lawn
        for i in range(160):
            a, d = rng.uniform(0, 2 * math.pi), rng.uniform(0.8, 6.0)
            x, y = math.sin(a) * d, 1.2 + math.cos(a) * d
            if y > -0.2 and abs(x) < 0.12 * max(y, 0.0) + 0.15:    # out of the main frame only (the scatter above is in it)
                continue
            ob = obj(f"dew_env{i}", dmesh, C_DEW)
            ob.location = (x, y, rng.uniform(0.01, 0.04))
            ob.scale = (rng.uniform(0.002, 0.004),) * 3
            ob.visible_shadow = ob.visible_diffuse = False

    # ───────── aerial perspective: everything in the garden fades into the mist with distance ─────────
    # mix the surface shader towards an emission of the mist colour: fac = (1 - exp(-d / D)) * cap, d = camera distance,
    # brighter towards the sun (forward scattering). Alpha cards keep their transparency (the haze goes into the opaque branch)
    D = 30.0 / max(MIST, 1e-3)
    FWD = env("SB_FWD", "0.2")
    sun_t = tuple(sun_dir)

    def hazify(mat):
        t = mat.node_tree
        out = next((n for n in t.nodes if n.type == "OUTPUT_MATERIAL"), None)
        if not out or not out.inputs["Surface"].is_linked:
            return
        src = out.inputs["Surface"].links[0].from_node
        target = out.inputs["Surface"]
        if src.type == "MIX_SHADER" and src.inputs[1].is_linked and src.inputs[1].links[0].from_node.type == "BSDF_TRANSPARENT":
            target = src.inputs[2]
        if not target.is_linked:
            return
        S = target.links[0].from_socket
        L = t.links.new
        cam = t.nodes.new("ShaderNodeCameraData")
        geo = t.nodes.new("ShaderNodeNewGeometry")

        def mth(op, a, b=None, c=None):
            n = t.nodes.new("ShaderNodeMath")
            n.operation = op
            for i, x in enumerate((a, b, c)):
                if x is None:
                    continue
                if isinstance(x, (int, float)):
                    n.inputs[i].default_value = x
                else:
                    L(x, n.inputs[i])
            return n.outputs[0]
        dd = mth("MAXIMUM", mth("SUBTRACT", cam.outputs["View Distance"], 2.5), 0.0)            # clear air for the first metres
        fac = mth("MULTIPLY", mth("SUBTRACT", 1.0, mth("EXPONENT", mth("DIVIDE", dd, -D))), 0.9)
        dt = t.nodes.new("ShaderNodeVectorMath")
        dt.operation = "DOT_PRODUCT"
        L(geo.outputs["Incoming"], dt.inputs[0])
        dt.inputs[1].default_value = tuple(-c for c in sun_t)              # -incoming . sun
        fwd = mth("EXPONENT", mth("DIVIDE", mth("SUBTRACT", dt.outputs["Value"], 1.0), 0.03))
        em = t.nodes.new("ShaderNodeEmission")
        em.inputs["Color"].default_value = MIST_COL
        gain = env("SB_LAWN_HAZE", "0.25") if mat.name == "lawn" else 1.0
        L(mth("MULTIPLY", mth("MULTIPLY_ADD", fwd, FWD, 1.0), 0.75 * SKY * gain), em.inputs["Strength"])
        mx = t.nodes.new("ShaderNodeMixShader")
        L(fac, mx.inputs[0])
        L(S, mx.inputs[1])
        L(em.outputs[0], mx.inputs[2])
        L(mx.outputs[0], target)

    wand_mats = {"plastic_pink", "plastic_pink_ring", "plastic_mint", "dew"}
    for mat in list(bpy.data.materials):
        if mat.use_nodes and mat.name not in wand_mats and not mat.name.startswith("glint"):
            hazify(mat)

    # ───────── the wand: soft dawn light, wet coat ─────────
    ring_c = g["RING_C"]
    WK = env("SB_WAND_KEY", "1.0")
    # broad sources only: a lavender sky fill from above-front, a big peach key up-left (the low sun through mist, from
    # behind: a rim), a soft pink-white bounce from the camera side (no small keys: those made the blocky highlights)
    for name, col, energy, size, loc in (("wand_fill", (0.80, 0.80, 1.0), 9.0, 1.2, (-0.3, 0.2, 2.0)),
                                         ("wand_key", (1.0, 0.86, 0.80), 10.0 * WK, 0.8, (-0.75, 0.35, 1.55)),
                                         ("wand_rim", (1.0, 0.80, 0.66), 14.0, 0.6, (-0.25, 2.2, 1.45)),
                                         ("wand_kick", (0.85, 0.82, 1.0), 6.0, 0.6, (0.7, 1.6, 1.3))):
        lo = bpy.data.objects.get(name)
        if lo:
            lo.data.color = col
            lo.data.energy = energy
            lo.data.size = size
            lo.location = loc
            lo.rotation_euler = (ring_c - Vector(loc)).normalized().to_track_quat("-Z", "Y").to_euler()
    WET = env("SB_WAND_WET", "1.0") > 0
    if WET:
        for mat in [bpy.data.materials.get(n) for n in ("plastic_pink", "plastic_pink_ring", "plastic_mint")]:
            if not mat:
                continue
            nt_ = mat.node_tree
            b = next(n for n in nt_.nodes if n.type == "BSDF_PRINCIPLED")
            b.inputs["Coat Weight"].default_value = 1.0
            b.inputs["Coat Roughness"].default_value = 0.04
            b.inputs["Specular IOR Level"].default_value = 0.05                 # the wet coat reflects, not a milky base
            worn = next(n for n in nt_.nodes if n.type == "MAP_RANGE")
            worn.inputs["To Min"].default_value, worn.inputs["To Max"].default_value = 0.22, 0.30
            # smooth liquid film: the coat takes the plain shading normal (no ridges / speckle under it), the base loses the
            # fine speckle bump (pixel-sized highlight patches) but keeps the moulded ridges
            for lk in list(b.inputs["Coat Normal"].links):
                nt_.links.remove(lk)
            for bn in [n for n in nt_.nodes if n.type == "BUMP" and abs(n.inputs["Strength"].default_value - 0.08) < 1e-6]:
                bn.inputs["Strength"].default_value = 0.0
        # a large, soft bright patch of morning sky behind the camera, up-left: one smooth streak along the wet coat
        wd = bpy.data.lights.new("wand_window", "AREA")
        wd.shape = "ELLIPSE"
        wd.size, wd.size_y = 1.1, 0.8
        wd.energy = 90.0 * env("SB_WAND_WINDOW", "1.0")
        wd.color = (1.0, 0.93, 0.92)
        wl = obj("wand_window", wd, g["C_FX"])
        wl.location = (-0.9, -1.6, 2.2)
        wl.rotation_euler = (ring_c - wl.location).normalized().to_track_quat("-Z", "Y").to_euler()
        wl.visible_camera = wl.visible_diffuse = wl.visible_transmission = wl.visible_volume_scatter = False
        wl.light_linking.receiver_collection = g["C_WAND"]

    print("DAWN blossom trees", sorted(ring_ids))
    return {"look": "dawn", "sun_dir": list(sun_dir), "sun_el": SUN_EL, "sun_az": SUN_AZ}
