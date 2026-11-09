import json
import math
import re
from dataclasses import replace
from pathlib import Path

import pytest

from benchmarks import run as bench
from benchmarks.run import (ALL_TASKS, load_task, max_dimension_deviation, render_results_md, render_summary_md, run_benchmarks,
                            run_task, stage_names)
from benchmarks.sim_user import CONFIRM_LINE, SYSTEM_TEMPLATE, USER_TEMPLATE, SimUser
from cad_agent.agent.loop import Agent
from cad_agent.brief import Brief
from cad_agent.checks.spec import CheckResult, parse_checks
from cad_agent.config import Config
from cad_agent.llm.client import LLMReply
from cad_agent.llm.fake import ScriptedLLM, scripted_call
from cad_agent.notebook import FeatureList
from cad_agent.sandbox.execute import RunResult
from cad_agent.session import Session
from cad_agent.tools import ToolBox, Workspace
from helpers import BOX, PHONE_W, TILT, USER_PARAMS, good_result

PROMPTS_DOC = Path(__file__).resolve().parent.parent / "docs" / "superpowers" / "plans" / "2026-11-09-cad-agent-v1-prompts.md"
TASKS_DIR = Path(__file__).resolve().parent.parent / "benchmarks" / "tasks"


# ---------------------------------------------------------------- 任务文件


def test_tasks_load_and_validate():
    assert ALL_TASKS == ["phone_stand", "flange", "l_bracket"]
    for name in ALL_TASKS:
        task = load_task(name)
        assert task["id"] == name and task["initial"].strip() and task["hidden_spec"].strip()
        assert task["max_user_turns"] == 12 and len(task["modifications"]) == 1
        assert list(task["acceptance"]) == stage_names(task) == ["after_initial", "after_mod_1"]
        for stage, raw in task["acceptance"].items():
            assert len(parse_checks(raw, set())) == 3 + len(raw), (name, stage)
            ids = [c["id"] for c in raw]
            assert len(ids) == len(set(ids)) and raw


def test_task_texts_follow_the_plan():
    assert load_task("phone_stand")["initial"] == "做一个放在桌上看视频的小支架"
    assert load_task("flange")["initial"] == "帮我做一个法兰盘"
    assert load_task("l_bracket")["initial"] == "做一个 L 形的安装支架，要带加强筋"
    assert load_task("phone_stand")["modifications"] == ["支撑角度改成 70 度"]
    assert load_task("flange")["modifications"] == ["螺栓孔改成 8 个"]
    assert load_task("l_bracket")["modifications"] == ["孔径改成 8.4（M8）"]
    spec = load_task("l_bracket")["hidden_spec"]
    assert "立板在底板的一端" in spec and "正中间" in spec


def by_id(task, stage):
    return {c["id"]: c for c in task["acceptance"][stage]}


def test_phone_stand_acceptance_numbers():
    task = load_task("phone_stand")
    first, second = by_id(task, "after_initial"), by_id(task, "after_mod_1")
    assert first["width-x"]["expected"] == 90 and first["width-x"]["tol"] == 0.5
    assert first["tilt-angle"]["expected"] == 115 and second["tilt-angle"]["expected"] == 110
    assert first["tilt-angle"]["tol"] == 0.5
    for gap in ("gap-wall-left", "gap-wall-right"):
        assert first[gap]["op"] == ">=" and first[gap]["expected"] == 1 and first[gap]["kind"] == "faces"
    assert ["geom.center.x", ">=", -10.5] in first["gap-wall-left"]["where"]
    assert ["geom.normal.x", "<=", -0.99] in first["gap-wall-right"]["where"]
    assert ["geom.area", ">=", 5000] in first["tilt-angle"]["a"] and ["geom.center.z", "<=", 0.1] in first["tilt-angle"]["b"]


