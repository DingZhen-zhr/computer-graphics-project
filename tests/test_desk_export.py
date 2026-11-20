"""把一个会话导出成静态回放，产品主页（第二版计划 4 Task 5）。"""

from __future__ import annotations

import filecmp
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from cad_agent.desk.export import DEFAULT_TITLE, export_static
from cad_agent.desk.routes import VERSION_FILES
from cad_agent.maintenance import INSTALL_PS1, INSTALL_SH, REPO

ROOT = Path(__file__).resolve().parent.parent
DEMO = ROOT / "cad_agent" / "desk" / "demo_data" / "phone_stand"
SITE = ROOT / "site"
DEMO_TITLE = DEFAULT_TITLE   # 命令行不给 --title 时用的标题；site/demo/ 就是这样导出的
NODE = shutil.which("node")
TEXT_SUFFIXES = {".html", ".js", ".css", ".json", ".py", ".md", ".step", ".txt", ""}
REQUIREMENTS = "Windows 10/11（64 位），或 Apple 芯片的 Mac（macOS 14 及以上）。需要一个大模型服务的 API key，推荐 DeepSeek。"


@pytest.fixture(scope="module")
def exported(tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("export") / "demo"
    export_static(DEMO, out, title=DEMO_TITLE)
    return out


def _all_files(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*") if p.is_file())


def test_export_layout(exported):
    assert (exported / "index.html").is_file()
    assert (exported / "static" / "js" / "main.js").is_file() and (exported / "static" / "css" / "tokens.css").is_file()
    assert (exported / "static" / "vendor" / "three" / "three.module.js").is_file()
    assert (exported / "state.json").is_file() and (exported / "files").is_dir()
    html = (exported / "index.html").read_text(encoding="utf-8")
    assert 'data-mode="static"' in html
    assert f"<title>{DEMO_TITLE} · 卡尺 Caliper</title>" in html
    assert '"/static/' not in html and "'/static/" not in html   # 都是相对路径，放在子目录里也能用
    # import map 里的相对地址必须以 ./ 开头，写成 static/… 浏览器会当成无效地址，three.js 加载不了
    m = re.search(r'<script type="importmap">(.*?)</script>', html, re.S)
    assert json.loads(m.group(1)) == {"imports": {"three": "./static/vendor/three/three.module.js"}}
    state = json.loads((exported / "state.json").read_text(encoding="utf-8"))
    assert state["session"]["demo"] is True
    assert [v["name"] for v in state["versions"]] == ["v1", "v2"]
    assert state["busy"] is False
    for v in state["versions"]:
        assert (exported / "files" / v["name"] / "view.png").is_file()
        assert (exported / "files" / v["name"] / "model.stl").is_file()


def test_export_has_versions_diff(exported):
    """版本对比在静态回放里没有服务算，导出时先算好放进 state.json。"""
    state = json.loads((exported / "state.json").read_text(encoding="utf-8"))
    diffs = state["static_diffs"]
    assert "v1|v2" in diffs and diffs["v1|v2"] and "v2|v1" in diffs


def test_export_has_no_absolute_paths_or_secrets(exported):
    home = str(Path.home())
    patterns = [re.compile(r"\b[A-Za-z]:[\\/]"), re.compile(r"[\\/]Users[\\/]"), re.compile(r"[\\/]home[\\/]\w"),
                re.compile(r"sk-[A-Za-z0-9]{8,}")]
    checked = 0
    for p in _all_files(exported):
        if p.suffix not in TEXT_SUFFIXES:
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        assert home not in text and home.replace("\\", "\\\\") not in text and home.replace("\\", "/") not in text, p
        for pat in patterns:
            m = pat.search(text)
            assert m is None, (p.relative_to(exported), text[max(0, m.start() - 40):m.end() + 40])
        checked += 1
    assert checked > 10


def test_export_only_whitelisted_files(exported):
    for p in _all_files(exported / "files"):
        rel = p.relative_to(exported / "files").parts
        assert re.fullmatch(r"v\d+", rel[0]), rel
        assert (len(rel) == 2 and rel[1] in VERSION_FILES) or (len(rel) == 3 and rel[1] == "stages" and rel[2].endswith(".stl")), rel
    top = {p.name for p in exported.iterdir()}
    assert top <= {"index.html", "static", "state.json", "files", ".nojekyll"}, top


def test_export_refuses_to_overwrite_a_foreign_dir(tmp_path):
    out = tmp_path / "mine"
    out.mkdir()
    (out / "keep.txt").write_text("别删我", encoding="utf-8")
    with pytest.raises(FileExistsError):
        export_static(DEMO, out, title=DEMO_TITLE)
    assert (out / "keep.txt").is_file()


def test_export_command_line(tmp_path):
    out = tmp_path / "cli"
    r = subprocess.run([str(Path(os.sys.executable)), "-m", "cad_agent.desk.export", str(DEMO), str(out)],
                       capture_output=True, text=True, encoding="utf-8", env={**os.environ, "PYTHONUTF8": "1"}, cwd=ROOT, timeout=120)
    assert r.returncode == 0, r.stderr
    assert (out / "state.json").is_file()


@pytest.mark.skipif(NODE is None, reason="没有 node")
def test_static_mode_api():
    test_file = ROOT / "cad_agent" / "desk" / "static" / "js" / "tests" / "api-static.test.js"
    r = subprocess.run([NODE, "--test", str(test_file)], capture_output=True, text=True, encoding="utf-8",
                       env={**os.environ, "NODE_NO_WARNINGS": "1"}, timeout=120)
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr[-2000:]
    assert re.search(r"^# fail 0$", r.stdout, re.M)
    assert re.search(r"^# pass [1-9]", r.stdout, re.M)


def test_site_is_up_to_date(tmp_path):
    fresh = tmp_path / "demo"
    export_static(DEMO, fresh, title=DEMO_TITLE)
    committed = SITE / "demo"
    fresh_files = {p.relative_to(fresh).as_posix() for p in _all_files(fresh)}
    committed_files = {p.relative_to(committed).as_posix() for p in _all_files(committed)}
    assert fresh_files == committed_files, sorted(fresh_files ^ committed_files)[:10]
    for rel in sorted(fresh_files):
        assert filecmp.cmp(fresh / rel, committed / rel, shallow=False), (
            f"site/demo/{rel} 不是最新的，请重新运行 python -m cad_agent.desk.export cad_agent/desk/demo_data/phone_stand site/demo")


def test_homepage_content():
    html = (SITE / "index.html").read_text(encoding="utf-8")
    assert f"irm {INSTALL_PS1} | iex" in html
    assert f"curl -fsSL {INSTALL_SH} | sh" in html
    assert REQUIREMENTS in html
    assert "说出你要的零件，它来建模，每一步都实测。" in html and "卡尺 Caliper" in html
    assert 'href="demo/"' in html
    assert f"https://github.com/{REPO}" in html
    for step in ("澄清", "确认", "规划", "逐阶段建模与实测", "终检与交付"):
        assert step in html, step
    # 没有外部脚本、样式、字体
    assert not re.search(r"<script[^>]+src=[\"']https?://", html)
    assert not re.search(r"<link[^>]+href=[\"']https?://", html)
    assert "@import" not in html and "fonts.googleapis" not in html and "url(http" not in html
    # 没有成功率数字
    visible = re.sub(r"<(style|script)\b.*?</\1>", " ", html, flags=re.S)   # 样式里的 100% 不是成功率
    text = re.sub(r"<[^>]+>", " ", visible)
    assert not re.search(r"\d+(\.\d+)?\s*%", text), re.findall(r".{20}\d+(?:\.\d+)?\s*%.{5}", text)
    assert "成功率" not in text
    # 复制按钮
    assert html.count("复制") >= 2


def test_homepage_uses_the_same_tokens_and_both_themes():
    html = (SITE / "index.html").read_text(encoding="utf-8")
    assert 'href="demo/static/css/tokens.css"' in html
    assert "prefers-color-scheme" in html or "data-theme" in html


def test_pages_workflow_publishes_site():
    text = (ROOT / ".github" / "workflows" / "pages.yml").read_text(encoding="utf-8")
    data = yaml.safe_load(text)
    steps = list(data["jobs"].values())[0]["steps"]
    upload = [s for s in steps if "upload-pages-artifact" in str(s.get("uses", ""))]
    assert upload and upload[0]["with"]["path"] == "site"
    assert any("deploy-pages" in str(s.get("uses", "")) for s in steps)
    assert "python -m cad_agent.desk.export cad_agent/desk/demo_data/phone_stand site/demo" in text
    assert "cad_agent.web" not in text
    assert "secrets." not in text


def test_exported_scripts_import_only_relative_paths(exported):
    """在线回放放在 /computer-graphics-project/demo/ 下面：脚本里 import 的地址不能以 / 开头（Task 5 实测时 3D 视图因此没加载出来）。"""
    bad = []
    for p in _all_files(exported / "static" / "js"):
        for line in p.read_text(encoding="utf-8").splitlines():
            if re.match(r"\s*(import|export)\b.*\bfrom\s+[\"']/", line):
                bad.append(f"{p.name}: {line.strip()}")
    assert bad == []


def test_export_writes_lf_line_endings(exported):
    """Windows 上检出代码时 git 会把文字文件换成 CRLF：导出要不受影响，否则 site/demo/ 在不同电脑上导出来不一样
    （持续集成第一次运行时旧的同类测试就因为 three.js 的 LICENSE 换行不同而失败）。"""
    crlf = [p.relative_to(exported).as_posix() for p in _all_files(exported)
            if p.suffix in TEXT_SUFFIXES and b"\r\n" in p.read_bytes()]
    assert crlf == []


def test_export_does_not_depend_on_file_times(tmp_path):
    """持续集成第二次运行时 site/demo/state.json 和现导出的不一样：版本的 created 原来取的是目录的修改时间，
    换一台电脑检出就变了。导出时改用会话日志里这个版本交付时记下的时间。"""
    import os

    copy = tmp_path / "src" / "phone_stand"
    shutil.copytree(DEMO, copy)
    for p in [copy, *copy.rglob("*")]:
        os.utime(p, (1_000_000_000, 1_000_000_000))   # 2001 年
    export_static(DEMO, tmp_path / "a", title=DEMO_TITLE)
    export_static(copy, tmp_path / "b", title=DEMO_TITLE)
    assert (tmp_path / "a" / "state.json").read_bytes() == (tmp_path / "b" / "state.json").read_bytes()
    state = json.loads((tmp_path / "a" / "state.json").read_text(encoding="utf-8"))
    assert [v["created"] for v in state["versions"]] == ["2026-11-09T17:36:15", "2026-11-09T17:36:24"]
