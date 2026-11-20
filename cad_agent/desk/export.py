r"""把一个会话导出成静态回放（第二版计划 4 Task 5），放到 GitHub Pages 这种只能放静态文件的地方。

    .venv\Scripts\python -m cad_agent.desk.export cad_agent/desk/demo_data/phone_stand site/demo

输出目录里：
- index.html：桌面端的页面，根元素带 data-mode="static"（api.js 看到它就从下面的文件里读，写操作一律返回"只读"）；
- static/：样式、脚本、three.js；
- state.json：这个会话的完整状态（demo 为真），另带 static_diffs（各版本两两之间的参数变化，在线回放没有服务来算）；
- files/<版本>/…：白名单里的文件（截图、STL、STEP、源文件、检查报告、各阶段的 STL）。
页面里的路径都是相对的，放在子目录下也能用。导出的文字里不留绝对路径、用户名（会话日志里录到的路径只留 versions\… 之后的部分）。
"""

from __future__ import annotations

import argparse
import itertools
import json
import re
import shutil
import sys
from pathlib import Path
from typing import Any

from cad_agent import brand
from cad_agent.cli import _load_brief, diff_briefs
from cad_agent.desk.routes import STAGE_FILE_RE, VERSION_FILES
from cad_agent.desk.server import STATIC_DIR
from cad_agent.desk.workbench import Workbench
from cad_agent.session import Session

DEFAULT_TITLE = "在线示例"
STATIC_SKIP = ("index.html", "tests")   # 页面单独处理；node 测试不发布
# 这些是文字文件，导出时一律写成 LF 换行：Windows 上检出代码时 git 会把它们换成 CRLF，不统一的话不同电脑导出来不一样
TEXT_SUFFIXES = {".html", ".js", ".css", ".json", ".py", ".md", ".step", ".txt", ""}
CRLF, LF = b"\r\n", b"\n"
# 录在日志里的绝对路径：Windows 的盘符路径，或 Mac、Linux 用户目录下的路径。到空白、引号或中文标点为止
_ABS_PATH = re.compile(r"(?:[A-Za-z]:[\\/]|(?<![\w.])/(?:Users|home)/)[^\s\"'<>|，。；：）】]*")


def _short_path(match: re.Match) -> str:
    """绝对路径只留 versions 之后的部分（"versions\\v1\\view.png"）；没有 versions 就只留文件名。"""
    parts = re.split(r"[\\/]+", match.group(0))
    if "versions" in parts:
        sep = "\\" if "\\" in match.group(0) else "/"
        return sep.join(parts[parts.index("versions"):])
    return parts[-1]


def scrub(value: Any) -> Any:
    """把状态里所有文字中的绝对路径换成相对的；结构不变。"""
    if isinstance(value, str):
        return _ABS_PATH.sub(_short_path, value)
    if isinstance(value, list):
        return [scrub(v) for v in value]
    if isinstance(value, dict):
        return {k: scrub(v) for k, v in value.items()}
    return value


def _is_previous_export(out_dir: Path) -> bool:
    index = out_dir / "index.html"
    return (out_dir / "state.json").is_file() and index.is_file() and 'data-mode="static"' in index.read_text(encoding="utf-8")


def _prepare(out_dir: Path) -> None:
    if out_dir.exists():
        if any(out_dir.iterdir()) and not _is_previous_export(out_dir):
            raise FileExistsError(f"{out_dir} 不是空目录，也不是之前导出的回放，不覆盖")
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)


def _page(title: str) -> str:
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    html = html.replace('"/static/', '"./static/')   # import map 里的地址必须以 ./ 开头，不然解析不出来
    html = re.sub(r"<html ([^>]*)>", lambda m: f'<html {m.group(1)} data-mode="static">', html, count=1)
    return re.sub(r"<title>.*?</title>", f"<title>{title} · {brand.DISPLAY}</title>", html, count=1)


def _copy_static(out_dir: Path) -> None:
    shutil.copytree(STATIC_DIR, out_dir / "static", ignore=lambda d, names: [n for n in names if n in STATIC_SKIP])


def _copy_version_files(vdir: Path, dst: Path) -> None:
    for name in VERSION_FILES:
        if (vdir / name).is_file():
            dst.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(vdir / name, dst / name)
    stages = vdir / "stages"
    if stages.is_dir():
        for f in sorted(stages.iterdir()):
            if f.is_file() and STAGE_FILE_RE.fullmatch(f.name):
                (dst / "stages").mkdir(parents=True, exist_ok=True)
                shutil.copyfile(f, dst / "stages" / f.name)


def _normalize_line_endings(out_dir: Path) -> None:
    for f in sorted(out_dir.rglob("*")):
        if f.is_file() and f.suffix.lower() in TEXT_SUFFIXES:
            raw = f.read_bytes()
            if CRLF in raw:
                f.write_bytes(raw.replace(CRLF, LF))


def _created_from_log(session: Session) -> dict[str, str]:
    """各版本是什么时候生成的：取会话日志里交付（或手动改参数）那一行记下的时间。
    不用目录的修改时间：换一台电脑检出代码，修改时间就变了，导出来的 state.json 会不一样。"""
    out: dict[str, str] = {}
    for row in session.read_log():
        version, ts = row.get("version"), row.get("ts")
        if row.get("kind") in ("delivered", "manual") and isinstance(version, str) and isinstance(ts, str) and version not in out:
            out[version] = ts[:19]
    return out


def _diffs(session: Session, names: list[str]) -> dict[str, list[str]]:
    base = session.part_dir() / "versions"
    out: dict[str, list[str]] = {}
    for a, b in itertools.permutations(names, 2):
        out[f"{a}|{b}"] = diff_briefs(_load_brief(base / a), _load_brief(base / b))
    return out


def export_static(session_dir: Path, out_dir: Path, *, title: str) -> None:
    session_dir, out_dir = Path(session_dir), Path(out_dir)
    if not (session_dir / "log.jsonl").is_file():
        raise FileNotFoundError(f"{session_dir} 不是一个会话目录（里面没有 log.jsonl）")
    session = Session.open(session_dir)
    state = Workbench(None, session, demo=True).state()   # type: ignore[arg-type]  # 回放没有智能体
    names = [v["name"] for v in state["versions"]]
    created = _created_from_log(session)
    for v in state["versions"]:
        v["created"] = created.get(v["name"])
    state = scrub(state)
    state["static_diffs"] = scrub(_diffs(session, names))

    _prepare(out_dir)
    (out_dir / "index.html").write_text(_page(title), encoding="utf-8")
    _copy_static(out_dir)
    (out_dir / "state.json").write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    for name in names:
        _copy_version_files(session.part_dir() / "versions" / name, out_dir / "files" / name)
    _normalize_line_endings(out_dir)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m cad_agent.desk.export", description="把一个会话导出成静态的只读回放")
    parser.add_argument("session_dir", help="会话目录")
    parser.add_argument("out_dir", help="输出目录")
    parser.add_argument("--title", default=DEFAULT_TITLE, help=f"页面标题（默认：{DEFAULT_TITLE}）")
    args = parser.parse_args(argv)
    try:
        export_static(Path(args.session_dir), Path(args.out_dir), title=args.title)
    except (FileNotFoundError, FileExistsError) as e:
        print(e)
        return 1
    print(f"已导出到 {args.out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
