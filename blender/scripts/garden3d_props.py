"""Generate cute stylised 3D garden props as GLB files for the three.js garden.

Run headless:
  Blender -b --factory-startup -P blender/scripts/garden3d_props.py [-- options]

Options (after "--"):
  --only a,b        build only these props (manifest is merged with the existing one)
  --preview PATH    where to write the contact sheet (default: blender/renders/garden3d_props_preview.png)
  --no-preview      skip the contact sheet render
  --validate        do not build: re-import every GLB and print checks

Contract (the app loader depends on it):
  * metres, Y-up GLB (exporter converts Blender Z-up), origin at the centre of the base on the ground
    (exception: the wand, whose origin is the ring centre and whose ring axis is +Z in three.js);
  * colour lives in COLOR_0 (linear vertex colour, AO and sun gradient baked in) times a white base colour; one mesh +
    one material per prop. Exception: the daisy heads carry TEXCOORD_0 into the painted head atlas
    (app/assets/garden3d/tex/daisy_petals.png, cell-local uv: centre 0.5, rim 0/1), every other vertex of the prop has
    uv (−1, −1) so the app can tell head from stem; the GLB itself references no image;
  * every prop is built procedurally as plain vertex/face lists, so there are no modifiers to apply.
"""

import bpy
import bmesh
import json
import math
import os
import random
import struct
import sys

from mathutils import Matrix, Vector, noise
from mathutils.bvhtree import BVHTree

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
OUT_DIR = os.path.join(ROOT, "app", "assets", "garden3d", "models")
DEFAULT_PREVIEW = os.path.join(ROOT, "blender", "renders", "garden3d_props_preview.png")

ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def arg_value(flag, default=None):
    if flag in ARGS:
        i = ARGS.index(flag)
        if i + 1 < len(ARGS):
            return ARGS[i + 1]
    return default


TAU = 2.0 * math.pi
WHITE = (1.0, 1.0, 1.0)


# ---------------------------------------------------------------------------
# Colour helpers (all colours are handled in sRGB, converted to linear on write)
# ---------------------------------------------------------------------------

def hexc(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))


def srgb_to_lin(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def mix(a, b, t):
    t = max(0.0, min(1.0, t))
    return tuple(x + (y - x) * t for x, y in zip(a, b))


def mul(a, s):
    if isinstance(s, (int, float)):
        return tuple(x * s for x in a)
    return tuple(x * y for x, y in zip(a, s))


def smoothstep(e0, e1, x):
    t = max(0.0, min(1.0, (x - e0) / (e1 - e0)))
    return t * t * (3.0 - 2.0 * t)


def clamp_col(c):
    return tuple(max(0.0, min(1.0, x)) for x in c)


# ---------------------------------------------------------------------------
# Geometry container
# ---------------------------------------------------------------------------

NO_UV = (-1.0, -1.0)


class Part:
    """Plain geometry: vertex positions, faces (index tuples) and one sRGB colour per vertex."""

    def __init__(self, v=None, f=None, c=None, uv=None):
        self.v = v if v is not None else []
        self.f = f if f is not None else []
        self.c = c if c is not None else [WHITE] * len(self.v)
        self.uv = uv  # optional per-vertex (u, v); parts without one get (−1, −1) when merged with one that has

    def add(self, other):
        off = len(self.v)
        if self.uv is not None or other.uv is not None:
            mine = self.uv if self.uv is not None else [NO_UV] * len(self.v)
            theirs = other.uv if other.uv is not None else [NO_UV] * len(other.v)
            self.uv = mine + list(theirs)
        self.v += [p.copy() for p in other.v]
        self.f += [tuple(i + off for i in face) for face in other.f]
        self.c += list(other.c)
        return self

    def xform(self, m):
        self.v = [m @ p for p in self.v]
        return self

    def to_bm(self):
        bm = bmesh.new()
        verts = [bm.verts.new(p) for p in self.v]
        for face in self.f:
            try:
                bm.faces.new([verts[i] for i in face])
            except ValueError:
                pass
        bm.verts.ensure_lookup_table()
        return bm

    def normals(self):
        bm = self.to_bm()
        bm.normal_update()
        ns = [vv.normal.copy() for vv in bm.verts]
        bm.free()
        return ns

    def fix_normals(self):
        bm = self.to_bm()
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
        bm.verts.index_update()
        self.f = [tuple(vv.index for vv in face.verts) for face in bm.faces]
        bm.free()
        return self

    def paint(self, fn):
        ns = self.normals()
        self.c = [clamp_col(fn(p, n)) for p, n in zip(self.v, ns)]
        return self

    def fill(self, col):
        self.c = [col] * len(self.v)
        return self

    def tris(self):
        return sum(len(face) - 2 for face in self.f)

    def compact(self):
        used = sorted({i for face in self.f for i in face})
        remap = {o: n for n, o in enumerate(used)}
        self.v = [self.v[i] for i in used]
        self.c = [self.c[i] for i in used]
        if self.uv is not None:
            self.uv = [self.uv[i] for i in used]
        self.f = [tuple(remap[i] for i in face) for face in self.f]
        return self

    def bvh(self):
        return BVHTree.FromPolygons([tuple(p) for p in self.v], self.f)

    def bbox(self):
        xs = [p.x for p in self.v]
        ys = [p.y for p in self.v]
        zs = [p.z for p in self.v]
        return (min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs))


def from_bm(bm):
    bm.verts.index_update()
    v = [vv.co.copy() for vv in bm.verts]
    f = [tuple(vv.index for vv in face.verts) for face in bm.faces]
    return Part(v, f)


def icosphere(subdiv, radius=1.0):
    # subdiv 0 = icosahedron (20 tris), 1 = 80, 2 = 320, 3 = 1280
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=subdiv + 1, radius=radius)
    p = from_bm(bm)
    bm.free()
    return p


def lathe(profile, segs, cols=None, rmod=None, zmod=None, phase=0.0):
    """Revolve a (r, z) profile around Z. r == 0 at an end makes a pole vertex.

    rmod(theta, t) scales the radius, zmod(theta, t) offsets z (t = profile parameter 0..1)."""
    v, c, rings = [], [], []
    n = len(profile)
    for i, (r, z) in enumerate(profile):
        t = i / (n - 1)
        col = cols[i] if cols else WHITE
        if r < 1e-7 and i in (0, n - 1):
            rings.append([len(v)])
            v.append(Vector((0.0, 0.0, z)))
            c.append(col)
            continue
        ring = []
        for j in range(segs):
            th = TAU * j / segs + phase
            rr = r * (rmod(th, t) if rmod else 1.0)
            zz = z + (zmod(th, t) if zmod else 0.0)
            ring.append(len(v))
            v.append(Vector((rr * math.cos(th), rr * math.sin(th), zz)))
            c.append(col)
        rings.append(ring)
    f = []
    for a, b in zip(rings, rings[1:]):
        if len(a) == 1:
            f += [(a[0], b[j], b[(j + 1) % segs]) for j in range(segs)]
        elif len(b) == 1:
            f += [(a[j], a[(j + 1) % segs], b[0]) for j in range(segs)]
        else:
            f += [(a[j], a[(j + 1) % segs], b[(j + 1) % segs], b[j]) for j in range(segs)]
    return Part(v, f, c).fix_normals()


def catmull(points, per_seg=3):
    """Resample a polyline into a smooth Catmull-Rom curve through its points."""
    pts = [Vector(p) for p in points]
    out = []
    for i in range(len(pts) - 1):
        p0 = pts[max(i - 1, 0)]
        p1, p2 = pts[i], pts[i + 1]
        p3 = pts[min(i + 2, len(pts) - 1)]
        for k in range(per_seg):
            t = k / per_seg
            t2, t3 = t * t, t * t * t
            out.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2
                              + (-p0 + 3 * p1 - 3 * p2 + p3) * t3))
    out.append(pts[-1].copy())
    return out


def resample(values, n):
    """Linearly resample a list of floats to n values."""
    out = []
    for i in range(n):
        x = i / (n - 1) * (len(values) - 1)
        k = min(int(x), len(values) - 2)
        out.append(values[k] + (values[k + 1] - values[k]) * (x - k))
    return out


def tube(points, radii, segs, side=Vector((1, 0, 0)), ellipse=(1.0, 1.0), rmod=None,
         cap_start=True, cap_end=True):
    """Sweep a circle (or ellipse) along a path with parallel-transport frames.

    `side` seeds the frame's first axis; ellipse scales (side axis, other axis)."""
    n = len(points)
    pts = [Vector(p) for p in points]
    tangents = []
    for i in range(n):
        a = pts[max(i - 1, 0)]
        b = pts[min(i + 1, n - 1)]
        tangents.append((b - a).normalized())
    nrm = Vector(side) - tangents[0] * Vector(side).dot(tangents[0])
    if nrm.length < 1e-6:
        nrm = tangents[0].orthogonal()
    nrm.normalize()
    frames = [nrm]
    for i in range(1, n):
        q = tangents[i - 1].rotation_difference(tangents[i])
        m = q @ frames[-1]
        m = (m - tangents[i] * m.dot(tangents[i])).normalized()
        frames.append(m)
    v, rings = [], []
    for i in range(n):
        t = i / (n - 1)
        N = frames[i]
        B = tangents[i].cross(N)
        ring = []
        for j in range(segs):
            th = TAU * j / segs
            r = radii[i] * (rmod(th, t) if rmod else 1.0)
            ring.append(len(v))
            v.append(pts[i] + (N * math.cos(th) * ellipse[0] + B * math.sin(th) * ellipse[1]) * r)
        rings.append(ring)
    f = []
    for a, b in zip(rings, rings[1:]):
        f += [(a[j], a[(j + 1) % segs], b[(j + 1) % segs], b[j]) for j in range(segs)]
    if cap_start:
        ci = len(v)
        v.append(pts[0] - tangents[0] * radii[0] * 0.3)
        f += [(ci, rings[0][(j + 1) % segs], rings[0][j]) for j in range(segs)]
    if cap_end:
        ci = len(v)
        v.append(pts[-1] + tangents[-1] * radii[-1] * 0.3)
        f += [(rings[-1][j], rings[-1][(j + 1) % segs], ci) for j in range(segs)]
    return Part(v, f).fix_normals()


