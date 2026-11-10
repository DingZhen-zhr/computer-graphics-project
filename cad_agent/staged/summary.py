"""阶段小结：一个阶段通过后，轮内的工具往来折叠成这段文字（第二版提示词文档第 4 节）。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from cad_agent.staged.build import Advance

if TYPE_CHECKING:
    from cad_agent.notebook import Feature
    from cad_agent.tools import Workspace

SUMMARY_HEAD = "【阶段已通过（程序生成）】"


def num(x: float) -> str:
    return f"{x:.4f}".rstrip("0").rstrip(".")


def feature_block(features: list["Feature"]) -> str:
    """快照和小结里的特征列表：每个特征一行标题、下面接代码，特征之间空一行；没有时写"无"。"""
    return "\n\n".join(f"--- {f.slug}（{f.role}，{f.stage}）---\n{f.code}" for f in features) or "无"


def stage_summary(ws: "Workspace", adv: Advance) -> str:
    runs = {sr.stage_id: sr.run for sr in adv.runs}
    parts = []
    for sid in adv.passed:
        stage, run = ws.plan.get(sid), runs[sid]
        size, volume = run.facts.get("size", [0, 0, 0]), run.facts.get("volume", 0)
        parts.append("\n".join([
            f"{SUMMARY_HEAD}{sid} {stage.title}",
            "特征：",
            feature_block(ws.features.in_stage(sid)),
            f"检查：{len(run.checks)} 条，全部通过。",
            f"外形：{' × '.join(num(v) for v in size)}，体积 {num(volume)}",
        ]))
    text = "\n\n".join(parts)
    nxt = ws.plan.current()
    if nxt is not None:
        text += f"\n\n现在是 {nxt.id}：{nxt.title}。做完的标志：{nxt.done_when}"
    return text
