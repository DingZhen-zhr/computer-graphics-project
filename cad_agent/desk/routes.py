"""桌面端会话相关的接口和版本文件的白名单（第二版计划 3 Task 6）。不碰 HTTP，只做"请求 → 结果"。

出错一律抛 ApiError（状态码 + 中文说明）；Hub 和工作台的异常在这里翻译：
不存在 404、正忙 409、参数不对 400、示例会话只读 403。
"""

from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any, Callable

from cad_agent.cli import _load_brief, diff_briefs
from cad_agent.desk.hub import Hub
from cad_agent.desk.workbench import Busy

VERSION_RE = re.compile(r"^v\d+$")
STAGE_FILE_RE = re.compile(r"^s\d+\.stl$")
ROUND_RE = re.compile(r"^round-\d+$")
VIEW_RE = re.compile(r"^[a-z]+\.png$")
VERSION_FILES = ("view.png", "model.step", "model.stl", "model.py", "checks.json", "gate.json", "review.json",
                 "product.step", "assembly.py", "motion.json")   # 后三个是多零件（3.0）的
PART_RE = re.compile(r"^[a-z0-9_]+$")
PART_FILES = ("model.step", "model.stl", "model.py", "checks.json")
NOT_FOUND = "没有这个会话"


class ApiError(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status, self.message = status, message


def translate(e: Exception) -> ApiError:
    if isinstance(e, ApiError):
        return e
    if isinstance(e, FileNotFoundError):
        return ApiError(404, NOT_FOUND)
    if isinstance(e, Busy):
        return ApiError(409, str(e) or "正在运行，等这一轮结束再操作。")
    if isinstance(e, PermissionError):
        return ApiError(403, str(e) or "示例会话只能看，不能改。")
    if isinstance(e, ValueError):
        return ApiError(400, str(e) or "参数不对")
    raise e


def _need_dict(body: Any) -> dict:
    if not isinstance(body, dict):
        raise ApiError(400, "请求内容应该是一个 JSON 对象")
    return body


def _text(body: Any, key: str) -> str:
    value = _need_dict(body).get(key)
    if not isinstance(value, str):
        raise ApiError(400, f"需要文字字段 {key}")
    return value


def _values(body: Any) -> dict[str, float]:
    values = _need_dict(body).get("values")
    if not isinstance(values, dict) or not values:
        raise ApiError(400, "需要 {\"values\": {参数名: 数值}}")
    for name, v in values.items():
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
            raise ApiError(400, f"参数 {name} 的数值不对")
    return values


def _version_dir(hub: Hub, sid: str, name: str) -> Path:
    if not isinstance(name, str) or not VERSION_RE.fullmatch(name):
        raise ApiError(400, "版本名应该像 v1、v2 这样")
    d = hub.open(sid).session.part_dir() / "versions" / name
    if not d.is_dir():
        raise ApiError(404, "没有这个版本")
    return d


def session_api(hub: Hub, method: str, segs: list[str], query: dict, body: Any, reveal: Callable[[Path], None]) -> Any:
    """segs 是 /api/ 后面按 / 分开的部分（已解码）。返回要发给页面的 JSON 数据；出错抛 ApiError。"""
    try:
        return _dispatch(hub, method, segs, query, body, reveal)
    except Exception as e:  # noqa: BLE001 - 翻译不了的会原样抛出，由服务端变成 500
        raise translate(e) from None


def _dispatch(hub: Hub, method: str, segs: list[str], query: dict, body: Any, reveal: Callable[[Path], None]) -> Any:
    if segs == ["sessions"]:
        if method == "GET":
            return hub.list()
        if method == "POST":
            return {"id": hub.create()}
    if len(segs) == 2 and segs[0] == "sessions" and method == "DELETE":
        hub.delete(segs[1])
        return {"ok": True}
    if len(segs) != 3 or segs[0] != "sessions":
        raise ApiError(404, "没有这个接口")
    sid, action = segs[1], segs[2]
    route = (method, action)
    if route == ("POST", "rename"):
        hub.rename(sid, _text(body, "title"))
        return {"ok": True}
    if route == ("GET", "state"):
        return hub.open(sid).state()
    if route == ("POST", "message"):
        hub.open(sid).submit(_text(body, "text"))
        return {"ok": True}
    if route == ("POST", "stop"):
        hub.open(sid).stop()
        return {"ok": True}
    if route == ("POST", "params"):
        values = _values(body)
        r = hub.open(sid).apply_params(values)
        return {"ok": r.ok, "text": r.text, "version": r.version_dir.name if r.version_dir else None, "changes": r.changes,
                "failed_checks": r.failed_checks, "error": r.error}
    if route == ("POST", "case"):
        tags = _need_dict(body).get("tags")
        if not isinstance(tags, list) or not all(isinstance(t, str) for t in tags):
            raise ApiError(400, "标签应该是文字的列表")
        return {"id": hub.open(sid).save_case(_text(body, "title"), tags, hub.cases_dir)}
    if route == ("GET", "diff"):
        a, b = (query.get(k, [""])[0] for k in ("a", "b"))
        va, vb = _version_dir(hub, sid, a), _version_dir(hub, sid, b)
        return {"lines": diff_briefs(_load_brief(va), _load_brief(vb))}
    if route == ("POST", "reveal"):
        reveal(_version_dir(hub, sid, _need_dict(body).get("version")))
        return {"ok": True}
    raise ApiError(404, "没有这个接口")


def version_file(hub: Hub, sid: str, rest: list[str]) -> Path:
    """/files/<id>/<版本>/<文件> 里允许取的文件；不在白名单里的一律 404。"""
    try:
        base = hub.open(sid).session.part_dir()
    except FileNotFoundError:
        raise ApiError(404, "没有这个文件") from None
    path: Path | None = None
    if len(rest) >= 2 and rest[0] == "current":
        tail = rest[1:]
        if len(tail) == 2 and tail[0] == "stages" and STAGE_FILE_RE.fullmatch(tail[1]):
            path = base / "stages" / tail[1]
        elif len(tail) == 3 and tail[0] == "review" and ROUND_RE.fullmatch(tail[1]) and VIEW_RE.fullmatch(tail[2]):
            path = base / "review" / tail[1] / tail[2]
    elif len(rest) >= 2 and VERSION_RE.fullmatch(rest[0]):
        v, tail = base / "versions" / rest[0], rest[1:]
        if len(tail) == 1 and tail[0] in VERSION_FILES:
            path = v / tail[0]
        elif len(tail) == 2 and tail[0] == "stages" and STAGE_FILE_RE.fullmatch(tail[1]):
            path = v / "stages" / tail[1]
        elif len(tail) == 3 and tail[0] == "parts" and PART_RE.fullmatch(tail[1]) and tail[2] in PART_FILES:
            path = v / "parts" / tail[1] / tail[2]
    if path is None or not path.is_file():
        raise ApiError(404, "没有这个文件")
    return path
