from pathlib import Path

import pytest

from cad_agent.config import Config, ConfigError, load_config

EXAMPLE = Path(__file__).resolve().parent.parent / "config.example.toml"


def test_load_example():
    c = load_config(EXAMPLE)
    assert c == Config(
        base_url="https://api.deepseek.com", model="deepseek-chat", api_key_env="DEEPSEEK_API_KEY",
        temperature=0.2, run_timeout_s=60, max_build_failures=3, max_tool_calls=40, sessions_dir=Path("sessions"),
    )


def test_defaults():
    c = Config(base_url="http://x", model="m")
    assert (c.api_key_env, c.temperature, c.run_timeout_s, c.max_build_failures, c.max_tool_calls, c.sessions_dir) == (
        "DEEPSEEK_API_KEY", 0.2, 60, 3, 40, Path("sessions"))


def test_api_key_missing_message(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    with pytest.raises(ConfigError, match="DEEPSEEK_API_KEY") as e:
        Config(base_url="http://x", model="m").api_key()
    assert str(e.value) == "请先设置环境变量 DEEPSEEK_API_KEY"


def test_api_key_read_from_configured_variable(monkeypatch):
    monkeypatch.setenv("MY_LLM_KEY", "abc123")
    assert Config(base_url="http://x", model="m", api_key_env="MY_LLM_KEY").api_key() == "abc123"
    monkeypatch.setenv("MY_LLM_KEY", "   ")
    with pytest.raises(ConfigError, match="MY_LLM_KEY"):
        Config(base_url="http://x", model="m", api_key_env="MY_LLM_KEY").api_key()


def test_key_is_not_part_of_repr(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "super-secret-value")
    c = load_config(EXAMPLE)
    assert "super-secret-value" not in repr(c) and "super-secret-value" not in str(c.__dict__)


def write(tmp_path, text):
    p = tmp_path / "c.toml"
    p.write_text(text, encoding="utf-8")
    return p


def test_load_overrides(tmp_path):
    p = write(tmp_path, '[llm]\nbase_url = "http://localhost:1234/v1"\nmodel = "glm-4"\napi_key_env = "GLM_KEY"\ntemperature = 0.5\n'
                        '[agent]\nrun_timeout_s = 90\nmax_build_failures = 5\nmax_tool_calls = 10\nsessions_dir = "D:/cad-sessions"\n')
    c = load_config(p)
    assert (c.base_url, c.model, c.api_key_env, c.temperature) == ("http://localhost:1234/v1", "glm-4", "GLM_KEY", 0.5)
    assert (c.run_timeout_s, c.max_build_failures, c.max_tool_calls, c.sessions_dir) == (90, 5, 10, Path("D:/cad-sessions"))


def test_chinese_comments_in_file(tmp_path):
    p = write(tmp_path, '# 模型地址\n[llm]\nbase_url = "http://x"  # 注释\nmodel = "m"\n')
    assert load_config(p).model == "m"


@pytest.mark.parametrize("text,hint", [
    ('[llm]\nmodel = "m"\n', "base_url"),
    ('[llm]\nbase_url = "http://x"\n', "model"),
    ('[llm]\nbase_url = "http://x"\nmodel = "m"\nmodle = "typo"\n', "modle"),
    ('[llm]\nbase_url = "http://x"\nmodel = "m"\n[agent]\nmax_tool_calls = "many"\n', "max_tool_calls"),
    ('[llm]\nbase_url = "http://x"\nmodel = "m"\n[other]\na = 1\n', "other"),
    ("这不是 toml", "格式"),
])
def test_bad_config_has_clear_message(tmp_path, text, hint):
    with pytest.raises(ConfigError, match=hint):
        load_config(write(tmp_path, text))


def test_missing_file(tmp_path):
    with pytest.raises(ConfigError, match="config.toml"):
        load_config(tmp_path / "config.toml")
