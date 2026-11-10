"""需求单的位置关系（第二版计划 1 Task 3）。"""

import json

import pytest

from cad_agent.brief import PATCH_KEYS, Brief, BriefError, feature_name
from cad_agent.notebook import FeatureList
from cad_agent.tools import ToolBox, Workspace
from helpers import Runner, make_brief

RELATION_ERROR = "这些部分还没有写明怎么相接：{}。在 relations 里各写一句，要原样写出它的名字"


def three_part_brief(**over) -> Brief:
    b = make_brief()
    b.features = ["底板", "立板，在左端", "加强筋"]
    b.relations = ["立板的下端和底板的一端重叠"]
    b.require_relations = True
    for k, v in over.items():
        setattr(b, k, v)
    return b


def test_patch_keys_end_with_relations():
    assert PATCH_KEYS[-1] == "relations"


def test_feature_name():
    assert feature_name("底板，放在最下面") == "底板"
    assert feature_name("立板（左端）") == "立板"
    assert feature_name("加强筋") == "加强筋"
    assert feature_name("  侧板: 两块 ") == "侧板"
    assert feature_name("凸台(中间)，高 5") == "凸台"


def test_missing_relations_off_by_default():
    b = three_part_brief(require_relations=False, relations=[])
    assert b.missing_relations() == []
    assert Brief().require_relations is False


def test_missing_relations():
    assert three_part_brief().missing_relations() == ["加强筋"]
    assert three_part_brief(features=["底板"], relations=[]).missing_relations() == []
    assert three_part_brief(features=["底板", "立板"], relations=[]).missing_relations() == ["立板"]
    assert three_part_brief(relations=["立板的下端和底板重叠", "加强筋贴着立板和底板"]).missing_relations() == []


def test_to_dict_has_relations_only_when_set():
    b = make_brief()
    assert "relations" not in b.to_dict()
    b.relations = ["立板的下端和底板的一端重叠"]
    d = b.to_dict()
    keys = list(d)
    assert keys[keys.index("features") + 1] == "relations"
    assert d["relations"] == ["立板的下端和底板的一端重叠"]
    assert "require_relations" not in d
    back = Brief.from_dict(d)
    assert back.relations == b.relations and back.to_dict() == d


def test_render_text_shows_relations():
    b = make_brief()
    assert "位置关系" not in b.render_text()
    b.features = ["底板", "立板"]
    b.relations = ["立板的下端和底板的一端重叠", "立板外侧面和底板端面平齐"]
    lines = b.render_text().splitlines()
    i = lines.index("位置关系：")
    assert lines[i - 2:i] == ["  1. 底板", "  2. 立板"]
    assert lines[i + 1:i + 3] == ["  - 立板的下端和底板的一端重叠", "  - 立板外侧面和底板端面平齐"]


def test_patch_relations_replaces_and_resets_confirmation():
    b = make_brief(confirmed=True)
    changes = b.apply_patch({"relations": [" 立板的下端和底板的一端重叠 "]})
    assert b.relations == ["立板的下端和底板的一端重叠"]
    assert changes == ["位置关系有改动"] and b.confirmed is False
    b.confirmed = True
    assert b.apply_patch({"relations": ["立板的下端和底板的一端重叠"]}) == []   # 没有变化：不清确认
    assert b.confirmed is True
    b.apply_patch({"relations": ["加强筋贴着立板"]})
    assert b.relations == ["加强筋贴着立板"] and b.confirmed is False


@pytest.mark.parametrize("bad", ["立板贴着底板", ["立板贴着底板", ""], ["  "], [1], None])
def test_patch_relations_rejects_bad_values(bad):
    b = make_brief(confirmed=True)
    b.relations = ["原来的一条"]
    before = b.to_dict()
    with pytest.raises(BriefError):
        b.apply_patch({"relations": bad})
    assert b.to_dict() == before and b.confirmed is True


def make_box(brief: Brief) -> ToolBox:
    return ToolBox(Workspace(brief, FeatureList(), []), run_job=Runner())


def test_confirmation_refused_until_relations_complete():
    box = make_box(three_part_brief())
    out = box.call("request_confirmation", {})
    assert json.loads(out.content) == {"error": RELATION_ERROR.format("加强筋")}
    assert not out.end_turn and box.ws.awaiting_confirmation is False
    box.ws.brief.features = ["底板", "立板", "加强筋", "侧板"]
    assert json.loads(box.call("request_confirmation", {}).content)["error"] == RELATION_ERROR.format("加强筋、侧板")
    box.ws.brief.relations.append("加强筋贴着立板和底板，侧板在加强筋外面")
    out = box.call("request_confirmation", {})
    assert out.end_turn and out.kind == "confirm" and box.ws.awaiting_confirmation


def test_confirmation_without_require_relations_is_unchanged():
    box = make_box(three_part_brief(require_relations=False, relations=[]))
    assert box.call("request_confirmation", {}).kind == "confirm"


def test_update_brief_reports_relations_missing():
    box = make_box(three_part_brief())
    body = json.loads(box.call("update_brief", {"features": ["底板", "立板", "加强筋"]}).content)
    assert body["relations_missing"] == ["加强筋"]
    body = json.loads(box.call("update_brief", {"relations": ["立板的下端和底板重叠", "加强筋贴着立板"]}).content)
    assert "relations_missing" not in body and body["changes"] == ["位置关系有改动"]
    legacy = make_box(three_part_brief(require_relations=False))
    assert "relations_missing" not in json.loads(legacy.call("update_brief", {"features": ["底板", "立板", "加强筋"]}).content)