def test_flange_acceptance_numbers():
    task = load_task("flange")
    first, second = by_id(task, "after_initial"), by_id(task, "after_mod_1")
    assert [first[k]["expected"] for k in ("size-x", "size-y", "height-z")] == [100, 100, 30]
    assert first["bore-open"]["type"] == "point_outside" and first["bore-open"]["point"] == [0, 0, 15]
    low, high = (c[2] for c in first["bolt-holes"]["where"] if c[0] == "geom.area")
    area = math.pi * 11 * 10
    assert abs(low - area * 0.95) < 0.1 and abs(high - area * 1.05) < 0.1
    assert first["bolt-holes"]["expected"] == 6 and second["bolt-holes"]["expected"] == 8


def test_l_bracket_acceptance_numbers():
    task = load_task("l_bracket")
    first, second = by_id(task, "after_initial"), by_id(task, "after_mod_1")
    assert [first[k]["expected"] for k in ("len-x", "len-y", "len-z")] == [60, 40, 60]
    assert all(first[k]["tol"] == 0.5 for k in ("len-x", "len-y", "len-z"))
    assert first["total-volume"]["expected"] == 26316 and second["total-volume"]["expected"] == 25892
    assert first["total-volume"]["rel_tol"] == 0.03
    for stage, d in ((first, 6.6), (second, 8.4)):
        low, high = (c[2] for c in stage["hole-faces"]["where"] if c[0] == "geom.area")
        area = math.pi * d * 5
        assert abs(low - area * 0.95) < 0.1 and abs(high - area * 1.05) < 0.1 and stage["hole-faces"]["expected"] == 4
    # 手算过程写进了 YAML 注释
    text = (TASKS_DIR / "l_bracket.yaml").read_text(encoding="utf-8")
    assert "24000" in text and "26316" in text and "25892" in text


def test_load_task_rejects_bad_files(tmp_path):
    def write(text):
        p = tmp_path / "bad.yaml"
        p.write_text(text, encoding="utf-8")
        return p

    base = 'id: bad\ninitial: "x"\nhidden_spec: "y"\nmodifications: ["m"]\n'
    with pytest.raises(ValueError, match="after_mod_1"):
        load_task(write(base + "acceptance:\n  after_initial: []\n"))
    with pytest.raises(ValueError, match="bbox"):
        load_task(write(base + "acceptance:\n  after_initial: [{id: a, type: weight, expected: 1}]\n  after_mod_1: []\n"))
    with pytest.raises(ValueError, match="hidden_spec"):
        load_task(write('id: bad\ninitial: "x"\nacceptance: {after_initial: []}\n'))
    with pytest.raises(ValueError, match="bad"):
        load_task(write('id: other\ninitial: "x"\nhidden_spec: "y"\nacceptance: {after_initial: []}\n'))  # id 要和文件名一致
    with pytest.raises(ValueError, match="没有这个任务"):
        load_task("no_such_task")


# ---------------------------------------------------------------- 模拟用户


def test_sim_user_prompts_are_verbatim_copy():
    doc = PROMPTS_DOC.read_text(encoding="utf-8")
    blocks = re.findall(r"```text\n(.*?)\n```", doc.split("## 5. 模拟用户提示词")[1].split("## 6. 速查表格式")[0], flags=re.S)
    assert [SYSTEM_TEMPLATE, USER_TEMPLATE, CONFIRM_LINE] == blocks


def test_sim_user_reply_formats_messages():
    llm = ScriptedLLM([LLMReply(" 78 毫米 ", [], {"total_tokens": 11}), LLMReply("确认", [], {"total_tokens": 4}), LLMReply("", [], {})])
    user = SimUser(llm, "手机宽 78 mm\n角度 65 度\n")
    assert user.reply("手机多宽？", "question") == "78 毫米"
    assert user.reply("【需求单】…", "confirm") == "确认"
    assert user.reply("你想要什么？", "reply") == "你定吧"  # 模型什么都没说时用“你定吧”
    system0, user0 = llm.calls[0]
    assert system0["role"] == "system" and "手机宽 78 mm\n角度 65 度" in system0["content"] and "<hidden_spec>" not in system0["content"]
    assert user0 == {"role": "user", "content": "助手说：\n手机多宽？"}
    assert llm.calls[1][1]["content"] == "助手说：\n【需求单】…\n（助手正在请你确认需求单）"
    assert "确认" not in llm.calls[0][1]["content"] and (user.calls, user.tokens) == (3, 15)
    assert llm.tool_lists == [[], [], []]  # 模拟用户不用工具


