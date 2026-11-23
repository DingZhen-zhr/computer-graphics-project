"""3.0 修改清单第 3 条：验收用到的尺寸，模拟用户要能从隐藏需求里说出来（只查 toolbox 第一轮漏写的几项）。"""

from __future__ import annotations

from benchmarks.run import load_task


def test_toolbox_hidden_spec_states_what_acceptance_measures():
    spec = load_task("toolbox")["hidden_spec"]
    for words in ("提手总高 17 mm", "握把直径 8 mm", "握把中心离盖子顶面 13 mm", "铰链耳外径 8 mm",
                  "x = -60 到 -40、-10 到 10、40 到 60", "x = -39.5 到 -10.5、10.5 到 39.5"):
        assert words in spec, words


def test_toolbox_handle_span_is_defined():
    """计划 6 Task 5（F7）：写清"跨距"的量法，照参考答案 tests/references_v3.py::_handle。"""
    spec = load_task("toolbox")["hidden_spec"]
    for words in ("跨距 70 mm 是提手两端外缘之间的总长", "立柱 8×8 mm 的方柱，外侧和底板两端齐平"):
        assert words in spec, words