def align_z(normal):
    """Rotation matrix taking +Z to `normal`."""
    return Vector((0, 0, 1)).rotation_difference(Vector(normal).normalized()).to_matrix().to_4x4()


def scale_m(sx, sy, sz):
    return Matrix.Diagonal((sx, sy, sz, 1.0))


# ---------------------------------------------------------------------------
# Lumpy blob clusters (tree canopies, bushes, potted plant)
# ---------------------------------------------------------------------------

def blob_cluster(blobs, subdiv=3, amp=0.07, freq=1.7, seed=0, ground=False):
    """Union of lumpy spheres. Faces fully inside another blob (or under the ground) are removed.

    blobs: list of (centre, radius, (sx, sy, sz))."""
    rnd = random.Random(seed)
    data = []
    for c, r, sc in blobs:
        data.append((Vector(c), r, Vector(sc), Vector((rnd.uniform(-50, 50), rnd.uniform(-50, 50),
                                                       rnd.uniform(-50, 50)))))

    def radius_at(j, d):
        c, r, sc, off = data[j]
        return r * (1.0 + amp * noise.noise(d * freq + off) + 0.35 * amp * noise.noise(d * freq * 2.7 + off))

    def inside(j, p, margin=0.985):
        c, r, sc, off = data[j]
        q = p - c
        q = Vector((q.x / sc.x, q.y / sc.y, q.z / sc.z))
        L = q.length
        if L < 1e-9:
            return True
        return L < radius_at(j, q / L) * margin

    out = Part()
    base = icosphere(subdiv, 1.0)
    for j, (c, r, sc, off) in enumerate(data):
        verts = []
        for p in base.v:
            d = p.normalized()
            q = d * radius_at(j, d)
            verts.append(c + Vector((q.x * sc.x, q.y * sc.y, q.z * sc.z)))
        if ground:
            verts = [Vector((p.x, p.y, max(p.z, 0.0))) for p in verts]
        hidden = [any(inside(k, p) for k in range(len(data)) if k != j) for p in verts]
        faces = []
        for face in base.f:
            if all(hidden[i] for i in face):
                continue
            if ground and all(verts[i].z <= 1e-5 for i in face):
                continue
            faces.append(face)
        part = Part([p.copy() for p in verts], faces).compact()
        out.add(part)
    return out


def scatter_on(target, count, seed, zmin=-0.1, centre=None, jitter=0.25):
    """Even-ish points on the outer surface of `target`: rays shot inward from a Fibonacci sphere."""
    rnd = random.Random(seed)
    bvh = target.bvh()
    lo, hi = target.bbox()
    ctr = Vector(centre) if centre else (Vector(lo) + Vector(hi)) * 0.5
    reach = (Vector(hi) - Vector(lo)).length * 2.0
    hits = []
    golden = math.pi * (3.0 - math.sqrt(5.0))
    total = count * 3
    for i in range(total):
        z = 1.0 - 2.0 * (i + 0.5) / total
        if z < zmin:
            continue
        rr = math.sqrt(max(0.0, 1.0 - z * z))
        th = golden * i + rnd.uniform(-jitter, jitter)
        d = Vector((rr * math.cos(th), rr * math.sin(th), z)).normalized()
        loc, nrm, _, _ = bvh.ray_cast(ctr + d * reach, -d, reach * 2.0)
        if loc is not None:
            if nrm.dot(d) < 0:
                nrm = -nrm
            hits.append((loc, nrm))
    rnd.shuffle(hits)
    return hits[:count]


# ---------------------------------------------------------------------------
# Painterly shading: baked AO with cool shadows + noise variation
# ---------------------------------------------------------------------------

def hemisphere_dirs(n):
    dirs = []
    golden = math.pi * (3.0 - math.sqrt(5.0))
    for i in range(n):
        u = (i + 0.5) / n
        r = math.sqrt(u)  # cosine-weighted
        th = golden * i
        dirs.append((r * math.cos(th), r * math.sin(th), math.sqrt(max(0.0, 1.0 - u))))
    return dirs


SHADOW_TINT = (0.62, 0.68, 0.86)  # shadows lean cool (blue-violet), like painted anime backgrounds


def bake_ao(part, dist, strength=0.8, rays=40, ground=True, smooth=2, tint=SHADOW_TINT):
    ns = part.normals()
    bvh = part.bvh()
    dirs = hemisphere_dirs(rays)
    ao = []
    for p, n in zip(part.v, ns):
        if n.length < 1e-6:
            ao.append(1.0)
            continue
        t = n.orthogonal().normalized()
        b = n.cross(t)
        o = p + n * (dist * 0.004)
        occ = 0.0
        for x, y, z in dirs:
            d = t * x + b * y + n * z
            hit = bvh.ray_cast(o, d, dist)
            if hit[0] is not None:
                occ += 1.0 - 0.6 * (hit[3] / dist)
            elif ground and d.z < -1e-4:
                tg = o.z / -d.z
                if tg < dist:
                    occ += 1.0 - 0.6 * (tg / dist)
        ao.append(1.0 - occ / rays)
    # Smooth the AO over mesh edges to remove ray noise.
    nbrs = [set() for _ in part.v]
    for face in part.f:
        for k in range(len(face)):
            a, b2 = face[k], face[(k + 1) % len(face)]
            nbrs[a].add(b2)
            nbrs[b2].add(a)
    for _ in range(smooth):
        ao = [(a + sum(ao[j] for j in nb)) / (1 + len(nb)) if nb else a for a, nb in zip(ao, nbrs)]
    out = []
    for col, a in zip(part.c, ao):
        k = (1.0 - a) * strength          # 0 = open, 1 = fully occluded
        shade = mix(WHITE, mul(tint, 0.55), k)
        out.append(clamp_col(mul(col, shade)))
    part.c = out
    return part


def sun_light(n, lift=0.12, drop=0.10):
    """Brightness factor from a soft top light (lighter on top, slightly darker underneath)."""
    return 1.0 + lift * max(0.0, n.z) - drop * max(0.0, -n.z)


def painterly(base, p, n, scale=1.0, amount=0.06, seed=0.0):
    """Low-frequency colour variation (hue + value) so flat surfaces look hand-painted."""
    q = p * scale + Vector((seed, seed * 1.7, seed * 0.3))
    a = noise.noise(q)
    b = noise.noise(q * 2.3 + Vector((7.1, 3.3, 1.9)))
    col = (base[0] * (1 + amount * a), base[1] * (1 + amount * 0.6 * b), base[2] * (1 - amount * a))
    return col


# ---------------------------------------------------------------------------
# Props
# ---------------------------------------------------------------------------

def foliage_painter(dark, light, top_light, zlo, zhi, seed=0.0, nscale=1.6):
    def fn(p, n):
        h = smoothstep(zlo, zhi, p.z)
        up = n.z * 0.5 + 0.5
        t = 0.55 * h + 0.6 * up - 0.15
        col = mix(dark, light, t)
        col = mix(col, top_light, smoothstep(0.55, 1.0, n.z) * 0.45 * (0.4 + 0.6 * h))
        col = painterly(col, p, n, nscale, 0.08, seed)
        return mul(col, sun_light(n, 0.05, 0.06))
    return fn


def trunk_painter(base, light):
    def fn(p, n):
        col = mix(base, light, 0.5 + 0.5 * n.z + 0.15 * noise.noise(p * 6.0))
        return painterly(col, p, n, 3.0, 0.05, 2.0)
    return fn


def make_tree(seed, trunk_path, trunk_radii, branches, blobs, greens, ao_dist=1.0):
    trunk_pts = catmull(trunk_path, 3)
    radii = resample(trunk_radii, len(trunk_pts))

    def root_flare(th, t):
        return 1.0 + 0.32 * max(0.0, math.cos(4 * th + 0.4)) ** 2 * max(0.0, 1.0 - t * 4.5) ** 2

    wood = Part()
    wood.add(tube(trunk_pts, radii, 12, rmod=root_flare, cap_start=False))
    for path, r0, r1 in branches:
        pts = catmull(path, 2)
        wood.add(tube(pts, resample([r0, r1], len(pts)), 8, cap_start=False))
    wood.paint(trunk_painter(hexc("#8a5a3c"), hexc("#b07a4f")))

    canopy = blob_cluster(blobs, subdiv=3, amp=0.075, freq=1.5, seed=seed)
    lo, hi = canopy.bbox()
    canopy.paint(foliage_painter(greens[0], greens[1], greens[2], lo[2], hi[2], seed=seed * 3.1))

    tree = Part().add(wood).add(canopy)
    return bake_ao(tree, ao_dist, strength=0.85, rays=36)


