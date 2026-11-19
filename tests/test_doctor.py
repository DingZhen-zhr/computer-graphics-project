"""caliper doctor 自检（第二版计划 4 Task 1）。

各项的探测函数都在测试里换掉；钥匙串用内存里的假后端，不碰真实的系统钥匙串；不连任何模型服务。
只有 test_all_ok_on_this_machine（标记 sca）真的用沙盒建一个方块。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import keyring
import pytest

from cad_agent import app, doctor
from cad_agent.doctor import CheckItem, doctor_exit_code, render_doctor, run_doctor
from cad_agent.llm.providers import load_providers
from test_keystore import MemoryKeyring, NoBackend

IDS = ["platform", "python", "sca", "sandbox", "workdir", "window", "keyring", "data", "provider", "key"]
FAKE_KEY = "fake-doctor-key-7Q2W9E4R6T"


@pytest.fixture
def env(monkeypatch, tmp_path):
    """数据目录放到临时目录；清掉所有模型服务的 key 环境变量；钥匙串换成内存后端；沙盒和网络都换成假的。"""
    monkeypatch.setenv("CALIPER_HOME", str(tmp_path / "home"))
    for p in load_providers():
        monkeypatch.delenv(p.api_key_env, raising=False)
    previous = keyring.get_keyring()
    backend = MemoryKeyring()
    keyring.set_keyring(backend)
    monkeypatch.setattr(doctor, "_sandbox_box", lambda: (10.0, 20.0, 30.0))
    monkeypatch.setattr(doctor, "_connect", lambda host, port, timeout: None)
    yield backend
    keyring.set_keyring(previous)


def by_id(items: list[CheckItem]) -> dict[str, CheckItem]:
    return {i.id: i for i in items}


@pytest.mark.sca
def test_all_ok_on_this_machine(monkeypatch, tmp_path):
    monkeypatch.setenv("CALIPER_HOME", str(tmp_path / "home"))
    previous = keyring.get_keyring()
    keyring.set_keyring(MemoryKeyring())
    try:
        items = run_doctor(offline=True)
    finally:
        keyring.set_keyring(previous)
    assert [i.status for i in items if i.status == "fail"] == [], render_doctor(items)
    assert by_id(items)["sandbox"].status == "ok"


def test_order_and_ids(env):
    items = run_doctor(offline=True)
    assert [i.id for i in items] == IDS
    assert all(isinstance(i, CheckItem) and i.name and i.detail for i in items)
    assert all(i.advice for i in items if i.status in ("warn", "fail"))


def test_non_ascii_temp_is_reported_with_fallback(env, monkeypatch, tmp_path):
    fallback = tmp_path / "work"
    monkeypatch.setattr(doctor, "_temp_dir", lambda: Path("C:/Users/张三/AppData/Local/Temp"))
    monkeypatch.setattr(doctor, "_fallback_dir", lambda: fallback)
    item = by_id(run_doctor(offline=True))["workdir"]
    assert item.status == "warn"
    assert "张三" in item.detail and "中文" in item.detail
    assert str(fallback) in item.detail and "自动改用" in item.detail
    assert fallback.is_dir() and list(fallback.iterdir()) == []   # 试写的文件删掉了


def test_fallback_dir_not_writable_is_a_failure(env, monkeypatch, tmp_path):
    monkeypatch.setattr(doctor, "_temp_dir", lambda: Path("C:/Users/张三/AppData/Local/Temp"))

    def cannot_create() -> Path:
        raise PermissionError("拒绝访问")

    monkeypatch.setattr(doctor, "_fallback_dir", cannot_create)
    item = by_id(run_doctor(offline=True))["workdir"]
    assert item.status == "fail" and "建不了" in item.detail
    assert item.advice

    # 目录能建、但写不进去，也是 fail
    monkeypatch.setattr(doctor, "_fallback_dir", lambda: tmp_path / "work")

    def cannot_write(path: Path) -> None:
        raise PermissionError("拒绝访问")

    monkeypatch.setattr(doctor, "_try_write", cannot_write)
    item = by_id(run_doctor(offline=True))["workdir"]
    assert item.status == "fail" and item.advice


def test_ascii_temp_is_ok(env, monkeypatch):
    monkeypatch.setattr(doctor, "_temp_dir", lambda: Path("C:/Temp"))
    assert by_id(run_doctor(offline=True))["workdir"].status == "ok"


def test_missing_webview2_is_a_warning_with_advice(env, monkeypatch):
    monkeypatch.setattr(doctor, "_system", lambda: "win32")
    monkeypatch.setattr(doctor, "_import_webview", lambda: None)
    monkeypatch.setattr(doctor, "_webview2_version", lambda: None)
    item = by_id(run_doctor(offline=True))["window"]
    assert item.status == "warn"
    assert "WebView2" in item.detail
    assert "WebView2" in item.advice and "caliper --browser" in item.advice


def test_webview2_present_is_ok(env, monkeypatch):
    monkeypatch.setattr(doctor, "_system", lambda: "win32")
    monkeypatch.setattr(doctor, "_import_webview", lambda: None)
    monkeypatch.setattr(doctor, "_webview2_version", lambda: "157.0.4341.60")
    item = by_id(run_doctor(offline=True))["window"]
    assert item.status == "ok" and "157.0.4341.60" in item.detail


def test_webview_import_failure_is_warn(env, monkeypatch):
    def broken() -> None:
        raise ImportError("No module named 'webview'")

    monkeypatch.setattr(doctor, "_import_webview", broken)
    item = by_id(run_doctor(offline=True))["window"]
    assert item.status == "warn" and "caliper --browser" in item.advice


def test_keyring_probe_cleans_up(env):
    item = by_id(run_doctor(offline=True))["keyring"]
    assert item.status == "ok"
    assert env.store == {}   # 测试项删掉了，什么都没留下


def test_keyring_probe_writes_under_its_own_service(env, monkeypatch):
    seen: list[tuple[str, str]] = []
    original = MemoryKeyring.set_password

    def spy(self, service, username, password):
        seen.append((service, username))
        original(self, service, username, password)

    monkeypatch.setattr(MemoryKeyring, "set_password", spy)
    run_doctor(offline=True)
    assert seen and all(service == "caliper-doctor" for service, _ in seen)


def test_keyring_unavailable_is_warn(env):
    keyring.set_keyring(NoBackend())
    item = by_id(run_doctor(offline=True))["keyring"]
    assert item.status == "warn"
    assert "环境变量" in item.advice


def test_provider_unreachable_is_warn(env, monkeypatch):
    calls: list[tuple[str, int, float]] = []

    def refuse(host: str, port: int, timeout: float) -> None:
        calls.append((host, port, timeout))
        raise TimeoutError("timed out")

    monkeypatch.setattr(doctor, "_connect", refuse)
    item = by_id(run_doctor(offline=False))["provider"]
    assert item.status == "warn" and item.advice
    assert calls == [("api.deepseek.com", 443, 5)]


def test_provider_reachable_is_ok(env, monkeypatch):
    calls: list[tuple[str, int, float]] = []
    monkeypatch.setattr(doctor, "_connect", lambda host, port, timeout: calls.append((host, port, timeout)))
    item = by_id(run_doctor(offline=False))["provider"]
    assert item.status == "ok" and "api.deepseek.com" in item.detail
    assert calls == [("api.deepseek.com", 443, 5)]


def test_offline_skips_provider(env, monkeypatch):
    def must_not_connect(host: str, port: int, timeout: float) -> None:
        raise AssertionError("离线时不该连网")

    monkeypatch.setattr(doctor, "_connect", must_not_connect)
    item = by_id(run_doctor(offline=True))["provider"]
    assert item.status == "skip"


def _fragments(secret: str, n: int = 4) -> list[str]:
    return [secret[i:i + n] for i in range(len(secret) - n + 1)]


def test_key_item_never_shows_key(env, monkeypatch, capsys):
    monkeypatch.setenv("DEEPSEEK_API_KEY", FAKE_KEY)
    items = run_doctor(offline=True)
    item = by_id(items)["key"]
    assert item.status == "ok" and "环境变量" in item.detail and "DEEPSEEK_API_KEY" in item.detail
    text = render_doctor(items)
    assert app.main(["doctor", "--offline", "--json"]) == 0
    out = capsys.readouterr().out
    for frag in _fragments(FAKE_KEY):
        assert frag not in text, frag
        assert frag not in out, frag

    # 钥匙串里的 key 也一样
    monkeypatch.delenv("DEEPSEEK_API_KEY")
    keyring.set_password("caliper", "deepseek", FAKE_KEY)
    items = run_doctor(offline=True)
    assert by_id(items)["key"].status == "ok" and "钥匙串" in by_id(items)["key"].detail
    text = render_doctor(items)
    for frag in _fragments(FAKE_KEY):
        assert frag not in text, frag


def test_no_key_is_warn(env):
    item = by_id(run_doctor(offline=True))["key"]
    assert item.status == "warn" and "DEEPSEEK_API_KEY" in item.advice


def test_one_crashing_check_does_not_stop_the_rest(env, monkeypatch):
    def boom() -> tuple:
        raise RuntimeError("探测的时候炸了")

    monkeypatch.setattr(doctor, "check_window", boom)
    items = run_doctor(offline=True)
    assert [i.id for i in items] == IDS
    item = by_id(items)["window"]
    assert item.status == "fail" and "RuntimeError" in item.detail and item.advice
    assert by_id(items)["keyring"].status == "ok" and by_id(items)["data"].status == "ok"


def test_data_dir_not_writable_is_fail(env, monkeypatch):
    real = doctor._try_write

    def deny(path: Path) -> None:
        if "home" in str(path):
            raise PermissionError("拒绝访问")
        real(path)

    monkeypatch.setattr(doctor, "_try_write", deny)
    item = by_id(run_doctor(offline=True))["data"]
    assert item.status == "fail" and item.advice


def test_platform_gate(env, monkeypatch):
    monkeypatch.setattr(doctor, "_platform_info", lambda: ("darwin", "x86_64", "14.5"))
    assert by_id(run_doctor(offline=True))["platform"].status == "fail"
    monkeypatch.setattr(doctor, "_platform_info", lambda: ("darwin", "arm64", "13.6"))
    assert by_id(run_doctor(offline=True))["platform"].status == "fail"
    monkeypatch.setattr(doctor, "_platform_info", lambda: ("darwin", "arm64", "14.5"))
    assert by_id(run_doctor(offline=True))["platform"].status == "ok"
    monkeypatch.setattr(doctor, "_platform_info", lambda: ("win32", "AMD64", "10.0.26200"))
    assert by_id(run_doctor(offline=True))["platform"].status == "ok"
    monkeypatch.setattr(doctor, "_platform_info", lambda: ("linux", "x86_64", "6.1"))
    assert by_id(run_doctor(offline=True))["platform"].status == "fail"


def test_python_version_gate(env, monkeypatch):
    monkeypatch.setattr(doctor, "_python_version", lambda: (3, 9, 18))
    assert by_id(run_doctor(offline=True))["python"].status == "fail"
    monkeypatch.setattr(doctor, "_python_version", lambda: (3, 12, 7))
    assert by_id(run_doctor(offline=True))["python"].status == "ok"
    monkeypatch.setattr(doctor, "_python_version", lambda: (3, 14, 0))
    assert by_id(run_doctor(offline=True))["python"].status == "fail"


def test_sca_wrong_version_is_fail(env, monkeypatch):
    monkeypatch.setattr(doctor, "_sca_version", lambda: "2.2.6")
    assert by_id(run_doctor(offline=True))["sca"].status == "fail"
    monkeypatch.setattr(doctor, "_sca_version", lambda: None)
    assert by_id(run_doctor(offline=True))["sca"].status == "fail"


def test_sandbox_wrong_size_is_fail(env, monkeypatch):
    monkeypatch.setattr(doctor, "_sandbox_box", lambda: (10.0, 20.0, 31.0))
    assert by_id(run_doctor(offline=True))["sandbox"].status == "fail"


def test_exit_code():
    ok = CheckItem("a", "甲", "ok", "好")
    warn = CheckItem("b", "乙", "warn", "注意", "这样办")
    skip = CheckItem("c", "丙", "skip", "跳过")
    fail = CheckItem("d", "丁", "fail", "坏了", "这样修")
    assert doctor_exit_code([ok, warn, skip]) == 0
    assert doctor_exit_code([ok, fail, warn]) == 1
    assert doctor_exit_code([]) == 0


def test_render_format():
    items = [CheckItem("a", "甲", "ok", "好的"), CheckItem("b", "乙", "warn", "有点问题", "这样办"),
             CheckItem("c", "丙", "skip", "跳过了"), CheckItem("d", "丁", "fail", "坏了", "这样修")]
    lines = render_doctor(items).splitlines()
    assert lines[0].startswith("✓") and "甲" in lines[0] and "好的" in lines[0]
    assert lines[1].startswith("!") and "乙" in lines[1] and "有点问题" in lines[1]
    assert lines[2].startswith("  ") and "这样办" in lines[2]
    assert lines[3].startswith("—") and "丙" in lines[3]
    assert lines[4].startswith("✗") and "丁" in lines[4]
    assert lines[5].startswith("  ") and "这样修" in lines[5]
    assert lines[-1] == "有 1 项不能用"
    assert render_doctor(items[:1]).splitlines()[-1] == "全部正常"
    assert render_doctor(items[:3]).splitlines()[-1] == "有 1 项需要注意"
    assert render_doctor([items[0], items[2]]).splitlines()[-1] == "全部正常"


def test_json_output(env, capsys):
    code = app.main(["doctor", "--offline", "--json"])
    rows = json.loads(capsys.readouterr().out)
    assert [r["id"] for r in rows] == IDS
    assert all(set(r) == {"id", "name", "status", "detail", "advice"} for r in rows)
    assert code == (1 if any(r["status"] == "fail" for r in rows) else 0)


def test_doctor_command_prints_report(env, capsys):
    code = app.main(["doctor", "--offline"])
    out = capsys.readouterr().out
    lines = out.strip().splitlines()
    assert lines[-1] in ("全部正常",) or re.fullmatch(r"有 \d+ 项(需要注意|不能用)", lines[-1])
    assert any(x.startswith("—") and "模型服务" in x for x in lines)
    assert code == (1 if lines[-1].endswith("不能用") else 0)


def test_smoke_flag(env, capsys):
    assert app.main(["--smoke"]) == 0
    assert capsys.readouterr().out.strip().splitlines()[-1] == "smoke ok"


def test_smoke_flag_is_hidden(capsys):
    with pytest.raises(SystemExit):
        app.main(["--help"])
    out = capsys.readouterr().out
    assert "--smoke" not in out and "doctor" in out
