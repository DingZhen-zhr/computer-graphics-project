"""启动信息、设置、key、测试连接、测试识图、案例的接口（第二版计划 3 Task 7）。

key 只走一条路：界面的输入框 → POST /api/key → 系统钥匙串。任何返回里都没有 key，只有来源和后四位提示；
模型服务返回的报错文字里如果带着 key，也先抹掉再给页面。
make_llm_for(设置, 阶段) 造模型客户端（key 由它自己从环境变量或钥匙串取）；"clarify" 用来测试连接，"review" 用来测试识图。
"""

from __future__ import annotations

import dataclasses
import importlib.metadata
import re
import shutil
import sys
import threading
from typing import Any, Callable

from cad_agent import __version__, keystore, paths
from cad_agent.cases import BUILTIN_DIR, load_cases
from cad_agent.config import ConfigError
from cad_agent.desk.hub import Hub
from cad_agent.llm.client import LLM, LLMError
from cad_agent.llm.providers import get_provider, load_providers
from cad_agent.llm.vision import test_vision
from cad_agent.settings import Settings, _parse, load_settings, save_settings

TIMEOUT_S = 15
PING = "只回答：好"
OK_TEXT = "连接正常。"
AUTH_TEXT = "密钥不对，或者没有权限用这个模型。请检查密钥和模型名。"
NET_TEXT = "连不上模型服务。请检查网络和地址。"
OTHER_TEXT = "模型服务返回了错误：{head}"
CASE_ID_RE = re.compile(r"^[A-Za-z0-9-]+$")
_KEYISH = re.compile(r"(sk-|sk_|key-)[A-Za-z0-9_\-]{6,}")


# ---------------------------------------------------------------- 小工具


def settings_dict(s: Settings) -> dict:
    d = dataclasses.asdict(s)
    d["pricing"] = dataclasses.asdict(s.pricing) if s.pricing is not None else None
    return d


def _raw(s: Settings) -> dict:
    """Settings → 设置文件那种原始字典（_parse 能读回的格式）。"""
    d = settings_dict(s)
    if d["pricing"] is None:
        del d["pricing"]
    return d


def _platform() -> str:
    return {"win32": "windows", "darwin": "mac"}.get(sys.platform, "other")


def _sca_version() -> str | None:
    try:
        return importlib.metadata.version("simplecadapi")
    except importlib.metadata.PackageNotFoundError:
        return None


def key_info(provider_id: str) -> dict:
    env = get_provider(provider_id).api_key_env
    return {"source": keystore.key_source(provider_id, env), "hint": keystore.key_hint(provider_id, env), "env": env}


def _scrub(text: str, provider_id: str) -> str:
    """报错文字里如果带着 key（有的服务会回显），换成"…"。"""
    try:
        key = keystore.get_key(provider_id, get_provider(provider_id).api_key_env)
    except ConfigError:
        key = None
    if key:
        text = text.replace(key, "…")
    return _KEYISH.sub("…", text)


def _with_timeout(fn: Callable[[], Any]) -> tuple[bool, Any]:
    """在另一个线程里跑 fn，最多等 TIMEOUT_S 秒。返回 (是否按时结束, 结果或异常)。"""
    box: dict = {}

    def run() -> None:
        try:
            box["value"] = fn()
        except BaseException as e:  # noqa: BLE001 - 交给调用方按类型处理
            box["error"] = e

    t = threading.Thread(target=run, daemon=True, name="caliper-ping")
    t.start()
    t.join(TIMEOUT_S)
    if t.is_alive():
        return False, None
    return True, box.get("error", box.get("value"))


def _llm_error_text(e: LLMError, provider_id: str) -> str:
    text = str(e)
    if "拒绝了请求" in text or "（401）" in text or "（403）" in text:
        return AUTH_TEXT
    if "网络连接失败" in text or "超时" in text:
        return NET_TEXT
    return OTHER_TEXT.format(head=_scrub(text, provider_id)[:80])


# ---------------------------------------------------------------- 路由


