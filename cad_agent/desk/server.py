"""桌面端的本机 HTTP 服务（第二版计划 3 Task 6）：页面、静态文件、接口、SSE、版本文件。只用标准库。

保护：只监听 127.0.0.1；Host 必须是 127.0.0.1:<端口> 或 localhost:<端口>；带了 Origin 时必须是这两个之一；
所有 /api/ 和 /files/ 请求必须带本次启动的随机令牌（请求头 X-Caliper-Token；查询参数 t 只给 SSE 和文件下载用），
页面本身要 ?t=。不满足一律 403。这样别的网页和本机其他程序都调不了这些接口（包括写 key 的接口）。

extra 是另外一组路由（设置、key、案例），签名 extra(method, path, query, body) -> (状态码, 数据) | None，None 表示不归它管。
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, unquote, urlsplit

from cad_agent.desk.hub import Hub
from cad_agent.desk.routes import ApiError, session_api, translate, version_file
from cad_agent.web.server import STATIC_DIR as WEB_STATIC
from cad_agent.web.server import _content_type

logger = logging.getLogger("caliper.desk")

STATIC_DIR = Path(__file__).parent / "static"
VENDOR_DIR = WEB_STATIC / "vendor" / "three"
VENDOR_PREFIX = "vendor/three/"
KEEPALIVE_S = 15.0
MAX_BODY = 200_000
SSE_PATH = re.compile(r"^/api/sessions/[^/]+/events$")
INLINE_SCRIPT = re.compile(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", re.S)
BAD_TOKEN = "令牌不对，拒绝访问。请从卡尺的窗口里打开这个页面。"
BAD_ORIGIN = "请求的来源不对，拒绝访问。"
Extra = Callable[[str, str, dict, Any], "tuple[int, Any] | None"]
# 地址栏里没有令牌的页面请求（页面加载后会把令牌从地址栏去掉，按 F5 时就是这样）：
# 用这个标签页自己存的令牌重新进来；存的也没有，就说明要从卡尺的窗口里打开。页面里没有令牌。
RECOVER_PAGE = """<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><title>卡尺 Caliper</title></head>
<body><p id="m"></p><script>
var t = null;
try { t = sessionStorage.getItem("caliper.token"); } catch (e) {}
if (t) { location.replace("/?t=" + encodeURIComponent(t)); }
else { document.getElementById("m").textContent = "这个页面要从卡尺的窗口里打开。请关掉它，重新打开卡尺。"; }
</script></body></html>"""


def reveal_path(path: Path) -> None:
    """在系统的文件管理器里显示这个目录。"""
    if sys.platform == "win32":
        os.startfile(str(path))  # noqa: S606 - 只打开程序自己的版本目录
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])


def _csp(html: str) -> str:
    """页面的内容安全策略：脚本只能来自本机，内联的只有 import map（按内容的哈希放行）。"""
    hashes = " ".join(f"'sha256-{base64.b64encode(hashlib.sha256(m.encode('utf-8')).digest()).decode()}'"
                      for m in INLINE_SCRIPT.findall(html))
    return (f"default-src 'self'; script-src 'self' {hashes}; style-src 'self'; img-src 'self' data: blob:; "
            "connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'")


def make_desk_server(hub: Hub, extra: Callable | None, *, port: int = 0, token: str | None = None) -> tuple[ThreadingHTTPServer, str]:
    token = token or secrets.token_urlsafe(32)
    stopping = threading.Event()

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        server_version = "Caliper"

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002 - 终端保持干净
            pass

        # ---- 发送 ----
        def _headers(self, status: int, content_type: str, length: int | None, cache: str = "no-store", extra: dict | None = None) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            if length is not None:
                self.send_header("Content-Length", str(length))
            self.send_header("Cache-Control", cache)
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()

        def _send(self, status: int, body: bytes, content_type: str, cache: str = "no-store", extra: dict | None = None) -> None:
            self._headers(status, content_type, len(body), cache, extra)
            self.wfile.write(body)

        def _json(self, status: int, data: Any) -> None:
            self._send(status, json.dumps(data, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

        def _error(self, status: int, message: str) -> None:
            self._json(status, {"error": message})

        # ---- 检查 ----
        def _local_names(self) -> set[str]:
            p = self.server.server_address[1]
            return {f"127.0.0.1:{p}", f"localhost:{p}"}

        def _origin_ok(self) -> bool:
            if (self.headers.get("Host") or "") not in self._local_names():
                return False
            origin = self.headers.get("Origin")
            return origin is None or origin in {f"http://{n}" for n in self._local_names()}

        def _token_ok(self, query: dict, allow_query: bool) -> bool:
            given = self.headers.get("X-Caliper-Token") or (query.get("t", [""])[0] if allow_query else "")
            return bool(given) and hmac.compare_digest(given.encode("utf-8"), token.encode("utf-8"))

        def _body(self) -> Any:
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                raise ApiError(400, "请求的长度不对") from None
            if length < 0 or length > MAX_BODY:
                self.close_connection = True
                if 0 < length <= MAX_BODY * 20:   # 先把多出来的读掉再回答，不然对方还在发就被断开（Windows 上会报连接被重置）
                    left = length
                    while left > 0:
                        chunk = self.rfile.read(min(left, 65536))
                        if not chunk:
                            break
                        left -= len(chunk)
                raise ApiError(400, "请求内容太大")
            raw = self.rfile.read(length) if length else b""
            if not raw:
                return None
            try:
                return json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, ValueError):
                raise ApiError(400, "请求内容不是合法的 JSON") from None

        # ---- 分发 ----
        def do_GET(self) -> None:  # noqa: N802
            self._guarded("GET")

        def do_POST(self) -> None:  # noqa: N802
            self._guarded("POST")

        def do_DELETE(self) -> None:  # noqa: N802
            self._guarded("DELETE")

        def _guarded(self, method: str) -> None:
            try:
                self._handle(method)
            except ApiError as e:
                self._error(e.status, e.message)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass   # 页面关掉了
            except Exception:  # noqa: BLE001 - 任何意外都变成 500，不让连接线程把服务带崩；堆栈只进程序日志
                logger.exception("处理请求时出错：%s %s", method, self.path.split("?")[0])
                try:
                    self._error(500, "服务内部出错了，可以刷新页面再试")
                except OSError:
                    pass

        def _handle(self, method: str) -> None:
            url = urlsplit(self.path)
            path, query = url.path, parse_qs(url.query)
            if not self._origin_ok():
                if method != "GET":
                    self.close_connection = True
                raise ApiError(403, BAD_ORIGIN)
            if method == "GET" and path in ("/", "/index.html"):
                if not self._token_ok(query, allow_query=True):
                    if "text/html" in (self.headers.get("Accept") or ""):
                        return self._send(403, RECOVER_PAGE.encode("utf-8"), "text/html; charset=utf-8",
                                          extra={"Content-Security-Policy": _csp(RECOVER_PAGE)})
                    raise ApiError(403, BAD_TOKEN)
                return self._page()
            if method == "GET" and path.startswith("/static/"):
                return self._static(path[len("/static/"):])
            if not (path.startswith("/api/") or path.startswith("/files/")):
                raise ApiError(404, "没有这个页面")
            allow_query = method == "GET" and (path.startswith("/files/") or bool(SSE_PATH.match(path)))
            if not self._token_ok(query, allow_query):
                self.close_connection = True
                raise ApiError(403, BAD_TOKEN)
            segs = [unquote(s) for s in path.split("/")[2:]]
            if path.startswith("/files/"):
                if method != "GET" or len(segs) < 2:
                    raise ApiError(404, "没有这个文件")
                return self._file(version_file(hub, segs[0], segs[1:]))
            if SSE_PATH.match(path) and method == "GET":
                return self._events(segs[1], query)
            body = self._body() if method in ("POST", "DELETE") else None
            if extra is not None:
                handled = extra(method, path, {k: v for k, v in query.items()}, body)
                if handled is not None:
                    return self._json(*handled)
            return self._json(200, session_api(hub, method, segs, query, body, lambda p: reveal_path(p)))

        # ---- 页面和文件 ----
        def _page(self) -> None:
            html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
            self._send(200, html.encode("utf-8"), "text/html; charset=utf-8", extra={"Content-Security-Policy": _csp(html)})

        def _static(self, rel: str) -> None:
            parts = [unquote(p) for p in rel.split("/")]
            if not rel or any(p in ("", ".", "..") or "/" in p or "\\" in p or "\x00" in p or ":" in p for p in parts):
                raise ApiError(404, "没有这个文件")
            rel = "/".join(parts)
            root, sub = (VENDOR_DIR, rel[len(VENDOR_PREFIX):]) if rel.startswith(VENDOR_PREFIX) else (STATIC_DIR, rel)
            target = (root / sub).resolve()
            if not target.is_relative_to(root.resolve()) or not target.is_file():
                raise ApiError(404, "没有这个文件")
            self._file(target, cache="no-cache")

        def _file(self, path: Path, cache: str = "no-store") -> None:
            try:
                data = path.read_bytes()
            except OSError:
                raise ApiError(404, "没有这个文件") from None
            self._send(200, data, _content_type(path), cache)

        # ---- SSE ----
        def _events(self, sid: str, query: dict) -> None:
            try:
                since = int(query.get("since", ["0"])[0] or 0)
            except ValueError:
                raise ApiError(400, "since 应该是整数") from None
            try:
                wb = hub.open(sid)
            except Exception as e:  # noqa: BLE001
                raise translate(e) from None
            self.close_connection = True
            self._headers(200, "text/event-stream; charset=utf-8", None, extra={"Connection": "close"})
            self.wfile.flush()
            while not stopping.is_set():
                events = wb.bus.wait(since, KEEPALIVE_S)
                if events:
                    out = []
                    for e in events:
                        since = max(since, int(e["seq"]))
                        out.append(f"id: {e['seq']}\ndata: {json.dumps(e, ensure_ascii=False)}\n\n")
                    self.wfile.write("".join(out).encode("utf-8"))
                else:
                    self.wfile.write(b": keepalive\n\n")   # 保持连接；页面断开后这里写失败，线程退出
                self.wfile.flush()

    class Server(ThreadingHTTPServer):
        daemon_threads = True
        allow_reuse_address = False

        def shutdown(self) -> None:
            stopping.set()
            super().shutdown()

        def handle_error(self, request: Any, client_address: Any) -> None:
            logger.exception("连接出错")

    return Server(("127.0.0.1", port), Handler), token
