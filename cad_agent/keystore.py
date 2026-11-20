"""API key 的存取（设计文档第 4.4 节）：先环境变量，后系统钥匙串（服务名 datum，用户名是预设 id）。

规矩：key 不打印、不写日志、不写文件；异常信息里不带 key，也不转述底层异常的原文（里面可能有 key）。
钥匙串不可用时不退回到明文文件，而是告诉用户可以改用环境变量。
"""

from __future__ import annotations

import os
from typing import Literal

import keyring
import keyring.errors

from cad_agent import brand

SERVICE = brand.KEYRING_SERVICE
HINT_MIN_LEN = 8  # key 不到这么长时，提示里一位都不显示


class KeyStoreError(Exception):
    """钥匙串读写失败或 key 不合法；信息是中文，不含 key。"""


def _env_value(env_name: str) -> str | None:
    value = os.environ.get(env_name, "").strip() if env_name else ""
    return value or None


def _keyring_value(provider_id: str) -> str | None:
    """钥匙串里的 key；没有、或者钥匙串用不了，都当作没有（读的时候不报错，存的时候才说明）。"""
    try:
        value = keyring.get_password(SERVICE, provider_id)
    except keyring.errors.KeyringError:   # 包括"没有可用的后端"；原因在保存 key 时再告诉用户
        return None
    value = (value or "").strip()
    return value or None


def get_key(provider_id: str, env_name: str) -> str | None:
    """先环境变量（空白不算），后钥匙串；都没有返回 None。"""
    return _env_value(env_name) or _keyring_value(provider_id)


def key_source(provider_id: str, env_name: str) -> Literal["env", "keyring", None]:
    if _env_value(env_name) is not None:
        return "env"
    if _keyring_value(provider_id) is not None:
        return "keyring"
    return None


def key_hint(provider_id: str, env_name: str) -> str | None:
    """给界面看的提示："…" 加最后 4 位；key 不到 8 位时只返回 "…"；没有 key 时是 None。"""
    key = get_key(provider_id, env_name)
    if key is None:
        return None
    return "…" + key[-4:] if len(key) >= HINT_MIN_LEN else "…"


def _env_name_for(provider_id: str) -> str | None:
    from cad_agent.config import ConfigError
    from cad_agent.llm.providers import get_provider

    try:
        return get_provider(provider_id).api_key_env
    except ConfigError:
        return None


def _unavailable(provider_id: str, what: str) -> KeyStoreError:
    env = _env_name_for(provider_id)
    how = f"设置环境变量 {env}" if env else "把 key 放进环境变量（变量名见设置页）"
    return KeyStoreError(f"{what}：这台电脑上没有可用的系统钥匙串。可以改用环境变量：{how}，然后重新打开 {brand.PRODUCT}。")


def set_key(provider_id: str, key: str) -> None:
    """只写钥匙串（环境变量不动；两边都有时仍以环境变量为准）。"""
    value = key.strip() if isinstance(key, str) else ""
    if not value:
        raise KeyStoreError("key 不能是空的")
    try:
        keyring.set_password(SERVICE, provider_id, value)
    except keyring.errors.NoKeyringError:
        raise _unavailable(provider_id, "没能保存 key") from None
    except Exception:  # noqa: BLE001 - 后端的原始异常可能带着 key，不转述
        raise KeyStoreError("没能把 key 存进系统钥匙串。可以改用环境变量，或者稍后再试。") from None


def delete_key(provider_id: str) -> None:
    """从钥匙串删除；本来就没有、或者没有可用的钥匙串，都不报错。"""
    try:
        keyring.delete_password(SERVICE, provider_id)
    except (keyring.errors.PasswordDeleteError, keyring.errors.NoKeyringError):
        return
    except Exception:  # noqa: BLE001 - 后端的原始异常可能带着 key，不转述
        raise KeyStoreError("没能从系统钥匙串里删除 key，可以稍后再试。") from None
