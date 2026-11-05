"""Build the stitches short scene. Run: blender -b --python tools/build_scene.py -- build/scene.blend [--cuts 23] [--hair 12000]
One file on purpose. Sections: human, wound field, materials, stitches, clothes, walk, camera, render settings.
Units are metres. Man walks toward -X on a treadmill; camera sits at -Y; near leg is the left leg.
Armature space (where all wound work happens): he faces -Y, his left is +X, up is +Z."""
import math
import random
import sys
import bpy
import bmesh
import numpy as np
from mathutils import Matrix, Quaternion, Vector
from mathutils.bvhtree import BVHTree

from bl_ext.blender_org.mpfb.services.humanservice import HumanService

FPS = 30000 / 1001
FRAMES = 930
ZC, HALF_L = 0.37, 0.066  # wound centre height, half length


def fr(t):
    return int(round(t * FPS)) + 1


def get_arg(name, default):
    a = sys.argv
    return int(a[a.index(name) + 1]) if name in a else default


# ---------------------------------------------------------------- human
def build_human():
    macro = {"gender": 1.0, "age": 0.5, "muscle": 0.88, "weight": 0.62, "proportions": 0.7,
             "height": 0.55, "cupsize": 0.5, "firmness": 0.5,
             "race": {"asian": 0.0, "caucasian": 1.0, "african": 0.0}}
    body = HumanService.create_human(mask_helpers=False, macro_detail_dict=macro)
    rig = HumanService.add_builtin_rig(body, "default", import_weights=True)
    bpy.context.view_layer.objects.active = body
    body.select_set(True)
    if body.data.shape_keys:
        bpy.ops.object.shape_key_remove(all=True, apply_mix=True)
    # Keep only skin below the lower spine; helpers, arms, and the upper body never reach the frame.
    vg = body.vertex_groups["body"].index
    bm = bmesh.new()
    bm.from_mesh(body.data)
    dl = bm.verts.layers.deform.verify()
    kill = [v for v in bm.verts if vg not in v[dl] or v.co.z > 1.08 or abs(v.co.x) > 0.30]
    bmesh.ops.delete(bm, geom=kill, context="VERTS")
    bm.to_mesh(body.data)
    bm.free()
    for g in list(body.vertex_groups):
        if not g.name.startswith(("upperleg", "lowerleg", "foot", "toe", "pelvis", "spine", "root")):
            body.vertex_groups.remove(g)
    for m in list(body.modifiers):
        if m.type != "ARMATURE":
            body.modifiers.remove(m)
    for p in body.data.polygons:
        p.use_smooth = True
    return body, rig


def add_subsurf_applied(ob, levels=1):
    bpy.context.view_layer.objects.active = ob
    m = ob.modifiers.new("ss", "SUBSURF")
    m.levels = levels
    bpy.ops.object.modifier_move_to_index(modifier="ss", index=0)
    bpy.ops.object.modifier_apply(modifier="ss")


