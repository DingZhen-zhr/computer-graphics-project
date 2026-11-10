"""案例库（设计文档第 3.7 节）：自带案例在包里的 case_data/，用户案例在数据目录的 cases/。

每个案例是一个目录，里面一个 case.yaml。进入规划时按相似度挑最多 2 个，作为【参考案例】放在快照后面。
相似度只用汉字（和字母数字）的相邻二元组重合加标签命中，不引入分词库和向量库。
"""

from __future__ import annotations

import copy
import datetime
import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from cad_agent.brief import Brief
from cad_agent.notebook import Feature, FeatureList
from cad_agent.plan import PlanError, revise, stage_id
from cad_agent.staged.summary import feature_block
from cad_agent.tools import Workspace

BUILTIN_DIR = Path(__file__).parent / "case_data"
TAG_BONUS = 0.15
THRESHOLD = 0.10
MAX_CASE_CHARS = 3000
KEYS = ("title", "tags", "request", "brief", "plan", "features", "checks")
CASES_HEAD = "【参考案例（程序生成，只供参考；尺寸和结构以需求单为准）】"
CUT_TAIL = "…（后面的内容省略）"
_NOT_WORD = re.compile(r"[\W_]+")


class CaseError(ValueError):
    """案例文件写得不对；信息里有文件位置。"""


@dataclass(frozen=True)
class Case:
    id: str                 # 目录名
    title: str
    tags: tuple[str, ...]
    request: str            # 一句话需求
    brief: dict             # Brief.to_dict() 的格式
    plan: list[dict]        # [{"title", "done_when"}]
    features: list[dict]    # [{"slug", "role", "stage", "code"}]
    checks: list[dict]      # 每条带 "stage"
    builtin: bool


# ---------------------------------------------------------------- 读取


def _need(cond: bool, where: Path, why: str) -> None:
    if not cond:
        raise CaseError(f"{where}：{why}")


def _text_list(value: object) -> bool:
    return isinstance(value, list) and all(isinstance(x, str) and x.strip() for x in value)


