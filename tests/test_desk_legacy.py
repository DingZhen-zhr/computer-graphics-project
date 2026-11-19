"""从旧网页界面（cad_agent/web/）搬过来的测试（第二版计划 4 Task 6）。

旧网页退役时，仍在使用的模块搬到了 cad_agent/desk/：事件折叠 web/events.py → desk/events.py，
会话日志通知、回放读取、版本摘要 web/app.py → desk/replay.py。下面这十条测试从 tests/test_web.py 原样搬来，
只改了导入路径，断言一个字没动。最后一条确认旧网页确实删干净了。
"""

from __future__ import annotations

import importlib
import re
from pathlib import Path

import pytest

from cad_agent.desk.events import describe_event, fold
from cad_agent.desk.replay import LiveSession, ReplayApp, version_summary

ROOT = Path(__file__).resolve().parent.parent

def test_describe_event_cases():
    assert describe_event("tool", {"name": "upsert_feature", "args": {"slug": "base"}, "content": '{"ok": true}'}) == "写特征 base"
    assert describe_event("tool", {"name": "set_checks", "args": {"checks": [1, 2, 3]}, "content": '{"ok": true}'}) == "写检查项（3 条）"
    assert describe_event("tool", {"name": "update_brief", "args": {}, "content": '{"changes": []}'}) == "更新需求单"
    assert describe_event("tool", {"name": "upsert_feature", "args": {"slug": "x"}, "content": '{"error": "代码不能 import"}'}) == "写特征出错，模型正在改"
    assert describe_event("tool", {"name": "build", "skipped": True, "content": '{"error": "x"}'}) == "前面的调用出错，这次运行跳过了"
    assert describe_event("tool", {"name": "build", "content": "{}"}) is None
    assert describe_event("tool", {"name": "ask_user", "content": "{}"}) is None
    assert describe_event("build", {"passed": True, "passed_checks": 7, "total_checks": 7}) == "运行通过，检查 7/7"
    assert describe_event("build", {"passed": False, "error": {"feature": "base", "type": "E", "message": "m"}}) == "运行出错（特征 base），模型正在修"
    assert describe_event("build", {"passed": False, "error": None, "failed_checks": ["tilt"]}) == "检查没通过：tilt"
    assert describe_event("build", {"passed": False, "error": None, "failed_checks": [], "missing_coverage": ["w"]}) == "还缺检查：w"
    assert describe_event("auto", {"action": "request_confirmation"}) == "需求单整理好了，请你确认"
    assert describe_event("auto", {"action": "build", "reason": "param_change"}) == "只改了参数，程序自动重新运行"
    assert describe_event("auto", {"action": "build", "reason": "turn_end"}) == "程序补跑一次检查"
    assert describe_event("assistant", {"tool_calls": []}) is None
    assert describe_event("startup", {}) is None


def test_describe_new_events():
    assert describe_event("stage", {"id": "s2", "title": "立板", "checks": 7}) == "阶段 s2（立板）通过，检查 7 条"
    assert describe_event("gate", {"missing_coverage": [], "unconstrained": [], "unbuildable": ["b"], "skipped": [], "mutation": []}) == "终检通过"
    assert describe_event("gate", {"missing_coverage": ["a", "b"], "unconstrained": []}) == "终检没通过：还缺检查（a、b）"
    assert describe_event("gate", {"missing_coverage": [], "unconstrained": ["wall"]}) == "终检没通过：这些参数改了检查也不变（wall）"
    assert describe_event("cases", {"ids": ["tray", "knob"]}) == "参考了 2 个相似案例"
    assert describe_event("manual", {"values": {"a": 1}, "ok": True, "version": "v2"}) == "手动修改了参数"
    assert describe_event("tool", {"name": "set_plan", "args": {}, "content": "{}"}) == "制定计划"
    assert describe_event("tool", {"name": "probe", "args": {"code": "print(1)"}, "content": "{}"}) == "试验代码"
    assert describe_event("tool", {"name": "read_reference", "args": {"name": "x"}, "content": "{}"}) == "查阅文档"
    assert describe_event("tool", {"name": "probe", "args": {}, "content": '{"error": "x"}'}) == "试验代码出错，模型正在改"
    # 分阶段的 build：有阶段通过、没有别的问题时不另报"运行没通过"（阶段通过由 stage 记录说）
    assert describe_event("build", {"passed": False, "error": None, "failed_checks": [], "missing_coverage": [], "stages_passed": ["s1"]}) is None
    # 旧流程的 build 记录没有 stages_passed，说法不变
    assert describe_event("build", {"passed": False, "error": None, "failed_checks": [], "missing_coverage": []}) == "运行没通过"


def test_fold_structured_entries_and_stage():
    events = [
        ("user", {"text": "做个支架"}),
        ("assistant", {"usage": {"prompt_tokens": 100, "cached_tokens": 60}, "cost": 0.01, "tool_calls": [{"name": "ask_user"}]}),
        ("question", {"text": "先问\n1. 多宽？", "lead": "先问", "questions": ["多宽？"], "llm_calls": 1, "cost": 0.01,
                      "prompt_tokens": 100, "cached_tokens": 60}),
        ("user", {"text": "78"}),
        ("confirm", {"text": "【需求单】…", "lead": "", "brief": {"params": [{"name": "w", "value": 78}]}, "llm_calls": 1, "cost": 0.02,
                     "prompt_tokens": 50, "cached_tokens": 0}),
    ]
    out = fold(events, confirmed=False, busy=False)
    q, c = out["transcript"][1], out["transcript"][3]
    assert q["kind"] == "question" and q["questions"] == ["多宽？"] and q["lead"] == "先问"
    assert c["kind"] == "confirm" and c["brief"]["params"][0]["name"] == "w"
    assert out["stage"] == "confirm" and out["activity"] == []
    assert out["stats"]["cost"] == pytest.approx(0.03) and out["stats"]["prompt_tokens"] == 150 and out["stats"]["cache_ratio"] == pytest.approx(0.4)


