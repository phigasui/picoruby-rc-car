"""PicoRuby BLE ラジコンカーの車体を Fusion で作るスクリプト.

Fusion の「ユーティリティ > アドイン > スクリプトとアドイン」で
このフォルダを追加して実行すると、新しいデザインに次の 3 つを作る。

- Chassis: 底板 (TT モーターの壁, Pico 2 W のスタンドオフ, 電池・ブレッドボードの枠,
  ボディ用の柱, キャスター台座)
- Body:    上にかぶせる丸みのあるカバー (ライトの穴, ホイールアーチ, 名前の彫り込みは任意)
- Bumper:  前のバンパー (底板の前端に差し込んで M2 で留める)

最後に同じフォルダの stl/ に STL を書き出す。

座標系: X = 前, Y = 左, Z = 上, 原点 = 底板の下面の中心。寸法はすべて mm。
寸法を変えたいときは下の P を書き換えてもう一度実行する。
"""

import os
import traceback

import adsk.core
import adsk.fusion

P = {
    # 底板
    "plate_l": 176.0,         # Bambu Lab A1 mini (180mm) に収まる長さ
    "plate_w": 108.0,         # ブレッドボードとモーターの壁のすき間が約 3.75mm になる幅
    "plate_t": 3.0,
    "plate_corner_r": 15.0,  # 底板の四隅の丸み (ボディと同じ)
    "plate_edge_r": 1.0,     # 底板の上下のふちの丸み
    # タイヤ (TT モーター用 65mm)
    "wheel_d": 65.0,
    # TT ギアモーター (秋月 MG-TTY1048D の寸法図より)
    #   https://akizukidenshi.com/goodsaffix/TTY1048D_1120D.pdf
    #   取付穴 2 つは上下に並び、シャフトと同じ向きに貫通している
    "tt_w": 18.75,       # Y 方向 (シャフトと同じ向き) の厚み
    "tt_h": 22.4,        # 高さ
    "tt_shaft_z": 11.2,  # モーターの底からシャフト中心までの高さ
    "tt_front": 11.3,    # シャフト中心から前端まで (ツメを除く)
    "tt_rear": 53.5,     # シャフト中心から後端 (モーター缶の端) まで
    "tt_hole_x": 20.0,   # シャフト中心から取付穴まで (後ろ向き)
    "tt_hole_zc": 11.2,      # モーターの底から 2 つの取付穴の中心まで
    "tt_hole_spacing": 17.54,  # 上下の取付穴の間隔 (中心から中心)
    "shaft_x": 40.0,     # 車体中心からシャフトまで (前向き)
    "mount_wall_t": 3.0,
    "mount_wall_h": 24.0,
    # ボディ
    "body_h": 45.0,
    "body_wall": 2.0,
    "body_top": 2.0,
    "body_clear": 1.0,   # モーター壁とのすき間
    "body_end_gap": 12.0,  # 底板の前後端からボディまで (バンパー・キャスター用)
    # True: ボディを車体の幅いっぱいにしてモーターも覆う (タイヤのところはホイールアーチで切り欠く)
    # False: モーターの間だけを覆う細いボディ
    "body_cover_motors": True,
    "arch_clear": 3.0,     # タイヤとホイールアーチのすき間
    "skirt_gap": 0.5,      # 底板の横の端とボディの横の壁のすき間
    "body_corner_r": 15.0, # ボディの四隅 (たての辺) の丸み
    "body_top_r": 8.0,     # ボディの上面のふちの丸み
    # ネジ
    # ネジ: モーターとキャスターは M3、ボディとバンパーは M2
    "m3_clear": 3.4,     # M3 の通し穴 (モーター, キャスター)
    "screw_clear": 2.4,  # M2 の通し穴 (バンパー, ボディの上面)
    "screw_pilot": 1.7,  # タッピングネジの下穴 (ボディの柱)
    "m2_pilot": 1.8,     # Pico のスタンドオフ
    "post_d": 8.0,
    # Pico 2 W (穴 47 x 11.4, M2)。ブレッドボードに直接さすなら False にしてスタンドオフを作らない
    "pico_standoffs": False,
    "pico_x": 34.0,
    "pico_y": -19.5,
    "pico_hole_dx": 47.0,
    "pico_hole_dy": 11.4,
    "standoff_d": 5.0,
    "standoff_h": 4.0,
    # ブレッドボード (83 x 53。Pico 2 WH と DRV8833 をここにさす)
    "bb_x": 23.0,
    "bb_y": 0.0,
    "bb_l": 83.0,
    "bb_w": 53.0,
    # 単3 x 3 電池ボックス (秋月 SBH-331AS: 68.5 x 48 x 18.7)
    # 横向き (長いほうを Y 方向) にして、モーターの後ろに置く
    "batt_x": -47.5,
    "batt_l": 48.0,   # X 方向
    "batt_w": 69.0,   # Y 方向
    # 底からスイッチを操作する穴。電池ボックスの左後ろの角から (前後 X, 左右 Y)
    "batt_switch_hole": (20.0, 10.0),
    # 枠 (ずれ止め)
    "lip_t": 1.5,
    "lip_h": 3.0,
    "lip_gap": 0.5,
    # ボールキャスター
    "caster_x": -81.0,   # ナットがボディの外に出る位置
    "caster_hole_spacing": 20.0,  # Y 方向 (中心から中心)
    "caster_h": 25.0,             # 地面から取付面まで (タミヤ 70144 の低いほうの組み方)
    # バンパー
    "bumper_depth": 10.0,
    "bumper_tab": 10.0,
    "bumper_h": 16.0,
    "bumper_hole_y": 30.0,
    # かざり
    "name_text": "",       # ボディの上に彫る文字。空なら彫らない
    "name_font": "Arial Rounded MT Bold",
    "name_h": 14.0,
    "name_depth": 1.0,
    "headlight_d": 10.0,
}

