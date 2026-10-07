"""Build a house in Blender from <house>/plan.json (headless).

  $BLENDER -b --factory-startup --python blender/build_model.py -- \
      --house examples/simple-house --version v1 [--variant B] [--render] [--fast] [--glb out.glb]

Writes <house>/out/<version>/model_<variant>.blend, geometry_reference_<variant>.json next to it
and, with --render, the stills from <house>/shots.json into stills_<variant>/. Never edits
plan.json; every number comes from it. 1 Blender unit = 1 m, origin at the SW outer corner,
x east, y north, z = 0 at +-0.00.
"""
import json
import math
import sys
from pathlib import Path

import bmesh
import bpy

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from plan import load_plan  # noqa: E402
from roof import Roof, ccw, rect  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def arg(name, default=None):
    return argv[argv.index(name) + 1] if name in argv else default


HOUSE = Path(arg("--house", "house"))
if not HOUSE.is_absolute():
    HOUSE = (Path.cwd() / HOUSE).resolve()
VERSION = arg("--version")
if not VERSION:
    sys.exit("--version is required (v1, v2, ...); every build gets its own out/<version>/")
VARIANT = arg("--variant", "A")
GLB = arg("--glb")
RENDER = "--render" in argv
FAST = "--fast" in argv
OUT = HOUSE / "out" / VERSION
OUT.mkdir(parents=True, exist_ok=True)

P = load_plan(HOUSE, VARIANT)
LV = {k: v["z"] for k, v in P["levels"].items()}
for need in ("ground_outside", "floor", "ceiling", "wall_plate"):
    if need not in LV:
        sys.exit(f"plan.json levels: {need} is missing")
ROOF = Roof(P["roof"])
M = 0.01                    # cm -> m
EXT_T = P["wall_types"]["ext"]["thickness"]


# ------------------------------------------------------------------ scene helpers
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
scene.unit_settings.system = "METRIC"


def collection(name):
    c = bpy.data.collections.new(name)
    scene.collection.children.link(c)
    return c


