"""读取配置。API key 只从环境变量读，不写进配置，也不出现在 repr 里。"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path


class ConfigError(Exception):
    """配置有问题；信息是中文，可以直接显示给用户。"""


@dataclass(frozen=True)
class Config:
    base_url: str
    model: str
    api_key_env: str = "DEEPSEEK_API_KEY"
    temperature: float = 0.2
    run_timeout_s: float = 60
    max_build_failures: int = 3
    max_tool_calls: int = 40
    sessions_dir: Path = field(default_factory=lambda: Path("sessions"))

    def api_key(self) -> str:
        key = os.environ.get(self.api_key_env, "").strip()
        if not key:
            raise ConfigError(f"请先设置环境变量 {self.api_key_env}")
        return key


# 段名 → {键: 类型}
_SCHEMA: dict[str, dict[str, type | tuple[type, ...]]] = {
    "llm": {"base_url": str, "model": str, "api_key_env": str, "temperature": (int, float)},
    "agent": {"run_timeout_s": (int, float), "max_build_failures": int, "max_tool_calls": int, "sessions_dir": str},
}


def load_config(path: Path) -> Config:
    path = Path(path)
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as e:
        raise ConfigError(f"找不到配置文件 {path}。请把 config.example.toml 复制成 {path.name} 再按需修改") from e
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"配置文件 {path} 格式不对：{e}") from e

    unknown_sections = sorted(set(raw) - set(_SCHEMA))
    if unknown_sections:
        raise ConfigError(f"配置文件里有不认识的段 {'、'.join(unknown_sections)}；只能有 [llm] 和 [agent]")
    values: dict = {}
    for section, keys in _SCHEMA.items():
        data = raw.get(section, {})
        unknown = sorted(set(data) - set(keys))
        if unknown:
            raise ConfigError(f"[{section}] 里有不认识的项 {'、'.join(unknown)}；可用项：{'、'.join(keys)}")
        for key, typ in keys.items():
            if key in data:
                v = data[key]
                if isinstance(v, bool) or not isinstance(v, typ):
                    raise ConfigError(f"[{section}] 的 {key} 类型不对，收到 {v!r}")
                values[key] = v
    for required in ("base_url", "model"):
        if required not in values:
            raise ConfigError(f"配置文件 {path} 的 [llm] 里缺少 {required}")
    if "sessions_dir" in values:
        values["sessions_dir"] = Path(values["sessions_dir"])
    return Config(**values)
