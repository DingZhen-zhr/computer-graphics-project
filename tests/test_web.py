"""网页前端的后端测试：都用 ScriptedLLM 和测试里的假 run_job，不联网；服务开在 0 号端口，跑在后台线程里。"""

from __future__ import annotations

import http.client
import inspect
import json
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
from cad_agent.web.app import AppState, LiveSession, describe_event
from cad_agent.web.server import make_server
from helpers import BOX, PHONE_W, TILT, USER_PARAMS, Runner, make_brief

UPSERT = scripted_call("upsert_feature", {"slug": "base", "role": "build", "code": BOX})
SET_CHECKS = scripted_call("set_checks", {"checks": [PHONE_W, TILT]})
BUILD = scripted_call("build", {})
CHANGE = scripted_call("update_brief", {"set_params": [{"name": "tilt_deg", "value": 70, "unit": "deg", "source": "user", "note": "支撑角度"}]})
FIRST_REQUEST = scripted_call("update_brief", {"part": {"name": "手机支架"}, "set_params": USER_PARAMS, "features": ["底座"]})


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


def make_state(tmp_path: Path, llm, confirmed: bool = False, runner=None) -> AppState:
    def make_agent():
        ws = Workspace(make_brief(True) if confirmed else Brief(), FeatureList(), [])
        session = LiveSession(tmp_path / "sessions")
        agent = Agent(llm, ToolBox(ws, run_job=runner or Runner()), session, Config(base_url="http://x", model="m"))
        return agent, session

    return AppState(make_agent, "test-model")


@pytest.fixture
def serve():
    started = []

    def start(state: AppState):
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
    conn.close()
    return resp.status, data


def get_state(server) -> dict:
    status, data = call(server, "GET", "/api/state")
    assert status == 200
    return json.loads(data)


# ---------------------------------------------------------------- describe_event


def test_describe_event_cases():
    assert describe_event("assistant", {"content": "", "tool_calls": [{"name": "upsert_feature", "args": {}}, {"name": "build", "args": {}}]}) \
        == "正在调用：upsert_feature、build"
    assert describe_event("assistant", {"content": "好的", "tool_calls": []}) == "正在整理回复"
    assert describe_event("tool", {"name": "upsert_feature", "args": {"slug": "base-plate", "role": "build", "code": "x"}}) == "写特征 base-plate"
    assert describe_event("tool", {"name": "set_checks", "args": {"checks": []}}) == "写检查项"
    assert describe_event("tool", {"name": "update_brief", "args": {}}) == "更新需求单"
    assert describe_event("build", {"passed": True, "error": None, "failed_checks": [], "missing_coverage": [], "passed_checks": 12, "total_checks": 12}) \
        == "运行检查：12/12 通过"
    assert describe_event("build", {"passed": False, "error": {"feature": "base", "type": "NameError", "message": "name 'x' is not defined"},
                                    "failed_checks": [], "missing_coverage": [], "passed_checks": 0, "total_checks": 0}) \
        == "运行没通过：name 'x' is not defined"
    assert describe_event("build", {"passed": False, "error": None, "failed_checks": ["tilt"], "missing_coverage": [], "passed_checks": 3, "total_checks": 4}) \
        == "运行没通过：检查 tilt 没通过"
    assert describe_event("build", {"passed": False, "error": None, "failed_checks": [], "missing_coverage": ["lip_h"], "passed_checks": 3, "total_checks": 3}) \
        == "运行没通过：缺少检查 lip_h"
    assert describe_event("auto", {"action": "build", "id": "auto-build-1", "reason": "param_change"}) == "程序自动重新 build"
    assert describe_event("auto", {"action": "request_confirmation"}) == "程序自动请你确认"
    assert describe_event("tool", {"name": "api_help", "args": {"name": "x"}}) is None
    assert describe_event("tool", {"name": "build", "args": {}}) is None   # build 的进度由 build 记录负责，不重复
    assert describe_event("user", {"text": "你好"}) is None


