"""从代码生成 docs/prompts-and-tools.md（3.0 计划 5 Task 2）：系统提示词、17 个工具定义、程序生成给模型的消息、模拟用户的提示词。

文档里的每一段都直接取自代码里的文件和常量；tests/test_prompts_doc.py 会重新生成一遍，和仓库里的逐字比对。
用法：.venv\\Scripts\\python scripts\\export_prompts.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
OUT = ROOT / "docs" / "prompts-and-tools.md"


def _fence(text: str, lang: str = "text") -> str:
    return f"```{lang}\n{text.rstrip()}\n```"


def build() -> str:
    from benchmarks import sim_user
    from cad_agent import tool_common
    from cad_agent.agent.state import PROMPT_DIR, SNAPSHOT_TITLE, V2_PARTS
    from cad_agent.product import flow, tools as ptools
    from cad_agent.staged import messages as msg
    from cad_agent.staged.specs import TOOL_SPECS_V2
    from cad_agent.staged.summary import SUMMARY_HEAD

    out = ["# 提示词与工具定义", "",
           "这份文档由 `scripts/export_prompts.py` 从代码生成，内容和程序实际发给模型的逐字相同。", "",
           "## 系统提示词", "",
           "分阶段流程（默认）的系统提示词由下面几段依次拼成，段与段之间空一行。", ""]
    for i, name in enumerate(V2_PARTS, 1):
        out += [f"### {i}. {name}", "", f"来源：`cad_agent/agent/prompts/{name}`", "",
                _fence((PROMPT_DIR / name).read_text(encoding="utf-8")), ""]
    out += ["## 工具定义", "", f"一共 {len(TOOL_SPECS_V2)} 个工具（OpenAI function 格式）。只有一个零件时，最后 5 个多零件工具不出现。", ""]
    for spec in TOOL_SPECS_V2:
        f = spec["function"]
        out += [f"### {f['name']}", "", f["description"], "", _fence(json.dumps(f["parameters"], ensure_ascii=False, indent=2), "json"), ""]
    hints = [("运行超时", tool_common._hint(None, True, [], [])),
             ("出错位置在某个特征里", tool_common._hint({"feature": "<特征>"}, False, [], [])),
             ("出错位置不在某个特征里", tool_common._hint({"feature": None}, False, [], [])),
             ("有检查没通过", tool_common._hint(None, False, [1], [])),
             ("还缺检查", tool_common._hint(None, False, [], ["<参数>"])),
             ("全部通过", tool_common._hint(None, False, [], [])),
             ("最后检查：有尺寸没被管住", msg.hint_unconstrained(["<参数>"]))]
    out += ["## 程序生成给模型的消息", "",
            "### 每一轮开头的快照标题", "", _fence(SNAPSHOT_TITLE), "",
            "### 一个步骤通过后的小结开头", "", _fence(SUMMARY_HEAD), "",
            "### 一个零件做完后的小结", "", _fence(f"{flow.PART_HEAD}<编号> <名字>\n步骤：<各步标题>\n检查：<n> 项，全部通过。外形：<尺寸>"), "",
            _fence(flow.NEXT_PART), "", _fence(flow.ALL_PARTS), "",
            "### build 返回里的 hint", ""]
    out += [f"- {k}：{v}" for k, v in hints]
    out += ["", "### build_assembly 返回里的 hint", ""]
    out += [f"- {k}：{v}" for k, v in (("运行出错", ptools.HINT_ERROR), ("连接点没挂在真实几何上", ptools.HINT_ANCHOR),
                                         ("装好后穿模", ptools.HINT_OVERLAP), ("运动中碰撞", ptools.HINT_HIT),
                                         ("有别的检查没通过", ptools.HINT_FAILED), ("全部通过", ptools.HINT_DONE))]
    out += ["", "### 关卡报错（不计失败次数）", ""]
    out += [f"- {t}" for t in (msg.NO_PLAN, msg.ALL_PASSED, msg.PROBE_LIMIT_REACHED, ptools.SINGLE_PART, ptools.NO_ASSEMBLY, ptools.PARTS_LEFT)]
    out += ["", "## 模拟用户的提示词", "", "评测时扮演用户的模型用的提示词（来源：`benchmarks/sim_user.py`）。", "",
            "### 系统提示词", "", _fence(sim_user.SYSTEM_TEMPLATE), "", "### 每次发给它的用户消息", "", _fence(sim_user.USER_TEMPLATE), "",
            "### 请它确认需求单时加的一行", "", _fence(sim_user.CONFIRM_LINE), "", "### 用户提出修改后加进隐藏需求的一行", "",
            _fence(sim_user.CHANGE_LINE), ""]
    return "\n".join(out)


def main() -> None:
    OUT.write_text(build(), encoding="utf-8")
    print(f"写出 {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
