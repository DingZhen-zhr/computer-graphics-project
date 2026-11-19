"""启动信息、设置、key、测试连接、案例的接口（第二版计划 3 Task 7）。

钥匙串全部用内存里的假后端；模型全部是假的；key 都是明显的假值。
"""

from __future__ import annotations

import json
import shutil
import threading
import time

import keyring
import pytest

from cad_agent.desk import settings_api
from cad_agent.desk.settings_api import make_settings_routes
from cad_agent.llm.client import LLMError, LLMReply
from cad_agent.llm.providers import load_providers
from cad_agent.settings import Settings, load_settings
from test_desk_hub import make_hub
from test_keystore import MemoryKeyring, NoBackend

FAKE_KEY = "sk-fake-0000-1111-2222-WXYZ"
OK = "连接正常。"
AUTH = "密钥不对，或者没有权限用这个模型。请检查密钥和模型名。"
NO_NET = "连不上模型服务。请检查网络和地址。"


class FakeLLM:
    def __init__(self, reply=None, error: Exception | None = None, delay: float = 0) -> None:
        self.reply, self.error, self.delay = reply or LLMReply("好", [], {}), error, delay
        self.calls: list = []
        self.release = threading.Event()

    def chat(self, messages, tools, **kw):
        self.calls.append(messages)
        if self.delay:
            self.release.wait(self.delay)
        if self.error is not None:
            raise self.error
        return self.reply


class Maker:
    def __init__(self, llm: FakeLLM) -> None:
        self.llm, self.asked = llm, []

    def __call__(self, settings: Settings, phase: str):
        self.asked.append((settings.provider, phase))
        return self.llm


@pytest.fixture
def env(monkeypatch, tmp_path):
    monkeypatch.setenv("CALIPER_HOME", str(tmp_path / "home"))
    for p in load_providers():
        monkeypatch.delenv(p.api_key_env, raising=False)
    previous = keyring.get_keyring()
    backend = MemoryKeyring()
    keyring.set_keyring(backend)
    yield backend
    keyring.set_keyring(previous)


class Api:
    def __init__(self, tmp_path, llm: FakeLLM | None = None) -> None:
        self.hub = make_hub(tmp_path)
        self.refreshed = 0
        original = self.hub.refresh_agents

        def counted() -> None:
            self.refreshed += 1
            original()

        self.hub.refresh_agents = counted   # type: ignore[method-assign]
        self.maker = Maker(llm or FakeLLM())
        self.routes = make_settings_routes(self.hub, make_llm_for=self.maker)
        self.seen: list = []

    def __call__(self, method: str, path: str, body=None, query: dict | None = None):
        got = self.routes(method, path, query or {}, body)
        self.seen.append(got)
        return got


def test_boot_shape(env, tmp_path):
    api = Api(tmp_path)
    status, body = api("GET", "/api/boot")
    assert status == 200
    assert set(body) >= {"version", "platform", "providers", "settings", "key", "ready", "sca_version"}
    assert body["platform"] in ("windows", "mac", "other") and body["sca_version"] == "2.2.7"
    assert [p["id"] for p in body["providers"]][0] == "deepseek"
    assert set(body["providers"][0]) >= {"id", "name", "kind", "base_url", "models", "api_key_env", "vision"}
    assert body["settings"]["provider"] == "deepseek" and body["settings"]["theme"] == "system"
    assert body["key"] == {"source": None, "hint": None, "env": "DEEPSEEK_API_KEY"}
    assert body["ready"] is False
    assert api("GET", "/api/nope") is None   # 不归它管的路径返回 None


def test_boot_ready_reflects_key(env, tmp_path):
    api = Api(tmp_path)
    api("POST", "/api/key", {"provider": "deepseek", "key": FAKE_KEY})
    status, body = api("GET", "/api/boot")
    assert body["ready"] is True and body["key"]["source"] == "keyring" and body["key"]["hint"] == "…WXYZ"


def test_save_settings_round_trip(env, tmp_path):
    api = Api(tmp_path)
    status, body = api("POST", "/api/settings", {"theme": "dark", "model": "deepseek-reasoner",
                                                 "pricing": {"input_hit": 0.2, "input_miss": 2, "output": 3},
                                                 "gates": {"staged": True, "mutation_check": False, "visual_review": True, "cases": True}})
    assert status == 200 and body["theme"] == "dark" and body["gates"]["mutation_check"] is False
    s = load_settings()
    assert s.theme == "dark" and s.model == "deepseek-reasoner" and s.pricing.output == 3 and s.gates.mutation_check is False
    assert api("GET", "/api/settings")[1] == body and api.refreshed == 1
    status, body = api("POST", "/api/settings", {"pricing": None})
    assert status == 200 and body["pricing"] is None and load_settings().pricing is None