def test_live_session_notifies_listener(tmp_path):
    session = LiveSession(tmp_path / "s")
    seen = []
    session.log("user", text="早期的记录，没有人在听")
    session.listener = lambda kind, data: seen.append((kind, data))
    session.log("user", text="你好", phase="clarify")
    assert seen == [("user", {"text": "你好", "phase": "clarify"})]
    assert len((session.dir / "log.jsonl").read_text(encoding="utf-8").splitlines()) == 2   # 日志照常写


def test_live_session_survives_a_failing_listener(tmp_path):
    session = LiveSession(tmp_path / "s")

    def broken(kind, data):
        raise ValueError("listener bug")

    session.listener = broken
    session.log("user", text="你好")   # 不能抛出来，否则会打断智能体
    assert (session.dir / "log.jsonl").exists()


# ---------------------------------------------------------------- 接口


def test_message_flow(tmp_path, serve):
    state = make_state(tmp_path, ScriptedLLM([FIRST_REQUEST]))
    server = serve(state)
    status, data = call(server, "POST", "/api/message", {"text": "做一个支架"})
    assert status == 202
    assert state.wait_idle(15)
    s = get_state(server)
    assert s["busy"] is False and s["model"] == "test-model" and s["activity"] == [] and s["error"] is None
    assert [m["role"] for m in s["transcript"]] == ["user", "assistant"]
    assert s["transcript"][0]["text"] == "做一个支架"
    assistant = s["transcript"][1]
    assert assistant["kind"] == "confirm" and "【需求单】" in assistant["text"] and assistant["llm_calls"] == 1
    assert s["brief"]["part"]["name"] == "手机支架" and [p["name"] for p in s["brief"]["params"]] == ["phone_w", "tilt_deg"]
    assert s["checks"] == [] and s["versions"] == []
    assert set(s["stats"]) == {"cost", "prompt_tokens", "cached_tokens"}


def test_stats_accumulate(tmp_path, serve):
    usage = {"prompt_tokens": 1000, "completion_tokens": 100, "total_tokens": 1100, "cached_tokens": 600, "reasoning_tokens": 0}
    llm = ScriptedLLM([LLMReply("你好", [], usage, cost=0.01), LLMReply("再见", [], usage, cost=0.02)])
    state = make_state(tmp_path, llm)
    server = serve(state)
    for text in ("你好", "再见"):
        assert call(server, "POST", "/api/message", {"text": text})[0] == 202
        assert state.wait_idle(15)
    s = get_state(server)
    assert s["stats"]["prompt_tokens"] == 2000 and s["stats"]["cached_tokens"] == 1200 and s["stats"]["cost"] == pytest.approx(0.03)
    assert s["transcript"][1]["cost"] == pytest.approx(0.01)


def test_stats_cost_is_null_without_pricing(tmp_path, serve):
    state = make_state(tmp_path, ScriptedLLM([LLMReply("你好", [], {"prompt_tokens": 10, "total_tokens": 10})]))
    server = serve(state)
    call(server, "POST", "/api/message", {"text": "你好"})
    assert state.wait_idle(15)
    assert get_state(server)["stats"]["cost"] is None


def test_busy_returns_409(tmp_path, serve):
    llm = GateLLM(LLMReply("好的", [], {}))
    state = make_state(tmp_path, llm)
    server = serve(state)
    assert call(server, "POST", "/api/message", {"text": "第一条"})[0] == 202
    assert llm.entered.wait(10)
    assert call(server, "POST", "/api/message", {"text": "第二条"})[0] == 409
    assert call(server, "POST", "/api/reset")[0] == 409   # 忙时也不能重置
    s = get_state(server)
    assert s["busy"] is True and s["activity"] != []
    llm.gate.set()
    assert state.wait_idle(15)
    s = get_state(server)
    assert s["busy"] is False and s["activity"] == [] and [m["text"] for m in s["transcript"]] == ["第一条", "好的"]


