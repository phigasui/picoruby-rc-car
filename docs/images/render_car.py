"""完成イメージ画像を Blender でレンダリングするスクリプト.

寸法は cad/RcCarChassis/RcCarChassis.py の P を読み込んで使う (見た目用の簡略モデル)。

    /Applications/Blender.app/Contents/MacOS/Blender -b --factory-startup \
        --python docs/images/render_car.py

docs/images/car_complete.png (完成) と car_inside.png (ボディなし) を書き出す。
"""

import math
import os

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
CAD = os.path.join(HERE, "..", "..", "cad", "RcCarChassis", "RcCarChassis.py")

# P だけを取り出す (adsk は Blender にないので import しない)
src = open(CAD, encoding="utf-8").read()
start = src.index("P = {")
end = src.index("\n}\n", start) + 3
ns = {}
exec(src[start:end], ns)
P = ns["P"]

S = 0.001  # mm -> m

# ------------------------------------------------------------ derived
hl, hw = P["plate_l"] / 2, P["plate_w"] / 2
t = P["plate_t"]
wall_in = hw - P["tt_w"] - P["mount_wall_t"]
channel_w = 2 * (wall_in - P["body_clear"])
cover = P.get("body_cover_motors", False)
bw = 2 * (hw + P["skirt_gap"] + P["body_wall"]) if cover else channel_w
bl = P["plate_l"] - 2 * P["body_end_gap"]
post_x = bl / 2 - P["body_wall"] - P.get("body_top_r", 0) - P["post_d"] / 2 - 1
if cover:
    post_y = bw / 2 - P["body_wall"] - P["body_top_r"] - P["post_d"] / 2 - 1
else:
    post_y = channel_w / 2 - P["body_wall"] - P["post_d"] / 2 - 0.5
G = P["wheel_d"] / 2 - t - P["tt_shaft_z"]  # 地面から底板の下面まで
top = G + t  # 底板の上面
axle_z = P["wheel_d"] / 2
sx = P["shaft_x"]

# ------------------------------------------------------------ scene
for o in list(bpy.data.objects):
    bpy.data.objects.remove(o, do_unlink=True)
scene = bpy.context.scene


def mat(name, color, rough=0.5, metal=0.0, emit=0.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*color, 1)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    if emit:
        b.inputs["Emission Color"].default_value = (*color, 1)
        b.inputs["Emission Strength"].default_value = emit
    return m


M = {
    "chassis": mat("chassis", (0.55, 0.62, 0.70), 0.45),
    "body": mat("body", (0.98, 0.42, 0.12), 0.35),
    "bumper": mat("bumper", (0.15, 0.45, 0.95), 0.4),
    "motor": mat("motor", (0.98, 0.78, 0.10), 0.5),
    "tire": mat("tire", (0.03, 0.03, 0.03), 0.8),
    "hub": mat("hub", (0.98, 0.80, 0.12), 0.4),
    "metal": mat("metal", (0.8, 0.8, 0.82), 0.25, 1.0),
    "light": mat("light", (1.0, 0.95, 0.7), 0.2, emit=6.0),
    "tail": mat("tail", (1.0, 0.1, 0.05), 0.2, emit=3.0),
    "dark": mat("dark", (0.05, 0.05, 0.06), 0.6),
    "text": mat("text", (0.12, 0.10, 0.10), 0.6),
    "pcb_green": mat("pcb_green", (0.05, 0.40, 0.18), 0.5),
    "pcb_blue": mat("pcb_blue", (0.25, 0.15, 0.55), 0.5),
    "breadboard": mat("breadboard", (0.97, 0.97, 0.97), 0.6),
    "battery": mat("battery", (0.08, 0.08, 0.08), 0.5),
    "aa": mat("aa", (0.1, 0.35, 0.9), 0.3, 0.3),
    "floor": mat("floor", (0.80, 0.80, 0.82), 0.9),
}


def link(obj, material, bevel=0.0):
    scene.collection.objects.link(obj)
    obj.data.materials.append(material)
    if bevel:
        m = obj.modifiers.new("bevel", "BEVEL")
        m.width = bevel * S
        m.segments = 3
    return obj


def prism(name, pts, z0, z1, material, bevel=0.0):
    n = len(pts)
    verts = [(x * S, y * S, z0 * S) for x, y in pts] + [(x * S, y * S, z1 * S) for x, y in pts]
    faces = [list(range(n))[::-1], list(range(n, 2 * n))]
    faces += [[i, (i + 1) % n, n + (i + 1) % n, n + i] for i in range(n)]
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.update()
    return link(bpy.data.objects.new(name, me), material, bevel)


