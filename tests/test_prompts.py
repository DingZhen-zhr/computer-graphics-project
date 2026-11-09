import re
from pathlib import Path

from cad_agent.agent.api_docs import api_names
import json

from cad_agent.agent.state import PROMPT_DIR, load_system_prompt, render_snapshot
from cad_agent.brief import Brief
from cad_agent.notebook import Feature, FeatureList
from cad_agent.sandbox.guard import check_code
from cad_agent.tools import Workspace
from helpers import PHONE_W, TILT, make_brief

PROMPTS_DOC = Path(__file__).resolve().parent.parent / "docs" / "superpowers" / "plans" / "2026-11-09-cad-agent-v1-prompts.md"
PROMPTS_DOC_V11 = Path(__file__).resolve().parent.parent / "docs" / "superpowers" / "plans" / "2026-11-09-cad-agent-v1.1-prompts.md"
SECTIONS = ["基本体", "草图轮廓与拉伸", "多边形截面拉伸", "旋转体", "布尔运算", "移动与旋转", "阵列", "圆角与倒角", "选面选边（QL）", "常见报错与改法",
            "检查写法"]


def read(name: str) -> str:
    return (PROMPT_DIR / name).read_text(encoding="utf-8")


def test_system_prompt_is_verbatim_copy():
    doc = PROMPTS_DOC.read_text(encoding="utf-8")
    block = re.findall(r"```text\n(.*?)\n```", doc.split("## 1. 系统提示词")[1].split("## 2. 状态消息格式")[0], flags=re.S)
    assert len(block) == 1 and read("system.md").rstrip("\n") == block[0]


def test_full_system_text_is_prompt_plus_cheatsheet():
    full = load_system_prompt()
    assert full.startswith(read("system.md").rstrip("\n")) and full.endswith(read("sca_cheatsheet.md").rstrip("\n") + "\n")
    assert "## 工作顺序" in full and "# SCA 常用写法速查（simplecadapi 2.2.7 实测）" in full


def test_cheatsheet_sections_follow_the_prompts_doc():
    text = read("sca_cheatsheet.md")
    assert text.startswith("# SCA 常用写法速查（simplecadapi 2.2.7 实测）\n")
    assert re.findall(r"^## (.+)$", text, flags=re.M) == SECTIONS
    doc = PROMPTS_DOC.read_text(encoding="utf-8")
    template = re.findall(r"```text\n(# SCA 常用写法速查.*?)\n```", doc, flags=re.S)[0]
    assert re.findall(r"^## (.+)$", template, flags=re.M) == SECTIONS[:-1]   # 第一版的模板没有"检查写法"
    doc11 = PROMPTS_DOC_V11.read_text(encoding="utf-8")   # 第 1.1 版文档第 8 节新增这一节
    assert "## 检查写法" in doc11.split("## 8. 速查表新增一节：检查写法")[1]


def sections() -> dict[str, str]:
    parts = re.split(r"^## (.+)$", read("sca_cheatsheet.md"), flags=re.M)
    return {parts[i]: parts[i + 1] for i in range(1, len(parts), 2)}


def test_cheatsheet_has_required_entries():
    s = sections()
    must = {
        "基本体": ["make_box_rsolid", "make_cylinder_rsolid", "bottom_face_center", "width", "height", "depth"],
        "草图轮廓与拉伸": ["make_rectangle_rface", "make_circle_rface", "extrude_rsolid"],
        "多边形截面拉伸": ["make_polyline_rwire", "make_face_from_wire_rface", "extrude_rsolid", "normal=(0, -1, 0)"],
        "旋转体": ["revolve_rsolid"],
        "布尔运算": ["union_rsolid", "cut_rsolid", "intersect_rsolid", "skip_non_intersecting=False"],
        "移动与旋转": ["translate_shape", "rotate_shape"],
        "阵列": ["radial_pattern_rsolidlist", "linear_pattern_rsolidlist", "range("],
        "圆角与倒角": ["fillet_rsolid", "chamfer_rsolid", ".exactly("],
        "选面选边（QL）": ["ql.faces()", "ql.edges()", ".where(", "ql.and_", "ql.prop", ".resolve(", ".exactly("],
    }
    for name, words in must.items():
        for w in words:
            assert w in s[name], (name, w)


