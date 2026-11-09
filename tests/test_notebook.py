import math

import pytest

from cad_agent.brief import Param
from cad_agent.notebook import (
    Feature,
    FeatureList,
    NotebookError,
    ROLES,
    RenderedNotebook,
    render_notebook,
)

P = [
    Param("base_l", 60, "mm", "user"),
    Param("hole_d", 10, "mm", "user"),
    Param("tilt_deg", 65, "deg", "user"),
    Param("bolt_n", 6, "1", "user"),
]
BASE = Feature("base", "build", "base = scad.make_box_rsolid(width=base_l, height=36, depth=8, bottom_face_center=(0, 0, 0))")
DRILL = Feature(
    "drill",
    "subtract",
    "_tool = scad.make_cylinder_rsolid(radius=hole_d / 2, height=10, bottom_face_center=(0, 0, -1))\n"
    "drill = scad.cut_rsolid(base, _tool)",
)
F = [BASE, DRILL]


def test_roles():
    assert ROLES == {"build", "add", "subtract", "intersect", "modify", "pattern"}


def test_header_and_setup():
    t = render_notebook(P, F).text
    for s in ['id = "model"', "import simplecadapi as scad", "from simplecadapi import ql", "import math"]:
        assert s in t


def test_params_cell_from_brief():
    t = render_notebook(P, F).text
    assert 'tilt_deg = scad.var("tilt_deg", 65, unit="deg")' in t
    assert 'base_l = scad.var("base_l", 60, unit="mm")' in t
    assert "bolt_n = 6\n" in t  # "1" 单位写成普通整数常量
    assert "scad.var(\"bolt_n\"" not in t


def test_params_non_integer_value_keeps_decimals():
    t = render_notebook([Param("hole_d", 6.6, "mm", "user")], F).text
    assert 'hole_d = scad.var("hole_d", 6.6, unit="mm")' in t


def test_inputs_inferred_and_sorted():
    t = render_notebook(P, F).text
    # base 用到 base_l；drill 用到 base、hole_d
    assert "def _(base_l):" in t
    assert "def _(base, hole_d):" in t
    assert "return (drill,)" in t


def test_product_cell_uses_last_feature():
    t = render_notebook(P, F).text
    assert 'model = scad.Part(part_id="model", body=drill)' in t
    assert "def _(drill):" in t


def test_feature_must_assign_own_var():
    bad = Feature("drill", "subtract", "_tool = scad.make_cylinder_rsolid(radius=3, height=5)")
    with pytest.raises(NotebookError, match="drill") as e:
        render_notebook(P, [BASE, bad])
    assert e.value.feature == "drill"


def test_forward_reference_rejected():
    a = Feature("a", "build", "a = scad.cut_rsolid(b, b)")
    b = Feature("b", "add", "b = scad.make_box_rsolid(width=base_l, height=1, depth=1)")
    with pytest.raises(NotebookError, match="b") as e:
        render_notebook(P, [a, b])
    assert e.value.feature == "a" and "后面" in str(e.value)


def test_extra_toplevel_name_rejected():
    bad = Feature("drill", "subtract", "tool = scad.make_cylinder_rsolid(radius=3, height=5)\ndrill = scad.cut_rsolid(base, tool)")
    with pytest.raises(NotebookError, match="tool"):
        render_notebook(P, [BASE, bad])


def test_loop_variable_must_be_private():
    bad = Feature("drill", "subtract", "for i in range(3):\n    pass\ndrill = base")
    with pytest.raises(NotebookError, match="i"):
        render_notebook(P, [BASE, bad])
    ok = Feature("drill", "subtract", "for _i in range(3):\n    pass\ndrill = base")
    assert render_notebook(P, [BASE, ok]).text


def test_comprehension_and_lambda_locals_are_allowed():
    ok = Feature("drill", "subtract", "drill = base\n_xs = [i for i in range(bolt_n)]\n_f = lambda k: k + hole_d")
    t = render_notebook(P, [BASE, ok]).text
    assert "def _(base, bolt_n, hole_d):" in t


@pytest.mark.parametrize("slug", ["Bad", "1abc", "has space", "under_score", "", "a.b"])
def test_bad_slug_rejected(slug):
    with pytest.raises(NotebookError):
        render_notebook(P, [Feature(slug, "build", "x = 1")])
    with pytest.raises(NotebookError):
        FeatureList().upsert(Feature(slug, "build", "x = 1"))


