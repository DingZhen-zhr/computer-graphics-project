import re
from pathlib import Path

from cad_agent.agent.api_docs import api_names
from cad_agent.agent.state import PROMPT_DIR, load_system_prompt, render_state
from cad_agent.brief import Brief
from cad_agent.notebook import Feature, FeatureList
from cad_agent.sandbox.guard import check_code
from cad_agent.tools import Workspace
from helpers import PHONE_W, TILT, bad_result, good_result, make_brief

PROMPTS_DOC = Path(__file__).resolve().parent.parent / "docs" / "superpowers" / "plans" / "2026-11-09-cad-agent-v1-prompts.md"
SECTIONS = ["基本体", "草图轮廓与拉伸", "多边形截面拉伸", "旋转体", "布尔运算", "移动与旋转", "阵列", "圆角与倒角", "选面选边（QL）", "常见报错与改法"]


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
    assert re.findall(r"^## (.+)$", template, flags=re.M) == SECTIONS


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


def test_state_message_format_when_empty():
    text = render_state(box_ws(), failures_left=3, calls_left=40)
    lines = text.splitlines()
    assert lines[0] == "【当前状态】" and lines[1] == "阶段：澄清中（需求单未确认）" and lines[2] == "需求单："
    assert '"part": {' in text and '"name": "手机支架"' in text  # ensure_ascii=False, indent=1
    assert "特征（按顺序）：无" in text and "检查项：无" in text and "上次 build：未运行" in text
    assert lines[-1] == "本轮剩余：建模失败还可 3 次，工具调用还可 40 次"
    assert text.index("需求单：") < text.index('"part"') < text.index("特征（按顺序）")


def test_state_message_with_features_checks_and_builds():
    ws = box_ws(confirmed=True)
    ws.features.upsert(Feature("base", "build", "base = 1"))
    ws.features.upsert(Feature("hole", "subtract", "hole = 1"))
    ws.checks_raw = [PHONE_W, TILT]
    text = render_state(ws, 2, 35)
    assert "阶段：可以建模（需求单已确认）" in text
    assert "特征（按顺序）：base(build)、hole(subtract)" in text and "检查项：width、tilt" in text
    assert text.splitlines()[-1] == "本轮剩余：建模失败还可 2 次，工具调用还可 35 次"
    ws.last_run = good_result()
    assert "上次 build：通过" in render_state(ws, 3, 40)
    ws.last_run = bad_result("boom", cell="hole")
    assert "上次 build：没通过：hole" in render_state(ws, 3, 40)
    ws.last_run = bad_result("boom", cell=None, type_="NotebookError")
    assert "上次 build：没通过：" in render_state(ws, 3, 40) and "NotebookError" in render_state(ws, 3, 40)
    failed = good_result(ok=False)
    failed.checks[-1].passed = False
    ws.last_run = failed
    assert "上次 build：没通过：width" in render_state(ws, 3, 40)


def test_state_message_reports_missing_coverage_after_ok_run():
    ws = box_ws(confirmed=True)
    ws.checks_raw = [PHONE_W]  # tilt_deg 没有检查
    ws.last_run = good_result()
    assert "上次 build：没通过：缺少检查 tilt_deg" in render_state(ws, 3, 40)


def test_state_message_uses_brief_json():
    b = Brief(part_name="板", confirmed=True)
    ws = Workspace(b, FeatureList(), [])
    assert '"confirmed": true' in render_state(ws, 3, 40)
