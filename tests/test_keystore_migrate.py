"""从卡尺升级时带上钥匙串里的 key（3.0 计划 1 Task 3）。全部用内存里的假后端，key 都是明显的假值。"""

from __future__ import annotations

import json
import logging

import keyring
import keyring.errors
import pytest

from cad_agent import keystore, paths
from cad_agent.keystore import delete_key, get_key, key_hint, key_source, set_key
from test_keystore import MemoryKeyring

ENV = "CALIPER_TEST_KEY"
OLD = "caliper"
NEW = "datum"
OLD_KEY = "fake-old-service-key-0000-OLDK"
NEW_KEY = "fake-new-service-key-0000-NEWK"
ENV_KEY = "fake-env-key-0000-ENVK"


class WriteFails(MemoryKeyring):
    """读得出来、写不进去；报错信息里故意带着 key，看程序会不会转述出去。"""

    def set_password(self, service, username, password):
        raise keyring.errors.PasswordSetError(f"写入失败：{password}")


@pytest.fixture(autouse=True)
def home(monkeypatch, tmp_path):
    """记"已经回退过"的小文件放在临时的数据目录里，碰不到真实的数据目录。"""
    monkeypatch.setenv("DATUM_HOME", str(tmp_path / "home"))
    return tmp_path / "home"


def _marker(home) -> dict:
    return json.loads((home / "key_migration.json").read_text(encoding="utf-8"))


@pytest.fixture
def memory(monkeypatch):
    previous = keyring.get_keyring()
    backend = MemoryKeyring()
    keyring.set_keyring(backend)
    monkeypatch.delenv(ENV, raising=False)
    yield backend
    keyring.set_keyring(previous)


def test_key_falls_back_to_old_service_and_copies(memory):
    memory.store[(OLD, "deepseek")] = OLD_KEY
    assert get_key("deepseek", ENV) == OLD_KEY
    assert memory.store[(NEW, "deepseek")] == OLD_KEY      # 复制了一份到新服务名
    assert memory.store[(OLD, "deepseek")] == OLD_KEY      # 旧的不删
    assert key_source("deepseek", ENV) == "keyring"
    assert key_hint("deepseek", ENV) == "…" + OLD_KEY[-4:]
    assert get_key("glm", ENV) is None and (NEW, "glm") not in memory.store


def test_key_source_of_old_service_is_keyring(memory):
    memory.store[(OLD, "kimi")] = OLD_KEY
    assert key_source("kimi", ENV) == "keyring"


def test_new_service_wins(memory):
    memory.store[(OLD, "deepseek")] = OLD_KEY
    memory.store[(NEW, "deepseek")] = NEW_KEY
    assert get_key("deepseek", ENV) == NEW_KEY
    assert memory.store == {(OLD, "deepseek"): OLD_KEY, (NEW, "deepseek"): NEW_KEY}


def test_env_still_wins(memory, monkeypatch):
    memory.store[(OLD, "deepseek")] = OLD_KEY
    monkeypatch.setenv(ENV, ENV_KEY)
    assert get_key("deepseek", ENV) == ENV_KEY
    assert key_source("deepseek", ENV) == "env"
    assert (NEW, "deepseek") not in memory.store            # 用不到钥匙串时不去复制


def test_copy_failure_does_not_break_get(monkeypatch, caplog):
    previous = keyring.get_keyring()
    backend = WriteFails()
    keyring.set_keyring(backend)
    monkeypatch.delenv(ENV, raising=False)
    try:
        backend.store[(OLD, "deepseek")] = OLD_KEY
        with caplog.at_level(logging.DEBUG):
            assert get_key("deepseek", ENV) == OLD_KEY
            assert get_key("deepseek", ENV) == OLD_KEY        # 下次还是从旧的取
        assert backend.store == {(OLD, "deepseek"): OLD_KEY}
        assert key_source("deepseek", ENV) == "keyring"
    finally:
        keyring.set_keyring(previous)
    assert OLD_KEY not in caplog.text and OLD_KEY[-4:] not in caplog.text


def test_delete_only_touches_new_service(memory):
    memory.store[(OLD, "deepseek")] = OLD_KEY
    memory.store[(NEW, "deepseek")] = NEW_KEY
    delete_key("deepseek")
    assert memory.store == {(OLD, "deepseek"): OLD_KEY}
    set_key("glm", NEW_KEY)
    assert memory.store[(NEW, "glm")] == NEW_KEY and (OLD, "glm") not in memory.store


