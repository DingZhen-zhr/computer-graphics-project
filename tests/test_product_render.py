"""3.0 计划 2 Task 5：零件 notebook 带编号和材料，生成装配 notebook。"""

from __future__ import annotations

import ast
import json
import os
from pathlib import Path

import pytest

from cad_agent.brief import Brief, Param
from cad_agent.notebook import Feature, FeatureList, render_notebook
from cad_agent.product.render import render_assembly_notebook, render_part_notebook
from cad_agent.product.workspace import ensure_parts, select_part
from cad_agent.tools import Workspace

GOLDEN = Path(__file__).parent / "data" / "notebook_v2_golden.json"
I4 = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]


def test_default_render_is_unchanged():
    """对照样本是用改动前的 notebook.py 生成的（四组第二版测试里的参数和特征）。"""
    for case in json.loads(GOLDEN.read_text(encoding="utf-8")):
        params = [Param(**p) for p in case["params"]]
        feats = [Feature(**f) for f in case["features"]]
        assert render_notebook(params, feats, case["probe"]).text == case["text"]


def _ws() -> Workspace:
    b = Brief()
    b.apply_patch({"part": {"name": "盒子"},
                   "parts": [{"id": "body", "name": "盒体", "material": "abs", "features": ["盒体"]},
                             {"id": "lid", "name": "盖子", "material": "anodized", "color": "#FF8000", "features": ["盖板"]}],
                   "set_params": [{"name": "w", "value": 40, "unit": "mm", "source": "user", "note": ""},
                                  {"name": "n", "value": 2, "unit": "1", "source": "user", "note": ""},
                                  {"name": "body_h", "value": 10, "unit": "mm", "source": "user", "note": "", "part": "body"},
                                  {"name": "lid_t", "value": 4, "unit": "mm", "source": "user", "note": "", "part": "lid"}]})
    ws = Workspace(b, FeatureList(), [])
    ensure_parts(ws)
    ws.features.upsert(Feature("shell", "build", "shell = scad.make_box_rsolid(width=w, height=w, depth=body_h, bottom_face_center=(0, 0, 0))", "s1"))
    select_part(ws, "lid")
    ws.features.upsert(Feature("plate", "build", "plate = scad.make_box_rsolid(width=w, height=w, depth=lid_t, bottom_face_center=(0, 0, 0))", "s1"))
    return ws


def test_part_notebook_uses_part_id_and_params():
    ws = _ws()
    text = render_part_notebook(ws, "body").text
    assert 'id = "body"' in text and 'scad.make_part_rpart("body", shell)' in text
    assert 'body_h = scad.var("body_h", 10, unit="mm")' in text and "lid_t" not in text and "n = 2" in text
    lid = render_part_notebook(ws, "lid").text
    assert 'id = "lid"' in lid and "plate" in lid and "body_h" not in lid


def test_part_notebook_has_material_color():
    ws = _ws()
    assert 'scad.make_material_rmaterial("abs", name="abs", color=(0.227, 0.247, 0.278))' in render_part_notebook(ws, "body").text
    # 需求单里写了颜色就用写的颜色
    assert 'scad.make_material_rmaterial("anodized", name="anodized", color=(1, 0.502, 0))' in render_part_notebook(ws, "lid").text


def _rot_x90(tz: float) -> list[float]:
    return [1, 0, 0, 0, 0, 0, -1, 0, 0, 1, 0, tz, 0, 0, 0, 1]


def test_assembly_notebook_uses_all_parts_and_placements():
    text = render_assembly_notebook(_ws(), {"body": I4, "lid": _rot_x90(10)})
    assert 'id = "product"' in text
    assert '_body = scad.use("parts/body/model.py", w=w, n=n, body_h=body_h)' in text
    assert '_a = scad.add_component_rassembly(_a, _body, "body", scad.make_placement_rplacement((0, 0, 0), x_axis=(1, 0, 0), y_axis=(0, 1, 0)))' in text
    assert 'scad.make_placement_rplacement((0, 0, 10), x_axis=(1, 0, 0), y_axis=(0, 0, 1))' in text
    assert "product = _a" in text


def test_assembly_notebook_passes_whole_param_cell():
    text = render_assembly_notebook(_ws(), {"body": I4, "lid": I4})
    assert 'scad.use("parts/lid/model.py", w=w, n=n, lid_t=lid_t)' in text
    for name in ("w", "n", "body_h", "lid_t"):
        assert f"    {name} = " in text


def test_rendered_notebooks_parse():
    ws = _ws()
    for pid in ("body", "lid"):
        ast.parse(render_part_notebook(ws, pid).text)
    ast.parse(render_assembly_notebook(ws, {"body": I4, "lid": _rot_x90(10)}))


@pytest.mark.sca
def test_assembly_notebook_runs(tmp_path):
    from simplecadapi.runtime import run_notebook

    ws = _ws()
    for pid in ("body", "lid"):
        d = tmp_path / "parts" / pid
        d.mkdir(parents=True)
        (d / "model.py").write_text(render_part_notebook(ws, pid).text, encoding="utf-8")
    (tmp_path / "product.py").write_text(render_assembly_notebook(ws, {"body": I4, "lid": _rot_x90(10)}), encoding="utf-8")
    old = os.getcwd()
    os.chdir(tmp_path)
    try:
        run = run_notebook(tmp_path / "product.py", cache=False, timeout=120)
    finally:
        os.chdir(old)
    assert type(run.product).__name__ == "Assembly"
    assert [c.component_id for c in run.product.components] == ["body", "lid"]