# ---------------------------------------------------------------- run_task


class BenchRunner:
    """代替 run_job：构建调用返回成功；导出调用写文件；验收调用按 deviation 造出测量结果。"""

    def __init__(self, deviation: float = 0.0, acceptance_error: dict | None = None) -> None:
        self.deviation, self.acceptance_error, self.acceptance_calls = deviation, acceptance_error, []

    def __call__(self, rendered, checks_raw, param_names, **kw):
        if kw.get("export_step") is not None:
            kw["export_step"].parent.mkdir(parents=True, exist_ok=True)
            kw["export_step"].write_bytes(b"STEP")
            kw["render_png"].write_bytes(b"PNG")
            return good_result(step_path=kw["export_step"], png_path=kw["render_png"])
        if param_names:
            return good_result()
        self.acceptance_calls.append((rendered, checks_raw))
        if self.acceptance_error:
            return RunResult(ok=False, error=self.acceptance_error)
        checks = [CheckResult(i, i, True, None, None, None, "") for i in ("valid", "single_solid", "positive_volume")]
        for raw in checks_raw:
            expected = float(raw["expected"]) if "expected" in raw else None
            measured = None if expected is None else expected + self.deviation
            checks.append(CheckResult(raw["id"], raw["type"], measured is None or abs(self.deviation) <= 0.5, measured, expected, 0.5, ""))
        return RunResult(ok=all(c.passed for c in checks), error=None, checks=checks)


DEMO = {
    "id": "demo", "initial": "做一块板", "hidden_spec": "板宽 78 mm，角度 65 度", "max_user_turns": 6,
    "modifications": ["角度改成 70 度"],
    "acceptance": {
        "after_initial": [{"id": "w", "type": "bbox", "axis": "x", "expected": 78, "tol": 0.5}],
        "after_mod_1": [{"id": "w", "type": "bbox", "axis": "x", "expected": 78, "tol": 0.5},
                        {"id": "n", "type": "count", "kind": "faces", "where": [], "expected": 6}],
    },
}
CHANGE = scripted_call("update_brief", {"set_params": [{"name": "tilt_deg", "value": 70, "unit": "deg", "source": "user", "note": "角度"}]})
FULL_SCRIPT = [
    scripted_call("update_brief", {"part": {"name": "板"}, "set_params": USER_PARAMS, "features": ["板"]}),
    scripted_call("request_confirmation", {}),
    scripted_call("upsert_feature", {"slug": "base", "role": "build", "code": BOX}),
    scripted_call("set_checks", {"checks": [PHONE_W, TILT]}),
    scripted_call("build", {}),
    CHANGE,
    scripted_call("build", {}),
]


def agent_factory(replies, runner):
    def make_agent(root: Path) -> Agent:
        ws = Workspace(Brief(), FeatureList(), [])
        return Agent(ScriptedLLM(replies), ToolBox(ws, run_job=runner), Session(root / "sessions"), Config(base_url="http://x", model="m"))

    return make_agent


def sim(*replies: str) -> SimUser:
    return SimUser(ScriptedLLM([LLMReply(r, [], {"total_tokens": 3}) for r in replies]), DEMO["hidden_spec"])