def test_fold_parses_old_logs_without_structured_fields():
    events = [
        ("user", {"text": "做个支架"}),
        ("question", {"text": "需要先确认：\n\n1. 手机多宽？\n2. 要充电口吗？", "llm_calls": 1}),
        ("user", {"text": "确认"}),
        ("delivered", {"text": "已交付 v2。\n检查结果（共 9 项，全部通过）：\n本版变化：tilt_deg: 65 → 70 (deg)；lip_h: 15 → 18 (mm)",
                       "version": "v2", "llm_calls": 2, "repairs": 1}),
    ]
    out = fold(events, confirmed=True, busy=False)
    q, d = out["transcript"][1], out["transcript"][3]
    assert q["questions"] == ["手机多宽？", "要充电口吗？"] and q["lead"] == "需要先确认："
    assert (d["passed"], d["total"], d["repairs"]) == (9, 9, 1)
    assert d["changes"] == ["tilt_deg: 65 → 70 (deg)", "lip_h: 15 → 18 (mm)"]
    assert out["stage"] == "delivered" and out["last_version"] == "v2"
    assert out["stats"]["cost"] is None  # 旧日志没有费用


def test_fold_live_turn_shows_activity_and_stage():
    events = [("user", {"text": "开始"}), ("assistant", {"usage": {"prompt_tokens": 10}, "cost": 0.001, "tool_calls": [{"name": "build"}]}),
              ("build", {"passed": False, "error": None, "failed_checks": ["tilt"]})]
    out = fold(events, confirmed=True, busy=True)
    assert out["stage"] == "checking" and out["activity"] == ["检查没通过：tilt"]
    assert out["stats"]["llm_calls"] == 1 and out["stats"]["cost"] == pytest.approx(0.001)
    assert fold(events[:1], confirmed=False, busy=True)["stage"] == "clarify"
    assert fold([], confirmed=False, busy=False)["stage"] == "clarify"


def test_live_session_notifies_listener_and_survives_its_errors(tmp_path):
    seen = []
    session = LiveSession(tmp_path / "s")
    session.listener = lambda kind, data: seen.append((kind, data))
    session.log("build", passed=True)
    assert seen == [("build", {"passed": True})]
    session.listener = lambda kind, data: 1 / 0
    session.log("user", text="还能写")
    assert '"还能写"' in (session.dir / "log.jsonl").read_text(encoding="utf-8")


def test_replay_skips_broken_lines_and_needs_a_log(tmp_path):
    d = tmp_path / "s"
    d.mkdir()
    with pytest.raises(FileNotFoundError):
        ReplayApp(d)
    (d / "log.jsonl").write_text('{"kind": "startup", "model": "deepseek-flash"}\n坏掉的一行\n{"kind": "user", "text": "你好"}\n'
                                 '{"kind": "reply", "text": "在的", "llm_calls": 1}\n', encoding="utf-8")
    snap = ReplayApp(d).snapshot()
    assert snap["model"] == "deepseek-flash" and [t.get("text") for t in snap["transcript"]] == ["你好", "在的"]
    assert snap["versions"] == [] and snap["brief"]["params"] == []


def test_demo_session_is_in_the_repo():
    demo = ROOT / "demo" / "phone_stand"
    snap = ReplayApp(demo).snapshot()
    assert [v["name"] for v in snap["versions"]] == ["v1", "v2"] and all(v["has_stl"] for v in snap["versions"])
    assert snap["stage"] == "delivered" and any(t.get("kind") == "question" and t["questions"] for t in snap["transcript"])


def test_version_summary_tolerates_missing_files(tmp_path):
    v = tmp_path / "v1"
    v.mkdir()
    assert version_summary(v) == {"name": "v1", "has_stl": False, "has_png": False, "passed": 0, "total": 0, "changes": [], "params": []}


@pytest.mark.sca
def test_backfill_stl(tmp_path):
    import sys

    from cad_agent.brief import Param
    from cad_agent.notebook import Feature, render_notebook

    sys.path.insert(0, str(ROOT / "scripts"))
    from backfill_stl import backfill

    v = tmp_path / "s" / "versions" / "v1"
    v.mkdir(parents=True)
    rendered = render_notebook([Param("w", 30, "mm", "user")],
                               [Feature("base", "build", "base = scad.make_box_rsolid(width=w, height=20, depth=5, bottom_face_center=(0, 0, 0))")])
    (v / "model.py").write_text(rendered.text, encoding="utf-8")
    assert backfill(tmp_path / "s") == [f"v1：已导出 model.stl（{(v / 'model.stl').stat().st_size} 字节）"]
    assert (v / "model.stl").stat().st_size > 84
    assert backfill(tmp_path / "s") == ["v1：已有 model.stl，跳过"]


def test_old_web_package_is_gone():
    with pytest.raises(ImportError):
        importlib.import_module("cad_agent.web")
    assert not (ROOT / "cad_agent" / "web").exists()
    assert not (ROOT / "start_web.bat").exists() and not (ROOT / "start_replay.bat").exists()
    three = ROOT / "cad_agent" / "desk" / "static" / "vendor" / "three" / "three.module.js"
    assert three.is_file()
    assert re.search(r"const REVISION = '(\d+)'", three.read_text(encoding="utf-8")).group(1) == "160"
