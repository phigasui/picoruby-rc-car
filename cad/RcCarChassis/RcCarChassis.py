"""PicoRuby BLE ラジコンカーの車体を Fusion で作るスクリプト.

Fusion の「ユーティリティ > アドイン > スクリプトとアドイン」で
このフォルダを追加して実行すると、新しいデザインに次の 3 つを作る。

- Chassis: 底板 (TT モーターの壁, Pico 2 W のスタンドオフ, 電池・ブレッドボードの枠,
  ボディ用の柱, キャスター台座)
- Body:    上にかぶせるカバー (名前の彫り込み, ライトの穴, 配線の切り欠き)
- Bumper:  前のバンパー (底板の前端に差し込んで M3 で留める)

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
    "plate_l": 192.0,
    "plate_w": 132.0,
    "plate_t": 3.0,
    "plate_chamfer": 10.0,
    # タイヤ (TT モーター用 65mm)
    "wheel_d": 65.0,
    # TT ギアモーター (製品で少しちがうので実物をはかって直す)
    "tt_w": 22.5,        # Y 方向 (シャフトと同じ向き) の厚み
    "tt_shaft_z": 9.4,   # モーターの底からシャフト中心までの高さ
    "tt_front": 11.0,    # シャフト中心から前端まで
    "tt_rear": 59.0,     # シャフト中心から後端 (モーター缶の端) まで
    "tt_hole1": 20.0,    # シャフト中心から 1 つめの取付穴まで (後ろ向き)
    "tt_hole2": 37.5,    # シャフト中心から 2 つめの取付穴まで
    "tt_hole_z": 9.4,    # モーターの底から取付穴までの高さ
    "shaft_x": 40.0,     # 車体中心からシャフトまで (前向き)
    "mount_wall_t": 3.0,
    "mount_wall_h": 20.0,
    # ボディ
    "body_h": 45.0,
    "body_wall": 2.0,
    "body_top": 2.0,
    "body_clear": 1.0,   # モーター壁とのすき間
    "body_end_gap": 12.0,  # 底板の前後端からボディまで (バンパー・キャスター用)
    # ネジ
    "m3_clear": 3.4,
    "m3_pilot": 2.6,
    "m2_pilot": 1.8,
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
    "bb_x": 36.5,
    "bb_y": 0.0,
    "bb_l": 83.0,
    "bb_w": 53.0,
    # 単3 x 3 電池ボックス (秋月 SBH-331AS: 68.5 x 48 x 18.7)
    "batt_x": -44.5,
    "batt_l": 69.0,
    "batt_w": 48.0,
    # 枠 (ずれ止め)
    "lip_t": 1.5,
    "lip_h": 3.0,
    "lip_gap": 0.5,
    # ボールキャスター
    "caster_x": -86.0,
    "caster_hole_spacing": 25.0,  # Y 方向
    "caster_h": 25.0,             # 地面から取付面まで (タミヤ 70144 の低いほうの組み方)
    # バンパー
    "bumper_depth": 10.0,
    "bumper_tab": 10.0,
    "bumper_h": 16.0,
    "bumper_hole_y": 30.0,
    # かざり
    "name_text": "KURUMA",
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
    d["body_w"] = 2 * (d["wall_in_y"] - P["body_clear"])
    d["body_l"] = P["plate_l"] - 2 * P["body_end_gap"]
    d["post_x"] = d["body_l"] / 2 - P["body_wall"] - P["post_d"] / 2 - 0.5
    d["post_y"] = d["body_w"] / 2 - P["body_wall"] - P["post_d"] / 2 - 0.5
    d["post_h"] = P["body_h"] - P["body_top"]
    # 地面から底板の下面まで
    d["ground"] = P["wheel_d"] / 2 - P["plate_t"] - P["tt_shaft_z"]
    d["caster_boss"] = max(0.0, d["ground"] - P["caster_h"])
    return d


# ---------------------------------------------------------------- parts

def build_chassis(comp, d):
    t = P["plate_t"]
    hl, hw, c = d["half_l"], d["half_w"], P["plate_chamfer"]
    plate = poly(comp, [
        (hl - c, -hw), (hl, -hw + c), (hl, hw - c), (hl - c, hw),
        (-hl + c, hw), (-hl, hw - c), (-hl, -hw + c), (-hl + c, -hw),
    ], 0, t)
    plate.name = "Chassis"

    # TT モーターを留める壁 (M3 ボルトを壁 → モーターに通して外側でナット)
    sx = P["shaft_x"]
    for s in (1, -1):
        y_in = s * d["wall_in_y"]
        y_out = s * (d["wall_in_y"] + P["mount_wall_t"])
        box(comp, sx - P["tt_hole2"] - 8, y_in, sx + 5, y_out, t, P["mount_wall_h"], plate)
    for hx in (P["tt_hole1"], P["tt_hole2"]):
        hole_y(comp, sx - hx, t + P["tt_hole_z"], P["m3_clear"], plate)

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

    # ボディを留める柱 (M3 タッピング)
    posts = [(sx_ * d["post_x"], sy_ * d["post_y"]) for sx_ in (1, -1) for sy_ in (1, -1)]
    for x, y in posts:
        cyl(comp, x, y, P["post_d"], t, d["post_h"], plate)
    for x, y in posts:
        cyl(comp, x, y, P["m3_pilot"], t, d["post_h"], plate, cut=True)

    # ボールキャスターの台座 (底板の下)
    cx, cs = P["caster_x"], P["caster_hole_spacing"]
    if d["caster_boss"] > 0.1:
        box(comp, cx - 6, -cs / 2 - 6, cx + 6, cs / 2 + 6, -d["caster_boss"], d["caster_boss"], plate)
    for y in (cs / 2, -cs / 2):
        hole_z(comp, cx, y, P["m3_clear"], plate)

    # バンパーを留める穴
    for y in (P["bumper_hole_y"], -P["bumper_hole_y"]):
        hole_z(comp, hl - P["bumper_tab"] / 2, y, P["m3_clear"], plate)

    return plate, posts


def build_body(comp, d, posts):
    t, wall = P["plate_t"], P["body_wall"]
    bl, bw, bh = d["body_l"], d["body_w"], P["body_h"]
    x0, x1, y0, y1 = -bl / 2, bl / 2, -bw / 2, bw / 2
    top = t + bh

    body = box(comp, x0, y0, x1, y1, t, bh)
    body.name = "Body"
    box(comp, x0 + wall, y0 + wall, x1 - wall, y1 - wall, t, bh - P["body_top"], body, cut=True)

    # 上から柱に留めるネジ穴
    for x, y in posts:
        hole_z(comp, x, y, P["m3_clear"], body)

    # モーターの配線を通す切り欠き (左右)
    wx = P["shaft_x"] - P["tt_rear"] + 8
    for ya, yb in ((y0 - 1, y0 + wall + 1), (y1 - wall - 1, y1 + 1)):
        box(comp, wx - 6, ya, wx + 6, yb, t, 8, body, cut=True)

    # 電池ボックスのスイッチに指がとどく窓 (後ろ)
    box(comp, x0 - 1, -15, x0 + wall + 1, 15, t + 2, 18, body, cut=True)

    # ヘッドライト (前)
    for y in (bw / 4, -bw / 4):
        hole_x(comp, y, t + bh * 0.6, P["headlight_d"], body)

    # 名前の彫り込み (上面)。上面を下にして印刷するので浮き彫りではなく彫り込みにする
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
        hole_z(comp, hl - tab / 2, y, P["m3_clear"], bumper)
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