app = adsk.core.Application.get()
ui = app.userInterface


# ---------------------------------------------------------------- helpers

def mm(v):
    return v / 10.0  # Fusion API の内部単位は cm


def vi(v):
    return adsk.core.ValueInput.createByReal(mm(v))


def p3(x, y, z=0.0):
    return adsk.core.Point3D.create(mm(x), mm(y), mm(z))


def _extrude(comp, profile, z0, h, op, body):
    ext = comp.features.extrudeFeatures
    inp = ext.createInput(profile, op)
    inp.setOneSideExtent(
        adsk.fusion.DistanceExtentDefinition.create(vi(h)),
        adsk.fusion.ExtentDirections.PositiveExtentDirection,
    )
    if z0:
        inp.startExtent = adsk.fusion.OffsetStartDefinition.create(vi(z0))
    if body is not None:
        inp.participantBodies = [body]
    return ext.add(inp)


def _op(body, cut):
    if cut:
        return adsk.fusion.FeatureOperations.CutFeatureOperation
    if body is None:
        return adsk.fusion.FeatureOperations.NewBodyFeatureOperation
    return adsk.fusion.FeatureOperations.JoinFeatureOperation


def box(comp, x0, y0, x1, y1, z0, h, body=None, cut=False):
    """XY 平面に長方形を描いて z0 から h だけ押し出す。新しいボディを返す."""
    sk = comp.sketches.add(comp.xYConstructionPlane)
    sk.sketchCurves.sketchLines.addTwoPointRectangle(p3(x0, y0), p3(x1, y1))
    f = _extrude(comp, sk.profiles.item(0), z0, h, _op(body, cut), body)
    return body if body is not None else f.bodies.item(0)


def poly(comp, pts, z0, h, body=None, cut=False):
    sk = comp.sketches.add(comp.xYConstructionPlane)
    lines = sk.sketchCurves.sketchLines
    for i, (x, y) in enumerate(pts):
        nx, ny = pts[(i + 1) % len(pts)]
        lines.addByTwoPoints(p3(x, y), p3(nx, ny))
    f = _extrude(comp, sk.profiles.item(0), z0, h, _op(body, cut), body)
    return body if body is not None else f.bodies.item(0)


def cyl(comp, cx, cy, d, z0, h, body=None, cut=False):
    sk = comp.sketches.add(comp.xYConstructionPlane)
    sk.sketchCurves.sketchCircles.addByCenterRadius(p3(cx, cy), mm(d / 2))
    f = _extrude(comp, sk.profiles.item(0), z0, h, _op(body, cut), body)
    return body if body is not None else f.bodies.item(0)


