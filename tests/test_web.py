"""网页界面的测试：日志折叠、实时模式、回放模式、HTTP 接口、静态文件。

都用 ScriptedLLM 和假的 run_job，不联网；服务开在 0 号端口，跑在后台线程里。
"""

from __future__ import annotations

import http.client
import inspect
import json
import shutil
import subprocess
import threading
from pathlib import Path

import pytest

from cad_agent.agent.loop import Agent
from cad_agent.brief import Brief
from cad_agent.config import Config
from cad_agent.llm.client import LLMReply
from cad_agent.llm.fake import ScriptedLLM, scripted_call
from cad_agent.notebook import FeatureList
from cad_agent.tools import ToolBox, Workspace
from cad_agent.web.app import LiveApp, LiveSession, ReplayApp, version_summary
from cad_agent.web.events import describe_event, fold
from cad_agent.web.server import make_server
from helpers import BOX, PHONE_W, TILT, USER_PARAMS, Runner, bad_result, make_brief

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "cad_agent" / "web" / "static"
VENDOR = STATIC / "vendor" / "three"

UPSERT = scripted_call("upsert_feature", {"slug": "base", "role": "build", "code": BOX})
SET_CHECKS = scripted_call("set_checks", {"checks": [PHONE_W, TILT]})
BUILD = scripted_call("build", {})
CHANGE = scripted_call("update_brief", {"set_params": [{"name": "tilt_deg", "value": 70, "unit": "deg", "source": "user", "note": "支撑角度"}]})
FIRST_REQUEST = scripted_call("update_brief", {"part": {"name": "手机支架", "purpose": "放桌上看视频"}, "set_params": USER_PARAMS, "features": ["底座"]})
ASK = scripted_call("update_brief", {"part": {"name": "手机支架"}, "open_questions": ["手机多宽？"]}, "先问两件事",
                    ("ask_user", {"questions": ["手机多宽？建议 78 mm", "要充电口吗？"]}))


class GateLLM:
    """第一次被调用时卡住，直到测试放行；用来让一条消息一直处于"处理中"。"""

    def __init__(self, reply: LLMReply) -> None:
        self.gate, self.entered, self.reply = threading.Event(), threading.Event(), reply

    def chat(self, messages, tools):
        self.entered.set()
        assert self.gate.wait(15), "测试没有放行"
        return self.reply


class CrashOnceLLM:
    """第一次调用抛出意外异常（不是 LLMError），之后正常回复。"""

    def __init__(self) -> None:
        self.calls = 0

    def chat(self, messages, tools):
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("boom")
        return LLMReply("你好，我在。", [], {})


def make_state(tmp_path: Path, llm, confirmed: bool = False, runner=None) -> LiveApp:
    def make_agent():
        ws = Workspace(make_brief(True) if confirmed else Brief(), FeatureList(), [])
        session = LiveSession(tmp_path / "sessions")
        agent = Agent(llm, ToolBox(ws, run_job=runner or Runner()), session, Config(base_url="http://x", model="m"))
        return agent, session

    return LiveApp(make_agent, "test-model")


@pytest.fixture
def serve():
    started = []

    def start(state):
        server = make_server(state, port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        started.append((server, thread))
        return server

    yield start
    for server, thread in started:
        server.shutdown()
        server.server_close()
        thread.join(5)


def call(server, method: str, path: str, body=None, raw: bytes | None = None):
    conn = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=10)
    payload = raw if raw is not None else (json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None)
    conn.request(method, path, body=payload, headers={"Content-Type": "application/json"} if payload is not None else {})
    resp = conn.getresponse()
    data = resp.read()
    content_type = resp.getheader("Content-Type") or ""
    conn.close()
    return resp.status, data, content_type


def get_state(server) -> dict:
    status, data, _ = call(server, "GET", "/api/state")
    assert status == 200
    return json.loads(data)


def say(server, state: LiveApp, text: str) -> dict:
    status, _, _ = call(server, "POST", "/api/message", {"text": text})
    assert status == 202
    assert state.wait_idle(10)
    return get_state(server)


