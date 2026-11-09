"""SCA 2.2.7 摸底脚本（Task 1）。

在英文临时目录里逐项实测，每项打印 `[项目] 结果`。
用法：.venv\\Scripts\\python scripts\\probe_sca.py
第 14、15 项（速查表条目和常见报错）在 probe_sca_cheatsheet.py 里。
"""

from __future__ import annotations

import math
import os
import shutil
import sys
from pathlib import Path

import simplecadapi as scad
from simplecadapi import exporter, ql

import traceback

from probe_common import Cell, build_nb, facts, new_tmp, run_nb, say, tb_frames, try_run

PARAMS = [("w", 60, "mm"), ("h", 36, "mm"), ("t", 8, "mm"), ("r", 5, "mm"), ("a", 30, "deg")]
PLATE_CELLS = [
    Cell("plate", "build", ["h", "t", "w"],
         "plate = scad.make_box_rsolid(width=w, height=h, depth=t, bottom_face_center=(0, 0, 0))", ["plate"]),
    Cell("hole", "subtract", ["plate", "r", "t"],
         "_tool = scad.make_cylinder_rsolid(radius=r, height=t + 2, bottom_face_center=(0, 0, -1))\n"
         "hole = scad.cut_rsolid(plate, _tool)", ["hole"]),
]


def plate_run(workdir: Path | None = None):
    return run_nb(build_nb(PARAMS, PLATE_CELLS), workdir)


def item1_3_params_volume() -> None:
    run = plate_run()
    say("1 运行", f"product={type(run.product).__name__} cells={[c.status for c in run.cells]}")
    w, a = run.values["w"], run.values["a"]
    say("2 参数", f"type(w)={type(w).__name__} float(w)={float(w)} float(a)={float(a)} a.default={a.default}")
    say("2 参数", f"scad.var 的 unit 写法: unit='deg' 可用；a.evaluate()={a.evaluate()}")
    for bad_unit in ("degree", "degrees", "rad", "°"):
        try:
            v = scad.var("x", 1, unit=bad_unit)
            say("2 参数", f"unit={bad_unit!r} 可用, evaluate()={v.evaluate()}")
        except Exception as e:  # noqa: BLE001
            say("2 参数", f"unit={bad_unit!r} 异常 {type(e).__name__}")
    body = run.product.body
    expected = 60 * 36 * 8 - math.pi * 25 * 8
    say("3 体积", f"body.get_volume()={body.get_volume():.4f} 期望={expected:.4f}")
    return run


def item4_bbox(body) -> None:
    f = facts(body)
    say("4 包围盒", f"inspect_shape_rbrepinspection.bounding_box={f['bbox']} (xmin,ymin,zmin,xmax,ymax,zmax)")
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib

    bb = Bnd_Box()
    BRepBndLib.Add_s(body.wrapped, bb)
    say("4 包围盒", f"OCP Bnd_Box.Get()={tuple(round(v, 6) for v in bb.Get())} (带 1e-7 的缝隙)")
    say("4 包围盒", f"Solid 上有 bbox 方法吗: {[n for n in ('bounding_box', 'get_bounding_box', 'bbox') if hasattr(body, n)]}")


def item5_6_ql(body) -> None:
    cyl = ql.faces().where(ql.prop("geom.type", "==", "CYLINDER")).resolve(body)
    say("5 QL", f"CYLINDER 面数量={len(cyl)}")
    f = cyl[0]
    c = f.get_center()
    say("5 QL", f"面: get_center()={c.to_tuple()} get_area()={f.get_area():.4f} get_normal_at()={f.get_normal_at().to_tuple()}")
    top = ql.faces().where(ql.and_(ql.prop("geom.type", "==", "PLANE"), ql.prop("geom.normal.z", ">=", 0.99))).resolve(body)
    bot = ql.faces().where(ql.and_(ql.prop("geom.type", "==", "PLANE"), ql.prop("geom.normal.z", "<=", -0.99))).resolve(body)
    say("5 QL", f"顶面(normal.z>=0.99) {len(top)} 个, center.z={top[0].get_center().z:.3f}, normal={top[0].get_normal_at().to_tuple()}")
    say("5 QL", f"底面(normal.z<=-0.99) {len(bot)} 个, center.z={bot[0].get_center().z:.3f}, normal={bot[0].get_normal_at().to_tuple()}")
    allf = ql.faces().resolve(body)
    say("5 QL", f"全部面 {len(allf)} 个; geom.normal.z>=-1e9 命中 {len(ql.faces().where(ql.prop('geom.normal.z', '>=', -1e9)).resolve(body))} 个（圆柱面也有 normal，所以按法向选面必须同时限定 PLANE）")
    edges = ql.edges().resolve(body)
    kinds: dict[str, int] = {}
    for t in ("LINE", "CIRCLE", "ELLIPSE", "BSPLINE"):
        kinds[t] = len(ql.edges().where(ql.prop("geom.type", "==", t)).resolve(body))
    e0 = edges[0]
    say("5 QL", f"边: 共 {len(edges)} 条 {kinds}; get_length()={e0.get_length():.4f} get_center()={e0.get_center().to_tuple()}")
    circ = ql.edges().where(ql.prop("geom.type", "==", "CIRCLE")).resolve(body)
    say("5 QL", f"圆边长度={[round(e.get_length(), 4) for e in circ]} (2*pi*5={2 * math.pi * 5:.4f})")
    for path in ("geom.radius", "geom.diameter", "geom.axis.z"):
        n = len(ql.faces().where(ql.prop(path, ">=", -1e9)).resolve(body))
        say("6 属性", f"{path}: 命中 {n} 个面（0 表示这个属性不存在，查询不报错只是选不到）")
    for path in ("geom.area", "geom.center.x", "geom.normal.x"):
        n = len(ql.faces().where(ql.prop(path, ">=", -1e9)).resolve(body))
        say("6 属性", f"{path}: 命中 {n} 个面")
    n = len(ql.edges().where(ql.prop("geom.length", ">=", 0)).resolve(body))
    say("6 属性", f"geom.length (边): 命中 {n} 条边")