def test_errors_never_contain_key(monkeypatch, caplog, capsys):
    previous = keyring.get_keyring()
    backend = WriteFails()
    keyring.set_keyring(backend)
    monkeypatch.delenv(ENV, raising=False)
    try:
        backend.store[(OLD, "deepseek")] = OLD_KEY
        with caplog.at_level(logging.DEBUG):
            get_key("deepseek", ENV)
            key_source("deepseek", ENV)
            with pytest.raises(keystore.KeyStoreError) as e:
                set_key("deepseek", NEW_KEY)
    finally:
        keyring.set_keyring(previous)
    out = capsys.readouterr()
    for text in (str(e.value), caplog.text, out.out, out.err):
        for secret in (OLD_KEY, NEW_KEY):
            assert secret not in text and secret[-4:] not in text


# ---- 每个服务只从旧服务名回退一次（规划会话的计划修订，偏离 D24） ----


def test_deleted_key_does_not_come_back(memory, home):
    memory.store[(OLD, "deepseek")] = OLD_KEY
    assert get_key("deepseek", ENV) == OLD_KEY and memory.store[(NEW, "deepseek")] == OLD_KEY
    delete_key("deepseek")
    assert get_key("deepseek", ENV) is None
    assert key_source("deepseek", ENV) is None and key_hint("deepseek", ENV) is None
    assert (NEW, "deepseek") not in memory.store
    assert memory.store[(OLD, "deepseek")] == OLD_KEY      # 旧服务名里的照旧不删


def test_delete_before_any_fallback_also_blocks_it(memory, home):
    """还没取过就先在设置页里删：删完也不能再从旧的复制回来。"""
    memory.store[(OLD, "deepseek")] = OLD_KEY
    delete_key("deepseek")
    assert get_key("deepseek", ENV) is None and memory.store == {(OLD, "deepseek"): OLD_KEY}
    assert _marker(home) == {"deepseek": True}


def test_fallback_only_once_per_provider(memory, home):
    memory.store[(OLD, "deepseek")] = OLD_KEY
    memory.store[(OLD, "glm")] = OLD_KEY
    assert get_key("deepseek", ENV) == OLD_KEY
    assert _marker(home) == {"deepseek": True}
    del memory.store[(NEW, "deepseek")]                     # 新服务名里的被别的办法删掉了
    assert get_key("deepseek", ENV) is None                 # 不再回退
    assert (NEW, "deepseek") not in memory.store
    assert get_key("glm", ENV) == OLD_KEY                   # 别的服务各算各的
    assert _marker(home) == {"deepseek": True, "glm": True}


def test_marker_file_corrupt_is_ignored(memory, home):
    home.mkdir(parents=True)
    (home / "key_migration.json").write_text("{坏掉的内容", encoding="utf-8")
    memory.store[(OLD, "deepseek")] = OLD_KEY
    assert get_key("deepseek", ENV) == OLD_KEY               # 当作没记过，照常回退
    assert memory.store[(NEW, "deepseek")] == OLD_KEY
    assert _marker(home) == {"deepseek": True}
    (home / "key_migration.json").write_text("[1, 2]", encoding="utf-8")   # 能解析但不是对象，也当作没记过
    del memory.store[(NEW, "deepseek")]
    assert get_key("deepseek", ENV) == OLD_KEY


def test_copy_failure_does_not_mark(monkeypatch, home):
    previous = keyring.get_keyring()
    backend = WriteFails()
    keyring.set_keyring(backend)
    monkeypatch.delenv(ENV, raising=False)
    try:
        backend.store[(OLD, "deepseek")] = OLD_KEY
        assert get_key("deepseek", ENV) == OLD_KEY
        assert not (home / "key_migration.json").exists()   # 没记，下次还会再试
        assert get_key("deepseek", ENV) == OLD_KEY
    finally:
        keyring.set_keyring(previous)


def test_marker_write_failure_only_logs(memory, monkeypatch, tmp_path, caplog):
    blocker = tmp_path / "not-a-dir"
    blocker.write_text("这是个文件，数据目录建不出来", encoding="utf-8")
    monkeypatch.setenv("DATUM_HOME", str(blocker / "home"))
    memory.store[(OLD, "deepseek")] = OLD_KEY
    with caplog.at_level(logging.WARNING):
        assert get_key("deepseek", ENV) == OLD_KEY
        delete_key("deepseek")
    assert "key_migration.json" in caplog.text
    assert OLD_KEY not in caplog.text and OLD_KEY[-4:] not in caplog.text


def test_no_marker_written_without_old_key(memory, home):
    """旧服务名里什么都没有时，取、删都不写这个文件（也就不会为此建出数据目录）。"""
    memory.store[(NEW, "deepseek")] = NEW_KEY
    assert get_key("deepseek", ENV) == NEW_KEY and get_key("glm", ENV) is None
    delete_key("deepseek")
    delete_key("glm")
    assert not home.exists()
    assert paths.app_home() == home
