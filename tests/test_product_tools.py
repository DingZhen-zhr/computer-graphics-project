"""3.0 计划 2 Task 9：多零件的五个工具（假的 run_assembly，不跑沙盒）。"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from cad_agent.brief import Brief
from cad_agent.gates import Gates
from cad_agent.notebook import FeatureList
from cad_agent.sandbox.runner_assembly import AssemblyRun
from cad_agent.staged.final_gate import GateResult
from cad_agent.staged.specs import TOOL_SPECS_V2
from cad_agent.tools import ToolBox, Workspace
from helpers import Runner, make_brief

PROMPTS = Path(__file__).resolve().parents[1] / "docs/superpowers/plans/2026-11-20-datum-2-multipart-prompts.md"
I4 = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]
TOP = [["geom.type", "==", "PLANE"], ["geom.normal.z", ">=", 0.99]]
BOT = [["geom.type", "==", "PLANE"], ["geom.normal.z", "<=", -0.99]]
AX = [["geom.type", "==", "CYLINDER"]]
NAMES = ["select_part", "set_connectors", "set_assembly", "set_assembly_checks", "build_assembly"]


def j(out) -> dict:
    return json.loads(out.content)


def _doc_text(heading: str) -> str:
    text = PROMPTS.read_text(encoding="utf-8")
    return re.findall(r"```text\n(.*?)\n```", text.split(heading, 1)[1], flags=re.S)[0]


class FakeAssembly:
    def __init__(self, run: AssemblyRun) -> None:
        self.run, self.calls = run, []

    def __call__(self, ws, **kw):  # noqa: ANN001
        self.calls.append(kw)
        return self.run


def _run(**kw) -> AssemblyRun:
    base = dict(ok=True, error=None, connectors={"body.top": {"selected": 1, "type": "PLANE"}, "lid.hinge": {"selected": 1, "type": "CYLINDER"}},
                rest={"body": I4, "lid": I4}, overlaps=[], measures={},
                samples={"open": [{"value": 0, "poses": {}, "hits": [], "error": None, "joints": {"open": 0}},
                                  {"value": 110, "poses": {}, "hits": [], "error": None, "joints": {"open": 110}}]})
    base.update(kw)
    return AssemblyRun(**base)


def multi_box(run: AssemblyRun | None = None) -> ToolBox:
    b = Brief()
    b.apply_patch({"part": {"name": "盒子"},
                   "parts": [{"id": "body", "name": "盒体", "material": "abs", "features": ["盒体"]},
                             {"id": "lid", "name": "盖子", "material": "aluminum", "features": ["盖板"]}],
                   "relations": ["盖子盖在盒体上"],
                   "set_params": [{"name": "w", "value": 40, "unit": "mm", "source": "user", "note": ""}]})
    b.confirmed = True
    box = ToolBox(Workspace(b, FeatureList(), []), run_job=Runner(), gates=Gates())
    box.run_assembly = FakeAssembly(run or _run())
    return box


def _declare(box: ToolBox) -> None:
    assert j(box.call("set_connectors", {"part": "body", "connectors": [{"name": "top", "kind": "faces", "where": TOP},
                                                                         {"name": "hinge", "kind": "faces", "where": AX}]}))["ok"]
    assert j(box.call("set_connectors", {"part": "lid", "connectors": [{"name": "hinge", "kind": "faces", "where": AX}]}))["ok"]
    assert j(box.call("set_assembly", {"ground": "body", "mates": [{"id": "lid_on", "fixed": "body.hinge", "moving": "lid.hinge", "align": "same"}],
                                       "joints": [{"id": "open", "mate": "lid_on", "type": "revolute", "range": [0, 110], "label": "盖子翻开"}]}))["ok"]


def _all_done(box: ToolBox) -> None:
    for st in box.ws.parts.values():
        st.done = True


def test_new_specs_verbatim():
    sec3 = PROMPTS.read_text(encoding="utf-8").split("## 3. 工具说明", 1)[1].split("## 4. 程序生成的消息", 1)[0]
    want = {d["name"]: d for d in (json.loads(b) for b in re.findall(r"```json\n(.*?)\n```", sec3, flags=re.S))}
    got = {s["function"]["name"]: s["function"] for s in TOOL_SPECS_V2}
    for name in NAMES + ["update_brief"]:
        assert got[name] == want[name], name


def test_tools_hidden_for_single_part():
    box = ToolBox(Workspace(make_brief(True), FeatureList(), []), run_job=Runner(), gates=Gates())
    shown = [s["function"]["name"] for s in box.schemas()]
    assert not set(NAMES) & set(shown)
    for name in NAMES:
        assert j(box.call(name, {"part": "x", "connectors": [], "checks": []})) == {"error": "这个需求只有一个零件，用不到这个工具。"}
    multi = multi_box()
    assert [s["function"]["name"] for s in multi.schemas()][-5:] == NAMES


def test_select_part():
    box = multi_box()
    out = j(box.call("select_part", {"part": "lid"}))
    assert out["ok"] and out["part"] == "lid" and out["name"] == "盖子" and out["plan"] is None and out["params"] == ["w"]
    assert box.ws.active == "lid"
    assert "没有零件" in j(box.call("select_part", {"part": "cap"}))["error"]


def test_set_connectors_and_assembly_reset_passed():
    box = multi_box()
    box.ws.assembly_passed = True
    _declare(box)
    assert box.ws.assembly is not None and not box.ws.assembly_passed
    box.ws.assembly_passed = True
    out = j(box.call("set_assembly", {"ground": "body", "mates": [{"id": "lid_on", "fixed": "body.hinge", "moving": "lid.hinge", "align": "same"}],
                                      "joints": [{"id": "open", "mate": "lid_on", "type": "revolute", "range": [110, 0], "label": "盖子翻开"}]}))
    assert out["notes"] == ["关节 open 的范围写反了，已经按从小到大处理"] and not box.ws.assembly_passed
    out = j(box.call("set_assembly", {"ground": "body", "mates": [{"id": "m", "fixed": "body.top", "moving": "body.hinge", "align": "same"}]}))
    assert "error" in out and box.ws.assembly is not None      # 写错了：原来的装配关系保持不变
    # 改掉装配关系用到的连接点：装配关系作废
    out = j(box.call("set_connectors", {"part": "lid", "connectors": [{"name": "edge", "kind": "faces", "where": TOP}]}))
    assert out["ok"] and "note" in out and box.ws.assembly is None
    assert j(box.call("set_assembly_checks", {"checks": []})) == {"error": "还没有装配关系。先用 set_connectors 和 set_assembly 写好。"}


def test_build_assembly_refused_until_parts_done():
    box = multi_box()
    _declare(box)
    assert j(box.call("build_assembly", {})) == {"error": "还有零件没做完：body、lid。全部零件做完才能装配。"}
    box.ws.parts["body"].done = True
    assert j(box.call("build_assembly", {})) == {"error": "还有零件没做完：lid。全部零件做完才能装配。"}
    assert box.run_assembly.calls == [] and box.build_failures == 0
    _doc = _doc_text("还有零件没做完时调用 build_assembly：")
    assert _doc == "还有零件没做完：<编号，用顿号连接>。全部零件做完才能装配。"


def test_build_assembly_body_and_hints(monkeypatch):
    anchor = _run(connectors={"body.top": {"selected": 0, "error": "零件 body 的连接点 top 选中了 0 个几何，要恰好 1 个。改一下 where 的条件。"}}, rest={})
    box = multi_box(anchor)
    _declare(box)
    _all_done(box)
    out = j(box.call("build_assembly", {}))
    assert not out["passed"] and out["hint"] == _doc_text("A：") and out["connectors"]["body.top"]["selected"] == 0

    overlap = _run(overlaps=[{"a": "body", "b": "lid", "volume": 12.5}])
    box = multi_box(overlap)
    _declare(box)
    _all_done(box)
    out = j(box.call("build_assembly", {}))
    want = _doc_text("B：").replace("<a>", "body").replace("<b>", "lid").replace("<v>", "12.5")
    assert out["hint"] == want

    hit_rows = [{"value": 0, "poses": {}, "hits": [], "error": None, "joints": {}},
                {"value": 110, "poses": {}, "hits": [{"a": "body", "b": "lid", "volume": 3}], "error": None, "joints": {}}]
    box = multi_box(_run(samples={"open": hit_rows}))
    _declare(box)
    _all_done(box)
    out = j(box.call("build_assembly", {}))
    want = (_doc_text("C：").replace("<关节名字>", "盖子翻开").replace("<value><单位>", "110°")
            .replace("<a>", "body").replace("<b>", "lid").replace("<v>", "3"))
    assert out["hint"] == want
    assert out["hits"] == [{"joint": "open", "label": "盖子翻开", "value": 110, "a": "body", "b": "lid", "volume": 3}]
    assert set(out) == {"passed", "error", "connectors", "failed_checks", "passed_checks", "hits", "final_gate", "failures_left", "hint"}

    # 全部通过：做产品终检，通过就可以交付
    import cad_agent.product.flow as flow

    monkeypatch.setattr(flow, "run_product_gate", lambda box: GateResult(passed=True, missing_coverage=[]))
    box = multi_box()
    _declare(box)
    _all_done(box)
    res = box.call("build_assembly", {})
    out = j(res)
    assert out["passed"] and res.deliverable and out["hint"] == "全部通过，程序会自动交付。" and box.ws.assembly_passed
    assert box.run_assembly.calls[0]["mode"] == "check" and box.run_assembly.calls[0]["samples"] == 24


def test_assembly_failure_counts():
    box = multi_box(_run(overlaps=[{"a": "body", "b": "lid", "volume": 5}]))
    _declare(box)
    _all_done(box)
    box.max_build_failures = 3
    assert j(box.call("build_assembly", {}))["failures_left"] == 2
    assert j(box.call("build_assembly", {}))["failures_left"] == 1
    assert box.build_failures == 2


@pytest.mark.parametrize("bad", [{"part": "body", "connectors": [{"name": "A", "kind": "faces", "where": TOP}]},
                                 {"part": "cap", "connectors": []}])
def test_set_connectors_rejects(bad):
    box = multi_box()
    assert "error" in j(box.call("set_connectors", bad))