def box(name, x0, x1, y0, y1, z0, z1, material, bevel=0.0):
    return prism(name, [(x0, y0), (x1, y0), (x1, y1), (x0, y1)], z0, z1, material, bevel)


def cyl(name, x, y, z, r, depth, material, axis="Z", verts=48):
    rot = {"Z": (0, 0, 0), "Y": (math.pi / 2, 0, 0), "X": (0, math.pi / 2, 0)}[axis]
    bpy.ops.mesh.primitive_cylinder_add(vertices=verts, radius=r * S, depth=depth * S,
                                        location=(x * S, y * S, z * S), rotation=rot)
    o = bpy.context.active_object
    o.name = name
    o.data.materials.append(material)
    bpy.ops.object.shade_smooth()
    return o


def wire(name, pts, color):
    cu = bpy.data.curves.new(name, "CURVE")
    cu.dimensions = "3D"
    cu.bevel_depth = 0.8 * S
    sp = cu.splines.new("BEZIER")
    sp.bezier_points.add(len(pts) - 1)
    for bp, (x, y, z) in zip(sp.bezier_points, pts):
        bp.co = (x * S, y * S, z * S)
        bp.handle_left_type = bp.handle_right_type = "AUTO"
    return link(bpy.data.objects.new(name, cu), mat(name, color, 0.4))


# ------------------------------------------------------------ chassis
def rounded_rect(x0, x1, y0, y1, r, n=10):
    pts = []
    for cx_, cy_, a0 in ((x1 - r, y0 + r, -90), (x1 - r, y1 - r, 0), (x0 + r, y1 - r, 90), (x0 + r, y0 + r, 180)):
        for i in range(n + 1):
            a = math.radians(a0 + 90 * i / n)
            pts.append((cx_ + r * math.cos(a), cy_ + r * math.sin(a)))
    return pts


prism("plate", rounded_rect(-hl, hl, -hw, hw, P["plate_corner_r"]), G, top, M["chassis"],
      bevel=P["plate_edge_r"])

inside = []  # ボディを外したときだけ見せるもの

for s in (1, -1):
    # モーター壁
    box(f"wall{s}", sx - P["tt_hole_x"] - 8, sx + 5,
        s * wall_in, s * (wall_in + P["mount_wall_t"]), top, top + P["mount_wall_h"], M["chassis"], 0.5)
    # TT モーター (ギアボックス + モーター缶)
    y_in, y_out = s * (hw - P["tt_w"]), s * hw
    gb_rear = 37.0  # シャフトからギアボックス後端まで
    box(f"gearbox{s}", sx - gb_rear, sx + P["tt_front"], min(y_in, y_out), max(y_in, y_out),
        top, top + P["tt_h"], M["motor"], 1.0)
    can_l = P["tt_rear"] - gb_rear
    cyl(f"can{s}", sx - gb_rear - can_l / 2, s * (hw - P["tt_w"] / 2), top + P["tt_shaft_z"],
        7.5, can_l, M["metal"], axis="X")
    for hz in (P["tt_hole_zc"] - P["tt_hole_spacing"] / 2, P["tt_hole_zc"] + P["tt_hole_spacing"] / 2):
        cyl(f"bolt{s}{hz}", sx - P["tt_hole_x"], s * (hw + 1), top + hz, 2.8, 2, M["metal"], axis="Y")
    # タイヤ
    wy = s * (hw + 4 + 13)
    cyl(f"tire{s}", sx, wy, axle_z, P["wheel_d"] / 2, 25, M["tire"], axis="Y", verts=96)
    cyl(f"hub{s}", sx, s * (hw + 4 + 13 + 0.6), axle_z, 22, 25, M["hub"], axis="Y", verts=12)
    cyl(f"shaft{s}", sx, s * (hw + 2), axle_z, 2.7, 6, M["dark"], axis="Y")
    # ボディの柱
    for px in (post_x, -post_x):
        inside.append(cyl(f"post{s}{px}", px, s * post_y, top + 21.5, 4, 43, M["chassis"]))

# キャスター
cx = P["caster_x"]
cyl("caster_body", cx, 0, (5 + G) / 2 + 2, 11, G - 5, M["metal"])
bpy.ops.mesh.primitive_uv_sphere_add(radius=5 * S, location=(cx * S, 0, 5 * S))
ball = bpy.context.active_object
ball.data.materials.append(M["metal"])
bpy.ops.object.shade_smooth()

# バンパー
bw_ = P["plate_w"] - 10
box("bumper_tab", hl - P["bumper_tab"], hl, -bw_ / 2, bw_ / 2,
    top, top + 5, M["bumper"], 1.0)
box("bumper_front", hl, hl + P["bumper_depth"], -bw_ / 2, bw_ / 2,
    G - 4, G - 4 + P["bumper_h"], M["bumper"], 3.0)
