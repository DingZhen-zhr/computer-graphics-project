"""桌面端页面的静态检查（第二版计划 3 Task 8 起）：node 测试、脚本语法、离线、三栏、文件长度、颜色字面值。"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "cad_agent" / "desk" / "static"
JS = STATIC / "js"
NODE = shutil.which("node")
needs_node = pytest.mark.skipif(NODE is None, reason="没有 node")   # 这台机器有 node；CI 里也装了


def _own_files(*suffixes: str) -> list[Path]:
    # 第三方的 three.js 不算自己写的文件：计划 4 Task 6 把它搬进了 static/vendor/three/（偏离 D19）
    return sorted(p for p in STATIC.rglob("*")
                  if p.is_file() and p.suffix in suffixes and "vendor" not in p.relative_to(STATIC).parts)


@needs_node
def test_node_tests_pass():
    files = sorted(str(p) for p in (JS / "tests").glob("*.test.js"))
    assert files, "还没有 node 测试"
    env = {**os.environ, "NODE_NO_WARNINGS": "1"}
    result = subprocess.run([NODE, "--test", *files], capture_output=True, text=True, encoding="utf-8", env=env, timeout=120)
    assert result.returncode == 0, result.stdout[-3000:] + result.stderr[-2000:]
    assert re.search(r"^# fail 0$", result.stdout, re.M), result.stdout[-2000:]


@needs_node
def test_all_modules_parse():
    files = _own_files(".js")
    assert len(files) >= 8
    for path in files:
        result = subprocess.run([NODE, "--check", "--input-type=module"], input=path.read_text(encoding="utf-8"),
                                capture_output=True, text=True, encoding="utf-8", timeout=60)
        assert result.returncode == 0, (path.name, result.stderr[:500])


def test_no_external_resources():
    for path in _own_files(".js", ".css", ".html"):
        for line in path.read_text(encoding="utf-8").splitlines():
            if "http://" in line or "https://" in line:
                assert ("许可证" in line or "License" in line) and line.strip().startswith(("//", "/*", "*", "<!--")), (path.name, line)
        text = path.read_text(encoding="utf-8")
        assert "innerHTML" not in text and "insertAdjacentHTML" not in text and "document.write" not in text, path.name


def test_index_has_three_columns_and_import_map():
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    assert '<html lang="zh-CN"' in html and '<meta charset="utf-8">' in html
    m = re.search(r'<script type="importmap">(.*?)</script>', html, re.S)
    assert m and __import__("json").loads(m.group(1)) == {"imports": {"three": "/static/vendor/three/three.module.js"}}
    for region in ('class="sidebar"', 'class="chat"', 'class="bench"'):
        assert html.count(region) == 1, region
    for css in ("tokens.css", "base.css", "layout.css"):
        assert f'href="/static/css/{css}"' in html
    assert '<script type="module" src="/static/js/main.js"></script>' in html
    layout = (STATIC / "css" / "layout.css").read_text(encoding="utf-8")
    assert "240px" in layout and "minmax(420px" in layout and "minmax(440px" in layout


def test_every_file_under_300_lines():
    for path in _own_files(".js", ".css", ".html"):
        n = len(path.read_text(encoding="utf-8").splitlines())
        assert n <= 300, (path.name, n)


def test_no_color_literals_in_js():
    for path in _own_files(".js", ".html"):
        text = re.sub(r"//[^\n]*|/\*.*?\*/|<!--.*?-->", "", path.read_text(encoding="utf-8"), flags=re.S)
        assert not re.search(r"(?<![\w&])#[0-9a-fA-F]{3}(?:[0-9a-fA-F]{3})?(?:[0-9a-fA-F]{2})?\b", text), path.name
        assert not re.search(r"\b(rgba?|hsla?)\(", text), path.name
        assert not re.search(r"\b0x[0-9a-fA-F]{6}\b", text), path.name


def test_page_texts_are_verbatim():
    """计划"界面文字"一节里这一任务用到的原文（逐字）。"""
    text = "\n".join(p.read_text(encoding="utf-8") for p in _own_files(".js", ".html"))
    for line in ("连接断开，正在重试", '删除"${', '"？它的全部版本和文件都会一起删掉，不能恢复。'):
        assert line in text, line