def tree_round_a():
    return make_tree(
        seed=11,
        trunk_path=[(0, 0, 0), (0.03, 0.0, 0.45), (0.11, 0.03, 0.95), (0.12, 0.03, 1.4),
                    (0.05, 0.0, 1.85), (0.0, -0.02, 2.35)],
        trunk_radii=[0.2, 0.16, 0.135, 0.12, 0.105, 0.085],
        branches=[([(0.11, 0.03, 1.35), (0.35, 0.08, 1.7), (0.62, 0.1, 2.1)], 0.065, 0.035),
                  ([(0.06, 0.0, 1.7), (-0.2, -0.08, 1.95), (-0.5, -0.15, 2.3)], 0.055, 0.03)],
        blobs=[((0.0, 0.0, 3.0), 1.08, (1, 1, 0.95)),
               ((0.75, 0.15, 2.6), 0.78, (1, 1, 0.92)),
               ((-0.7, 0.25, 2.65), 0.8, (1, 1, 0.92)),
               ((0.1, -0.65, 2.55), 0.78, (1, 1, 0.92)),
               ((0.2, 0.55, 3.45), 0.72, (1, 1, 1)),
               ((-0.35, -0.3, 3.55), 0.68, (1, 1, 1))],
        greens=(hexc("#3f9e45"), hexc("#a6e05a"), hexc("#e4f58a")),
    )


def tree_round_b():
    return make_tree(
        seed=23,
        trunk_path=[(0, 0, 0), (-0.04, 0.02, 0.5), (-0.1, 0.03, 1.1), (-0.06, 0.02, 1.7),
                    (0.04, 0.0, 2.3), (0.08, 0.0, 2.9)],
        trunk_radii=[0.18, 0.14, 0.12, 0.105, 0.09, 0.07],
        branches=[([(-0.09, 0.03, 1.5), (-0.35, 0.05, 1.95), (-0.55, 0.12, 2.6)], 0.055, 0.03),
                  ([(-0.02, 0.01, 2.0), (0.25, -0.1, 2.3), (0.5, -0.2, 2.75)], 0.05, 0.028)],
        blobs=[((0.05, 0.0, 3.25), 0.88, (1, 1, 1.12)),
               ((0.6, 0.15, 2.95), 0.62, (1, 1, 1.05)),
               ((-0.55, 0.2, 3.0), 0.64, (1, 1, 1.05)),
               ((0.05, -0.55, 3.0), 0.62, (1, 1, 1.05)),
               ((-0.1, 0.45, 3.15), 0.6, (1, 1, 1.05)),
               ((0.1, 0.05, 4.05), 0.7, (1, 1, 1)),
               ((0.3, -0.15, 4.5), 0.42, (1, 1, 1))],
        greens=(hexc("#2f9a5a"), hexc("#8fde6a"), hexc("#d8f68e")),
    )


def make_bush(seed, blobs, greens, flowers=0):
    bush = blob_cluster(blobs, subdiv=3, amp=0.09, freq=2.2, seed=seed, ground=True)
    lo, hi = bush.bbox()
    bush.paint(foliage_painter(greens[0], greens[1], greens[2], 0.0, hi[2], seed=seed * 1.3, nscale=3.0))
    if flowers:
        rnd = random.Random(seed + 5)
        pink, white, yellow = hexc("#ff8fbf"), hexc("#fff7fa"), hexc("#ffd34d")
        for k, (loc, nrm) in enumerate(scatter_on(bush, flowers, seed, zmin=-0.05,
                                                  centre=(0, 0, hi[2] * 0.45))):
            r = rnd.uniform(0.028, 0.04)
            dot = icosphere(1, 1.0)
            col = pink if k % 3 else white
            dot.c = [mix(col, yellow, smoothstep(0.75, 1.0, p.z)) for p in dot.v]
            dot.xform(Matrix.Translation(loc + nrm * r * 0.12) @ align_z(nrm) @ scale_m(r, r, r * 0.45))
            bush.add(dot)
    return bake_ao(bush, 0.45, strength=0.85, rays=36)


def bush_a():
    return make_bush(31, [((0.0, 0.0, 0.48), 0.5, (1, 1, 0.95)),
                          ((0.42, 0.08, 0.38), 0.38, (1, 1, 0.95)),
                          ((-0.42, -0.05, 0.4), 0.4, (1, 1, 0.95)),
                          ((0.05, 0.32, 0.4), 0.36, (1, 1, 0.95)),
                          ((0.0, -0.3, 0.4), 0.36, (1, 1, 0.95)),
                          ((0.08, 0.02, 0.78), 0.32, (1, 1, 1))],
                     (hexc("#2f9447"), hexc("#86d65a"), hexc("#d4f286")))


def bush_b():
    return make_bush(47, [((0.0, 0.0, 0.42), 0.44, (1, 1, 0.95)),
                          ((0.36, 0.1, 0.33), 0.33, (1, 1, 0.95)),
                          ((-0.34, -0.06, 0.34), 0.34, (1, 1, 0.95)),
                          ((0.02, 0.0, 0.66), 0.3, (1, 1, 1))],
                     (hexc("#349c4c"), hexc("#94dc63"), hexc("#dcf590")), flowers=24)


CAP_PROFILE = [(0.0, 0.12), (0.35, 0.08), (0.7, 0.02), (0.92, 0.0), (1.0, 0.08), (1.0, 0.22),
               (0.93, 0.45), (0.78, 0.7), (0.55, 0.88), (0.28, 0.98), (0.0, 1.0)]
STEM_PROFILE = [(0.0, 0.0), (0.85, 0.0), (1.0, 0.04), (0.97, 0.3), (0.88, 0.7), (0.82, 1.0), (0.0, 1.02)]


