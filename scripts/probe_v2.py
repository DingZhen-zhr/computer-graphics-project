"""第二版（卡尺）计划 1 Task 1 的 SCA 探测。

只给开发时探测用，输出追加进 docs/sca-probe-output.txt，结论写进 docs/sca-api-notes.md 第 17–22 节。
每个实验单独 try/except，出错记下异常类型和前 300 个字符后继续。
"""

from __future__ import annotations

import math
import os
import sys
import tempfile
import time
import traceback
import linecache
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from probe_common import HEADER, facts, new_tmp, say  # noqa: E402


def attempt(tag: str, fn) -> object:
    try:
        return fn()
    except Exception as e:  # noqa: BLE001 - 探测脚本要记录任何异常后继续
        say(tag, f"异常 {type(e).__name__}: {str(e).replace(chr(10), ' | ')[:300]}")
        return None


def run_text(text: str, timeout: float = 60):
    from simplecadapi.runtime import run_notebook

    d = new_tmp("cad-probe2-")
    (d / "model.py").write_text(text, encoding="utf-8")
    old = os.getcwd()
    os.chdir(d)  # probe 单元把 probe_out.txt 写在当前目录（沙盒里当前目录就是临时工作目录）
    try:
        return d, run_notebook(d / "model.py", cache=False, timeout=timeout)
    finally:
        os.chdir(old)


PARAMS_CELL = '''
@app.cell
def _():
    # ---- params ----
    phone_w = scad.var("phone_w", 78, unit="mm")
    n = 3
    return n, phone_w
'''

BOX_CELL = '''
@app.cell
def _(phone_w):
    # ---- feature: base (build) ----
    base = scad.make_box_rsolid(width=phone_w, height=40, depth=8, bottom_face_center=(0, 0, 0))
    return (base,)
'''


def probe_cell(inputs: list[str], body: list[str], model_arg: str) -> str:
    code = "\n".join("        " + ln for ln in body)
    return f'''
@app.cell
def _({", ".join(inputs)}):
    # ---- probe ----
    import contextlib as _ctx
    import io as _io
    def _probe(model):
{code}
    _buf = _io.StringIO()
    try:
        with _ctx.redirect_stdout(_buf):
            _probe({model_arg})
    finally:
        with open("probe_out.txt", "w", encoding="utf-8") as _f:
            _f.write(_buf.getvalue())
    return ()
'''


def product_cell(var: str) -> str:
    return f'''
@app.cell
def _({var}):
    model = scad.Part(part_id="model", body={var})
    return (model,)
'''


# ---------------------------------------------------------------- 实验 1：probe 单元


def exp1() -> None:
    body = [
        "print('phone_w =', float(phone_w))",
        "print('model type', type(model).__name__)",
        "print('n =', n)",
    ]
    text = HEADER + PARAMS_CELL + BOX_CELL + probe_cell(["base", "n", "phone_w"], body, "base") + product_cell("base")
    d, run = run_text(text)
    out = (d / "probe_out.txt").read_text(encoding="utf-8") if (d / "probe_out.txt").exists() else None
    say("1 probe 正常", f"cells={[c.status for c in run.cells.values()] if hasattr(run.cells, 'values') else run.cells}")
    say("1 probe 正常", f"probe_out.txt 内容={out!r}")
    say("1 probe 正常", f"产品体积={facts(run.product.body)['volume']}")



def exp1b() -> None:
    # 笔记第 4 节的 brep 检视函数在 notebook 里能不能用
    body2 = [
        "_bb = scad.inspect.brep.inspect_shape_rbrepinspection(model.wrapped).bounding_box",
        "print('size', [round(_bb[i + 3] - _bb[i], 4) for i in range(3)])",
    ]
    text2 = HEADER + PARAMS_CELL + BOX_CELL + probe_cell(["base"], body2, "base") + product_cell("base")
    run_text(text2)


def exp1c() -> None:
    # 在 notebook 里能用的写法：体积用 get_volume()，包围盒用全部顶点的坐标
    body2 = [
        "print('volume', round(model.get_volume(), 4))",
        "_pts = [v.get_center() for v in ql.vertices().resolve(model)]",
        "_xs, _ys, _zs = [p.x for p in _pts], [p.y for p in _pts], [p.z for p in _pts]",
        "print('size', round(max(_xs) - min(_xs), 4), round(max(_ys) - min(_ys), 4), round(max(_zs) - min(_zs), 4))",
        "print('faces', len(ql.faces().resolve(model)), 'edges', len(ql.edges().resolve(model)))",
    ]
    text2 = HEADER + PARAMS_CELL + BOX_CELL + probe_cell(["base"], body2, "base") + product_cell("base")
    d2, _ = run_text(text2)
    say("1 probe 包围盒（顶点）", f"{(d2 / 'probe_out.txt').read_text(encoding='utf-8')!r}")


