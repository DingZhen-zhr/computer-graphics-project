"""3.0 计划 2 Task 11：多零件和零件设计感的提示词。"""

from __future__ import annotations

import json
import re
from pathlib import Path

from cad_agent.agent.state import PROMPT_DIR, load_system_prompt, render_snapshot
from cad_agent.brief import Brief
from cad_agent.checks.expr import expr_names
from cad_agent.notebook import Feature, FeatureList
from cad_agent.product.spec import parse_assembly, parse_connectors
from cad_agent.product.workspace import ensure_parts
from cad_agent.tools import Workspace
from helpers_staged import staged_brief

PROMPTS = Path(__file__).resolve().parents[1] / "docs/superpowers/plans/2026-11-20-datum-2-multipart-prompts.md"
WHERE = [["geom.type", "==", "PLANE"]]


def test_system_multipart_verbatim():
    doc = PROMPTS.read_text(encoding="utf-8").split("## 1. 系统提示词的新增两段", 1)[1]
    [block] = re.findall(r"```text\n(.*?)\n```", doc.split("---", 1)[0], flags=re.S)
    assert (PROMPT_DIR / "system_multipart.md").read_text(encoding="utf-8").rstrip("\n") == block


def test_system_prompt_order():
    full = load_system_prompt(True)
    names = ("system_v2.md", "system_multipart.md", "references_index.md", "sca_cheatsheet.md", "sca_cheatsheet_more.md")
    heads = [(PROMPT_DIR / n).read_text(encoding="utf-8").strip().splitlines()[0] for n in names]
    pos = [full.index(h) for h in heads]
    assert pos == sorted(pos)
    assert "## 多个零件的产品" in full and "## 零件要做得好看、好用" in full


def _multi_ws() -> Workspace:
    b = Brief()
    b.apply_patch({"part": {"name": "工具盒"},
                   "parts": [{"id": "body", "name": "盒体", "material": "abs", "features": ["盒体"]},
                             {"id": "lid", "name": "盖子", "material": "anodized", "features": ["盖板"]}],
                   "set_params": [{"name": "w", "value": 40, "unit": "mm", "source": "user", "note": ""}]})
    b.confirmed = True
    ws = Workspace(b, FeatureList(), [])
    ensure_parts(ws)
    ws.features.upsert(Feature("shell", "build", "shell = scad.make_box_rsolid(width=w, height=w, depth=10, bottom_face_center=(0, 0, 0))", "s1"))
    return ws


def test_snapshot_lists_parts():
    ws = _multi_ws()
    snap = render_snapshot(ws, True)
    assert "零件：\nbody 盒体（ABS 塑料）—— 当前\nlid 盖子（阳极氧化铝）—— 未开始\n计划：" in snap
    assert "装配：" not in snap
    for st in ws.parts.values():
        st.done = True
    assert "装配：未开始" in render_snapshot(ws, True)
    ws.last_assembly = object()
    assert "装配：没通过" in render_snapshot(ws, True)
    ws.assembly_passed = True
    assert "body 盒体（ABS 塑料）—— 已做完" in render_snapshot(ws, True) and "装配：已通过" in render_snapshot(ws, True)


def test_snapshot_single_part_unchanged():
    ws = Workspace(staged_brief(), FeatureList(), [])
    snap = render_snapshot(ws, True)
    assert "零件：" not in snap and "装配：" not in snap


def _examples() -> list[dict]:
    text = (PROMPT_DIR / "sca_cheatsheet_more.md").read_text(encoding="utf-8").split("## 装配的写法", 1)[1]
    lines = text.split("\n## ", 1)[0].splitlines()
    return [json.loads(ln.split("例：", 1)[1]) for ln in lines if ln.strip().startswith("例：")]


def test_cheatsheet_has_assembly_section():
    text = (PROMPT_DIR / "sca_cheatsheet_more.md").read_text(encoding="utf-8")
    assert "## 装配的写法" in text
    section = text.split("## 装配的写法", 1)[1]
    for word in ("铰链", "抽屉", "齿轮联动", "贴在一起"):
        assert word in section, word
    assert len(_examples()) >= 4


def test_assembly_examples_are_valid():
    for ex in _examples():
        if "connectors" in ex:
            assert parse_connectors(ex["part"], ex["connectors"], set())
            continue
        refs = [m[k] for m in ex["mates"] for k in ("fixed", "moving")]
        parts = sorted({r.split(".")[0] for r in refs} | {ex["ground"]})
        cons = {p: parse_connectors(p, [{"name": r.split(".")[1], "kind": "faces", "where": WHERE}
                                        for r in sorted(set(refs)) if r.startswith(p + ".")], set()) for p in parts}
        names = set()
        for j in ex.get("joints", []):
            for v in j["range"]:
                names |= expr_names(v)
        for c in ex.get("couplings", []):
            names |= expr_names(c["ratio"])
        assert parse_assembly(ex, parts, cons, names)
