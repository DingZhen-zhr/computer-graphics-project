"""分阶段流程给模型和用户的固定文字：逐字取自第二版提示词文档 7.2、7.3、7.4 节。

`<…>` 的部分由函数参数填入；多个编号或名字一律用顿号连接。
"""

from __future__ import annotations

from typing import Iterable

from cad_agent.plan import PLAN_LOCKED, STAGE_HAS_FEATURES, Stage

SEP = "、"

# ---- 7.2 hint ----


def hint_stage_passed(passed_ids: Iterable[str], next_stage: Stage) -> str:
    return (f"阶段 {SEP.join(passed_ids)} 通过。现在是 {next_stage.id}：{next_stage.title}。"
            "先用 set_checks 写这个阶段的检查，再写特征，最后 build。")


def hint_unconstrained(names: Iterable[str]) -> str:
    return (f"这些参数改掉 20% 之后，所有检查仍然通过：{SEP.join(names)}。要么模型没有真正用到它，要么没有检查约束它。"
            "先用 inspect 或 probe 弄清是哪一种，再改特征或补检查，然后 build。")


# ---- 7.3 关卡报错 ----

NO_PLAN = "还没有计划。先调用 set_plan 把零件拆成阶段。"
ALL_PASSED = "所有阶段都已通过。要加新的特征，先用 set_plan 在末尾追加阶段。"
PROBE_LIMIT_REACHED = "这个阶段的 probe 已经用了 10 次，不能再用了。把已经试明白的写进特征，然后 build。"


def need_checks(stage_id: str) -> str:
    return f"阶段 {stage_id} 还没有检查，不能写这个阶段的特征。先用 set_checks（stage 写 {stage_id}）写这个阶段做完后必须成立的检查。"


def all_passed() -> str:
    return ALL_PASSED


def plan_locked(stage_id: str) -> str:
    return PLAN_LOCKED.format(id=stage_id)


def stage_has_features(stage_id: str, slugs: Iterable[str]) -> str:
    return STAGE_HAS_FEATURES.format(id=stage_id, slugs=SEP.join(slugs))


def unknown_stage(stage: str, ids: Iterable[str]) -> str:
    return f"没有阶段 {stage}。现在的阶段有：{SEP.join(ids)}。"


def future_stage(stage: str, current_id: str) -> str:
    return f"阶段 {stage} 还没轮到。现在是 {current_id}，先把它做完。"


def before_other_stage(stage_id: str) -> str:
    return f"before 只能指向同一阶段（{stage_id}）里的特征。"


def build_no_features(stage_id: str) -> str:
    return f"阶段 {stage_id} 还没有特征。先写这个阶段的特征再 build。"


def build_no_checks(stage_id: str) -> str:
    return f"阶段 {stage_id} 还没有检查。先用 set_checks 写这个阶段做完后必须成立的检查。"


def ref_unknown(name: str, names: Iterable[str]) -> str:
    return f"没有叫 {name} 的文档。可以读的有：{SEP.join(names)}。"


def ref_no_section(name: str, section: str, sections: Iterable[str]) -> str:
    return f"{name} 里没有叫 {section} 的小节。它的小节有：{SEP.join(sections)}。"


# ---- 7.4 每阶段工具调用的提醒和上限 ----


def stage_calls_left(n: int) -> str:
    return f"这个阶段的工具调用只剩 {n} 次"


def stage_cap_text(stage_id: str, title: str, n: int) -> str:
    return (f"阶段 {stage_id}（{title}）的工具调用已经达到上限（{n} 次），先停下来了。需求单、计划和已经通过的阶段都保留着，"
            "你可以说「继续」让我接着做，或者告诉我该怎么调整。")