def exp1d() -> None:
    # probe 里抛异常：文件里仍有之前打印的内容；记下 traceback 里 probe 单元的帧
    body3 = ["print('到这里')", "print(undefined_name)"]
    text3 = HEADER + PARAMS_CELL + BOX_CELL + probe_cell(["base"], body3, "base") + product_cell("base")
    d3 = None
    try:
        d3, _ = run_text(text3)
        say("1 probe 出错", "没有抛异常（不符合预期）")
    except Exception as e:  # noqa: BLE001
        say("1 probe 出错", f"异常 {type(e).__name__}: {str(e)[:200]}")
        for f in traceback.extract_tb(e.__traceback__):
            if "__marimo__cell_" in f.filename:
                first = "".join(linecache.getlines(f.filename)[:2]).replace("\n", " ⏎ ")
                say("1 probe 出错帧", f"文件名含 __marimo__cell_，行号={f.lineno}，函数={f.name}，源码前两行={first!r}")
        found = sorted(new_tmp_root().glob("cad-probe2-*/probe_out.txt"), key=lambda p: p.stat().st_mtime)
        if found:
            say("1 probe 出错", f"最新的 probe_out.txt 内容={found[-1].read_text(encoding='utf-8')!r}")


def new_tmp_root() -> Path:
    return Path(tempfile.gettempdir())


# ---------------------------------------------------------------- 实验 2：没有特征时的占位


def exp2() -> None:
    placeholder = '''
@app.cell
def _():
    placeholder_body = scad.make_box_rsolid(width=1, height=1, depth=1, bottom_face_center=(0, 0, 0))
    return (placeholder_body,)
'''
    body = ["print(model is None)", "print(float(phone_w))"]
    text = HEADER + PARAMS_CELL + placeholder + probe_cell(["phone_w"], body, "None") + product_cell("placeholder_body")
    d, run = run_text(text)
    say("2 占位产品", f"运行成功，probe_out.txt={(d / 'probe_out.txt').read_text(encoding='utf-8')!r}，产品={facts(run.product.body)['bbox']}")


# ---------------------------------------------------------------- 实验 3：一次运行取各阶段末尾的实体


def exp3() -> None:
    hole = '''
@app.cell
def _(base):
    # ---- feature: hole (subtract) ----
    _t = scad.make_cylinder_rsolid(radius=5, height=10, bottom_face_center=(0, 0, -1))
    hole = scad.cut_rsolid(base, _t, skip_non_intersecting=False)
    return (hole,)
'''
    text = HEADER + PARAMS_CELL + BOX_CELL + hole + product_cell("hole")
    _, run = run_text(text)
    keys = sorted(run.values.keys()) if hasattr(run.values, "keys") else run.values
    say("3 中间实体", f"run.values 的键={keys}")
    for name in ("base", "hole"):
        if hasattr(run.values, "keys") and name in run.values:
            v = run.values[name]
            say("3 中间实体", f"run.values[{name!r}] 类型={type(v).__name__}，facts={facts(v)['bbox']}，体积={facts(v)['volume']}")


# ---------------------------------------------------------------- 实验 4~8：建模写法（在 notebook 里用 Var 参数跑）


def run_feature(tag: str, params: str, code: str, var: str) -> dict | None:
    sig = sorted(ln.split("=")[0].strip() for ln in params.strip().splitlines())  # 参数单元里的全部名字都作为输入
    cell = f'''
@app.cell
def _({", ".join(sig)}):
    # ---- feature: {var.replace("_", "-")} (build) ----
{chr(10).join("    " + ln for ln in code.strip().splitlines())}
    return ({var},)
'''
    pc = f'''
@app.cell
def _():
    # ---- params ----
{chr(10).join("    " + ln for ln in params.strip().splitlines())}
    return {", ".join(sig) if sig else "()"}{"," if len(sig) == 1 else ""}
'''
    started = time.monotonic()
    _, run = run_text(HEADER + pc + cell + product_cell(var))
    f = facts(run.product.body)
    say(tag, f"{f}，用时 {time.monotonic() - started:.1f} 秒")
    return f


