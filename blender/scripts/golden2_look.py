# Golden hour v2 ("backlit park at sunset, 85 mm f/2") for build_scene.py: called with SB_LOOK=golden2 once the golden
# garden is built. Same garden, camera, sun direction and wand; what changes (the v1 golden look read as a murky
# olive / mustard wash with flat yellow blobs and a huge blown sun in the bubbles):
#   - world: a painted sky instead of the physical one: warm amber-peach at the horizon -> pale gold -> cream -> soft
#     dusty blue overhead, warmer on the sun's side, cooler behind the camera. The sun is a SMALL hot core (~0.6 deg) with
#     a modest halo, so the bubbles mirror a small bright highlight, not a blown disc
#   - a warm sun lamp (amber, 1.2 deg) does the lighting; the sky gives a cool fill, so shadows stay rich and slightly blue
#     instead of olive
#   - aerial perspective (as in dawn_look.py): every garden material fades with camera distance towards a haze colour
#     that is warm amber towards the sun (forward scattering, brighter) and dusty blue-lilac away from it. Depth, and the
#     ring of trees in the env stops reading as a saturated green strip
#   - leaves: backlight tint turned from lemon yellow-green to a warmer gold, slightly darker and less saturated base
#   - bokeh: the glints recoloured to cream / peach / amber and kept below clipping, so the discs keep the lens texture
#   - the lens (as in night_look.py): a round aperture (creamy discs), an aperture filter (bright rims + faint onion rings) and a
#     barrel stop (cat-eyes towards the frame edges)
#   - the two cosmos clumps near the lens go (loud magenta blobs next to the ring)
# Knobs (env vars): SB_EXPOSURE SB_WB SB_SKY (sky gain) SB_SUNCORE (core gain) SB_HALO (halo gain) SB_SUN (lamp gain)
#   SB_HAZE2 (haze density) SB_GLINT (glint gain) SB_LEAF (leaf value) SB_RIM SB_ONION SB_CATEYE SB_BLADES
import bpy, bmesh, math, os
from mathutils import Vector

rad = math.radians


