# Studio look ("macro studio") for build_scene.py: called with SB_LOOK=studio once the golden garden is built.
# Classic soap-bubble macro photography: a black velvet backdrop and one big softbox, so the thin-film colours glow on black.
# Same camera and wand; what changes:
#   - the garden (and every other non-wand object / light) is removed; the world is pure black
#   - key: a 1.2 x 1.6 m rectangular softbox (5000 K, warm-neutral) 2.2 m from the bubble position, up-left behind the camera
#     (azimuth -25 deg from the camera-facing direction, elevation +17 deg). An emissive panel with a soft-edged, slightly
#     centre-weighted face (like a real diffuser) rather than a flat area light: it is what the bubbles and the wand mirror
#   - an optional thin vertical strip light behind the camera on the right (a second, narrow catchlight)
#   - a black velvet backdrop 5 m behind the wand, grazed by a weak, very broad spot: a faint far glow so it is not flat black
#   - the wand: wet clear coat like night_look.py (SB_WAND_WET), lit by the softbox itself (its own light-linked lights removed)
# Knobs (env vars): SB_EXPOSURE SB_SOFTBOX (softbox radiance) SB_STRIP (strip radiance, 0 = none) SB_GLOW (backdrop glow)
#   SB_WAND_WET (0 = dry) SB_WAND_MENISCUS SB_WAND_BASE_SPEC
import bpy, math, os
from mathutils import Vector

rad = math.radians

SOFT_AZ, SOFT_EL, SOFT_D = -25.0, 17.0, 2.2       # from the bubble position; azimuth 0 = towards the camera, - = left
SOFT_W, SOFT_H = 1.2, 1.6
STRIP_AZ, STRIP_EL, STRIP_D = 38.0, 4.0, 2.0
STRIP_W, STRIP_H = 0.14, 1.3


def k5000():
    # 5000 K blackbody in linear Rec.709, normalised to max 1 (warm-neutral)
    return (1.0, 0.894, 0.807)