def test_run_task_with_fakes(tmp_path):
    runner = BenchRunner()
    result = run_task(DEMO, agent_factory(FULL_SCRIPT, runner), sim("确认"), tmp_path / "demo", run_job=runner)
    assert set(result) >= {"task", "success", "stages", "repairs", "duration_s", "llm_calls", "tokens", "user_turns"}
    assert result["task"] == "demo" and result["success"] is True
    assert [s["stage"] for s in result["stages"]] == ["after_initial", "after_mod_1"] and all(s["delivered"] for s in result["stages"])
    assert result["user_turns"] == 3 and result["llm_calls"] == 7 and result["repairs"] == 0
    assert result["sim_llm_calls"] == 1 and result["sim_tokens"] == 3 and result["duration_s"] >= 0
    first = result["stages"][0]["acceptance"][0]
    assert first["id"] == "w" and first["expected"] == 78 and first["measured"] == 78 and first["deviation"] == 0 and first["passed"] is True
    assert [a["id"] for a in result["stages"][1]["acceptance"]] == ["w", "n"]
    assert result["stages"][0]["version"] == "v1" and result["stages"][1]["version"] == "v2"
    json.dumps(result)  # 结果要能写成 JSON
    # 验收用的是交付版本里的 model.py，参数集合为空
    rendered, checks_raw = runner.acceptance_calls[0]
    assert "def _" in rendered.text and rendered.cell_lines == {} and checks_raw == DEMO["acceptance"]["after_initial"]
    assert (tmp_path / "demo" / "sessions").is_dir()


def test_run_task_gives_up_after_max_user_turns(tmp_path):
    task = {**DEMO, "max_user_turns": 3}
    chat = [LLMReply(f"第 {i} 次回复", [], {}) for i in range(3)]
    result = run_task(task, agent_factory(chat, BenchRunner()), sim("你定吧", "你定吧"), tmp_path / "t", run_job=BenchRunner())
    assert result["success"] is False and result["user_turns"] == 3
    assert [(s["stage"], s["delivered"]) for s in result["stages"]] == [("after_initial", False), ("after_mod_1", False)]
    assert result["stages"][0]["acceptance"] == [] and result["stages"][1]["skipped"] is True
    assert result["sim_llm_calls"] == 2  # 最后一轮之后不用再请模拟用户回复


def test_run_task_acceptance_failure_records_deviation(tmp_path):
    runner = BenchRunner(deviation=2.0)
    result = run_task(DEMO, agent_factory(FULL_SCRIPT, runner), sim("确认"), tmp_path / "t", run_job=runner)
    assert result["success"] is False and all(s["delivered"] for s in result["stages"])
    entry = result["stages"][0]["acceptance"][0]
    assert entry["deviation"] == 2.0 and entry["passed"] is False and entry["measured"] == 80


def test_run_task_acceptance_run_error(tmp_path):
    runner = BenchRunner(acceptance_error={"cell": None, "type": "SandboxCrash", "message": "boom"})
    result = run_task(DEMO, agent_factory(FULL_SCRIPT, runner), sim("确认"), tmp_path / "t", run_job=runner)
    stage = result["stages"][0]
    assert result["success"] is False and stage["error"]["message"] == "boom"
    assert stage["acceptance"][0]["passed"] is False and stage["acceptance"][0]["measured"] is None


def test_run_task_counts_repairs(tmp_path):
    class Flaky(BenchRunner):
        def __init__(self):
            super().__init__()
            self.builds = 0

        def __call__(self, rendered, checks_raw, param_names, **kw):
            if param_names and kw.get("export_step") is None:
                self.builds += 1
                if self.builds == 1:
                    return RunResult(ok=False, error={"cell": "base", "type": "NameError", "message": "x"})
            return super().__call__(rendered, checks_raw, param_names, **kw)

    runner = Flaky()
    script = [*FULL_SCRIPT[:5], scripted_call("build", {}), *FULL_SCRIPT[5:]]
    result = run_task(DEMO, agent_factory(script, runner), sim("确认"), tmp_path / "t", run_job=runner)
    assert result["success"] is True and result["repairs"] == 1