for y in (P["bumper_hole_y"], -P["bumper_hole_y"]):
    cyl(f"bumper_screw{y}", hl - P["bumper_tab"] / 2, y, top + 5.6, 2.8, 1.2, M["metal"])

# ------------------------------------------------------------ 中身
# 電池ボックス
bx, bl_, bw2 = P["batt_x"], P["batt_l"], P["batt_w"]
inside.append(box("battery", bx - bl_ / 2, bx + bl_ / 2, -bw2 / 2, bw2 / 2, top, top + 15, M["battery"], 1.0))
for i in (-1, 0, 1):
    inside.append(cyl(f"aa{i}", bx + i * 14.5, 0, top + 15, 7, 50, M["aa"], axis="Y"))
inside.append(box("switch", bx - bl_ / 2 - 2, bx - bl_ / 2, -5, 5, top + 4, top + 12, M["dark"]))

# ブレッドボード
bbx, bby, bbl, bbw = P["bb_x"], P["bb_y"], P["bb_l"], P["bb_w"]
bb_top = top + 9
inside.append(box("breadboard", bbx - bbl / 2, bbx + bbl / 2, bby - bbw / 2, bby + bbw / 2,
                  top, bb_top, M["breadboard"], 0.8))
inside.append(box("bb_trench", bbx - bbl / 2 + 3, bbx + bbl / 2 - 3, bby - 1.2, bby + 1.2,
                  bb_top - 1, bb_top + 0.05, M["dark"]))
# Pico 2 WH (溝をまたいで、USB を前に)
pico_x = bbx + bbl / 2 - 3 - 25.5
inside.append(box("pico", pico_x - 25.5, pico_x + 25.5, bby - 10.5, bby + 10.5,
                  bb_top + 8, bb_top + 9, M["pcb_green"]))
inside.append(box("pico_usb", pico_x + 25.5 - 5, pico_x + 25.5 + 1, bby - 4, bby + 4,
                  bb_top + 9, bb_top + 12, M["metal"]))
inside.append(box("pico_rf", pico_x - 25.5 + 2, pico_x - 25.5 + 14, bby - 5, bby + 5,
                  bb_top + 9, bb_top + 10.5, M["metal"]))
inside.append(box("rp2350", pico_x, pico_x + 7, bby - 3.5, bby + 3.5,
                  bb_top + 9, bb_top + 9.8, M["dark"]))
# DRV8833
drv_x = bbx - bbl / 2 + 14
inside.append(box("drv8833", drv_x - 10, drv_x + 10, bby - 7, bby + 7,
                  bb_top + 8, bb_top + 9.6, M["pcb_blue"]))
inside.append(box("drv_chip", drv_x - 3, drv_x + 3, bby - 2.5, bby + 2.5,
                  bb_top + 9.6, bb_top + 10.6, M["dark"]))

# 配線 (見た目用)
z = bb_top + 2
inside += [
    wire("w_bat_red", [(bx + bl_ / 2 - 3, 6, top + 15), (bx + bl_ / 2 + 8, 12, top + 25), (drv_x - 8, bby + 12, z)], (0.85, 0.1, 0.1)),
    wire("w_bat_blk", [(bx + bl_ / 2 - 3, -6, top + 15), (bx + bl_ / 2 + 8, -12, top + 25), (drv_x - 8, bby - 12, z)], (0.05, 0.05, 0.05)),
    wire("w_ml1", [(sx - 47, wall_in, top + 10), (sx - 50, wall_in - 8, top + 25), (drv_x + 4, bby + 9, z)], (0.85, 0.1, 0.1)),
    wire("w_ml2", [(sx - 49, wall_in, top + 6), (sx - 54, wall_in - 10, top + 22), (drv_x + 8, bby + 9, z)], (0.05, 0.05, 0.05)),
    wire("w_mr1", [(sx - 47, -wall_in, top + 10), (sx - 50, -wall_in + 8, top + 25), (drv_x + 4, bby - 9, z)], (0.85, 0.1, 0.1)),
    wire("w_mr2", [(sx - 49, -wall_in, top + 6), (sx - 54, -wall_in + 10, top + 22), (drv_x + 8, bby - 9, z)], (0.05, 0.05, 0.05)),
    wire("w_sig1", [(drv_x + 9, bby + 3, z + 8), (drv_x + 20, bby + 14, z + 14), (pico_x - 10, bby + 12, z + 8)], (0.1, 0.5, 0.95)),
    wire("w_sig2", [(drv_x + 9, bby + 1, z + 8), (drv_x + 22, bby + 16, z + 16), (pico_x - 6, bby + 12, z + 8)], (0.1, 0.65, 0.55)),
    wire("w_sig3", [(drv_x + 9, bby - 1, z + 8), (drv_x + 22, bby - 16, z + 16), (pico_x - 6, bby - 12, z + 8)], (0.98, 0.55, 0.05)),
    wire("w_sig4", [(drv_x + 9, bby - 3, z + 8), (drv_x + 20, bby - 14, z + 14), (pico_x - 10, bby - 12, z + 8)], (0.45, 0.3, 0.2)),
]

