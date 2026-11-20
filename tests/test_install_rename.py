"""安装脚本改用 Datum 并处理旧版卡尺（3.0 计划 1 Task 5）。脚本只在演示模式下运行；假的 uv 一被调用就留下记号。"""

from __future__ import annotations

import os
import re
import subprocess

import keyring
import pytest

from cad_agent import maintenance
from cad_agent.maintenance import REPO, run_uninstall, shortcut_paths
from test_install_scripts import (OLD_VERSION_HINT, PS1, PS_ENCODING, POWERSHELL, SH, SH_EXE, _code, _env, _fake, _fake_bin,
                                  _fake_uname, _steps_in_order, _text, needs_sh, windows_only)
from test_keystore import MemoryKeyring
from test_maintenance import Recorder

FAKE = "fake-rename-key-0000-ZXCV"


def test_default_source_is_v3_tag():
    for p in (PS1, SH):
        text = _text(p)
        assert f"git+https://github.com/{REPO}@v3.0.0" in text, p.name
        assert f"datum-cad @ https://github.com/{REPO}/archive/refs/tags/v3.0.0.zip" in text, p.name
        assert "v2.0.0" not in text, p.name


def test_install_scripts_mention_old_caliper():
    for p in (PS1, SH):
        text = _text(p)
        assert OLD_VERSION_HINT in text, p.name
        assert "tool list" in _code(text), p.name                    # 用 uv tool list 查有没有旧版
        for line in _code(text).splitlines():                        # uv tool uninstall 只出现在那句提示里，不真的执行
            if "tool uninstall" in line:
                assert OLD_VERSION_HINT in line, (p.name, line)


@windows_only
def test_old_shortcuts_are_removed_in_dry_run_ps1(tmp_path):
    bin_dir, marker = _fake_bin(tmp_path)
    env = _env(tmp_path, DATUM_DRY_RUN="1", PATH=f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    command = f"Get-Content -Raw -Encoding UTF8 -LiteralPath '{PS1}' | Invoke-Expression; exit $LASTEXITCODE"
    r = subprocess.run([POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
                       capture_output=True, text=True, encoding=PS_ENCODING, errors="replace", env=env, timeout=120)
    out = r.stdout + r.stderr
    assert r.returncode == 0, out
    _steps_in_order(out)
    assert "Caliper.lnk" in out and "uv tool list" in out          # 只打印：删旧快捷方式、查旧版
    assert "datum.exe doctor" in out and "caliper.exe" not in out
    assert not marker.exists()


@needs_sh
def test_old_shortcuts_are_removed_in_dry_run_sh(tmp_path):
    bin_dir, marker = _fake_bin(tmp_path)
    _fake_uname(bin_dir, "arm64", "Darwin")
    _fake(bin_dir, "sw_vers", "14.5")
    old_app = tmp_path / "home" / "Applications" / "Caliper.app"
    old_app.mkdir(parents=True)
    env = _env(tmp_path, DATUM_DRY_RUN="1", PATH=f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    r = subprocess.run([SH_EXE, str(SH)], capture_output=True, text=True, encoding="utf-8", errors="replace", env=env, timeout=120)
    out = r.stdout + r.stderr
    assert r.returncode == 0, out
    _steps_in_order(out)
    assert "Applications/Caliper.app" in out and "uv tool list" in out
    assert "Applications/Datum.app" in out and "datum-app" in out and "datum doctor" in out
    assert old_app.exists() and not marker.exists()                  # 演示模式什么都不删


@pytest.fixture
def box(monkeypatch, tmp_path):
    home = tmp_path / "home"
    data = home / "AppData" / "Local" / "Datum"
    data.mkdir(parents=True)
    monkeypatch.setenv("DATUM_HOME", str(data))
    monkeypatch.setattr(maintenance, "_home", lambda: home)
    monkeypatch.setattr(maintenance, "_programs_dir", lambda: home / "Start Menu" / "Programs")
    monkeypatch.setattr(maintenance, "_desktop_dir", lambda: home / "Desktop")
    monkeypatch.setattr(maintenance, "_system", lambda: "win32")
    monkeypatch.setattr(maintenance, "_interactive", lambda: False)
    monkeypatch.setattr(maintenance, "_uv", lambda: "uv")
    previous = keyring.get_keyring()
    backend = MemoryKeyring()
    keyring.set_keyring(backend)
    backend.set_password("datum", "deepseek", FAKE)
    backend.set_password("caliper", "deepseek", FAKE)
    yield {"home": home, "keyring": backend}
    keyring.set_keyring(previous)


def test_uninstall_uses_new_names(box):
    assert [p.name for p in shortcut_paths()] == ["Datum 基准.lnk", "Datum 基准.lnk"]
    run = Recorder()
    said: list[str] = []
    assert run_uninstall(delete_data=False, say=said.append, run=run) == 0
    assert "tool uninstall datum-cad" in " ".join(run.calls[0])
    assert box["keyring"].store == {("caliper", "deepseek"): FAKE}   # 只删新服务名；旧版的不动
    text = "\n".join(said)
    assert "服务名 datum" in text and not re.search(r"caliper|卡尺", text, re.IGNORECASE)