def deliver_two_versions(tmp_path, serve):
    state = make_state(tmp_path, ScriptedLLM([UPSERT, SET_CHECKS, BUILD, CHANGE]), confirmed=True)
    server = serve(state)
    say(server, state, "开始建模")
    return state, server, say(server, state, "支撑角度改成 70 度")


# ---------------------------------------------------------------- 一条日志 → 一句进度


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


# ---------------------------------------------------------------- 整份日志 → 网页内容


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


# ---------------------------------------------------------------- 会话日志通知


def test_live_session_notifies_listener_and_survives_its_errors(tmp_path):
    seen = []
    session = LiveSession(tmp_path / "s")
    session.listener = lambda kind, data: seen.append((kind, data))
    session.log("build", passed=True)
    assert seen == [("build", {"passed": True})]
    session.listener = lambda kind, data: 1 / 0
    session.log("user", text="还能写")
    assert '"还能写"' in (session.dir / "log.jsonl").read_text(encoding="utf-8")


# ---------------------------------------------------------------- 实时模式


def test_question_flow(tmp_path, serve):
    state = make_state(tmp_path, ScriptedLLM([ASK]))
    server = serve(state)
    assert get_state(server)["transcript"] == [] and get_state(server)["mode"] == "live"
    snap = say(server, state, "做一个支架")
    user, bot = snap["transcript"]
    assert user == {"role": "user", "text": "做一个支架"}
    assert bot["kind"] == "question" and bot["questions"] == ["手机多宽？建议 78 mm", "要充电口吗？"] and bot["lead"] == "先问两件事"
    assert snap["busy"] is False and snap["activity"] == [] and snap["stage"] == "clarify" and snap["part"]["name"] == "手机支架"


def test_confirm_flow_carries_the_brief(tmp_path, serve):
    state = make_state(tmp_path, ScriptedLLM([FIRST_REQUEST]))
    server = serve(state)
    snap = say(server, state, "做一个支架")
    bot = snap["transcript"][-1]
    assert bot["kind"] == "confirm" and [p["name"] for p in bot["brief"]["params"]] == ["phone_w", "tilt_deg"]
    assert snap["stage"] == "confirm" and snap["brief"]["part"]["purpose"] == "放桌上看视频"


def test_delivery_fills_checks_versions_and_stage(tmp_path, serve):
    state, server, snap = deliver_two_versions(tmp_path, serve)
    v1, v2 = snap["versions"]
    assert (v1["name"], v2["name"]) == ("v1", "v2") and v1["has_png"] and not v1["has_stl"]
    assert v2["changes"] == ["tilt_deg: 65 → 70 (deg)"] and [p["value"] for p in v2["params"] if p["name"] == "tilt_deg"] == [70]
    delivered = [t for t in snap["transcript"] if t.get("kind") == "delivered"]
    assert [d["version"] for d in delivered] == ["v1", "v2"] and delivered[0]["total"] == delivered[0]["passed"] == 4
    assert snap["current_version"] == "v2" and snap["stage"] == "delivered"
    assert {c["id"] for c in snap["checks"]} >= {"valid", "width"} and snap["facts"]["size"] == [78.0, 40.0, 8.0]


def test_busy_returns_409_and_reports_progress(tmp_path, serve):
    llm = GateLLM(LLMReply("好的", [], {}))
    state = make_state(tmp_path, llm)
    server = serve(state)
    assert call(server, "POST", "/api/message", {"text": "第一句"})[0] == 202
    assert llm.entered.wait(5)
    try:
        snap = get_state(server)
        assert snap["busy"] is True and snap["busy_seconds"] is not None and snap["stage"] == "clarify"
        assert snap["transcript"] == [{"role": "user", "text": "第一句"}]
        assert call(server, "POST", "/api/message", {"text": "第二句"})[0] == 409
        assert call(server, "POST", "/api/reset", {})[0] == 409
    finally:
        llm.gate.set()
    assert state.wait_idle(10) and get_state(server)["transcript"][-1]["text"] == "好的"


def test_bad_messages_400(tmp_path, serve):
    server = serve(make_state(tmp_path, ScriptedLLM([])))
    assert call(server, "POST", "/api/message", {"text": "   "})[0] == 400
    assert call(server, "POST", "/api/message", {"txt": "x"})[0] == 400
    assert call(server, "POST", "/api/message", raw=b"{not json")[0] == 400


