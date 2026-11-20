"""3.0 计划 2 Task 6：装配摆放和关节姿态（数都是手算的）。"""

from __future__ import annotations

import pytest

from cad_agent.product.kinematics import (apply_point, explode_directions, frame_from_geometry, joint_value_samples,
                                          poses_at, rest_placements)
from cad_agent.product.model import Assembly, Coupling, Joint, Mate

I4 = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]


def _close(a, b, tol=1e-9):
    assert len(a) == len(b)
    for x, y in zip(a, b):
        assert x == pytest.approx(y, abs=tol), (a, b)


def test_frame_from_cylinder_and_plane():
    f = frame_from_geometry("cylinder", (5, 0, 5), (0, 0, 2), 2, False)
    _close(f.origin, (5, 0, 7)); _close(f.z, (0, 0, 1)); _close(f.x, (1, 0, 0))
    p = frame_from_geometry("plane", (-20, 0, 5), (1, 0, 0), 0, True)
    _close(p.z, (-1, 0, 0)); _close(p.x, (0, 1, 0)); _close(p.origin, (-20, 0, 5))


TOP = frame_from_geometry("plane", (0, 0, 10), (0, 0, 1), 0, False)       # 10 毫米方块的顶面
BOTTOM = frame_from_geometry("plane", (0, 0, 0), (0, 0, -1), 0, False)    # 另一个方块的底面（朝外是 -z）


def _two(align: str, gap=0, angle=0, bottom=BOTTOM) -> tuple:
    asm = Assembly("a", [Mate("m", "a.top", "b.bottom", align, gap, angle)], [], [])
    return asm, {"a.top": TOP, "b.bottom": bottom}


def test_rest_opposite_and_same_align():
    asm, fr = _two("opposite")
    _close(rest_placements(asm, fr, {})["b"], [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 10, 0, 0, 0, 1])
    asm, fr = _two("same", bottom=frame_from_geometry("plane", (0, 0, 0), (0, 0, -1), 0, True))
    _close(rest_placements(asm, fr, {})["b"], [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 10, 0, 0, 0, 1])
    asm, fr = _two("opposite", gap="g")
    _close(rest_placements(asm, fr, {"g": 2})["b"], [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 12, 0, 0, 0, 1])
    asm, fr = _two("opposite", angle=90)
    _close(rest_placements(asm, fr, {})["b"], [0, -1, 0, 0, 1, 0, 0, 0, 0, 0, 1, 10, 0, 0, 0, 1])


def _box() -> tuple:
    hinge = frame_from_geometry("cylinder", (0, 50, 0), (1, 0, 0), 0, False)
    asm = Assembly("body", [Mate("lid_on", "body.hinge", "lid.hinge", "same"),
                            Mate("handle_on", "lid.top", "handle.base", "opposite")],
                   [Joint("open", "lid_on", "revolute", 0, 110, None, "盖子翻开")], [])
    frames = {"body.hinge": hinge, "lid.hinge": hinge,
              "lid.top": frame_from_geometry("plane", (0, 0, 6), (0, 0, 1), 0, False),
              "handle.base": frame_from_geometry("plane", (0, 0, 0), (0, 0, -1), 0, False)}
    return asm, frames


def test_revolute_pose():
    asm, frames = _box()
    rest = rest_placements(asm, frames, {})
    _close(rest["lid"], I4)
    poses = poses_at(asm, frames, rest, {"open": 90}, {})
    # 盖子上的点 (0, 50, 6) 绕过 (0, 50, 0)、沿 x 的轴转 90 度：(0, 50 - 6, 0)
    _close(apply_point(poses["lid"], (0, 50, 6)), (0, 44, 0))
    _close(apply_point(poses["lid"], (0, 0, 6)), (0, 44, -50))