def material(name, rgb, rough=0.8, alpha=1.0, transmission=0.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    bsdf = next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    bsdf.inputs["Base Color"].default_value = (*rgb, 1)
    bsdf.inputs["Roughness"].default_value = rough
    if transmission:
        bsdf.inputs["Transmission Weight"].default_value = transmission
        bsdf.inputs["IOR"].default_value = 1.45
    if alpha < 1:
        bsdf.inputs["Alpha"].default_value = alpha
    m.diffuse_color = (*rgb, alpha)
    return m


MAT = {
    "wall": material("clay_wall", (0.80, 0.80, 0.78)),
    "part": material("clay_partition", (0.86, 0.86, 0.84)),
    "roof": material("roof_grey", (0.22, 0.23, 0.24), 0.7),
    "slab": material("clay_slab", (0.74, 0.74, 0.72)),
    "floor": material("floor", (0.55, 0.55, 0.53)),
    "glass": material("glass", (0.75, 0.85, 0.90), 0.05, alpha=0.25, transmission=1.0),
    "door": material("door_grey", (0.35, 0.36, 0.37), 0.6),
    "ground": material("ground", (0.42, 0.45, 0.38), 0.95),
    "stack": material("stack", (0.30, 0.30, 0.30)),
    "rail": material("rail_steel", (0.035, 0.036, 0.038), 0.45),
}


def mesh_obj(name, bm, coll, mat):
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    ob.data.materials.append(mat)
    coll.objects.link(ob)
    return ob


def prism(bm, poly, z0, z1):
    """Vertical prism over a polygon [(x, y), ...] in cm; z0/z1 numbers or callables(x, y)."""
    poly = ccw(poly)
    f0 = z0 if callable(z0) else (lambda x, y, v=z0: v)
    f1 = z1 if callable(z1) else (lambda x, y, v=z1: v)
    bot = [bm.verts.new((x * M, y * M, f0(x, y) * M)) for x, y in poly]
    top = [bm.verts.new((x * M, y * M, f1(x, y) * M)) for x, y in poly]
    bm.faces.new(list(reversed(bot)))
    bm.faces.new(top)
    n = len(poly)
    for i in range(n):
        j = (i + 1) % n
        bm.faces.new((bot[i], bot[j], top[j], top[i]))


def strips(x0, y0, x1, y1):
    """Split a rect along its long axis at the roof's crease lines so a sloped top stays exact."""
    along_x = (x1 - x0) >= (y1 - y0)
    a0, a1 = (x0, x1) if along_x else (y0, y1)
    cuts = {a0, a1}
    prev = None
    for k in range(math.floor(a0), math.ceil(a1) + 1):
        pts = [(k, y0), (k, y1)] if along_x else [(x0, k), (x1, k)]
        zs = [ROOF.under(*p) for p in pts]
        z = min(v for v in zs if v is not None) if any(v is not None for v in zs) else None
        if prev is not None and z is not None and prev[1] is not None:
            slope = z - prev[1]
            if prev[2] is not None and abs(slope - prev[2]) > 1e-6:
                cuts.add(prev[0])
            prev = (k, z, slope)
        else:
            prev = (k, z, None)
    cuts = sorted(c for c in cuts if a0 <= c <= a1)
    for c0, c1 in zip(cuts, cuts[1:]):
        if c1 - c0 < 0.5:
            continue
        yield (c0, y0, c1, y1) if along_x else (x0, c0, x1, c1)


def roof_or(z_default):
    return lambda x, y: ROOF.under(x, y) or z_default


def wall_top_fn(kind):
    """Exterior walls end exactly on the roof underside (gables, and no overlap at the eaves);
    interior walls stop at the ceiling."""
    return roof_or(LV["wall_plate"]) if kind == "ext" else (lambda x, y: LV["ceiling"])


def rect_sub(rects, cut):
    """Rectangle difference that keeps faces non-overlapping."""
    out = []
    cx0, cy0, cx1, cy1 = cut
    for x0, y0, x1, y1 in rects:
        if cx1 <= x0 or cx0 >= x1 or cy1 <= y0 or cy0 >= y1:
            out.append((x0, y0, x1, y1)); continue
        if y0 < cy0: out.append((x0, y0, x1, cy0))
        if cy1 < y1: out.append((x0, cy1, x1, y1))
        my0, my1 = max(y0, cy0), min(y1, cy1)
        if x0 < cx0: out.append((x0, my0, cx0, my1))
        if cx1 < x1: out.append((cx1, my0, x1, my1))
    return out


# ------------------------------------------------------------------ build
C_WALL, C_OPEN, C_SLAB, C_ROOF, C_FLOOR, C_SITE = (collection(n) for n in
    ("walls", "openings", "slab", "roof", "floor", "site"))
ref = {"version": VERSION, "variant": VARIANT, "units": "m", "walls": [], "openings": []}

for w in P["walls"]:
    bm = bmesh.new()
    top = wall_top_fn(w["type"])
    z0 = LV["ground_outside"] if w["type"] == "ext" else LV["floor"]
    # walls run through their openings in plan.json; the opening fillers below take that part
    pieces = [(w["x0"], w["y0"], w["x1"], w["y1"])]
    for o in P["openings"]:
        pieces = rect_sub(pieces, (o["x0"], o["y0"], o["x1"], o["y1"]))
    for pc in pieces:
        for s in strips(*pc):
            prism(bm, rect(*s), z0, top)
    ob = mesh_obj(w["id"], bm, C_WALL, MAT["wall" if w["type"] == "ext" else "part"])
    ob["type"] = w["type"]
    ref["walls"].append({"id": w["id"], "type": w["type"], "bbox": [list(v) for v in
                         (ob.bound_box[0], ob.bound_box[6])]})

for s in P.get("shafts", []):
    bm = bmesh.new()
    prism(bm, rect(s["x0"], s["y0"], s["x1"], s["y1"]), LV["floor"], P["slab"]["z1"])
    mesh_obj(s["id"], bm, C_WALL, MAT["stack"])
for s in P["roof"].get("stacks", []):
    bm = bmesh.new()
    prism(bm, rect(s["x0"], s["y0"], s["x1"], s["y1"]), P["slab"]["z1"], s["top"])
    mesh_obj(s["id"], bm, C_ROOF, MAT["stack"])

# openings: lintel above the head, parapet below the sill, glass or door leaf in the gap
for o in P["openings"]:
    x0, y0, x1, y1 = o["x0"], o["y0"], o["x1"], o["y1"]
    kind = "ext" if o["exterior"] else "part"
    top = wall_top_fn(kind)
    sill = o.get("sill") or 0
    if o.get("shape") == "to_roof":
        head = lambda x, y, d=o["below_roof"]: ROOF.under(x, y) - d
    elif o.get("shape") == "line":         # sloped head given as [[along, z], [along, z]]
        (ua, za), (ub, zb) = o["top_line"]
        along_x = (x1 - x0) >= (y1 - y0)
        head = lambda x, y, ua=ua, za=za, ub=ub, zb=zb, ax=along_x: za + ((x if ax else y) - ua) * (zb - za) / (ub - ua)
    else:
        head = lambda x, y, h=o["h"], s=sill: s + h
    bm = bmesh.new()
    for s in strips(x0, y0, x1, y1):
        prism(bm, rect(*s), head, lambda x, y: max(top(x, y), head(x, y) + 0.1))
    if sill > 0:
        prism(bm, rect(x0, y0, x1, y1), LV["ground_outside"] if o["exterior"] else LV["floor"], sill)
    mesh_obj(o["id"] + "_fill", bm, C_OPEN, MAT["wall" if o["exterior"] else "part"])
    if o["exterior"]:
        along_x = (x1 - x0) >= (y1 - y0)
        bm = bmesh.new()
        for s in strips(x0, y0, x1, y1):
            if along_x:
                ym = (y0 + y1) / 2
                prism(bm, rect(max(s[0], x0 + 0.3), ym - 1, min(s[2], x1 - 0.3), ym + 1), sill, head)
            else:
                xm = (x0 + x1) / 2
                prism(bm, rect(xm - 1, max(s[1], y0 + 0.3), xm + 1, min(s[3], y1 - 0.3)), sill, head)
        mesh_obj(o["id"] + "_pane", bm, C_OPEN, MAT["door" if o["kind"] == "door" else "glass"])
    ref["openings"].append({"id": o["id"], "w_cm": max(x1 - x0, y1 - y0), "sill_cm": sill})

# ceiling slab: room side of the exterior walls plus 1 cm, so slab edges sit inside the walls
# (coplanar faces render black in Cycles)
inner = [(x0 - 1, y0 - 1, x1 + 1, y1 + 1) for x0, y0, x1, y1 in P["inner_rects"]]


def past_walls(v):
    """A void side along an exterior wall reaches past the slab edge, so no 1 cm strip is left
    and no cut face lies in the wall's plane."""
    x0, y0, x1, y1 = v["x0"], v["y0"], v["x1"], v["y1"]
    for r in inner:
        if r[0] - 2 <= x0 and r[1] - 2 <= y0 and x1 <= r[2] + 2 and y1 <= r[3] + 2:
            return (r[0] - 1 if x0 - r[0] <= 3 else x0, r[1] - 1 if y0 - r[1] <= 3 else y0,
                    r[2] + 1 if r[2] - x1 <= 3 else x1, r[3] + 1 if r[3] - y1 <= 3 else y1)
    return (x0, y0, x1, y1)


slab_rects = list(inner)
for v in P.get("voids", []) + P.get("slab_holes", []):
    slab_rects = rect_sub(slab_rects, past_walls(v))
bm = bmesh.new()
for r in slab_rects:
    prism(bm, rect(*r), P["slab"]["z0"], P["slab"]["z1"])
mesh_obj("ceiling_slab", bm, C_SLAB, MAT["slab"])

bm = bmesh.new()
for r in inner:
    prism(bm, rect(*r), LV["floor"] - 10, LV["floor"])
mesh_obj("floor_slab", bm, C_FLOOR, MAT["floor"])

# attic walls (e.g. along a void edge): from the slab top up to the roof underside
z_attic = P["slab"]["z1"]
for aw in P.get("attic_walls", []):
    bm = bmesh.new()
    for s in strips(aw["x0"], aw["y0"], aw["x1"], aw["y1"]):
        prism(bm, rect(*s), z_attic, roof_or(z_attic))
    mesh_obj(aw["id"], bm, C_SLAB, MAT["part"])


def build_rail(rl, z0):
    """Steel railing: handrail, bottom rail, posts about every metre, 2 cm balusters at 12 cm."""
    (ax, ay), (bx, by), H = rl["a"], rl["b"], rl["h"]
    L = math.hypot(bx - ax, by - ay)
    ux, uy = (bx - ax) / L, (by - ay) / L
    bm = bmesh.new()

    def bar(u0, u1, wide, z1, z2):
        nx, ny = -uy * wide / 2, ux * wide / 2
        p0, p1 = (ax + ux * u0, ay + uy * u0), (ax + ux * u1, ay + uy * u1)
        prism(bm, [(p0[0] - nx, p0[1] - ny), (p1[0] - nx, p1[1] - ny), (p1[0] + nx, p1[1] + ny),
                   (p0[0] + nx, p0[1] + ny)], z0 + z1, z0 + z2)

    bar(0, L, 6, H - 5, H)
    bar(0, L, 4, 4, 8)
    posts = max(1, round(L / 100))
    for i in range(posts + 1):
        u = min(L - 3, max(3, L * i / posts))      # inset: no end face in the rails' end planes
        bar(u - 2.5, u + 2.5, 5, 0.2, H - 5)
    u = 12
    while u < L - 6:
        bar(u - 1, u + 1, 2, 8, H - 5)
        u += 12
    mesh_obj(rl["id"], bm, C_SLAB, MAT["rail"])


for rl in P.get("rails", []):
    build_rail(rl, rl.get("z", z_attic))

# roof: one prism per convex facet piece, top on the slope plane, vertical thickness below it
bm = bmesh.new()
for (_, a, b, c, _, _), pieces in ROOF.facets():
    plane = lambda x, y, a=a, b=b, c=c: a * x + b * y + c
    for poly in pieces:
        prism(bm, poly, lambda x, y, f=plane: f(x, y) - ROOF.v_thick, plane)
roof = mesh_obj("roof", bm, C_ROOF, MAT["roof"])

# ground
xs = [w[k] for w in P["roof"]["wings"] for k in ("x0", "x1")]
ys = [w[k] for w in P["roof"]["wings"] for k in ("y0", "y1")]
bm = bmesh.new()
prism(bm, rect(min(xs) - 3000, min(ys) - 3000, max(xs) + 3000, max(ys) + 3000),
      LV["ground_outside"] - 5, LV["ground_outside"])
mesh_obj("ground", bm, C_SITE, MAT["ground"])


# ------------------------------------------------------------------ measurements
def world_verts(ob):
    return [ob.matrix_world @ v.co for v in ob.data.vertices]


rv = world_verts(roof)
ref["ridge_z_m"] = round(max(v.z for v in rv), 4)
pitches = []
for p in roof.data.polygons:
    n = roof.matrix_world.to_3x3() @ p.normal
    if n.z > 0.1:
        pitches.append(round(math.degrees(math.acos(min(1, n.z))), 3))
ref["roof_pitches_deg"] = sorted(set(pitches))
allv = [v for ob in C_WALL.objects if ob.get("type") for v in world_verts(ob)]
ref["envelope_m"] = {"x": round(max(v.x for v in allv) - min(v.x for v in allv), 4),
                     "y": round(max(v.y for v in allv) - min(v.y for v in allv), 4)}
stacks = [v for s in P["roof"].get("stacks", []) for v in world_verts(bpy.data.objects[s["id"]])]
ref["stack_top_m"] = round(max(v.z for v in stacks), 4) if stacks else None
ref["max_height_above_ground_m"] = round(ref["ridge_z_m"] - LV["ground_outside"] * M, 4)
(OUT / f"geometry_reference_{VARIANT}.json").write_text(json.dumps(ref, indent=1))

blend = OUT / f"model_{VARIANT}.blend"
bpy.ops.wm.save_as_mainfile(filepath=str(blend))
print("saved", blend)
print(json.dumps({k: ref[k] for k in ("ridge_z_m", "roof_pitches_deg", "envelope_m",
                                       "stack_top_m", "max_height_above_ground_m")}, indent=1))

if GLB:
    # house only (no ground); one node per collection so a web page can toggle roof / slab
    for ob in scene.objects:
        ob.select_set(ob.users_collection[0].name != "site")
    bpy.ops.export_scene.gltf(filepath=str(Path(GLB).resolve()), export_format="GLB", use_selection=True,
                              export_hierarchy_full_collections=True, export_apply=True,
                              export_extras=True, export_cameras=False, export_lights=False)
    print("exported", GLB)

if RENDER:
    sys.path.insert(0, str(ROOT / "blender"))
    import shots  # noqa: E402
    shots.render_all(scene, HOUSE / "shots.json", OUT / f"stills_{VARIANT}", fast=FAST)
    bpy.ops.wm.save_as_mainfile(filepath=str(blend))