def item7_validity(body) -> None:
    from simplecadapi.inspect import brep

    i = brep.inspect_shape_rbrepinspection(body.wrapped)
    say("7 有效性", f"字段 valid={i.valid} counts={i.counts}")
    say("7 有效性", f"volume={i.volume:.4f} surface_area={i.surface_area:.4f} center_of_mass={i.center_of_mass}")
    say("7 有效性", f"surface_type_counts={i.surface_type_counts} edge_type_counts={i.edge_type_counts}")
    say("7 有效性", "实体个数取 counts['solid']；面数取 counts['unique_faces']；边数取 counts['unique_edges']")


def item_extra_points_distance(body) -> None:
    """Task 5 要用的：点在不在材料里、两组几何的最小距离、两平面法向夹角。"""
    from OCP.BRepClass3d import BRepClass3d_SolidClassifier
    from OCP.BRepExtrema import BRepExtrema_DistShapeShape
    from OCP.gp import gp_Pnt
    from OCP.TopAbs import TopAbs_IN, TopAbs_ON, TopAbs_OUT

    def state(x: float, y: float, z: float) -> str:
        c = BRepClass3d_SolidClassifier(body.wrapped, gp_Pnt(x, y, z), 1e-6)
        s = c.State()
        return {TopAbs_IN: "IN", TopAbs_OUT: "OUT", TopAbs_ON: "ON"}[s]

    say("附 点分类", f"(0,0,4) 孔中心 -> {state(0, 0, 4)}；(20,0,4) 板内 -> {state(20, 0, 4)}；(100,0,4) -> {state(100, 0, 4)}；(30,0,4) 侧面上 -> {state(30, 0, 4)}")
    cyl = ql.faces().where(ql.prop("geom.type", "==", "CYLINDER")).resolve(body)[0]
    side = ql.faces().where(ql.and_(ql.prop("geom.type", "==", "PLANE"), ql.prop("geom.normal.x", ">=", 0.99))).resolve(body)[0]
    d = BRepExtrema_DistShapeShape(cyl.wrapped, side.wrapped)
    d.Perform()
    say("附 距离", f"圆柱面到 +x 侧面: IsDone={d.IsDone()} Value()={d.Value():.6f} (期望 25)")
    top = ql.faces().where(ql.and_(ql.prop("geom.type", "==", "PLANE"), ql.prop("geom.normal.z", ">=", 0.99))).resolve(body)[0]
    n1, n2 = top.get_normal_at(), side.get_normal_at()
    dot = n1.x * n2.x + n1.y * n2.y + n1.z * n2.z
    say("附 夹角", f"顶面与 +x 侧面法向夹角 = {math.degrees(math.acos(max(-1, min(1, dot)))):.4f}° (期望 90)")


def item8_9_render_export(run, outdir: Path, tag_suffix: str = "") -> None:
    body = run.product.body
    png = outdir / "view.png"
    for view in ("iso", (30, 45), "auto"):
        p = outdir / f"view_{abs(hash(str(view))) % 10000}.png"
        r = try_run("8 截图" + tag_suffix, lambda v=view, p=p: scad.render_screenshot_rpath(body, str(p), view=v))
        if r is not None:
            say("8 截图" + tag_suffix, f"view={view!r} 成功, 返回值是路径字符串, 文件大小={p.stat().st_size}")
    r = try_run("8 截图" + tag_suffix, lambda: scad.render_screenshot_rpath(body, str(png), view="iso"))
    if r is not None:
        say("8 截图" + tag_suffix, f"用 view='iso' 输出 {png.name} 大小={png.stat().st_size}")
    pkg = outdir / "model.scadpkg"
    step = outdir / "model.step"

    def do_export():
        cap = scad.capture(run.definition, pkg)
        rep = exporter.export_product_package_to_step(cap.package, step)
        return rep

    rep = try_run("9 STEP" + tag_suffix, do_export)
    if rep is not None:
        say("9 STEP" + tag_suffix, f"capture(run.definition, pkg) + export_product_package_to_step(cap.package, step): 成功, STEP 大小={step.stat().st_size}, 报告类型={type(rep).__name__}")