def hole(comp, plane, center, d, body):
    """plane 上の点 center (モデル座標) を通る丸穴を、両側に貫通させて開ける."""
    sk = comp.sketches.add(plane)
    c = sk.modelToSketchSpace(p3(*center))
    sk.sketchCurves.sketchCircles.addByCenterRadius(c, mm(d / 2))
    ext = comp.features.extrudeFeatures
    inp = ext.createInput(sk.profiles.item(0), adsk.fusion.FeatureOperations.CutFeatureOperation)
    inp.setSymmetricExtent(vi(400), True)
    inp.participantBodies = [body]
    ext.add(inp)


def edges_where(body, pred):
    """両端の頂点が pred(start, end) を満たす辺を集める."""
    coll = adsk.core.ObjectCollection.create()
    for e in body.edges:
        if pred(e.startVertex.geometry, e.endVertex.geometry):
            coll.add(e)
    return coll


def fillet(comp, edges, r):
    if edges.count == 0 or r <= 0:
        return
    fillets = comp.features.filletFeatures
    inp = fillets.createInput()
    try:
        inp.edgeSetInputs.addConstantRadiusEdgeSet(edges, vi(r), True)
    except AttributeError:
        # 古い API
        inp.addConstantRadiusEdgeSet(edges, vi(r), True)
    fillets.add(inp)


def shell_open_bottom(comp, body, z, thickness):
    """高さ z の平らな下の面を開けて、厚さ thickness でくり抜く."""
    faces = adsk.core.ObjectCollection.create()
    for f in body.faces:
        if (f.geometry.surfaceType == adsk.core.SurfaceTypes.PlaneSurfaceType
                and abs(f.pointOnFace.z - mm(z)) < 1e-4):
            faces.add(f)
    shells = comp.features.shellFeatures
    inp = shells.createInput(faces, False)
    inp.insideThickness = vi(thickness)
    shells.add(inp)


def plane_at_y(comp, y):
    """Y = y の位置に XZ 平面と平行な作業平面を作る.

    XZ 平面の法線の向きに頼らないよう、できた平面の位置を見て符号を合わせる。
    """
    planes = comp.constructionPlanes
    for sign in (1, -1):
        pin = planes.createInput()
        pin.setByOffset(comp.xZConstructionPlane, vi(sign * y))
        plane = planes.add(pin)
        if abs(plane.geometry.origin.y - mm(y)) < 1e-6 or abs(y) < 1e-9:
            return plane
        plane.deleteMe()
    raise RuntimeError("plane_at_y: Y=%s mm の平面が作れませんでした" % y)


def cut_cylinder_y(comp, x, z, r, ya, yb, body):
    """Y 方向を軸にした円柱 (Y = ya..yb) で body を切り取る."""
    plane = plane_at_y(comp, (ya + yb) / 2)
    sk = comp.sketches.add(plane)
    c = sk.modelToSketchSpace(p3(x, (ya + yb) / 2, z))
    sk.sketchCurves.sketchCircles.addByCenterRadius(c, mm(r))
    ext = comp.features.extrudeFeatures
    inp = ext.createInput(sk.profiles.item(0), adsk.fusion.FeatureOperations.CutFeatureOperation)
    inp.setSymmetricExtent(vi(abs(yb - ya)), True)
    inp.participantBodies = [body]
    ext.add(inp)


def hole_z(comp, x, y, d, body):
    hole(comp, comp.xYConstructionPlane, (x, y, 0), d, body)


def hole_y(comp, x, z, d, body):
    hole(comp, comp.xZConstructionPlane, (x, 0, z), d, body)


def hole_x(comp, y, z, d, body):
    hole(comp, comp.yZConstructionPlane, (0, y, z), d, body)


def frame(comp, cx, cy, l, w, body):
    """部品がずれないための枠 (高さ lip_h)."""
    g, t, h, z = P["lip_gap"], P["lip_t"], P["lip_h"], P["plate_t"]
    x0, x1 = cx - l / 2 - g, cx + l / 2 + g
    y0, y1 = cy - w / 2 - g, cy + w / 2 + g
    box(comp, x0 - t, y0 - t, x1 + t, y1 + t, z, h, body)
    box(comp, x0, y0, x1, y1, z, h, body, cut=True)


