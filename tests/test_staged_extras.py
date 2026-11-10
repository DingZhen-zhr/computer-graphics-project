"""probe、read_reference 两个工具和第二版的系统提示词（第二版计划 1 Task 9）。"""

import json

from cad_agent.agent.state import PROMPT_DIR, load_system_prompt
from cad_agent.gates import Gates
from cad_agent.staged import messages as msg
from cad_agent.staged.extras import PROBE_LIMIT
from cad_agent.tools import ToolBox
from helpers_staged import StageRunner, passing, two_stage_ws


def j(out) -> dict:
    return json.loads(out.content)


def probe_box(ws=None, result=None):
    ws = ws or two_stage_ws()
    r = StageRunner(default=result or passing(probe_output="体积 24960"))
    return ToolBox(ws, run_job=r, gates=Gates()), r


def test_probe_runs_and_counts():
    box, r = probe_box()
    box.build_failures, box.unbuilt_edits = 1, True
    last = box.ws.last_run
    body = j(box.call("probe", {"code": "print(model.get_volume())"}))
    assert body == {"output": "体积 24960", "error": None, "probes_left": PROBE_LIMIT - 1} and PROBE_LIMIT == 10
    assert box.build_failures == 1 and box.unbuilt_edits is True and box.ws.last_run is last
    assert r.calls[0]["mode"] == "probe" and r.calls[0]["checks_raw"] == []
    assert "print(model.get_volume())" in r.calls[0]["text"] and "# ---- probe ----" in r.calls[0]["text"]
    assert box.ws.probes_used == 1


def test_probe_reports_error_in_build_format():
    bad = passing(probe_output="到这里")
    bad.ok, bad.error = False, {"cell": "probe", "type": "NameError", "message": "name 'x' is not defined"}
    box, _ = probe_box(result=bad)
    body = j(box.call("probe", {"code": "print('到这里')\nprint(x)"}))
    assert body["output"] == "到这里" and body["error"] == {"feature": "probe", "type": "NameError", "message": "name 'x' is not defined"}
    assert body["probes_left"] == 9


def test_probe_limit():
    box, r = probe_box()
    for _ in range(PROBE_LIMIT):
        assert "output" in j(box.call("probe", {"code": "print(1)"}))
    assert j(box.call("probe", {"code": "print(1)"})) == {"error": msg.PROBE_LIMIT_REACHED}
    assert len(r.calls) == PROBE_LIMIT


def test_probe_guard():
    box, r = probe_box()
    body = j(box.call("probe", {"code": "import os\nprint(os.getcwd())"}))
    assert body["error"].startswith("probe 代码没有通过检查：") and r.calls == []
    assert box.ws.probes_used == 0
    assert "必须是文字" in j(box.call("probe", {"code": 3}))["error"]


def test_probe_uses_features_up_to_current_stage():
    ws = two_stage_ws()
    box, r = probe_box(ws)
    box.call("probe", {"code": "print(1)"})
    assert "# ---- feature: base" in r.calls[-1]["text"] and "# ---- feature: wall" not in r.calls[-1]["text"]
    ws.plan.mark_passed("s1")
    box.call("probe", {"code": "print(1)"})
    assert "# ---- feature: wall" in r.calls[-1]["text"]
    ws.plan.mark_passed("s2")   # 全部通过：用到最后一个阶段为止
    box.call("probe", {"code": "print(1)"})
    assert "# ---- feature: wall" in r.calls[-1]["text"]


def test_read_reference_before_confirmation():
    ws = two_stage_ws()
    ws.brief.confirmed, ws.plan = False, None
    box = ToolBox(ws, run_job=StageRunner(), gates=Gates())
    body = j(box.call("read_reference", {"name": "part-modeling", "section": "Boolean discipline"}))
    assert body["text"].startswith("## Boolean discipline") and body["name"] == "part-modeling"
    assert j(box.call("read_reference", {"name": "nope"}))["error"].startswith("没有叫 nope 的文档。")
    assert "必须是文字" in j(box.call("read_reference", {"name": "part-modeling", "section": 3}))["error"]


def test_full_system_prompt_v2():
    full = load_system_prompt(True)
    parts = [(PROMPT_DIR / n).read_text(encoding="utf-8").rstrip("\n")
             for n in ("system_v2.md", "references_index.md", "sca_cheatsheet.md", "sca_cheatsheet_more.md")]
    assert full == "\n\n".join(parts) + "\n"
    assert load_system_prompt() == load_system_prompt(False)
    assert "set_plan" not in load_system_prompt(False) and "set_plan" in full