def apply(g):
    sc = g["sc"]
    M, hexc, obj = g["M"], g["hexc"], g["obj"]
    env = lambda k, d: float(os.environ.get(k, d))
    sun_dir = Vector(g["SUN_DIR"])
    SKY = env("SB_SKY", "1.0")

    # ───────── colour management: neutral-warm, contrast from the light, not from a yellow white balance ─────────
    sc.view_settings.exposure = env("SB_EXPOSURE", "1.35")
    for look in ("AgX - Medium High Contrast", "AgX - Base Contrast", "None"):
        try:
            sc.view_settings.look = look
            break
        except TypeError:
            continue
    if hasattr(sc.view_settings, "use_white_balance"):
        sc.view_settings.use_white_balance = True
        sc.view_settings.white_balance_temperature = env("SB_WB", "6000")
    sc.cycles.sample_clamp_indirect = 4.0

    # ───────── remove the loud cosmos next to the lens and the haze volume ─────────
    for ob in [o for o in bpy.data.objects if o.name in ("flowers_7", "flowers_8", "haze")]:
        bpy.data.objects.remove(ob)

    # ───────── world: painted golden-hour sky with a small sun ─────────
    world = bpy.data.worlds.new("golden2_sky")
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
    # the frame's sky is the lowest ~12 deg (z 0..0.2): amber -> gold -> cream there, the blue only overhead
    stops = [(0.0, "#ffaa5c"), (0.03, "#ffbc78"), (0.07, "#fccb94"), (0.12, "#efd2b0"), (0.2, "#c9cdd0"),
             (0.4, "#9fb6d4"), (1.0, "#7f9ccc")]
    el = ramp.color_ramp.elements
    for i, (p, c) in enumerate(stops):
        e = el[i] if i < len(el) else el.new(p)
        e.position, e.color = p, hexc(c)
    link(z, ramp.inputs["Fac"])
    sky = ramp.outputs["Color"]
    dsun = node("ShaderNodeVectorMath", operation="DOT_PRODUCT")
    link(nrm.outputs["Vector"], dsun.inputs[0])
    dsun.inputs[1].default_value = tuple(sun_dir)
    cosg = dsun.outputs["Value"]
    side = math_("MULTIPLY", math_("ADD", cosg, 1.0), 0.5)                      # 0 behind .. 1 at the sun
    # warmer, richer amber on the sun's side; a cool dusty blue low in the sky behind the camera
    sky = mixc(math_("MULTIPLY", math_("POWER", side, 4.0), 0.45), sky, hexc("#ffa95e"))
    sky = mixc(math_("MULTIPLY", math_("POWER", math_("SUBTRACT", 1.0, side), 2.0), 0.55), sky, hexc("#a7b3cc"))
    # below the horizon (the world under the lawn's edge): a dark warm ground
    below = math_("LESS_THAN", sep.outputs["Z"], 0.0)
    sky = mixc(below, sky, hexc("#4a3a2a"))
    # the sun: a small hot core and a modest halo (the env keeps only a few pixels clipped)
    CORE, HALO = env("SB_SUNCORE", "1.0"), env("SB_HALO", "1.0")
    core = math_("EXPONENT", math_("DIVIDE", math_("SUBTRACT", cosg, 1.0), 0.00005))     # ~0.6 deg
    halo = math_("EXPONENT", math_("DIVIDE", math_("SUBTRACT", cosg, 1.0), 0.0007))      # ~2 deg
    wide = math_("EXPONENT", math_("DIVIDE", math_("SUBTRACT", cosg, 1.0), 0.012))       # ~9 deg
    glow = math_("ADD", math_("ADD", math_("MULTIPLY", core, 60.0 * CORE), math_("MULTIPLY", halo, 1.6 * HALO)),
                 math_("MULTIPLY", wide, 0.55 * HALO))
    sky = mixc(glow, sky, hexc("#ffdcae"), blend="ADD")
    # camera rays (bg and env) see a soft-clipped copy: c / (1 + c / K) keeps the leaf-gap bokeh sampleable
    K = env("SB_SKY_CLIP", "14")
    lp = node("ShaderNodeLightPath")
    vdiv = node("ShaderNodeVectorMath", operation="SCALE")
    link(sky, vdiv.inputs[0])
    vdiv.inputs["Scale"].default_value = 1.0 / K
    vadd = node("ShaderNodeVectorMath", operation="ADD")
    link(vdiv.outputs[0], vadd.inputs[0])
    vadd.inputs[1].default_value = (1, 1, 1)
    vq = node("ShaderNodeVectorMath", operation="DIVIDE")
    link(sky, vq.inputs[0])
    link(vadd.outputs[0], vq.inputs[1])
    sky = mixc(lp.outputs["Is Camera Ray"], sky, vq.outputs[0])
    link(sky, bg.inputs["Color"])
    bg.inputs["Strength"].default_value = 0.8 * SKY

    # ───────── warm sun lamp (the lighting; the sky is the cool fill) ─────────
    sd = bpy.data.lights.new("golden2_sun", "SUN")
    sd.energy = 3.2 * env("SB_SUN", "1.0")
    sd.color = (1.0, 0.70, 0.42)
    sd.angle = rad(1.2)
    sun = obj("golden2_sun", sd, g["C_FX"])
    sun.rotation_euler = (-sun_dir).to_track_quat("-Z", "Y").to_euler()

    # ───────── leaves: gold backlight instead of lemon, a touch darker ─────────
    LEAF = env("SB_LEAF", "0.75")
    for mat in bpy.data.materials:
        if mat.name.startswith("leaf_") or mat.name == "hedge":
            for nd in mat.node_tree.nodes:
                if nd.type == "MIX" and getattr(nd, "blend_type", "") == "MULTIPLY":
                    ins = [s_ for s_ in nd.inputs if s_.type == "RGBA"]
                    if not ins[1].is_linked and ins[1].default_value[2] < 0.5:
                        ins[1].default_value = (1.25, 0.95, 0.46, 1)
                if nd.type == "HUE_SAT":
                    nd.inputs["Saturation"].default_value = 0.8
                if nd.type == "MATH" and nd.operation == "MULTIPLY_ADD" and nd.inputs[0].is_linked \
                        and nd.inputs[0].links[0].from_node.type == "OBJECT_INFO" and abs(nd.inputs[1].default_value - 0.5) < 1e-6:
                    nd.inputs[1].default_value *= LEAF
                    nd.inputs[2].default_value *= LEAF

    # ───────── bokeh glints: cream / peach / amber, below clipping ─────────
    GL = env("SB_GLINT", "1.0")
    pal = [hexc("#ffc77a"), hexc("#ffb066"), hexc("#ffd59a"), hexc("#ff9f5a"), hexc("#ffe2b4")]
    for i, ob in enumerate(o for o in bpy.data.objects if o.name.startswith("glint_")):
        for slot in ob.material_slots:
            m = slot.material
            if not m:
                continue
            e = next((n for n in m.node_tree.nodes if n.type == "EMISSION"), None)
            if e:
                e.inputs["Color"].default_value = pal[i % len(pal)]
                e.inputs["Strength"].default_value *= GL

    # ───────── aerial perspective: warm towards the sun, dusty blue away from it ─────────
    D = 60.0 / max(env("SB_HAZE2", "1.0"), 1e-3)
    HAZE_SUN, HAZE_BACK = hexc("#ffae78"), hexc("#a9b2c6")
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
        dd = mth("MAXIMUM", mth("SUBTRACT", cam.outputs["View Distance"], 3.0), 0.0)
        fac = mth("MULTIPLY", mth("SUBTRACT", 1.0, mth("EXPONENT", mth("DIVIDE", dd, -D))), 0.5)
        dt = t.nodes.new("ShaderNodeVectorMath")
        dt.operation = "DOT_PRODUCT"
        L(geo.outputs["Incoming"], dt.inputs[0])
        dt.inputs[1].default_value = tuple(-c for c in sun_t)              # -incoming . sun
        cs = dt.outputs["Value"]
        side = mth("MULTIPLY", mth("ADD", cs, 1.0), 0.5)
        fwd = mth("EXPONENT", mth("DIVIDE", mth("SUBTRACT", cs, 1.0), 0.04))
        mixn = t.nodes.new("ShaderNodeMix")
        mixn.data_type = "RGBA"
        L(mth("POWER", side, 2.0), mixn.inputs["Factor"])
        cins = [s_ for s_ in mixn.inputs if s_.type == "RGBA"]
        cins[0].default_value, cins[1].default_value = HAZE_BACK, HAZE_SUN
        em = t.nodes.new("ShaderNodeEmission")
        L([s_ for s_ in mixn.outputs if s_.type == "RGBA"][0], em.inputs["Color"])
        L(mth("MULTIPLY", mth("MULTIPLY_ADD", fwd, 1.3, mth("MULTIPLY_ADD", side, 0.35, 0.25)), 0.8 * SKY), em.inputs["Strength"])
        mx = t.nodes.new("ShaderNodeMixShader")
        L(fac, mx.inputs[0])
        L(S, mx.inputs[1])
        L(em.outputs[0], mx.inputs[2])
        L(mx.outputs[0], target)

    skip = {"plastic_pink", "plastic_pink_ring", "plastic_mint"}
    for mat in list(bpy.data.materials):
        if mat.use_nodes and mat.name not in skip and not mat.name.startswith("glint"):
            hazify(mat)

    # ───────── the lens: 9 blades, aperture filter (rims, onion rings), barrel stop (cat-eyes) ─────────
    cam = sc.camera
    cdat = cam.data
    BLADES = int(env("SB_BLADES", "0"))
    cdat.dof.aperture_blades = BLADES if BLADES >= 3 else 0
    cdat.dof.aperture_rotation = rad(env("SB_BLADE_ROT", "12"))
    cdat.clip_start = 0.001
    A = cdat.lens / 1000.0 / (2 * cdat.dof.aperture_fstop)
    RIM, ONION, CATEYE = env("SB_RIM", "0.35"), env("SB_ONION", "0.14"), env("SB_CATEYE", "1.45")

    def lens_part(name, me, mat):
        me.materials.append(mat)
        ob = obj(name, me, g["C_FX"])
        ob.parent = cam
        ob["lens_only"] = 1
        for v in ("visible_diffuse", "visible_glossy", "visible_transmission", "visible_volume_scatter", "visible_shadow"):
            setattr(ob, v, False)
        return ob

    def disc_mesh(name, r_in, r_out, zz, seg=128):
        bm_ = bmesh.new()
        ring_in, ring_out = [], []
        for i in range(seg):
            a = 2 * math.pi * i / seg
            if r_in > 0:
                ring_in.append(bm_.verts.new((r_in * math.cos(a), r_in * math.sin(a), zz)))
            ring_out.append(bm_.verts.new((r_out * math.cos(a), r_out * math.sin(a), zz)))
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
        fm = M("lens_filter")
        fm.n.remove(fm.bsdf)
        oc = fm.node("ShaderNodeTexCoord")
        sepo = fm.node("ShaderNodeSeparateXYZ")
        fm.link(oc.outputs["Object"], sepo.inputs[0])
        rr = fm.math("DIVIDE", fm.math("SQRT", fm.math("ADD", fm.math("MULTIPLY", sepo.outputs[0], sepo.outputs[0]),
                                                           fm.math("MULTIPLY", sepo.outputs[1], sepo.outputs[1]))), A)
        rim = fm.node("ShaderNodeMapRange", interpolation_type="SMOOTHSTEP")
        rim.inputs["From Min"].default_value, rim.inputs["From Max"].default_value = 0.5, 1.0
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
        sm = M("lens_stop")
        sm.n.remove(sm.bsdf)
        e_ = sm.node("ShaderNodeEmission")
        e_.inputs["Strength"].default_value = 0.0
        sm.to_out(e_.outputs[0])
        lens_part("lens_stop", disc_mesh("lens_stop", A * CATEYE, 0.3, -0.10), sm.m)

    # ───────── the wand: warm sun rim from behind, cool sky fill from the front ─────────
    ring_c = g["RING_C"]
    for name, col, energy, size, loc in (("wand_fill", (0.86, 0.90, 1.0), 10.0, 0.9, (-0.45, 0.3, 1.6)),
                                         ("wand_key", (1.0, 0.90, 0.80), 3.0, 0.08, None),
                                         ("wand_rim", (1.0, 0.70, 0.40), 12.0, 0.2, None),
                                         ("wand_kick", (1.0, 0.76, 0.50), 5.0, 0.25, None)):
        lo = bpy.data.objects.get(name)
        if lo:
            lo.data.color = col
            lo.data.energy = energy
            lo.data.size = size
            if loc:
                lo.location = loc
                lo.rotation_euler = (ring_c - Vector(loc)).normalized().to_track_quat("-Z", "Y").to_euler()

    return {"look": "golden2"}