def test_unknown_setting_is_400(env, tmp_path):
    api = Api(tmp_path)
    for bad in ({"api_key": FAKE_KEY}, {"nope": 1}, {"theme": "purple"}, {"provider": "nope"}, [1], {"gates": {"x": True}}):
        status, body = api("POST", "/api/settings", bad)
        assert status == 400 and body["error"], bad
    assert not (tmp_path / "home" / "settings.toml").exists() and api.refreshed == 0


def test_set_key_then_hint(env, tmp_path):
    api = Api(tmp_path)
    status, body = api("POST", "/api/key", {"provider": "deepseek", "key": FAKE_KEY})
    assert status == 200 and body == {"source": "keyring", "hint": "…WXYZ", "env": "DEEPSEEK_API_KEY"}
    assert env.store[("caliper", "deepseek")] == FAKE_KEY and api.refreshed == 1


def test_key_is_trimmed(env, tmp_path):
    api = Api(tmp_path)
    api("POST", "/api/key", {"provider": "deepseek", "key": f"  {FAKE_KEY}\r\n"})
    assert env.store[("caliper", "deepseek")] == FAKE_KEY


def test_blank_key_is_400(env, tmp_path):
    api = Api(tmp_path)
    for bad in ({"provider": "deepseek", "key": "   "}, {"provider": "deepseek"}, {"provider": "nope", "key": FAKE_KEY}, {"key": FAKE_KEY}):
        status, body = api("POST", "/api/key", bad)
        assert status == 400 and body["error"], bad
    assert env.store == {}


def test_delete_key(env, tmp_path):
    api = Api(tmp_path)
    api("POST", "/api/key", {"provider": "deepseek", "key": FAKE_KEY})
    status, body = api("DELETE", "/api/key", query={"provider": ["deepseek"]})
    assert status == 200 and body["source"] is None and env.store == {}
    assert api("DELETE", "/api/key", query={})[0] == 400


