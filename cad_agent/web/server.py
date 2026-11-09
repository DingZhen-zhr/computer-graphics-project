"""HTTP 路由。只用标准库；只监听本机；文件只能从白名单目录里取。"""

from __future__ import annotations

import json
import mimetypes
import sys
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

from cad_agent.web.app import READ_ONLY, VERSION_NAME_RE, LiveApp, ReplayApp

STATIC_DIR = Path(__file__).parent / "static"
FILE_WHITELIST = ("view.png", "model.step", "model.stl", "model.py", "checks.json")
MAX_BODY = 200_000
CONTENT_TYPES = {".js": "text/javascript; charset=utf-8", ".mjs": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8",
                 ".html": "text/html; charset=utf-8", ".svg": "image/svg+xml", ".png": "image/png", ".json": "application/json; charset=utf-8",
                 ".py": "text/plain; charset=utf-8", ".step": "application/octet-stream", ".stl": "application/octet-stream"}


def _content_type(path: Path) -> str:
    return CONTENT_TYPES.get(path.suffix.lower()) or mimetypes.guess_type(path.name)[0] or "application/octet-stream"


def make_server(state: LiveApp | ReplayApp, host: str = "127.0.0.1", port: int = 8765) -> ThreadingHTTPServer:
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

        def _json(self, status: int, data) -> None:
            self._send(status, json.dumps(data, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

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
            if path == "/api/state":
                return self._json(200, state.snapshot())
            if path == "/api/diff":
                return self._diff(parse_qs(url.query))
            if path.startswith("/files/"):
                return self._files(path)
            self._error(404, "没有这个页面")

        def _send_static(self, rel: str) -> None:
            parts = rel.split("/")
            if not rel or any(p in ("", ".", "..") or "\\" in p or "\x00" in p or ":" in p for p in parts):
                return self._error(404, "没有这个文件")
            target = (STATIC_DIR / rel).resolve()
            if not target.is_relative_to(STATIC_DIR.resolve()) or not target.is_file():
                return self._error(404, "没有这个文件")
            self._send_file(target)

        def _files(self, path: str) -> None:
            parts = path.split("/")   # ['', 'files', 'v1', 'view.png']
            if len(parts) != 4 or parts[3] not in FILE_WHITELIST or not VERSION_NAME_RE.match(parts[2]):
                return self._error(404, "没有这个文件")
            version = state.version_dir(parts[2])
            if version is None or not (version / parts[3]).is_file():
                return self._error(404, "没有这个文件")
            self._send_file(version / parts[3])

        def _diff(self, query: dict) -> None:
            a, b = (query.get(k, [""])[0] for k in ("a", "b"))
            if not VERSION_NAME_RE.match(a) or not VERSION_NAME_RE.match(b):
                return self._error(400, "要给两个版本名，比如 ?a=v1&b=v2")
            changes = state.diff(a, b)
            if changes is None:
                return self._error(404, "没有这个版本")
            self._json(200, {"a": a, "b": b, "changes": changes})

        # ---- POST ----
        def do_POST(self) -> None:  # noqa: N802
            self._guarded(self._post)

        def _post(self) -> None:
            path = unquote(urlsplit(self.path).path)
            if path == "/api/message":
                return self._message()
            if path == "/api/reset":
                self._read_body()
                status = state.reset()
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

        def _message(self) -> None:
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
            status = state.submit(text)
            if status == 202:
                return self._json(202, {"ok": True})
            messages = {400: "消息不能为空", READ_ONLY: "回放模式只能看，不能发消息"}
            self._error(status, messages.get(status, "正在处理上一条消息，请稍等"))

    class Server(ThreadingHTTPServer):
        daemon_threads = True

        def handle_error(self, request, client_address) -> None:  # 连接级别的错误只打到终端，不影响服务
            traceback.print_exc(file=sys.stderr)

    return Server((host, port), Handler)
