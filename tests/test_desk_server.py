"""桌面端的本机服务（第二版计划 3 Task 6）：起一个真的本机服务，配假流程的真 Hub。"""

from __future__ import annotations

import http.client
import json
import socket
import threading
import time
from pathlib import Path

import pytest

from cad_agent.desk import server as desk_server
from cad_agent.desk.server import make_desk_server
from cad_agent.llm.client import LLMReply
from cad_agent.llm.fake import ScriptedLLM
from cad_agent.session import Session
from helpers_staged import staged_brief
from test_desk_hub import Factory, make_hub
from test_desk_workbench import PLAN_TALK, GateLLM, wait_idle
from test_staged_loop import S1, S2

ROOT = Path(__file__).resolve().parent.parent


class Client:
    def __init__(self, server, token: str) -> None:
        self.port, self.token = server.server_address[1], token

    def call(self, method: str, path: str, body=None, *, token: bool = True, headers: dict | None = None, raw: bytes | None = None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        h = {"X-Caliper-Token": self.token} if token else {}
        payload = raw if raw is not None else (json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None)
        if payload is not None:
            h["Content-Type"] = "application/json"
        h.update(headers or {})
        conn.request(method, path, body=payload, headers=h)
        resp = conn.getresponse()
        data = resp.read()
        kind = resp.getheader("Content-Type") or ""
        conn.close()
        parsed = json.loads(data) if kind.startswith("application/json") and data else data
        return resp.status, parsed, kind

    def sse(self, sid: str, since: int, until: str, *, limit: float = 10) -> list[dict]:
        """连上事件流，一直读到出现 type == until 的事件为止，然后断开。"""
        sock = socket.create_connection(("127.0.0.1", self.port), timeout=limit)
        req = (f"GET /api/sessions/{sid}/events?since={since}&t={self.token} HTTP/1.1\r\nHost: 127.0.0.1:{self.port}\r\n"
               "Accept: text/event-stream\r\n\r\n")
        sock.sendall(req.encode("ascii"))
        buf, events, head = b"", [], True
        deadline = time.monotonic() + limit
        try:
            while time.monotonic() < deadline:
                chunk = sock.recv(65536)
                if not chunk:
                    break
                buf += chunk
                if head:
                    if b"\r\n\r\n" not in buf:
                        continue
                    header, buf = buf.split(b"\r\n\r\n", 1)
                    text = header.decode("utf-8")
                    assert " 200 " in text.splitlines()[0] and "text/event-stream" in text
                    head = False
                while b"\n\n" in buf:
                    block, buf = buf.split(b"\n\n", 1)
                    text = block.decode("utf-8")
                    lines = dict(line.split(": ", 1) for line in text.splitlines() if ": " in line and not line.startswith(":"))
                    if "data" in lines:
                        ev = json.loads(lines["data"])
                        assert int(lines["id"]) == ev["seq"]
                        events.append(ev)
                        if ev["type"] == until:
                            return events
        finally:
            sock.close()
        raise AssertionError(f"没等到 {until}，收到 {[e['type'] for e in events]}")


@pytest.fixture
def serve(tmp_path):
    started = []

    def start(hub=None, extra=None, factory=None):
        hub = hub or make_hub(tmp_path, factory, demo_dir=ROOT / "demo")
        server, token = make_desk_server(hub, extra)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        started.append((server, hub))
        return Client(server, token), hub

    yield start
    for server, hub in started:
        server.shutdown()
        server.server_close()
        hub.close()


def seeded(hub) -> str:
    sid = hub.create()
    Session.open(hub.sessions_dir / sid).save_state(staged_brief(), [], [], "")
    return sid


def delivered(serve):
    c, hub = serve(factory=Factory(ScriptedLLM([PLAN_TALK, S1, S2])))
    sid = seeded(hub)
    assert c.call("POST", f"/api/sessions/{sid}/message", {"text": "开始建模吧"})[0] == 200
    wait_idle(hub.open(sid))
    return c, hub, sid


def test_requests_without_token_are_rejected(serve):
    c, hub = serve()
    sid = hub.create()
    for method, path in (("GET", "/"), ("GET", "/?t=wrong"), ("GET", "/api/sessions"), ("POST", "/api/sessions"),
                         ("GET", f"/files/{sid}/v1/view.png"), ("GET", f"/api/sessions/{sid}/events?since=0"),
                         ("GET", f"/api/sessions/{sid}/events?since=0&t=wrong"), ("DELETE", f"/api/sessions/{sid}")):
        status, body, _ = c.call(method, path, token=False)
        assert status == 403 and "令牌" in body["error"], (method, path)
    assert c.call("GET", "/api/sessions", headers={"X-Caliper-Token": "wrong"}, token=False)[0] == 403
    assert (hub.sessions_dir / sid).is_dir()


def test_token_in_header_or_query(serve, monkeypatch, tmp_path):
    static = tmp_path / "static"
    static.mkdir()
    (static / "index.html").write_text("<!doctype html><title>卡尺</title>", encoding="utf-8")
    monkeypatch.setattr(desk_server, "STATIC_DIR", static)
    c, hub = serve()
    status, body, kind = c.call("GET", f"/?t={c.token}", token=False)
    assert status == 200 and kind.startswith("text/html") and "卡尺".encode() in body
    assert c.call("GET", "/api/sessions")[0] == 200
    assert c.call("GET", f"/api/sessions?t={c.token}", token=False)[0] == 403   # 查询参数只给 SSE 和文件用
    sid = hub.create()
    assert c.call("GET", f"/files/{sid}/v1/view.png?t={c.token}", token=False)[0] == 404   # 令牌对了，只是没有这个文件


def test_foreign_origin_and_host_are_rejected(serve):
    c, hub = serve()
    port = c.port
    assert c.call("GET", "/api/sessions", headers={"Origin": "https://evil.example"})[0] == 403
    assert c.call("POST", "/api/key", {"provider": "deepseek", "key": "x"}, headers={"Origin": "https://evil.example"})[0] == 403
    assert c.call("GET", "/api/sessions", headers={"Host": "evil.example"})[0] == 403
    assert c.call("GET", "/api/sessions", headers={"Host": f"evil.example:{port}"})[0] == 403
    assert c.call("GET", "/static/css/tokens.css", headers={"Host": "evil.example"})[0] == 403
    assert c.call("GET", "/api/sessions", headers={"Origin": f"http://127.0.0.1:{port}"})[0] == 200
    assert c.call("GET", "/api/sessions", headers={"Origin": f"http://localhost:{port}", "Host": f"localhost:{port}"})[0] == 200
    assert c.call("GET", "/api/sessions", headers={"Origin": f"http://127.0.0.1:{port + 1}"})[0] == 403
    assert c.call("GET", "/api/sessions", headers={"Origin": "null"})[0] == 403


def test_session_crud_over_http(serve):
    c, hub = serve()
    status, body, _ = c.call("POST", "/api/sessions", {})
    assert status == 200 and set(body) == {"id"}
    sid = body["id"]
    listed = c.call("GET", "/api/sessions")[1]
    assert listed[0]["id"] == sid and listed[-1]["id"] == "demo-phone_stand"
    assert c.call("POST", f"/api/sessions/{sid}/rename", {"title": "底板"})[1] == {"ok": True}
    assert c.call("GET", "/api/sessions")[1][0]["title"] == "底板"
    st = c.call("GET", f"/api/sessions/{sid}/state")[1]
    assert st["session"]["title"] == "底板" and st["phase"] == "clarify"
    assert c.call("DELETE", f"/api/sessions/{sid}")[1] == {"ok": True}
    assert [x["id"] for x in c.call("GET", "/api/sessions")[1]] == ["demo-phone_stand"]


def test_message_then_events_then_state(serve):
    c, hub = serve(factory=Factory(ScriptedLLM([PLAN_TALK, S1, S2])))
    sid = seeded(hub)
    assert c.call("POST", f"/api/sessions/{sid}/message", {"text": "开始建模吧"})[1] == {"ok": True}
    events = c.sse(sid, 0, "turn_end")
    assert events[0]["type"] == "turn_start" and events[-1]["kind"] == "delivered"
    wait_idle(hub.open(sid))
    st = c.call("GET", f"/api/sessions/{sid}/state")[1]
    assert st["phase"] == "delivered" and st["versions"][0]["name"] == "v1"


def test_sse_reconnect_with_since(serve):
    c, hub, sid = delivered(serve)
    first = c.sse(sid, 0, "state")
    assert len(first) > 6
    cut = first[4]["seq"]
    again = c.sse(sid, cut, "state")
    assert [e["seq"] for e in again] == [e["seq"] for e in first if e["seq"] > cut]
    assert again == [e for e in first if e["seq"] > cut]


def test_sse_keepalive_comment(serve, monkeypatch):
    monkeypatch.setattr(desk_server, "KEEPALIVE_S", 0.2)
    c, hub = serve()
    sid = hub.create()
    sock = socket.create_connection(("127.0.0.1", c.port), timeout=5)
    sock.sendall(f"GET /api/sessions/{sid}/events?since=0&t={c.token} HTTP/1.1\r\nHost: 127.0.0.1:{c.port}\r\n\r\n".encode())
    buf = b""
    deadline = time.monotonic() + 5
    while b"\n: " not in buf and time.monotonic() < deadline:
        buf += sock.recv(4096)
    sock.close()
    assert b"\n: " in buf or buf.split(b"\r\n\r\n", 1)[1].startswith(b": ")


def test_busy_is_409(serve):
    gate = GateLLM(LLMReply("好", [], {}))
    c, hub = serve(factory=Factory(gate))
    sid = hub.create()
    assert c.call("POST", f"/api/sessions/{sid}/message", {"text": "你好"})[0] == 200
    assert gate.entered.wait(5)
    for method, path, body in (("POST", f"/api/sessions/{sid}/message", {"text": "再来"}),
                               ("POST", f"/api/sessions/{sid}/params", {"values": {"phone_w": 90}}),
                               ("DELETE", f"/api/sessions/{sid}", None)):
        status, data, _ = c.call(method, path, body)
        assert status == 409 and data["error"], path
    assert c.call("POST", f"/api/sessions/{sid}/stop", {})[1] == {"ok": True}
    gate.gate.set()
    wait_idle(hub.open(sid))


def test_bad_json_is_400(serve):
    c, hub = serve()
    sid = hub.create()
    for raw in (b"{not json", "你好".encode("gbk"), b"[1, 2]", b'{"text": 5}', b'{"text": "   "}'):
        status, data, _ = c.call("POST", f"/api/sessions/{sid}/message", raw=raw)
        assert status == 400 and data["error"], raw
    assert c.call("POST", f"/api/sessions/{sid}/params", {"values": [1]})[0] == 400
    assert c.call("POST", f"/api/sessions/{sid}/params", {"values": {"a": "x"}})[0] == 400
    assert c.call("POST", f"/api/sessions/{sid}/rename", {"title": ""})[0] == 400
    big = json.dumps({"text": "x" * 210_000}).encode()
    assert c.call("POST", f"/api/sessions/{sid}/message", raw=big)[0] == 400


def test_unknown_session_is_404(serve):
    c, hub = serve()
    for method, path in (("GET", "/api/sessions/nope/state"), ("POST", "/api/sessions/nope/message"), ("DELETE", "/api/sessions/nope"),
                         ("GET", "/api/sessions/..%2f..%2fx/state"), ("GET", "/api/nope"), ("GET", "/nope")):
        status, data, _ = c.call(method, path, {"text": "x"} if method == "POST" else None)
        assert status == 404 and data["error"], path


def test_demo_is_403_for_writes(serve):
    c, hub = serve()
    sid = "demo-phone_stand"
    assert c.call("GET", f"/api/sessions/{sid}/state")[1]["session"]["demo"] is True
    for method, path, body in (("POST", f"/api/sessions/{sid}/message", {"text": "你好"}),
                               ("POST", f"/api/sessions/{sid}/params", {"values": {"device_w": 80}}),
                               ("POST", f"/api/sessions/{sid}/case", {"title": "x", "tags": ["y"]}),
                               ("POST", f"/api/sessions/{sid}/rename", {"title": "x"}),
                               ("DELETE", f"/api/sessions/{sid}", None)):
        status, data, _ = c.call(method, path, body)
        assert status == 403 and data["error"], path
    status, data, kind = c.call("GET", f"/files/{sid}/v1/view.png")
    assert status == 200 and kind == "image/png"


def test_files_whitelist(serve):
    c, hub, sid = delivered(serve)
    for name, kind in (("view.png", "image/png"), ("model.step", "application/octet-stream"), ("model.stl", "application/octet-stream"),
                       ("model.py", "text/plain"), ("checks.json", "application/json"), ("gate.json", "application/json"),
                       ("stages/s1.stl", "application/octet-stream"), ("stages/s2.stl", "application/octet-stream")):
        status, body, got = c.call("GET", f"/files/{sid}/v1/{name}")
        assert status == 200 and got.startswith(kind) and body, name
    assert c.call("GET", f"/files/{sid}/current/stages/s1.stl")[0] == 200
    assert c.call("GET", f"/files/{sid}/v1/review.json")[0] == 200
    for bad in ("v1/brief.json", "v1/../log.jsonl", "v1/%2e%2e/log.jsonl", "v1/stages/../../log.jsonl", "v1/stages/s1.stl/x",
                "v1/a/view.png", "current/view.png", "current/model.step", "v9/view.png", "x1/view.png", "current/stages/../log.jsonl",
                "v1/stages/s1.txt", "log.jsonl", "v1"):
        assert c.call("GET", f"/files/{sid}/{bad}")[0] == 404, bad
    rev = hub.sessions_dir / sid / "review" / "round-1"
    rev.mkdir(parents=True)
    (rev / "iso.png").write_bytes(b"PNG")
    assert c.call("GET", f"/files/{sid}/current/review/round-1/iso.png")[0] == 200
    assert c.call("GET", f"/files/{sid}/current/review/round-1/../x.png")[0] == 404
    assert c.call("GET", f"/files/{sid}/v1/review/round-1/iso.png")[0] == 404


def test_params_endpoint_returns_manual_result(serve):
    c, hub, sid = delivered(serve)
    status, body, _ = c.call("POST", f"/api/sessions/{sid}/params", {"values": {"phone_w": 90}})
    assert status == 200 and body["ok"] is True and body["version"] == "v2"
    assert set(body) == {"ok", "text", "version", "changes", "failed_checks", "error"}
    assert body["changes"] == ["手动修改参数：phone_w 78 → 90（mm）"] and "C:" not in json.dumps(body)
    status, body, _ = c.call("POST", f"/api/sessions/{sid}/params", {"values": {"nope": 1}})
    assert status == 200 and body["ok"] is False and body["version"] is None


def test_diff_endpoint(serve):
    c, hub, sid = delivered(serve)
    c.call("POST", f"/api/sessions/{sid}/params", {"values": {"phone_w": 90}})
    status, body, _ = c.call("GET", f"/api/sessions/{sid}/diff?a=v1&b=v2")
    assert status == 200 and body == {"lines": ["phone_w: 78 → 90 (mm)"]}
    assert c.call("GET", f"/api/sessions/{sid}/diff?a=v1&b=v9")[0] == 404
    assert c.call("GET", f"/api/sessions/{sid}/diff?a=../x&b=v2")[0] == 400


def test_case_and_reveal_endpoints(serve, monkeypatch):
    shown: list[Path] = []
    monkeypatch.setattr(desk_server, "reveal_path", shown.append)
    c, hub, sid = delivered(serve)
    status, body, _ = c.call("POST", f"/api/sessions/{sid}/case", {"title": "L 形支架", "tags": ["支架"]})
    assert status == 200 and (hub.cases_dir / body["id"] / "case.yaml").is_file()
    assert c.call("POST", f"/api/sessions/{sid}/case", {"title": "", "tags": ["支架"]})[0] == 400
    assert c.call("POST", f"/api/sessions/{sid}/reveal", {"version": "v1"})[1] == {"ok": True}
    assert shown == [hub.sessions_dir / sid / "versions" / "v1"]
    assert c.call("POST", f"/api/sessions/{sid}/reveal", {"version": "../x"})[0] == 400
    assert c.call("POST", f"/api/sessions/{sid}/reveal", {"version": "v7"})[0] == 404


def test_extra_routes_are_called(serve):
    seen = []

    def extra(method, path, query, body):
        seen.append((method, path, query, body))
        if path == "/api/boot":
            return 200, {"hello": "你好"}
        return None

    c, hub = serve(extra=extra)
    assert c.call("GET", "/api/boot")[1] == {"hello": "你好"}
    assert c.call("POST", "/api/nothing", {"a": 1})[0] == 404
    assert seen[-1] == ("POST", "/api/nothing", {}, {"a": 1})


def test_static_and_vendor(serve):
    c, hub = serve()
    status, body, kind = c.call("GET", "/static/vendor/three/three.module.js", token=False)
    assert status == 200 and kind.startswith("text/javascript") and b"REVISION" in body
    status, body, kind = c.call("GET", "/static/css/tokens.css", token=False)
    assert status == 200 and kind.startswith("text/css")
    for bad in ("/static/../server.py", "/static/%2e%2e/server.py", "/static/css/../../server.py", "/static/vendor/three/../../app.js"):
        assert c.call("GET", bad, token=False)[0] == 404, bad


def test_binds_localhost_only(serve):
    c, hub = serve()
    server, token = make_desk_server(hub, None)
    try:
        assert server.server_address[0] == "127.0.0.1" and server.server_address[1] > 0 and len(token) >= 32
    finally:
        server.server_close()
    server, token = make_desk_server(hub, None, token="given-token")
    try:
        assert token == "given-token"
    finally:
        server.server_close()


def test_error_bodies_are_chinese_json(serve):
    c, hub = serve()
    for method, path, headers in (("GET", "/api/nope", {}), ("GET", "/api/sessions", {"Origin": "https://evil.example"}),
                                  ("GET", "/api/sessions/nope/state", {})):
        status, body, kind = c.call(method, path, headers=headers)
        assert kind.startswith("application/json") and isinstance(body, dict) and set(body) == {"error"}
        assert any("一" <= ch <= "鿿" for ch in body["error"]), body
        assert "Traceback" not in body["error"]


def test_responses_do_not_leak_referrer(serve):
    c, hub = serve()
    conn = http.client.HTTPConnection("127.0.0.1", c.port, timeout=5)
    conn.request("GET", "/api/sessions", headers={"X-Caliper-Token": c.token})
    resp = conn.getresponse()
    resp.read()
    assert resp.getheader("Referrer-Policy") == "no-referrer" and resp.getheader("X-Content-Type-Options") == "nosniff"
    conn.close()


def test_reload_without_token_gets_a_recovery_page(serve):
    """页面把令牌从地址栏去掉了，按 F5 重新加载时：浏览器拿到一个小页面，用这个标签页自己存的令牌重新进来。"""
    c, hub = serve()
    status, body, kind = c.call("GET", "/", token=False, headers={"Accept": "text/html,application/xhtml+xml"})
    assert status == 403 and kind.startswith("text/html")
    text = body.decode("utf-8")
    assert "sessionStorage" in text and c.token not in text and "从卡尺的窗口里打开" in text
    status, body, kind = c.call("GET", "/", token=False)   # 不是浏览器：照旧是 JSON
    assert status == 403 and body["error"]


def test_message_without_text_key_is_400(serve):
    """接替 test_web.py::test_bad_messages_400 里键名写错（txt）那一项（计划 4 Task 6 Step 1 核对时补的）。"""
    c, hub = serve()
    sid = hub.create()
    status, data, _ = c.call("POST", f"/api/sessions/{sid}/message", {"txt": "x"})
    assert status == 400 and data["error"]