def new_component(root, name):
    occ = root.occurrences.addNewComponent(adsk.core.Matrix3D.create())
    occ.component.name = name
    return occ.component


# ---------------------------------------------------------------- derived

def derived():
    d = {}
    d["half_l"] = P["plate_l"] / 2
    d["half_w"] = P["plate_w"] / 2
    # モーター壁の内側の面 (車体の中心側)
    d["wall_in_y"] = d["half_w"] - P["tt_w"] - P["mount_wall_t"]
    # モーターの間の通路の幅。柱はこの中に立てる
    d["channel_w"] = 2 * (d["wall_in_y"] - P["body_clear"])
    if P["body_cover_motors"]:
        d["body_w"] = 2 * (d["half_w"] + P["skirt_gap"] + P["body_wall"])
    else:
        d["body_w"] = d["channel_w"]
    d["body_l"] = P["plate_l"] - 2 * P["body_end_gap"]
    # 柱は、上面のふちの丸みにかからない位置に立てる
    d["post_x"] = d["body_l"] / 2 - P["body_wall"] - P["body_top_r"] - P["post_d"] / 2 - 1
    if P["body_cover_motors"]:
        # 広いボディのときは四隅寄りに立てる (モーターより前と後ろ)
        d["post_y"] = d["body_w"] / 2 - P["body_wall"] - P["body_top_r"] - P["post_d"] / 2 - 1
    else:
        d["post_y"] = d["channel_w"] / 2 - P["body_wall"] - P["post_d"] / 2 - 0.5
    d["axle_z"] = P["plate_t"] + P["tt_shaft_z"]  # 底板の下面から車軸まで
    d["post_h"] = P["body_h"] - P["body_top"]
    # 地面から底板の下面まで
    d["ground"] = P["wheel_d"] / 2 - P["plate_t"] - P["tt_shaft_z"]
    d["caster_boss"] = max(0.0, d["ground"] - P["caster_h"])
    return d


# ---------------------------------------------------------------- parts

