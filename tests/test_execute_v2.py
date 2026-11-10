"""沙盒的 probe 模式和冻结检查期望值（第二版计划 1 Task 5，真实 SCA）。"""

import pytest

from cad_agent.brief import Param
from cad_agent.notebook import Feature, render_notebook
from cad_agent.sandbox.execute import PROBE_OUTPUT_LIMIT, run_job

pytestmark = pytest.mark.sca

TAIL = "\n…（后面的输出省略）"
PARAMS = [Param("phone_w", 78, "mm", "user"), Param("plate_t", 8, "mm", "user")]
BASE = Feature("base", "build", "base = scad.make_box_rsolid(width=phone_w, height=40, depth=plate_t, bottom_face_center=(0, 0, 0))", "s1")
PHONE_W = {"id": "phone-w", "type": "bbox", "axis": "x", "expected": "phone_w"}
NAMES = {"phone_w", "plate_t"}


def probe(code: str, features=(BASE,), **kw):
    return run_job(render_notebook(PARAMS, list(features), probe=code), [], NAMES, mode="probe", **kw)


def test_probe_prints_facts():
    # 包围盒的写法取自笔记第 17 节（brep 检视函数在 notebook 里不能用，偏离 D10）
    r = probe(
        "print(phone_w)\n"
        "_pts = [v.get_center() for v in ql.vertices().resolve(model)]\n"
        "_xs, _ys, _zs = [p.x for p in _pts], [p.y for p in _pts], [p.z for p in _pts]\n"
        "print('size', round(max(_xs) - min(_xs), 4), round(max(_ys) - min(_ys), 4), round(max(_zs) - min(_zs), 4))"
    )
    assert r.error is None and r.ok
    assert "78" in r.probe_output
    assert "size 78.0 40.0 8.0" in r.probe_output
    assert r.checks == [] and r.step_path is None


def test_probe_model_is_none_without_features():
    r = probe("print(model is None)", features=())
    assert r.error is None and r.probe_output.strip() == "True"


def test_probe_error_is_reported_with_partial_output():
    r = probe("print('到这里')\nprint(undefined_name)")
    assert r.error["cell"] == "probe" and r.error["type"] == "NameError"
    assert "到这里" in r.probe_output and not r.ok


def test_probe_output_truncated():
    r = probe("print('a' * 5000)")
    assert r.error is None
    assert r.probe_output.endswith(TAIL)
    assert len(r.probe_output) <= PROBE_OUTPUT_LIMIT + len(TAIL)
    assert r.probe_output.startswith("a" * PROBE_OUTPUT_LIMIT)


def test_probe_timeout():
    r = probe("while True:\n    pass", timeout_s=3)
    assert r.timed_out and not r.ok
    assert r.probe_output == "" or isinstance(r.probe_output, str)


def test_build_result_has_no_probe_output():
    r = run_job(render_notebook(PARAMS, [BASE]), [PHONE_W], NAMES)
    assert r.ok and r.probe_output is None


def test_check_values_freeze_expected():
    wide = [Param("phone_w", 93.6, "mm", "user"), Param("plate_t", 8, "mm", "user")]
    nb = render_notebook(wide, [BASE])
    frozen = run_job(nb, [PHONE_W], NAMES, check_values={"phone_w": 78.0, "plate_t": 8.0})
    c = next(c for c in frozen.checks if c.id == "phone-w")
    assert not c.passed and c.expected == 78.0 and abs(c.measured - 93.6) < 1e-6
    assert not frozen.ok and frozen.error is None
    assert frozen.values["phone_w"] == pytest.approx(93.6)   # 运行得到的参数值照实返回
    free = run_job(nb, [PHONE_W], NAMES)
    assert free.ok


def test_check_values_also_freeze_where():
    thick = [Param("phone_w", 78, "mm", "user"), Param("plate_t", 9.6, "mm", "user")]
    top = {"id": "top", "type": "count", "kind": "faces", "expected": 1,
           "where": [["geom.type", "==", "PLANE"], ["geom.center.z", ">=", "plate_t - 0.1"], ["geom.center.z", "<=", "plate_t + 0.1"]]}
    nb = render_notebook(thick, [BASE])
    assert run_job(nb, [top], NAMES).ok
    frozen = run_job(nb, [top], NAMES, check_values={"phone_w": 78.0, "plate_t": 8.0})
    c = next(c for c in frozen.checks if c.id == "top")
    assert not c.passed and c.measured == 0
