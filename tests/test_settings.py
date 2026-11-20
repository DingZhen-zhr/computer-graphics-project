"""settings.toml ↔ Settings ↔ Config；旧的 config.toml 照常能用。"""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

from cad_agent.config import Config, ConfigError, PhaseOverride, load_config
from cad_agent.gates import Gates
from cad_agent.llm.client import Pricing
from cad_agent.llm.providers import get_provider, load_providers
from cad_agent.settings import Settings, load_settings, save_settings, to_config

EXAMPLE = Path(__file__).resolve().parent.parent / "config.example.toml"
TOP_KEYS = {"provider", "model", "base_url", "temperature", "vision", "review_provider", "review_model", "theme", "run_timeout_s"}


@pytest.fixture(autouse=True)
def home(monkeypatch, tmp_path):
    h = tmp_path / "数据目录"
    monkeypatch.setenv("DATUM_HOME", str(h))
    return h


def test_providers_load():
    ids = [p.id for p in load_providers()]
    assert ids == ["deepseek", "glm", "kimi", "qwen", "openai", "claude", "custom"]
    ds = get_provider("deepseek")
    assert ds.kind == "openai" and ds.models[0] == "deepseek-flash" and isinstance(ds.models, tuple)
    with pytest.raises(ConfigError, match="nope"):
        get_provider("nope")


def test_defaults_when_no_file(home):
    s = load_settings()
    assert s == Settings()
    assert (s.provider, s.model, s.base_url, s.temperature, s.vision, s.theme) == ("deepseek", "", "", 0.2, "auto", "system")
    assert s.pricing is None and s.gates == Gates() and s.run_timeout_s == 60
    assert not (home / "settings.toml").exists()


def test_round_trip(home):
    s = Settings(provider="glm", model="glm-5.3", base_url="https://example.invalid/v4/", temperature=0.5, vision="on",
                 review_provider="claude", review_model="claude-sonnet-5-5", pricing=Pricing(0.2, 2.0, 8.0), theme="dark",
                 gates=Gates(staged=True, mutation_check=False, visual_review=True, cases=False), run_timeout_s=90.5)
    save_settings(s)
    path = home / "settings.toml"
    assert path.exists() and "数据目录" in str(path)
    assert load_settings() == s
    assert load_settings(path) == s
    other = home / "子目录" / "另一个.toml"
    save_settings(Settings(), other)
    assert load_settings(other) == Settings()
    assert sorted(p.name for p in home.iterdir()) == ["settings.toml", "子目录"]


def test_save_leaves_no_temp_files(home):
    save_settings(Settings(theme="light"))
    save_settings(Settings(theme="dark"))
    assert sorted(p.name for p in home.iterdir()) == ["settings.toml"]
    assert load_settings().theme == "dark"


def test_text_with_quotes_round_trips(home):
    s = Settings(provider="custom", model='m"o\\del', base_url="https://例子.invalid/v1")
    save_settings(s)
    assert load_settings() == s


def test_unknown_keys_are_reported(home):
    home.mkdir(parents=True)
    (home / "settings.toml").write_text('provider = "deepseek"\ncolour = "red"\n', encoding="utf-8")
    with pytest.raises(ConfigError, match="colour"):
        load_settings()
    (home / "settings.toml").write_text('[gates]\nstaged = true\nfast = true\n', encoding="utf-8")
    with pytest.raises(ConfigError, match="fast"):
        load_settings()
    (home / "settings.toml").write_text('[other]\nx = 1\n', encoding="utf-8")
    with pytest.raises(ConfigError, match="other"):
        load_settings()


def test_bad_values_are_reported(home):
    home.mkdir(parents=True)
    for text, word in (('vision = "maybe"\n', "vision"), ('theme = "blue"\n', "theme"), ('temperature = "hot"\n', "temperature"),
                       ('provider = "nope"\n', "nope"), ('[pricing]\ninput_hit = 1\n', "pricing"), ("provider = \n", "格式")):
        (home / "settings.toml").write_text(text, encoding="utf-8")
        with pytest.raises(ConfigError, match=word):
            load_settings()


def test_to_config_uses_preset(home):
    c = to_config(Settings(provider="glm"))
    glm = get_provider("glm")
    assert (c.base_url, c.model, c.api_key_env, c.kind, c.provider) == (glm.base_url, glm.models[0], glm.api_key_env, "openai", "glm")
    assert c.sessions_dir == home / "sessions" and c.cases_dir == home / "cases"
    claude = to_config(Settings(provider="claude"))
    assert claude.kind == "anthropic" and claude.model == "claude-opus-5-5" and claude.api_key_env == "ANTHROPIC_API_KEY"
    assert claude.review == PhaseOverride()