def test_run_task_sums_usage_and_cost(tmp_path):
    usage = {"prompt_tokens": 100, "completion_tokens": 10, "total_tokens": 110, "cached_tokens": 60, "reasoning_tokens": 4}
    script = [replace(r, usage=usage, cost=0.01) for r in FULL_SCRIPT]
    runner = BenchRunner()
    user = SimUser(ScriptedLLM([LLMReply("确认", [], {"total_tokens": 3}, cost=0.002)]), DEMO["hidden_spec"])
    result = run_task(DEMO, agent_factory(script, runner), user, tmp_path / "t", run_job=runner)
    n = result["llm_calls"]
    assert n > 0 and result["success"] is True
    assert (result["prompt_tokens"], result["completion_tokens"], result["cached_tokens"], result["reasoning_tokens"]) == (100 * n, 10 * n, 60 * n, 4 * n)
    assert result["cost"] == pytest.approx(0.01 * n) and result["tokens"] == 110 * n
    assert result["sim_cost"] == pytest.approx(0.002) and result["sim_tokens"] == 3
    json.dumps(result)


def test_run_task_cost_is_none_without_pricing(tmp_path):
    runner = BenchRunner()
    result = run_task(DEMO, agent_factory(FULL_SCRIPT, runner), sim("确认"), tmp_path / "t", run_job=runner)
    assert result["cost"] is None and result["sim_cost"] is None and result["prompt_tokens"] == 0


# ---------------------------------------------------------------- 汇总


def fake_result(task="demo", success=True, deviation=0.3, typ="bbox"):
    return {"task": task, "success": success, "repairs": 2, "duration_s": 12.345, "llm_calls": 9, "tokens": 1500, "user_turns": 3,
            "stages": [{"stage": "after_initial", "delivered": True, "version": "v1", "error": None, "acceptance": [
                {"id": "w", "type": typ, "expected": 78, "measured": 78 + deviation, "deviation": deviation, "passed": success},
                {"id": "ang", "type": "angle", "expected": 115, "measured": 118, "deviation": 3, "passed": False},
                {"id": "pt", "type": "point_outside", "expected": None, "measured": None, "deviation": None, "passed": True}]}]}


def test_max_dimension_deviation_only_counts_lengths():
    assert max_dimension_deviation(fake_result(deviation=-0.4)) == pytest.approx(0.4)  # 角度的 3 度不算尺寸
    assert max_dimension_deviation(fake_result(typ="volume")) is None
    assert max_dimension_deviation({"stages": []}) is None


def test_results_md_has_header_and_rows():
    md = render_results_md([fake_result("flange"), fake_result("l_bracket", success=False)])
    assert "任务 | 成功 | 修复次数 | 耗时(s) | 模型调用 | token | 最大尺寸偏差" in md
    assert "| flange | 是 | 2 | 12.3 | 9 | 1500 | 0.3 mm |" in md and "| l_bracket | 否 |" in md
    assert "## flange" in md and "after_initial" in md and "ang" in md


def metered(task="flange", success=True, cost=0.2, run=None, **extra):
    r = {**fake_result(task, success=success), "prompt_tokens": 1000, "cached_tokens": 600, "completion_tokens": 200,
         "reasoning_tokens": 100, "cost": cost, **extra}
    if run is not None:
        r["run"] = run
    return r


def test_summary_md_rows():
    md = render_summary_md([metered(success=s, cost=c, run=i) for i, (s, c) in enumerate([(True, 0.1), (False, 0.2), (True, 0.3)], 1)])
    assert "| 任务 | 成功 | 平均费用(元) | 平均耗时(s) | 平均模型调用 | 平均输入 | 其中命中缓存 | 平均输出 | 其中思考 |" in md
    assert "| flange | 2/3 | 0.2000 | 12.3 | 9.0 | 1000 | 600 | 200 | 100 |" in md
    assert "| 合计 | 2/3 | 0.2000 |" in md


def test_summary_md_one_row_per_task_in_first_seen_order():
    md = render_summary_md([metered("l_bracket", run=1), metered("flange", run=1), metered("l_bracket", run=2)])
    rows = [line for line in md.splitlines() if line.startswith("| ") and "任务" not in line]
    assert [r.split(" | ")[0] for r in rows] == ["| l_bracket", "| flange", "| 合计"]
    assert rows[0].split(" | ")[1] == "2/2" and rows[2].split(" | ")[1] == "3/3"