def test_agent_crash_is_reported_and_service_keeps_going(tmp_path, serve):
    state = make_state(tmp_path, CrashOnceLLM())
    server = serve(state)
    snap = say(server, state, "你好")
    assert snap["error"] and "RuntimeError" in snap["error"] and snap["transcript"][-1]["kind"] == "error"
    snap = say(server, state, "再来一次")
    assert snap["error"] is None and snap["transcript"][-1]["text"] == "你好，我在。"


def test_failed_build_turn_shows_failure(tmp_path, serve):
    runner = Runner(bad_result("e1"), bad_result("e2"), bad_result("e3"))
    state = make_state(tmp_path, ScriptedLLM([UPSERT, SET_CHECKS, BUILD, BUILD, BUILD]), confirmed=True, runner=runner)
    server = serve(state)
    snap = say(server, state, "开始建模")
    assert snap["transcript"][-1]["kind"] == "failed" and "3 次" in snap["transcript"][-1]["text"]
    assert snap["versions"] == [] and snap["stage"] == "modeling"


def test_files_whitelist(tmp_path, serve):
    _, server, _ = deliver_two_versions(tmp_path, serve)
    status, data, kind = call(server, "GET", "/files/v1/view.png")
    assert status == 200 and data and kind == "image/png"
    for bad in ("/files/v1/../../config.toml", "/files/v1/brief.json", "/files/v9/view.png", "/files/x/view.png",
                "/static/../app.py", "/static/%2e%2e/app.py", "/files/v1/model.stl"):
        assert call(server, "GET", bad)[0] == 404, bad


def test_diff_endpoint(tmp_path, serve):
    _, server, _ = deliver_two_versions(tmp_path, serve)
    status, data, _ = call(server, "GET", "/api/diff?a=v1&b=v2")
    assert status == 200 and any("65 → 70" in line for line in json.loads(data)["changes"])
    assert call(server, "GET", "/api/diff?a=v1&b=v9")[0] == 404
    assert call(server, "GET", "/api/diff?a=../x&b=v2")[0] == 400


def test_reset_starts_a_clean_session(tmp_path, serve):
    state, server, _ = deliver_two_versions(tmp_path, serve)
    old = state.session_dir()
    assert call(server, "POST", "/api/reset", {})[0] == 200
    snap = get_state(server)
    assert state.session_dir() != old and snap["transcript"] == [] and snap["versions"] == [] and snap["current_version"] is None


def test_unknown_route_and_localhost_only(tmp_path, serve):
    assert inspect.signature(make_server).parameters["host"].default == "127.0.0.1"
    server = serve(make_state(tmp_path, ScriptedLLM([])))
    assert server.server_address[0] == "127.0.0.1"
    assert call(server, "GET", "/nope")[0] == 404 and call(server, "POST", "/api/nope", {})[0] == 404


# ---------------------------------------------------------------- 回放模式


def test_replay_matches_the_live_session(tmp_path, serve):
    state, _, live = deliver_two_versions(tmp_path, serve)
    replay = ReplayApp(state.session_dir())
    snap = replay.snapshot()
    assert snap["mode"] == "replay" and snap["replay_of"] == state.session_dir().name
    assert snap["transcript"] == live["transcript"] and snap["versions"] == live["versions"]
    assert snap["current_version"] == "v2" and snap["stage"] == "delivered" and snap["busy"] is False
    assert snap["brief"]["params"][1]["value"] == 70 and {c["id"] for c in snap["checks"]} >= {"width"}


def test_replay_is_read_only_over_http(tmp_path, serve):
    state, _, _ = deliver_two_versions(tmp_path, serve)
    server = serve(ReplayApp(state.session_dir()))
    status, data, _ = call(server, "POST", "/api/message", {"text": "改一下"})
    assert status == 403 and "回放" in json.loads(data)["error"]
    assert call(server, "POST", "/api/reset", {})[0] == 403
    assert call(server, "GET", "/files/v2/view.png")[0] == 200


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


