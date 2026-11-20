"""3.0 计划 2 Task 13：多零件状态和文件给界面用。"""

from __future__ import annotations

import pytest

from cad_agent.desk.events import describe_event
from cad_agent.desk.view import build_state
from cad_agent.brief import Brief
from cad_agent.notebook import FeatureList
from cad_agent.session import Session
from cad_agent.tools import Workspace
from helpers_staged import staged_brief
from test_product_flow import BODY, CONNECT, LID, make_agent


def test_state_single_part_has_null_product(tmp_path):
    s = Session(tmp_path)
    st = build_state(s, Workspace(staged_brief(), FeatureList(), []), busy=False, demo=False)
    assert st["product"] is None
    assert [p["name"] for p in st["params_view"]] == ["phone_w", "tilt_deg"]
    assert all("part" in c and "selected" in c for c in st["checks"])


def test_state_multipart_parts_and_joints(tmp_path):
    agent, ws, llm, box, session = make_agent(tmp_path, BODY + LID + [CONNECT])
    assert agent.handle_user("开始").kind == "delivered"
    st = build_state(session, ws, busy=False, demo=False)
    prod = st["product"]
    assert [(p["id"], p["status"], p["material"], p["finish"]) for p in prod["parts"]] == [
        ("body", "done", "abs", "matte"), ("lid", "done", "aluminum", "metal")]
    assert prod["parts"][0]["checks"]["total"] > 0 and prod["parts"][0]["checks"]["passed"] == prod["parts"][0]["checks"]["total"]
    assert prod["joints"] == [{"id": "open", "label": "盖子翻开", "type": "revolute", "unit": "deg", "lo": 0, "hi": 110}]
    assert prod["assembly"] == "passed"
    assert prod["motion"] == f"/files/{session.dir.name}/v1/motion.json"
    assert {c["part"] for c in st["checks"]} == {"body", "lid", "assembly"}
    # 示例会话（没有工作区）：从文件读
    st2 = build_state(session, None, busy=False, demo=True)
    assert st2["product"]["assembly"] == "passed" and st2["product"]["joints"][0]["hi"] == 110


def test_params_view_labels_and_groups():
    b = Brief()
    b.apply_patch({"part": {"name": "盒子"},
                   "parts": [{"id": "body", "name": "盒体", "material": "abs", "features": ["盒体"]},
                             {"id": "lid", "name": "盖子", "material": "abs", "features": ["盖板"]}],
                   "set_params": [{"name": "lid_t", "value": 6, "unit": "mm", "source": "suggested", "note": "盖子厚度（建议）"},
                                  {"name": "box_l", "value": 160, "unit": "mm", "source": "user", "note": "长度"},
                                  {"name": "rim", "value": 2, "unit": "mm", "source": "user", "note": "", "part": "body"}]})
    from cad_agent.desk.product_view import params_view

    pv = {p["name"]: p for p in params_view(b)}
    assert (pv["lid_t"]["label"], pv["lid_t"]["group"]) == ("盖子厚度", "盖子")
    assert (pv["box_l"]["label"], pv["box_l"]["group"]) == ("长度", "其他")
    assert (pv["rim"]["label"], pv["rim"]["group"], pv["rim"]["part"]) == ("rim", "盒体", "body")
    assert set(pv["lid_t"]) == {"name", "label", "group", "unit", "value", "source", "part"}


def test_new_events_described():
    assert describe_event("part_done", {"id": "body", "name": "盒体"}) == "盒体做完了"
    assert describe_event("assembly", {"passed": True}) == "装好了，检查都过了"
    assert describe_event("assembly", {"passed": False, "reason": "装好后零件 body 和 lid 重叠了 3 立方毫米"}) == \
        "装配没通过：装好后零件 body 和 lid 重叠了 3 立方毫米"


@pytest.mark.parametrize("rest,ok", [
    (["v1", "motion.json"], True), (["v1", "product.step"], True), (["v1", "assembly.py"], True),
    (["v1", "parts", "body", "model.stl"], True), (["v1", "parts", "lid", "checks.json"], True),
    (["v1", "parts", "..", "log.jsonl"], False), (["v1", "parts", "A", "model.stl"], False),
    (["v1", "parts", "body", "brief.json"], False),
])
def test_file_whitelist_multipart(tmp_path, rest, ok):
    from cad_agent.desk.routes import version_file
    from cad_agent.desk.workbench import Busy  # noqa: F401 - routes 依赖它，确认能导入

    agent, ws, llm, box, session = make_agent(tmp_path, BODY + LID + [CONNECT])
    assert agent.handle_user("开始").kind == "delivered"
    (session.dir / "log.jsonl").touch()
    (session.dir / "versions" / "v1" / "parts" / "body" / "brief.json").write_text("{}", encoding="utf-8")

    class Hub:
        def open(self, sid):  # noqa: ANN001, ANN202
            return type("W", (), {"session": session})()

    if ok:
        assert version_file(Hub(), "x", rest).is_file()
    else:
        with pytest.raises(Exception) as e:
            version_file(Hub(), "x", rest)
        assert getattr(e.value, "status", 404) == 404
