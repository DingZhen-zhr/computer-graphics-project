"""桌面端自带的示例会话（第二版计划 3 Task 12）。"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

from cad_agent.desk.hub import Hub

ROOT = Path(__file__).resolve().parent.parent
DEMO = ROOT / "cad_agent" / "desk" / "demo_data"


def test_demo_data_is_packaged():
    d = DEMO / "phone_stand"
    for rel in ("log.jsonl", "brief.json", "versions/v1/model.stl", "versions/v1/view.png", "versions/v1/model.step", "versions/v2/model.stl"):
        assert (d / rel).is_file(), rel
    # 和仓库里的录制一模一样
    for path in (ROOT / "demo" / "phone_stand" / "versions").rglob("*"):
        if path.is_file():
            copy = d / "versions" / path.relative_to(ROOT / "demo" / "phone_stand" / "versions")
            assert copy.is_file() and copy.read_bytes() == path.read_bytes(), copy
    assert (d / "log.jsonl").read_bytes() == (ROOT / "demo" / "phone_stand" / "log.jsonl").read_bytes()
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert "desk/demo_data/**/*" in data["tool"]["setuptools"]["package-data"]["cad_agent"]
    assert "desk/static/**/*" in data["tool"]["setuptools"]["package-data"]["cad_agent"]


def test_demo_session_state(tmp_path):
    hub = Hub(make_agent=lambda s: None, sessions_dir=tmp_path / "s", cases_dir=tmp_path / "c", demo_dir=DEMO)   # type: ignore[arg-type,return-value]
    assert [x["id"] for x in hub.list()] == ["demo-phone_stand"]
    st = hub.open("demo-phone_stand").state()
    assert st["session"]["demo"] is True and len(st["versions"]) >= 1 and st["transcript"]
    assert st["phase"] == "delivered" and st["versions"][-1]["has_stl"] is True


def test_demo_log_has_no_secrets():
    for path in (DEMO / "phone_stand").rglob("*"):
        if path.suffix in (".json", ".jsonl", ".py", ".md"):
            text = path.read_text(encoding="utf-8")
            assert "sk-" not in text, path.name
            assert not re.search(r'"api_key"\s*:\s*"[^"]+"', text), path.name
            assert not re.search(r"(?i)bearer\s+[a-z0-9]", text), path.name
