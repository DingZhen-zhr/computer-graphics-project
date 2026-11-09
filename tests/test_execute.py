import tempfile

import pytest

from cad_agent.brief import Param
from cad_agent.notebook import Feature, render_notebook
from cad_agent.sandbox.execute import RunResult, run_job

pytestmark = pytest.mark.sca

PARAMS = [Param("w", 60, "mm", "user"), Param("h", 36, "mm", "user"), Param("t", 8, "mm", "user"), Param("r", 5, "mm", "user")]
PLATE = Feature("plate", "build", "plate = scad.make_box_rsolid(width=w, height=h, depth=t, bottom_face_center=(0, 0, 0))")
HOLE = Feature(
    "hole", "subtract",
    "_tool = scad.make_cylinder_rsolid(radius=r, height=t + 2, bottom_face_center=(0, 0, -1))\n"
    "hole = scad.cut_rsolid(plate, _tool)",
)
BBOX_X = {"id": "x", "type": "bbox", "axis": "x", "expected": "w"}


def nb_with_code(slug: str, code: str):
    return render_notebook(PARAMS, [PLATE, Feature(slug, "modify", code)])


def nb_with_bad(slug: str):
    return nb_with_code(slug, f"_x = 1 / 0\n{slug} = plate")


@pytest.fixture(scope="module")
def plate_nb():
    return render_notebook(PARAMS, [PLATE, HOLE])


def test_run_ok(plate_nb):
    r = run_job(plate_nb, [BBOX_X], {"w"})
    assert isinstance(r, RunResult)
    assert r.ok and r.error is None and r.values["w"] == 60
    assert [c.id for c in r.checks] == ["valid", "single_solid", "positive_volume", "x"] and all(c.passed for c in r.checks)
    assert r.facts["size"] == [60.0, 36.0, 8.0] and not r.timed_out and r.duration_s > 0
    assert r.query is None and r.step_path is None and r.png_path is None


def test_values_only_for_requested_params(plate_nb):
    r = run_job(plate_nb, [], {"w", "r"})
    assert r.values == {"w": 60.0, "r": 5.0}


def test_failed_check_is_not_ok_but_has_no_error(plate_nb):
    r = run_job(plate_nb, [{"id": "x2", "type": "bbox", "axis": "x", "expected": 61}], {"w"})
    assert not r.ok and r.error is None and [c.id for c in r.checks if not c.passed] == ["x2"]


def test_failing_feature_names_slug():
    r = run_job(nb_with_bad("boom"), [], set())
    assert not r.ok and r.error["cell"] == "boom" and r.error["type"] == "ZeroDivisionError"
    assert "division by zero" in r.error["message"] and r.checks == []


def test_name_error_names_slug_and_name():
    r = run_job(nb_with_code("typo", "typo = scad.make_box_rsolid(width=wd, height=h, depth=t)"), [], set())
    assert r.error["cell"] == "typo" and r.error["type"] == "NameError" and "wd" in r.error["message"]


def test_scad_error_message_is_condensed():
    r = run_job(nb_with_code("round", "_e = ql.edges().where(ql.prop('geom.type', '==', 'LINE')).exactly(12)\n"
                                       "round = scad.fillet_rsolid(solid=plate, edges=_e, radius=50)"), [], set())
    assert r.error["cell"] == "round" and r.error["type"] == "SimpleCADError"
    msg = r.error["message"]
    assert "radius 50" in msg and ".simplecad" not in msg and "Evidence" not in msg and len(msg) <= 900


def test_type_error_keeps_signature_not_noise():
    r = run_job(nb_with_code("wrong", "wrong = scad.make_box_rsolid(w=w, height=h, depth=t)"), [], set())
    assert r.error["type"] == "TypeError" and "width" in r.error["message"] and "Var(name" not in r.error["message"]


def test_timeout():
    r = run_job(nb_with_code("spin", "while True:\n    pass\nspin = plate"), [], set(), timeout_s=5)
    assert r.timed_out and not r.ok
    assert "运行超过 5 秒被终止" in r.error["message"] and r.duration_s < 25