def build_chassis(comp, d):
    t = P["plate_t"]
    hl, hw = d["half_l"], d["half_w"]
    plate = box(comp, -hl, -hw, hl, hw, 0, t)
    plate.name = "Chassis"
    # ほかの形を足す前に、四隅と上下のふちを丸める
    eps = 1e-4
    fillet(comp, edges_where(plate, lambda a, b: abs(a.x - b.x) < eps and abs(a.y - b.y) < eps),
           P["plate_corner_r"])
    fillet(comp, edges_where(plate, lambda a, b: abs(a.z - b.z) < eps), P["plate_edge_r"])

    # TT モーターを留める壁 (M3×25 をタイヤ側から モーター → 壁 に通して内側でナット)
    sx = P["shaft_x"]
    for s in (1, -1):
        y_in = s * d["wall_in_y"]
        y_out = s * (d["wall_in_y"] + P["mount_wall_t"])
        box(comp, sx - P["tt_hole_x"] - 8, y_in, sx + 5, y_out, t, P["mount_wall_h"], plate)
    for hz in (P["tt_hole_zc"] - P["tt_hole_spacing"] / 2, P["tt_hole_zc"] + P["tt_hole_spacing"] / 2):
        hole_y(comp, sx - P["tt_hole_x"], t + hz, P["m3_clear"], plate)
    # 下の穴は底板に近いので、壁の内側のナットが底板に当たらないよう浅い逃げを彫る
    low = P["tt_hole_zc"] - P["tt_hole_spacing"] / 2
    nut_r = 3.3  # M3 ナットの角まで
    if low < nut_r + 0.3:
        depth = min(t - 1.5, nut_r + 0.3 - low)
        hx = sx - P["tt_hole_x"]
        for s_ in (1, -1):
            ya, yb = s_ * (d["wall_in_y"] - 4.5), s_ * d["wall_in_y"]
            box(comp, hx - 4, min(ya, yb), hx + 4, max(ya, yb), t - depth, depth, plate, cut=True)

    # Pico 2 W のスタンドオフ (M2 タッピング)
    px, py = P["pico_x"], P["pico_y"]
    pico_holes = [(px + ix * P["pico_hole_dx"] / 2, py + iy * P["pico_hole_dy"] / 2)
                  for ix in (1, -1) for iy in (1, -1)] if P["pico_standoffs"] else []
    for x, y in pico_holes:
        cyl(comp, x, y, P["standoff_d"], t, P["standoff_h"], plate)
    for x, y in pico_holes:
        cyl(comp, x, y, P["m2_pilot"], t, P["standoff_h"], plate, cut=True)

    # ブレッドボードと電池ボックスの枠
    frame(comp, P["bb_x"], P["bb_y"], P["bb_l"], P["bb_w"], plate)
    frame(comp, P["batt_x"], 0, P["batt_l"], P["batt_w"], plate)

    # 電池ボックスのスイッチを底から操作する穴 (左後ろの角から)
    if P["batt_switch_hole"]:
        hx, hy = P["batt_switch_hole"]
        bx0 = P["batt_x"] - P["batt_l"] / 2   # 後ろの端
        by1 = P["batt_w"] / 2                 # 左の端 (+Y)
        box(comp, bx0, by1 - hy, bx0 + hx, by1, 0, t, plate, cut=True)

    # ボディを留める柱 (M2 タッピング)
    posts = [(sx_ * d["post_x"], sy_ * d["post_y"]) for sx_ in (1, -1) for sy_ in (1, -1)]
    for x, y in posts:
        cyl(comp, x, y, P["post_d"], t, d["post_h"], plate)
    for x, y in posts:
        cyl(comp, x, y, P["screw_pilot"], t, d["post_h"], plate, cut=True)

    # ボールキャスターの台座 (底板の下)
    cx, cs = P["caster_x"], P["caster_hole_spacing"]
    if d["caster_boss"] > 0.1:
        box(comp, cx - 6, -cs / 2 - 6, cx + 6, cs / 2 + 6, -d["caster_boss"], d["caster_boss"], plate)
    for y in (cs / 2, -cs / 2):
        hole_z(comp, cx, y, P["m3_clear"], plate)

    # バンパーを留める穴
    for y in (P["bumper_hole_y"], -P["bumper_hole_y"]):
        hole_z(comp, hl - P["bumper_tab"] / 2, y, P["screw_clear"], plate)

    return plate, posts


def build_body(comp, d, posts):
    t, wall = P["plate_t"], P["body_wall"]
    bl, bw, bh = d["body_l"], d["body_w"], P["body_h"]
    x0, x1, y0, y1 = -bl / 2, bl / 2, -bw / 2, bw / 2
    top = t + bh

    body = box(comp, x0, y0, x1, y1, t, bh)
    body.name = "Body"
    # 角を丸めてから、下の面を開けて中をくり抜く (丸い角でも壁の厚さがそろう)
    eps = 1e-4
    fillet(comp, edges_where(body, lambda a, b: abs(a.x - b.x) < eps and abs(a.y - b.y) < eps),
           P["body_corner_r"])
    fillet(comp, edges_where(body, lambda a, b: abs(a.z - mm(top)) < eps and abs(b.z - mm(top)) < eps),
           P["body_top_r"])
    shell_open_bottom(comp, body, t, wall)

    if P["body_cover_motors"]:
        # 横の壁は底板の外側にあるので、底板の横の端も隠れるように下まで伸ばす
        cr = P["body_corner_r"]
        for ya, yb in ((y0, y0 + wall), (y1 - wall, y1)):
            box(comp, x0 + cr, ya, x1 - cr, yb, 0, t, body)
        # ホイールアーチ: モーターの外側の面より外を、タイヤに合わせて丸く切り取る
        r = P["wheel_d"] / 2 + P["arch_clear"]
        y_from = d["half_w"] - 1
        for s in (1, -1):
            cut_cylinder_y(comp, P["shaft_x"], d["axle_z"], r,
                           s * y_from, s * (y1 + 1), body)

    # 上から柱に留めるネジ穴
    for x, y in posts:
        hole_z(comp, x, y, P["screw_clear"], body)

    # モーターの配線を通す切り欠き (モーターがボディの外にあるときだけ)
    if not P["body_cover_motors"]:
        wx = P["shaft_x"] - P["tt_rear"] + 8
        for ya, yb in ((y0 - 1, y0 + wall + 1), (y1 - wall - 1, y1 + 1)):
            box(comp, wx - 6, ya, wx + 6, yb, t, 8, body, cut=True)

    # ヘッドライト (前)
    for y in (bw / 4, -bw / 4):
        hole_x(comp, y, t + bh * 0.6, P["headlight_d"], body)

    # 名前の彫り込み (上面)。上面を下にして印刷するので浮き彫りではなく彫り込みにする
    if not P["name_text"]:
        return body
    try:
        planes = comp.constructionPlanes
        pin = planes.createInput()
        pin.setByOffset(comp.xYConstructionPlane, vi(top))
        plane = planes.add(pin)
        sk = comp.sketches.add(plane)
        ti = sk.sketchTexts.createInput2(P["name_text"], mm(P["name_h"]))
        ti.setAsMultiLine(
            sk.modelToSketchSpace(p3(x0 + 10, y0 + 6, top)),
            sk.modelToSketchSpace(p3(x1 - 10, y1 - 6, top)),
            adsk.core.HorizontalAlignments.CenterHorizontalAlignment,
            adsk.core.VerticalAlignments.MiddleVerticalAlignment,
            0,
        )
        ti.fontName = P["name_font"]
        text = sk.sketchTexts.add(ti)
        ext = comp.features.extrudeFeatures
        inp = ext.createInput(text, adsk.fusion.FeatureOperations.CutFeatureOperation)
        inp.setDistanceExtent(False, vi(-P["name_depth"]))
        inp.participantBodies = [body]
        ext.add(inp)
    except Exception:
        # フォントがない環境などでは文字なしで続ける
        app.log("name text skipped:\n" + traceback.format_exc())

    return body


