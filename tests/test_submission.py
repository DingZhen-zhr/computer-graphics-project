"""3.0 计划 5 Task 1：一键整理提交材料。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cad_agent.submission import build_submission, submission_main

ROOT = Path(__file__).resolve().parents[1]
SECRET = "sk-" + "tst" * 4 + str(7 * 1234567)   # 拼出来的：仓库里不出现这个完整的值


def _session(root: Path, name: str, versions=("v1",), multipart=False) -> Path:
    s = root / name
    s.mkdir(parents=True)
    (s / "log.jsonl").write_text('{"kind": "user", "text": "做个支架"}\n', encoding="utf-8")
    (s / "brief.json").write_text("{}", encoding="utf-8")
    for v in versions:
        d = s / "versions" / v
        d.mkdir(parents=True)
        if multipart:
            for pid in ("body", "lid"):
                (d / "parts" / pid).mkdir(parents=True)
                (d / "parts" / pid / "model.py").write_text("# 零件", encoding="utf-8")
                (d / "parts" / pid / "model.step").write_text("STEP", encoding="utf-8")
            for n in ("assembly.py", "product.step", "motion.json", "view.png"):
                (d / n).write_text("x", encoding="utf-8")
        else:
            for n in ("model.py", "model.step", "model.stl", "view.png"):
                (d / n).write_text("x", encoding="utf-8")
    return s


def test_layout_and_checklist(tmp_path):
    s = _session(tmp_path / "sessions", "20261120-1")
    r = build_submission([s], tmp_path / "out", repo_root=ROOT)
    assert r.folder == tmp_path / "out" and not r.warnings
    for d in ("01-代码/cad_agent", "01-代码/benchmarks", "01-代码/scripts", "01-代码/tests", "02-提示词与工具定义",
              "03-测试需求与验收结果/tasks", "04-参数化源文件与STEP/20261120-1/v1", "05-运行日志/20261120-1", "06-配置和运行说明"):
        assert (r.folder / d).is_dir(), d
    assert (r.folder / "04-参数化源文件与STEP/20261120-1/v1/model.step").is_file()
    assert (r.folder / "02-提示词与工具定义/prompts-and-tools.md").is_file()
    assert not any("__pycache__" in p.parts for p in (r.folder / "01-代码").rglob("*"))
    text = (r.folder / "清单.md").read_text(encoding="utf-8")
    assert "| 代码 | 01-代码/ | 已放入 |" in text


def test_session_without_versions_is_listed(tmp_path):
    s = _session(tmp_path / "sessions", "empty", versions=())
    r = build_submission([s], tmp_path / "out", repo_root=ROOT)
    assert r.folder is not None
    assert "这个会话没有交付版本，只带了运行日志" in (r.folder / "清单.md").read_text(encoding="utf-8")
    assert (r.folder / "05-运行日志/empty/log.jsonl").is_file()


def test_existing_target_is_not_overwritten(tmp_path):
    (tmp_path / "out").mkdir()
    (tmp_path / "out" / "mine.txt").write_text("别动", encoding="utf-8")
    r = build_submission([], tmp_path / "out", repo_root=ROOT)
    assert r.folder == tmp_path / "out-2"
    assert (tmp_path / "out" / "mine.txt").read_text(encoding="utf-8") == "别动"


def test_key_in_session_blocks_export(tmp_path, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", SECRET)
    s = _session(tmp_path / "sessions", "leak")
    (s / "log.jsonl").write_text(json.dumps({"kind": "failed", "text": f"401 {SECRET}"}) + "\n", encoding="utf-8")
    r = build_submission([s], tmp_path / "out", repo_root=ROOT)
    assert r.folder is None and not (tmp_path / "out").exists()
    assert r.warnings == ["05-运行日志/leak/log.jsonl 第 1 行里有 key"]


def test_no_absolute_paths_in_checklist(tmp_path):
    s = _session(tmp_path / "sessions", "a")
    r = build_submission([s], tmp_path / "out", repo_root=ROOT)
    text = (r.folder / "清单.md").read_text(encoding="utf-8")
    assert str(tmp_path) not in text and ":\\" not in text and str(ROOT) not in text


def test_multipart_session_files(tmp_path):
    s = _session(tmp_path / "sessions", "box", multipart=True)
    r = build_submission([s], tmp_path / "out", repo_root=ROOT)
    v = r.folder / "04-参数化源文件与STEP/box/v1"
    for n in ("assembly.py", "product.step", "motion.json", "parts/body/model.py", "parts/lid/model.step"):
        assert (v / n).is_file(), n


def test_command_line(tmp_path, monkeypatch, capsys):
    home = tmp_path / "home"
    monkeypatch.setenv("DATUM_HOME", str(home))
    _session(home / "sessions", "done")
    _session(home / "sessions", "empty", versions=())
    assert submission_main([str(tmp_path / "pkg")]) == 0
    assert (tmp_path / "pkg/04-参数化源文件与STEP/done").is_dir() and not (tmp_path / "pkg/05-运行日志/empty").exists()
    assert submission_main([str(tmp_path / "pkg"), "--session", "nope"]) == 2
    assert "没有这些会话" in capsys.readouterr().out