def mushroom(h, cap_r, cap_h, stem_r, cap_col, stem_col, segs=24, dots=0, seed=0, lean=(0.0, 0.0)):
    cap_base = h - cap_h
    under = mix(stem_col, hexc("#e8d6b0"), 0.5)
    cap = lathe([(r * cap_r, cap_base + z * cap_h) for r, z in CAP_PROFILE], segs,
                cols=[under] * 4 + [cap_col] * 7)
    # Re-colour: underside cream, top cap colour with a soft highlight on top.
    cap.c = []
    ns = cap.normals()
    for p, n in zip(cap.v, ns):
        if p.z < cap_base + 0.05 * cap_h and n.z < 0.2:
            cap.c.append(under)
        else:
            col = mix(cap_col, mix(cap_col, WHITE, 0.25), smoothstep(0.3, 1.0, n.z))
            cap.c.append(clamp_col(painterly(col, p, n, 20.0 / h, 0.05, seed)))
    stem_h = cap_base + 0.3 * cap_h
    stem = lathe([(r * stem_r, z * stem_h) for r, z in STEM_PROFILE], max(10, segs // 2))
    stem.paint(lambda p, n: mul(stem_col, sun_light(n, 0.04, 0.0)))
    part = Part().add(stem).add(cap)
    if dots:
        rnd = random.Random(seed)
        hits = scatter_on(cap, dots, seed, zmin=0.25, centre=(0, 0, cap_base))
        for loc, nrm in hits:
            r = rnd.uniform(0.11, 0.17) * cap_r
            d = icosphere(1, 1.0).fill(hexc("#fffaf2"))
            d.xform(Matrix.Translation(loc + nrm * r * 0.05) @ align_z(nrm) @ scale_m(r, r, r * 0.28))
            part.add(d)
    # Gentle lean: shear x/y proportional to height.
    lx, ly = lean
    part.v = [Vector((p.x + lx * p.z, p.y + ly * p.z, p.z)) for p in part.v]
    return part


def mushroom_red():
    m = mushroom(0.25, 0.115, 0.1, 0.036, hexc("#ec4a42"), hexc("#fbf0d8"), segs=28, dots=9, seed=5,
                 lean=(0.04, 0.0))
    return bake_ao(m, 0.08, strength=0.8, rays=32)


def mushroom_pair():
    a = mushroom(0.16, 0.068, 0.062, 0.019, hexc("#b8723f"), hexc("#f8ecd3"), segs=24, seed=1,
                 lean=(0.06, 0.02))
    a.xform(Matrix.Translation((0.035, 0.0, 0.0)))
    b = mushroom(0.105, 0.047, 0.044, 0.014, hexc("#cf8d52"), hexc("#f8ecd3"), segs=20, seed=2,
                 lean=(-0.12, 0.05))
    b.xform(Matrix.Translation((-0.055, 0.03, 0.0)) @ Matrix.Rotation(0.6, 4, "Z"))
    return bake_ao(Part().add(a).add(b), 0.06, strength=0.8, rays=32)


def beveled_prism(outline, depth, bevel, segments=2):
    """Extrude a convex XZ outline along +Y by `depth` (centred) and bevel all edges."""
    bm = bmesh.new()
    verts = [bm.verts.new((x, -depth / 2, z)) for x, z in outline]
    face = bm.faces.new(verts)
    res = bmesh.ops.extrude_face_region(bm, geom=[face])
    moved = [e for e in res["geom"] if isinstance(e, bmesh.types.BMVert)]
    bmesh.ops.translate(bm, verts=moved, vec=(0, depth, 0))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    bmesh.ops.bevel(bm, geom=bm.edges[:], offset=bevel, offset_type="OFFSET", segments=segments,
                    profile=0.5, affect="EDGES", clamp_overlap=True)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    p = from_bm(bm)
    bm.free()
    return p


def fence_segment():
    rnd = random.Random(3)
    white = hexc("#fbf3e2")
    part = Part()
    w, top, thick = 0.085, 0.7, 0.022
    arc = [(w / 2 * math.cos(a), top - w / 2 + w / 2 * math.sin(a))
           for a in [math.pi * k / 8 for k in range(9)]]
    outline = [(-w / 2, 0.0), (w / 2, 0.0)] + arc  # the arc runs right -> left over the top
    count = 14
    for i in range(count):
        x = -0.93 + i * (1.86 / (count - 1))
        pk = beveled_prism(outline, thick, 0.006)
        hh = 1.0 + rnd.uniform(-0.02, 0.02)
        pk.xform(Matrix.Translation((x, 0.0, 0.0)) @ Matrix.Rotation(rnd.uniform(-0.015, 0.015), 4, "Y")
                 @ scale_m(1, 1, hh))
        part.add(pk)
    for z in (0.2, 0.5):
        rail = beveled_prism([(-1.0, z - 0.032), (1.0, z - 0.032), (1.0, z + 0.032), (-1.0, z + 0.032)],
                             0.024, 0.007)
        rail.xform(Matrix.Translation((0.0, thick / 2 + 0.012, 0.0)))
        part.add(rail)
    part.paint(lambda p, n: mul(painterly(white, p, n, 2.0, 0.025, 4.0), sun_light(n, 0.0, 0.05)))
    return bake_ao(part, 0.14, strength=0.7, rays=32)


def make_stone(seed, size, col, flat=0.6):
    rx, ry, rz = size
    rnd = random.Random(seed)
    off = Vector((rnd.uniform(-9, 9), rnd.uniform(-9, 9), rnd.uniform(-9, 9)))
    s = icosphere(3, 1.0)
    out = []
    for p in s.v:
        d = p.normalized()
        r = 1.0 + 0.1 * noise.noise(d * 1.3 + off) + 0.03 * noise.noise(d * 3.5 + off)
        q = d * r
        z = q.z
        if z < -flat:
            z = -flat + (z + flat) * 0.12   # squash the underside flat
        out.append(Vector((q.x * rx, q.y * ry, z * rz)))
    s.v = out
    zmin = min(p.z for p in s.v)
    s.xform(Matrix.Translation((0, 0, -zmin)))

    def fn(p, n):
        c = mix(mul(col, 0.9), mix(col, WHITE, 0.25), 0.5 + 0.5 * n.z)
        c = mul(c, 1.0 + 0.05 * noise.noise(p * (14.0 / max(size)) + off))
        return c
    s.paint(fn)
    return bake_ao(s, max(size) * 0.6, strength=0.7, rays=32)


def stone_a():
    return make_stone(1, (0.24, 0.19, 0.17), hexc("#b3a690"), flat=0.45)


def stone_b():
    return make_stone(2, (0.11, 0.09, 0.08), hexc("#bcae94"), flat=0.5)


def stone_c():
    return make_stone(3, (0.3, 0.24, 0.07), hexc("#a9a193"), flat=0.3)


def wand():
    pink, mint = hexc("#ff7fb0"), hexc("#8fe0c8")
    R, r = 0.035 + 0.006, 0.006
    seg_major, seg_minor = 48, 12
    v, f = [], []
    for i in range(seg_major):
        th = TAU * i / seg_major
        for j in range(seg_minor):
            ph = TAU * j / seg_minor
            rr = R + r * math.cos(ph)
            # Ring in the XZ plane, axis along Blender Y (= glTF/three.js Z after the Y-up conversion).
            v.append(Vector((rr * math.cos(th), r * math.sin(ph), rr * math.sin(th))))
    for i in range(seg_major):
        for j in range(seg_minor):
            a = i * seg_minor + j
            b = ((i + 1) % seg_major) * seg_minor + j
            c = ((i + 1) % seg_major) * seg_minor + (j + 1) % seg_minor
            d = i * seg_minor + (j + 1) % seg_minor
            f.append((a, b, c, d))
    ring = Part(v, f).fix_normals().fill(pink)
    hr = 0.007
    top = -(R + r) + 0.003
    bottom = top - 0.22
    prof = [(0.0, bottom), (hr * 0.6, bottom + 0.0012), (hr * 0.92, bottom + 0.0035), (hr, bottom + 0.007),
            (hr, top - 0.03), (hr * 1.0, top - 0.018), (hr * 1.35, top - 0.014), (hr * 1.35, top - 0.006),
            (hr * 0.9, top - 0.002), (0.0, top + 0.002)]
    handle = lathe(prof, 14).fill(mint)
    return Part().add(ring).add(handle)


def make_daisy_head(radius, petals, segs_per_petal=6, cup=0.27):
    """Flat flower: a petal disc (lathe with a petal-shaped radius) and a domed yellow-orange centre (kept for the
    flower pot; the meadow daisies use make_daisy_head_tex)."""
    segs = petals * segs_per_petal
    half = petals / 2.0

    # each petal its own length (±12 %): identical petals read as clip-art
    plen = [1.0 + 0.12 * math.sin(k * 2.399 + petals * 0.7) * math.cos(k * 1.3) for k in range(petals)]

    def rmod(th, t):
        # narrow petals with rounded tips (art director: fewer, wider petals read as a plastic toy)
        k = int(round(th / TAU * petals)) % petals
        return (0.34 + 0.66 * min(1.0, 1.22 * abs(math.cos(half * th)) ** 1.5)) * (1.0 + (plen[k] - 1.0) * smoothstep(0.3, 0.9, abs(math.cos(half * th))))

    white, cream = hexc("#f7f3ea"), hexc("#d8d1bf")
    prof = [(0.0, 0.0018 * radius / 0.0225), (0.45 * radius, 0.0024 * radius / 0.0225 + cup * 0.2 * radius),
            (radius, cup * radius), (0.45 * radius, -0.0012), (0.0, -0.002)]
    disc = lathe(prof, segs, rmod=rmod, cols=[cream, white, white, cream, cream], phase=0.0)
    disc.paint(lambda p, n: mix(cream, white, smoothstep(0.1, 0.6, Vector((p.x, p.y)).length / radius))
               if n.z > -0.3 else mul(cream, 0.92))
    ctr_r = radius * 0.26
    ctr = icosphere(1, 1.0)
    ctr.xform(Matrix.Translation((0, 0, 0.003)) @ scale_m(ctr_r, ctr_r, ctr_r * 0.62))
    yellow, orange = hexc("#ffd23a"), hexc("#ff9a1f")
    ctr.paint(lambda p, n: mix(yellow, orange, smoothstep(0.5, 1.0, n.z)))
    return Part().add(disc).add(ctr)


def make_daisy_head_tex(radius, cup=0.2, segs=20):
    """The meadow daisy's head: a round disc, cupped toward the rim, with the yellow centre domed up out of it, both
    sides (petals are seen from below on tilted heads), planar uv into one cell of the painted head atlas. The petal
    outlines, their crease and the florets are painted (tools/paint_daisy.py); the disc is cut out by its alpha.
    (g32's modelled petals were blunt plastic strips around a flat orange button.)"""
    rc = 0.2  # the painted disc's radius, as a fraction of the head radius
    fr = [0.0, 0.07, 0.13, 0.18, 0.22, 0.32, 0.46, 0.62, 0.8, 1.0]

    def z_at(f):
        dome = 0.36 * rc * radius * math.sqrt(max(0.0, 1.0 - (f / rc) ** 2)) if f < rc else 0.0
        return dome + cup * radius * smoothstep(rc, 1.0, f) ** 1.5

    v, f_, uv = [], [], []
    for side in (1, -1):
        off = len(v)
        v.append(Vector((0.0, 0.0, z_at(0.0) if side > 0 else -0.0006)))
        uv.append((0.5, 0.5))
        for i, fi in enumerate(fr[1:]):
            for k in range(segs):
                a = TAU * k / segs
                x, y = math.cos(a) * fi * radius, math.sin(a) * fi * radius
                # the back sheet sits a hair under the front one (and under the dome)
                z = z_at(fi) if side > 0 else (z_at(fi) if fi > rc else 0.0) - 0.0006
                v.append(Vector((x, y, z)))
                uv.append((0.5 + 0.5 * fi * math.cos(a), 0.5 + 0.5 * fi * math.sin(a)))
        for k in range(segs):
            k2 = (k + 1) % segs
            tri = (off, off + 1 + k, off + 1 + k2)
            f_.append(tri if side > 0 else tri[::-1])
        for i in range(len(fr) - 2):
            for k in range(segs):
                k2 = (k + 1) % segs
                a0, b0 = off + 1 + i * segs + k, off + 1 + i * segs + k2
                a1, b1 = a0 + segs, b0 + segs
                q = (a0, a1, b1, b0)
                f_.append(q if side > 0 else q[::-1])
    return Part(v, f_, [WHITE] * len(v), uv)


def leaf(length, width, phi, lift=0.9, droop=0.6, segs=5, rings=7):
    """A thin curved leaf blade growing from the origin in direction phi."""
    d = Vector((math.cos(phi), math.sin(phi), 0.0))
    pts = []
    for i in range(rings):
        t = i / (rings - 1)
        out = length * t
        up = length * (lift * t - droop * t * t) * 0.6
        pts.append(d * out + Vector((0, 0, max(0.0, up) + 0.002)))
    radii = [width * (0.25 + 1.3 * math.sin(math.pi * min(1.0, 0.1 + t * 0.95)) ** 0.8)
             for t in [i / (rings - 1) for i in range(rings)]]
    radii[-1] = width * 0.08
    side = Vector((-math.sin(phi), math.cos(phi), 0.0))
    return tube(pts, radii, segs, side=side, ellipse=(1.0, 0.16), cap_start=False)


def stem(height, lean, radius, segs=5, rings=4):
    pts = [Vector((lean[0] * (i / (rings - 1)) ** 1.6, lean[1] * (i / (rings - 1)) ** 1.6,
                   height * i / (rings - 1))) for i in range(rings)]
    return tube(pts, resample([radius * 1.2, radius], rings), segs, cap_start=False, cap_end=False), pts


GREEN_DARK, GREEN_LIGHT = hexc("#3aa047"), hexc("#9be36a")


def green_paint(p, n, h):
    return mix(GREEN_DARK, GREEN_LIGHT, 0.25 + 0.6 * smoothstep(0.0, h, p.z) + 0.25 * n.z)


def daisy(height, lean, radius, petals, tilt, stem_r=0.0011, stem_segs=5, stem_rings=4, seed=0):
    s, pts = stem(height, lean, stem_r, stem_segs, stem_rings)
    s.paint(lambda p, n: green_paint(p, n, height))
    # (the painted petals end at 0.76–0.98 of the cell: a touch larger than the modelled head's radius)
    head = make_daisy_head_tex(radius * 1.08)
    head.xform(Matrix.Rotation(seed * 1.3, 4, "Z"))
    tip_dir = (pts[-1] - pts[-2]).normalized()
    up = (tip_dir + Vector((0, 0, 1.0)) * tilt).normalized()
    head.xform(Matrix.Translation(pts[-1]) @ align_z(up))
    return Part().add(s).add(head)


def daisy_single():
    p = daisy(0.13, (0.012, 0.004), 0.0225, 18, 0.6, stem_r=0.0011, stem_segs=4, stem_rings=3, seed=1)
    lf = leaf(0.06, 0.007, 0.8, segs=4, rings=4).paint(lambda q, n: green_paint(q, n, 0.05))
    p.add(lf)
    return bake_ao(p, 0.04, strength=0.6, rays=24)


def daisy_clump():
    rnd = random.Random(9)
    part = Part()
    n = 7
    for i in range(n):
        a = TAU * i / n + rnd.uniform(-0.3, 0.3)
        rr = 0.0 if i == 0 else rnd.uniform(0.025, 0.05)
        base = Vector((rr * math.cos(a), rr * math.sin(a), 0.0))
        h = 0.25 - 0.012 if i == 0 else rnd.uniform(0.15, 0.22)
        lean = (math.cos(a) * rnd.uniform(0.02, 0.05), math.sin(a) * rnd.uniform(0.02, 0.05))
        d = daisy(h, lean, rnd.uniform(0.02, 0.025), rnd.choice([16, 18, 20]), 0.8, seed=i)
        d.xform(Matrix.Translation(base))
        part.add(d)
    for i in range(6):
        phi = TAU * i / 6 + rnd.uniform(-0.3, 0.3)
        lf = leaf(rnd.uniform(0.07, 0.1), rnd.uniform(0.008, 0.011), phi, lift=1.1, droop=0.9)
        part.add(lf.paint(lambda q, n: green_paint(q, n, 0.06)))
    return bake_ao(part, 0.05, strength=0.65, rays=24)


def tulip_clump():
    rnd = random.Random(17)
    cols = [hexc("#f04a4f"), hexc("#ff8fbf"), hexc("#ffd23f"), hexc("#ff9a4a"), hexc("#c99bf2")]
    part = Part()
    for i in range(5):
        a = TAU * i / 5 + rnd.uniform(-0.3, 0.3)
        rr = rnd.uniform(0.02, 0.05)
        base = Vector((rr * math.cos(a), rr * math.sin(a), 0.0))
        h = 0.28 if i == 0 else rnd.uniform(0.2, 0.26)
        lean = (math.cos(a) * rnd.uniform(0.02, 0.04), math.sin(a) * rnd.uniform(0.02, 0.04))
        s, pts = stem(h, lean, 0.004, 6, 5)
        s.paint(lambda p, n: green_paint(p, n, h))
        col = cols[i]

        def zmod(th, t):
            return 0.009 * max(0.0, math.cos(3 * th)) ** 2 * smoothstep(0.55, 1.0, t)

        def rmod(th, t):
            return 1.0 + 0.07 * math.cos(3 * th) * smoothstep(0.4, 1.0, t)

        prof = [(0.0, 0.0), (0.012, 0.003), (0.022, 0.013), (0.0265, 0.028), (0.0265, 0.043),
                (0.022, 0.057), (0.015, 0.066), (0.0, 0.07)]
        head = lathe(prof, 18, rmod=rmod, zmod=zmod)
        dark = mul(col, 0.82)
        head.paint(lambda p, n, col=col, dark=dark: mix(dark, mix(col, WHITE, 0.18), smoothstep(0.0, 0.07, p.z)))
        tip = (pts[-1] - pts[-2]).normalized()
        head.xform(Matrix.Translation(pts[-1] - tip * 0.004) @ align_z(tip))
        s.add(head)
        s.xform(Matrix.Translation(base))
        part.add(s)
    for i in range(7):
        phi = TAU * i / 7 + rnd.uniform(-0.25, 0.25)
        lf = leaf(rnd.uniform(0.13, 0.19), rnd.uniform(0.014, 0.018), phi, lift=1.6, droop=1.0,
                  segs=6, rings=9)
        part.add(lf.paint(lambda q, n: green_paint(q, n, 0.12)))
    return bake_ao(part, 0.07, strength=0.7, rays=28)


def flower_pot():
    terracotta = hexc("#e07a4f")
    prof = [(0.0, 0.0), (0.085, 0.0), (0.095, 0.006), (0.1, 0.02), (0.13, 0.2), (0.152, 0.2),
            (0.158, 0.21), (0.158, 0.262), (0.152, 0.27), (0.14, 0.27), (0.135, 0.255), (0.12, 0.08),
            (0.0, 0.08)]
    pot = lathe(prof, 32)
    pot.paint(lambda p, n: mul(painterly(terracotta, p, n, 8.0, 0.05, 1.0), sun_light(n, 0.12, 0.08)))
    soil = lathe([(0.0, 0.252), (0.08, 0.25), (0.136, 0.243), (0.13, 0.23), (0.0, 0.23)], 24)
    soil.paint(lambda p, n: hexc("#6e4a33"))
    plant = blob_cluster([((0.0, 0.0, 0.38), 0.14, (1, 1, 0.95)),
                          ((0.08, 0.05, 0.33), 0.1, (1, 1, 1)),
                          ((-0.08, 0.03, 0.34), 0.1, (1, 1, 1)),
                          ((0.0, -0.08, 0.33), 0.1, (1, 1, 1))], subdiv=2, amp=0.1, freq=2.4, seed=7)
    lo, hi = plant.bbox()
    plant.paint(foliage_painter(hexc("#2f9a4a"), hexc("#94df63"), hexc("#dcf590"), lo[2], hi[2], 2.0, 8.0))
    part = Part().add(pot).add(soil).add(plant)
    for k, (loc, nrm) in enumerate(scatter_on(plant, 6, 3, zmin=0.0, centre=(0, 0, 0.36))):
        head = make_daisy_head(0.024, 10)
        head.xform(Matrix.Translation(loc + nrm * 0.004) @ align_z(nrm) @ Matrix.Rotation(k, 4, "Z"))
        part.add(head)
    return bake_ao(part, 0.12, strength=0.75, rays=32)


def wild_head(radius, petals, cup, base, tip, ctr, ctr_r=0.28, spp=4, shape=1.2, notch=0.3, seed=0):
    """A small wildflower head: like make_daisy_head with its own colours, cupped by `cup` (0 flat … 1 deep bowl)."""
    segs = petals * spp
    half = petals / 2.0

    def rmod(th, t):
        return notch + (1 - notch) * min(1.0, 1.15 * abs(math.cos(half * th)) ** shape)

    prof = [(0.0, 0.0012), (0.5 * radius, 0.0016 + cup * 0.35 * radius), (radius, cup * radius),
            (0.5 * radius, cup * 0.3 * radius - 0.0008), (0.0, -0.0012)]
    disc = lathe(prof, segs, rmod=rmod, phase=seed * 0.7)
    disc.paint(lambda p, n: mix(base, tip, smoothstep(0.15, 0.8, Vector((p.x, p.y)).length / radius))
               if n.z > -0.3 else mul(base, 0.85))
    c = icosphere(1, 1.0)
    cr = radius * ctr_r
    c.xform(Matrix.Translation((0, 0, 0.0015 + cup * 0.25 * radius)) @ scale_m(cr, cr, cr * 0.6))
    c.paint(lambda p, n: ctr)
    return Part().add(disc).add(c)


def wild_stem_flower(height, lean, head, tilt=0.5, stem_r=0.0009):
    s, pts = stem(height, lean, stem_r, 4, 3)
    s.paint(lambda p, n: green_paint(p, n, height))
    tip_dir = (pts[-1] - pts[-2]).normalized()
    up = (tip_dir + Vector((0, 0, 1.0)) * tilt).normalized()
    head.xform(Matrix.Translation(pts[-1]) @ align_z(up))
    return Part().add(s).add(head)


def buttercup_clump():
    """Three or four glossy buttercups on thin stems: small cupped five-petal heads, warm butter yellow."""
    rnd = random.Random(23)
    part = Part()
    n = 4
    for i in range(n):
        a = TAU * i / n + rnd.uniform(-0.4, 0.4)
        rr = 0.0 if i == 0 else rnd.uniform(0.015, 0.035)
        h = rnd.uniform(0.075, 0.105)  # (round 15: heads inside the daisy layer, not above it)
        lean = (math.cos(a) * rnd.uniform(0.01, 0.03), math.sin(a) * rnd.uniform(0.01, 0.03))
        # five petals cupped up ~40° round a darker green-gold eye (round 15: open ones read as flat plates on sticks;
        # round 5: deep egg cups read as plastic)
        head = wild_head(rnd.uniform(0.0095, 0.012), 5, 0.42, hexc("#e0aa1e"), hexc("#ffe27e"), hexc("#8f8a2a"),
                         ctr_r=0.3, spp=6, shape=0.7, notch=0.45, seed=i)
        f = wild_stem_flower(h, lean, head, rnd.uniform(0.4, 0.9), stem_r=0.0012)
        f.xform(Matrix.Translation((rr * math.cos(a), rr * math.sin(a), 0.0)))
        part.add(f)
    for i in range(3):
        phi = TAU * i / 3 + rnd.uniform(-0.3, 0.3)
        part.add(leaf(rnd.uniform(0.05, 0.07), rnd.uniform(0.008, 0.011), phi, lift=1.0, droop=0.9)
                 .paint(lambda q, n_: green_paint(q, n_, 0.05)))
    return bake_ao(part, 0.04, strength=0.6, rays=24)


def forget_me_not():
    """A sprig of forget-me-nots: a thin stem forking into three short sprays, each with a cluster of tiny sky-blue
    five-petal flowers with a yellow eye."""
    rnd = random.Random(41)
    part = Part()
    s, pts = stem(0.12, (0.006, 0.0), 0.0012, 4, 3)
    s.paint(lambda p, n: green_paint(p, n, 0.12))
    part.add(s)
    top = pts[-1]
    for b in range(3):
        a = TAU * b / 3 + rnd.uniform(-0.3, 0.3)
        tip = top + Vector((math.cos(a) * 0.022, math.sin(a) * 0.022, rnd.uniform(0.012, 0.03)))
        br = tube([top, (top + tip) * 0.5 + Vector((0, 0, 0.004)), tip], [0.0011, 0.0009, 0.0008], 4,
                  cap_start=False, cap_end=False)
        br.paint(lambda p, n: green_paint(p, n, 0.15))
        part.add(br)
        for k in range(5):
            o = Vector((rnd.uniform(-0.009, 0.009), rnd.uniform(-0.009, 0.009), rnd.uniform(-0.004, 0.006)))
            head = wild_head(rnd.uniform(0.0045, 0.0058), 5, 0.12, hexc("#8fa4c8"), hexc("#bccbe2"), hexc("#f4ecd0"),
                             ctr_r=0.3, spp=4, shape=0.6, notch=0.5, seed=k + b * 5)
            up = (Vector((o.x, o.y, 0.02)) + Vector((0, 0, 1))).normalized()
            head.xform(Matrix.Translation(tip + o) @ align_z(up))
            part.add(head)
    for i in range(3):
        phi = TAU * i / 3 + rnd.uniform(-0.3, 0.3)
        part.add(leaf(rnd.uniform(0.04, 0.055), rnd.uniform(0.006, 0.008), phi, lift=1.0, droop=0.8)
                 .paint(lambda q, n_: green_paint(q, n_, 0.04)))
    return bake_ao(part, 0.04, strength=0.55, rays=24)


def poppy_head(radius, seed=0):
    """A field poppy: four broad, overlapping, crinkled petals in a shallow cup, muted coral (not a saturated red),
    a dark plum blotch at their base round a pale green seed pod with a dark crown."""
    rnd = random.Random(seed)
    petals = 4
    segs = 48
    ph = rnd.uniform(0, 1)

    def rmod(th, t):
        return 0.78 + 0.22 * min(1.0, abs(math.cos(petals / 2.0 * th)) ** 0.35) + 0.035 * math.sin(th * 17 + ph * 9)

    def zmod(th, t):
        return 0.0018 * t * math.sin(th * 13 + ph * 5)  # crinkled like tissue

    cup = 0.5
    prof = [(0.0, 0.0012), (0.45 * radius, 0.0016 + cup * 0.3 * radius), (radius, cup * radius),
            (0.45 * radius, cup * 0.28 * radius - 0.0008), (0.0, -0.0012)]
    disc = lathe(prof, segs, rmod=rmod, zmod=zmod, phase=ph)
    base, tip, blotch = hexc("#d9614c"), hexc("#ee8d72"), hexc("#3b2630")
    disc.paint(lambda p, n: (mix(blotch, base, smoothstep(0.16, 0.3, Vector((p.x, p.y)).length / radius))
                             if Vector((p.x, p.y)).length / radius < 0.3
                             else mix(base, tip, smoothstep(0.3, 0.95, Vector((p.x, p.y)).length / radius)))
               if n.z > -0.3 else mul(base, 0.8))
    pod = icosphere(1, 1.0)
    pr = radius * 0.2
    pod.xform(Matrix.Translation((0, 0, 0.002 + cup * 0.2 * radius)) @ scale_m(pr, pr, pr * 0.9))
    pod.paint(lambda p, n: hexc("#4a4436") if n.z > 0.6 else hexc("#a9b48a"))
    return Part().add(disc).add(pod)


def poppy_clump():
    """Two or three poppies on tall, slightly crooked stems, and a nodding bud."""
    rnd = random.Random(61)
    part = Part()
    n = 3
    for i in range(n):
        a = TAU * i / n + rnd.uniform(-0.4, 0.4)
        rr = 0.0 if i == 0 else rnd.uniform(0.02, 0.04)
        h = rnd.uniform(0.17, 0.23)
        lean = (math.cos(a) * rnd.uniform(0.015, 0.035), math.sin(a) * rnd.uniform(0.015, 0.035))
        f = wild_stem_flower(h, lean, poppy_head(rnd.uniform(0.019, 0.024), seed=i), rnd.uniform(0.5, 0.9), stem_r=0.0011)
        f.xform(Matrix.Translation((rr * math.cos(a), rr * math.sin(a), 0.0)))
        part.add(f)
    # a nodding bud, hairy green with a coral seam
    s, pts = stem(0.15, (-0.03, 0.01), 0.001, 4, 4)
    s.paint(lambda p, n_: green_paint(p, n_, 0.15))
    bud = icosphere(1, 1.0)
    bud.xform(scale_m(0.006, 0.006, 0.009))
    bud.paint(lambda p, n_: mix(hexc("#6f8a45"), hexc("#a8b77a"), 0.5 + 0.5 * n_.z))
    bud.xform(Matrix.Translation(pts[-1] + Vector((-0.006, 0.0, -0.006))) @ Matrix.Rotation(2.3, 4, "Y"))
    part.add(s).add(bud)
    for i in range(4):
        phi = TAU * i / 4 + rnd.uniform(-0.3, 0.3)
        part.add(leaf(rnd.uniform(0.05, 0.075), rnd.uniform(0.006, 0.009), phi, lift=1.0, droop=0.8)
                 .paint(lambda q, n_: green_paint(q, n_, 0.05)))
    return bake_ao(part, 0.05, strength=0.55, rays=24)


def cornflower():
    """A cornflower stem branching into three ragged dusty-blue heads (fringed florets round a deeper violet eye),
    each sitting on a scaly grey-green bract cup."""
    rnd = random.Random(73)
    part = Part()
    s, pts = stem(0.15, (0.008, 0.004), 0.001, 4, 4)
    s.paint(lambda p, n_: green_paint(p, n_, 0.15))
    part.add(s)
    for b in range(3):
        a = TAU * b / 3 + rnd.uniform(-0.3, 0.3)
        top = pts[-1] if b == 0 else pts[-2]
        tip = top + (Vector((0, 0, 0.012)) if b == 0 else Vector((math.cos(a) * 0.025, math.sin(a) * 0.025, rnd.uniform(0.015, 0.03))))
        if b:
            br = tube([top, (top + tip) * 0.5 + Vector((0, 0, 0.004)), tip], [0.0009, 0.0008, 0.0007], 4,
                      cap_start=False, cap_end=False)
            br.paint(lambda p, n_: green_paint(p, n_, 0.15))
            part.add(br)
        r = rnd.uniform(0.011, 0.014) * (1.0 if b == 0 else 0.85)
        ph = rnd.uniform(0, 6)

        def rmod(th, t, ph=ph):
            return 0.35 + 0.65 * min(1.0, 1.1 * abs(math.cos(4.5 * th)) ** 2.2) * (0.86 + 0.14 * math.sin(th * 37 + ph))

        prof = [(0.0, 0.002), (0.5 * r, 0.004), (r, 0.006), (0.5 * r, 0.002), (0.0, 0.0)]
        head = lathe(prof, 54, rmod=rmod, phase=ph)
        head.paint(lambda p, n_, r=r: mix(hexc("#5b6aa8"), hexc("#9cb2de"), smoothstep(0.2, 0.9, Vector((p.x, p.y)).length / r)))
        eye = icosphere(1, 1.0)
        eye.xform(Matrix.Translation((0, 0, 0.0045)) @ scale_m(r * 0.28, r * 0.28, r * 0.2))
        eye.paint(lambda p, n_: hexc("#4a4a80"))
        cupb = icosphere(1, 1.0)
        cupb.xform(Matrix.Translation((0, 0, -0.002)) @ scale_m(r * 0.42, r * 0.42, r * 0.5))
        cupb.paint(lambda p, n_: mix(hexc("#6f7f5a"), hexc("#a4ad8c"), 0.5 + 0.5 * math.sin(p.z * 3000)))
        h = Part().add(cupb).add(head).add(eye)
        up = (tip - top).normalized() + Vector((0, 0, 1.2))
        h.xform(Matrix.Translation(tip) @ align_z(up.normalized()))
        part.add(h)
    for i in range(3):
        phi = TAU * i / 3 + rnd.uniform(-0.3, 0.3)
        part.add(leaf(rnd.uniform(0.05, 0.07), rnd.uniform(0.003, 0.0045), phi, lift=1.1, droop=0.7)
                 .paint(lambda q, n_: mix(green_paint(q, n_, 0.05), hexc("#9aa88a"), 0.35)))
    return bake_ao(part, 0.04, strength=0.55, rays=24)


def clover_clump():
    """Low red-clover: three or four knobbly pale-pink pompom heads among trefoil leaves with a pale chevron."""
    rnd = random.Random(87)
    part = Part()
    for i in range(4):
        a = TAU * i / 4 + rnd.uniform(-0.4, 0.4)
        rr = rnd.uniform(0.0, 0.035)
        h = rnd.uniform(0.045, 0.07)
        s, pts = stem(h, (math.cos(a) * 0.01, math.sin(a) * 0.01), 0.0009, 4, 3)
        s.paint(lambda p, n_: green_paint(p, n_, 0.06))
        r = rnd.uniform(0.0075, 0.0095)
        # a head of ~30 tiny tubular florets (a smooth ball read as a pink Easter egg): each a little cone pointing
        # out and up, deep rose at the base of the head, pale pink at the top, a touch of brown on the lowest ones
        hd = Part()
        nf = 30
        for q in range(nf):
            zz = 1.0 - 1.6 * (q + 0.5) / nf
            rq = math.sqrt(max(0.0, 1 - zz * zz))
            th = q * 2.39996 + i
            d = Vector((rq * math.cos(th), rq * math.sin(th), zz))
            fl = lathe([(0.0, 0.0), (0.32, 0.25), (0.22, 1.0), (0.0, 1.05)], 5)
            fl.xform(scale_m(r * 0.42, r * 0.42, r * 0.62))
            fl.xform(Matrix.Translation(d * r * 0.55) @ align_z((d + Vector((0, 0, 0.5))).normalized()))
            k = smoothstep(-0.6, 0.9, zz)
            col = mix(hexc("#a0687a") if zz > -0.45 else hexc("#8a6a5a"), hexc("#f0cfdb"), k)
            fl.paint(lambda p, n_, col=col: col)
            hd.add(fl)
        hd.xform(Matrix.Translation(pts[-1] + Vector((0, 0, r * 0.7))))
        f = Part().add(s).add(hd)
        f.xform(Matrix.Translation((rr * math.cos(a), rr * math.sin(a), 0.0)))
        part.add(f)
    # trefoil leaves on short stalks
    for k in range(6):
        a = TAU * k / 6 + rnd.uniform(-0.3, 0.3)
        base = Vector((math.cos(a) * rnd.uniform(0.01, 0.04), math.sin(a) * rnd.uniform(0.01, 0.04), 0.0))
        top = base + Vector((0, 0, rnd.uniform(0.02, 0.035)))
        st = tube([base, top], [0.0007, 0.0006], 3, cap_start=False, cap_end=False)
        st.paint(lambda p, n_: green_paint(p, n_, 0.04))
        part.add(st)
        for j in range(3):
            phi = a + TAU * j / 3
            lr = rnd.uniform(0.0065, 0.008)
            prof = [(0.0, 0.0006), (lr, 0.0), (0.0, -0.0004)]
            lf = lathe(prof, 12, rmod=lambda th, t: 0.62 + 0.38 * abs(math.cos(th)))
            lf.paint(lambda p, n_, lr=lr: mix(hexc("#3f7a34"), hexc("#a6c58e"),
                                              0.6 * smoothstep(0.3, 0.55, Vector((p.x, p.y)).length / lr)
                                              * (1 - smoothstep(0.6, 0.75, Vector((p.x, p.y)).length / lr))))
            lf.xform(Matrix.Translation(top + Vector((math.cos(phi), math.sin(phi), 0.0)) * lr * 0.95)
                     @ Matrix.Rotation(phi, 4, "Z") @ Matrix.Rotation(-0.25, 4, "Y"))
            part.add(lf)
    return bake_ao(part, 0.03, strength=0.55, rays=20)


def cow_parsley():
    """Cow parsley (wild chervil): a tall thin stem holding flat lacy umbels of tiny cream florets on fine rays, and a
    smaller side umbel; airy white lace above the meadow."""
    rnd = random.Random(97)
    part = Part()
    s, pts = stem(0.34, (0.02, -0.01), 0.0013, 4, 5)
    s.paint(lambda p, n_: green_paint(p, n_, 0.34))
    part.add(s)
    cream, shade = hexc("#f4f1e4"), hexc("#d9d6c4")

    def umbel(centre, size, n_rays, seed):
        r2 = random.Random(seed)
        u = Part()
        for k in range(n_rays):
            a = TAU * k / n_rays + r2.uniform(-0.2, 0.2)
            L = size * r2.uniform(0.8, 1.05)
            tip = centre + Vector((math.cos(a) * L, math.sin(a) * L, L * r2.uniform(0.35, 0.6)))
            ray = tube([centre, (centre + tip) * 0.5 + Vector((0, 0, L * 0.12)), tip], [0.0005, 0.00045, 0.0004], 3,
                       cap_start=False, cap_end=False)
            ray.paint(lambda p, n_: green_paint(p, n_, 0.3))
            u.add(ray)
            for j in range(7):
                o = Vector((r2.uniform(-1, 1), r2.uniform(-1, 1), r2.uniform(-0.3, 0.6))) * size * 0.16
                fl = icosphere(0, 1.0)
                fr = r2.uniform(0.0017, 0.0024)
                fl.xform(Matrix.Translation(tip + o) @ scale_m(fr, fr, fr * 0.7))
                fl.paint(lambda p, n_: mix(shade, cream, 0.5 + 0.5 * n_.z))
                u.add(fl)
        return u

    part.add(umbel(pts[-1], 0.03, 10, 5))
    side_base = pts[-3]
    side_tip = side_base + Vector((-0.05, 0.02, 0.07))
    side = tube([side_base, (side_base + side_tip) * 0.5 + Vector((0, 0, 0.01)), side_tip], [0.001, 0.0009, 0.0008], 4,
                cap_start=False, cap_end=False)
    side.paint(lambda p, n_: green_paint(p, n_, 0.3))
    part.add(side).add(umbel(side_tip, 0.022, 8, 6))
    for i in range(3):
        phi = TAU * i / 3 + rnd.uniform(-0.3, 0.3)
        part.add(leaf(rnd.uniform(0.07, 0.09), rnd.uniform(0.008, 0.011), phi, lift=1.0, droop=0.9)
                 .paint(lambda q, n_: green_paint(q, n_, 0.05)))
    return bake_ao(part, 0.05, strength=0.5, rays=20)


# name -> (builder, triangle budget, roughness, sharp-edge angle or None, preview display height)
PROPS = [
    ("tree_round_a", tree_round_a, 8000, 0.85, None, 2.3),
    ("tree_round_b", tree_round_b, 8000, 0.85, None, 2.5),
    ("daisy_clump", daisy_clump, 3000, 0.7, None, 1.1),
    ("daisy_single", daisy_single, 400, 0.7, None, 0.8),
    ("bush_a", bush_a, 6000, 0.85, None, 1.2),
    ("bush_b", bush_b, 6000, 0.85, None, 1.05),
    ("mushroom_red", mushroom_red, 6000, 0.55, None, 0.75),
    ("mushroom_pair", mushroom_pair, 6000, 0.55, None, 0.55),
    ("fence_segment", fence_segment, 6000, 0.65, 40.0, 0.7),
    ("stone_a", stone_a, 6000, 0.8, None, 0.45),
    ("stone_b", stone_b, 6000, 0.8, None, 0.3),
    ("stone_c", stone_c, 6000, 0.8, None, 0.22),
    ("wand", wand, 6000, 0.22, None, 0.9),
    ("flower_pot", flower_pot, 6000, 0.7, None, 1.0),
    ("tulip_clump", tulip_clump, 6000, 0.7, None, 0.85),
    ("buttercup_clump", buttercup_clump, 3000, 0.6, None, 0.5),
    ("forget_me_not", forget_me_not, 3000, 0.7, None, 0.45),
    ("poppy_clump", poppy_clump, 3000, 0.7, None, 0.5),
    ("cornflower", cornflower, 3000, 0.7, None, 0.45),
    ("clover_clump", clover_clump, 3000, 0.7, None, 0.3),
    ("cow_parsley", cow_parsley, 4000, 0.7, None, 0.7),
]


# ---------------------------------------------------------------------------
# Blender objects, export, manifest
# ---------------------------------------------------------------------------

def make_material(name, roughness):
    mat = bpy.data.materials.new(name)
    try:
        mat.use_nodes = True
    except Exception:
        pass
    nt = mat.node_tree
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    vc = nt.nodes.new("ShaderNodeVertexColor")
    vc.layer_name = "Col"
    # The exporter writes the socket's default as baseColorFactor: keep it white so that
    # three.js (which multiplies COLOR_0 by the base colour) shows the vertex colours unchanged.
    bsdf.inputs["Base Color"].default_value = (1.0, 1.0, 1.0, 1.0)
    nt.links.new(vc.outputs["Color"], bsdf.inputs["Base Color"])
    mat.use_backface_culling = True  # closed meshes: export as single-sided (doubleSided false)
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = 0.0
    return mat


def make_object(name, part, roughness, sharp_angle):
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(p) for p in part.v], [], part.f)
    me.validate(clean_customdata=False)
    attr = me.color_attributes.new("Col", "FLOAT_COLOR", "POINT")
    flat = []
    for c in part.c[:len(me.vertices)]:
        flat += [srgb_to_lin(c[0]), srgb_to_lin(c[1]), srgb_to_lin(c[2]), 1.0]
    attr.data.foreach_set("color", flat)
    me.color_attributes.active_color = attr
    try:
        me.color_attributes.render_color_index = me.color_attributes.active_color_index
    except Exception:
        pass
    if part.uv is not None:
        lay = me.uv_layers.new(name="UVMap")
        loops = [0.0] * (len(me.loops) * 2)
        for li, lp in enumerate(me.loops):
            u, w = part.uv[lp.vertex_index]
            loops[li * 2], loops[li * 2 + 1] = u, w
        lay.data.foreach_set("uv", loops)
    me.shade_smooth()
    if sharp_angle:
        me.set_sharp_from_angle(angle=math.radians(sharp_angle))
    me.materials.append(make_material(name + "_mat", roughness))
    obj = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def export_glb(obj, path):
    for o in bpy.context.scene.objects:
        o.select_set(False)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.export_scene.gltf(
        filepath=path,
        export_format="GLB",
        use_selection=True,
        export_yup=True,
        export_apply=True,
        export_vertex_color="ACTIVE",
        export_all_vertex_colors=False,
        export_normals=True,
        export_texcoords=True,
        export_materials="EXPORT",
        export_image_format="NONE",
        export_cameras=False,
        export_lights=False,
        export_animations=False,
        export_draco_mesh_compression_enable=False,
    )