def test_summary_md_missing_fields_show_dash():
    md = render_summary_md([fake_result("flange"), {"task": "crash", "success": False, "stages": [], "error": "boom"}])
    assert "| flange | 1/1 | - | 12.3 | 9.0 | - | - | - | - |" in md
    assert "| crash | 0/1 | - | - |" in md and "| 合计 | 1/2 | - |" in md


def test_results_md_shows_run_number():
    md = render_results_md([metered(run=2)])
    assert "| flange#2 | 是 |" in md and "## flange#2" in md


def test_repeat_runs_each_task(tmp_path, monkeypatch):
    seen = []

    def fake_run_task(task, make_agent, sim_user, out_dir, **kw):
        seen.append((task["id"], Path(out_dir).name))
        return fake_result(task["id"])

    monkeypatch.setattr(bench, "run_task", fake_run_task)
    results = run_benchmarks(["phone_stand", "flange"], make_agent=lambda root: None, make_sim_user=lambda spec: SimUser(ScriptedLLM([]), spec),
                             results_dir=tmp_path / "r", print_fn=lambda *a, **k: None, repeat=3)
    assert len(results) == 6 and [r["run"] for r in results] == [1, 2, 3, 1, 2, 3]
    assert [r["task"] for r in results] == ["phone_stand"] * 3 + ["flange"] * 3
    assert seen[:2] == [("phone_stand", "phone_stand-1"), ("phone_stand", "phone_stand-2")] and seen[3] == ("flange", "flange-1")
    saved = json.loads((tmp_path / "r" / "results.json").read_text(encoding="utf-8"))
    assert len(saved) == 6 and saved[0]["run"] == 1
    md = (tmp_path / "r" / "results.md").read_text(encoding="utf-8")
    assert md.startswith("| 任务 | 成功 | 平均费用(元)") and "| phone_stand | 3/3 |" in md and "phone_stand#2" in md


def test_single_run_keeps_the_v1_layout(tmp_path, monkeypatch):
    seen = []

    def fake_run_task(task, make_agent, sim_user, out_dir, **kw):
        seen.append(Path(out_dir).name)
        return fake_result(task["id"])

    monkeypatch.setattr(bench, "run_task", fake_run_task)
    results = run_benchmarks(["flange"], make_agent=lambda root: None, make_sim_user=lambda spec: SimUser(ScriptedLLM([]), spec),
                             results_dir=tmp_path / "r", print_fn=lambda *a, **k: None)
    assert seen == ["flange"] and "run" not in results[0]


def test_crash_in_a_repeat_run_is_recorded_with_its_run_number(tmp_path, monkeypatch):
    def fake_run_task(task, make_agent, sim_user, out_dir, **kw):
        raise RuntimeError("模型崩了")

    monkeypatch.setattr(bench, "run_task", fake_run_task)
    results = run_benchmarks(["flange"], make_agent=lambda root: None, make_sim_user=lambda spec: SimUser(ScriptedLLM([]), spec),
                             results_dir=tmp_path / "r", print_fn=lambda *a, **k: None, repeat=2)
    assert [(r["run"], r["success"]) for r in results] == [(1, False), (2, False)] and "模型崩了" in results[1]["error"]


