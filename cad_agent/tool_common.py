"""工具层共用的小件：工具的返回、JSON 文字、给模型看的报错和 hint（hint 原文取自 1.1 版提示词文档第 4 节）。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from cad_agent.sandbox.execute import RunResult

INSPECT_LIMIT = 30


@dataclass
class ToolOutcome:
    content: str                    # 给模型看的 JSON 文本
    end_turn: bool = False          # 为真时本轮到此结束，等用户回复
    kind: str | None = None         # "question" 或 "confirm"
    build: RunResult | None = None  # 只有 build 工具会带
    deliverable: bool = False       # 只有 build 全部通过且不缺检查时为真


def _json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False)


def _err(message: str, **extra: Any) -> ToolOutcome:
    return ToolOutcome(_json({"error": message, **extra}))


def _error_for_model(err: dict) -> dict:
    return {"feature": err.get("cell"), "type": err["type"], "message": err["message"]}


def _hint(error: dict | None, timed_out: bool, failed: list, missing: list[str]) -> str:
    if timed_out:
        return "运行超时了。检查是否写了很慢的操作，比如过多的阵列数量或过细的样条。"
    if error and error["feature"]:
        return f"只修改特征 {error['feature']}。拿不准函数用法时先用 api_help 查。"
    if error:
        return "出错位置不在某个特征里，多半是参数或特征之间的引用有问题。先检查参数名和变量名是否一致。"
    if failed:
        return "先看每条 detail 里选中了哪些几何：选错了就改检查条件，选对了但数值不对就改模型。"
    if missing:
        return f"模型和检查都通过了，但这些用户参数还没有检查：{'、'.join(missing)}。补上检查后再 build。"
    return "全部通过，程序会自动交付。"
