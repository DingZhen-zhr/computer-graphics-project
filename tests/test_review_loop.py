"""主循环里的看图审查：分阶段的假流程 + 假审查模型 + 会写四视图的假 run_job。"""

from __future__ import annotations

import json

from cad_agent.agent.loop import Agent
from cad_agent.config import Config
from cad_agent.gates import Gates
from cad_agent.llm.client import LLMError, LLMReply, ToolCall
from cad_agent.llm.fake import ScriptedLLM, scripted_call
from cad_agent.llm.vision import tiny_test_image
from cad_agent.notebook import FeatureList
from cad_agent.review import VIEWS
from cad_agent.session import Session
from cad_agent.tools import ToolBox, Workspace
from helpers import Runner, make_brief
from helpers_staged import StageRunner, staged_brief
from test_staged_loop import BUILD, PLAN, S1, S2, log_rows

REVIEW_ON = Gates(mutation_check=False, cases=False)
TARGETS = ["底板", "立板", "立板的下端和底板的一端重叠"]
OBJECTION_HEAD = "【看图审查没有通过（程序生成）】"


class ViewRunner(StageRunner):
    """给了 render_views 时，往那个目录写四张图（views 可以只写其中几张）。"""

    def __init__(self, views=VIEWS, **kw) -> None:
        super().__init__(**kw)
        self.views = views
        self.view_calls: list = []

    def __call__(self, rendered, checks_raw, param_names, **kw):
        result = super().__call__(rendered, checks_raw, param_names, **kw)
        out = kw.get("render_views")
        if out is not None:
            self.view_calls.append(out)
            out.mkdir(parents=True, exist_ok=True)
            result.view_paths = {}
            for name in self.views:
                p = out / f"{name}.png"
                p.write_bytes(tiny_test_image() + name.encode("ascii"))
                result.view_paths[name] = p
        return result


def verdicts(*vs: str) -> LLMReply:
    items = [{"target": t, "verdict": v, "reason": f"{t}：{v} 的理由"} for t, v in zip(TARGETS, vs)]
    return LLMReply("", [ToolCall("r1", "submit_review", {"items": items, "overall": "总体印象"})],
                    {"prompt_tokens": 1000, "completion_tokens": 30, "total_tokens": 1030, "cached_tokens": 0, "reasoning_tokens": 0})


def make(tmp_path, replies, review_replies=None, runner=None, gates: Gates = REVIEW_ON, review_llm_none: bool = False):
    ws = Workspace(staged_brief(), FeatureList(), [])
    runner = runner or ViewRunner()
    llm = ScriptedLLM(replies)
    review_llm = None if review_llm_none else ScriptedLLM(review_replies or [])
    box = ToolBox(ws, run_job=runner, gates=gates)
    session = Session(tmp_path / "sessions")
    agent = Agent(llm, box, session, Config(base_url="http://x", model="m"), review_llm=review_llm)
    return agent, ws, llm, review_llm, runner, session


def review_json(turn) -> dict:
    return json.loads((turn.version_dir / "review.json").read_text(encoding="utf-8"))


def test_review_pass_then_deliver(tmp_path):
    # 3.0 计划 2（偏离 D30，用户同意）：清单最后多一项"整体做工"，剧本里的审查员四项都答符合
    four = verdicts("match", "match", "match")
    four.tool_calls[0].arguments["items"].append({"target": "整体做工", "verdict": "match", "reason": "整体做工：match 的理由"})
    agent, ws, llm, review_llm, runner, session = make(tmp_path, [PLAN, S1, S2], [four])
    turn = agent.handle_user("开始")
    assert turn.kind == "delivered"
    data = review_json(turn)
    assert data["passed"] is True and [i["verdict"] for i in data["items"]] == ["match"] * 4
    assert "看图审查：通过（4 项符合，0 项看不出）。" in turn.text
    rows = [r for r in log_rows(session) if r["kind"] == "review"]
    assert len(rows) == 1 and rows[0]["round"] == 1 and rows[0]["passed"] is True and rows[0]["overall"] == "总体印象"
    assert turn.llm_calls == 4 and turn.prompt_tokens >= 1000 and turn.completion_tokens >= 30   # 审查的用量计入本轮
    assert len(review_llm.calls) == 1 and [m["role"] for m in review_llm.calls[0]] == ["system", "user"]
    out = runner.view_calls[0]
    assert out == session.dir / "review" / "round-1" and sorted(p.name for p in out.iterdir()) == [f"{v}.png" for v in sorted(VIEWS)]
    lines = turn.text.splitlines()
    assert lines.index("看图审查：通过（4 项符合，0 项看不出）。") > 0


