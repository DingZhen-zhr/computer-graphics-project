"""读取配置。API key 只从环境变量读，不写进配置，也不出现在 repr 里。"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from cad_agent.gates import Gates
from cad_agent.llm.client import Pricing


class ConfigError(Exception):
    """配置有问题；信息是中文，可以直接显示给用户。"""


Phase = Literal["base", "clarify", "modeling", "review"]
Kind = Literal["openai", "anthropic"]
KINDS = ("openai", "anthropic")


@dataclass(frozen=True)
class PhaseOverride:
    """[llm.clarify] / [llm.modeling] / [llm.review] 里写了的项；没写的是 None，沿用 [llm]。

    base_url、kind、api_key_env 只有 [llm.review] 能写：让看图审查走另一家服务。
    """

    model: str | None = None
    temperature: float | None = None
    extra_body: dict | None = None
    pricing: Pricing | None = None
    base_url: str | None = None
    kind: Kind | None = None
    api_key_env: str | None = None


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
    gates: Gates = field(default_factory=Gates)
    max_tool_calls_per_stage: int = 25   # 分阶段时每个阶段的工具调用上限
    max_tool_calls_total: int = 200      # 分阶段时每轮的工具调用总上限（max_tool_calls 只在关掉分阶段时用）
    cases_dir: Path = field(default_factory=lambda: Path("cases"))
    kind: Kind = "openai"                # 接口类型：OpenAI 兼容，或 Claude 官方接口
    provider: str = ""                   # 预设 id（来自 settings.toml 时才有）
    vision: bool = False                 # 看图审查用的模型能不能识图
    review: PhaseOverride = field(default_factory=PhaseOverride)

    def api_key(self) -> str:
        key = os.environ.get(self.api_key_env, "").strip()
        if not key:
            raise ConfigError(f"请先设置环境变量 {self.api_key_env}")
        return key

    def llm_settings(self, phase: Phase) -> LLMSettings:
        """某个阶段实际用的模型设置：覆盖段写了的项用覆盖值（extra_body 整体替换，不合并），没写的沿用 [llm]。"""
        override = {"base": PhaseOverride(), "clarify": self.clarify, "modeling": self.modeling, "review": self.review}[phase]
        return LLMSettings(
            model=self.model if override.model is None else override.model,
            temperature=self.temperature if override.temperature is None else override.temperature,
            extra_body=dict(self.extra_body if override.extra_body is None else override.extra_body),
            pricing=self.pricing if override.pricing is None else override.pricing,
        )


    def endpoint(self, phase: Phase) -> tuple[Kind, str, str]:
        """某个阶段连哪里：（接口类型, 地址, key 的环境变量名）。只有 review 能换服务，其余阶段都和 [llm] 相同。"""
        o = self.review if phase == "review" else PhaseOverride()
        return (o.kind or self.kind, o.base_url or self.base_url, o.api_key_env or self.api_key_env)


# 段名 → {键: 类型}
_SCHEMA: dict[str, dict[str, type | tuple[type, ...]]] = {
    "llm": {"base_url": str, "model": str, "api_key_env": str, "temperature": (int, float),
            "extra_body": dict, "pricing": dict, "clarify": dict, "modeling": dict,
            "kind": str, "vision": bool, "review": dict},
    "agent": {"run_timeout_s": (int, float), "max_build_failures": int, "max_tool_calls": int, "sessions_dir": str,
              "staged": bool, "mutation_check": bool, "visual_review": bool, "cases": bool,
              "max_tool_calls_per_stage": int, "max_tool_calls_total": int, "cases_dir": str},
}
_GATE_KEYS = ("staged", "mutation_check", "visual_review", "cases")
_POSITIVE_KEYS = ("max_tool_calls_per_stage", "max_tool_calls_total")
_OVERRIDE_KEYS: dict[str, type | tuple[type, ...]] = {"model": str, "temperature": (int, float), "extra_body": dict, "pricing": dict}
_REVIEW_KEYS: dict[str, type | tuple[type, ...]] = {**_OVERRIDE_KEYS, "base_url": str, "kind": str, "api_key_env": str}
_PRICING_KEYS = ("input_hit", "input_miss", "output")


def _check_type(section: str, key: str, value: object, typ: type | tuple[type, ...]) -> None:
    if typ is bool:
        if not isinstance(value, bool):
            raise ConfigError(f"[{section}] 的 {key} 应该是 true 或 false，收到 {value!r}")
        return
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


def _check_kind(section: str, value: str) -> None:
    if value not in KINDS:
        raise ConfigError(f"[{section}] 的 kind 只能是 {' 或 '.join(KINDS)}，收到 {value!r}")


def _parse_override(section: str, data: dict) -> PhaseOverride:
    allowed = _REVIEW_KEYS if section == "llm.review" else _OVERRIDE_KEYS
    unknown = sorted(set(data) - set(allowed))
    if unknown:
        raise ConfigError(f"[{section}] 里有不认识的项 {'、'.join(unknown)}；可用项：{'、'.join(allowed)}")
    for key, typ in allowed.items():
        if key in data:
            _check_type(section, key, data[key], typ)
    if "kind" in data:
        _check_kind(section, data["kind"])
    return PhaseOverride(
        model=data.get("model"), temperature=data.get("temperature"), extra_body=data.get("extra_body"),
        pricing=_parse_pricing(f"{section}.pricing", data["pricing"]) if "pricing" in data else None,
        base_url=data.get("base_url"), kind=data.get("kind"), api_key_env=data.get("api_key_env"),
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
    if "cases_dir" in values:
        values["cases_dir"] = Path(values["cases_dir"])
    for key in _POSITIVE_KEYS:
        if key in values and values[key] <= 0:
            raise ConfigError(f"[agent] 的 {key} 应该是正整数，收到 {values[key]!r}")
    values["gates"] = Gates(**{k: values.pop(k) for k in _GATE_KEYS if k in values})
    if "pricing" in values:
        values["pricing"] = _parse_pricing("llm.pricing", values["pricing"])
    if "kind" in values:
        _check_kind("llm", values["kind"])
    for phase in ("clarify", "modeling", "review"):
        if phase in values:
            values[phase] = _parse_override(f"llm.{phase}", values[phase])
    return Config(**values)
