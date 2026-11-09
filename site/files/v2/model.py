# /// script
# requires-python = ">=3.10"
# dependencies = ["simplecadapi"]
#
# [tool.simplecadapi]
# id = "model"
# ///
import marimo

app = marimo.App()

with app.setup:
    import simplecadapi as scad
    from simplecadapi import ql
    import math


@app.cell
def _():
    # ---- params ----
    device_w = scad.var("device_w", 78, unit="mm")
    device_t = scad.var("device_t", 12, unit="mm")
    tilt_deg = scad.var("tilt_deg", 70, unit="deg")
    base_w = scad.var("base_w", 90, unit="mm")
    base_d = scad.var("base_d", 80, unit="mm")
    lip_h = scad.var("lip_h", 15, unit="mm")
    back_h = scad.var("back_h", 110, unit="mm")
    slot_gap = scad.var("slot_gap", 2, unit="mm")
    plate_t = scad.var("plate_t", 5, unit="mm")
    notch_w = scad.var("notch_w", 20, unit="mm")
    phone_h = scad.var("phone_h", 160, unit="mm")
    return device_w, device_t, tilt_deg, base_w, base_d, lip_h, back_h, slot_gap, plate_t, notch_w, phone_h


@app.cell
def _(base_d, base_w, plate_t):
    # ---- feature: base-plate (build) ----
    base_plate = scad.make_box_rsolid(width=base_w, height=base_d, depth=plate_t, bottom_face_center=(0, 0, 0))
    return (base_plate,)


@app.cell
def _(back_h, base_d, base_plate, base_w, plate_t, tilt_deg):
    # ---- feature: back-plate (add) ----
    _c = math.cos(math.radians(tilt_deg))
    _s = math.sin(math.radians(tilt_deg))
    # 斜支撑板前表面在插槽底线处（z = plate_t）的 y 坐标：顶端正好落在底板后边沿附近
    _y0 = base_d / 2 - back_h * _c
    # 板底向底板内延伸一点，保证与底板重叠相接
    _d = (plate_t / 2) / _s
    _p1 = (_y0 - _d * _c, plate_t - _d * _s)
    _p2 = (_y0 + back_h * _c, plate_t + back_h * _s)
    _p3 = (_p2[0] + plate_t * _s, _p2[1] - plate_t * _c)
    _p4 = (_p1[0] + plate_t * _s, _p1[1] - plate_t * _c)
    _wire = scad.make_polyline_rwire(points=[(0, _p1[0], _p1[1]), (0, _p2[0], _p2[1]), (0, _p3[0], _p3[1]), (0, _p4[0], _p4[1])], closed=True)
    _face = scad.make_face_from_wire_rface(wire=_wire, normal=(-1, 0, 0))
    _slab = scad.extrude_rsolid(profile=_face, direction=(1, 0, 0), distance=base_w)
    _slab = scad.translate_shape(shape=_slab, vector=(-base_w / 2, 0, 0))
    back_plate = scad.union_rsolid(base_plate, _slab)
    return (back_plate,)


@app.cell
def _(back_h, back_plate, base_d, base_w, device_t, lip_h, notch_w, plate_t, slot_gap, tilt_deg):
    # ---- feature: lip-left (add) ----
    _c = math.cos(math.radians(tilt_deg))
    _s = math.sin(math.radians(tilt_deg))
    _y0 = base_d / 2 - back_h * _c
    # 托唇后表面：与斜板前表面平行，垂直间距 = 槽宽 device_t + slot_gap
    _yb = _y0 - (device_t + slot_gap) / _s
    _d = (plate_t / 2) / _s
    # 底边伸进底板，保证相接；顶边沿斜面长 lip_h
    _bb = (_yb - _d * _c, plate_t - _d * _s)
    _bf = (_bb[0] - plate_t * _s, _bb[1] + plate_t * _c)
    _tb = (_yb + lip_h * _c, plate_t + lip_h * _s)
    _tf = (_tb[0] - plate_t * _s, _tb[1] + plate_t * _c)
    _wire = scad.make_polyline_rwire(points=[(0, _bf[0], _bf[1]), (0, _tf[0], _tf[1]), (0, _tb[0], _tb[1]), (0, _bb[0], _bb[1])], closed=True)
    _face = scad.make_face_from_wire_rface(wire=_wire, normal=(-1, 0, 0))
    _lip = scad.extrude_rsolid(profile=_face, direction=(1, 0, 0), distance=(base_w - notch_w) / 2)
    _lip = scad.translate_shape(shape=_lip, vector=(-base_w / 2, 0, 0))
    lip_left = scad.union_rsolid(back_plate, _lip)
    return (lip_left,)


@app.cell
def _(back_h, base_d, base_w, device_t, lip_h, lip_left, notch_w, plate_t, slot_gap, tilt_deg):
    # ---- feature: lip-right (add) ----
    _c = math.cos(math.radians(tilt_deg))
    _s = math.sin(math.radians(tilt_deg))
    _y0 = base_d / 2 - back_h * _c
    _yb = _y0 - (device_t + slot_gap) / _s
    _d = (plate_t / 2) / _s
    _bb = (_yb - _d * _c, plate_t - _d * _s)
    _bf = (_bb[0] - plate_t * _s, _bb[1] + plate_t * _c)
    _tb = (_yb + lip_h * _c, plate_t + lip_h * _s)
    _tf = (_tb[0] - plate_t * _s, _tb[1] + plate_t * _c)
    _wire = scad.make_polyline_rwire(points=[(0, _bf[0], _bf[1]), (0, _tf[0], _tf[1]), (0, _tb[0], _tb[1]), (0, _bb[0], _bb[1])], closed=True)
    _face = scad.make_face_from_wire_rface(wire=_wire, normal=(-1, 0, 0))
    _lip = scad.extrude_rsolid(profile=_face, direction=(1, 0, 0), distance=(base_w - notch_w) / 2)
    _lip = scad.translate_shape(shape=_lip, vector=(notch_w / 2, 0, 0))
    lip_right = scad.union_rsolid(lip_left, _lip)
    return (lip_right,)


@app.cell
def _(lip_right):
    model = scad.Part(part_id="model", body=lip_right)
    return (model,)


if __name__ == "__main__":
    app.run()