def test_main_replay(tmp_path):
    from cad_agent.web.__main__ import main

    out: list[str] = []
    assert main(["--replay", str(tmp_path), "--no-browser"], print_fn=lambda *a, **k: out.append(" ".join(map(str, a)))) == 1
    assert "log.jsonl" in "\n".join(out)


def test_demo_session_is_in_the_repo():
    demo = ROOT / "demo" / "phone_stand"
    snap = ReplayApp(demo).snapshot()
    assert [v["name"] for v in snap["versions"]] == ["v1", "v2"] and all(v["has_stl"] for v in snap["versions"])
    assert snap["stage"] == "delivered" and any(t.get("kind") == "question" and t["questions"] for t in snap["transcript"])


def test_version_summary_tolerates_missing_files(tmp_path):
    v = tmp_path / "v1"
    v.mkdir()
    assert version_summary(v) == {"name": "v1", "has_stl": False, "has_png": False, "passed": 0, "total": 0, "changes": [], "params": []}


# ---------------------------------------------------------------- 启动


def test_main_reports_a_missing_key(monkeypatch, tmp_path):
    from cad_agent.web.__main__ import main

    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    out: list[str] = []
    code = main(["--config", str(ROOT / "config.example.toml"), "--no-browser"], print_fn=lambda *a, **k: out.append(" ".join(map(str, a))))
    assert code == 1 and "请先设置环境变量 DEEPSEEK_API_KEY" in "\n".join(out)


def test_main_reports_a_missing_config(tmp_path):
    from cad_agent.web.__main__ import main

    out: list[str] = []
    assert main(["--config", str(tmp_path / "nope.toml")], print_fn=lambda *a, **k: out.append(" ".join(map(str, a)))) == 1
    assert "找不到配置文件" in "\n".join(out)


def test_bind_server_tries_the_next_port(tmp_path):
    import socket

    from cad_agent.web.__main__ import bind_server

    state = make_state(tmp_path, ScriptedLLM([]))
    blocker = socket.socket()
    blocker.bind(("127.0.0.1", 0))
    blocker.listen()
    busy_port = blocker.getsockname()[1]
    try:
        server = bind_server(state, "127.0.0.1", busy_port)
        try:
            assert busy_port < server.server_address[1] < busy_port + 10
        finally:
            server.server_close()
    finally:
        blocker.close()


def test_build_live_agent_uses_a_live_session(monkeypatch, tmp_path):
    from dataclasses import replace

    from cad_agent.config import load_config
    from cad_agent.web.__main__ import build_live_agent

    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key-not-real")
    config = replace(load_config(ROOT / "config.example.toml"), sessions_dir=tmp_path / "s")
    agent, session = build_live_agent(config)
    assert isinstance(session, LiveSession) and agent.session is session and agent.modeling_llm is not None
    first = (session.dir / "log.jsonl").read_text(encoding="utf-8").splitlines()[0]
    assert json.loads(first)["kind"] == "startup" and "test-key-not-real" not in first


# ---------------------------------------------------------------- 页面


def test_static_files_offline_ready():
    for name in ("three.module.js", "OrbitControls.js", "STLLoader.js", "LICENSE"):
        assert (VENDOR / name).is_file() and (VENDOR / name).stat().st_size > 0, name
    assert "REVISION = '160'" in (VENDOR / "three.module.js").read_text(encoding="utf-8")
    files = [p for p in STATIC.rglob("*") if p.is_file()]
    assert {p.name for p in files} >= {"index.html", "style.css", "app.js", "chat.js", "panels.js", "viewer.js", "dom.js"}
    for path in files:
        text = path.read_text(encoding="utf-8")
        for bad in ("fonts.googleapis", "fonts.gstatic", "cdn.jsdelivr", "unpkg", "innerHTML"):
            assert bad not in text, (path.name, bad)
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    assert '<script type="importmap">' in html and "/static/vendor/three/three.module.js" in html and 'lang="zh-CN"' in html
    for no, title in (("01", "模型"), ("02", "检查"), ("03", "需求单"), ("04", "版本")):
        assert f'<span class="section-no">{no}</span><h2 class="section-title"' in html and f">{title}</h2>" in html
    for stage in ("clarify", "confirm", "modeling", "checking", "delivered"):
        assert f'data-stage="{stage}"' in html


