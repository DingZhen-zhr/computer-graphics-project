"""从工具盒的标准答案（tests/references_v3.py）生成多零件的走查剧本 scripts/demo_script_multi.json。

剧本对应四条用户消息："做一个带铰链盖的工具盒" / 回答两个问题 / 确认 / "盖子最多翻到 95 度"。
零件、步骤、特征、检查、连接点、装配都取自标准答案，和 tests/test_benchmark_references_v3.py 验过的完全一样。
用法：.venv\\Scripts\\python scripts\\gen_demo_multi.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))
from references_v3 import TOOLBOX_PARAMS, toolbox  # noqa: E402

OUT = ROOT / "scripts" / "demo_script_multi.json"
NOTES = {"box_l": "盒子长度（x 方向）", "box_w": "盒子宽度（y 方向）", "box_h": "盒子高度", "wall": "侧壁厚", "floor_t": "底厚",
         "lid_t": "盖子厚度", "hinge_off": "铰链轴在后壁外侧多远", "pin_d": "铰链轴直径", "handle_span": "提手跨距", "lid_max": "盖子最多翻开的角度"}
FIRST = ("box_l", "box_w", "box_h", "wall", "floor_t", "lid_t", "pin_d", "handle_span")


def _param(name: str, value: float, unit: str) -> dict:
    return {"name": name, "value": value, "unit": unit, "source": "user", "note": NOTES[name]}


def _strip(c: dict) -> dict:
    return {k: v for k, v in c.items() if k != "stage"}


def build() -> list[dict]:
    ws = toolbox()
    params = {n: (v, u) for n, v, u in TOOLBOX_PARAMS}
    parts = [{"id": p.id, "name": p.name, "material": p.material, "features": p.features} for p in ws.brief.parts]
    replies = [
        {"content": "好的，做一个带铰链盖的工具盒：盒体、盖子、铰链轴、提手四个零件。先问两件事。",
         "tool_calls": [
             {"name": "update_brief", "args": {
                 "part": {"name": "工具盒", "purpose": "装小工具，盖子能翻开"},
                 "parts": parts,
                 "set_params": [_param(n, *params[n]) for n in FIRST],
                 "relations": ["盖子盖上时压在盒体上沿，后边用铰链和盒体连起来", "铰链轴穿过盒体和盖子的铰链耳",
                               "提手装在盖子顶面正中"],
                 "motions": ["盖子绕后边的铰链向上翻开，0 到 110 度"],
                 "open_questions": ["铰链轴离后壁多远？", "盖子最多翻开多少度？"]}},
             {"name": "ask_user", "args": {"questions": ["铰链轴放在后壁外侧多远？建议 5 mm。", "盖子最多翻开多少度？建议 110 度。"]}}]},
        {"content": "记下了。需求单整理好了，请你看一下。",
         "tool_calls": [{"name": "update_brief", "args": {
             "set_params": [_param("hinge_off", *params["hinge_off"]), _param("lid_max", *params["lid_max"])],
             "open_questions": []}}]},
    ]
    for p in ws.brief.parts:
        st = ws.parts[p.id]
        replies.append({"content": f"开始做{p.name}。", "tool_calls": [
            {"name": "set_plan", "args": {"stages": [{"title": s.title, "done_when": s.done_when} for s in st.plan.stages]}}]})
        for s in st.plan.stages:
            calls = [{"name": "set_checks", "args": {"stage": s.id, "checks": [_strip(c) for c in st.checks_raw if c["stage"] == s.id]}}]
            calls += [{"name": "upsert_feature", "args": {"slug": f.slug, "role": f.role, "code": f.code}}
                      for f in st.features.items if f.stage == s.id]
            calls.append({"name": "build", "args": {}})
            replies.append({"content": f"{p.name}：{s.title}。", "tool_calls": calls})
    connect = [{"name": "set_connectors", "args": {"part": pid, "connectors": [c.to_dict() for c in st.connectors]}}
               for pid, st in ws.parts.items()]
    connect += [{"name": "set_assembly", "args": ws.assembly.to_dict()}, {"name": "build_assembly", "args": {}}]
    replies.append({"content": "四个零件都做好了，现在装起来，检查盖子翻开时碰不碰盒体。", "tool_calls": connect})
    replies.append({"content": "好的，把盖子最多翻开的角度改成 95 度，再装一次检查。", "tool_calls": [
        {"name": "update_brief", "args": {"set_params": [_param("lid_max", 95, "deg")]}}, {"name": "build_assembly", "args": {}}]})
    return replies


def main() -> None:
    OUT.write_text(json.dumps(build(), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"写出 {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