def exp4() -> None:
    params = 'l = scad.var("l", 120, unit="mm")\nt = scad.var("t", 8, unit="mm")\nh = scad.var("h", 60, unit="mm")\nw = scad.var("w", 30, unit="mm")'
    code = '''
_s = scad.make_sketch_rsketch("l_profile", plane="XZ")
_pts = [(-l / 2, 0), (l / 2, 0), (l / 2, t), (-l / 2 + 20, t), (-l / 2 + 20, h), (-l / 2, h)]
for _i, (_u, _v) in enumerate(_pts):
    _s = scad.add_point_rsketch(_s, f"p{_i}", _u, _v)
for _i in range(6):
    _s = scad.add_line_rsketch(_s, f"e{_i}", f"p{_i}", f"p{(_i + 1) % 6}")
_face = scad.make_face_from_sketch_rface(_s)
_solid = scad.extrude_rsolid(profile=_face, direction=(0, 1, 0), distance=w)
lsk = scad.translate_shape(shape=_solid, vector=(0, -w / 2, 0))
'''
    attempt("4 草图 L 形（XZ 平面，Var 坐标）", lambda: run_feature("4 草图 L 形（XZ 平面，Var 坐标）", params, code, "lsk"))
    # 求解状态
    import simplecadapi as scad

    s = scad.make_sketch_rsketch("l_profile", plane="XZ")
    for i, (u, v) in enumerate([(-60, 0), (60, 0), (60, 8), (-40, 8), (-40, 60), (-60, 60)]):
        s = scad.add_point_rsketch(s, f"p{i}", u, v)
    for i in range(6):
        s = scad.add_line_rsketch(s, f"e{i}", f"p{i}", f"p{(i + 1) % 6}")
    r = scad.inspect_sketch_rsketchresult(s)
    say("4 求解状态", f"status={r.status} dof={r.dof} residual={r.residual_norm}")
    face = scad.make_face_from_sketch_rface(s)
    say("4 面的法向", f"XZ 平面草图的面法向={face.get_normal_at().to_tuple()}（局部 u→x、v→z）")
    for d in ((0, 1, 0), (0, 0, 1)):
        solid = scad.extrude_rsolid(profile=face, direction=d, distance=30)
        say("4 拉伸方向", f"direction={d}: {facts(solid)['bbox']} 体积={facts(solid)['volume']} valid={facts(solid)['valid']}")
    # 圆弧：add_arc_rsketch(sketch, id, start, end, center)，按正方向（逆时针）从 start 扫到 end
    s2 = scad.make_sketch_rsketch("d_profile", plane="XY")
    for pid, (x, y) in {"a": (-20, -10), "b": (20, -10), "c": (20, 10), "d": (-20, 10), "o": (20, 0)}.items():
        s2 = scad.add_point_rsketch(s2, pid, x, y)
    s2 = scad.add_line_rsketch(s2, "ab", "a", "b")
    s2 = attempt("4 圆弧", lambda: scad.add_arc_rsketch(s2, "bc", "b", "c", "o"))
    if s2 is not None:
        s2 = scad.add_line_rsketch(s2, "cd", "c", "d")
        s2 = scad.add_line_rsketch(s2, "da", "d", "a")
        solid = scad.extrude_rsolid(profile=scad.make_face_from_sketch_rface(s2), direction=(0, 0, 1), distance=5)
        f = facts(solid)
        say("4 圆弧", f"直线 + 半圆（圆心 (20,0)，从 (20,-10) 逆时针到 (20,10)）：{f['bbox']} 体积={f['volume']}（期望 {(40 * 20 + math.pi * 100 / 2) * 5:.4f}）")


