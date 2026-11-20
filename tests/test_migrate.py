"""从卡尺升级时复制数据目录（3.0 计划 1 Task 2）。

全在临时目录里：sys.platform、LOCALAPPDATA、HOME、USERPROFILE 都换掉，真实的数据目录碰不到；钥匙串用内存里的假后端。
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import keyring
import pytest

from cad_agent import app, migrate, paths
from cad_agent.llm.providers import load_providers
from cad_agent.migrate import MigrationResult, migrate_home
from test_keystore import MemoryKeyring

SETTINGS = 'provider = "custom"\napi_key_env = "CALIPER_API_KEY"\nrun_timeout_s = 61\n'
FILES = {
    "settings.toml": SETTINGS,
    "sessions/x/log.jsonl": '{"kind": "user", "text": "做一个盒子"}\n',
    "cases/y/case.yaml": "title: 盒子\n",
}


@pytest.fixture
def fs(monkeypatch, tmp_path):
    """假的 Windows 用户目录：旧目录是 local/Caliper，新目录是 local/Datum。"""
    monkeypatch.delenv("DATUM_HOME", raising=False)
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    monkeypatch.setenv("HOME", str(tmp_path / "user"))
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "user"))
    (tmp_path / "local").mkdir()
    return {"old": tmp_path / "local" / "Caliper", "new": tmp_path / "local" / "Datum", "tmp": tmp_path}


def _fill(root: Path, files: dict[str, str]) -> None:
    for rel, text in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_bytes(text.encode("utf-8"))


def _snapshot(root: Path) -> dict[str, bytes]:
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}


def test_copies_old_home_once(fs):
    _fill(fs["old"], FILES)
    before = _snapshot(fs["old"])
    result = migrate_home()
    assert result == MigrationResult(done=True, reason="复制了")
    assert _snapshot(fs["new"]) == before   # 内容一样，settings.toml 里的旧名字原样保留
    assert _snapshot(fs["old"]) == before   # 旧目录原样还在
    assert not (fs["tmp"] / "local" / "Datum.migrating").exists()
    again = migrate_home()
    assert again.done is False and again.reason == "新目录已存在"


def test_migration_skips_when_new_home_exists(fs):
    _fill(fs["old"], FILES)
    _fill(fs["new"], {"settings.toml": 'provider = "glm"\n'})
    result = migrate_home()
    assert result.done is False and result.reason == "新目录已存在"
    assert _snapshot(fs["new"]) == {"settings.toml": b'provider = "glm"\n'}   # 不复制、不覆盖
    assert _snapshot(fs["old"]) == {k: v.encode("utf-8") for k, v in FILES.items()}


def test_migration_skipped_when_datum_home_set(fs, monkeypatch):
    _fill(fs["old"], FILES)
    custom = fs["tmp"] / "custom"
    monkeypatch.setenv("DATUM_HOME", str(custom))
    result = migrate_home()
    assert result.done is False and result.reason == "设置了 DATUM_HOME"
    assert not custom.exists() and not fs["new"].exists()
    assert _snapshot(fs["old"]) == {k: v.encode("utf-8") for k, v in FILES.items()}


def test_no_old_home_is_fine(fs):
    result = migrate_home()
    assert result.done is False and result.reason == "没有旧目录"
    assert not fs["new"].exists()


def test_migration_failure_leaves_no_partial_home(fs, monkeypatch):
    _fill(fs["old"], FILES)
    real_copy = migrate._copy_file
    calls = {"n": 0}

    def flaky(src, dst):
        calls["n"] += 1
        if calls["n"] == 2:
            raise OSError("磁盘满了")
        return real_copy(src, dst)

    monkeypatch.setattr(migrate, "_copy_file", flaky)
    result = migrate_home()
    assert result.done is False and "复制失败" in result.reason and "磁盘满了" in result.reason
    assert not fs["new"].exists() and not (fs["tmp"] / "local" / "Datum.migrating").exists()
    assert _snapshot(fs["old"]) == {k: v.encode("utf-8") for k, v in FILES.items()}
    monkeypatch.setattr(migrate, "_copy_file", real_copy)   # 下次启动还能重试
    assert migrate_home().done is True and (fs["new"] / "settings.toml").read_text(encoding="utf-8") == SETTINGS


def test_leftover_temp_dir_from_a_crash_is_replaced(fs):
    """上次复制到一半程序被关掉，留下了临时目录：这次照常复制，不把残留的东西带进新目录。"""
    _fill(fs["old"], FILES)
    _fill(fs["tmp"] / "local" / "Datum.migrating", {"half.txt": "残留"})
    assert migrate_home().done is True
    assert _snapshot(fs["new"]) == _snapshot(fs["old"])
    assert not (fs["tmp"] / "local" / "Datum.migrating").exists()


@pytest.fixture
def quiet_app(monkeypatch):
    """app.main 要用的东西：内存钥匙串、没有任何 key 的环境变量、干净的程序日志（结束时关掉这次建的日志文件）。"""
    for p in load_providers():
        monkeypatch.delenv(p.api_key_env, raising=False)
    previous = keyring.get_keyring()
    keyring.set_keyring(MemoryKeyring())
    log = logging.getLogger("datum")
    monkeypatch.setattr(log, "handlers", [])
    yield log
    for handler in log.handlers:
        handler.close()
    keyring.set_keyring(previous)


def test_app_start_migrates_and_logs(fs, quiet_app, monkeypatch):
    _fill(fs["old"], FILES)
    monkeypatch.setattr(app, "open_browser", lambda url: None)
    monkeypatch.setattr(app, "wait_for_exit", lambda: None)
    assert app.main(["--browser"]) == 0
    assert (fs["new"] / "settings.toml").read_text(encoding="utf-8") == SETTINGS
    assert (fs["new"] / "sessions" / "x" / "log.jsonl").is_file() and (fs["new"] / "cases" / "y" / "case.yaml").is_file()
    for handler in quiet_app.handlers:
        handler.flush()
    log_text = (paths.logs_dir() / "datum.log").read_text(encoding="utf-8")
    assert paths.logs_dir() == fs["new"] / "logs" and "复制了" in log_text
    assert (fs["old"] / "settings.toml").read_text(encoding="utf-8") == SETTINGS


def test_app_start_survives_failed_migration(fs, quiet_app, monkeypatch):
    """复制失败不打断启动，只在日志里记一条。"""
    _fill(fs["old"], FILES)

    def broken(src, dst):
        raise OSError("文件被占用")

    monkeypatch.setattr(migrate, "_copy_file", broken)
    monkeypatch.setattr(app, "open_browser", lambda url: None)
    monkeypatch.setattr(app, "wait_for_exit", lambda: None)
    assert app.main(["--browser"]) == 0
    for handler in quiet_app.handlers:
        handler.flush()
    assert "复制失败" in (paths.logs_dir() / "datum.log").read_text(encoding="utf-8")


def test_doctor_first_does_not_block_migration(fs, quiet_app):
    """安装脚本装完先运行 datum doctor，自检会建出数据目录：迁移必须在它之前，不然老用户的数据永远带不过来。"""
    _fill(fs["old"], FILES)
    app.main(["doctor", "--offline"])
    assert (fs["new"] / "settings.toml").read_text(encoding="utf-8") == SETTINGS
    assert (fs["new"] / "sessions" / "x" / "log.jsonl").is_file()


def test_old_app_home_per_platform(fs, monkeypatch):
    tmp = fs["tmp"]
    assert paths.old_app_home() == tmp / "local" / "Caliper"
    monkeypatch.delenv("LOCALAPPDATA")
    assert paths.old_app_home() == tmp / "user" / "AppData" / "Local" / "Caliper"
    monkeypatch.setattr(sys, "platform", "darwin")
    assert paths.old_app_home() == tmp / "user" / "Library" / "Application Support" / "Caliper"
    monkeypatch.setattr(sys, "platform", "linux")
    assert paths.old_app_home() == tmp / "user" / ".caliper"
    monkeypatch.setenv("DATUM_HOME", str(tmp / "custom"))   # 新目录的环境变量不影响旧目录在哪
    assert paths.old_app_home() == tmp / "user" / ".caliper"
    assert paths.app_home() == tmp / "custom"
