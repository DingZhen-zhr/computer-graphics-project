"""render_notebook 的 probe 单元（第二版计划 1 Task 5，不需要 SCA）。"""

import ast
import re

import pytest

from cad_agent.brief import Param
from cad_agent.notebook import Feature, NotebookError, render_notebook

P = [Param("phone_w", 78, "mm", "user"), Param("n", 3, "1", "user")]
F = [
    Feature("base", "build", "base = scad.make_box_rsolid(width=phone_w, height=40, depth=8, bottom_face_center=(0, 0, 0))", "s1"),
    Feature("hole", "subtract", "_t = scad.make_cylinder_rsolid(radius=5, height=10, bottom_face_center=(0, 0, -1))\nhole = scad.cut_rsolid(base, _t)", "s1"),
]


def cells(text: str) -> list[str]:
    """notebook 文字按 @app.cell 切开（第一段是文件头）。"""
    return text.split("@app.cell\n")


def test_no_probe_output_is_unchanged():
    a, b = render_notebook(P, F), render_notebook(P, F, None)
    assert a.text == b.text and a.cell_lines == b.cell_lines
    assert "# ---- probe ----" not in a.text


def test_probe_cell_reads_params_and_features():
    plain = render_notebook(P, F)
    r = render_notebook(P, F, probe="print(phone_w)\nprint(base.get_volume(), model)")
    parts = cells(r.text)
    probe_idx = next(i for i, c in enumerate(parts) if "# ---- probe ----" in c)
    hole_idx = next(i for i, c in enumerate(parts) if "# ---- feature: hole" in c)
    product_idx = next(i for i, c in enumerate(parts) if 'scad.Part(part_id="model"' in c)
    assert hole_idx < probe_idx < product_idx and probe_idx == hole_idx + 1
    sig = re.match(r"def _\((.*)\):", parts[probe_idx]).group(1).split(", ")
    assert "phone_w" in sig and "base" in sig and "hole" in sig      # 读到的名字和最后一个特征
    assert "model" not in sig and "n" not in sig
    assert "        print(phone_w)" in parts[probe_idx]                 # probe 代码整体缩进一层，放在 _probe 里
    assert "            _probe(hole)" in parts[probe_idx]
    assert r.cell_lines == plain.cell_lines                              # cell_lines 里没有多出条目
    ast.parse(r.text)


def test_probe_cell_shape_matches_the_plan():
    r = render_notebook(P, F, probe="print(1)")
    probe = next(c for c in cells(r.text) if "# ---- probe ----" in c)
    lines = probe.splitlines()
    assert lines[1:5] == ["    # ---- probe ----", "    import contextlib as _ctx", "    import io as _io", "    def _probe(model):"]
    assert lines[5] == "        print(1)"
    assert lines[6:] == [
        "    _buf = _io.StringIO()", "    try:", "        with _ctx.redirect_stdout(_buf):", "            _probe(hole)", "    finally:",
        '        with open("probe_out.txt", "w", encoding="utf-8") as _f:', "            _f.write(_buf.getvalue())", "    return ()", "", "",
    ]


def test_probe_assignments_do_not_leak():
    r = render_notebook(P, F, probe="x = 1\nprint(x + phone_w)")
    for c in cells(r.text)[1:]:
        ret = [ln for ln in c.splitlines() if ln.strip().startswith("return")]
        assert all("x" not in re.findall(r"\b\w+\b", ln) for ln in ret), c
    ast.parse(r.text)


def test_probe_without_features_uses_placeholder():
    r = render_notebook(P, [], probe="print(model is None)")
    parts = cells(r.text)
    ph = next(i for i, c in enumerate(parts) if "placeholder_body = scad.make_box_rsolid(width=1, height=1, depth=1, bottom_face_center=(0, 0, 0))" in c)
    probe = next(i for i, c in enumerate(parts) if "# ---- probe ----" in c)
    product = next(i for i, c in enumerate(parts) if 'scad.Part(part_id="model", body=placeholder_body)' in c)
    assert ph + 1 == probe and probe + 1 == product
    assert "            _probe(None)" in parts[probe]
    assert r.cell_lines == {}
    ast.parse(r.text)


def test_no_features_and_no_probe_still_raises():
    with pytest.raises(NotebookError):
        render_notebook(P, [])
    with pytest.raises(NotebookError):
        render_notebook(P, [], None)
