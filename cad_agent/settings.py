"""用户设置：数据目录里的 settings.toml ↔ Settings ↔ Config。

settings.toml 里只有 key 以外的设置（key 在环境变量或系统钥匙串里，见 keystore.py）。
文件格式很简单：顶层几个键，加 [pricing]、[gates] 两个小节；只有文字、数字、布尔，所以自己写 TOML，不引入新依赖。
"""

from __future__ import annotations

import json
import math
import os
import tempfile
import tomllib
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Literal

from cad_agent import brand, paths
from cad_agent.config import Config, ConfigError, PhaseOverride, _parse_pricing
from cad_agent.gates import Gates
from cad_agent.llm.client import Pricing
from cad_agent.llm.providers import Provider, get_provider

VISION_CHOICES = ("auto", "on", "off")
THEMES = ("system", "light", "dark")
_TEXT_KEYS = ("provider", "model", "base_url", "review_provider", "review_model")
_GATE_KEYS = tuple(f.name for f in fields(Gates))
_PRICING_KEYS = ("input_hit", "input_miss", "output")


@dataclass
class Settings:
    provider: str = "deepseek"
    model: str = ""                 # 空的时候用预设的第一个模型
    base_url: str = ""              # 空的时候用预设的地址
    temperature: float = 0.2
    vision: Literal["auto", "on", "off"] = "auto"     # auto：看预设，unknown 当作不能
    review_provider: str = ""       # 空的时候和 provider 相同
    review_model: str = ""
    pricing: Pricing | None = None
    theme: Literal["system", "light", "dark"] = "system"
    gates: Gates = field(default_factory=Gates)
    run_timeout_s: float = 60


# ---------------------------------------------------------------- 读


def _number(key: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ConfigError(f"设置文件里 {key} 应该是数字，收到 {value!r}")
    return value


def _parse(raw: dict) -> Settings:
    known = {f.name for f in fields(Settings)}
    unknown = sorted(set(raw) - known)
    if unknown:
        raise ConfigError(f"设置文件里有不认识的项 {'、'.join(unknown)}；可用项：{'、'.join(sorted(known))}")
    values: dict = {}
    for key in _TEXT_KEYS:
        if key in raw:
            if not isinstance(raw[key], str):
                raise ConfigError(f"设置文件里 {key} 应该是文字，收到 {raw[key]!r}")
            values[key] = raw[key].strip()
    for key, choices in (("vision", VISION_CHOICES), ("theme", THEMES)):
        if key in raw:
            if raw[key] not in choices:
                raise ConfigError(f"设置文件里 {key} 只能是 {'、'.join(choices)}，收到 {raw[key]!r}")
            values[key] = raw[key]
    if "temperature" in raw:
        values["temperature"] = float(_number("temperature", raw["temperature"]))
    if "run_timeout_s" in raw:
        if _number("run_timeout_s", raw["run_timeout_s"]) <= 0:
            raise ConfigError(f"设置文件里 run_timeout_s 应该是正数，收到 {raw['run_timeout_s']!r}")
        values["run_timeout_s"] = raw["run_timeout_s"]
    if "pricing" in raw:
        if not isinstance(raw["pricing"], dict):
            raise ConfigError("设置文件里 pricing 应该是一个小节 [pricing]")
        values["pricing"] = _parse_pricing("pricing", raw["pricing"])
    if "gates" in raw:
        g = raw["gates"]
        if not isinstance(g, dict):
            raise ConfigError("设置文件里 gates 应该是一个小节 [gates]")
        bad = sorted(set(g) - set(_GATE_KEYS))
        if bad:
            raise ConfigError(f"设置文件的 [gates] 里有不认识的项 {'、'.join(bad)}；可用项：{'、'.join(_GATE_KEYS)}")
        for k, v in g.items():
            if not isinstance(v, bool):
                raise ConfigError(f"设置文件的 [gates] 里 {k} 应该是 true 或 false，收到 {v!r}")
        values["gates"] = Gates(**g)
    s = Settings(**values)
    get_provider(s.provider)   # 不存在就报错
    if s.review_provider:
        get_provider(s.review_provider)
    return s


def load_settings(path: Path | None = None) -> Settings:
    """读设置；文件不存在时返回默认值（不创建文件）。"""
    path = Path(path) if path is not None else paths.settings_path()
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return Settings()
    try:
        raw = tomllib.loads(text)
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"设置文件 {path} 格式不对：{e}") from e
    return _parse(raw)


# ---------------------------------------------------------------- 写


def _toml_value(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    return json.dumps(str(value), ensure_ascii=False)   # JSON 的转义写法也是合法的 TOML 基本字符串


def render_settings(s: Settings) -> str:
    lines = [f"# {brand.PRODUCT} 的设置。API key 不在这里：它在环境变量或系统钥匙串里。"]
    for f in fields(Settings):
        if f.name not in ("pricing", "gates"):
            lines.append(f"{f.name} = {_toml_value(getattr(s, f.name))}")
    if s.pricing is not None:
        lines += ["", "[pricing]  # 元 / 百万 token，照模型服务的价目页填"]
        lines += [f"{k} = {_toml_value(getattr(s.pricing, k))}" for k in _PRICING_KEYS]
    lines += ["", "[gates]"]
    lines += [f"{k} = {_toml_value(getattr(s.gates, k))}" for k in _GATE_KEYS]
    return "\n".join(lines) + "\n"


def save_settings(s: Settings, path: Path | None = None) -> None:
    """先写同目录下的临时文件再改名，写到一半断电也不会留下半个文件。"""
    path = Path(path) if path is not None else paths.settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".settings-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(render_settings(s))
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


# ---------------------------------------------------------------- 转成 Config


def _vision(choice: str, provider: Provider) -> bool:
    if choice == "on":
        return True
    if choice == "off":
        return False
    return provider.vision == "yes"   # auto：unknown、no 都当作不能


def to_config(s: Settings) -> Config:
    p = get_provider(s.provider)
    base_url = s.base_url or p.base_url
    model = s.model or (p.models[0] if p.models else "")
    if not base_url:
        raise ConfigError(f"「{p.name}」还没有填接口地址，请在设置里填上")
    if not model:
        raise ConfigError(f"「{p.name}」还没有填模型名，请在设置里填上")
    review = PhaseOverride(model=s.review_model or None)
    vision_provider = p
    if s.review_provider and s.review_provider != p.id:
        rp = get_provider(s.review_provider)
        vision_provider = rp
        review = PhaseOverride(model=s.review_model or (rp.models[0] if rp.models else None),
                               base_url=rp.base_url or None, kind=rp.kind, api_key_env=rp.api_key_env)
    return Config(
        base_url=base_url, model=model, api_key_env=p.api_key_env, temperature=s.temperature,
        run_timeout_s=s.run_timeout_s, sessions_dir=paths.sessions_dir(), pricing=s.pricing, gates=s.gates,
        cases_dir=paths.cases_dir(), kind=p.kind, provider=p.id, vision=_vision(s.vision, vision_provider), review=review,
    )
