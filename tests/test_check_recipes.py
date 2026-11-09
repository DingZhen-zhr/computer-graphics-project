"""速查表"检查写法"一节里每一条写法的实测：

- 用 SCA 建一个小模型，参数正确时，写法里的检查全部通过；
- "做错了的模型"：notebook 里参数的值不变，只在特征代码里把这个参数换成 (参数 * 1.2) 或 (参数 * 0.8)
  （孔数这类计数参数换成多一个、少一个），这些检查必须有不通过的。

RECIPES 里的检查 JSON 和速查表里"例："后面的 JSON 逐项相等（tests/test_prompts.py 里有测试比对）。
特征代码里的 @P@ 是被测参数出现的位置。
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from cad_agent.brief import Param
from cad_agent.notebook import Feature, render_notebook
from cad_agent.sandbox.execute import run_job

pytestmark = pytest.mark.sca


def P(name: str, value: float, unit: str = "mm") -> Param:
    return Param(name, value, unit, "user")


@dataclass(frozen=True)
class Recipe:
    kind: str                                   # 参数种类，和速查表里的 **<参数种类> 逐字一致
    param: str                                  # 被测参数
    params: tuple[Param, ...]
    features: tuple[tuple[str, str, str], ...]  # (slug, role, 代码)，代码里的 @P@ 是被测参数的位置
    checks: tuple[dict, ...]
    count_like: bool = False                    # 计数参数：做错的写法是多一个、少一个

    def wrong(self) -> tuple[str, str]:
        if self.count_like:
            return f"({self.param} + 1)", f"({self.param} - 1)"
        return f"({self.param} * 1.2)", f"({self.param} * 0.8)"


PLATE = "plate = scad.make_box_rsolid(width=plate_w, height=plate_d, depth=plate_t, bottom_face_center=(0, 0, 0))"
PLATE_PARAMS = (P("plate_w", 60), P("plate_d", 40), P("plate_t", 5))
TOP = ["geom.type", "==", "PLANE"], ["geom.normal.z", ">=", 0.99]
BOTTOM = ["geom.type", "==", "PLANE"], ["geom.normal.z", "<=", -0.99]
CORNER_EDGE = (
    "_edges = ql.edges().where(ql.and_(ql.prop('geom.type', '==', 'LINE'), "
    "ql.prop('geom.center.x', '>=', plate_w / 2 - 0.1), ql.prop('geom.center.x', '<=', plate_w / 2 + 0.1), "
    "ql.prop('geom.center.y', '>=', plate_d / 2 - 0.1), ql.prop('geom.center.y', '<=', plate_d / 2 + 0.1), "
    "ql.prop('geom.center.z', '>=', plate_h / 2 - 0.1), ql.prop('geom.center.z', '<=', plate_h / 2 + 0.1))).exactly(1)\n"
)
BLOCK = "plate = scad.make_box_rsolid(width=plate_w, height=plate_d, depth=plate_h, bottom_face_center=(0, 0, 0))"
BLOCK_PARAMS = (P("plate_w", 60), P("plate_d", 40), P("plate_h", 10))

RECIPES: list[Recipe] = [
    Recipe(
        "总体尺寸", "plate_w", PLATE_PARAMS,
        (("plate", "build", PLATE.replace("width=plate_w", "width=@P@")),),
        ({"id": "size-x", "type": "bbox", "axis": "x", "expected": "plate_w"},),
    ),
    Recipe(
        "板厚", "plate_t", PLATE_PARAMS,
        (("plate", "build", PLATE.replace("depth=plate_t", "depth=@P@")),),
        ({"id": "thickness", "type": "distance", "a": {"kind": "faces", "where": [*TOP]}, "b": {"kind": "faces", "where": [*BOTTOM]},
          "expected": "plate_t"},),
    ),
    Recipe(
        "孔径", "hole_d", (*PLATE_PARAMS, P("hole_d", 8)),
        (("plate", "build", PLATE),
         ("hole", "subtract",
          "_tool = scad.make_cylinder_rsolid(radius=@P@ / 2, height=plate_t + 2, bottom_face_center=(0, 0, -1))\n"
          "hole = scad.cut_rsolid(plate, _tool, skip_non_intersecting=False)")),
        ({"id": "hole-dia", "type": "count", "kind": "faces", "expected": 1,
          "where": [["geom.type", "==", "CYLINDER"], ["geom.area", ">=", "pi * hole_d * plate_t * 0.95"],
                    ["geom.area", "<=", "pi * hole_d * plate_t * 1.05"]]},),
    ),
    Recipe(
        "孔数", "hole_n", (P("plate_w", 100), P("plate_d", 100), P("plate_t", 5), P("hole_d", 6), P("pcd", 60), P("hole_n", 6, "1")),
        (("plate", "build", PLATE),
         ("holes", "pattern",
          "_hole = scad.make_cylinder_rsolid(radius=hole_d / 2, height=plate_t + 2, bottom_face_center=(pcd / 2, 0, -1))\n"
          "_holes = scad.radial_pattern_rsolidlist(shape=_hole, center=(0, 0, 0), axis=(0, 0, 1), count=@P@, total_rotation_angle=360)\n"
          "holes = scad.cut_rsolid(plate, _holes, skip_non_intersecting=False)")),
        ({"id": "hole-count", "type": "count", "kind": "faces", "expected": "hole_n",
          "where": [["geom.type", "==", "CYLINDER"], ["geom.area", ">=", "pi * hole_d * plate_t * 0.95"],
                    ["geom.area", "<=", "pi * hole_d * plate_t * 1.05"]]},),
        count_like=True,
    ),
    Recipe(
        "孔位", "hole_x", (P("plate_w", 80), P("plate_d", 40), P("plate_t", 5), P("hole_d", 6), P("hole_x", 25)),
        (("plate", "build", PLATE),
         ("hole", "subtract",
          "_tool = scad.make_cylinder_rsolid(radius=hole_d / 2, height=plate_t + 2, bottom_face_center=(@P@, 0, -1))\n"
          "hole = scad.cut_rsolid(plate, _tool, skip_non_intersecting=False)")),
        ({"id": "hole-center-empty", "type": "point_outside", "point": ["hole_x", 0, "plate_t / 2"]},
         {"id": "hole-edge-solid", "type": "point_inside", "point": ["hole_x + hole_d / 2 + 0.5", 0, "plate_t / 2"]}),
    ),
    Recipe(
        "槽或缺口宽度", "slot_w", (*PLATE_PARAMS, P("slot_w", 10), P("slot_len", 15)),
        (("plate", "build", PLATE),
         ("slot", "subtract",
          "_tool = scad.make_box_rsolid(width=@P@, height=slot_len + 1, depth=plate_t + 2, "
          "bottom_face_center=(0, plate_d / 2 - slot_len / 2 + 0.5, -1))\n"
          "slot = scad.cut_rsolid(plate, _tool, skip_non_intersecting=False)")),
        ({"id": "slot-empty", "type": "point_outside", "point": ["slot_w / 2 - 0.5", 12, "plate_t / 2"]},
         {"id": "slot-wall", "type": "point_inside", "point": ["slot_w / 2 + 0.5", 12, "plate_t / 2"]}),
    ),
    Recipe(
        "圆角半径", "fillet_r", (*BLOCK_PARAMS, P("fillet_r", 4)),
        (("plate", "build", BLOCK),
         ("corner-round", "modify", CORNER_EDGE + "corner_round = scad.fillet_rsolid(solid=plate, edges=_edges, radius=@P@)")),
        ({"id": "fillet-r", "type": "count", "kind": "faces", "expected": 1,
          "where": [["geom.type", "==", "CYLINDER"], ["geom.area", ">=", "pi / 2 * fillet_r * plate_h * 0.95"],
                    ["geom.area", "<=", "pi / 2 * fillet_r * plate_h * 1.05"]]},),
    ),
    Recipe(
        "倒角尺寸", "chamfer_c", (*BLOCK_PARAMS, P("chamfer_c", 3)),
        (("plate", "build", BLOCK),
         ("corner-chamfer", "modify", CORNER_EDGE + "corner_chamfer = scad.chamfer_rsolid(solid=plate, edges=_edges, distance=@P@)")),
        ({"id": "chamfer-c", "type": "count", "kind": "faces", "expected": 1,
          "where": [["geom.type", "==", "PLANE"], ["geom.normal.x", ">=", 0.6], ["geom.normal.x", "<=", 0.8],
                    ["geom.normal.y", ">=", 0.6], ["geom.normal.y", "<=", 0.8],
                    ["geom.area", ">=", "sqrt(2) * chamfer_c * plate_h * 0.95"], ["geom.area", "<=", "sqrt(2) * chamfer_c * plate_h * 1.05"]]},),
    ),
    Recipe(
        "两面夹角", "slope_deg", (P("wedge_l", 60), P("wedge_w", 30), P("slope_deg", 30, "deg")),
        (("wedge", "build",
          "_h = wedge_l * math.tan(math.radians(@P@))\n"
          "_wire = scad.make_polyline_rwire(points=[(0, 0, 0), (wedge_l, 0, 0), (0, 0, _h)], closed=True)\n"
          "_profile = scad.make_face_from_wire_rface(wire=_wire, normal=(0, -1, 0))\n"
          "wedge = scad.extrude_rsolid(profile=_profile, direction=(0, 1, 0), distance=wedge_w)"),),
        ({"id": "slope-angle", "type": "angle", "expected": "180 - slope_deg",
          "a": [["geom.type", "==", "PLANE"], ["geom.normal.x", ">=", 0.1], ["geom.normal.z", ">=", 0.1]],
          "b": [["geom.type", "==", "PLANE"], ["geom.normal.z", "<=", -0.99]]},),
    ),
]
IDS = [r.kind for r in RECIPES]


def run(recipe: Recipe, expr: str):
    features = [Feature(slug, role, code.replace("@P@", expr)) for slug, role, code in recipe.features]
    names = {p.name for p in recipe.params}
    return run_job(render_notebook(list(recipe.params), features), [dict(c) for c in recipe.checks], names, mode="build", timeout_s=120)


def report(result) -> str:
    return "\n".join(f"{c.id}: passed={c.passed} measured={c.measured} expected={c.expected} {c.detail}" for c in result.checks)


def test_recipes_cover_the_nine_kinds_in_order():
    assert IDS == ["总体尺寸", "板厚", "孔径", "孔数", "孔位", "槽或缺口宽度", "圆角半径", "倒角尺寸", "两面夹角"]
    assert len({c["id"] for r in RECIPES for c in r.checks}) == sum(len(r.checks) for r in RECIPES)   # 检查名不重复


@pytest.mark.parametrize("recipe", RECIPES, ids=IDS)
def test_recipe_passes_with_the_correct_model(recipe):
    result = run(recipe, recipe.param)
    assert result.error is None, result.error
    assert result.ok, report(result)
    assert len(result.checks) == 3 + len(recipe.checks)


@pytest.mark.parametrize("which", [0, 1], ids=["偏大", "偏小"])
@pytest.mark.parametrize("recipe", RECIPES, ids=IDS)
def test_recipe_catches_a_wrong_parameter(recipe, which):
    result = run(recipe, recipe.wrong()[which])
    assert result.error is None, result.error   # 模型本身能建出来，是检查把它挡住
    failed = {c.id for c in result.checks if not c.passed}
    assert failed and failed <= {c["id"] for c in recipe.checks}, report(result)
    assert not result.ok