def build_bumper(comp, d):
    t, hl = P["plate_t"], d["half_l"]
    tab, depth, h = P["bumper_tab"], P["bumper_depth"], P["bumper_h"]
    w = P["plate_w"] - 10
    z0 = -4.0
    # 底板をはさむ部分 + 前の太い部分
    bumper = box(comp, hl - tab, -w / 2, hl + depth, w / 2, z0, t + 8)
    bumper.name = "Bumper"
    box(comp, hl, -w / 2, hl + depth, w / 2, z0, h, bumper)
    # 底板が入るすき間
    box(comp, hl - tab - 1, -w / 2 - 1, hl + 0.3, w / 2 + 1, -0.2, t + 0.4, bumper, cut=True)
    for y in (P["bumper_hole_y"], -P["bumper_hole_y"]):
        hole_z(comp, hl - tab / 2, y, P["screw_clear"], bumper)
    return bumper


def export_stl(design, bodies):
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "stl")
    os.makedirs(out, exist_ok=True)
    em = design.exportManager
    for b in bodies:
        path = os.path.join(out, b.name + ".stl")
        opts = em.createSTLExportOptions(b, path)
        opts.meshRefinement = adsk.fusion.MeshRefinementSettings.MeshRefinementMedium
        em.execute(opts)
    return out


# ---------------------------------------------------------------- main

def run(context):
    try:
        app.documents.add(adsk.core.DocumentTypes.FusionDesignDocumentType)
        design = adsk.fusion.Design.cast(app.activeProduct)
        design.designType = adsk.fusion.DesignTypes.ParametricDesignType
        root = design.rootComponent
        d = derived()

        chassis, posts = build_chassis(new_component(root, "Chassis"), d)
        body = build_body(new_component(root, "Body"), d, posts)
        bumper = build_bumper(new_component(root, "Bumper"), d)

        out = export_stl(design, [chassis, body, bumper])
        ui.messageBox(
            "できました！\n\n"
            f"車体の大きさ: 長さ {P['plate_l'] + P['bumper_depth']:.0f} mm "
            f"x 幅 {P['plate_w']:.0f} mm (タイヤをのぞく)\n"
            f"地面から底板まで: {d['ground']:.1f} mm\n"
            f"キャスター台座の高さ: {d['caster_boss']:.1f} mm "
            f"(キャスターの高さ {P['caster_h']:.0f} mm として計算)\n\n"
            f"STL: {out}"
        )
    except Exception:
        ui.messageBox("エラーが出ました:\n" + traceback.format_exc())
