"""模型服务的预设：读包里的 cad_agent/providers.toml。地址和模型名的出处见 docs/llm-api-notes.md 第 9 节。"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Literal

PROVIDERS_FILE = Path(__file__).resolve().parent.parent / "providers.toml"


@dataclass(frozen=True)
class Provider:
    id: str
    name: str
    kind: Literal["openai", "anthropic"]
    base_url: str
    models: tuple[str, ...]
    api_key_env: str
    vision: Literal["yes", "no", "unknown"]


@lru_cache(maxsize=1)
def _load() -> tuple[Provider, ...]:
    raw = tomllib.loads(PROVIDERS_FILE.read_text(encoding="utf-8"))
    return tuple(
        Provider(p["id"], p["name"], p["kind"], p["base_url"], tuple(p["models"]), p["api_key_env"], p["vision"])
        for p in raw["provider"]
    )


def load_providers() -> list[Provider]:
    return list(_load())


def get_provider(provider_id: str) -> Provider:
    """按 id 取预设；不存在抛 ConfigError（中文，列出可用的 id）。"""
    from cad_agent.config import ConfigError  # 放这里：config 导入 llm.client，避免循环导入

    for p in _load():
        if p.id == provider_id:
            return p
    ids = "、".join(p.id for p in _load())
    raise ConfigError(f"没有叫 {provider_id} 的模型服务预设；可用的有：{ids}")
