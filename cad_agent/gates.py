"""流程开关（设计文档第 3.10 节）：每道新关卡一个开关，默认全开。

全部关掉（Gates.legacy()）就是 1.2 版的单阶段流程；ToolBox 不传 gates 时就是它。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Gates:
    staged: bool = True          # 分阶段流程
    mutation_check: bool = True  # 参数扰动验证
    visual_review: bool = True   # 看图审查（计划 2 实现）
    cases: bool = True           # 案例库

    @classmethod
    def legacy(cls) -> "Gates":
        """1.2 版的流程：四项全关。"""
        return cls(staged=False, mutation_check=False, visual_review=False, cases=False)