def build(only):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    os.makedirs(OUT_DIR, exist_ok=True)
    manifest_path = os.path.join(OUT_DIR, "manifest.json")
    manifest = {}
    if only and os.path.exists(manifest_path):
        with open(manifest_path) as fh:
            manifest = {m["name"]: m for m in json.load(fh)}
    objects = []
    for name, fn, budget, rough, sharp, disp_h in PROPS:
        if only and name not in only:
            continue
        part = fn()
        tris = part.tris()
        lo, hi = part.bbox()
        if name != "wand" and abs(lo[2]) > 1e-4:
            part.xform(Matrix.Translation((0, 0, -lo[2])))
            lo, hi = part.bbox()
        flag = "" if tris <= budget else "  OVER BUDGET"
        print(f"[props] {name}: {tris} tris, {len(part.v)} verts, bbox {tuple(round(x, 3) for x in lo)}"
              f" .. {tuple(round(x, 3) for x in hi)}{flag}")
        obj = make_object(name, part, rough, sharp)
        export_glb(obj, os.path.join(OUT_DIR, name + ".glb"))
        radius = max(math.hypot(p.x, p.y) for p in part.v)
        entry = {"name": name, "file": name + ".glb", "height_m": round(hi[2] - lo[2], 4),
                 "radius_m": round(radius, 4), "tris": tris}
        if name == "wand":
            entry["origin"] = "ring_centre"
            entry["ring_inner_radius_m"] = 0.035
            entry["ring_tube_radius_m"] = 0.006
        manifest[name] = entry
        objects.append((obj, lo, hi, disp_h))
    order = [p[0] for p in PROPS]
    with open(manifest_path, "w") as fh:
        json.dump([manifest[n] for n in order if n in manifest], fh, indent=2)
        fh.write("\n")
    print("[props] wrote", manifest_path)
    return objects


