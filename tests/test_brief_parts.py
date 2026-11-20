"""3.0 计划 2 Task 2：需求单写零件和运动。"""

from __future__ import annotations

import copy

import pytest

from cad_agent.brief import Brief, BriefError


def _p(name: str, value: float, part: str | None = None, note: str = "") -> dict:
    d = {"name": name, "value": value, "unit": "mm", "source": "user", "note": note}
    if part is not None:
        d["part"] = part
    return d


PARTS = [
    {"id": "body", "name": "盒体", "material": "abs", "features": ["底板", "四面墙"]},
    {"id": "lid", "name": "盖子", "material": "anodized", "color": "#4767E8", "features": ["盖板"]},
]


def _multi() -> Brief:
    b = Brief()
    b.apply_patch({"part": {"name": "工具盒", "purpose": "装工具"}, "parts": PARTS,
                   "set_params": [_p("box_l", 160), _p("lid_t", 6, "lid", "盖子厚度（建议）")],
                   "motions": ["盖子绕后边的铰链向上翻开，0 到 110 度"],
                   "relations": ["盖子盖在盒体上沿，后边用铰链连接"]})
    return b


def test_single_part_brief_unchanged():
    b = Brief()
    b.apply_patch({"part": {"name": "板"}, "set_params": [_p("w", 60)], "features": ["板"]})
    d = b.to_dict()
    assert set(d) == {"part", "params", "features", "open_questions", "confirmed"}
    assert set(d["params"][0]) == {"name", "value", "unit", "source", "note"}
    assert not b.is_multipart()


def test_parts_round_trip():
    b = _multi()
    d = b.to_dict()
    assert d["parts"][1] == {"id": "lid", "name": "盖子", "material": "anodized", "color": "#4767E8", "features": ["盖板"]}
    assert d["parts"][0]["color"] is None
    assert d["motions"] == ["盖子绕后边的铰链向上翻开，0 到 110 度"]
    assert d["params"][1]["part"] == "lid"
    again = Brief.from_dict(copy.deepcopy(d))
    assert again.to_dict() == d
    assert again.is_multipart()


@pytest.mark.parametrize("bad", [
    [PARTS[0], {**PARTS[1], "id": "body"}],
    [PARTS[0], {**PARTS[1], "id": "Lid"}],
    [PARTS[0], {**PARTS[1], "material": "gold"}],
    [PARTS[0], {**PARTS[1], "color": "blue"}],
    [PARTS[0], {**PARTS[1], "color": "#12345"}],
])
def test_part_ids_and_materials_validated(bad):
    b = _multi()
    before = b.to_dict()
    with pytest.raises(BriefError):
        b.apply_patch({"parts": bad})
    assert b.to_dict() == before


def test_param_part_must_exist():
    b = _multi()
    before = b.to_dict()
    with pytest.raises(BriefError):
        b.apply_patch({"set_params": [_p("x", 1, "handle")]})
    assert b.to_dict() == before
    # 删掉一个零件时，属于它的参数还在也不行
    with pytest.raises(BriefError):
        b.apply_patch({"parts": [PARTS[0], {**PARTS[1], "id": "cover"}]})
    assert b.to_dict() == before


def test_one_part_in_parts_rejected():
    b = Brief()
    with pytest.raises(BriefError):
        b.apply_patch({"parts": [PARTS[0]]})
    b.apply_patch({"parts": []})
    assert b.parts == []


def test_changing_parts_resets_confirmation():
    b = _multi()
    b.confirmed = True
    b.apply_patch({"parts": [PARTS[0], {**PARTS[1], "features": ["盖板", "提手"]}]})
    assert not b.confirmed
    b.confirmed = True
    b.apply_patch({"motions": ["盖子翻开 0 到 95 度"]})
    assert not b.confirmed
    b.confirmed = True
    b.apply_patch({"motions": ["盖子翻开 0 到 95 度"]})   # 没有变化
    assert b.confirmed


def test_missing_relations_uses_part_names():
    b = _multi()
    b.require_relations = True
    assert b.missing_relations() == []
    b.apply_patch({"relations": ["盒体放在桌上"]})
    assert b.missing_relations() == ["盖子"]


def test_params_of():
    b = _multi()
    assert [p.name for p in b.params_of(None)] == ["box_l"]
    assert [p.name for p in b.params_of("lid")] == ["lid_t"]
    assert b.params_of("body") == []


def test_render_text_lists_parts_and_motions():
    text = _multi().render_text()
    assert "零件：" in text and "body 盒体（ABS 塑料）：底板；四面墙" in text
    assert "lid 盖子（阳极氧化铝）：盖板" in text
    assert "会动的地方：" in text and "盖子绕后边的铰链向上翻开" in text
    assert text.index("产品参数") < text.index("box_l") < text.index("盖子的参数") < text.index("lid_t")
