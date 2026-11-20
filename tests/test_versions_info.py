"""会话日志记录软件和模型版本（3.0 计划 1 Task 4；作业要求"记录软件及模型版本"）。

不连任何模型服务：桌面端用剧本里的假模型；钥匙串用内存里的假后端；数据目录放在临时目录里。
"""

from __future__ import annotations

import importlib.metadata
import json
import platform
from pathlib import Path

import keyring
import pytest

from cad_agent import app, brand, cli
from cad_agent.config import Config, PhaseOverride
from cad_agent.llm.providers import load_providers
from cad_agent.settings import Settings
from cad_agent.versions_info import collect_versions
from test_keystore import MemoryKeyring

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "demo_script.json"
FAKE_KEY = "fake-versions-key-0000-QWER"
KEYS = {"datum", "python", "simplecadapi", "openai", "anthropic", "platform", "provider", "model", "models_by_phase"}


def _startups(session_dir: Path) -> list[dict]:
    rows = [json.loads(line) for line in (session_dir / "log.jsonl").read_text(encoding="utf-8").splitlines()]
    return [r for r in rows if r.get("kind") == "startup"]


def test_collect_versions_keys():
    config = Config(base_url="https://api.deepseek.com/v1", model="deepseek-chat", provider="deepseek",
                    modeling=PhaseOverride(model="deepseek-reasoner"), review=PhaseOverride(model="glm-4.5v"))
    info = collect_versions(config)
    assert KEYS <= set(info)
    assert info["datum"] == brand.VERSION == "3.0.0"
    assert info["python"] == platform.python_version()
    assert info["simplecadapi"] == "2.2.7"
    assert info["openai"] == importlib.metadata.version("openai")
    assert info["anthropic"] == importlib.metadata.version("anthropic")
    assert info["platform"] and isinstance(info["platform"], str)
    assert info["provider"] == "deepseek" and info["model"] == "deepseek-chat"
    assert info["models_by_phase"] == {"clarify": "deepseek-chat", "modeling": "deepseek-reasoner", "review": "glm-4.5v"}
    json.dumps(info)   # 能原样写进日志


def test_no_key_in_versions(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", FAKE_KEY)
    monkeypatch.setenv("CALIPER_TEST_KEY", FAKE_KEY)
    config = Config(base_url=f"https://user:{FAKE_KEY}@api.example.com/v1?api_key={FAKE_KEY}#{FAKE_KEY}", model="m",
                    api_key_env="CALIPER_TEST_KEY", provider="custom")
    text = json.dumps(collect_versions(config), ensure_ascii=False)
    assert FAKE_KEY not in text and FAKE_KEY[-4:] not in text
    assert "?" not in text and "api.example.com" in text   # 地址只留到路径，查询参数和账号密码都去掉


@pytest.fixture
def desk(monkeypatch, tmp_path):
    monkeypatch.setenv("DATUM_HOME", str(tmp_path / "home"))
    for p in load_providers():
        monkeypatch.delenv(p.api_key_env, raising=False)
    previous = keyring.get_keyring()
    keyring.set_keyring(MemoryKeyring())
    yield tmp_path / "home"
    keyring.set_keyring(previous)


def test_desk_new_session_logs_startup(desk):
    settings = Settings()
    hub = app.build_hub(settings, script=SCRIPT)
    try:
        wb = hub.open(hub.create())
        rows = _startups(wb.session.dir)
    finally:
        hub.close()
    assert len(rows) == 1
    assert KEYS <= set(rows[0]) and rows[0]["datum"] == brand.VERSION and rows[0]["provider"] == settings.provider
    assert set(rows[0]["models_by_phase"]) == {"clarify", "modeling", "review"}


def test_desk_reopened_session_logs_startup_again(desk):
    hub = app.build_hub(Settings(), script=SCRIPT)
    try:
        sid = hub.create()
        session_dir = hub.open(sid).session.dir
    finally:
        hub.close()
    hub = app.build_hub(Settings(), script=SCRIPT)   # 关掉窗口再打开
    try:
        hub.open(sid)
    finally:
        hub.close()
    rows = _startups(session_dir)
    assert len(rows) == 2 and all(KEYS <= set(r) for r in rows)


def test_cli_still_logs_startup(monkeypatch, tmp_path):
    monkeypatch.setenv("DEEPSEEK_API_KEY", FAKE_KEY)
    cfg = tmp_path / "c.toml"
    cfg.write_text(f'[llm]\nbase_url = "http://x"\nmodel = "m"\n[agent]\nsessions_dir = "{(tmp_path / "s").as_posix()}"\n'
                   f'cases_dir = "{(tmp_path / "cases").as_posix()}"\n', encoding="utf-8")
    out: list[str] = []
    code = cli.main(["--config", str(cfg)], input_fn=lambda p="": "/quit", print_fn=lambda *a, **k: out.append(" ".join(map(str, a))))
    assert code == 0
    rows = _startups(next((tmp_path / "s").iterdir()))
    assert len(rows) == 1
    row = rows[0]
    assert KEYS <= set(row) and row["model"] == "m" and row["simplecadapi"] == "2.2.7" and row["python"].startswith("3.")
    assert row["cases"] == 8 and row["case_problems"] == []   # 原来的两项还在
    assert FAKE_KEY not in json.dumps(row) and "Python" in "\n".join(out)