# ---------------------------------------------------------------------------
# Preview contact sheet
# ---------------------------------------------------------------------------

def render_preview(objects, path):
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x, scene.render.resolution_y = 960, 540
    scene.render.resolution_percentage = 100
    try:
        scene.eevee.taa_render_samples = 32
    except Exception:
        pass
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.look = "None"

    world = bpy.data.worlds.new("sky")
    scene.world = world
    try:
        world.use_nodes = True
    except Exception:
        pass
    bg = next(n for n in world.node_tree.nodes if n.type == "BACKGROUND")
    bg.inputs["Color"].default_value = (*[srgb_to_lin(c) for c in hexc("#bfe3ff")], 1.0)
    bg.inputs["Strength"].default_value = 1.0

    sun_data = bpy.data.lights.new("sun", "SUN")
    sun_data.energy = 3.2
    sun_data.color = hexc("#fff3dc")
    sun_data.angle = math.radians(12)
    sun = bpy.data.objects.new("sun", sun_data)
    sun.rotation_euler = (math.radians(50), 0.0, math.radians(-35))
    scene.collection.objects.link(sun)

    bpy.ops.mesh.primitive_plane_add(size=60, location=(0, 0, 0))
    ground = bpy.context.active_object
    gm = bpy.data.materials.new("ground")
    try:
        gm.use_nodes = True
    except Exception:
        pass
    gb = next(n for n in gm.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    gb.inputs["Base Color"].default_value = (*[srgb_to_lin(c) for c in hexc("#a9dc86")], 1.0)
    gb.inputs["Roughness"].default_value = 0.95
    ground.data.materials.append(gm)

    back = [o for o in objects if o[0].name in ("tree_round_a", "tree_round_b", "bush_a", "bush_b",
                                                 "fence_segment", "flower_pot")]
    front = [o for o in objects if o not in back]
    gap = 0.3
    rows = []
    for row, y in ((back, 3.2), (front, 0.0)):
        items = []
        for obj, lo, hi, disp_h in row:
            s = disp_h / max(1e-6, hi[2] - lo[2])
            items.append((obj, lo, hi, s, (hi[0] - lo[0]) * s))
        width = sum(i[4] for i in items) + gap * max(0, len(items) - 1)
        rows.append((items, y, width))
    max_w = max(r[2] for r in rows) if rows else 1.0
    for items, y, width in rows:
        x = -width / 2
        for obj, lo, hi, s, w in items:
            obj.scale = (s, s, s)
            obj.location = (x - lo[0] * s, y, -lo[2] * s)
            x += w + gap

    cam_data = bpy.data.cameras.new("cam")
    cam_data.type = "ORTHO"
    cam_data.ortho_scale = max_w + 0.8
    cam = bpy.data.objects.new("cam", cam_data)
    pitch = math.radians(64)
    cam.rotation_euler = (pitch, 0.0, 0.0)
    target = Vector((0.0, 1.6, 1.15))
    cam.location = target - Vector((0.0, math.sin(pitch), -math.cos(pitch))) * 30.0
    scene.collection.objects.link(cam)
    scene.camera = cam

    os.makedirs(os.path.dirname(path), exist_ok=True)
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
    print("[props] preview", path)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def read_glb_json(path):
    with open(path, "rb") as fh:
        data = fh.read()
    magic, version, length = struct.unpack_from("<III", data, 0)
    assert magic == 0x46546C67, "not a GLB"
    clen, ctype = struct.unpack_from("<II", data, 12)
    return json.loads(data[20:20 + clen].decode("utf-8")), len(data)


def validate():
    names = [p[0] for p in PROPS]
    with open(os.path.join(OUT_DIR, "manifest.json")) as fh:
        manifest = {m["name"]: m for m in json.load(fh)}
    ok = True
    for name in names:
        path = os.path.join(OUT_DIR, name + ".glb")
        if not os.path.exists(path):
            print(f"[validate] {name}: MISSING")
            ok = False
            continue
        gl, size = read_glb_json(path)
        prims = [p for m in gl.get("meshes", []) for p in m["primitives"]]
        has_col = all("COLOR_0" in p["attributes"] for p in prims)
        pos = [gl["accessors"][p["attributes"]["POSITION"]] for p in prims]
        mn = [min(a["min"][k] for a in pos) for k in range(3)]
        mx = [max(a["max"][k] for a in pos) for k in range(3)]
        tris = sum(gl["accessors"][p["indices"]]["count"] // 3 for p in prims)
        extras = [k for k in ("images", "textures", "cameras") if gl.get(k)]
        for m in gl.get("materials", []):
            bc = m.get("pbrMetallicRoughness", {}).get("baseColorFactor", [1, 1, 1, 1])
            if min(bc[:3]) < 0.999:
                extras.append("baseColorFactor!=1")
        exts = gl.get("extensionsUsed", [])
        # Fresh-scene re-import through Blender's importer (converts Y-up back to Z-up).
        bpy.ops.wm.read_factory_settings(use_empty=True)
        bpy.ops.import_scene.gltf(filepath=path)
        meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
        cols = [a.name for o in meshes for a in o.data.color_attributes]
        corners = [o.matrix_world @ Vector(c) for o in meshes for c in o.bound_box]
        bmin = [min(c[k] for c in corners) for k in range(3)]
        bmax = [max(c[k] for c in corners) for k in range(3)]
        good = has_col and not extras and "KHR_draco_mesh_compression" not in exts and len(meshes) == 1
        if name != "wand":
            good = good and abs(mn[1]) < 1e-3 and abs(mx[1] - manifest[name]["height_m"]) < 1e-3
        ok = ok and good
        print(f"[validate] {name}: {'OK ' if good else 'BAD'} {size / 1024:.0f} KB, tris {tris}, "
              f"prims {len(prims)}, COLOR_0 {has_col}, extras {extras or '-'}, ext {exts or '-'}\n"
              f"           glTF(Y-up) min {[round(x, 3) for x in mn]} max {[round(x, 3) for x in mx]}\n"
              f"           Blender re-import objs {len(meshes)} colour attrs {cols} "
              f"bbox min {[round(x, 3) for x in bmin]} max {[round(x, 3) for x in bmax]}")
    print("[validate] ALL OK" if ok else "[validate] PROBLEMS FOUND")


def main():
    if "--validate" in ARGS:
        validate()
        return
    only = set(filter(None, (arg_value("--only", "") or "").split(",")))
    objects = build(only)
    if "--no-preview" not in ARGS and objects:
        render_preview(objects, arg_value("--preview", DEFAULT_PREVIEW))


main()
