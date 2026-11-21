"""装配几何里不用建模内核的纯计算部分。"""

from __future__ import annotations

import math

import pytest

from cad_agent.sandbox.assembly_geom import line_distance_angle


def test_parallel_axes_distance():
    d, a = line_distance_angle((0, 0, 0), (0, 0, 1), (10, 0, 5), (0, 0, 1))
    assert d == pytest.approx(10) and a == pytest.approx(0)


def test_nearly_parallel_offset_axes_are_not_coaxial():
    """两条轴在同一平面里、偏开 10 毫米、稍微斜一点：异面直线公式会算成 0，要按点到线算（3.0 复查第 9 条）。"""
    t = math.radians(0.1)
    d, a = line_distance_angle((0, 0, 0), (0, 0, 1), (10, 0, 0), (math.sin(t), 0, math.cos(t)))
    assert a == pytest.approx(0.1, abs=1e-6) and d == pytest.approx(10, abs=0.01)


def test_skew_axes_distance():
    d, a = line_distance_angle((0, 0, 0), (1, 0, 0), (0, 5, 3), (0, 0, 1))
    assert d == pytest.approx(5) and a == pytest.approx(90)
