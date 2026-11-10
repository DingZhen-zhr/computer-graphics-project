"""从两份提示词文档生成 cad_agent/staged/specs.py（分阶段流程的 12 个工具说明）。

- 第二版提示词文档第 6 节的 json 块：update_brief、set_plan、upsert_feature、build、probe、read_reference；
- 1.1 版提示词文档第 4 节的同名 json 块：ask_user、request_confirmation、remove_feature、inspect、api_help；
- set_checks 按第二版第 6 节写的拼法，从 1.1 版的 set_checks 算出来。

用法：.venv\\Scripts\\python scripts\\gen_staged_specs.py
"""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLANS = ROOT / "docs" / "superpowers" / "plans"
DOC_V2 = PLANS / "2026-11-10-caliper-1-kernel-prompts.md"
DOC_V11 = PLANS / "2026-11-09-cad-agent-v1.1-prompts.md"
OUT = ROOT / "cad_agent" / "staged" / "specs.py"
REUSED = ("ask_user", "request_confirmation", "remove_feature", "inspect", "api_help")


def _section(doc: Path, start: str, end: str) -> str:
    return doc.read_text(encoding="utf-8").split(start)[1].split(end)[0]


def _json_blocks(text: str) -> list[str]:
    return re.findall(r"```json\n(.*?)\n```", text, flags=re.S)


def build_raw() -> tuple[list[str], list[str]]:
    sec6 = _section(DOC_V2, "## 6. 工具说明（分阶段流程）", "## 7. build 的返回")
    order = re.search(r"顺序：(.+?)。", sec6).group(1).split("、")
    new = {json.loads(b)["name"]: b for b in _json_blocks(sec6)}
    old_sec = _section(DOC_V11, "## 4. 工具说明", "## 5. 程序代按按钮时用到的原文")
    old = {json.loads(b)["name"]: b for b in _json_blocks(old_sec)}

    head = re.findall(r"```text\n(.*?)\n```", sec6.split("### set_checks")[1].split("### build")[0], flags=re.S)[0]
    sc = json.loads(old["set_checks"])
    desc = sc["description"]
    sc["description"] = head + desc[desc.index("\n表达式里可以用"):]
    params = copy.deepcopy(sc["parameters"])
    props = {"stage": {"type": "string", "description": "阶段编号，如 s1"}}
    props.update(params["properties"])
    params["properties"] = props
    params["required"] = ["stage", "checks"]
    params["properties"]["checks"]["items"]["properties"]["holds"] = {"type": "string", "enum": ["from_here", "here_only"]}
    sc["parameters"] = params

    raw: list[str] = []
    for name in order:
        if name == "set_checks":
            raw.append(json.dumps(sc, ensure_ascii=False, indent=2))
        elif name in REUSED:
            raw.append(old[name])
        else:
            raw.append(new[name])
    return order, raw


def main() -> None:
    order, raw = build_raw()
    assert len(order) == 12, order
    parts = [
        '"""分阶段流程的工具说明（OpenAI function 格式）。\n\n'
        "由 scripts/gen_staged_specs.py 生成，不要手改。内容逐字取自第二版提示词文档第 6 节和 1.1 版提示词文档第 4 节；\n"
        'set_checks 按第 6 节写的拼法算出。tests/test_staged_tools.py 会逐项比对。\n"""\n\n',
        "from __future__ import annotations\n\nimport json\n\n_RAW: list[str] = [\n",
    ]
    for r in raw:
        assert "'''" not in r
        parts.append("    r'''" + r + "''',\n")
    parts.append(
        "]\n\n"
        'TOOL_SPECS_V2: list[dict] = [{"type": "function", "function": json.loads(raw)} for raw in _RAW]\n'
        'TOOL_NAMES_V2: list[str] = [spec["function"]["name"] for spec in TOOL_SPECS_V2]\n'
        "# 需求单不能建模时只给这几个\n"
        'PRE_CONFIRM_TOOLS_V2: list[str] = ["update_brief", "ask_user", "request_confirmation", "api_help", "read_reference"]\n'
    )
    OUT.write_text("".join(parts), encoding="utf-8")
    print(f"写出 {OUT.relative_to(ROOT)}：{len(raw)} 个工具")


if __name__ == "__main__":
    main()