def test_review_mismatch_goes_back_once(tmp_path):
    fix = scripted_call(*BUILD)
    agent, ws, llm, review_llm, runner, session = make(
        tmp_path, [PLAN, S1, S2, fix], [verdicts("match", "mismatch", "match"), verdicts("match", "match", "match")])
    turn = agent.handle_user("开始")
    assert turn.kind == "delivered" and turn.version_dir.name == "v1"
    assert len(session.versions()) == 1 and len(review_llm.calls) == 2
    fourth = llm.calls[3]
    note = [m for m in fourth if m["role"] == "user" and OBJECTION_HEAD in str(m["content"])]
    assert len(note) == 1 and "- 立板：立板：mismatch 的理由" in note[0]["content"]
    assert fourth[-1] is not None and fourth.index(note[0]) == len(fourth) - 1   # 审查意见在工具结果之后
    rows = [r for r in log_rows(session) if r["kind"] == "review"]
    assert [(r["round"], r["passed"]) for r in rows] == [(1, False), (2, True)]
    assert runner.view_calls == [session.dir / "review" / "round-1", session.dir / "review" / "round-2"]


def test_second_mismatch_still_delivers_with_objections(tmp_path):
    fix = scripted_call(*BUILD)
    agent, ws, llm, review_llm, runner, session = make(
        tmp_path, [PLAN, S1, S2, fix], [verdicts("match", "mismatch", "match"), verdicts("mismatch", "mismatch", "match")])
    turn = agent.handle_user("开始")
    assert turn.kind == "delivered"
    assert "看图审查有异议，请你自己看一下模型：" in turn.text
    assert "  - 底板：底板：mismatch 的理由" in turn.text.splitlines() and "  - 立板：立板：mismatch 的理由" in turn.text.splitlines()
    data = review_json(turn)
    assert data["passed"] is False and data["rounds"] == 2
    assert len(review_llm.calls) == 2


def test_no_review_without_vision(tmp_path):
    agent, ws, llm, review_llm, runner, session = make(tmp_path, [PLAN, S1, S2], review_llm_none=True)
    turn = agent.handle_user("开始")
    assert turn.kind == "delivered" and runner.view_calls == []
    assert review_json(turn) == {"skipped": "模型不能识图"}
    assert "未做看图审查（模型不能识图）。" in turn.text.splitlines()


def test_review_off_by_gate(tmp_path):
    gates = Gates(mutation_check=False, visual_review=False, cases=False)
    agent, ws, llm, review_llm, runner, session = make(tmp_path, [PLAN, S1, S2], [verdicts("match", "match", "match")], gates=gates)
    turn = agent.handle_user("开始")
    assert turn.kind == "delivered" and runner.view_calls == [] and review_llm.calls == []
    assert review_json(turn) == {"skipped": "已关闭"}
    assert "看图审查" not in turn.text   # 关掉开关时交付文字和以前一样


def test_review_skipped_when_nothing_rendered(tmp_path):
    runner = ViewRunner(views=())
    agent, ws, llm, review_llm, runner, session = make(tmp_path, [PLAN, S1, S2], [verdicts("match", "match", "match")], runner=runner)
    turn = agent.handle_user("开始")
    assert turn.kind == "delivered" and review_llm.calls == [] and len(runner.view_calls) == 1
    assert review_json(turn) == {"skipped": "没有渲染出图片"}
    assert "未做看图审查（没有渲染出图片）。" in turn.text.splitlines()


def test_some_views_missing_still_reviews(tmp_path):
    runner = ViewRunner(views=("iso", "front"))
    agent, ws, llm, review_llm, runner, session = make(tmp_path, [PLAN, S1, S2], [verdicts("match", "match", "match")], runner=runner)
    assert agent.handle_user("开始").kind == "delivered"
    sent = review_llm.calls[0][1]["content"]
    assert sum(1 for p in sent if p["type"] == "image_url") == 2
    assert "俯视图（这张图没有渲染出来）" in [p.get("text") for p in sent]


def test_review_rounds_reset_after_delivery(tmp_path):
    fix = scripted_call(*BUILD)
    change = scripted_call("update_brief", {"set_params": [{"name": "phone_w", "value": 80, "unit": "mm", "source": "user"}]})
    rebuild = scripted_call(*BUILD)
    reviews = [verdicts("mismatch", "match", "match"), verdicts("match", "match", "match"),
               verdicts("mismatch", "match", "match"), verdicts("match", "match", "match")]
    agent, ws, llm, review_llm, runner, session = make(tmp_path, [PLAN, S1, S2, fix, change, rebuild, scripted_call(*BUILD)], reviews)
    assert agent.handle_user("开始").kind == "delivered"
    second = agent.handle_user("宽度改成 80")
    assert second.kind == "delivered" and second.version_dir.name == "v2"
    rows = [r for r in log_rows(session) if r["kind"] == "review"]
    assert [(r["round"], r["passed"]) for r in rows] == [(1, False), (2, True), (1, False), (2, True)]