def recipe_kinds_in_doc() -> list[str]:
    section8 = PROMPTS_DOC_V11.read_text(encoding="utf-8").split("## 8. 速查表新增一节：检查写法")[1]
    line = re.search(r"顺序也照这个：(.+)", section8).group(1)
    return line.strip().rstrip("。").split("、")


def test_cheatsheet_has_check_recipes():
    kinds = recipe_kinds_in_doc()
    assert len(kinds) == 9 and kinds[0] == "总体尺寸" and kinds[-1] == "两面夹角"
    section = sections()["检查写法"]
    assert re.findall(r"^- \*\*(.+?)\*\*：", section, flags=re.M) == kinds   # 9 个条目，顺序和文档一致
    for entry in re.split(r"^- ", section, flags=re.M)[1:]:
        assert "例：`" in entry, entry[:20]   # 每条至少一个例子


def test_check_recipe_examples_match_tests():
    from test_check_recipes import RECIPES

    section = sections()["检查写法"]
    found: dict[str, list[dict]] = {}
    for entry in re.split(r"^- ", section, flags=re.M)[1:]:
        kind = re.match(r"\*\*(.+?)\*\*：", entry).group(1)
        found[kind] = [json.loads(text) for text in re.findall(r"例：`([^`]+)`", entry)]
    assert found == {r.kind: list(r.checks) for r in RECIPES}
    assert list(found) == [r.kind for r in RECIPES]


def test_cheatsheet_has_at_least_four_common_errors():
    entries = re.findall(r"^- ", sections()["常见报错与改法"], flags=re.M)
    assert len(entries) >= 4
    text = sections()["常见报错与改法"]
    for word in ("exactly", "radius", "skip_non_intersecting", "NameError"):
        assert word in text


def test_cheatsheet_examples_use_real_functions_and_pass_the_guard():
    names = set(api_names())
    text = read("sca_cheatsheet.md")
    examples = re.findall(r"例：`([^`]+)`", text)
    assert len(examples) >= 15
    for code in examples:
        assert check_code(code) == [], code  # 示例必须是合法的单行 Python，并且能通过静态检查
        for fn in re.findall(r"\bscad\.([A-Za-z_]\w*)", code):
            assert fn in names, (fn, code)
        for fn in re.findall(r"\bql\.([A-Za-z_]\w*)", code):
            assert fn in {"faces", "edges", "prop", "and_", "or_", "not_", "value"}, (fn, code)


def box_ws(confirmed: bool = False) -> Workspace:
    return Workspace(make_brief(confirmed), FeatureList(), [])


def test_snapshot_clarify_phase():
    text = render_snapshot(box_ws())
    lines = text.splitlines()
    assert lines[:3] == ["【当前状态（程序生成，不是用户说的话）】", "阶段：澄清中（需求单未确认）", "需求单："]
    assert '"name": "手机支架"' in text   # ensure_ascii=False, indent=1
    assert "特征（按顺序）：" not in text and "检查项：" not in text and "上次 build" not in text


def test_snapshot_modeling_phase():
    ws = box_ws(confirmed=True)
    ws.features.upsert(Feature("base", "build", "base = 1"))
    ws.features.upsert(Feature("hole", "subtract", "hole = 1"))
    ws.checks_raw = [PHONE_W, TILT]
    text = render_snapshot(ws)
    assert "阶段：可以建模（需求单已确认）" in text
    assert "特征（按顺序）：\n--- base（build）---\nbase = 1\n\n--- hole（subtract）---\nhole = 1" in text
    assert "检查项：\n" + json.dumps([PHONE_W, TILT], ensure_ascii=False, indent=1) in text
    assert text.endswith("上次 build：\n未运行")
    ws.last_build_content = '{"passed": true}'
    assert render_snapshot(ws).endswith('上次 build：\n{"passed": true}')
    assert text.index("需求单：") < text.index('"part"') < text.index("特征（按顺序）：") < text.index("检查项：") < text.index("上次 build：")


def test_snapshot_modeling_phase_empty():
    text = render_snapshot(box_ws(confirmed=True))
    assert "特征（按顺序）：\n无" in text and "检查项：\n无" in text


def test_snapshot_uses_brief_json():
    b = Brief(part_name="板", confirmed=True)
    assert '"confirmed": true' in render_snapshot(Workspace(b, FeatureList(), []))