# ------------------------------------------------------------ ボディ
body_parts = []
btop = top + P["body_h"]
body = prism("body", rounded_rect(-bl / 2, bl / 2, -bw / 2, bw / 2, P.get("body_corner_r", 4)),
             G if cover else top, btop, M["body"])
bev = body.modifiers.new("bevel", "BEVEL")
bev.width = P.get("body_top_r", 4) * S
bev.segments = 8
bev.limit_method = "ANGLE"
body_parts.append(body)
if cover:
    # ホイールアーチ (Fusion スクリプトと同じく、モーターの外側の面より外を丸く切り取る)
    r = P["wheel_d"] / 2 + P["arch_clear"]
    y_from = hw - 1
    width = bw / 2 + 1 - y_from
    for s in (1, -1):
        cutter = cyl(f"arch{s}", sx, s * (y_from + width / 2), axle_z, r, width, M["dark"], axis="Y", verts=96)
        cutter.hide_render = True
        cutter.hide_viewport = True
        mod = body.modifiers.new(f"arch{s}", "BOOLEAN")
        mod.operation = "DIFFERENCE"
        mod.object = cutter
        mod.solver = "EXACT"
for y in (bw / 4, -bw / 4):
    body_parts.append(cyl(f"headlight{y}", bl / 2 + 0.2, y, top + P["body_h"] * 0.6,
                          P["headlight_d"] / 2, 1.2, M["light"], axis="X"))
    body_parts.append(cyl(f"taillight{y}", -bl / 2 - 0.2, y, top + P["body_h"] * 0.6,
                          P["headlight_d"] / 2, 1.2, M["tail"], axis="X"))
for sx_ in (1, -1):
    for sy_ in (1, -1):
        body_parts.append(cyl(f"screw{sx_}{sy_}", sx_ * post_x, sy_ * post_y, btop + 0.6, 3, 1.2, M["metal"]))

if P["name_text"]:
    cu = bpy.data.curves.new("name", "FONT")
    cu.body = P["name_text"]
    cu.align_x, cu.align_y = "CENTER", "CENTER"
    cu.size = P["name_h"] * 1.3 * S
    cu.extrude = 0.3 * S
    txt = link(bpy.data.objects.new("name", cu), M["text"])
    txt.location = (0, 0, (btop + 0.1) * S)
    body_parts.append(txt)

# ------------------------------------------------------------ stage
bpy.ops.mesh.primitive_plane_add(size=4, location=(0, 0, 0))
bpy.context.active_object.data.materials.append(M["floor"])

world = bpy.data.worlds.new("world")
world.use_nodes = True
world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.92, 0.94, 1.0, 1)
world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.25
scene.world = world

sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN"))
sun.data.energy = 1.5
sun.data.angle = math.radians(8)
sun.rotation_euler = (math.radians(40), math.radians(10), math.radians(-30))
scene.collection.objects.link(sun)

area = bpy.data.objects.new("key", bpy.data.lights.new("key", "AREA"))
area.data.energy = 12
area.data.size = 0.6
area.location = (0.4, -0.3, 0.5)
area.rotation_euler = (math.radians(45), 0, math.radians(50))
scene.collection.objects.link(area)

cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
cam.data.lens = 60
scene.collection.objects.link(cam)
scene.camera = cam


def aim(obj, target):
    from mathutils import Vector
    d = Vector(target) - obj.location
    obj.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()


scene.render.engine = "CYCLES"
scene.cycles.samples = 96
scene.cycles.use_denoising = True
scene.render.resolution_x, scene.render.resolution_y = 1600, 1000
scene.view_settings.view_transform = "AgX"
scene.view_settings.exposure = -0.3


def render(path, cam_loc, target):
    cam.location = cam_loc
    aim(cam, target)
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)


# 1. 完成 (前ななめ上から)
render(os.path.join(HERE, "car_complete.png"), (0.42, -0.36, 0.30), (0.0, 0.0, 0.03))

# 2. ボディを外した中身 (上から)
for o in body_parts:
    o.hide_render = True
render(os.path.join(HERE, "car_inside.png"), (0.30, -0.26, 0.38), (-0.005, 0.0, 0.02))