def test_review_llm_error_does_not_block_delivery(tmp_path):
    secret = "test-key-0000"
    agent, ws, llm, review_llm, runner, session = make(tmp_path, [PLAN, S1, S2], [LLMError("网络连接失败，已重试 2 次")])
    turn = agent.handle_user("开始")
    assert turn.kind == "delivered" and review_json(turn) == {"skipped": "审查调用失败"}
    assert "未做看图审查（审查调用失败）。" in turn.text.splitlines()
    rows = [r for r in log_rows(session) if r["kind"] == "review_error"]
    assert len(rows) == 1 and "网络连接失败" in rows[0]["message"]
    assert secret not in (session.dir / "log.jsonl").read_text(encoding="utf-8")


def test_review_images_not_in_log(tmp_path):
    agent, ws, llm, review_llm, runner, session = make(tmp_path, [PLAN, S1, S2], [verdicts("match", "match", "match")])
    agent.handle_user("开始")
    text = (session.dir / "log.jsonl").read_text(encoding="utf-8")
    assert "data:image" not in text and "iVBOR" not in text


def test_objection_hits_failure_limit(tmp_path):
    agent, ws, llm, review_llm, runner, session = make(tmp_path, [PLAN, S1, S2], [verdicts("mismatch", "match", "match")])
    agent.toolbox.build_failures = 0
    agent.config = Config(base_url="http://x", model="m", max_build_failures=1)
    agent.toolbox.max_build_failures = 1
    turn = agent.handle_user("开始")
    assert turn.kind == "failed" and "看图审查" in turn.text and session.versions() == []


def test_legacy_flow_has_no_review(tmp_path):
    from helpers import BOX, PHONE_W, TILT

    ws = Workspace(make_brief(confirmed=True), FeatureList(), [])
    review_llm = ScriptedLLM([])
    agent = Agent(ScriptedLLM([scripted_call("upsert_feature", {"slug": "base", "role": "build", "code": BOX}, "",
                                             ("set_checks", {"checks": [PHONE_W, TILT]}), ("build", {}))]),
                  ToolBox(ws, run_job=Runner()), Session(tmp_path / "sessions"), Config(base_url="http://x", model="m"),
                  review_llm=review_llm)
    turn = agent.handle_user("做")
    assert turn.kind == "delivered" and review_llm.calls == []
    assert not (turn.version_dir / "review.json").exists() and "看图审查" not in turn.text


def test_review_llm_is_built_only_with_vision(monkeypatch):
    from cad_agent.config import PhaseOverride
    from cad_agent.llm.anthropic_client import AnthropicLLM
    from cad_agent.llm.factory import make_review_llm, secret_env_names

    base = Config(base_url="https://api.deepseek.com", model="deepseek-flash")
    assert make_review_llm(base, "test-key-0000") is None                                   # 不能识图
    assert make_review_llm(Config(base_url="http://x", model="m", vision=True, gates=Gates(visual_review=False)), "k") is None
    assert make_review_llm(Config(base_url="http://x", model="m", vision=True, gates=Gates.legacy()), "k") is None
    same = make_review_llm(Config(base_url="http://x", model="m", vision=True), "test-key-0000")
    assert same is not None and same.model == "m"
    other = Config(base_url="https://api.deepseek.com", model="deepseek-flash", vision=True,
                   review=PhaseOverride(model="claude-haiku-5-5", kind="anthropic", base_url="https://api.anthropic.com",
                                        api_key_env="CALIPER_TEST_REVIEW_KEY"))
    assert secret_env_names(other) == ("DEEPSEEK_API_KEY", "CALIPER_TEST_REVIEW_KEY") and secret_env_names(base) == ("DEEPSEEK_API_KEY",)
    monkeypatch.delenv("CALIPER_TEST_REVIEW_KEY", raising=False)
    import pytest

    from cad_agent.config import ConfigError
    with pytest.raises(ConfigError, match="CALIPER_TEST_REVIEW_KEY"):
        make_review_llm(other, "test-key-0000")
    monkeypatch.setenv("CALIPER_TEST_REVIEW_KEY", "test-key-1111")
    review = make_review_llm(other, "test-key-0000")
    assert isinstance(review, AnthropicLLM) and review.model == "claude-haiku-5-5"


def test_cli_build_agent_passes_review_llm(monkeypatch, tmp_path):
    from cad_agent import cli

    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key-0000")
    cfg = Config(base_url="https://api.deepseek.com", model="deepseek-flash", sessions_dir=tmp_path / "s",
                 cases_dir=tmp_path / "c", vision=True)
    agent, _ = cli.build_agent(cfg)
    assert agent.review_llm is not None and agent.toolbox.secret_names == ("DEEPSEEK_API_KEY",)
    agent2, _ = cli.build_agent(Config(base_url="https://api.deepseek.com", model="deepseek-flash", sessions_dir=tmp_path / "s2",
                                       cases_dir=tmp_path / "c"))
    assert agent2.review_llm is None