def test_empty_message_400(tmp_path, serve):
    server = serve(make_state(tmp_path, ScriptedLLM([])))
    assert call(server, "POST", "/api/message", {"text": ""})[0] == 400
    assert call(server, "POST", "/api/message", {"text": "   \n"})[0] == 400
    assert call(server, "POST", "/api/message", raw=b"not json")[0] == 400
    assert call(server, "POST", "/api/message", {"other": 1})[0] == 400
    assert call(server, "POST", "/api/message", {"text": 5})[0] == 400
    assert get_state(server)["transcript"] == []


def test_agent_crash_is_reported(tmp_path, serve):
    llm = CrashOnceLLM()
    state = make_state(tmp_path, llm)
    server = serve(state)
    assert call(server, "POST", "/api/message", {"text": "你好"})[0] == 202
    assert state.wait_idle(15)
    s = get_state(server)
    assert s["busy"] is False and s["activity"] == []
    assert "意外错误" in s["error"] and "RuntimeError" in s["error"] and "boom" in s["error"]
    assert s["transcript"][-1]["role"] == "assistant" and s["transcript"][-1]["kind"] == "error" and "意外错误" in s["transcript"][-1]["text"]
    # 服务还活着，还能接下一条
    assert call(server, "POST", "/api/message", {"text": "还在吗"})[0] == 202
    assert state.wait_idle(15)
    s = get_state(server)
    assert s["error"] is None and s["transcript"][-1]["text"] == "你好，我在。"


def deliver(tmp_path, serve, extra=()):
    state = make_state(tmp_path, ScriptedLLM([UPSERT, SET_CHECKS, BUILD, *extra]), confirmed=True)
    server = serve(state)
    assert call(server, "POST", "/api/message", {"text": "开始建模"})[0] == 202
    assert state.wait_idle(30)
    return state, server


def test_delivery_fills_checks_and_versions(tmp_path, serve):
    state, server = deliver(tmp_path, serve)
    s = get_state(server)
    assert s["transcript"][-1]["kind"] == "delivered" and s["transcript"][-1]["version"] == "v1"
    assert s["versions"] == [{"name": "v1", "has_stl": False, "has_png": True}]
    assert {c["id"] for c in s["checks"]} >= {"valid", "single_solid", "positive_volume", "width"}   # 假 run_job 返回的 4 条
    assert all(set(c) >= {"id", "type", "passed", "measured", "expected", "detail"} for c in s["checks"])


def test_files_whitelist(tmp_path, serve):
    state, server = deliver(tmp_path, serve)
    status, data = call(server, "GET", "/files/v1/view.png")
    assert status == 200 and data == b"PNG"
    assert call(server, "GET", "/files/v1/model.step")[0] == 200
    assert call(server, "GET", "/files/v1/model.stl")[0] == 404   # 假 run_job 没写 STL，白名单里有也只是没有这个文件
    for bad in ("/files/v1/../../config.toml", "/files/v1/brief.json", "/static/../app.py", "/files/v9/view.png", "/files/v1/", "/files/..%2f..%2fconfig.toml/view.png",
                "/static/%2e%2e/app.py", "/files/v1/view.png/extra", "/static/"):
        assert call(server, "GET", bad)[0] == 404, bad


def test_diff_endpoint(tmp_path, serve):
    state, server = deliver(tmp_path, serve, extra=[CHANGE])
    assert call(server, "POST", "/api/message", {"text": "支撑角度改成 70 度"})[0] == 202
    assert state.wait_idle(30)
    status, data = call(server, "GET", "/api/diff?a=v1&b=v2")
    assert status == 200
    body = json.loads(data)
    assert any("65 → 70" in line for line in body["changes"])
    assert call(server, "GET", "/api/diff?a=v1&b=v9")[0] == 404
    assert call(server, "GET", "/api/diff?a=v1")[0] == 400
    assert call(server, "GET", "/api/diff?a=../x&b=v2")[0] == 400