def test_bad_role_rejected():
    with pytest.raises(NotebookError, match="role"):
        render_notebook(P, [Feature("base", "weld", BASE.code)])
    with pytest.raises(NotebookError, match="role"):
        FeatureList().upsert(Feature("base", "weld", BASE.code))


@pytest.mark.parametrize("slug", ["model", "scad", "if", "base-l"])
def test_slug_clashing_with_reserved_or_param_name_rejected(slug):
    code = f"{slug.replace('-', '_')} = 1"
    with pytest.raises(NotebookError):
        render_notebook(P, [Feature(slug, "build", code)])


def test_empty_features_rejected():
    with pytest.raises(NotebookError, match="特征"):
        render_notebook(P, [])


def test_syntax_error_names_feature_and_line():
    bad = Feature("drill", "subtract", "drill = (\n")
    with pytest.raises(NotebookError, match="drill") as e:
        render_notebook(P, [BASE, bad])
    assert e.value.feature == "drill" and "语法" in str(e.value)


def test_no_params_is_fine():
    t = render_notebook([], [Feature("base", "build", "base = scad.make_box_rsolid(width=1, height=1, depth=1)")]).text
    assert "# ---- params ----" not in t  # 没有参数就不生成参数 cell
    assert 'model = scad.Part(part_id="model", body=base)' in t


def test_upsert_keeps_position():
    fl = FeatureList()
    fl.upsert(BASE)
    fl.upsert(DRILL)
    new_base = Feature("base", "build", "base = scad.make_box_rsolid(width=base_l, height=40, depth=8)")
    fl.upsert(new_base, before="drill")  # 同名时原位替换，忽略 before
    assert [f.slug for f in fl.items] == ["base", "drill"]
    assert fl.items[0].code == new_base.code


def test_upsert_before_inserts():
    fl = FeatureList()
    fl.upsert(Feature("a", "build", "a = 1"))
    fl.upsert(Feature("fillet", "modify", "fillet = 1"))
    fl.upsert(Feature("b", "add", "b = 1"), before="fillet")
    assert [f.slug for f in fl.items] == ["a", "b", "fillet"]
    with pytest.raises(NotebookError, match="nope"):
        fl.upsert(Feature("c", "add", "c = 1"), before="nope")
    assert [f.slug for f in fl.items] == ["a", "b", "fillet"]


def test_remove_and_round_trip():
    fl = FeatureList()
    fl.upsert(BASE)
    fl.upsert(DRILL)
    again = FeatureList.from_list(fl.to_list())
    assert again.items == fl.items
    fl.remove("drill")
    assert [f.slug for f in fl.items] == ["base"]
    with pytest.raises(NotebookError, match="drill"):
        fl.remove("drill")


def test_items_is_a_copy():
    fl = FeatureList()
    fl.upsert(BASE)
    fl.items.clear()
    assert len(fl.items) == 1


def test_cell_lines_point_at_feature():
    r = render_notebook(P, F)
    assert isinstance(r, RenderedNotebook)
    lines = r.text.splitlines()
    for slug, role in (("base", "build"), ("drill", "subtract")):
        start, end = r.cell_lines[slug]
        assert f"# ---- feature: {slug} ({role}) ----" in "\n".join(lines[start - 1 : end])
    assert r.cell_lines["base"][1] < r.cell_lines["drill"][0]


def test_crlf_code_is_normalised():
    f = Feature("base", "build", "_a = 1\r\nbase = scad.make_box_rsolid(width=1, height=1, depth=1)\r\n")
    assert "\r" not in render_notebook([], [f]).text


@pytest.mark.sca
def test_rendered_notebook_runs(tmp_path):
    from simplecadapi.runtime import run_notebook

    params = [Param("w", 60, "mm", "user"), Param("h", 36, "mm", "user"), Param("t", 8, "mm", "user"), Param("r", 5, "mm", "user")]
    feats = [
        Feature("plate", "build", "plate = scad.make_box_rsolid(width=w, height=h, depth=t, bottom_face_center=(0, 0, 0))"),
        Feature(
            "hole",
            "subtract",
            "_tool = scad.make_cylinder_rsolid(radius=r, height=t + 2, bottom_face_center=(0, 0, -1))\n"
            "hole = scad.cut_rsolid(plate, _tool)",
        ),
    ]
    path = tmp_path / "model.py"
    path.write_text(render_notebook(params, feats).text, encoding="utf-8")
    run = run_notebook(path, cache=False)
    assert run.product is not None
    assert abs(run.product.body.get_volume() - (60 * 36 * 8 - math.pi * 25 * 8)) < 1e-3
