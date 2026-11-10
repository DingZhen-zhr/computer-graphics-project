r"""一键开放实时体验：在这台电脑上开服务 + Cloudflare 临时隧道，并把公网网址发布到演示站。

    .venv\Scripts\python scripts\go_public.py [--budget 5] [--max-busy 3] [--no-publish]

做的事：
1. 启动网页服务（公网模式：要访问密码、每人独立会话、共用花费上限）；
2. 启动 tools\cloudflared.exe 临时隧道，拿到 https://xxxx.trycloudflare.com；
3. 确认外网能连上后，把网址写进 site/live.json，只提交这一个文件并推送；
   GitHub Pages 大约一分钟后更新，演示站右上角就会出现"开始实时体验"；
4. 按 Ctrl+C（或关掉窗口）时停止服务和隧道，把 live.json 改回离线并推送。

访问密码从环境变量 CAD_WEB_PASSWORD 读；没有就在这里输入（不会显示，也不会写进任何文件）。
"""

from __future__ import annotations

import argparse
import datetime
import getpass
import json
import os
import re
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CLOUDFLARED = ROOT / "tools" / "cloudflared.exe"
LIVE = ROOT / "site" / "live.json"
PAGES_URL = "https://dingzhen-zhr.github.io/computer-graphics-project/"
URL_RE = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")
SERVER_RE = re.compile(r"http://127\.0\.0\.1:(\d+)/")


def say(text: str) -> None:
    print(text, flush=True)


def wait_health(url: str, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"{url.rstrip('/')}/api/health", timeout=5) as r:
                if r.status == 200 and json.loads(r.read()).get("ok"):
                    return True
        except Exception:  # noqa: BLE001 - 还没起来，接着等
            pass
        time.sleep(1.5)
    return False


def read_lines(stream, pattern: re.Pattern, found: list, echo: bool) -> None:
    """后台读子进程输出，找到第一个匹配就记下；echo 为真时原样打印。"""
    for raw in iter(stream.readline, ""):
        if echo:
            print(raw, end="", flush=True)
        if not found and (m := pattern.search(raw)):
            found.append(m.group(0) if pattern is URL_RE else m.group(1))


def publish(url: str | None, enabled: bool) -> None:
    """改 site/live.json，只提交这一个文件并推送。失败不影响服务，只提示。"""
    LIVE.write_text(json.dumps({"url": url, "updated": datetime.datetime.now().isoformat(timespec="seconds")}, ensure_ascii=False) + "\n",
                    encoding="utf-8")
    if not enabled:
        return
    msg = "chore: 实时体验上线" if url else "chore: 实时体验下线"
    for cmd in (["git", "add", "site/live.json"], ["git", "commit", "-q", "-m", msg, "--", "site/live.json"], ["git", "push", "-q", "origin", "HEAD"]):
        r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if r.returncode != 0 and "nothing to commit" not in (r.stdout + r.stderr):
            say(f"（更新演示站上的网址失败：{' '.join(cmd)}：{(r.stderr or r.stdout).strip()[:200]}；可以手动把网址发给大家）")
            return
    say("演示站上的实时体验入口已更新，大约一分钟后生效。" if url else "演示站已改回离线。")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="一键开放实时体验")
    parser.add_argument("--budget", type=float, default=5.0, help="所有人共用的花费上限（元），默认 5")
    parser.add_argument("--max-busy", type=int, default=3, help="同时在建模的人数上限，默认 3")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-publish", action="store_true", help="不更新演示站，只在这里打印网址")
    args = parser.parse_args(argv)

    if not CLOUDFLARED.is_file():
        say(f"缺少 {CLOUDFLARED}。请从 https://github.com/cloudflare/cloudflared/releases 下载 cloudflared-windows-amd64.exe，改名放到这里。")
        return 1
    env = dict(os.environ, PYTHONUTF8="1", PYTHONUNBUFFERED="1")  # 子进程输出不缓冲，才能及时读到它打印的网址
    if len(env.get("CAD_WEB_PASSWORD", "").strip()) < 6:
        env["CAD_WEB_PASSWORD"] = getpass.getpass("给这次体验设一个访问密码（至少 6 位，输入时不显示）：").strip()

    server = subprocess.Popen(
        [sys.executable, "-m", "cad_agent.web", "--config", "config.toml", "--public", "--no-browser", "--port", str(args.port),
         "--budget", str(args.budget), "--max-busy", str(args.max_busy)],
        cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
    port: list = []
    threading.Thread(target=read_lines, args=(server.stdout, SERVER_RE, port, True), daemon=True).start()
    deadline = time.monotonic() + 30
    while not port and server.poll() is None and time.monotonic() < deadline:
        time.sleep(0.3)
    if not port:
        say("网页服务没有启动成功（看上面的提示，常见原因：没设 API key、config.toml 没填价目表）。")
        server.kill()
        return 1
    local = f"http://127.0.0.1:{port[0]}"

    tunnel = subprocess.Popen([str(CLOUDFLARED), "tunnel", "--no-autoupdate", "--url", local], cwd=ROOT,
                              stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace")
    url: list = []
    threading.Thread(target=read_lines, args=(tunnel.stderr, URL_RE, url, False), daemon=True).start()
    deadline = time.monotonic() + 60
    while not url and tunnel.poll() is None and time.monotonic() < deadline:
        time.sleep(0.5)
    if not url or not wait_health(url[0], 60):
        say("临时隧道没有建立起来（检查网络后重试）。")
        tunnel.kill()
        server.kill()
        return 1

    say("")
    say(f"实时体验网址：{url[0]}")
    say(f"演示站：{PAGES_URL}（右上角会出现「开始实时体验」）")
    say(f"花费上限 ¥{args.budget:g}，同时建模最多 {args.max_busy} 人。按 Ctrl+C 结束开放。")
    say("")
    publish(url[0], not args.no_publish)
    try:
        while server.poll() is None and tunnel.poll() is None:
            time.sleep(1)
        say("服务或隧道意外停止了。")
    except KeyboardInterrupt:
        say("\n正在结束开放……")
    finally:
        for p in (tunnel, server):
            if p.poll() is None:
                p.terminate()
        publish(None, not args.no_publish)
    return 0


if __name__ == "__main__":
    sys.exit(main())