def exp5() -> None:
    params = 'l = scad.var("l", 80, unit="mm")\nw = scad.var("w", 50, unit="mm")\nh = scad.var("h", 30, unit="mm")\nwall = scad.var("wall", 2, unit="mm")'
    shell = '''
_box = scad.make_box_rsolid(width=l, height=w, depth=h, bottom_face_center=(0, 0, 0))
_top = ql.faces().where(ql.and_(ql.prop("geom.type", "==", "PLANE"), ql.prop("geom.normal.z", ">=", 0.99)))
tray = scad.shell_rsolid(solid=_box, faces_to_remove=_top, thickness=wall)
'''
    attempt("5 抽壳 shell_rsolid", lambda: run_feature("5 抽壳 shell_rsolid", params, shell, "tray"))
    cut = '''
_box = scad.make_box_rsolid(width=l, height=w, depth=h, bottom_face_center=(0, 0, 0))
_cavity = scad.make_box_rsolid(width=l - 2 * wall, height=w - 2 * wall, depth=h, bottom_face_center=(0, 0, wall))
tray = scad.cut_rsolid(_box, _cavity, skip_non_intersecting=False)
'''
    attempt("5 外形减内腔", lambda: run_feature("5 外形减内腔", params, cut, "tray"))
    say("5 期望体积", f"{80 * 50 * 30 - 76 * 46 * 28}")
    neg = shell.replace("thickness=wall", "thickness=-wall")
    attempt("5 抽壳负厚度", lambda: run_feature("5 抽壳负厚度", params, neg, "tray"))
    # 先圆角再抽壳
    fil = '''
_box = scad.make_box_rsolid(width=l, height=w, depth=h, bottom_face_center=(0, 0, 0))
_vert = ql.edges().where(ql.and_(ql.prop("geom.type", "==", "LINE"), ql.prop("geom.center.z", ">=", h / 2 - 0.1), ql.prop("geom.center.z", "<=", h / 2 + 0.1)))
_round = scad.fillet_rsolid(solid=_box, edges=_vert, radius=6)
_top = ql.faces().where(ql.and_(ql.prop("geom.type", "==", "PLANE"), ql.prop("geom.normal.z", ">=", 0.99)))
tray = scad.shell_rsolid(solid=_round, faces_to_remove=_top, thickness=wall)
'''
    attempt("5 先圆角再抽壳", lambda: run_feature("5 先圆角再抽壳", params, fil, "tray"))
    # 实验 8：沉头孔
    cs = '''
_plate = scad.make_box_rsolid(width=l, height=w, depth=wall * 4, bottom_face_center=(0, 0, 0))
_hole = scad.make_cylinder_rsolid(radius=2.5, height=wall * 4 + 2, bottom_face_center=(0, 0, -1))
_cb = scad.make_cylinder_rsolid(radius=5, height=3 + 1, bottom_face_center=(0, 0, wall * 4 - 3))
tray = scad.cut_rsolid(_plate, _hole, _cb, skip_non_intersecting=False)
'''
    f = attempt("8 沉头孔", lambda: run_feature("8 沉头孔（通孔 φ5 + 沉头 φ10 深 3，板厚 8）", params, cs, "tray"))
    if f:
        say("8 期望体积", f"{80 * 50 * 8 - math.pi * 2.5 ** 2 * 5 - math.pi * 5 ** 2 * 3:.4f}")


def exp6() -> None:
    params = 'r = scad.var("r", 4, unit="mm")\nh = scad.var("h", 30, unit="mm")\nl = scad.var("l", 40, unit="mm")'
    code = '''
_c = math.cos(math.radians(45))
_e1 = scad.make_segment_redge(start=(0, 0, 0), end=(0, 0, h))
_e2 = scad.make_three_point_arc_redge(start=(0, 0, h), middle=(10 - 10 * _c, 0, h + 10 * _c), end=(10, 0, h + 10))
_e3 = scad.make_segment_redge(start=(10, 0, h + 10), end=(10 + l, 0, h + 10))
_path = scad.make_wire_from_edges_rwire(edges=[_e1, _e2, _e3])
_profile = scad.make_circle_rface(center=(0, 0, 0), radius=r, normal=(0, 0, 1))
pipe = scad.sweep_rsolid(profile=_profile, path=_path)
'''
    attempt("6 扫掠（直线-圆弧-直线）", lambda: run_feature("6 扫掠（直线-圆弧-直线）", params, code, "pipe"))
    say("6 期望体积", f"{math.pi * 16 * (30 + 40 + 10 * math.pi / 2):.4f}")
    poly = '''
_path = scad.make_polyline_rwire(points=[(0, 0, 0), (0, 0, h), (l, 0, h)])
_profile = scad.make_circle_rface(center=(0, 0, 0), radius=r, normal=(0, 0, 1))
pipe = scad.sweep_rsolid(profile=_profile, path=_path)
'''
    attempt("6 扫掠（折线，没有圆弧）", lambda: run_feature("6 扫掠（折线，没有圆弧）", params, poly, "pipe"))