def test_stylesheet_follows_the_visual_spec():
    css = (STATIC / "style.css").read_text(encoding="utf-8")
    for token in ("--bg: #FFFFFF", "--surface: #F5F5F7", "--ink: #1D1D1F", "--ink-2: #6E6E73", "--hairline: #D2D2D7", "--accent: #0071E3",
                  "--pass: #188038", "--fail: #D70015", "--warn: #B25000", "--mark: #E5322D"):
        assert token in css, token
    for needle in ("-apple-system", "PingFang SC", "Microsoft YaHei", "tabular-nums", "prefers-reduced-motion", "focus-visible", "@media"):
        assert needle in css, needle


def test_page_scripts_are_valid_modules():
    node = shutil.which("node")
    if node is None:
        pytest.skip("没有 node，不检查脚本语法")
    for path in sorted(STATIC.glob("*.js")):
        result = subprocess.run([node, "--check", "--input-type=module"], input=path.read_text(encoding="utf-8"), capture_output=True,
                                text=True, encoding="utf-8")
        assert result.returncode == 0, (path.name, result.stderr[:500])


def test_pages_are_served_with_the_right_types(tmp_path, serve):
    server = serve(make_state(tmp_path, ScriptedLLM([])))
    status, data, kind = call(server, "GET", "/")
    assert status == 200 and kind.startswith("text/html") and "CAD 建模助手".encode() in data
    for path, want in (("/static/style.css", "text/css"), ("/static/app.js", "text/javascript"), ("/static/viewer.js", "text/javascript"),
                       ("/static/vendor/three/three.module.js", "text/javascript")):
        status, body, kind = call(server, "GET", path)
        assert status == 200 and kind.startswith(want) and body, path


def test_start_scripts_and_readme():
    bat = (ROOT / "start_web.bat").read_text(encoding="utf-8")
    assert "%~dp0" in bat and r".venv\Scripts\python -m cad_agent.web --config config.toml" in bat
    replay = (ROOT / "start_replay.bat").read_text(encoding="utf-8")
    assert "%~dp0" in replay and r"--replay demo\phone_stand" in replay
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "## 网页演示" in readme and "start_replay.bat" in readme and "--replay" in readme


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


# ---------------------------------------------------------------- 公网测试：访问密码和花费上限


def login(server, password: str):
    conn = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=10)
    conn.request("POST", "/api/login", body=json.dumps({"password": password}).encode(), headers={"Content-Type": "application/json"})
    resp = conn.getresponse()
    resp.read()
    cookie = resp.getheader("Set-Cookie")
    conn.close()
    return resp.status, cookie


def test_password_gate(tmp_path):
    state = make_state(tmp_path, ScriptedLLM([LLMReply("在的", [], {})]))
    server = make_server(state, port=0, password="secret-123")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        assert call(server, "GET", "/")[0] == 200 and call(server, "GET", "/static/app.js")[0] == 200  # 页面本身能打开，好显示登录框
        assert call(server, "GET", "/api/state")[0] == 401 and call(server, "GET", "/files/v1/view.png")[0] == 401
        assert call(server, "POST", "/api/message", {"text": "你好"})[0] == 401
        assert login(server, "wrong")[0] == 401
        status, cookie = login(server, "secret-123")
        assert status == 200 and "HttpOnly" in cookie and "SameSite=Strict" in cookie
        token = cookie.split(";")[0]
        conn = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=10)
        conn.request("GET", "/api/state", headers={"Cookie": token})
        resp = conn.getresponse()
        assert resp.status == 200 and json.loads(resp.read())["mode"] == "live"
        conn.close()
    finally:
        server.shutdown()
        server.server_close()