def test_prismatic_pose():
    asm = Assembly("cab", [Mate("slide", "cab.rail", "drawer.rail", "same")],
                   [Joint("pull", "slide", "prismatic", 0, 100, (0.0, -1.0, 0.0), "拉出抽屉")], [])
    f = frame_from_geometry("plane", (0, 0, 4), (0, 0, 1), 0, False)
    frames = {"cab.rail": f, "drawer.rail": f}
    rest = rest_placements(asm, frames, {})
    _close(poses_at(asm, frames, rest, {"pull": 30}, {})["drawer"], [1, 0, 0, 0, 0, 1, 0, -30, 0, 0, 1, 0, 0, 0, 0, 1])
    # 没给值时取 0
    _close(poses_at(asm, frames, rest, {}, {})["drawer"], I4)


def test_subtree_moves_together():
    asm, frames = _box()
    rest = rest_placements(asm, frames, {})
    _close(rest["handle"], [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 6, 0, 0, 0, 1])
    poses = poses_at(asm, frames, rest, {"open": 90}, {})
    # 提手的原点 (0,0,0) 装好时在 (0,0,6)，跟盖子一起转到 (0, 44, -50)
    _close(apply_point(poses["handle"], (0, 0, 0)), (0, 44, -50))


def _gears() -> tuple:
    up = frame_from_geometry("cylinder", (0, 0, 0), (0, 0, 1), 0, False)
    s2 = frame_from_geometry("cylinder", (60, 0, 0), (0, 0, 1), 0, False)
    asm = Assembly("plate", [Mate("m1", "plate.s1", "g1.bore", "same"), Mate("m2", "plate.s2", "g2.bore", "same")],
                   [Joint("j1", "m1", "revolute", 0, 360, None, "小齿轮"), Joint("j2", "m2", "revolute", -180, 0, None, "大齿轮")],
                   [Coupling("j1", "j2", "r", "gear")])
    return asm, {"plate.s1": up, "plate.s2": s2, "g1.bore": up, "g2.bore": up}


def test_gear_coupling():
    asm, frames = _gears()
    rest = rest_placements(asm, frames, {})
    _close(apply_point(rest["g2"], (0, 0, 0)), (60, 0, 0))
    poses = poses_at(asm, frames, rest, {"j1": 36}, {"r": -0.5})
    import math
    c, s = math.cos(math.radians(-18)), math.sin(math.radians(-18))
    _close(apply_point(poses["g2"], (10, 0, 0)), (60 + 10 * c, 10 * s, 0))
    c, s = math.cos(math.radians(36)), math.sin(math.radians(36))
    _close(apply_point(poses["g1"], (10, 0, 0)), (10 * c, 10 * s, 0))


def test_samples_include_both_ends():
    s = joint_value_samples(0, 110, 24)
    assert len(s) == 24 and s[0] == 0 and s[-1] == 110
    assert s[1] == pytest.approx(110 / 23)
    assert joint_value_samples(110, 0, 3) == [0, 55, 110]


def test_explode_directions():
    asm, frames = _two("opposite")
    rest = rest_placements(asm, frames, {})
    d = explode_directions(asm, frames, rest)
    assert d["a"] == (0.0, 0.0, 0.0)
    _close(d["b"], (0, 0, 1))
    # 抽屉沿 -y 滑出：fixed 端的方向是 +y 时取反成 -y（零件在 ground 的 -y 那边）
    f_back = frame_from_geometry("plane", (0, -50, 0), (0, 1, 0), 0, False)
    f_front = frame_from_geometry("plane", (0, 0, 0), (0, -1, 0), 0, False)
    asm2 = Assembly("cab", [Mate("m", "cab.f", "drawer.b", "opposite")], [], [])
    fr2 = {"cab.f": f_back, "drawer.b": f_front}
    rest2 = rest_placements(asm2, fr2, {})
    _close(apply_point(rest2["drawer"], (0, 0, 0)), (0, -50, 0))
    _close(explode_directions(asm2, fr2, rest2)["drawer"], (0, -1, 0))