def test_env_key_is_reported_as_env(env, tmp_path, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", FAKE_KEY)
    api = Api(tmp_path)
    body = api("GET", "/api/boot")[1]
    assert body["key"] == {"source": "env", "hint": "…WXYZ", "env": "DEEPSEEK_API_KEY"} and body["ready"] is True


def test_no_keyring_backend_message(env, tmp_path):
    keyring.set_keyring(NoBackend())
    api = Api(tmp_path)
    status, body = api("POST", "/api/key", {"provider": "deepseek", "key": FAKE_KEY})
    assert status == 400 and "环境变量" in body["error"] and "DEEPSEEK_API_KEY" in body["error"]


def test_connection_ok(env, tmp_path):
    llm = FakeLLM()
    api = Api(tmp_path, llm)
    assert api("POST", "/api/test-connection", {}) == (200, {"ok": True, "message": OK})
    assert llm.calls[0] == [{"role": "user", "content": "只回答：好"}] and api.maker.asked[0][0] == "deepseek"


def test_connection_auth_error_message(env, tmp_path):
    err = LLMError("模型服务拒绝了请求（401）：请检查 API key 是否正确、是否有该模型的权限")
    assert Api(tmp_path, FakeLLM(error=err))("POST", "/api/test-connection", {}) == (200, {"ok": False, "message": AUTH})


def test_connection_network_and_other_errors(env, tmp_path):
    net = LLMError("网络连接失败，已重试 2 次")
    assert Api(tmp_path / "a", FakeLLM(error=net))("POST", "/api/test-connection", {})[1] == {"ok": False, "message": NO_NET}
    other = LLMError("模型服务返回错误 404：" + "没有这个模型" * 30)
    body = Api(tmp_path / "b", FakeLLM(error=other))("POST", "/api/test-connection", {})[1]
    assert body["ok"] is False and body["message"] == "模型服务返回了错误：" + str(other)[:80]


def test_connection_without_key_or_settings_problem(env, tmp_path):
    from cad_agent.config import ConfigError

    api = Api(tmp_path)
    api.maker.llm = None
    def broken(settings, phase):
        raise ConfigError("还没有可用的密钥")
    api.routes = make_settings_routes(api.hub, make_llm_for=broken)
    status, body = api("POST", "/api/test-connection", {})
    assert status == 200 and body == {"ok": False, "message": "还没有可用的密钥"}


def test_connection_timeout_message(env, tmp_path, monkeypatch):
    assert settings_api.TIMEOUT_S == 15
    monkeypatch.setattr(settings_api, "TIMEOUT_S", 0.3)
    llm = FakeLLM(delay=20)
    api = Api(tmp_path, llm)
    started = time.monotonic()
    body = api("POST", "/api/test-connection", {})[1]
    llm.release.set()
    assert time.monotonic() - started < 5 and body == {"ok": False, "message": NO_NET}


def test_vision_success_turns_setting_on(env, tmp_path):
    api = Api(tmp_path, FakeLLM(LLMReply("左边红色，右边蓝色", [], {})))
    status, body = api("POST", "/api/test-vision", {})
    assert status == 200 and body["ok"] is True and load_settings().vision == "on"
    assert api.maker.asked[-1][1] == "review" and api.refreshed == 1


def test_vision_failure_keeps_setting(env, tmp_path):
    api = Api(tmp_path, FakeLLM(LLMReply("看不到图片", [], {})))
    body = api("POST", "/api/test-vision", {})[1]
    assert body["ok"] is False and body["message"] and load_settings().vision == "auto"
    api2 = Api(tmp_path / "x", FakeLLM(error=LLMError("模型服务返回错误 400：不支持图片")))
    assert api2("POST", "/api/test-vision", {})[1]["ok"] is False and load_settings().vision == "auto"


def test_cases_list_and_delete(env, tmp_path):
    api = Api(tmp_path)
    builtin = api("GET", "/api/cases")[1]
    assert len(builtin) == 8 and all(c["builtin"] for c in builtin)
    assert set(builtin[0]) == {"id", "title", "tags", "request", "builtin", "stages"} and builtin[0]["stages"]
    src = next(p for p in (settings_api.BUILTIN_DIR).iterdir() if p.is_dir())
    shutil.copytree(src, api.hub.cases_dir / "user-20261111-120000")
    cases = api("GET", "/api/cases")[1]
    mine = [c for c in cases if not c["builtin"]]
    assert [c["id"] for c in mine] == ["user-20261111-120000"]
    assert api("DELETE", "/api/cases/user-20261111-120000") == (200, {"ok": True})
    assert not (api.hub.cases_dir / "user-20261111-120000").exists()
    assert api("DELETE", "/api/cases/user-nope")[0] == 404
    assert api("DELETE", "/api/cases/..")[0] == 404


def test_builtin_case_cannot_be_deleted(env, tmp_path):
    api = Api(tmp_path)
    cid = api("GET", "/api/cases")[1][0]["id"]
    status, body = api("DELETE", f"/api/cases/{cid}")
    assert status == 403 and body["error"]
    assert (settings_api.BUILTIN_DIR / cid / "case.yaml").is_file()


def test_no_key_in_any_response(env, tmp_path, monkeypatch):
    api = Api(tmp_path, FakeLLM(error=LLMError(f"模型服务返回错误 400：bad key {FAKE_KEY}")))
    api("POST", "/api/key", {"provider": "deepseek", "key": FAKE_KEY})
    api("POST", "/api/key", {"provider": "kimi", "key": FAKE_KEY})
    for method, path, body in (("GET", "/api/boot", None), ("GET", "/api/settings", None), ("POST", "/api/settings", {"theme": "light"}),
                               ("POST", "/api/test-connection", {}), ("POST", "/api/test-vision", {}), ("GET", "/api/cases", None)):
        api(method, path, body)
    api("DELETE", "/api/key", query={"provider": ["kimi"]})
    text = json.dumps(api.seen, ensure_ascii=False)
    assert FAKE_KEY not in text and FAKE_KEY[:12] not in text


def test_open_data_folder(env, tmp_path, monkeypatch):
    from cad_agent import paths
    from cad_agent.desk import server as desk_server

    shown = []
    monkeypatch.setattr(desk_server, "reveal_path", shown.append)
    api = Api(tmp_path)
    assert api("POST", "/api/open-data", {}) == (200, {"ok": True})
    assert shown == [paths.app_home()] and paths.app_home().is_dir()


def test_theme_only_save_does_not_rebuild_agents(env, tmp_path):
    """只换外观时不用按新设置重造智能体（复查 M1）。"""
    api = Api(tmp_path)
    assert api("POST", "/api/settings", {"theme": "dark"})[0] == 200
    assert api.refreshed == 0
    api("POST", "/api/settings", {"model": "deepseek-v4-pro"})
    assert api.refreshed == 1
