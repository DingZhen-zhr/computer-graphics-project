"""持续集成工作流 .github/workflows/ci.yml（第二版计划 4 Task 4）。只读文件，不运行任何东西。"""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CI = ROOT / ".github" / "workflows" / "ci.yml"


def _load() -> dict:
    return yaml.safe_load(CI.read_text(encoding="utf-8"))


def _on(data: dict) -> dict:
    # YAML 1.1 会把键 on 读成 True
    return data.get("on", data.get(True))


def _steps(data: dict) -> list[dict]:
    jobs = list(data["jobs"].values())
    assert len(jobs) == 1
    return jobs[0]["steps"]


def _step_text(step: dict) -> str:
    return " ".join(str(step.get(k, "")) for k in ("name", "uses", "run", "with", "env"))


def test_workflow_name_and_triggers():
    data = _load()
    assert data["name"] == "持续集成"
    on = _on(data)
    assert on["push"]["branches"] == ["master"]
    assert "pull_request" in on


def test_matrix_has_both_platforms():
    job = list(_load()["jobs"].values())[0]
    matrix = job["strategy"]["matrix"]
    assert matrix["os"] == ["windows-latest", "macos-14"]
    assert job["runs-on"] == "${{ matrix.os }}"
    assert job["strategy"].get("fail-fast") is False   # 一个平台失败时另一个照样跑完


def test_workflow_sets_up_uv_node_and_python_312():
    steps = _steps(_load())
    texts = [_step_text(s) for s in steps]
    assert any("actions/checkout@" in t for t in texts)
    assert any("astral-sh/setup-uv@" in t for t in texts)
    assert any("actions/setup-node@" in t for t in texts)
    assert any("uv venv --python 3.12" in t for t in texts)
    assert any('-e ".[dev]"' in t for t in texts)


def test_workflow_runs_tests_install_doctor_smoke():
    steps = _steps(_load())
    texts = [_step_text(s) for s in steps]

    def first(pred, start: int = 0) -> int:
        for i in range(start, len(texts)):
            if pred(texts[i]):
                return i
        raise AssertionError(f"没找到这一步（从第 {start} 步往后）")

    tests = first(lambda t: "pytest" in t)
    install = first(lambda t: "install.ps1" in t or "install.sh" in t, tests + 1)
    doctor = first(lambda t: "doctor --offline" in t, install + 1)
    smoke = first(lambda t: "--smoke" in t, doctor + 1)
    again = first(lambda t: "install.ps1" in t or "install.sh" in t, smoke + 1)
    assert tests < install < doctor < smoke < again
    # 两个平台各自用自己的安装脚本，来源都指向检出的目录
    whole = CI.read_text(encoding="utf-8")
    assert "install.ps1" in whole and "install.sh" in whole
    assert "CALIPER_SOURCE" in whole and "github.workspace" in whole
    assert "PYTHONUTF8" in whole


def test_workflow_uses_no_secrets():
    text = CI.read_text(encoding="utf-8")
    assert "secrets." not in text
    for word in ("API_KEY", "DEEPSEEK", "ANTHROPIC", "OPENAI"):
        assert word not in text.upper(), word
