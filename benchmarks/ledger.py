"""评测的账本（3.0 计划 4 Task 1）：所有真实调用记进同一个账本，按调用结束时刻的价格（空闲 / 高峰）累计，到上限立刻停。

账本文件不进 git（benchmarks/results/ 已经忽略）；读不出来就拒绝开跑，不当作"一分钱没花"重新开始。
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Literal

from cad_agent.llm.client import LLM, LLMReply, call_cost

LEDGER = Path(__file__).parent / "results" / "ledger-v3.json"


class LedgerError(Exception):
    """账本文件坏了：拒绝开跑。"""


class BudgetExceeded(Exception):
    """累计花费到了上限：当前任务立刻停。"""


class TaskCapExceeded(BudgetExceeded):
    """这一个任务的花费到了它自己的上限：这个任务停，下一个任务照常开始（3.0 修改清单第 1 条）。"""


@dataclass
class Ledger:
    cap: float
    spent: float
    entries: list[dict] = field(default_factory=list)
    path: Path | None = None

    @classmethod
    def load(cls, path: Path, cap: float) -> "Ledger":
        path = Path(path)
        if not path.exists():
            led = cls(cap=cap, spent=0.0, entries=[], path=path)
            led._save()
            return led
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            entries = list(data["entries"])
            spent = round(sum(float(e["cost"]) for e in entries), 6)
        except (OSError, ValueError, KeyError, TypeError) as e:
            raise LedgerError(f"账本文件 {path} 读不出来（{type(e).__name__}），为了不重复花钱，先不跑。请检查或恢复这个文件。") from e
        return cls(cap=cap, spent=spent, entries=entries, path=path)

    def _save(self) -> None:
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(f".{self.path.name}.{os.getpid()}.tmp")
        tmp.write_text(json.dumps({"cap": self.cap, "spent": round(self.spent, 6), "entries": self.entries}, ensure_ascii=False, indent=1),
                       encoding="utf-8")
        os.replace(tmp, self.path)

    def add(self, label: str, task: str, who: Literal["agent", "sim_user"], cost: float,
            priced_as: Literal["peak", "offpeak"], ts: datetime | None = None) -> None:
        self.entries.append({"ts": (ts or datetime.now()).isoformat(timespec="seconds"), "label": label, "task": task, "who": who,
                             "cost": round(float(cost), 6), "priced_as": priced_as})
        self.spent = round(self.spent + float(cost), 6)
        self._save()
        if self.spent >= self.cap:
            raise BudgetExceeded(f"已花费 ¥{self.spent:.2f}，到了上限 ¥{self.cap:.2f}")

    def task_spent(self, label: str, task: str) -> float:
        return round(sum(e["cost"] for e in self.entries if e["label"] == label and e["task"] == task), 6)

    def remaining(self) -> float:
        return max(0.0, round(self.cap - self.spent, 6))

    def by_label(self) -> dict[str, float]:
        out: dict[str, float] = {}
        for e in self.entries:
            out[e["label"]] = round(out.get(e["label"], 0.0) + e["cost"], 6)
        return out


class _Metered:
    """包在 LLM 外面：每次调用之后按调用结束时刻的价格重新算费用，记进账本（到上限时抛 BudgetExceeded）。"""

    def __init__(self, inner: LLM, ledger: Ledger, config, label: str, task: str, who: str, now: Callable[[], datetime],
                 task_cap: float | None = None) -> None:
        self.inner, self.ledger, self.config, self.label, self.task, self.who, self.now = inner, ledger, config, label, task, who, now
        self.task_cap = task_cap

    def chat(self, messages: list[dict], tools: list[dict], **kw) -> LLMReply:   # noqa: ANN003 - 原样转给真正的模型
        reply = self.inner.chat(messages, tools, **kw)
        at = self.now()
        pricing = self.config.price_at(at)
        priced_as = "offpeak" if self.config.is_offpeak(at) else "peak"
        cost = call_cost(reply.usage or {}, pricing) or 0.0
        reply.cost = cost
        self.ledger.add(self.label, self.task, self.who, cost, priced_as, ts=at)
        if self.task_cap is not None and self.ledger.task_spent(self.label, self.task) >= self.task_cap:
            raise TaskCapExceeded(f"任务 {self.task} 已花费 ¥{self.ledger.task_spent(self.label, self.task):.2f}，到了这个任务的上限 ¥{self.task_cap:.2f}")
        return reply


def metered(llm: LLM, ledger: Ledger, config, label: str, task: str, who: str,
            now: Callable[[], datetime] = datetime.now, task_cap: float | None = None) -> LLM:
    return _Metered(llm, ledger, config, label, task, who, now, task_cap)
