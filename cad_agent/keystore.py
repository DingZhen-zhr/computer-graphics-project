"""API key 的存取（设计文档第 4.4 节）：先环境变量，后系统钥匙串（服务名 datum，用户名是预设 id）。
新服务名里没有时，再找第二版的旧服务名，找到就复制一份过来（旧的不删）；每个服务只回退一次，记在数据目录的
key_migration.json 里。set_key、delete_key 只动新服务名里的 key。

规矩：key 不打印、不写日志、不写文件；异常信息里不带 key，也不转述底层异常的原文（里面可能有 key）。
钥匙串不可用时不退回到明文文件，而是告诉用户可以改用环境变量。
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Literal

import keyring
import keyring.errors

from cad_agent import brand, paths

SERVICE = brand.KEYRING_SERVICE
logger = logging.getLogger(f"{brand.COMMAND}.keystore")
MARKER_FILE = "key_migration.json"   # 数据目录里，记哪些服务已经从旧服务名回退过
HINT_MIN_LEN = 8  # key 不到这么长时，提示里一位都不显示


class KeyStoreError(Exception):
    """钥匙串读写失败或 key 不合法；信息是中文，不含 key。"""


def _env_value(env_name: str) -> str | None:
    value = os.environ.get(env_name, "").strip() if env_name else ""
    return value or None


def _read(service: str, provider_id: str) -> str | None:
    """某个服务名下的 key；没有、或者钥匙串用不了，都当作没有（读的时候不报错，存的时候才说明）。"""
    try:
        value = keyring.get_password(service, provider_id)
    except keyring.errors.KeyringError:   # 包括"没有可用的后端"；原因在保存 key 时再告诉用户
        return None
    value = (value or "").strip()
    return value or None


def _marker_path() -> Path:
    return paths.app_home() / MARKER_FILE


def _fallen_back() -> dict:
    """哪些服务已经从旧服务名回退过（{预设 id: true}）。文件没有、读不出来、内容不对，都当作谁都没回退过。"""
    try:
        data = json.loads(_marker_path().read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as e:
        logger.warning("%s 读不出来（%s），当作还没有回退过", MARKER_FILE, type(e).__name__)
        return {}
    return data if isinstance(data, dict) else {}


def _mark_fallen_back(provider_id: str) -> None:
    """记下这个服务已经回退过；写不了只在日志里记一条（不影响取 key）。"""
    marks = {k: True for k, v in _fallen_back().items() if v is True}
    marks[provider_id] = True
    path = _marker_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_name(path.name + ".tmp")
        temp.write_text(json.dumps(marks, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(path)
    except OSError as e:
        logger.warning("没能写 %s（%s）：「%s」的 key 删掉后可能又会从旧服务名复制回来", MARKER_FILE, type(e).__name__, provider_id)


def _copy_to_new_service(provider_id: str, value: str) -> bool:
    """把第二版存的 key 复制一份到新服务名，返回成没成。失败不影响这次取到的 key，下次还会再试；旧的不删。"""
    try:
        keyring.set_password(SERVICE, provider_id, value)
    except Exception as e:  # noqa: BLE001 - 后端的原始异常可能带着 key，只记异常类型
        logger.warning("没能把「%s」的 key 从旧服务名复制到新服务名（%s），下次还从旧的取", provider_id, type(e).__name__)
        return False
    return True


def _keyring_value(provider_id: str) -> str | None:
    """钥匙串里的 key：先新服务名；没有、而且这个服务还没回退过时，再找第二版的旧服务名，
    找到就复制一份到新的并记下"回退过"（3.0 设计第 11 节，偏离 D24）。"""
    value = _read(SERVICE, provider_id)
    if value is not None:
        return value
    if _fallen_back().get(provider_id) is True:
        return None
    value = _read(brand.OLD_KEYRING_SERVICE, provider_id)
    if value is not None and _copy_to_new_service(provider_id, value):
        _mark_fallen_back(provider_id)
    return value


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
    """从钥匙串删除（只删新服务名里的）；本来就没有、或者没有可用的钥匙串，都不报错。
    旧服务名里还有这个服务的 key 时，记下"回退过"，免得删掉以后下次又从旧的复制回来；旧的照旧不删。"""
    try:
        keyring.delete_password(SERVICE, provider_id)
    except (keyring.errors.PasswordDeleteError, keyring.errors.NoKeyringError):
        pass
    except Exception:  # noqa: BLE001 - 后端的原始异常可能带着 key，不转述
        raise KeyStoreError("没能从系统钥匙串里删除 key，可以稍后再试。") from None
    if _read(brand.OLD_KEYRING_SERVICE, provider_id) is not None and _fallen_back().get(provider_id) is not True:
        _mark_fallen_back(provider_id)
