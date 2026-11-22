"""3.0 修改清单第 3 条：验收用到的尺寸，模拟用户要能从隐藏需求里说出来（只查 toolbox 第一轮漏写的几项）。"""

from __future__ import annotations

from benchmarks.run import load_task


def test_toolbox_hidden_spec_states_what_acceptance_measures():
    spec = load_task("toolbox")["hidden_spec"]
    for words in ("提手总高 17 mm", "握把直径 8 mm", "握把中心离盖子顶面 13 mm", "铰链耳外径 8 mm",
                  "x = -60 到 -40、-10 到 10、40 到 60", "x = -39.5 到 -10.5、10.5 到 39.5"):
        assert words in spec, words
