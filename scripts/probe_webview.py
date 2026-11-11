r"""一次性探测（第二版计划 3 Task 2 Step 0）：pywebview 窗口里 WebGL 和 SSE 能不能用。

    .venv\Scripts\python scripts\probe_webview.py [--seconds 10] [--browser]

起一个只监听本机的 HTTP 服务：页面用 three.js 画一个会转的方块，用 EventSource 每秒收一条服务端推来的消息；
页面每秒把"画了多少帧、收到几条消息、WebGL 是否可用"报回服务端。到时间后关窗口，打印结果，进程应当正常退出。
不联网、不调用任何模型。
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VENDOR = ROOT / "cad_agent" / "web" / "static" / "vendor" / "three"

PAGE = """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>探测</title>
<script type="importmap">{"imports": {"three": "/vendor/three.module.js"}}</script>
<style>body{margin:0;font:14px monospace;background:#F4F1EA;color:#1B1B1B}#info{position:fixed;left:8px;top:8px}</style>
</head><body><div id="info">启动中</div><canvas id="c" width="480" height="360"></canvas>
<script type="module">
import * as THREE from "three";
const info = document.getElementById("info");
const r = {webgl: false, frames: 0, sse: 0, last: null, error: null, ua: navigator.userAgent};
try {
  const renderer = new THREE.WebGLRenderer({canvas: document.getElementById("c"), antialias: true});
  r.webgl = !!renderer.getContext();
  const scene = new THREE.Scene();
  const cam = new THREE.PerspectiveCamera(50, 480 / 360, 0.1, 100);
  cam.position.set(0, 0, 4);
  const cube = new THREE.Mesh(new THREE.BoxGeometry(1.4, 1.4, 1.4), new THREE.MeshNormalMaterial());
  scene.add(cube);
  const tick = () => { cube.rotation.x += 0.02; cube.rotation.y += 0.03; renderer.render(scene, cam); r.frames++; requestAnimationFrame(tick); };
  tick();
} catch (e) { r.error = String(e); }
const es = new EventSource("/events");
es.onmessage = (ev) => { r.sse++; r.last = ev.data; };
setInterval(() => {
  info.textContent = `WebGL ${r.webgl ? "可用" : "不可用"} · 帧 ${r.frames} · SSE 消息 ${r.sse}（最近 ${r.last}）`;
  fetch("/report", {method: "POST", body: JSON.stringify(r)});
}, 1000);
</script></body></html>
"""


def make_server(report: dict) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:  # noqa: A002
            pass

        def _send(self, body: bytes, kind: str) -> None:
            self.send_response(200)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802
            if self.path == "/":
                return self._send(PAGE.encode("utf-8"), "text/html; charset=utf-8")
            if self.path.startswith("/vendor/"):
                f = VENDOR / self.path[len("/vendor/"):]
                return self._send(f.read_bytes(), "text/javascript; charset=utf-8")
            if self.path == "/events":
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                n = 0
                try:
                    while True:
                        n += 1
                        self.wfile.write(f"id: {n}\ndata: {n}\n\n".encode("utf-8"))
                        self.wfile.flush()
                        time.sleep(1)
                except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                    return
            self.send_error(404)

        def do_POST(self) -> None:  # noqa: N802
            length = int(self.headers.get("Content-Length") or 0)
            report.update(json.loads(self.rfile.read(length).decode("utf-8")))
            self._send(b"{}", "application/json")

    class Server(ThreadingHTTPServer):
        daemon_threads = True

    return Server(("127.0.0.1", 0), Handler)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seconds", type=float, default=10)
    parser.add_argument("--browser", action="store_true", help="不开窗口，打印地址，用别的浏览器看")
    args = parser.parse_args()
    report: dict = {}
    server = make_server(report)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_address[1]}/"
    if args.browser:
        print(url, flush=True)
        time.sleep(args.seconds)
    else:
        import webview

        window = webview.create_window("探测 pywebview", url, width=520, height=420)

        def close_later() -> None:
            time.sleep(args.seconds)
            window.destroy()

        webview.start(close_later)
        print("webview 后端：", getattr(webview, "renderer", None) or getattr(webview.guilib, "renderer", "?"))
    server.shutdown()
    server.server_close()
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