def test_budget_stops_new_messages(tmp_path, serve):
    reply = LLMReply("在的", [], {})
    reply.cost = 0.6
    from cad_agent.web.pool import Budget

    state = make_state(tmp_path, ScriptedLLM([reply, LLMReply("不该被调用", [], {})]))
    state.budget = Budget(0.5)
    server = serve(state)
    snap = say(server, state, "你好")
    assert snap["budget"] == {"limit": 0.5, "spent": 0.6}
    status, data, _ = call(server, "POST", "/api/message", {"text": "再来"})
    assert status == 402 and "上限" in json.loads(data)["error"]
    assert call(server, "POST", "/api/reset", {})[0] == 200
    assert call(server, "POST", "/api/message", {"text": "新会话也不行"})[0] == 402  # 累计花费不随新会话清零


def test_main_public_needs_password_and_pricing(monkeypatch, tmp_path):
    from cad_agent.web.__main__ import main

    out: list[str] = []
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key-not-real")
    monkeypatch.delenv("CAD_WEB_PASSWORD", raising=False)
    assert main(["--config", str(ROOT / "config.example.toml"), "--public", "--no-browser"], print_fn=lambda *a, **k: out.append(str(a))) == 1
    assert "CAD_WEB_PASSWORD" in "".join(out)
    monkeypatch.setenv("CAD_WEB_PASSWORD", "long-enough")
    out.clear()
    assert main(["--config", str(ROOT / "config.example.toml"), "--public", "--no-browser"], print_fn=lambda *a, **k: out.append(str(a))) == 1
    assert "pricing" in "".join(out)  # 示例配置没填价目表，没法限制花费，就不让开公网


def test_public_launcher_and_gitignore():
    bat = (ROOT / "start_public.bat").read_text(encoding="utf-8")
    assert r"scripts\go_public.py" in bat and "--budget" in bat
    script = (ROOT / "scripts" / "go_public.py").read_text(encoding="utf-8")
    assert '"--public"' in script and "cloudflared" in script and "CAD_WEB_PASSWORD" in script and '"--", "site/live.json"' in script
    assert "getpass" in script  # 密码不回显、不写文件
    assert "tools/" in (ROOT / ".gitignore").read_text(encoding="utf-8")


# ---------------------------------------------------------------- 公网多人：每人一个会话


def make_pool(tmp_path, replies_per_visitor, max_busy=3, max_visitors=30):
    from cad_agent.web.pool import Budget, VisitorPool

    budget = Budget(10)
    scripts = iter(replies_per_visitor)
    holder = {}

    def make_app():
        llm = next(scripts)
        n = len(holder)
        holder[n] = True

        def make_agent():
            session = LiveSession(tmp_path / f"visitor{n}")
            return Agent(llm, ToolBox(Workspace(Brief(), FeatureList(), []), run_job=Runner()), session, Config(base_url="http://x", model="m")), session

        return LiveApp(make_agent, "m", budget=budget, can_start=lambda: pool.can_start())

    pool = VisitorPool(make_app, max_busy=max_busy, max_visitors=max_visitors)
    return pool


def cookie_call(server, method, path, cookie, body=None):
    conn = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=10)
    payload = json.dumps(body, ensure_ascii=False).encode() if body is not None else None
    headers = {"Cookie": cookie}
    if payload is not None:
        headers["Content-Type"] = "application/json"
    conn.request(method, path, body=payload, headers=headers)
    resp = conn.getresponse()
    data = resp.read()
    conn.close()
    return resp.status, json.loads(data) if data else None


def test_each_visitor_gets_their_own_session(tmp_path):
    pool = make_pool(tmp_path, [ScriptedLLM([LLMReply("你好甲", [], {})]), ScriptedLLM([LLMReply("你好乙", [], {})])])
    server = make_server(None, port=0, password="secret-123", pool=pool)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        _, ca = login(server, "secret-123")
        _, cb = login(server, "secret-123")
        ca, cb = ca.split(";")[0], cb.split(";")[0]
        assert ca != cb and len(pool) == 2
        assert cookie_call(server, "POST", "/api/message", ca, {"text": "我是甲"})[0] == 202
        pool.get(ca.split("=", 1)[1]).wait_idle(10)
        a = cookie_call(server, "GET", "/api/state", ca)[1]
        b = cookie_call(server, "GET", "/api/state", cb)[1]
        assert [t["text"] for t in a["transcript"]] == ["我是甲", "你好甲"] and b["transcript"] == []
        assert cookie_call(server, "GET", "/api/state", "cad_auth=forged")[0] == 401
    finally:
        server.shutdown()
        server.server_close()


