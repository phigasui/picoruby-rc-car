"""砂の上を走るための、パドル付きタイヤを Fusion で作るスクリプト.

タミヤ ダブルギヤボックス (70168) の 3mm 六角シャフトに差し込む。
TPU (95A くらい) で印刷する。4 個印刷する。

Fusion の「ユーティリティ > アドイン > スクリプトとアドイン」で
このフォルダを追加して実行すると、新しいデザインに Tire を作り、
同じフォルダの stl/ に STL を書き出す。

座標系: Z = 車軸, 原点 = タイヤの片側の面の中心。寸法はすべて mm。
寸法を変えたいときは下の P を書き換えてもう一度実行する。
"""

import math
import os
import traceback

import adsk.core
import adsk.fusion

# ---------------------------------------------------------------- parameters

P = {
    "tire_d": 80.0,       # パドルの先までの直径
    "tire_w": 30.0,       # 幅 (Z 方向)
    "paddle_h": 4.0,      # パドルの高さ (外周から外へ)
    "paddle_t": 3.0,      # パドルの厚み
    "paddles": 12,        # パドルの数
    "tread_t": 4.0,       # 外周の輪の厚み
    "web_t": 4.0,         # 外周と軸をつなぐ板の厚み
    "hub_d": 14.0,        # 軸のまわりの太い部分
    # 3mm 六角シャフト (二面幅 3mm)。TPU は縮みやすいので少しゆるめにする。
    # きつすぎて入らないときは 0.1 ずつ増やす。ゆるくて抜けるときは減らす
    "hex_af": 3.25,
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


def poly(comp, pts, z0, h, body=None, cut=False):
    sk = comp.sketches.add(comp.xYConstructionPlane)
    lines = sk.sketchCurves.sketchLines
    for i, (x, y) in enumerate(pts):
        nx, ny = pts[(i + 1) % len(pts)]
        lines.addByTwoPoints(p3(x, y), p3(nx, ny))
    f = _extrude(comp, sk.profiles.item(0), z0, h, _op(body, cut), body)
    return body if body is not None else f.bodies.item(0)


def cyl(comp, d, z0, h, body=None, cut=False):
    sk = comp.sketches.add(comp.xYConstructionPlane)
    sk.sketchCurves.sketchCircles.addByCenterRadius(p3(0, 0), mm(d / 2))
    f = _extrude(comp, sk.profiles.item(0), z0, h, _op(body, cut), body)
    return body if body is not None else f.bodies.item(0)


# ---------------------------------------------------------------- parts

def build_tire(comp):
    w = P["tire_w"]
    r_out = P["tire_d"] / 2 - P["paddle_h"]   # 外周の輪の外側
    r_in = r_out - P["tread_t"]                # 外周の輪の内側

    # 外周の輪
    tire = cyl(comp, 2 * r_out, 0, w)
    tire.name = "Tire"
    cyl(comp, 2 * r_in, 0, w, tire, cut=True)

    # 輪と軸をつなぐ板 (幅の真ん中) と、軸のまわり
    cyl(comp, 2 * r_in + 1, (w - P["web_t"]) / 2, P["web_t"], tire)
    cyl(comp, P["hub_d"], 0, w, tire)

    # パドル: 外周から外へ出る板。輪に 0.5mm めりこませてつなぐ
    half = P["paddle_t"] / 2
    for i in range(P["paddles"]):
        a = 2 * math.pi * i / P["paddles"]
        c, s = math.cos(a), math.sin(a)
        corners = [(r_out - 0.5, -half), (r_out + P["paddle_h"], -half),
                   (r_out + P["paddle_h"], half), (r_out - 0.5, half)]
        pts = [(x * c - y * s, x * s + y * c) for x, y in corners]
        poly(comp, pts, 0, w, tire)

    # 3mm 六角シャフトの穴 (頂点までの半径 = 二面幅 / √3)
    rv = P["hex_af"] / math.sqrt(3)
    hexagon = [(rv * math.cos(math.pi / 3 * k), rv * math.sin(math.pi / 3 * k)) for k in range(6)]
    poly(comp, hexagon, 0, w, tire, cut=True)
    return tire


def export_stl(design, body):
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "stl")
    os.makedirs(out, exist_ok=True)
    em = design.exportManager
    path = os.path.join(out, body.name + ".stl")
    opts = em.createSTLExportOptions(body, path)
    opts.meshRefinement = adsk.fusion.MeshRefinementSettings.MeshRefinementMedium
    em.execute(opts)
    return out


# ---------------------------------------------------------------- main

def run(context):
    try:
        app.documents.add(adsk.core.DocumentTypes.FusionDesignDocumentType)
        design = adsk.fusion.Design.cast(app.activeProduct)
        design.designType = adsk.fusion.DesignTypes.ParametricDesignType
        occ = design.rootComponent.occurrences.addNewComponent(adsk.core.Matrix3D.create())
        occ.component.name = "Tire"
        tire = build_tire(occ.component)
        out = export_stl(design, tire)
        ui.messageBox(
            "できました！\n\n"
            f"タイヤ: 直径 {P['tire_d']:.0f} mm x 幅 {P['tire_w']:.0f} mm、パドル {P['paddles']} 枚\n"
            "TPU で 4 個印刷してください。\n\n"
            f"STL: {out}"
        )
    except Exception:
        ui.messageBox("エラーが出ました:\n" + traceback.format_exc())