def test_run_benchmarks_writes_results_and_survives_a_crash(tmp_path, monkeypatch):
    names = ["phone_stand", "flange"]
    seen = []

    def fake_run_task(task, make_agent, sim_user, out_dir, **kw):
        seen.append((task["id"], Path(out_dir).name, sim_user.system))
        if task["id"] == "flange":
            raise RuntimeError("模型崩了")
        return fake_result(task["id"])

    monkeypatch.setattr(bench, "run_task", fake_run_task)
    results = run_benchmarks(names, make_agent=lambda root: None, make_sim_user=lambda spec: SimUser(ScriptedLLM([]), spec),
                             results_dir=tmp_path / "r", print_fn=lambda *a, **k: None)
    assert [r["task"] for r in results] == names and results[0]["success"] is True
    assert results[1]["success"] is False and "模型崩了" in results[1]["error"]
    assert [s[:2] for s in seen] == [("phone_stand", "phone_stand"), ("flange", "flange")]
    assert "160×78×12" in seen[0][2]  # 模拟用户拿到了该任务的隐藏需求
    saved = json.loads((tmp_path / "r" / "results.json").read_text(encoding="utf-8"))
    assert [r["task"] for r in saved] == names
    assert "任务 | 成功" in (tmp_path / "r" / "results.md").read_text(encoding="utf-8")


def test_main_missing_key_returns_1(monkeypatch, tmp_path):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    out: list[str] = []
    code = bench.main(["--config", str(Path(__file__).resolve().parent.parent / "config.example.toml"), "--out", str(tmp_path / "r")],
                      print_fn=lambda *a, **k: out.append(" ".join(map(str, a))))
    assert code == 1 and "请先设置环境变量 DEEPSEEK_API_KEY" in "\n".join(out) and not (tmp_path / "r").exists()


def test_main_rejects_bad_repeat_and_empty_set(tmp_path, monkeypatch):
    monkeypatch.setattr(bench, "TASK_SETS", {"dev": ALL_TASKS, "holdout": [], "all": ALL_TASKS})  # 不依赖留出任务有没有写好
    out: list[str] = []

    def say(*a, **k):
        out.append(" ".join(map(str, a)))

    assert bench.main(["--repeat", "0", "--out", str(tmp_path / "r")], print_fn=say) == 1 and "repeat 至少是 1" in "\n".join(out)
    out.clear()
    assert bench.main(["--set", "holdout", "--out", str(tmp_path / "r")], print_fn=say) == 1 and "这一组还没有任务" in "\n".join(out)
    assert not (tmp_path / "r").exists()


def test_task_sets_and_default_tasks():
    assert bench.TASK_SETS["dev"] == ALL_TASKS and bench.TASK_SETS["all"] == ALL_TASKS + bench.HOLDOUT_TASKS
    assert bench.TASK_SETS["holdout"] == bench.HOLDOUT_TASKS


def test_main_runs_the_chosen_set_and_repeat(tmp_path, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "fake-key-for-test")
    captured = {}

    def fake_run_benchmarks(names, make_agent, make_sim_user, results_dir, **kw):
        captured.update(names=names, repeat=kw.get("repeat"))
        return [fake_result(names[0])]

    monkeypatch.setattr(bench, "run_benchmarks", fake_run_benchmarks)
    monkeypatch.setattr(bench, "TASK_SETS", {"dev": ALL_TASKS, "holdout": ["flange"], "all": ALL_TASKS})
    cfg = str(Path(__file__).resolve().parent.parent / "config.example.toml")
    assert bench.main(["--config", cfg, "--out", str(tmp_path / "r"), "--set", "holdout", "--repeat", "2"], print_fn=lambda *a, **k: None) == 0
    assert captured == {"names": ["flange"], "repeat": 2}
    assert bench.main(["--config", cfg, "--out", str(tmp_path / "r")], print_fn=lambda *a, **k: None) == 0
    assert captured == {"names": ALL_TASKS, "repeat": 1}
    assert bench.main(["--config", cfg, "--out", str(tmp_path / "r"), "--tasks", "l_bracket", "--set", "holdout"], print_fn=lambda *a, **k: None) == 0
    assert captured["names"] == ["l_bracket"]   # 给了 --tasks 就以它为准


def test_main_rejects_unknown_task(tmp_path):
    out: list[str] = []
    code = bench.main(["--tasks", "no_such", "--out", str(tmp_path / "r")], print_fn=lambda *a, **k: out.append(" ".join(map(str, a))))
    assert code == 1 and "没有这个任务" in "\n".join(out)
