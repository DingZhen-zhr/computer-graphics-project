"""STL 导出探测（网页前端 Task 1）：export_product_package_to_stl 的参数、返回值、中文目录、精度选项。

只给开发时探测用。输出原样记进 docs/sca-api-notes.md 第 16 节。
"""

from __future__ import annotations

import os
import struct
import sys
import tempfile
from pathlib import Path

from simplecadapi import exporter

import simplecadapi as scad
from simplecadapi.runtime import run_notebook

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from cad_agent.brief import Param  # noqa: E402
from cad_agent.notebook import Feature, render_notebook  # noqa: E402


def say(tag: str, msg: object) -> None:
    print(f"[{tag}] {msg}", flush=True)


def triangles(path: Path) -> int:
    data = path.read_bytes()
    return struct.unpack("<I", data[80:84])[0]


def main() -> None:
    os.chdir(tempfile.mkdtemp(prefix="stl-probe-cwd-"))   # SCA 会往当前目录写东西
    params = [Param("w", 60, "mm", "user"), Param("hole_d", 10, "mm", "user")]
    features = [
        Feature("plate", "build", "plate = scad.make_box_rsolid(width=w, height=40, depth=8, bottom_face_center=(0, 0, 0))"),
        Feature("hole", "subtract",
                "_t = scad.make_cylinder_rsolid(radius=hole_d / 2, height=10, bottom_face_center=(0, 0, -1))\n"
                "hole = scad.cut_rsolid(plate, _t, skip_non_intersecting=False)"),
    ]
    rendered = render_notebook(params, features)
    root = Path(tempfile.mkdtemp(prefix="stl-probe-"))
    nb = root / "model.py"
    nb.write_text(rendered.text, encoding="utf-8")
    run = run_notebook(str(nb), cache=False, timeout=60)
    cap = scad.capture(run.definition, root / "model.scadpkg")
    say("capture", type(cap.package).__name__)

    # 1. 默认参数
    out = root / "default.stl"
    report = exporter.export_product_package_to_stl(cap.package, out)
    say("默认参数", f"返回 {type(report).__name__}: {report}")
    say("默认参数", f"文件 {out.stat().st_size} 字节，三角形 {triangles(out)}，前 5 字节 {out.read_bytes()[:5]!r}")

    # 2. 直接传 .scadpkg 路径
    out2 = root / "from_path.stl"
    exporter.export_product_package_to_stl(root / "model.scadpkg", out2)
    say("传 .scadpkg 路径", f"文件 {out2.stat().st_size} 字节，三角形 {triangles(out2)}")

    # 3. 精度选项
    for lin, ang in ((0.5, 30.0), (0.1, 20.0), (0.02, 10.0)):
        o = root / f"lin{lin}.stl"
        exporter.export_product_package_to_stl(cap.package, o, linear_deflection=lin, angular_deflection_degrees=ang)
        say("精度", f"linear_deflection={lin}, angular={ang}: {o.stat().st_size} 字节，三角形 {triangles(o)}")
    o = root / "relative.stl"
    exporter.export_product_package_to_stl(cap.package, o, relative=True)
    say("relative=True", f"{o.stat().st_size} 字节，三角形 {triangles(o)}")

    # 4. 中文目录
    cn = root / "中文目录"
    cn.mkdir()
    o = cn / "model.stl"
    exporter.export_product_package_to_stl(cap.package, o)
    say("中文目录", f"写进 {o.parent.name}：{o.stat().st_size} 字节")

    # 5. 坐标范围（z 朝上、底面贴 z=0）：读出所有顶点
    data = default_vertices(out)
    xs, ys, zs = zip(*data)
    say("顶点范围", f"x [{min(xs):.3f}, {max(xs):.3f}] y [{min(ys):.3f}, {max(ys):.3f}] z [{min(zs):.3f}, {max(zs):.3f}]")


def default_vertices(path: Path) -> list[tuple[float, float, float]]:
    data = path.read_bytes()
    n = struct.unpack("<I", data[80:84])[0]
    verts = []
    for i in range(n):
        base = 84 + i * 50
        vals = struct.unpack("<12fH", data[base:base + 50])
        verts += [vals[3:6], vals[6:9], vals[9:12]]
    return verts


if __name__ == "__main__":
    main()