def test_inspect_mode(plate_nb):
    r = run_job(plate_nb, [], {"w"}, mode="inspect", query_spec={"kind": "faces", "where": [["geom.type", "==", "CYLINDER"]]})
    assert r.ok and len(r.query) == 1 and r.query[0]["type"] == "CYLINDER" and r.facts["n_faces"] == 7


def test_inspect_mode_uses_param_values(plate_nb):
    r = run_job(plate_nb, [], {"t"}, mode="inspect", query_spec={"kind": "faces", "where": [["geom.center.z", ">=", "t - 0.1"]]})
    assert len(r.query) == 1 and r.query[0]["normal"] == [0.0, 0.0, 1.0]


def test_bad_checks_are_reported_as_error(plate_nb):
    r = run_job(plate_nb, [{"id": "x", "type": "bbox", "axis": "q", "expected": 1}], {"w"})
    assert not r.ok and r.error["type"] == "CheckSpecError" and "axis" in r.error["message"]


def test_exports_into_chinese_dir(plate_nb, tmp_path):
    out = tmp_path / "中文目录"
    out.mkdir()
    r = run_job(plate_nb, [], {"w"}, export_step=out / "model.step", render_png=out / "view.png")
    assert r.ok and r.step_path.stat().st_size > 0 and r.png_path.stat().st_size > 0
    assert r.step_path.parent == out and r.png_path.parent == out


def test_export_creates_missing_parent_dirs(plate_nb, tmp_path):
    r = run_job(plate_nb, [], set(), export_step=tmp_path / "a" / "b" / "model.step")
    assert r.ok and r.step_path.exists() and r.png_path is None


def test_secrets_not_passed_to_child(plate_nb, monkeypatch):
    monkeypatch.setenv("MY_PRIVATE_THING", "abc")
    monkeypatch.setenv("SOME_API_KEY", "abc")
    code = (
        "import os as _os\n"
        "_bad = [k for k in ('MY_PRIVATE_THING', 'SOME_API_KEY') if _os.environ.get(k)]\n"
        "assert not _bad, _bad\n"
        "assert _os.environ.get('PYTHONUTF8') == '1'\n"
        "assert 'cad-agent-' in _os.getcwd(), _os.getcwd()\n"
        "ok = plate"
    )
    # 这个 notebook 故意绕过了 guard，用来从子进程内部检查环境
    r = run_job(nb_with_code("ok", code), [], set(), secret_names=("MY_PRIVATE_THING",))
    assert r.ok, r.error


def test_workdir_is_removed(plate_nb, tmp_path, monkeypatch):
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    r = run_job(plate_nb, [], set())
    assert r.ok and list(tmp_path.glob("cad-agent-*")) == []


def test_exports_stl(plate_nb, tmp_path):
    import struct

    out = tmp_path / "中文目录"   # 路径里有中文也要能导出
    out.mkdir()
    r = run_job(plate_nb, [], {"w"}, export_stl=out / "model.stl")
    assert r.ok and r.stl_error is None and r.stl_path == out / "model.stl"
    data = r.stl_path.read_bytes()
    triangles = struct.unpack("<I", data[80:84])[0]
    assert triangles > 0 and len(data) == 84 + 50 * triangles   # 二进制 STL：80 字节头 + 4 字节个数 + 每个三角形 50 字节
    assert r.step_path is None and r.png_path is None   # 没要求的不导出


def test_exports_stl_together_with_step_and_png(plate_nb, tmp_path):
    r = run_job(plate_nb, [], {"w"}, export_step=tmp_path / "model.step", render_png=tmp_path / "view.png", export_stl=tmp_path / "model.stl")
    assert r.ok and r.step_path.stat().st_size > 0 and r.png_path.stat().st_size > 0 and r.stl_path.stat().st_size > 0


def test_stl_not_requested_means_no_stl_fields(plate_nb):
    r = run_job(plate_nb, [], {"w"})
    assert r.stl_path is None and r.stl_error is None
