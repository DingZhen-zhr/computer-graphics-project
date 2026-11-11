"""cad_agent/providers.toml 的形状：7 个预设、字段齐全、不写价格。"""

import re
import tomllib
from pathlib import Path

import cad_agent

PROVIDERS_FILE = Path(cad_agent.__file__).resolve().parent / "providers.toml"
IDS = ["deepseek", "glm", "kimi", "qwen", "openai", "claude", "custom"]
FIELDS = {"id", "name", "kind", "base_url", "models", "api_key_env", "vision"}


def _load() -> list[dict]:
    return tomllib.loads(PROVIDERS_FILE.read_text(encoding="utf-8"))["provider"]


def test_providers_file_shape():
    providers = _load()
    assert [p["id"] for p in providers] == IDS
    for p in providers:
        assert set(p) == FIELDS, p["id"]
        assert isinstance(p["name"], str) and p["name"].strip()
        assert p["kind"] in ("openai", "anthropic")
        assert isinstance(p["base_url"], str)
        assert isinstance(p["models"], list) and all(isinstance(m, str) and m.strip() for m in p["models"])
        assert isinstance(p["api_key_env"], str) and re.fullmatch(r"[A-Z][A-Z0-9_]*", p["api_key_env"])
        assert p["vision"] in ("yes", "no", "unknown")
    by_id = {p["id"]: p for p in providers}
    assert by_id["deepseek"]["vision"] == "unknown"
    assert by_id["custom"]["base_url"] == ""
    assert by_id["claude"]["kind"] == "anthropic"
    assert all(by_id[i]["kind"] == "openai" for i in IDS if i != "claude")


def test_providers_file_has_no_prices():
    text = PROVIDERS_FILE.read_text(encoding="utf-8")
    keys = re.findall(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=", text, flags=re.MULTILINE)
    assert set(keys) <= FIELDS
    assert not re.search(r"price|pricing|cost|input_hit|input_miss|output\s*=|¥|\$|元", text, flags=re.IGNORECASE)