def load_case(path: Path, builtin: bool) -> Case:
    """path 是案例目录。格式不对时抛 CaseError，信息里有 case.yaml 的位置和原因。"""
    f = Path(path) / "case.yaml"
    _need(f.is_file(), f, "找不到 case.yaml")
    try:
        data = yaml.safe_load(f.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        raise CaseError(f"{f}：YAML 写法不对：{e}") from e
    _need(isinstance(data, dict), f, "内容必须是一个映射")
    missing = [k for k in KEYS if k not in data]
    _need(not missing, f, f"缺少 {'、'.join(missing)}")
    _need(isinstance(data["title"], str) and bool(data["title"].strip()), f, "title 必须是非空文字")
    _need(_text_list(data["tags"]), f, "tags 必须是非空文字组成的列表")
    _need(isinstance(data["request"], str) and bool(data["request"].strip()), f, "request 必须是非空文字")
    _need(isinstance(data["brief"], dict), f, "brief 必须是需求单（Brief.to_dict 的格式）")
    try:
        Brief.from_dict(data["brief"])
    except (KeyError, TypeError, ValueError) as e:
        raise CaseError(f"{f}：brief 读不出来：{e}") from e
    plan = data["plan"]
    _need(isinstance(plan, list) and len(plan) > 0, f, "plan 不能为空")
    try:
        ids = revise(None, plan, {}).ids()
    except PlanError as e:
        raise CaseError(f"{f}：plan 写得不对：{e}") from e
    feats = data["features"]
    _need(isinstance(feats, list) and len(feats) > 0, f, "features 必须是非空列表")
    for i, ft in enumerate(feats, 1):
        _need(isinstance(ft, dict) and all(isinstance(ft.get(k), str) for k in ("slug", "role", "stage", "code")), f,
              f"第 {i} 个特征要有 slug、role、stage、code 四项文字")
        _need(ft["stage"] in ids, f, f"特征 {ft['slug']} 的 stage {ft['stage']} 不在计划里（计划有 {'、'.join(ids)}）")
    checks = data["checks"]
    _need(isinstance(checks, list), f, "checks 必须是列表")
    for i, c in enumerate(checks, 1):
        _need(isinstance(c, dict) and c.get("stage") in ids, f, f"第 {i} 条检查要写 stage，并且是计划里的阶段")
    return Case(Path(path).name, data["title"].strip(), tuple(t.strip() for t in data["tags"]), data["request"].strip(),
                data["brief"], [{"title": s["title"], "done_when": s["done_when"]} for s in plan], feats, checks, builtin)


def _load_dir(root: Path | None, builtin: bool, problems: list[str]) -> list[Case]:
    if root is None or not Path(root).is_dir():
        return []
    out = []
    for d in sorted(p for p in Path(root).iterdir() if p.is_dir()):
        try:
            out.append(load_case(d, builtin))
        except CaseError as e:
            problems.append(str(e))
    return out


def load_cases(user_dir: Path | None) -> tuple[list[Case], list[str]]:
    """自带的在前，用户的在后；读不了的案例跳过，原因放进第二项。"""
    problems: list[str] = []
    found = _load_dir(BUILTIN_DIR, True, problems) + _load_dir(user_dir, False, problems)
    return found, problems


# ---------------------------------------------------------------- 检索


def _bigrams(text: str) -> set[str]:
    t = _NOT_WORD.sub("", text).lower()
    return {t[i:i + 2] for i in range(len(t) - 1)}


def query_text(brief: Brief) -> str:
    """检索用的需求单文字：零件名、用途、各组成部分连起来。"""
    return brief.part_name + brief.purpose + "".join(brief.features)


def _case_text(case: Case) -> str:
    return case.title + case.request + "".join(case.brief.get("features", []))


def score(query: str, case: Case) -> float:
    """二元组的交集大小除以并集大小，再加上 TAG_BONUS ×（在 query 里原样出现的标签个数）。"""
    a, b = _bigrams(query), _bigrams(_case_text(case))
    jaccard = len(a & b) / len(a | b) if a | b else 0.0
    return jaccard + TAG_BONUS * sum(1 for t in case.tags if t in query)


def pick_cases(brief: Brief, cases: list[Case], k: int = 2) -> list[Case]:
    q = query_text(brief)
    scored = [(score(q, c), c) for c in cases]
    scored = [x for x in scored if x[0] >= THRESHOLD]
    scored.sort(key=lambda x: (-x[0], not x[1].builtin, x[1].id))
    return [c for _, c in scored[:k]]


# ---------------------------------------------------------------- 给模型看的文字


def _case_block(case: Case) -> str:
    features = [Feature(f["slug"], f["role"], f["code"], f["stage"]) for f in case.features]
    lines = [f"== {case.title} ==", f"需求：{case.request}", "计划："]
    lines += [f"{stage_id(i)} {s['title']}：{s['done_when']}" for i, s in enumerate(case.plan)]
    lines += ["特征：", feature_block(features)]
    text = "\n".join(lines)
    if len(text) > MAX_CASE_CHARS:
        text = text[: MAX_CASE_CHARS - len(CUT_TAIL) - 1] + "\n" + CUT_TAIL
    return text


def render_cases(cases: list[Case]) -> str:
    """第二版提示词文档第 5 节；空表返回空文字。"""
    if not cases:
        return ""
    return CASES_HEAD + "\n" + "\n\n".join(_case_block(c) for c in cases)


# ---------------------------------------------------------------- 保存和取用


def save_case(user_dir: Path, title: str, tags: list[str], ws: Workspace) -> Path:
    """把交付过的零件存成用户案例，目录名 user-<时间>（重名时加 -2、-3）。不调用模型。"""
    if not isinstance(title, str) or not title.strip():
        raise CaseError("案例的标题不能为空")
    if not _text_list(tags):
        raise CaseError("标签必须是非空文字组成的列表")
    if ws.plan is None or not ws.plan.complete():
        raise CaseError("只有计划全部通过（交付过）的零件才能存成案例")
    root = Path(user_dir)
    root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    n = 1
    while True:
        d = root / (f"user-{stamp}" if n == 1 else f"user-{stamp}-{n}")
        try:
            d.mkdir()
            break
        except FileExistsError:
            n += 1
    brief = ws.brief
    data = {
        "title": title.strip(), "tags": [t.strip() for t in tags],
        "request": brief.purpose or brief.part_name or title.strip(),
        "brief": brief.to_dict(),
        "plan": [{"title": s.title, "done_when": s.done_when} for s in ws.plan.stages],
        "features": [{"slug": f.slug, "role": f.role, "stage": f.stage, "code": f.code} for f in ws.features.items],
        "checks": copy.deepcopy(ws.checks_raw),
    }
    (d / "case.yaml").write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return d


def case_workspace(case: Case) -> Workspace:
    """按案例造一个工作区：需求单已确认，计划各阶段未通过。"""
    brief = Brief.from_dict(copy.deepcopy(case.brief))
    brief.confirmed = True
    brief.require_relations = True
    features = FeatureList([Feature(f["slug"], f["role"], f["code"], f["stage"]) for f in case.features])
    ws = Workspace(brief, features, copy.deepcopy(case.checks))
    ws.plan = revise(None, case.plan, {})
    return ws
