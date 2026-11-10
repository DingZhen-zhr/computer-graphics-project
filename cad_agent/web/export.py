r"""把一个会话导出成静态网页（只读回放），放到 GitHub Pages 之类只能放静态文件的地方。

    .venv\Scripts\python -m cad_agent.web.export demo\phone_stand site

导出后的目录里：index.html（标成静态模式）、static/（页面和 three.js）、api/state.json（回放快照）、
files/vN/（各版本的截图、STL、STEP、源文件、检查报告）。页面里的路径都是相对的，放在子路径下也能用。
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from cad_agent.web.app import ReplayApp
from cad_agent.web.server import FILE_WHITELIST, STATIC_DIR

MARKER = ".cad-agent-site"  # 只清空带这个标记的目录，免得误删别的东西
LIVE_FILE = "live.json"


def export_site(session_dir: Path, out_dir: Path) -> Path:
    out_dir = Path(out_dir)
    live = (out_dir / LIVE_FILE).read_bytes() if (out_dir / LIVE_FILE).is_file() else None  # 实时体验的网址，由 go_public 维护，导出时保留
    if out_dir.exists():
        if any(out_dir.iterdir()) and not (out_dir / MARKER).is_file():
            raise FileExistsError(f"{out_dir} 不是空目录，也不是之前导出的演示站，不覆盖")
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)
    (out_dir / MARKER).write_text("由 python -m cad_agent.web.export 生成，重新导出时会整个覆盖\n", encoding="utf-8")
    (out_dir / ".nojekyll").write_text("", encoding="utf-8")  # GitHub Pages 不要用 Jekyll 处理
    if live is not None:
        (out_dir / LIVE_FILE).write_bytes(live)

    app = ReplayApp(Path(session_dir))
    shutil.copytree(STATIC_DIR, out_dir / "static", ignore=shutil.ignore_patterns("index.html"))
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    html = html.replace('<html lang="zh-CN">', '<html lang="zh-CN" data-mode="static">', 1)
    (out_dir / "index.html").write_text(html, encoding="utf-8")

    snap = app.snapshot()
    (out_dir / "api").mkdir()
    (out_dir / "api" / "state.json").write_text(json.dumps(snap, ensure_ascii=False), encoding="utf-8")
    for v in snap["versions"]:
        src = app.version_dir(v["name"])
        dst = out_dir / "files" / v["name"]
        dst.mkdir(parents=True)
        for name in FILE_WHITELIST:
            if src is not None and (src / name).is_file():
                shutil.copyfile(src / name, dst / name)
    return out_dir


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m cad_agent.web.export", description="把会话导出成静态的只读演示站")
    parser.add_argument("session_dir")
    parser.add_argument("out_dir")
    args = parser.parse_args(argv)
    try:
        out = export_site(Path(args.session_dir), Path(args.out_dir))
    except (FileNotFoundError, FileExistsError) as e:
        print(e)
        return 1
    print(f"已导出到 {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