def exp7() -> None:
    params = 'm = 2\nz = 30\ngw = scad.var("gw", 12, unit="mm")\nr = scad.var("r", 12, unit="mm")'
    gear = "gear = scad.std.gear.make_spur_gear_rsolid(n_teeth=z, module=m, gear_height=gw)"
    attempt("7 齿轮", lambda: run_feature("7 齿轮 m=2 z=30 齿宽 12", params, gear, "gear"))
    union = '''
_g = scad.std.gear.make_spur_gear_rsolid(n_teeth=z, module=m, gear_height=gw)
_hub = scad.make_cylinder_rsolid(radius=r, height=gw + 8, bottom_face_center=(0, 0, 0))
_bore = scad.make_cylinder_rsolid(radius=5, height=gw + 10, bottom_face_center=(0, 0, -1))
gear = scad.cut_rsolid(scad.union_rsolid(_g, _hub), _bore, skip_non_intersecting=False)
'''
    attempt("7 齿轮 + 轮毂 - 轴孔", lambda: run_feature("7 齿轮 + 轮毂 - 轴孔", params, union, "gear"))
    import simplecadapi as scad
    from OCP.BRepClass3d import BRepClass3d_SolidClassifier
    from OCP.gp import gp_Pnt

    g = scad.std.gear.make_spur_gear_rsolid(n_teeth=30, module=2, gear_height=12)
    states = {x: str(BRepClass3d_SolidClassifier(g.wrapped, gp_Pnt(x, 0, 6), 1e-6).State()).split(".")[-1] for x in (26.0, 29.0, 31.9, 32.1)}
    say("7 齿轮轴线与齿位", f"(x, 0, 6) 的点分类={states}（+x 方向正对一个齿）")
    # 齿条
    for kw in ({"module": 2, "n_teeth": 10}, {"module": 2, "n_teeth": 10, "rack_height": 10}):
        rack = scad.std.gear.make_spur_rack_rsolid(**kw)
        say("7 齿条", f"{kw}: {facts(rack)}")
    rack = scad.std.gear.make_spur_rack_rsolid(module=2, n_teeth=10, rack_height=10)
    h = scad.make_cylinder_rsolid(radius=1, height=20, bottom_face_center=(0, 0, -5))
    say("7 齿条减孔", f"{facts(scad.cut_rsolid(rack, h))}")
    say("7 齿条并料", "union_rsolid(齿条, 方块) 在 60 秒内没有返回（在单独的进程里试过两次，glue=True 也一样），这里不再运行")


# ---------------------------------------------------------------- 实验 9：多视角渲染


def exp9() -> None:
    import simplecadapi as scad

    # 不对称的块：+x、+y 角上有一根立柱，用来认方向
    body = scad.union_rsolid(
        scad.make_box_rsolid(width=60, height=30, depth=10, bottom_face_center=(0, 0, 0)),
        scad.make_box_rsolid(width=10, height=10, depth=30, bottom_face_center=(25, 10, 0)),
    )
    out = new_tmp("cad-probe2-views-")
    for name, view in (("iso", "iso"), ("front", (0, -90)), ("top", (90, 0)), ("right", (0, 0)),
                       ("preset-front", "front"), ("preset-top", "top"), ("preset-right", "right")):
        p = out / f"{name}.png"
        started = time.monotonic()
        attempt(f"9 渲染 {name}", lambda: scad.render_screenshot_rpath(body, str(p), view=view, image_size=(500, 400)))
        say(f"9 渲染 {name}", f"view={view!r} 文件={p.exists()} 大小={p.stat().st_size if p.exists() else 0} 用时 {time.monotonic() - started:.1f} 秒")
    say("9 渲染目录", str(out))


def main() -> None:
    os.chdir(tempfile.mkdtemp(prefix="cad-probe2-cwd-"))  # SCA 会往当前目录写诊断图
    for name, fn in (("probe 单元", exp1), ("probe 里用 brep", exp1b), ("probe 里量尺寸", exp1c), ("probe 出错", exp1d), ("占位产品", exp2), ("各阶段实体", exp3), ("草图", exp4), ("抽壳与沉头孔", exp5),
                     ("扫掠", exp6), ("标准件", exp7), ("多视角渲染", exp9)):
        print(f"\n==== {name} ====", flush=True)
        attempt(name, fn)


if __name__ == "__main__":
    main()
