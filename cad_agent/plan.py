"""分阶段计划：纯数据，不依赖 SCA，也不依赖 tools.py（设计文档第 3.3 节）。

计划是 1 到 12 个阶段，编号按位置是 s1、s2……；第一个未通过的阶段就是当前阶段。
set_plan 的校验与合并在 revise 里。
"""

from __future__ import annotations

from dataclasses import dataclass

MAX_STAGES = 12
# 提示词文档 7.3 的两条原文（set_plan 的关卡报错）
PLAN_LOCKED = "阶段 {id} 已经通过，不能在 set_plan 里改它。要改它的内容，直接修改这个阶段的特征或检查。"
STAGE_HAS_FEATURES = "阶段 {id} 里还有特征（{slugs}），不能删掉这个阶段。先删掉或改写这些特征。"


class PlanError(ValueError):
    """计划写得不对；信息是中文，直接返回给模型。"""


@dataclass
class Stage:
    id: str            # "s1"、"s2"……按位置编号
    title: str
    done_when: str
    passed: bool = False


def stage_id(index: int) -> str:
    """第 index 个阶段（从 0 数）的编号。"""
    return f"s{index + 1}"


@dataclass
class Plan:
    stages: list[Stage]

    def current(self) -> Stage | None:
        """第一个未通过的阶段；全部通过时是 None。"""
        return next((s for s in self.stages if not s.passed), None)

    def complete(self) -> bool:
        return all(s.passed for s in self.stages)

    def ids(self) -> list[str]:
        return [s.id for s in self.stages]

    def index(self, stage_id: str) -> int:
        for i, s in enumerate(self.stages):
            if s.id == stage_id:
                return i
        raise PlanError(f"没有阶段 {stage_id}。现在的阶段有：{'、'.join(self.ids())}。")

    def get(self, stage_id: str) -> Stage:
        return self.stages[self.index(stage_id)]

    def mark_passed(self, stage_id: str) -> None:
        self.get(stage_id).passed = True

    def invalidate_from(self, stage_id: str) -> None:
        """这个阶段和它后面的阶段都变回未通过。"""
        for s in self.stages[self.index(stage_id):]:
            s.passed = False

    def invalidate_all(self) -> None:
        for s in self.stages:
            s.passed = False

    def to_list(self) -> list[dict]:
        return [{"id": s.id, "title": s.title, "done_when": s.done_when, "passed": s.passed} for s in self.stages]

    @classmethod
    def from_list(cls, raw: list[dict]) -> "Plan":
        return cls([Stage(d["id"], d["title"], d["done_when"], bool(d.get("passed", False))) for d in raw])


def _parse_raw(raw: object) -> list[tuple[str, str]]:
    """校验 set_plan 传来的 stages：1 到 12 个 {"title", "done_when"}，都是非空文字。"""
    if not isinstance(raw, list):
        raise PlanError("stages 必须是数组，每一项写一个阶段：{\"title\": ..., \"done_when\": ...}")
    if not 1 <= len(raw) <= MAX_STAGES:
        raise PlanError(f"计划要有 1 到 {MAX_STAGES} 个阶段，收到 {len(raw)} 个")
    out: list[tuple[str, str]] = []
    for i, item in enumerate(raw, 1):
        if not isinstance(item, dict):
            raise PlanError(f"第 {i} 个阶段必须是对象，含 title 和 done_when")
        for key in ("title", "done_when"):
            if key not in item:
                raise PlanError(f"第 {i} 个阶段缺少 {key}")
            if not isinstance(item[key], str) or not item[key].strip():
                raise PlanError(f"第 {i} 个阶段的 {key} 必须是非空文字")
        out.append((item["title"].strip(), item["done_when"].strip()))
    return out


def revise(old: Plan | None, raw: object, slugs_by_stage: dict[str, list[str]]) -> Plan:
    """set_plan 的校验与合并。

    old 里已通过的阶段必须原样排在新计划最前面；新计划比旧计划短时，被去掉的阶段里不能还有特征。
    返回的新计划按位置重新编号，保留下来的已通过阶段仍是已通过。出错时抛 PlanError，old 不变。
    """
    items = _parse_raw(raw)
    if old is not None:
        for i, s in enumerate(old.stages):
            if not s.passed:
                continue
            if i >= len(items) or items[i] != (s.title, s.done_when):
                raise PlanError(PLAN_LOCKED.format(id=s.id))
        for s in old.stages[len(items):]:
            slugs = slugs_by_stage.get(s.id) or []
            if slugs:
                raise PlanError(STAGE_HAS_FEATURES.format(id=s.id, slugs="、".join(slugs)))
    stages = []
    for i, (title, done_when) in enumerate(items):
        kept = old is not None and i < len(old.stages) and old.stages[i].passed
        stages.append(Stage(stage_id(i), title, done_when, passed=kept))
    return Plan(stages)
