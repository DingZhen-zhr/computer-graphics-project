"""datum 命令和桌面窗口（第二版计划 3 Task 13）。不开真的窗口、不连任何模型服务；钥匙串用内存里的假后端。"""

from __future__ import annotations

import http.client
import json
import os
import socket
import sys
import time
import tomllib
from pathlib import Path

import keyring
import pytest

from cad_agent import app
from cad_agent.llm.client import LLMReply, ToolCall
from cad_agent.llm.fake import load_script
from cad_agent.llm.providers import load_providers
from cad_agent.settings import Settings
from cad_agent.staged.specs import TOOL_NAMES_V2
from test_keystore import MemoryKeyring

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "demo_script.json"
FAKE_KEY = "fake-app-test-0000-ABCD"
NO_KEY = '还没有可用的密钥。到右上角的"设置"里填好密钥，再发一次。'


@pytest.fixture
def home(monkeypatch, tmp_path):
    monkeypatch.setenv("DATUM_HOME", str(tmp_path / "home"))
    for p in load_providers():
        monkeypatch.delenv(p.api_key_env, raising=False)
    previous = keyring.get_keyring()
    backend = MemoryKeyring()
    keyring.set_keyring(backend)
    yield backend
    keyring.set_keyring(previous)


def wait_idle(wb, timeout=180):
    deadline = time.monotonic() + timeout
    while wb.is_busy():
        assert time.monotonic() < deadline, "这一轮一直没结束"
        time.sleep(0.05)


def test_load_script(tmp_path):
    f = tmp_path / "s.json"
    f.write_text(json.dumps([{"content": "你好"}, {"tool_calls": [{"name": "build", "args": {}}, {"name": "ask_user", "args": {"questions": ["多大？"]}}]}],
                            ensure_ascii=False), encoding="utf-8")
    replies = load_script(f)
    assert [r.content for r in replies] == ["你好", ""]
    assert replies[0].tool_calls == [] and isinstance(replies[1], LLMReply)
    assert replies[1].tool_calls == [ToolCall("call_1", "build", {}), ToolCall("call_2", "ask_user", {"questions": ["多大？"]})]
    f.write_text('[{"tool_calls": [{"args": {}}]}]', encoding="utf-8")
    with pytest.raises(ValueError):
        load_script(f)


def test_demo_script_file_is_valid():
    replies = load_script(SCRIPT)
    names = [tc.name for r in replies for tc in r.tool_calls]
    assert names and set(names) <= set(TOOL_NAMES_V2)
    assert names.count("build") == 2 and names.count("set_plan") == 1 and "ask_user" in names and "request_confirmation" in names


@pytest.mark.sca
def test_demo_script_runs_end_to_end(home):
    hub = app.build_hub(Settings(), script=SCRIPT)
    try:
        wb = hub.open(hub.create())
        for text in ("做一个安装板", "1. 5 mm\n2. 孔径 6，离边 10", "确认", "孔径改成 8"):
            wb.submit(text)
            wait_idle(wb)
        st = wb.state()
        assert [v["name"] for v in st["versions"]] == ["v1", "v2"]
        assert [t["kind"] for t in st["transcript"] if t["role"] == "assistant"] == ["question", "confirm", "delivered", "delivered"]
        assert st["versions"][1]["changes"] == ["hole_d: 6 → 8 (mm)"]
        assert all(v["has_stl"] and v["stages"] == ["s1", "s2"] for v in st["versions"])
    finally:
        hub.close()


def test_main_browser_mode_starts_server(home, monkeypatch):
    seen: dict = {}

    def fake_wait() -> None:
        url = seen["url"]
        port = int(url.split(":")[2].split("/")[0])
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
        conn.request("GET", url.split(str(port), 1)[1])
        resp = conn.getresponse()
        seen["status"], seen["body"] = resp.status, resp.read()
        conn.close()
        seen["port"] = port

    monkeypatch.setattr(app, "open_browser", lambda url: seen.setdefault("url", url))
    monkeypatch.setattr(app, "wait_for_exit", fake_wait)
    assert app.main(["--browser"]) == 0
    assert seen["url"].startswith("http://127.0.0.1:") and "/?t=" in seen["url"]
    assert seen["status"] == 200 and "基准".encode() in seen["body"]
    with pytest.raises(OSError):
        socket.create_connection(("127.0.0.1", seen["port"]), timeout=1).close()


def test_window_failure_falls_back_to_browser(home, monkeypatch, capsys):
    opened: list[str] = []
    monkeypatch.setitem(sys.modules, "webview", None)   # 一导入就失败
    monkeypatch.setattr(app, "open_browser", opened.append)
    monkeypatch.setattr(app, "wait_for_exit", lambda: None)
    assert app.main([]) == 0
    out = capsys.readouterr().out
    assert "桌面窗口打不开（" in out and "改用浏览器打开" in out and "datum doctor" in out
    assert len(opened) == 1 and opened[0].startswith("http://127.0.0.1:")


