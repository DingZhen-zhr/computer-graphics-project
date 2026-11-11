"""钥匙串：全部用内存里的假后端，不碰真实的系统钥匙串。key 都是明显的假值。"""

from __future__ import annotations

import keyring
import keyring.backend
import keyring.errors
import pytest

from cad_agent import keystore
from cad_agent.keystore import SERVICE, KeyStoreError

ENV = "CALIPER_TEST_KEY"


class MemoryKeyring(keyring.backend.KeyringBackend):
    priority = 1  # type: ignore[assignment]

    def __init__(self) -> None:
        super().__init__()
        self.store: dict[tuple[str, str], str] = {}

    def get_password(self, service, username):
        return self.store.get((service, username))

    def set_password(self, service, username, password):
        self.store[(service, username)] = password

    def delete_password(self, service, username):
        if (service, username) not in self.store:
            raise keyring.errors.PasswordDeleteError("没有这一项")
        del self.store[(service, username)]


class NoBackend(keyring.backend.KeyringBackend):
    """模拟精简版系统：没有可用的钥匙串后端。"""

    priority = 0  # type: ignore[assignment]

    def get_password(self, service, username):
        raise keyring.errors.NoKeyringError("No recommended backend was available.")

    def set_password(self, service, username, password):
        raise keyring.errors.NoKeyringError("No recommended backend was available.")

    def delete_password(self, service, username):
        raise keyring.errors.NoKeyringError("No recommended backend was available.")


@pytest.fixture
def memory(monkeypatch):
    previous = keyring.get_keyring()
    backend = MemoryKeyring()
    keyring.set_keyring(backend)
    monkeypatch.delenv(ENV, raising=False)
    yield backend
    keyring.set_keyring(previous)


@pytest.fixture
def no_backend(monkeypatch):
    previous = keyring.get_keyring()
    keyring.set_keyring(NoBackend())
    monkeypatch.delenv(ENV, raising=False)
    yield
    keyring.set_keyring(previous)


def test_set_get_delete_round_trip(memory):
    assert keystore.get_key("deepseek", ENV) is None and keystore.key_source("deepseek", ENV) is None
    keystore.set_key("deepseek", "test-key-0000")
    assert memory.store == {(SERVICE, "deepseek"): "test-key-0000"}
    assert keystore.get_key("deepseek", ENV) == "test-key-0000"
    assert keystore.key_source("deepseek", ENV) == "keyring"
    keystore.delete_key("deepseek")
    assert keystore.get_key("deepseek", ENV) is None and memory.store == {}
    keystore.delete_key("deepseek")   # 钥匙串里没有也不报错


def test_set_key_strips_spaces(memory):
    keystore.set_key("glm", "  test-key-1111\n")
    assert memory.store[(SERVICE, "glm")] == "test-key-1111"


def test_env_wins_over_keyring(memory, monkeypatch):
    keystore.set_key("deepseek", "test-key-from-keyring")
    monkeypatch.setenv(ENV, "test-key-from-env")
    assert keystore.get_key("deepseek", ENV) == "test-key-from-env"
    assert keystore.key_source("deepseek", ENV) == "env"
    assert keystore.key_hint("deepseek", ENV) == "…-env"
    keystore.set_key("deepseek", "test-key-new-value")
    assert memory.store[(SERVICE, "deepseek")] == "test-key-new-value"
    import os
    assert os.environ[ENV] == "test-key-from-env"
    assert keystore.get_key("deepseek", ENV) == "test-key-from-env"


def test_blank_env_falls_back_to_keyring(memory, monkeypatch):
    keystore.set_key("kimi", "test-key-2222")
    monkeypatch.setenv(ENV, "   ")
    assert keystore.get_key("kimi", ENV) == "test-key-2222" and keystore.key_source("kimi", ENV) == "keyring"


def test_key_hint_shows_only_last_four(memory):
    keystore.set_key("deepseek", "sk-abcdefgh1234")
    hint = keystore.key_hint("deepseek", ENV)
    assert hint == "…1234"
    assert "abcdefgh" not in hint and "sk-" not in hint
    keystore.set_key("deepseek", "abc1234")   # 7 位
    assert keystore.key_hint("deepseek", ENV) == "…"
    keystore.delete_key("deepseek")
    assert keystore.key_hint("deepseek", ENV) is None


def test_blank_key_is_rejected(memory):
    for bad in ("", "   ", "\n\t "):
        with pytest.raises(KeyStoreError):
            keystore.set_key("deepseek", bad)
    assert memory.store == {}


def test_no_keyring_backend(no_backend):
    with pytest.raises(KeyStoreError) as e:
        keystore.set_key("deepseek", "test-key-0000")
    text = str(e.value)
    assert "环境变量" in text and "DEEPSEEK_API_KEY" in text   # 预设里 key 的变量名
    assert keystore.get_key("deepseek", ENV) is None
    assert keystore.key_source("deepseek", ENV) is None and keystore.key_hint("deepseek", ENV) is None
    keystore.delete_key("deepseek")   # 没有后端时删除也不崩


def test_no_keyring_backend_message_for_unknown_provider(no_backend):
    with pytest.raises(KeyStoreError) as e:
        keystore.set_key("not-a-preset", "test-key-0000")
    assert "环境变量" in str(e.value)


class Exploding(keyring.backend.KeyringBackend):
    """各种失败：异常信息里故意带上 key，检查我们的报错不会把它转述出去。"""

    priority = 0  # type: ignore[assignment]

    def get_password(self, service, username):
        raise keyring.errors.KeyringError("读取失败 test-key-SECRET-9999")

    def set_password(self, service, username, password):
        raise keyring.errors.PasswordSetError(f"写入失败 {password}")

    def delete_password(self, service, username):
        raise keyring.errors.KeyringError("删除失败 test-key-SECRET-9999")


def test_key_never_in_exception_text(monkeypatch):
    previous = keyring.get_keyring()
    keyring.set_keyring(Exploding())
    monkeypatch.delenv(ENV, raising=False)
    try:
        with pytest.raises(KeyStoreError) as e:
            keystore.set_key("deepseek", "test-key-SECRET-9999")
        assert "SECRET" not in str(e.value) and e.value.__cause__ is None and e.value.__suppress_context__
        with pytest.raises(KeyStoreError) as e2:
            keystore.delete_key("deepseek")
        assert "SECRET" not in str(e2.value) and e2.value.__suppress_context__
        assert keystore.get_key("deepseek", ENV) is None   # 读不到当作没有，不抛
        with pytest.raises(KeyStoreError) as e3:
            keystore.set_key("deepseek", "   ")
        assert "SECRET" not in str(e3.value)
    finally:
        keyring.set_keyring(previous)
