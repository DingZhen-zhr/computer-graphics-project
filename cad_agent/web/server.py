"""HTTP 路由。只用标准库；只监听本机；文件只能从白名单目录里取。"""

from __future__ import annotations

import hmac
import json
import mimetypes
import secrets
import time
import sys
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

from cad_agent.web.app import CROWDED, OVER_BUDGET, READ_ONLY, VERSION_NAME_RE, LiveApp, ReplayApp
from cad_agent.web.pool import VisitorPool

STATIC_DIR = Path(__file__).parent / "static"
FILE_WHITELIST = ("view.png", "model.step", "model.stl", "model.py", "checks.json")
MAX_BODY = 200_000
CONTENT_TYPES = {".js": "text/javascript; charset=utf-8", ".mjs": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8",
                 ".html": "text/html; charset=utf-8", ".svg": "image/svg+xml", ".png": "image/png", ".json": "application/json; charset=utf-8",
                 ".py": "text/plain; charset=utf-8", ".step": "application/octet-stream", ".stl": "application/octet-stream"}


def _content_type(path: Path) -> str:
    return CONTENT_TYPES.get(path.suffix.lower()) or mimetypes.guess_type(path.name)[0] or "application/octet-stream"


COOKIE = "cad_auth"


def make_server(state: LiveApp | ReplayApp | None, host: str = "127.0.0.1", port: int = 8765, password: str | None = None,
                pool: VisitorPool | None = None) -> ThreadingHTTPServer:
    """password 不为空时（公网测试），除了页面、静态文件和 /api/health，其余接口都要先用密码登录，拿到 cookie。

    给了 pool 时，每次登录发一个新令牌、开一个独立会话（多人各用各的）；没给时所有人用同一个 state。
    """
    token = secrets.token_urlsafe(32)

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        server_version = "CadAgentWeb"

        # ---- 小工具 ----
        def log_message(self, format: str, *args) -> None:  # noqa: A002 - 演示时终端保持干净
            pass

        def _send(self, status: int, body: bytes, content_type: str, cache: str = "no-store") -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", cache)
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, status: int, data, headers: dict | None = None) -> None:
            body = json.dumps(data, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            for k, v in (headers or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def _cookie(self) -> str | None:
            for part in (self.headers.get("Cookie") or "").split(";"):
                name, _, value = part.strip().partition("=")
                if name == COOKIE:
                    return value
            return None

        def _state(self) -> LiveApp | ReplayApp | None:
            """这个请求对应的会话；没登录（或令牌过期）时是 None。"""
            if pool is not None:
                return pool.get(self._cookie())
            if not password:
                return state
            given = self._cookie()
            return state if given is not None and hmac.compare_digest(given, token) else None

        def _authed(self) -> bool:
            return self._state() is not None

        def _error(self, status: int, message: str) -> None:
            self._json(status, {"error": message})

        def _send_file(self, path: Path, cache: str = "no-cache") -> None:
            try:
                data = path.read_bytes()
            except OSError:
                self._error(404, "找不到这个文件")
                return
            self._send(200, data, _content_type(path), cache)

        def _guarded(self, fn) -> None:
            """任何意外都变成 500，不让连接线程把服务带崩。"""
            try:
                fn()
            except (BrokenPipeError, ConnectionResetError):
                pass  # 页面关掉了
            except Exception:  # noqa: BLE001
                traceback.print_exc(file=sys.stderr)
                try:
                    self._error(500, "服务内部出错了，可以刷新页面再试")
                except Exception:  # noqa: BLE001
                    pass

        # ---- GET ----
        def do_GET(self) -> None:  # noqa: N802
            self._guarded(self._get)

        def _get(self) -> None:
            url = urlsplit(self.path)
            path = unquote(url.path)
            if path == "/" or path == "/index.html":
                return self._send_static("index.html")
            if path.startswith("/static/"):
                return self._send_static(path[len("/static/"):])
            if path == "/api/health":  # 演示站（GitHub Pages）用它判断实时体验在不在线，不含任何会话内容
                health = {"ok": True, "public": bool(password), "busy": pool.busy_count() if pool is not None else None}
                return self._json(200, health, {"Access-Control-Allow-Origin": "*"})
            st = self._state()
            if (path.startswith("/api/") or path.startswith("/files/")) and st is None:
                return self._error(401, "需要先输入访问密码")
            if path == "/api/state":
                return self._json(200, st.snapshot())
            if path == "/api/diff":
                return self._diff(st, parse_qs(url.query))
            if path.startswith("/files/"):
                return self._files(st, path)
            self._error(404, "没有这个页面")

        def _send_static(self, rel: str) -> None:
            parts = rel.split("/")
            if not rel or any(p in ("", ".", "..") or "\\" in p or "\x00" in p or ":" in p for p in parts):
                return self._error(404, "没有这个文件")
            target = (STATIC_DIR / rel).resolve()
            if not target.is_relative_to(STATIC_DIR.resolve()) or not target.is_file():
                return self._error(404, "没有这个文件")
            self._send_file(target)

        def _files(self, st, path: str) -> None:
            parts = path.split("/")   # ['', 'files', 'v1', 'view.png']
            if len(parts) != 4 or parts[3] not in FILE_WHITELIST or not VERSION_NAME_RE.match(parts[2]):
                return self._error(404, "没有这个文件")
            version = st.version_dir(parts[2])
            if version is None or not (version / parts[3]).is_file():
                return self._error(404, "没有这个文件")
            self._send_file(version / parts[3])

        def _diff(self, st, query: dict) -> None:
            a, b = (query.get(k, [""])[0] for k in ("a", "b"))
            if not VERSION_NAME_RE.match(a) or not VERSION_NAME_RE.match(b):
                return self._error(400, "要给两个版本名，比如 ?a=v1&b=v2")
            changes = st.diff(a, b)
            if changes is None:
                return self._error(404, "没有这个版本")
            self._json(200, {"a": a, "b": b, "changes": changes})

        # ---- POST ----
        def do_POST(self) -> None:  # noqa: N802
            self._guarded(self._post)

        def _post(self) -> None:
            path = unquote(urlsplit(self.path).path)
            if path == "/api/login":
                return self._login()
            st = self._state()
            if st is None:
                self._read_body()
                return self._error(401, "需要先输入访问密码")
            if path == "/api/message":
                return self._message(st)
            if path == "/api/reset":
                self._read_body()
                status = st.reset()
                if status == 200:
                    return self._json(200, {"ok": True})
                return self._error(status, "回放模式只能看，不能开新会话" if status == READ_ONLY else "正在处理消息，现在不能重置")
            self._read_body()
            self._error(404, "没有这个接口")

        def _read_body(self) -> bytes | None:
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                return None
            if length < 0 or length > MAX_BODY:
                return None
            return self.rfile.read(length) if length else b""

        def _login(self) -> None:
            raw = self._read_body() or b""
            try:
                given = json.loads(raw.decode("utf-8")).get("password", "") if raw else ""
            except (UnicodeDecodeError, json.JSONDecodeError, AttributeError):
                given = ""
            if not password:
                return self._json(200, {"ok": True})
            if not isinstance(given, str) or not hmac.compare_digest(given.encode("utf-8"), password.encode("utf-8")):
                time.sleep(1)  # 拖慢暴力猜密码
                return self._error(401, "密码不对")
            issued = token
            if pool is not None:
                issued = pool.new_visitor()
                if issued is None:
                    return self._error(503, "现在体验的人太多了，请过一会儿再来")
            secure = "; Secure" if self.headers.get("X-Forwarded-Proto", "").lower() == "https" else ""  # 经过 https 隧道时
            cookie = f"{COOKIE}={issued}; HttpOnly; SameSite=Strict; Path=/; Max-Age=43200{secure}"
            self._json(200, {"ok": True}, {"Set-Cookie": cookie})

        def _message(self, st) -> None:
            raw = self._read_body()
            if raw is None:
                return self._error(400, "请求内容太大或格式不对")
            try:
                body = json.loads(raw.decode("utf-8")) if raw else None
            except (UnicodeDecodeError, json.JSONDecodeError):
                return self._error(400, "请求内容不是合法的 JSON")
            text = body.get("text") if isinstance(body, dict) else None
            if not isinstance(text, str):
                return self._error(400, "需要 {\"text\": \"…\"}")
            status = st.submit(text)
            if status == 202:
                return self._json(202, {"ok": True})
            messages = {400: "消息不能为空", READ_ONLY: "回放模式只能看，不能发消息",
                        OVER_BUDGET: "这次测试的花费已经到上限了，请联系组长",
                        CROWDED: "现在同时在建模的人比较多，请等一两分钟再发"}
            self._error(status, messages.get(status, "正在处理上一条消息，请稍等"))

    class Server(ThreadingHTTPServer):
        daemon_threads = True

        def handle_error(self, request, client_address) -> None:  # 连接级别的错误只打到终端，不影响服务
            traceback.print_exc(file=sys.stderr)

    return Server((host, port), Handler)