def test_window_mode_opens_pywebview(home, monkeypatch):
    calls: dict = {}

    class FakeWebview:
        @staticmethod
        def create_window(title, url, **kw):
            calls["window"] = (title, url, kw)

        @staticmethod
        def start(*a, **kw):
            calls["started"] = True

    monkeypatch.setitem(sys.modules, "webview", FakeWebview)
    monkeypatch.setattr(app, "open_browser", lambda url: calls.setdefault("browser", url))
    assert app.main([]) == 0
    title, url, kw = calls["window"]
    assert title == "Datum 基准" and url.startswith("http://127.0.0.1:") and "/?t=" in url
    assert (kw["width"], kw["height"]) == (1360, 860) and tuple(kw["min_size"]) == (1100, 700)
    assert calls["started"] and "browser" not in calls


def test_window_mode_enables_downloads(home, monkeypatch):
    """Mac 的 pywebview Cocoa 后端需要 ALLOW_DOWNLOADS=True 才能响应 <a download>。"""
    class FakeWebview:
        settings = {"ALLOW_DOWNLOADS": False}

        @staticmethod
        def create_window(title, url, **kw):
            pass

        @staticmethod
        def start(*a, **kw):
            pass

    monkeypatch.setitem(sys.modules, "webview", FakeWebview)
    assert app.main([]) == 0
    assert FakeWebview.settings["ALLOW_DOWNLOADS"] is True


def test_cli_mode_uses_keystore_when_no_config(home, monkeypatch):
    from cad_agent import cli

    keyring.set_password("datum", "deepseek", FAKE_KEY)
    captured: dict = {}
    monkeypatch.setattr(cli, "main", lambda argv=None, **kw: captured.update(argv=argv, **kw) or 0)
    config = None
    try:
        assert app.main(["--cli"]) == 0
        config = captured["config"]
        assert config.provider == "deepseek" and config.api_key() == FAKE_KEY
        os.environ.pop(config.api_key_env, None)
        captured.clear()
        assert app.main(["--cli", "--config", "x.toml"]) == 0
        assert captured["argv"] == ["--config", "x.toml"] and "config" not in captured
    finally:
        if config is not None:
            os.environ.pop(config.api_key_env, None)


def test_missing_key_turn_fails_with_hint(home):
    hub = app.build_hub(Settings())
    try:
        wb = hub.open(hub.create())
        wb.submit("做一个安装板")
        wait_idle(wb, 30)
        last = wb.state()["transcript"][-1]
        assert last["kind"] == "failed" and NO_KEY in last["text"]
    finally:
        hub.close()


def test_make_llm_for_without_key_is_a_config_error(home):
    from cad_agent.config import ConfigError

    with pytest.raises(ConfigError) as e:
        app.make_llm_for(Settings(), "clarify")
    assert "密钥" in str(e.value)
    keyring.set_password("datum", "deepseek", FAKE_KEY)
    llm = app.make_llm_for(Settings(), "clarify")   # 只造客户端，不发请求
    assert llm is not None and FAKE_KEY not in repr(vars(llm).get("model", ""))


def test_help_mentions_demo_script_only_as_dev(capsys):
    with pytest.raises(SystemExit):
        app.main(["--help"])
    out = capsys.readouterr().out
    lines = [x for x in out.strip().splitlines() if x.strip()]
    assert "--demo-script" in lines[-1] and "开发用" in lines[-1]
    assert sum("--demo-script" in x for x in lines) == 1


def test_entry_points_declared():
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert data["project"]["scripts"]["datum"] == "cad_agent.app:main"
    assert data["project"]["gui-scripts"]["datum-app"] == "cad_agent.app:gui_main"
    assert any(d.startswith("pywebview") for d in data["project"]["dependencies"])


def test_socksio_dependency_declared():
    """系统开着 SOCKS5 代理时 httpx2 需要 socksio（偏离 D49）。"""
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert any(d.startswith("socksio") for d in data["project"]["dependencies"])


def test_demo_script_resumes_where_the_session_left_off(home):
    """走查时关掉窗口再打开：剧本从这个会话已经用掉的回复后面接着往下走，不从头再来。"""
    from cad_agent.session import Session

    hub = app.build_hub(Settings(), script=SCRIPT)
    try:
        sid = hub.create()
        s = Session.open(hub.sessions_dir / sid)
        s.log("assistant", content="一", tool_calls=[])
        s.log("assistant", content="二", tool_calls=[])
        agent = hub.make_agent(Session.open(hub.sessions_dir / sid))
        script = load_script(SCRIPT)
        assert [r.content for r in agent.llm.replies] == [r.content for r in script[2:]]
        assert script[-1].tool_calls == [] and script[-1].content   # 最后一条是重开以后用的普通回复
    finally:
        hub.close()