def test_reset(tmp_path, serve):
    state, server = deliver(tmp_path, serve)
    old_session = state.session_dir()
    assert call(server, "POST", "/api/reset")[0] == 200
    s = get_state(server)
    assert s["transcript"] == [] and s["versions"] == [] and s["checks"] == [] and s["error"] is None
    assert s["stats"]["prompt_tokens"] == 0 and state.session_dir() != old_session
    assert call(server, "GET", "/files/v1/view.png")[0] == 404   # 旧会话的文件不再能取


def test_reset_gives_an_empty_brief(tmp_path, serve):
    state = make_state(tmp_path, ScriptedLLM([FIRST_REQUEST]))
    server = serve(state)
    call(server, "POST", "/api/message", {"text": "做一个支架"})
    assert state.wait_idle(15)
    assert len(get_state(server)["brief"]["params"]) == 2
    assert call(server, "POST", "/api/reset")[0] == 200
    assert get_state(server)["brief"]["params"] == []


def test_unknown_route_and_method(tmp_path, serve):
    server = serve(make_state(tmp_path, ScriptedLLM([])))
    assert call(server, "GET", "/nope")[0] == 404
    assert call(server, "POST", "/api/state")[0] in (404, 405)
    assert call(server, "GET", "/api/message")[0] in (404, 405)


def test_binds_localhost_only(tmp_path, serve):
    assert inspect.signature(make_server).parameters["host"].default == "127.0.0.1"
    server = serve(make_state(tmp_path, ScriptedLLM([])))
    assert server.server_address[0] == "127.0.0.1"


# ---------------------------------------------------------------- 启动


def test_main_reports_a_missing_key(monkeypatch, tmp_path):
    from cad_agent.web.__main__ import main

    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    out: list[str] = []
    example = Path(__file__).resolve().parent.parent / "config.example.toml"
    cfg = tmp_path / "c.toml"
    cfg.write_text(example.read_text(encoding="utf-8") + f'\n', encoding="utf-8")
    code = main(["--config", str(cfg), "--no-browser"], print_fn=lambda *a, **k: out.append(" ".join(map(str, a))))
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
            assert server.server_address[1] != busy_port and busy_port < server.server_address[1] < busy_port + 10
        finally:
            server.server_close()
    finally:
        blocker.close()


def test_build_live_agent_uses_a_live_session(monkeypatch, tmp_path):
    from dataclasses import replace

    from cad_agent.config import load_config
    from cad_agent.web.__main__ import build_live_agent

    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key-not-real")
    config = replace(load_config(Path(__file__).resolve().parent.parent / "config.example.toml"), sessions_dir=tmp_path / "s")
    agent, session = build_live_agent(config)
    assert isinstance(session, LiveSession) and agent.session is session and agent.modeling_llm is not None
    first = (session.dir / "log.jsonl").read_text(encoding="utf-8").splitlines()[0]
    assert json.loads(first)["kind"] == "startup" and "test-key-not-real" not in first


# ---------------------------------------------------------------- 页面

STATIC = Path(__file__).resolve().parent.parent / "cad_agent" / "web" / "static"
VENDOR = STATIC / "vendor" / "three"
ROOT = Path(__file__).resolve().parent.parent


def test_static_files_offline_ready():
    for name in ("three.module.js", "OrbitControls.js", "STLLoader.js", "LICENSE"):
        assert (VENDOR / name).is_file() and (VENDOR / name).stat().st_size > 0, name
    assert "REVISION = '160'" in (VENDOR / "three.module.js").read_text(encoding="utf-8")   # 固定的版本
    assert "MIT License" in (VENDOR / "LICENSE").read_text(encoding="utf-8")
    files = [p for p in STATIC.rglob("*") if p.is_file()]
    assert {p.name for p in files} >= {"index.html", "style.css", "app.js", "viewer.js"}
    for path in files:
        text = path.read_text(encoding="utf-8")
        for bad in ("fonts.googleapis", "fonts.gstatic", "cdn.jsdelivr", "unpkg"):
            assert bad not in text, (path.name, bad)
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    assert '<script type="importmap">' in html and "/static/vendor/three/three.module.js" in html
    for title in ("01 模型", "02 检查", "03 需求单", "04 版本"):
        assert title in html, title
    assert 'lang="zh-CN"' in html and "viewport" in html