# ---------------------------------------------------------------- wound field
def sm(x, a, b):
    t = np.clip((x - a) / (b - a), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def centre(v):
    """Wavy cut line: tangential offset from Y0 at normalized height v in -1..1."""
    return 0.0017 * np.sin(2.3 * np.pi * v + 0.6) + 0.0006 * np.sin(5.3 * np.pi * v + 1.1)


def taper(v):
    return np.sqrt(np.clip(1 - v * v, 0, 1))


def lobes(v, side):
    """Half-width of the swollen lips: lobed along the cut, wider on the camera-right side."""
    base = 0.0058 if side < 0 else 0.0085
    wave = 0.0019 * np.sin(4.1 * np.pi * v + (0.4 if side < 0 else 1.6)) + 0.0012 * np.sin(7.3 * np.pi * v + (2.0 if side < 0 else 0.3))
    return (base + wave) * sm(1.12 - np.abs(v), 0, 0.22) * (0.72 + 0.28 * sm(0.4 - v, 0, 0.9)) + 1e-5


def field(u, v):
    """Every stage displacement (metres along the normal) and every mask at (u, v)."""
    au, T = np.abs(u), taper(v)
    inside = np.abs(v) < 1
    w_o, w_c, w_g = 0.0058 * T + 1e-4, 0.0011 * T + 1e-4, 0.0026 * T + 1e-4
    g_open = (1 - sm(au, w_o * 0.55, w_o)) * inside
    g_close = (1 - sm(au, w_c * 0.4, w_c)) * inside
    g_gap = (1 - sm(au, w_g * 0.6, w_g)) * inside
    rim = np.exp(-((au - w_o * 1.25) / 0.0016) ** 2) * T
    s = np.where(u < 0, lobes(v, -1), lobes(v, 1))
    lobe = 1 - sm(au, s * 0.72, s * 1.02)
    fringe = (1 - sm(au, s * 1.0, s * 1.55)) * (1 - lobe)
    swell_h = 0.0044 * (0.72 + 0.28 * np.sin(3.3 * np.pi * v + 0.9)) * lobe * sm(au, 0, 0.0016)
    scar = (1 - sm(au, 0.0010, 0.0026)) * sm(1.0 - np.abs(v), 0, 0.12)
    return dict(open=-0.0028 * g_open + 0.0009 * rim, closed=-0.0042 * g_close, swell=swell_h,
                gap=-0.0022 * g_gap, scar=0.0007 * scar, g_open=g_open, g_close=g_close, g_gap=g_gap,
                lobe=lobe, fringe=fringe, scar_m=scar)


def vessel_segments():
    """Branching lines in (u, v) with growth order t. Two trunks braid along the cut; twigs leave them."""
    segs = []
    rng = random.Random(11)
    for sign in (-1, 1):
        vs = np.linspace(-0.98, 0.98, 46)
        us = sign * (0.0024 * np.sin(5.2 * np.pi * vs + (0.3 if sign > 0 else 2.2)) + 0.0006)
        for i in range(len(vs) - 1):
            t = abs(vs[i]) * 0.55
            segs.append((us[i], vs[i], us[i + 1], vs[i + 1], t, 0.0009))
            if rng.random() < 0.24:
                a, b = us[i], vs[i]
                d = rng.choice((-1, 1))
                for j in range(rng.randint(2, 5)):
                    a2 = a + d * rng.uniform(0.0007, 0.0020)
                    b2 = b + rng.uniform(-0.03, 0.03)
                    segs.append((a, b, a2, b2, t + 0.12 + j * 0.08, 0.00095 - j * 0.00012))
                    a, b = a2, b2
    return segs


def vessel_field(u, v):
    """Distance to the nearest segment over its width, and that segment's growth order, per point."""
    best, order = np.full(u.shape, 9.0), np.full(u.shape, 2.0)
    for a, b, c, e, t, wid in vessel_segments():
        ax, ay = a, b * HALF_L
        dx, dy = c - a, (e - b) * HALF_L
        l2 = dx * dx + dy * dy + 1e-12
        h = np.clip(((u - ax) * dx + (v * HALF_L - ay) * dy) / l2, 0, 1)
        d = np.hypot(u - ax - h * dx, v * HALF_L - ay - h * dy) / wid
        m = d < best
        best[m], order[m] = d[m], t
    return best, order


def build_patch(body, cuts):
    """Subdivide calf skin around the cut, then write shape keys and attributes on the real skin mesh.
    The wound IS the skin: nothing floats above it, so no triangulation poke-through (transcript's bug)."""
    me = body.data
    bm = bmesh.new()
    bm.from_mesh(me)
    # Y0: tangential centre of the outer calf at the wound height.
    ring = [v for v in bm.verts if v.co.x > 0.12 and abs(v.co.z - ZC) < 0.02]
    y0 = sum(v.co.y for v in sorted(ring, key=lambda v: -v.co.x)[:8]) / 8 + 0.006
    faces = [f for f in bm.faces if f.calc_center_median().x > 0.13
             and abs(f.calc_center_median().z - ZC) < 0.112
             and abs(f.calc_center_median().y - y0) < 0.046]
    edges = list({e for f in faces for e in f.edges})
    print("PATCH faces", len(faces), "y0", y0)
    bmesh.ops.subdivide_edges(bm, edges=edges, cuts=cuts, use_grid_fill=True, smooth=1.0)
    bm.normal_update()
    bm.to_mesh(me)
    bm.free()
    me.update()
    n = len(me.vertices)
    co = np.empty(n * 3)
    me.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    nor = np.empty(n * 3)
    me.vertex_normals.foreach_get("vector", nor)
    nor = nor.reshape(-1, 3)
    v = (co[:, 2] - ZC) / HALF_L
    u = co[:, 1] - y0 - centre(np.clip(v, -1, 1))
    far = (co[:, 0] < 0.12) | (np.abs(u) > 0.03) | (np.abs(v) > 1.5)
    f = field(u, v)
    vd, vt = vessel_field(u, v)
    for name in f:
        f[name] = np.where(far, 0.0, f[name])
    vd = np.where(far, 9.0, vd)
    ridge = 0.0026 * np.exp(-vd * vd) * np.clip(f["lobe"] + f["g_gap"], 0, 1) * sm(1.05 - np.abs(v), 0, 0.1)
    body.shape_key_add(name="Basis", from_mix=False)
    for name, d in (("open", f["open"]), ("closed", f["closed"]), ("swell", f["swell"]), ("gap", f["gap"]),
                    ("ridge", ridge), ("scar", f["scar"])):
        k = body.shape_key_add(name=name, from_mix=False)
        k.slider_min, k.slider_max = 0, 1.5
        k.data.foreach_set("co", (co + nor * d[:, None]).ravel())
    for name, val in (("a_g_open", f["g_open"]), ("a_g_close", f["g_close"]), ("a_g_gap", f["g_gap"]),
                      ("a_lobe", f["lobe"]), ("a_fringe", f["fringe"]), ("a_vd", np.clip(vd, 0, 9)),
                      ("a_vt", np.where(far, 2.0, vt)), ("a_scar", f["scar_m"]),
                      ("a_pale", np.where(co[:, 0] > 0.1, np.exp(-((u + 0.016) / 0.024) ** 2 - (v / 1.25) ** 2), 0.0))):
        a = me.attributes.new(name, "FLOAT", "POINT")
        a.data.foreach_set("value", val.astype(np.float32))
    rest = me.attributes.new("rest", "FLOAT_VECTOR", "POINT")
    rest.data.foreach_set("vector", co.astype(np.float32).ravel())
    print("MESH verts", n)
    return y0, co, nor


def key_value(owner, keys):
    for t, val in keys:
        owner.value = val
        owner.keyframe_insert("value", frame=fr(t))


# Stage timing (seconds, value) from beats.md.
STAGE_KEYS = {
    "open": [(0, 1), (2.6, 1), (5.0, 0)],
    "closed": [(0, 0), (2.6, 0), (5.0, 1), (15, 1), (18, 0.2), (24, 0)],
    "swell": [(0, 0), (8, 0), (11.5, 0.6), (15.5, 1), (24.8, 1), (26.6, 0)],
    "gap": [(0, 0), (13.2, 0), (15.5, 1), (19, 1), (22.5, 0.15), (25, 0)],
    "ridge": [(0, 0), (18.2, 0), (21, 0.8), (24, 1), (25, 0.8), (26.6, 0)],
    "scar": [(0, 0), (25, 0), (26.8, 1)],
}


# ---------------------------------------------------------------- materials
class G:
    """Thin node-graph helper: every call returns a node output socket."""

    def __init__(self, mat):
        mat.use_nodes = True
        self.t = mat.node_tree
        self.t.nodes.clear()

    def attr(self, name, out="Fac"):
        n = self.t.nodes.new("ShaderNodeAttribute")
        n.attribute_name = name
        return n.outputs[out]

    def val(self, name, keys):
        n = self.t.nodes.new("ShaderNodeValue")
        n.name = name
        for t, v in keys:
            n.outputs[0].default_value = v
            n.outputs[0].keyframe_insert("default_value", frame=fr(t))
        return n.outputs[0]

    def math(self, op, a, b=None):
        n = self.t.nodes.new("ShaderNodeMath")
        n.operation = op
        for i, x in enumerate((a, b)):
            if x is None:
                continue
            if isinstance(x, (int, float)):
                n.inputs[i].default_value = x
            else:
                self.t.links.new(x, n.inputs[i])
        return n.outputs[0]

    def ramp(self, x, a, b, c=0.0, d=1.0):
        n = self.t.nodes.new("ShaderNodeMapRange")
        n.interpolation_type = "SMOOTHSTEP"
        self.t.links.new(x, n.inputs["Value"])
        n.inputs["From Min"].default_value, n.inputs["From Max"].default_value = a, b
        n.inputs["To Min"].default_value, n.inputs["To Max"].default_value = c, d
        return n.outputs[0]

    def noise(self, vec, scale, detail=3.0, rough=0.55):
        n = self.t.nodes.new("ShaderNodeTexNoise")
        self.t.links.new(vec, n.inputs["Vector"])
        n.inputs["Scale"].default_value = scale
        n.inputs["Detail"].default_value = detail
        n.inputs["Roughness"].default_value = rough
        return n.outputs[0]

    def voronoi(self, vec, scale):
        n = self.t.nodes.new("ShaderNodeTexVoronoi")
        self.t.links.new(vec, n.inputs["Vector"])
        n.inputs["Scale"].default_value = scale
        return n.outputs["Distance"]

    def scale(self, vec, sx, sy, sz):
        n = self.t.nodes.new("ShaderNodeVectorMath")
        n.operation = "MULTIPLY"
        self.t.links.new(vec, n.inputs[0])
        n.inputs[1].default_value = (sx, sy, sz)
        return n.outputs[0]

    def mix(self, fac, a, b):
        n = self.t.nodes.new("ShaderNodeMix")
        n.data_type = "RGBA"
        n.clamp_factor = True
        for sock, x in (("A", a), ("B", b)):
            s = next(i for i in n.inputs if i.name == sock and i.type == "RGBA")
            if isinstance(x, tuple):
                s.default_value = (*x, 1)
            else:
                self.t.links.new(x, s)
        self.t.links.new(fac, n.inputs[0])
        return next(o for o in n.outputs if o.type == "RGBA")


def srgb(r, g, b):
    def f(c):
        c /= 255
        return c / 12.92 if c < 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    return (f(r), f(g), f(b))


def skin_material():
    m = bpy.data.materials.new("skin")
    g = G(m)
    t = g.t
    rest = g.attr("rest", "Vector")
    # Skin colour
    base = g.mix(g.ramp(g.noise(rest, 26, 4), 0.38, 0.62), srgb(214, 142, 96), srgb(190, 112, 72))
    base = g.mix(g.math("MULTIPLY", g.ramp(g.noise(rest, 170, 3), 0.48, 0.66), 0.2), base, srgb(205, 110, 78))
    pale = g.mix(g.math("MULTIPLY", g.ramp(g.noise(rest, 520, 3), 0.40, 0.70), 0.22), base, srgb(232, 186, 156))
    pale = g.mix(g.math("MULTIPLY", g.attr("a_pale"), 0.72), pale, srgb(236, 192, 170))
    dots = g.ramp(g.voronoi(rest, 640), 0.05, 0.22, 1.0, 0.0)
    col = g.mix(g.math("MULTIPLY", dots, 0.3), pale, srgb(130, 80, 58))
    # Hair-follicle dashes, stretched along the leg (Z)
    dash = g.ramp(g.noise(g.scale(rest, 900, 900, 170), 1, 2), 0.66, 0.74)
    col = g.mix(g.math("MULTIPLY", dash, 0.55), col, srgb(84, 50, 34))
    # Stage values
    k_inf = g.val("k_inf", [(0, 0), (8, 0), (11.5, 1), (24.6, 1), (26.5, 0.1), (31.1, 0)])
    k_yel = g.val("k_yel", [(0, 0), (13.4, 0), (15.2, 1), (18.5, 1), (20.5, 0.35), (23, 0)])
    k_v = g.val("k_v", [(0, 0), (18.2, 0), (18.6, 1), (21, 1), (22.6, 0), (31.1, 0)])
    k_grow = g.val("k_grow", [(0, 0), (18.2, 0), (20.6, 1.1), (31.1, 1.1)])
    k_tis = g.val("k_tis", [(0, 0), (20, 0), (22.4, 1), (25, 1), (26.4, 0)])
    k_scar = g.val("k_scar", [(0, 0), (25, 0), (26.6, 1), (31.1, 0.8)])
    k_open = g.val("k_open", [(0, 1), (2.6, 1), (5.0, 0), (31.1, 0)])
    k_closed = g.val("k_closed", [(0, 0), (2.6, 0), (5.0, 1), (15, 1), (18, 0.35), (24, 0)])
    lobe, fringe, vd = g.attr("a_lobe"), g.attr("a_fringe"), g.attr("a_vd")
    # Inflammation: orange fringe, then red lips, mottled by noise.
    col = g.mix(g.math("MULTIPLY", k_inf, g.math("MULTIPLY", fringe, 0.6)), col, srgb(214, 120, 60))
    red = g.mix(g.ramp(g.noise(rest, 300, 3), 0.42, 0.62), srgb(176, 62, 62), srgb(150, 42, 46))
    col = g.mix(g.math("MULTIPLY", k_inf, g.math("MULTIPLY", lobe, 0.96)), col, red)
    # Fibrous tissue: dark brown-red ridges over the lips while healing.
    tissue = g.mix(g.ramp(vd, 0.9, 2.2), srgb(92, 28, 24), srgb(190, 98, 90))
    col = g.mix(g.math("MULTIPLY", k_tis, g.math("MAXIMUM", lobe, g.attr("a_g_gap"))), col, tissue)
    # Yellow scaffold in the gap
    col = g.mix(g.math("MULTIPLY", k_yel, g.attr("a_g_gap")), col, srgb(232, 176, 58))
    # Vessels: bright orange-red, growing by order a_vt
    vmask = g.math("SUBTRACT", 1, g.ramp(vd, 0.8, 1.25))
    grown = g.math("SUBTRACT", 1, g.ramp(g.math("SUBTRACT", g.attr("a_vt"), k_grow), -0.03, 0.03))
    col = g.mix(g.math("MULTIPLY", g.math("MULTIPLY", vmask, grown), k_v), col, (0.85, 0.03, 0.005))
    # Open wound and closed cut
    inner = g.mix(g.ramp(g.attr("a_g_open"), 0.2, 0.85), srgb(232, 84, 44), srgb(142, 28, 22))
    col = g.mix(g.math("MULTIPLY", k_open, g.attr("a_g_open")), col, inner)
    col = g.mix(g.math("MULTIPLY", k_closed, g.attr("a_g_close")), col, srgb(26, 6, 6))
    # Scar
    col = g.mix(g.math("MULTIPLY", k_scar, g.attr("a_scar")), col, srgb(206, 92, 80))
    # Surface
    b = t.nodes.new("ShaderNodeBsdfPrincipled")
    t.links.new(col, b.inputs["Base Color"])
    t.links.new(g.math("ADD", 0.5, g.math("MULTIPLY", g.noise(rest, 240, 2), 0.16)), b.inputs["Roughness"])
    b.inputs["Subsurface Weight"].default_value = 0.45
    b.inputs["Subsurface Radius"].default_value = (0.9, 0.35, 0.18)
    b.inputs["Subsurface Scale"].default_value = 0.004
    b.inputs["Specular IOR Level"].default_value = 0.42
    # Bump: pores and fine grain.
    bump_h = g.math("ADD", g.math("MULTIPLY", dots, -0.5), g.math("MULTIPLY", g.noise(rest, 900, 4), 1.1))
    bump_h = g.math("ADD", bump_h, g.math("MULTIPLY", g.noise(g.scale(rest, 700, 700, 150), 1, 2), 0.9))
    bump_h = g.math("ADD", bump_h, g.math("MULTIPLY", g.noise(rest, 280, 4), 2.4))
    bump = t.nodes.new("ShaderNodeBump")
    t.links.new(bump_h, bump.inputs["Height"])
    bump.inputs["Strength"].default_value = 0.42
    bump.inputs["Distance"].default_value = 0.0011
    t.links.new(bump.outputs[0], b.inputs["Normal"])
    t.links.new(b.outputs[0], t.nodes.new("ShaderNodeOutputMaterial").inputs["Surface"])
    return m


def simple_material(name, rgb, rough=0.5, sss=0.0, metal=0.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*srgb(*rgb), 1)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    if sss:
        b.inputs["Subsurface Weight"].default_value = sss
        b.inputs["Subsurface Scale"].default_value = 0.001
    return m


def add_hair(body, rig, y0, count):
    """Real hair curves on the near lower leg, rigid with the shin bone. No particle system:
    particle hair came out about 10 cm long and took 37 s of a 38 s test frame."""
    me = body.data
    me.calc_loop_triangles()
    tri = np.empty(len(me.loop_triangles) * 3, dtype=np.int32)
    me.loop_triangles.foreach_get("vertices", tri)
    tri = tri.reshape(-1, 3)
    co = np.empty(len(me.vertices) * 3)
    me.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    nor = np.empty(len(me.vertices) * 3)
    me.vertex_normals.foreach_get("vector", nor)
    nor = nor.reshape(-1, 3)
    a, b, c = co[tri[:, 0]], co[tri[:, 1]], co[tri[:, 2]]
    area = np.linalg.norm(np.cross(b - a, c - a), axis=1)
    mid = (a + b + c) / 3
    v = (mid[:, 2] - ZC) / HALF_L
    u = mid[:, 1] - y0 - centre(np.clip(v, -1, 1))
    wound_keep = 1 - (1 - sm(np.abs(u), 0.022, 0.058)) * (1 - sm(np.abs(v), 1.05, 1.7))
    weight = area * wound_keep * (mid[:, 0] > 0.05) * sm(mid[:, 2], 0.135, 0.16) * (1 - sm(mid[:, 2], 0.44, 0.505))
    rng = np.random.default_rng(3)
    pick = rng.choice(len(tri), size=count, p=weight / weight.sum())
    r = rng.random((count, 2))
    flip = r.sum(1) > 1
    r[flip] = 1 - r[flip]
    w = np.stack((r[:, 0], r[:, 1], 1 - r.sum(1)), 1)
    idx = tri[pick]
    root = (co[idx] * w[..., None]).sum(1)
    n = (nor[idx] * w[..., None]).sum(1)
    n /= np.linalg.norm(n, axis=1, keepdims=True)
    # Lie down the leg, with some spread: down-the-leg tangent, plus random sideways, plus a little normal.
    down = np.array([0.0, 0.0, -1.0]) + n * n[:, 2:3]
    down /= np.linalg.norm(down, axis=1, keepdims=True)
    side = np.cross(n, down)
    length = rng.uniform(0.003, 0.006, (count, 1))
    tip_dir = down + side * rng.normal(0, 0.45, (count, 1)) + n * rng.uniform(0.18, 0.42, (count, 1))
    tip_dir /= np.linalg.norm(tip_dir, axis=1, keepdims=True)
    midp = root + (tip_dir * 0.5 + n * 0.08) * length
    tip = root + tip_dir * length
    pos = np.stack((root, midp, tip), 1).astype(np.float32)
    hc = bpy.data.hair_curves.new("hair")
    hc.add_curves([3] * count)
    hc.attributes["position"].data.foreach_set("vector", pos.ravel())
    rad = hc.attributes.get("radius") or hc.attributes.new("radius", "FLOAT", "POINT")
    rad.data.foreach_set("value", np.tile(np.array([0.00006, 0.00004, 0.000012], np.float32), count))
    hc.materials.append(simple_material("hair", (92, 62, 42), 0.45))
    ob = bpy.data.objects.new("hair", hc)
    bpy.context.scene.collection.objects.link(ob)
    parent_bone(ob, rig)


# ---------------------------------------------------------------- stitches, thread, needle, scissors
def curve_ob(name, pts, mat, depth):
    cu = bpy.data.curves.new(name, "CURVE")
    cu.dimensions = "3D"
    cu.bevel_depth = depth
    cu.bevel_resolution = 3
    cu.resolution_u = 8
    cu.use_fill_caps = True
    sp = cu.splines.new("NURBS")
    sp.points.add(len(pts) - 1)
    for p, c in zip(sp.points, pts):
        p.co = (*c, 1)
    sp.use_endpoint_u = True
    sp.order_u = 3
    ob = bpy.data.objects.new(name, cu)
    bpy.context.scene.collection.objects.link(ob)
    cu.materials.append(mat)
    return ob


def parent_bone(ob, rig, bone="lowerleg02.L"):
    """Bone-parent, keeping armature-space coordinates: the parent inverse cancels the bone's rest matrix."""
    ob.parent = rig
    ob.parent_type = "BONE"
    ob.parent_bone = bone
    b = rig.data.bones[bone]
    ob.matrix_parent_inverse = (b.matrix_local @ Matrix.Translation((0, b.length, 0))).inverted()


def surf(tree, y0, u, v, lift=0.0):
    """Skin point at (u, v), raised by lift along the normal; returns (point, normal)."""
    y = float(y0 + centre(np.clip(v, -1, 1)) + u)
    z = float(ZC + v * HALF_L)
    p, n, _, _ = tree.ray_cast(Vector((0.6, y, z)), Vector((-1, 0, 0)))
    if n.x < 0:
        n = -n
    return p + n * lift, n


STITCH_TIMES = [-0.5 + i * 7.5 / 30 for i in range(12)]  # one per 7.5 frames (transcript: 6-8 frames)


def stitch_v(i):
    return 0.92 - i * 1.84 / (len(STITCH_TIMES) - 1)


def build_stitches(body, rig, y0):
    # Ray-cast the rest mesh: body.data.vertices holds the Basis key.
    tree = BVHTree.FromPolygons([v.co.copy() for v in body.data.vertices],
                                [p.vertices[:] for p in body.data.polygons])
    white = simple_material("thread", (240, 240, 240), 0.38, sss=0.25)
    loopm = simple_material("loop", (176, 176, 186), 0.5)
    steel = simple_material("steel", (226, 228, 232), 0.22, metal=1.0)
    blue_steel = simple_material("blue_steel", (178, 194, 232), 0.34, metal=0.45)
    gold = simple_material("gold", (214, 176, 96), 0.3, metal=1.0)
    n = len(STITCH_TIMES)
    for i, t0 in enumerate(STITCH_TIMES):
        v0 = stitch_v(i)
        slope = 0.15 + 1.1 * max(0.0, 0.15 - v0)  # flat on top, slanted on the lower half (reference)
        half = 0.0064 + 0.0012 * math.sin(i * 1.7)
        rest_pts, swell_pts = [], []
        for u in np.linspace(-half, half, 9):
            v = v0 + slope * u / HALF_L
            fld = field(np.array([u]), np.array([v]))
            lift = 0.0011 - 0.0026 * float(sm(abs(u) / half, 0.72, 1.0))
            p, nor = surf(tree, y0, u, v, lift)
            rest_pts.append(p)
            edge = field(np.array([half]), np.array([v0 + slope * half / HALF_L]))["swell"][0]
            edge2 = field(np.array([-half]), np.array([v0 - slope * half / HALF_L]))["swell"][0]
            flat = 0.5 * float(edge + edge2)
            swell_pts.append(p + nor * (flat + 0.0036 * (1 - (u / half) ** 2)))
        ob = curve_ob(f"stitch{i:02d}", rest_pts, white, 0.00072)
        ob.shape_key_add(name="Basis", from_mix=False)
        ks = ob.shape_key_add(name="swell", from_mix=False)
        for d, c in zip(ks.data, swell_pts):
            d.co = c
        key_value(ks, STAGE_KEYS["swell"])
        # Draw itself over 7 frames, thicken for the macro framing, thin and vanish at the end.
        cu = ob.data
        if t0 + 7 / 30 > 0:  # stitches that landed before frame 1 stay whole
            cu.bevel_factor_end = 0.0
            cu.keyframe_insert("bevel_factor_end", frame=max(1, fr(t0) - 1))
            cu.bevel_factor_end = 1.0
            cu.keyframe_insert("bevel_factor_end", frame=max(2, fr(t0 + 7 / 30)))
        for t, dep in ((0, 0.00095), (12.5, 0.00095), (16, 0.0010), (24.6, 0.0010), (25.6, 0.00055), (26.4, 0.0)):
            cu.bevel_depth = dep
            cu.keyframe_insert("bevel_depth", frame=fr(t))
        parent_bone(ob, rig)
        # Slack thread loop on the camera-right side: cast-shadow zigzag until pulled tight at 4.6 s.
        if i < n - 1:
            v1 = stitch_v(i + 1)
            pa, na = surf(tree, y0, half, v0 + slope * half / HALF_L, 0.0003)
            pb, _ = surf(tree, y0, -half, v1, 0.0003)
            far_u = 0.020 + 0.003 * math.sin(i * 2.1)
            pc, _ = surf(tree, y0, far_u, (v0 + v1) / 2 + 0.05, 0.007)
            pd, _ = surf(tree, y0, far_u * 0.45, v1 + 0.03, 0.004)
            lp = curve_ob(f"loop{i:02d}", [pa, pa.lerp(pc, 0.55) + na * 0.004, pc, pd, pb], loopm, 0.00032)
            lp.shape_key_add(name="Basis", from_mix=False)
            kt = lp.shape_key_add(name="taut", from_mix=False)
            sink = pa.lerp(pb, 0.5) - na * 0.002
            for d, c in zip(kt.data, [pa, sink, sink, sink, pb]):
                d.co = c
            key_value(kt, [(0, 0), (3.2, 0), (5.0, 0.8)])  # a small loop stays until 10 s, as in the reference
            lc = lp.data
            if t0 + 13 / 30 > 0:
                lc.bevel_factor_end = 0.0
                lc.keyframe_insert("bevel_factor_end", frame=max(1, fr(t0 + 6 / 30)))
                lc.bevel_factor_end = 1.0
                lc.keyframe_insert("bevel_factor_end", frame=max(2, fr(t0 + 13 / 30)))
            lp.hide_render = False
            lp.keyframe_insert("hide_render", frame=fr(10))
            lp.hide_render = True
            lp.keyframe_insert("hide_render", frame=fr(10.05))
            parent_bone(lp, rig)
    # Lead thread: from the top stitch, off-screen left, until 4.0 s.
    a, nor = surf(tree, y0, -0.0066, stitch_v(0), 0.0012)
    lead_pts = [a + Vector((0.0, -(j / 5) ** 1.5 * 0.42, 0.015 * j / 5 - 0.03 * (j / 5) ** 2))
                + nor * (0.012 * math.sin(math.pi * min(j * 3 / 5, 1))) for j in range(6)]
    lead = curve_ob("lead", lead_pts, loopm, 0.00038)
    parent_bone(lead, rig)
    lead.hide_render = False
    lead.keyframe_insert("hide_render", frame=fr(3.95))
    lead.hide_render = True
    lead.keyframe_insert("hide_render", frame=fr(4.0))
    # Thread tail: thin white bar right of the last stitch, 2.8 s until the scissors cut it at 5.8 s.
    bpy.ops.mesh.primitive_cylinder_add(vertices=8, radius=0.00042, depth=0.042)
    needle = bpy.context.active_object
    needle.name = "needle"
    needle.data.materials.append(steel)
    p0, _ = surf(tree, y0, 0.018, -0.94, 0.0016)
    needle.matrix_world = Matrix.Translation(p0 + Vector((0, 0.022, 0))) @ Matrix.Rotation(math.pi / 2, 4, "X")
    parent_bone(needle, rig)
    for hide, f in ((True, 1), (False, fr(2.8)), (True, fr(5.84))):
        needle.hide_render = hide
        needle.keyframe_insert("hide_render", frame=f)
    build_scissors(blue_steel, gold, tree, y0, rig)


def build_scissors(steel, gold, tree, y0, rig):
    """Measured on the reference: pops in open at 5.3 s, closes at 5.8 s, pops out at 6.1 s, hovering with a cast shadow."""
    p, nor = surf(tree, y0, -0.012, -1.10, 0.012)
    pivot = bpy.data.objects.new("scissors", None)
    bpy.context.scene.collection.objects.link(pivot)
    parts = []
    for side in (-1, 1):
        bl = [(-0.0030, 0.0, 0), (0.0030, 0.0, 0), (0.0006, 0.060, 0), (-0.0002, 0.060, 0)]
        ha = [(-0.0028, 0.0, 0), (0.0028, 0.0, 0), (0.0018 + side * 0.008, -0.040, 0), (-0.0018 + side * 0.008, -0.040, 0)]
        me = bpy.data.meshes.new("blade")
        me.from_pydata(bl + ha, [], [(0, 1, 2, 3), (4, 5, 6, 7)])
        ob = bpy.data.objects.new("blade", me)
        bpy.context.scene.collection.objects.link(ob)
        ob.parent = pivot
        me.materials.append(steel)
        ob.modifiers.new("t", "SOLIDIFY").thickness = 0.0012
        bpy.ops.mesh.primitive_torus_add(major_radius=0.0095, minor_radius=0.0016, major_segments=32, minor_segments=8,
                                         location=(side * 0.011, -0.052, 0))
        ring = bpy.context.active_object
        ring.scale = (0.85, 1.25, 1)
        ring.parent = ob
        ring.data.materials.append(steel)
        parts += [ob, ring]
        for a, t in ((0.42, 5.27), (0.42, 5.67), (0.02, 5.84)):
            ob.rotation_euler = (0, 0, side * a)
            ob.keyframe_insert("rotation_euler", frame=fr(t))
    bpy.ops.mesh.primitive_cylinder_add(vertices=16, radius=0.0014, depth=0.0026, location=(0, 0, 0.001))
    rivet = bpy.context.active_object
    rivet.parent = pivot
    rivet.data.materials.append(gold)
    parts.append(rivet)
    # Local Y (blades) to armature up the leg and toward his back; local Z to the skin normal (+X).
    tilt = math.radians(68)
    ydir = Vector((0, math.sin(tilt), math.cos(tilt)))
    zdir = Vector((1, 0, 0))
    xdir = ydir.cross(zdir)
    pivot.rotation_mode = "QUATERNION"
    pivot.rotation_quaternion = Matrix((xdir, ydir, zdir)).transposed().to_quaternion()
    pivot.scale = (0.88, 0.88, 0.88)
    parent_bone(pivot, rig)
    away = Vector((0, 0.11, -0.13))
    for t, off in ((5.27, away), (5.42, Vector()), (5.62, Vector()), (5.84, ydir * 0.004), (6.0, ydir * 0.004), (6.2, away)):
        pivot.location = p + off
        pivot.keyframe_insert("location", frame=fr(t))
    for part in parts:
        for hide, f in ((True, 1), (False, fr(5.27)), (True, fr(6.2))):
            part.hide_render = hide
            part.keyframe_insert("hide_render", frame=f)


# ---------------------------------------------------------------- shorts, sock, shoes (shells of the body mesh)
def shell(body, name, zmin, zmax, offset, mat, solid=0.0):
    """A clothing shell: copy of the body between two heights, with weights, pushed out along normals."""
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bm.from_mesh(body.data)
    bm.normal_update()
    for z, keep_above in ((zmin, True), (zmax, False)):
        if z is None:
            continue
        geom = bm.verts[:] + bm.edges[:] + bm.faces[:]
        bmesh.ops.bisect_plane(bm, geom=geom, plane_co=(0, 0, z), plane_no=(0, 0.06, 1),
                               clear_inner=keep_above, clear_outer=not keep_above)
    bm.normal_update()
    for v in bm.verts:
        v.co += v.normal * offset(v.co)
    bm.to_mesh(me)
    bm.free()
    co = np.empty(len(me.vertices) * 3, dtype=np.float32)
    me.vertices.foreach_get("co", co)
    me.attributes.new("rest", "FLOAT_VECTOR", "POINT").data.foreach_set("vector", co)
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    for g in body.vertex_groups:
        ob.vertex_groups.new(name=g.name)
    ob.parent = body.parent
    if solid:
        s = ob.modifiers.new("sol", "SOLIDIFY")
        s.thickness = solid
        s.offset = 1
    ob.modifiers.new("arm", "ARMATURE").object = body.parent
    me.materials.clear()
    me.materials.append(mat)
    for p in me.polygons:
        p.use_smooth = True
    return ob


def shoe_material():
    m = bpy.data.materials.new("shoe")
    g = G(m)
    t = g.t
    rest = g.attr("rest", "Vector")
    sep = t.nodes.new("ShaderNodeSeparateXYZ")
    t.links.new(rest, sep.inputs[0])
    z = sep.outputs["Z"]
    upper = g.mix(g.ramp(g.noise(rest, 90, 3), 0.4, 0.62), srgb(238, 234, 224), srgb(250, 248, 240))
    col = g.mix(g.ramp(z, 0.031, 0.034), srgb(232, 224, 200), upper)  # cream sole
    groove = g.ramp(g.math("ABSOLUTE", g.math("SUBTRACT", z, 0.033)), 0.0012, 0.0002)
    col = g.mix(g.math("MULTIPLY", groove, 0.65), col, srgb(120, 112, 96))
    b = t.nodes.new("ShaderNodeBsdfPrincipled")
    t.links.new(col, b.inputs["Base Color"])
    b.inputs["Roughness"].default_value = 0.44
    t.links.new(b.outputs[0], t.nodes.new("ShaderNodeOutputMaterial").inputs["Surface"])
    return m


def build_clothes(body, rig):
    shorts_m = bpy.data.materials.new("shorts")
    g = G(shorts_m)
    t = g.t
    p = g.attr("rest", "Vector")
    wrink = g.noise(g.scale(p, 26, 26, 8), 1, 4)
    b = t.nodes.new("ShaderNodeBsdfPrincipled")
    t.links.new(g.mix(g.ramp(wrink, 0.35, 0.65), srgb(170, 166, 184), srgb(216, 212, 222)), b.inputs["Base Color"])
    b.inputs["Roughness"].default_value = 0.82
    bump = t.nodes.new("ShaderNodeBump")
    t.links.new(g.math("ADD", g.math("MULTIPLY", wrink, 4.5), g.math("MULTIPLY", g.noise(p, 900, 2), 0.5)), bump.inputs["Height"])
    bump.inputs["Distance"].default_value = 0.003
    t.links.new(bump.outputs[0], b.inputs["Normal"])
    t.links.new(b.outputs[0], t.nodes.new("ShaderNodeOutputMaterial").inputs["Surface"])
    hem = 0.610
    shell(body, "shorts", hem, None,
          lambda c: 0.013 + 0.018 * max(0.0, 1 - (c.z - hem) / 0.24) + 0.004 * math.sin(c.x * 60 + c.y * 41),
          shorts_m, 0.003)
    shell(body, "sock", 0.055, 0.128, lambda c: 0.0035, simple_material("sock", (136, 160, 222), 0.9))
    shoe = shell(body, "shoe", None, 0.096, lambda c: 0.011 + 0.010 * max(0.0, 0.03 - c.z) / 0.03, shoe_material(), 0.002)
    for v in shoe.data.vertices:  # flatten the sole so the shell reads as a shoe
        if v.co.z < 0.018:
            v.co.z = 0.004
    # Laces on the near shoe: short white bars across the instep, ray-cast onto the shell.
    tree = BVHTree.FromPolygons([v.co.copy() for v in shoe.data.vertices], [q.vertices[:] for q in shoe.data.polygons])
    lace_m = simple_material("lace", (240, 236, 226), 0.6)
    placed = 0
    for i in range(6):
        y = -0.052 - i * 0.012
        pts = []
        for j in range(5):
            x = 0.205 + (j - 2) * 0.008
            hit = tree.ray_cast(Vector((x, y, 0.4)), Vector((0, 0, -1)))
            if hit[0] is None:
                break
            pts.append(hit[0] + Vector((0, 0, 0.0014)))
        if len(pts) == 5:
            parent_bone(curve_ob(f"lace{i}", pts, lace_m, 0.0016), rig, "foot.L")
            placed += 1
    print("LACES", placed)


# ---------------------------------------------------------------- walk (treadmill, armature space)
def rot_key(pb, angle, frame):
    """Rotate pose bone by angle about armature X (positive: leg swings toward +Y, his back)."""
    axis = pb.bone.matrix_local.to_3x3().inverted() @ Vector((1, 0, 0))
    pb.rotation_mode = "QUATERNION"
    pb.rotation_quaternion = Quaternion(axis.normalized(), angle)
    pb.keyframe_insert("rotation_quaternion", frame=frame)


def build_walk(rig, period=5.0):
    """T=5 s puts t=0 and t=30 s at the same phase, as in the reference. Keys every 4 frames."""
    p = rig.pose.bones
    w = 2 * math.pi / period
    for f in range(1, FRAMES + 2, 4):
        s = math.sin(w * (f - 1) / FPS)
        # Near leg: stance, small sway. Far leg: stays behind and lifts, knee bending.
        rot_key(p["upperleg01.L"], math.radians(-5 + 2 * s), f)
        rot_key(p["lowerleg01.L"], math.radians(7 + 1.5 * s), f)
        rot_key(p["foot.L"], math.radians(-2 - 3 * s), f)
        rot_key(p["upperleg01.R"], math.radians(13 + 7 * s), f)
        rot_key(p["lowerleg01.R"], math.radians(20 + 12 * s), f)
        rot_key(p["foot.R"], math.radians(14 + 8 * s), f)


def pin_wound(rig, local, keep=0.22):
    """Key the armature location so the wound keeps only keep x its sway; the camera axis stays on it.
    Reference: the leg rocks and the wound stays near frame centre (0.447 px/frame at 256 px wide)."""
    bone = rig.data.bones["lowerleg02.L"]
    rest_inv = bone.matrix_local.inverted()
    sc = bpy.context.scene
    pts = {}
    for f in range(1, FRAMES + 2, 4):
        sc.frame_set(f)
        pts[f] = rig.matrix_world @ rig.pose.bones["lowerleg02.L"].matrix @ rest_inv @ local
    mean = sum(pts.values(), Vector((0, 0, 0))) / len(pts)
    for f, p in pts.items():
        rig.location = (mean - p) * (1 - keep)
        rig.keyframe_insert("location", frame=f)
    sc.frame_set(1)
    return mean


# ---------------------------------------------------------------- camera: single dolly axis
# (t, camera distance in metres). Timing from tools/measure.py on the reference. Distances calibrated on the
# stitch spacing in reference frames: phase correlation under-reads the push-in by about a power of 2.
DIST = [(0, 0.73), (4.2, 0.30), (5.5, 0.30), (9, 0.31), (12, 0.27), (13.2, 0.24), (16, 0.146), (19, 0.125), (22, 0.105),
        (23.8, 0.105), (24.6, 0.13), (26, 0.46), (27, 0.76), (28, 0.98), (29, 1.10), (31.1, 1.20)]


def build_camera(target, focus):
    sc = bpy.context.scene
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    sc.collection.objects.link(cam)
    sc.camera = cam
    cam.data.lens = 50
    cam.data.clip_start = 0.005
    cam.data.sensor_fit = "VERTICAL"
    cam.data.sensor_height = 36
    axis = Vector((0.10, -1.0, -0.30)).normalized()  # wound toward camera, from below the knee
    cam.rotation_mode = "QUATERNION"
    cam.rotation_quaternion = (-axis).to_track_quat("-Z", "Y")
    for t, d in DIST:
        cam.location = target + axis * d
        cam.keyframe_insert("location", frame=fr(t))
    a = cam.animation_data
    for fc in a.action.layers[0].strips[0].channelbag(a.action_slot).fcurves:
        for k in fc.keyframe_points:
            k.interpolation = "BEZIER"
            k.handle_left_type = k.handle_right_type = "AUTO_CLAMPED"
    cam.data.dof.use_dof = True
    cam.data.dof.focus_object = focus
    for t, stop in ((0, 3.2), (12, 3.6), (16, 8.0), (24.5, 8.0), (27, 3.2)):
        cam.data.dof.aperture_fstop = stop
        cam.data.dof.keyframe_insert("aperture_fstop", frame=fr(t))


# ---------------------------------------------------------------- render + light
def setup_render(samples=96):
    sc = bpy.context.scene
    sc.frame_start, sc.frame_end = 1, FRAMES
    sc.render.fps, sc.render.fps_base = 30, 1.001
    sc.render.engine = "CYCLES"
    sc.render.resolution_x, sc.render.resolution_y = 1080, 1920
    sc.render.film_transparent = True
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGBA"
    sc.render.use_persistent_data = True
    sc.render.use_motion_blur = True
    sc.render.motion_blur_shutter = 0.3
    sc.view_settings.view_transform = "Khronos PBR Neutral"
    c = sc.cycles
    c.device = "GPU"
    c.samples = samples
    c.use_denoising = True
    c.denoiser = "OPTIX"
    c.max_bounces = 4
    c.diffuse_bounces = 2
    c.glossy_bounces = 2
    c.transmission_bounces = 0
    c.volume_bounces = 0
    c.use_auto_tile = True
    c.tile_size = 1024


def build_light():
    sc = bpy.context.scene
    sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN"))
    sc.collection.objects.link(sun)
    sun.data.energy = 4.6
    sun.data.angle = math.radians(2.0)
    sun.data.color = (1.0, 0.95, 0.88)
    # Sun from upper left and in front: the leg's right edge falls into shade, as in the reference.
    sun.rotation_mode = "QUATERNION"
    sun.rotation_quaternion = Vector((-1.0, -0.22, 0.62)).to_track_quat("Z", "Y")
    w = bpy.data.worlds.new("w")
    sc.world = w
    w.use_nodes = True
    bg = w.node_tree.nodes["Background"]
    bg.inputs[0].default_value = (0.66, 0.80, 1.0, 1)
    bg.inputs[1].default_value = 0.26


def main():
    out = sys.argv[sys.argv.index("--") + 1]
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.preferences.addon_enable(module="bl_ext.blender_org.mpfb")
    body, rig = build_human()
    add_subsurf_applied(body, 1)
    body.data.materials.append(skin_material())
    build_clothes(body, rig)
    y0, co, _ = build_patch(body, get_arg("--cuts", 23))
    for name, keys in STAGE_KEYS.items():
        key_value(body.data.shape_keys.key_blocks[name], keys)
    near = (np.abs(co[:, 2] - ZC) < 0.002) & (np.abs(co[:, 1] - y0) < 0.002) & (co[:, 0] > 0.1)
    wound = Vector((float(co[near, 0].mean()), y0, ZC))
    build_stitches(body, rig, y0)
    add_hair(body, rig, y0, get_arg("--hair", 12000))
    rig.rotation_euler.z = -math.pi / 2
    build_walk(rig)
    bpy.context.view_layer.update()
    target = pin_wound(rig, wound)
    focus = bpy.data.objects.new("focus", None)
    bpy.context.scene.collection.objects.link(focus)
    focus.location = wound
    parent_bone(focus, rig)
    build_camera(target, focus)
    build_light()
    setup_render()
    print("VERTS", len(body.data.vertices), "target", tuple(round(x, 3) for x in target), "wound", tuple(wound))
    bpy.ops.wm.save_as_mainfile(filepath=out)
    print("OK", out)


main()
