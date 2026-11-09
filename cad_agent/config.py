"""读取配置。API key 只从环境变量读，不写进配置，也不出现在 repr 里。"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from cad_agent.llm.client import Pricing


class ConfigError(Exception):
    """配置有问题；信息是中文，可以直接显示给用户。"""


Phase = Literal["base", "clarify", "modeling"]


@dataclass(frozen=True)
class PhaseOverride:
    """[llm.clarify] / [llm.modeling] 里写了的项；没写的是 None，沿用 [llm]。"""

    model: str | None = None
    temperature: float | None = None
    extra_body: dict | None = None
    pricing: Pricing | None = None


@dataclass(frozen=True)
class LLMSettings:
    model: str
    temperature: float
    extra_body: dict
    pricing: Pricing | None


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
    extra_body: dict = field(default_factory=dict)
    pricing: Pricing | None = None
    clarify: PhaseOverride = field(default_factory=PhaseOverride)
    modeling: PhaseOverride = field(default_factory=PhaseOverride)

    def api_key(self) -> str:
        key = os.environ.get(self.api_key_env, "").strip()
        if not key:
            raise ConfigError(f"请先设置环境变量 {self.api_key_env}")
        return key

    def llm_settings(self, phase: Phase) -> LLMSettings:
        """某个阶段实际用的模型设置：覆盖段写了的项用覆盖值（extra_body 整体替换，不合并），没写的沿用 [llm]。"""
        override = {"base": PhaseOverride(), "clarify": self.clarify, "modeling": self.modeling}[phase]
        return LLMSettings(
            model=self.model if override.model is None else override.model,
            temperature=self.temperature if override.temperature is None else override.temperature,
            extra_body=dict(self.extra_body if override.extra_body is None else override.extra_body),
            pricing=self.pricing if override.pricing is None else override.pricing,
        )


# 段名 → {键: 类型}
_SCHEMA: dict[str, dict[str, type | tuple[type, ...]]] = {
    "llm": {"base_url": str, "model": str, "api_key_env": str, "temperature": (int, float),
            "extra_body": dict, "pricing": dict, "clarify": dict, "modeling": dict},
    "agent": {"run_timeout_s": (int, float), "max_build_failures": int, "max_tool_calls": int, "sessions_dir": str},
}
_OVERRIDE_KEYS: dict[str, type | tuple[type, ...]] = {"model": str, "temperature": (int, float), "extra_body": dict, "pricing": dict}
_PRICING_KEYS = ("input_hit", "input_miss", "output")


def _check_type(section: str, key: str, value: object, typ: type | tuple[type, ...]) -> None:
    if isinstance(value, bool) or not isinstance(value, typ):
        raise ConfigError(f"[{section}] 的 {key} 类型不对，收到 {value!r}")


def _parse_pricing(section: str, data: dict) -> Pricing:
    unknown = sorted(set(data) - set(_PRICING_KEYS))
    if unknown:
        raise ConfigError(f"[{section}] 里有不认识的项 {'、'.join(unknown)}；只能写 {'、'.join(_PRICING_KEYS)}")
    missing = [k for k in _PRICING_KEYS if k not in data]
    if missing:
        raise ConfigError(f"[{section}] 缺少 {'、'.join(missing)}；三项都要写：{'、'.join(_PRICING_KEYS)}（单位：元 / 百万 token）")
    for key in _PRICING_KEYS:
        _check_type(section, key, data[key], (int, float))
        if data[key] < 0:
            raise ConfigError(f"[{section}] 的 {key} 不能小于 0，收到 {data[key]!r}")
    return Pricing(*(float(data[k]) for k in _PRICING_KEYS))


def _parse_override(section: str, data: dict) -> PhaseOverride:
    unknown = sorted(set(data) - set(_OVERRIDE_KEYS))
    if unknown:
        raise ConfigError(f"[{section}] 里有不认识的项 {'、'.join(unknown)}；可用项：{'、'.join(_OVERRIDE_KEYS)}")
    for key, typ in _OVERRIDE_KEYS.items():
        if key in data:
            _check_type(section, key, data[key], typ)
    return PhaseOverride(
        model=data.get("model"), temperature=data.get("temperature"), extra_body=data.get("extra_body"),
        pricing=_parse_pricing(f"{section}.pricing", data["pricing"]) if "pricing" in data else None,
    )


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
                _check_type(section, key, data[key], typ)
                values[key] = data[key]
    for required in ("base_url", "model"):
        if required not in values:
            raise ConfigError(f"配置文件 {path} 的 [llm] 里缺少 {required}")
    if "sessions_dir" in values:
        values["sessions_dir"] = Path(values["sessions_dir"])
    if "pricing" in values:
        values["pricing"] = _parse_pricing("llm.pricing", values["pricing"])
    for phase in ("clarify", "modeling"):
        if phase in values:
            values[phase] = _parse_override(f"llm.{phase}", values[phase])
    return Config(**values)