def slug_of_failed_cell(exc: BaseException) -> tuple[str | None, str]:
    """从异常的 traceback 里找出出错的特征 slug。

    marimo 把每个 cell 编译成临时文件 __marimo__cell_xxx.py，行号是 cell 内部的行号；
    linecache 里能取到该 cell 的源码，其第 1 行就是 `# ---- feature: <slug> (<role>) ----`。
    """
    import linecache
    import re

    found: tuple[str | None, str] = (None, "")
    for f in traceback.extract_tb(exc.__traceback__):
        if "__marimo__cell_" in f.filename:
            src = "".join(linecache.getlines(f.filename)[:3])
            m = re.search(r"# ---- feature: ([a-z][a-z0-9-]*) \(", src)
            found = (m.group(1) if m else None, f"{Path(f.filename).name}:{f.lineno}")
    return found


def item10_traceback() -> None:
    cells = [
        Cell("plate", "build", ["h", "t", "w"],
             "plate = scad.make_box_rsolid(width=w, height=h, depth=t, bottom_face_center=(0, 0, 0))", ["plate"]),
        Cell("boom", "subtract", ["plate"], "_x = 1 / 0\nboom = plate", ["boom"]),
    ]
    text = build_nb(PARAMS, cells)
    try:
        run_nb(text, name="boom.py")
    except Exception as e:  # noqa: BLE001
        say("10 报错定位", f"异常 {type(e).__name__}: {str(e)[:200]}")
        for fn, ln, name in tb_frames(e):
            say("10 报错定位", f"帧: 文件={Path(fn).name} 行号={ln} 函数={name}")
        slug, where = slug_of_failed_cell(e)
        say("10 报错定位", f"按 __marimo__cell_ 帧 + linecache 找到的特征 slug={slug!r} 位置={where}（期望 'boom'）")
        say("10 报错定位", "结论：帧文件不是 notebook 本身，行号是 cell 内部行号，不能用 cell_lines 对照；要用 linecache 读 cell 源码里的特征注释")


def item11_12_paths() -> None:
    import simplecadapi

    root = Path(simplecadapi.__file__).parent / "skill" / "resources" / "docs" / "skill" / "references" / "docs"
    api = root / "api"
    say("11 文档位置", f"API 文档目录={api} 存在={api.is_dir()} md 文件数={len(list(api.glob('*.md')))}")
    say("11 文档位置", f"make_box_rsolid.md 存在={(api / 'make_box_rsolid.md').exists()}；其他目录: {[p.name for p in root.iterdir()]}")
    say("11 文档位置", f"ql 速查: {root.parent / 'ql-playbook.md'} 存在={(root.parent / 'ql-playbook.md').exists()}")
    say("12 sca 命令", f"shutil.which('sca')={shutil.which('sca')}")
    cand = Path(sys.executable).parent / ("sca.exe" if sys.platform == "win32" else "sca")
    say("12 sca 命令", f"与 python 同目录的 sca: {cand} 存在={cand.exists()}")


def item13_chinese_dir(run) -> None:
    base = new_tmp()
    cn = base / "中文目录"
    cn.mkdir()
    say("13 中文路径", f"目录={cn}")
    item8_9_render_export(run, cn, tag_suffix="(中文目录)")
    # 拆开测：文件名是中文 / 目录是中文，分别能不能运行 notebook
    en = new_tmp()
    for label, workdir, name in (("英文目录+中文文件名", en, "模型.py"), ("中文目录+英文文件名", cn, "model.py")):
        r = try_run("13 中文路径/运行 notebook " + label, lambda w=workdir, n=name: run_nb(build_nb(PARAMS, PLATE_CELLS), w, name=n))
        if r is not None:
            say("13 中文路径/运行 notebook " + label, "run_notebook 成功")


def main() -> None:
    os.chdir(new_tmp("cad-probe-cwd-"))  # SCA 会在当前目录写 .simplecad/diagnostics，所以不能在项目目录里跑
    say("环境", f"python={sys.version.split()[0]} simplecadapi={scad.__version__ if hasattr(scad, '__version__') else '?'}")
    run = item1_3_params_volume()
    body = run.product.body
    item4_bbox(body)
    item5_6_ql(body)
    item7_validity(body)
    item_extra_points_distance(body)
    out = new_tmp()
    item8_9_render_export(run, out)
    item10_traceback()
    item11_12_paths()
    item13_chinese_dir(run)
    from probe_sca_cheatsheet import main as cheat_main

    cheat_main()


if __name__ == "__main__":
    main()