def apply(g):
    sc = g["sc"]
    M, obj = g["M"], g["obj"]
    env = lambda k, d: float(os.environ.get(k, d))
    BUB = Vector(g["BUBBLE_POS"])
    RING_C = g["RING_C"]
    C_WAND, C_FX = g["C_WAND"], g["C_FX"]

    sc.view_settings.exposure = env("SB_EXPOSURE", "0.0")
    if hasattr(sc.view_settings, "use_white_balance"):
        sc.view_settings.use_white_balance = False
    sc.cycles.sample_clamp_indirect = 4.0

    # ───────── strip the garden: keep the wand, the cameras ─────────
    keep = set(C_WAND.all_objects) | {g["cam"], g["envcam"]}
    for ob in [o for o in bpy.data.objects if o not in keep]:
        bpy.data.objects.remove(ob)

    # ───────── world: black ─────────
    world = bpy.data.worlds.new("studio_black")
    sc.world = world
    bgn = next(n for n in world.node_tree.nodes if n.type == "BACKGROUND")
    bgn.inputs["Color"].default_value = (0, 0, 0, 1)
    bgn.inputs["Strength"].default_value = 0.0

    def sph(az, el):
        # azimuth 0 = from the bubble towards the camera (-y), negative = camera-left (-x)
        return Vector((math.sin(rad(az)) * math.cos(rad(el)), -math.cos(rad(az)) * math.cos(rad(el)), math.sin(rad(el))))

    def panel(name, centre, w, h, strength, col, edge, falloff):
        """Emissive rectangle facing the bubble: flat-ish diffuser face, soft rounded edges (edge = feather in uv units),
        a slight centre hot spot (falloff) and a faint darker frame, like a photographed softbox."""
        bpy.ops.mesh.primitive_plane_add(size=1.0)
        ob = bpy.context.object
        ob.name = name
        for cl in ob.users_collection:
            cl.objects.unlink(ob)
        C_FX.objects.link(ob)
        ob.scale = (w, h, 1)
        ob.location = centre
        # plane normal (+z) towards the bubble, local y stays up
        ob.rotation_euler = (BUB - centre).normalized().to_track_quat("Z", "Y").to_euler()
        m = M(name)
        m.n.remove(m.bsdf)
        tc = m.node("ShaderNodeTexCoord")
        sep = m.node("ShaderNodeSeparateXYZ")
        m.link(tc.outputs["UV"], sep.inputs[0])

        def axis(s):                                   # 0 at the edge -> 1 inside, smooth feather
            d = m.math("MINIMUM", s, m.math("SUBTRACT", 1.0, s))
            mr = m.node("ShaderNodeMapRange", interpolation_type="SMOOTHSTEP")
            mr.inputs["From Min"].default_value, mr.inputs["From Max"].default_value = 0.0, edge
            m.link(d, mr.inputs["Value"])
            return mr.outputs[0], d
        ax, dx = axis(sep.outputs["X"])
        ay, dy = axis(sep.outputs["Y"])
        mask = m.math("MULTIPLY", ax, ay)
        # centre weighting: 1 in the middle -> 1 - falloff at the edges
        cx = m.math("SUBTRACT", sep.outputs["X"], 0.5)
        cy = m.math("SUBTRACT", sep.outputs["Y"], 0.5)
        r2 = m.math("ADD", m.math("MULTIPLY", cx, cx), m.math("MULTIPLY", cy, cy))
        hot = m.math("SUBTRACT", 1.0, m.math("MULTIPLY", r2, falloff * 2.0))
        st = m.math("MULTIPLY", m.math("MULTIPLY", mask, hot), strength)
        em = m.node("ShaderNodeEmission")
        em.inputs["Color"].default_value = col + (1,)
        m.link(st, em.inputs["Strength"])
        tr = m.node("ShaderNodeBsdfTransparent")
        # outside the feathered face the panel is see-through (no hard black card edge in the reflections)
        mix = m.node("ShaderNodeMixShader")
        m.link(m.math("MINIMUM", m.math("MULTIPLY", mask, 8.0), 1.0), mix.inputs["Fac"])
        m.link(tr.outputs[0], mix.inputs[1])
        m.link(em.outputs[0], mix.inputs[2])
        m.to_out(mix.outputs[0])
        ob.data.materials.append(m.m)
        ob.visible_shadow = False
        return ob

    # ───────── key: the softbox ─────────
    SOFT = env("SB_SOFTBOX", "9.0")
    soft_c = BUB + sph(SOFT_AZ, SOFT_EL) * SOFT_D
    panel("softbox", soft_c, SOFT_W, SOFT_H, SOFT, k5000(), 0.06, 0.35)
    STRIP = env("SB_STRIP", "2.5")
    if STRIP > 0:
        panel("strip", BUB + sph(STRIP_AZ, STRIP_EL) * STRIP_D, STRIP_W, STRIP_H, STRIP, (1.0, 0.93, 0.86), 0.2, 0.2)

    # ───────── backdrop: black velvet, a faint far glow ─────────
    bpy.ops.mesh.primitive_plane_add(size=1.0)
    bd = bpy.context.object
    bd.name = "backdrop"
    for cl in bd.users_collection:
        cl.objects.unlink(bd)
    C_FX.objects.link(bd)
    bd.scale = (14, 10, 1)
    bd.location = (0, 6.2, 1.6)
    bd.rotation_euler = (rad(90), 0, 0)
    vm = M("velvet")
    b = vm.bsdf
    b.inputs["Base Color"].default_value = (0.012, 0.011, 0.011, 1)
    b.inputs["Roughness"].default_value = 1.0
    b.inputs["Specular IOR Level"].default_value = 0.0
    b.inputs["Sheen Weight"].default_value = 0.6
    b.inputs["Sheen Roughness"].default_value = 0.6
    b.inputs["Sheen Tint"].default_value = (0.20, 0.19, 0.18, 1)
    bd.data.materials.append(vm.m)
    bd["lens_only"] = 1                                  # render_passes.py hides it in the env pass: the env is black
    GLOW = env("SB_GLOW", "0.5")
    if GLOW > 0:
        sd = bpy.data.lights.new("backdrop_glow", "SPOT")
        sd.energy = 900.0 * GLOW
        sd.color = (1.0, 0.92, 0.84)
        sd.spot_size = rad(70)
        sd.spot_blend = 1.0
        sd.shadow_soft_size = 0.5
        sl = obj("backdrop_glow", sd, C_FX)
        sl.location = (-0.4, 3.4, 2.2)
        tgt = Vector((-0.3, 6.2, 2.7))
        sl.rotation_euler = (tgt - sl.location).normalized().to_track_quat("-Z", "Y").to_euler()
        sl.light_linking.receiver_collection = bpy.data.collections.new("backdrop_only")
        sl.light_linking.receiver_collection.objects.link(bd)

    # ───────── the wand: only the studio lights (its own light-linked garden lights are gone) ─────────
    # wet clear coat, as in night_look.py (SB_WAND_WET=0 keeps the dry plastic)
    WET = env("SB_WAND_WET", "1.0") > 0
    BASE_SPEC = env("SB_WAND_BASE_SPEC", "0.03")
    MENISCUS = env("SB_WAND_MENISCUS", "0.6")
    if WET:
        for mat in [bpy.data.materials.get(n) for n in ("plastic_pink", "plastic_pink_ring", "plastic_mint")]:
            if not mat:
                continue
            nt_, ln = mat.node_tree, mat.node_tree.links.new
            b = next(n for n in nt_.nodes if n.type == "BSDF_PRINCIPLED")
            b.inputs["Coat Weight"].default_value = 1.0
            b.inputs["Coat Roughness"].default_value = 0.05
            b.inputs["Specular IOR Level"].default_value = BASE_SPEC
            worn = next(n for n in nt_.nodes if n.type == "MAP_RANGE")
            worn.inputs["To Min"].default_value, worn.inputs["To Max"].default_value = 0.20, 0.30
            # smooth liquid film: the coat takes the plain shading normal, the base loses the fine speckle bump
            if mat.name != "plastic_pink_ring":
                for lk in list(b.inputs["Coat Normal"].links):
                    nt_.links.remove(lk)
            for bn in [n for n in nt_.nodes if n.type == "BUMP" and abs(n.inputs["Strength"].default_value - 0.08) < 1e-6]:
                bn.inputs["Strength"].default_value = 0.0
            if mat.name != "plastic_pink_ring":
                continue
            # meniscus on the ring's inner edge: the coat normal bends towards the film plane, so the band catches the
            # softbox behind the camera as a thin bright crescent
            tco = nt_.nodes.new("ShaderNodeTexCoord")
            sep_ = nt_.nodes.new("ShaderNodeSeparateXYZ")
            ln(tco.outputs["Object"], sep_.inputs[0])
            cxy = nt_.nodes.new("ShaderNodeCombineXYZ")
            ln(sep_.outputs["X"], cxy.inputs["X"])
            ln(sep_.outputs["Y"], cxy.inputs["Y"])
            rho = nt_.nodes.new("ShaderNodeVectorMath")
            rho.operation = "LENGTH"
            ln(cxy.outputs[0], rho.inputs[0])
            band = nt_.nodes.new("ShaderNodeMapRange")
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
            mixr = nt_.nodes.new("ShaderNodeMix")
            mixr.data_type = "FLOAT"
            ln(wet, mixr.inputs["Factor"])
            ln(worn.outputs[0], mixr.inputs["A"])
            mixr.inputs["B"].default_value = 0.12
            ln(mixr.outputs[0], b.inputs["Roughness"])
            ln(lerp(wet, BASE_SPEC, 0.35), b.inputs["Specular IOR Level"])
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
            for lk in list(b.inputs["Coat Normal"].links):
                nt_.links.remove(lk)
            ln(to_w.outputs[0], b.inputs["Coat Normal"])

    d = (soft_c - BUB)
    ang_w = 2 * math.atan(SOFT_W / 2 / d.length)
    ang_h = 2 * math.atan(SOFT_H / 2 / d.length)
    print(f"STUDIO softbox centre {tuple(round(v, 3) for v in soft_c)} az {SOFT_AZ} el {SOFT_EL} "
          f"angular {ang_w:.3f} x {ang_h:.3f} rad")
    return {"look": "studio", "key_pos": list(soft_c), "key_name": "softbox",
            "softbox": {"az_deg": SOFT_AZ, "el_deg": SOFT_EL, "dist_m": SOFT_D, "size_m": [SOFT_W, SOFT_H],
                        "angular_rad": [round(ang_w, 4), round(ang_h, 4)]}}
