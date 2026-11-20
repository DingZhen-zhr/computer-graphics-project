"""3.0 计划 3 Task 8：修改前后对比的接口。"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from cad_agent.desk.compare_api import compare_versions
from cad_agent.desk.routes import ApiError, session_api


def _version(root, name, params, checks, *, stl=True):
    v = root / "versions" / name
    v.mkdir(parents=True)
    (v / "brief.json").write_text(json.dumps({"params": params}, ensure_ascii=False), encoding="utf-8")
    (v / "checks.json").write_text(json.dumps(checks, ensure_ascii=False), encoding="utf-8")
    if stl:
        (v / "model.stl").write_bytes(b"x")
    return v


def _p(name, value, note="", unit="mm"):
    return {"name": name, "value": value, "unit": unit, "source": "user", "note": note}


def test_only_changed_items(tmp_path):
    a = _version(tmp_path, "v1", [_p("hole_d", 6, "孔径（贯通）"), _p("w", 60, "宽")], [{"id": "w", "passed": True}, {"id": "hole", "passed": True}])
    b = _version(tmp_path, "v2", [_p("hole_d", 8, "孔径（贯通）"), _p("w", 60, "宽")], [{"id": "w", "passed": True}, {"id": "hole", "passed": False}], stl=False)
    r = compare_versions(a, b)
    assert r["params"] == [{"name": "hole_d", "label": "孔径", "unit": "mm", "a": 6, "b": 8}]
    assert r["checks"] == [{"id": "hole", "part": "main", "a": True, "b": False}]
    assert r["files"]["a"]["stl"] and not r["files"]["b"]["stl"]


def test_multipart_checks_have_part(tmp_path):
    a = _version(tmp_path, "v1", [_p("lid_max", 110, "", "deg")], [{"id": "w", "part": "lid", "passed": True}, {"id": "x", "part": "assembly", "passed": True}])
    b = _version(tmp_path, "v2", [_p("lid_max", 95, "", "deg")], [{"id": "w", "part": "lid", "passed": True}, {"id": "x", "part": "assembly", "passed": False}])
    r = compare_versions(a, b)
    assert r["params"][0]["label"] == "lid_max" and r["checks"] == [{"id": "x", "part": "assembly", "a": True, "b": False}]


class _Session:
    def __init__(self, root):  # noqa: ANN001
        self.root = root

    def part_dir(self, part_id="main"):  # noqa: ANN001, ANN201
        return self.root


class _Hub:
    def __init__(self, root):  # noqa: ANN001
        self.work = SimpleNamespace(session=_Session(root))

    def open(self, sid):  # noqa: ANN001, ANN201
        return self.work


def test_route_and_missing_version_404(tmp_path):
    _version(tmp_path, "v1", [_p("w", 1)], [])
    _version(tmp_path, "v2", [_p("w", 2)], [])
    hub = _Hub(tmp_path)
    r = session_api(hub, "GET", ["sessions", "x", "compare"], {"a": ["v1"], "b": ["v2"]}, None, lambda p: None)
    assert r["params"][0]["b"] == 2
    with pytest.raises(ApiError) as e:
        session_api(hub, "GET", ["sessions", "x", "compare"], {"a": ["v1"], "b": ["v9"]}, None, lambda p: None)
    assert e.value.status == 404
