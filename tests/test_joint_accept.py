"""3.0 修改清单第 2 条：同一个转动写成"轴反过来、角度也反过来"时，验收按同一个运动来判（不调用 SCA）。"""

from __future__ import annotations

import benchmarks.assembly_accept as aa

HINGE = {"id": "hinge", "type": "joint", "kind": "revolute", "axis": [1, 0, 0], "through": [0, 55, 63], "pos_tol": 0.5, "lo": 0, "hi": 110}


def _axes(direction: list[float], rng: list[float]) -> dict:
    return {"j": ([0.0, 55.0, 63.0], direction, {"type": "revolute", "range": rng, "label": "盖子翻开"}, "lid")}


def test_flipped_axis_and_range_is_the_same_hinge():
    a = aa._joint(HINGE, _axes([-1.0, 0.0, 0.0], [0, 110]), {})
    b = aa._joint(HINGE, _axes([1.0, 0.0, 0.0], [-110, 0]), {})
    assert a["passed"] and b["passed"]
    assert a["measured"] == 110 and b["measured"] == 110
    # 换算到同一种写法后，转动方向一样
    assert [a["sign"] * v for v in (-1.0, 0.0, 0.0)] == [b["sign"] * v for v in (1.0, 0.0, 0.0)]


def test_too_small_range_still_fails_either_way():
    assert not aa._joint(HINGE, _axes([1.0, 0.0, 0.0], [-50, 0]), {})["passed"]
    assert not aa._joint(HINGE, _axes([1.0, 0.0, 0.0], [0, 50]), {})["passed"]


def test_at_pose_turns_by_the_matched_sign(monkeypatch):
    seen = []
    monkeypatch.setattr(aa, "_rot", lambda d, v, p: seen.append((list(d), v)) or "m")
    monkeypatch.setattr(aa, "_subtree", lambda asm, root: set())
    monkeypatch.setattr(aa, "_check", lambda c, shapes: {"passed": True})
    c = {"id": "open-90", "type": "at_pose", "joint": "hinge", "value": 90, "checks": []}
    aa._at_pose(c, {"hinge": "j"}, _axes([1.0, 0.0, 0.0], [-110, 0]), {"couplings": []}, {}, {}, {"j": -1})
    assert seen == [([1.0, 0.0, 0.0], -90.0)]
