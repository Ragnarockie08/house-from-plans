"""Fixed review cameras from <house>/shots.json and a clay render of each."""
import json
import math
from pathlib import Path

import bpy
from mathutils import Vector


def look_at(ob, target):
    d = Vector(target) - ob.location
    ob.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()


def use_gpu(scene):
    try:
        prefs = bpy.context.preferences.addons["cycles"].preferences
    except KeyError:
        return
    for kind in ("METAL", "OPTIX", "CUDA", "HIP", "ONEAPI"):
        try:
            prefs.compute_device_type = kind
        except TypeError:
            continue
        prefs.get_devices()
        devs = [d for d in prefs.devices if d.type != "CPU"]
        if devs:
            for d in prefs.devices:
                d.use = True
            scene.cycles.device = "GPU"
            print("GPU:", kind, [d.name for d in devs])
            return
    print("no GPU found, rendering on the CPU (slower)")


def setup_render(scene, sun_cfg, fast):
    try:
        scene.render.engine = "CYCLES"
    except TypeError as e:
        print("engine fallback:", e)
    scene.cycles.samples = 24 if fast else 96
    scene.cycles.use_denoising = True
    use_gpu(scene)
    fmt = scene.render.image_settings
    if "PNG" in [i.identifier for i in fmt.bl_rna.properties["file_format"].enum_items]:
        fmt.file_format = "PNG"
    vts = [i.identifier for i in scene.view_settings.bl_rna.properties["view_transform"].enum_items]
    if "AgX" in vts:
        scene.view_settings.view_transform = "AgX"

    world = scene.world or bpy.data.worlds.new("sky")
    scene.world = world
    world.use_nodes = True
    bg = next(n for n in world.node_tree.nodes if n.type == "BACKGROUND")
    bg.inputs["Color"].default_value = (0.78, 0.84, 0.92, 1)
    bg.inputs["Strength"].default_value = 0.9

    sun = bpy.data.lights.new("sun", "SUN")
    sun.energy = 3.5
    sun.angle = math.radians(1.5)
    ob = bpy.data.objects.new("sun", sun)
    scene.collection.objects.link(ob)
    aim_sun(ob, sun_cfg["elevation_deg"], sun_cfg["azimuth_deg"])
    return ob


def aim_sun(ob, elev_deg, azim_deg):
    """Sun from azimuth azim_deg (from north, clockwise) at elevation elev_deg (y = north)."""
    ob.rotation_euler = (math.radians(90 - elev_deg), 0, math.radians(180 - azim_deg))


def section_cut(scene, x_cut, keep="west"):
    """Boolean away one side of x = x_cut so the cut faces are capped (camera clipping leaves
    them open and black). The cutter's dark material goes onto the cut faces."""
    import bmesh
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    me = bpy.data.meshes.new("section_cutter")
    bm.to_mesh(me); bm.free()
    cutter = bpy.data.objects.new("section_cutter", me)
    scene.collection.objects.link(cutter)
    cutter.scale = (100, 200, 60)
    cutter.location = (x_cut + 50 if keep == "west" else x_cut - 50, 0, 10)
    cutter.hide_render = True
    poche = bpy.data.materials.new("section_poche")
    poche.use_nodes = True
    bsdf = next(n for n in poche.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    bsdf.inputs["Base Color"].default_value = (0.08, 0.08, 0.09, 1)
    poche.diffuse_color = (0.08, 0.08, 0.09, 1)
    me.materials.append(poche)
    mods = []
    for ob in scene.objects:
        if ob.type != "MESH" or ob is cutter or ob.name == "ground":
            continue
        m = ob.modifiers.new("section", "BOOLEAN")
        m.operation = "DIFFERENCE"
        m.object = cutter
        try:
            m.material_mode = "TRANSFER"
        except (TypeError, AttributeError) as e:
            print("boolean material transfer unavailable:", e)
        mods.append((ob, m))
    return cutter, mods


def render_all(scene, shots_path: Path, out_dir: Path, fast=False, only=None):
    data = json.loads(Path(shots_path).read_text())
    out_dir.mkdir(parents=True, exist_ok=True)
    sun_cfg = data.get("sun", {"elevation_deg": 38, "azimuth_deg": 225})
    sun = setup_render(scene, sun_cfg, fast)
    for sh in data["shots"]:
        if only and sh["id"] not in only:
            continue
        name, kind = sh["id"], sh["kind"]
        cam_data = bpy.data.cameras.new(name)
        cam = bpy.data.objects.new(name, cam_data)
        scene.collection.objects.link(cam)
        cam.location = sh["pos"]
        look_at(cam, sh["target"])
        if kind in ("ORTHO", "SECTION"):
            cam_data.type = "ORTHO"
            cam_data.ortho_scale = sh["ortho_scale"]
        else:
            cam_data.lens = sh["lens"]
        cam_data.clip_start = sh.get("clip_start") or 0.05
        cam_data.clip_end = 300
        hidden = [o for c in sh.get("hide", []) for o in bpy.data.collections[c].all_objects]
        for o in hidden:
            o.hide_render = True
        cut = None
        if kind == "SECTION":
            cut = section_cut(scene, sh["section_x"], sh.get("keep", "west"))
            s = sh.get("sun", {"elevation_deg": 30, "azimuth_deg": 100})
            aim_sun(sun, s["elevation_deg"], s["azimuth_deg"])     # light the cut face
        res = sh.get("res", [1800, 1200])
        scale = 0.67 if fast else 1.0
        scene.render.resolution_x, scene.render.resolution_y = int(res[0] * scale), int(res[1] * scale)
        scene.view_settings.exposure = sh.get("exposure", 0.0)
        scene.camera = cam
        scene.render.filepath = str(out_dir / f"{name}.png")
        bpy.ops.render.render(write_still=True)
        print("rendered", scene.render.filepath)
        for o in hidden:
            o.hide_render = False
        if cut:
            cutter, mods = cut
            for ob, m in mods:
                ob.modifiers.remove(m)
            bpy.data.objects.remove(cutter)
            aim_sun(sun, sun_cfg["elevation_deg"], sun_cfg["azimuth_deg"])