def test_stylesheet_follows_the_visual_spec():
    css = (STATIC / "style.css").read_text(encoding="utf-8")
    for token in ("--bg: #FFFFFF", "--surface: #F5F5F7", "--ink: #1D1D1F", "--ink-2: #6E6E73", "--hairline: #D2D2D7", "--accent: #0071E3",
                  "--pass: #188038", "--fail: #D70015", "--warn: #B25000", "--mark: #E5322D"):
        assert token in css, token
    for needle in ("-apple-system", "PingFang SC", "Microsoft YaHei", "Cascadia Mono", "tabular-nums", "prefers-reduced-motion", "max-width: 1440px",
                   "1100px", "700px", "focus-visible"):
        assert needle in css, needle
    assert "box-shadow" not in css.replace("inset", "")   # 不用阴影


def test_index_served(tmp_path, serve):
    server = serve(make_state(tmp_path, ScriptedLLM([])))
    status, data = call(server, "GET", "/")
    assert status == 200 and data.lstrip().lower().startswith(b"<!doctype html>") and "CAD 建模助手".encode() in data
    conn = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=10)
    conn.request("GET", "/")
    resp = conn.getresponse()
    resp.read()
    assert resp.getheader("Content-Type").startswith("text/html")
    conn.close()


def test_static_files_are_served_with_the_right_types(tmp_path, serve):
    server = serve(make_state(tmp_path, ScriptedLLM([])))
    for path, kind in (("/static/style.css", "text/css"), ("/static/app.js", "text/javascript"), ("/static/viewer.js", "text/javascript"),
                       ("/static/vendor/three/three.module.js", "text/javascript"), ("/static/vendor/three/OrbitControls.js", "text/javascript")):
        conn = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=10)
        conn.request("GET", path)
        resp = conn.getresponse()
        body = resp.read()
        conn.close()
        assert resp.status == 200 and resp.getheader("Content-Type").startswith(kind) and body, path


def test_page_scripts_are_valid_modules():
    import shutil
    import subprocess

    node = shutil.which("node")
    if node is None:
        pytest.skip("没有 node，不检查脚本语法")
    scripts = sorted(STATIC.glob("*.js"))
    assert {p.name for p in scripts} >= {"app.js", "viewer.js", "dom.js", "chat.js", "panels.js"}
    for path in scripts:
        result = subprocess.run([node, "--check", "--input-type=module"], input=path.read_text(encoding="utf-8"), capture_output=True, text=True,
                                encoding="utf-8")
        assert result.returncode == 0, (path.name, result.stderr[:500])


def test_dom_helper_skips_empty_children():
    # 目测时发现过：原生 el.append(null) 会写出文字 "null"，所以页面里往节点里加可能为空的东西，要用 dom.js 的 h/add
    dom = (STATIC / "dom.js").read_text(encoding="utf-8")
    assert "export function add(" in dom and "child === null" in dom and "child === undefined" in dom
    chat = (STATIC / "chat.js").read_text(encoding="utf-8")
    assert "add(body, meta(entry))" in chat


def test_start_script_and_readme():
    bat = (ROOT / "start_web.bat").read_text(encoding="utf-8")
    assert "cd /d" in bat and "%~dp0" in bat and r".venv\Scripts\python -m cad_agent.web --config config.toml" in bat and "pause" in bat
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "## 网页演示" in readme and "start_web.bat" in readme and "python -m cad_agent.web" in readme