def test_to_config_overrides(home):
    s = Settings(provider="deepseek", model="deepseek-v4-pro", base_url="http://localhost:9/v1", temperature=0.7,
                 pricing=Pricing(1.0, 2.0, 3.0), gates=Gates(cases=False), run_timeout_s=30)
    c = to_config(s)
    assert (c.model, c.base_url, c.temperature, c.pricing, c.gates, c.run_timeout_s) == (
        "deepseek-v4-pro", "http://localhost:9/v1", 0.7, Pricing(1.0, 2.0, 3.0), Gates(cases=False), 30)
    assert c.api_key_env == "DEEPSEEK_API_KEY"


def test_custom_provider_needs_address_and_model(home):
    with pytest.raises(ConfigError, match="地址"):
        to_config(Settings(provider="custom", model="m"))
    with pytest.raises(ConfigError, match="模型"):
        to_config(Settings(provider="custom", base_url="http://localhost:9/v1"))
    c = to_config(Settings(provider="custom", base_url="http://localhost:9/v1", model="m"))
    assert c.api_key_env == "DATUM_API_KEY" and c.vision is False


def test_vision_auto(home):
    assert to_config(Settings(provider="openai")).vision is True        # 预设 yes
    assert to_config(Settings(provider="deepseek")).vision is False     # unknown
    assert to_config(Settings(provider="openai", vision="off")).vision is False
    assert to_config(Settings(provider="deepseek", vision="on")).vision is True


def test_review_can_use_another_provider(home):
    c = to_config(Settings(provider="deepseek", review_provider="claude", review_model="claude-haiku-5-5"))
    assert c.kind == "openai" and c.vision is True   # 审查用的服务能看图
    assert c.review == PhaseOverride(model="claude-haiku-5-5", base_url="https://api.anthropic.com", kind="anthropic",
                                     api_key_env="ANTHROPIC_API_KEY")
    assert c.endpoint("review") == ("anthropic", "https://api.anthropic.com", "ANTHROPIC_API_KEY")
    assert c.endpoint("modeling") == ("openai", "https://api.deepseek.com", "DEEPSEEK_API_KEY")
    assert c.llm_settings("review").model == "claude-haiku-5-5"
    same = to_config(Settings(provider="deepseek", review_model="deepseek-v4-pro"))
    assert same.review == PhaseOverride(model="deepseek-v4-pro") and same.endpoint("review") == same.endpoint("base")
    default_model = to_config(Settings(provider="deepseek", review_provider="openai"))
    assert default_model.review.model == "gpt-6-astra"


def test_settings_file_has_no_key(home, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key-0000")
    save_settings(Settings(pricing=Pricing(0.2, 2.0, 8.0)))
    text = (home / "settings.toml").read_text(encoding="utf-8")
    raw = tomllib.loads(text)
    assert set(raw) == TOP_KEYS | {"pricing", "gates"}
    assert set(raw["pricing"]) == {"input_hit", "input_miss", "output"}
    assert set(raw["gates"]) == {"staged", "mutation_check", "visual_review", "cases"}
    assert "test-key-0000" not in text and "api_key" not in text
    save_settings(Settings())
    assert set(tomllib.loads((home / "settings.toml").read_text(encoding="utf-8"))) == TOP_KEYS | {"gates"}


def test_config_file_still_works():
    c = load_config(EXAMPLE)
    assert c.kind == "openai" and c.vision is False and c.provider == "" and c.review == PhaseOverride()
    assert c.endpoint("review") == ("openai", c.base_url, c.api_key_env)


def test_config_file_review_section(tmp_path):
    p = tmp_path / "c.toml"
    p.write_text('[llm]\nbase_url = "http://x"\nmodel = "m"\nkind = "openai"\nvision = true\n'
                 '[llm.review]\nmodel = "claude-opus-5-5"\nkind = "anthropic"\nbase_url = "https://api.anthropic.com"\n'
                 'api_key_env = "ANTHROPIC_API_KEY"\n', encoding="utf-8")
    c = load_config(p)
    assert c.vision is True and c.review.kind == "anthropic" and c.llm_settings("review").model == "claude-opus-5-5"
    assert c.endpoint("review") == ("anthropic", "https://api.anthropic.com", "ANTHROPIC_API_KEY")
    p.write_text('[llm]\nbase_url = "http://x"\nmodel = "m"\nkind = "gemini"\n', encoding="utf-8")
    with pytest.raises(ConfigError, match="kind"):
        load_config(p)
    p.write_text('[llm]\nbase_url = "http://x"\nmodel = "m"\n[llm.clarify]\nkind = "anthropic"\n', encoding="utf-8")
    with pytest.raises(ConfigError, match="kind"):   # 只有 review 能换服务
        load_config(p)


def test_config_equality_with_new_defaults():
    assert Config(base_url="http://x", model="m") == Config(base_url="http://x", model="m", kind="openai", provider="",
                                                             vision=False, review=PhaseOverride())
