"""README 和 Mac 人工清单（第二版计划 4 Task 7）。只读文件。"""

from __future__ import annotations

import re
from pathlib import Path

from cad_agent.maintenance import INSTALL_PS1, INSTALL_SH

ROOT = Path(__file__).resolve().parent.parent
README = ROOT / "README.md"
MAC = ROOT / "docs" / "mac-checklist.md"
HEADINGS = ["# Datum 基准", "## 安装", "## 装不上怎么办", "## 怎么用", "## 它是怎么保证质量的", "## 命令", "## 模型服务和密钥",
            "## 数据放在哪", "## 给开发者", "## 验证到什么程度", "## 参考与致谢"]


def _text() -> str:
    return README.read_text(encoding="utf-8")


def _section(title: str) -> str:
    text = _text()
    start = text.index(f"\n{title}\n")
    nxt = re.search(r"\n## ", text[start + len(title) + 2:])
    return text[start: start + len(title) + 2 + nxt.start()] if nxt else text[start:]


def test_readme_sections_in_order():
    lines = _text().splitlines()
    found = [line for line in lines if re.match(r"^#{1,2} ", line)]
    assert found == HEADINGS


def test_readme_install_commands_match():
    install = _section("## 安装")
    assert f"irm {INSTALL_PS1} | iex" in install
    assert f"curl -fsSL {INSTALL_SH} | sh" in install
    assert "Windows 10/11（64 位）" in install and "macOS 14" in install


def test_readme_has_screenshot():
    m = re.search(r"!\[[^\]]*\]\((docs/images/[^)]+)\)", _text())
    assert m and (ROOT / m.group(1)).is_file()


def test_readme_has_no_success_rate_for_v2():
    section = _section("## 验证到什么程度")
    assert "没有做过真实模型的成功率评测" in section
    assert "docs/results-v1.1.md" in section


def test_readme_mentions_unverified_parts():
    section = _section("## 模型服务和密钥")
    assert "未用真实接口验证" in section
    for name in ("Claude", "看图审查"):
        assert name in section, name
    assert "DeepSeek 以外" in section


def test_readme_trouble_section():
    section = _section("## 装不上怎么办")
    for word in ("DATUM_MIRROR", "DATUM_SOURCE", "WebView2", "datum doctor", "Get-Content -Raw -Encoding UTF8"):
        assert word in section, word
    for item in ("platform", "python", "sca", "sandbox", "workdir", "window", "keyring", "data", "provider", "key"):
        assert f"`{item}`" in section, item


def test_readme_commands_section():
    section = _section("## 命令")
    for cmd in ("datum", "datum --browser", "datum --cli", "datum doctor", "datum update", "datum uninstall"):
        assert f"`{cmd}" in section, cmd


def test_readme_developer_section_warns_about_cost():
    section = _section("## 给开发者")
    assert "--budget 15" in section and "会花钱" in section
    for gate in ("staged", "mutation_check", "visual_review", "cases"):
        assert gate in section, gate


def test_readme_has_no_old_commands():
    text = _text()
    for old in ("start_web.bat", "start_public", "python -m cad_agent.web"):
        assert old not in text, old


def test_mac_checklist_has_all_items():
    text = MAC.read_text(encoding="utf-8")
    items = [line for line in text.splitlines() if line.lstrip().startswith("- [ ]")]
    assert len(items) >= 15
    for word in ("系统版本", "芯片", "安装命令", "应用程序", "datum doctor", "引导", "--demo-script", "旋转", "阶段刻度",
                 "参数", "深色", "字体", "STEP", "在文件夹中显示", "重开", "datum uninstall"):
        assert any(word in item for item in items), word
    assert all("看到了什么" in item or "看到了什么" in text for item in items)
    tail = text.strip().splitlines()[-4:]
    assert any("签名" in line for line in tail) and any("日期" in line for line in tail)


def test_readme_v3_name_and_multipart():
    """3.0 计划 5 Task 5：README 用 Datum 的名字；"卡尺"只出现在讲从第二版升级的句子里；有多零件一节、teardown 致谢。"""
    text = README.read_text(encoding="utf-8")
    assert text.startswith("# Datum 基准")
    for line in text.splitlines():
        if "卡尺" in line:
            assert "第二版" in line, line
    assert "### 多个零件和会动的东西" in text and "装配和运动检查" in text and "teardown" in text
