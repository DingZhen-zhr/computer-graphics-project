"""3.0 计划 5 Task 3：演示脚本和实验报告初稿。"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "docs" / "demo-script.md"
REPORT = ROOT / "docs" / "report-draft.md"
RESULTS = ROOT / "docs" / "results-v3.md"


def test_titles():
    demo = DEMO.read_text(encoding="utf-8")
    for t in ("## 镜头 1：需求输入", "## 镜头 2：自动建模", "## 镜头 3：反馈修正", "## 镜头 4：多轮修改", "## 单零件版", "## 录制前的检查清单"):
        assert t in demo, t
    report = REPORT.read_text(encoding="utf-8")
    for t in ("## 1 系统设计", "## 2 测试与结果", "## 3 自主完成的工作", "## 4 成员分工", "## 5 不足与后续"):
        assert t in report, t


def test_success_counts_come_from_results():
    report = REPORT.read_text(encoding="utf-8")
    results = RESULTS.read_text(encoding="utf-8") if RESULTS.is_file() else ""
    for frac in re.findall(r"\b\d+/\d+\b", report):
        assert frac in results, f"报告里的 {frac} 在 docs/results-v3.md 里找不到"


def test_member_section_has_no_names():
    section = REPORT.read_text(encoding="utf-8").split("## 4 成员分工", 1)[1].split("## 5", 1)[0]
    rows = [ln for ln in section.splitlines() if ln.startswith("|") and "---" not in ln][1:]
    assert rows and all(set(c.strip() for c in r.strip("|").split("|")) == {"请填写"} for r in rows)


def test_no_key():
    for p in (DEMO, REPORT):
        text = p.read_text(encoding="utf-8")
        assert not re.search(r"sk-[A-Za-z0-9]{16,}", text), p.name