def test_too_many_busy_visitors_wait(tmp_path):
    gate = GateLLM(LLMReply("好", [], {}))
    pool = make_pool(tmp_path, [gate, ScriptedLLM([LLMReply("不该被调用", [], {})])], max_busy=1)
    server = make_server(None, port=0, password="secret-123", pool=pool)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        ca, cb = (login(server, "secret-123")[1].split(";")[0] for _ in range(2))
        assert cookie_call(server, "POST", "/api/message", ca, {"text": "先来"})[0] == 202
        assert gate.entered.wait(5)
        status, body = cookie_call(server, "POST", "/api/message", cb, {"text": "后到"})
        assert status == 429 and "稍" in body["error"] or "等" in body["error"]
    finally:
        gate.gate.set()
        server.shutdown()
        server.server_close()


def test_visitor_limit_and_health(tmp_path):
    pool = make_pool(tmp_path, [ScriptedLLM([])], max_visitors=1)
    server = make_server(None, port=0, password="secret-123", pool=pool)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        assert login(server, "secret-123")[0] == 200
        assert login(server, "secret-123")[0] == 503
        conn = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=10)
        conn.request("GET", "/api/health")
        resp = conn.getresponse()
        body = json.loads(resp.read())
        assert resp.status == 200 and resp.getheader("Access-Control-Allow-Origin") == "*" and body == {"ok": True, "public": True, "busy": 0}
        conn.close()
    finally:
        server.shutdown()
        server.server_close()


def test_export_keeps_live_json(tmp_path):
    from cad_agent.web.export import export_site

    out = export_site(ROOT / "demo" / "phone_stand", tmp_path / "site")
    (out / "live.json").write_text('{"url": "https://x.trycloudflare.com"}', encoding="utf-8")
    export_site(ROOT / "demo" / "phone_stand", out)
    assert json.loads((out / "live.json").read_text(encoding="utf-8"))["url"] == "https://x.trycloudflare.com"


# ---------------------------------------------------------------- 静态演示站


def test_export_static_site(tmp_path):
    from cad_agent.web.export import export_site

    out = export_site(ROOT / "demo" / "phone_stand", tmp_path / "site")
    html = (out / "index.html").read_text(encoding="utf-8")
    assert 'data-mode="static"' in html and 'href="static/style.css"' in html and '"./static/vendor/three/three.module.js"' in html
    snap = json.loads((out / "api" / "state.json").read_text(encoding="utf-8"))
    assert snap["mode"] == "replay" and [v["name"] for v in snap["versions"]] == ["v1", "v2"]
    for name in ("model.stl", "model.step", "view.png", "model.py", "checks.json"):
        assert (out / "files" / "v2" / name).is_file(), name
    assert (out / ".nojekyll").is_file() and (out / "static" / "vendor" / "three" / "three.module.js").is_file()
    assert not (out / "static" / "index.html").exists()
    export_site(ROOT / "demo" / "phone_stand", out)  # 再导出一次会覆盖
    other = tmp_path / "mine"
    other.mkdir()
    (other / "important.txt").write_text("x", encoding="utf-8")
    with pytest.raises(FileExistsError):
        export_site(ROOT / "demo" / "phone_stand", other)  # 不是导出过的目录，不覆盖


def test_committed_site_is_up_to_date(tmp_path):
    """site/ 是要发布到 GitHub Pages 的；页面改了却忘了重新导出时，这个测试会提醒。"""
    from cad_agent.web.export import export_site

    fresh = export_site(ROOT / "demo" / "phone_stand", tmp_path / "site")
    for path in fresh.rglob("*"):
        if path.is_file():
            committed = ROOT / "site" / path.relative_to(fresh)
            assert committed.is_file() and committed.read_bytes() == path.read_bytes(), f"{path.relative_to(fresh)} 不是最新的，请重新运行 python -m cad_agent.web.export demo\phone_stand site"
    workflow = (ROOT / ".github" / "workflows" / "pages.yml").read_text(encoding="utf-8")
    assert "path: site" in workflow and "actions/deploy-pages" in workflow