def make_settings_routes(hub: Hub, *, make_llm_for: Callable[[Settings, str], LLM]) -> Callable:
    def boot() -> dict:
        s = load_settings()
        key = key_info(s.provider)
        return {"version": __version__, "platform": _platform(), "python": sys.version.split()[0], "sca_version": _sca_version(),
                "providers": [dataclasses.asdict(p) for p in load_providers()], "settings": settings_dict(s), "key": key,
                "ready": key["source"] is not None, "data_dir": str(paths.app_home())}

    def save(body: Any) -> tuple[int, Any]:
        if not isinstance(body, dict):
            return 400, {"error": "设置应该是一个 JSON 对象"}
        known = {f.name for f in dataclasses.fields(Settings)}
        unknown = sorted(set(body) - known)
        if unknown:
            return 400, {"error": f"不认识的设置项：{'、'.join(unknown)}"}
        raw = {**_raw(load_settings()), **body}
        if raw.get("pricing") is None:
            raw.pop("pricing", None)
        try:
            s = _parse(raw)
        except (ConfigError, TypeError, ValueError) as e:
            return 400, {"error": str(e) or "设置的值不对"}
        save_settings(s)
        hub.refresh_agents()
        return 200, settings_dict(s)

    def set_key(body: Any) -> tuple[int, Any]:
        if not isinstance(body, dict) or not isinstance(body.get("provider"), str) or not isinstance(body.get("key"), str):
            return 400, {"error": "需要 provider 和 key 两项"}
        try:
            get_provider(body["provider"])
            keystore.set_key(body["provider"], body["key"])   # 里面去掉首尾空白；空的报错
        except (ConfigError, keystore.KeyStoreError) as e:
            return 400, {"error": str(e)}
        hub.refresh_agents()
        return 200, key_info(body["provider"])

    def delete_key(query: dict) -> tuple[int, Any]:
        provider = (query.get("provider") or [""])[0]
        try:
            get_provider(provider)
            keystore.delete_key(provider)
        except (ConfigError, keystore.KeyStoreError) as e:
            return 400, {"error": str(e)}
        hub.refresh_agents()
        return 200, key_info(provider)

    def ping(phase: str, check: Callable[[LLM], tuple[bool, str]]) -> tuple[bool, str]:
        s = load_settings()
        try:
            llm = make_llm_for(s, phase)
        except ConfigError as e:
            return False, str(e)
        finished, result = _with_timeout(lambda: check(llm))
        if not finished:
            return False, NET_TEXT
        if isinstance(result, LLMError):
            return False, _llm_error_text(result, s.provider)
        if isinstance(result, BaseException):
            raise result
        ok, message = result
        return ok, _scrub(message, s.review_provider or s.provider)

    def test_connection() -> tuple[int, Any]:
        def check(llm: LLM) -> tuple[bool, str]:
            llm.chat([{"role": "user", "content": PING}], [])
            return True, OK_TEXT
        ok, message = ping("clarify", check)
        return 200, {"ok": ok, "message": message}

    def test_vision_route() -> tuple[int, Any]:
        ok, message = ping("review", test_vision)
        if ok:
            s = load_settings()
            save_settings(dataclasses.replace(s, vision="on"))
            hub.refresh_agents()
        return 200, {"ok": ok, "message": message}

    def cases() -> list[dict]:
        found, _ = load_cases(hub.cases_dir)
        return [{"id": c.id, "title": c.title, "tags": list(c.tags), "request": c.request, "builtin": c.builtin,
                 "stages": [str(s.get("title", "")) for s in c.plan]} for c in found]

    def delete_case(case_id: str) -> tuple[int, Any]:
        if (BUILTIN_DIR / case_id).is_dir() and CASE_ID_RE.match(case_id):
            return 403, {"error": "自带的案例不能删除。"}
        d = hub.cases_dir / case_id
        if not CASE_ID_RE.match(case_id) or not (d / "case.yaml").is_file():
            return 404, {"error": "没有这个案例"}
        shutil.rmtree(d)
        return 200, {"ok": True}

    def routes(method: str, path: str, query: dict, body: Any) -> "tuple[int, Any] | None":
        if (method, path) == ("GET", "/api/boot"):
            return 200, boot()
        if path == "/api/settings":
            if method == "GET":
                return 200, settings_dict(load_settings())
            if method == "POST":
                return save(body)
        if path == "/api/key":
            if method == "POST":
                return set_key(body)
            if method == "DELETE":
                return delete_key(query)
        if (method, path) == ("POST", "/api/test-connection"):
            return test_connection()
        if (method, path) == ("POST", "/api/test-vision"):
            return test_vision_route()
        if (method, path) == ("POST", "/api/open-data"):
            from cad_agent.desk import server   # 放这里：server 不依赖这个文件，测试可以替换 reveal_path
            home = paths.app_home()
            home.mkdir(parents=True, exist_ok=True)
            server.reveal_path(home)
            return 200, {"ok": True}
        if (method, path) == ("GET", "/api/cases"):
            return 200, cases()
        if method == "DELETE" and path.startswith("/api/cases/"):
            return delete_case(path[len("/api/cases/"):])
        return None

    return routes
