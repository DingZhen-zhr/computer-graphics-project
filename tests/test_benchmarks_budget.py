"""评测脚本的花费上限（--budget）和案例开关（--cases）。全部用假的 run_task，不调用任何模型。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import benchmarks.run as bench

EXAMPLE = Path(__file__).resolve().parent.parent / "config.example.toml"
NAMES = ["phone_stand", "flange", "l_bracket"]


def fake_result(name: str, cost: float | None, sim_cost: float | None) -> dict:
    return {"task": name, "success": True, "stages": [], "repairs": 0, "duration_s": 1.0, "llm_calls": 2, "tokens": 10,
            "user_turns": 1, "prompt_tokens": 8, "completion_tokens": 2, "cached_tokens": 0, "reasoning_tokens": 0,
            "cost": cost, "sim_cost": sim_cost, "sim_llm_calls": 1, "sim_tokens": 3}


@pytest.fixture
def fake_tasks(monkeypatch):
    """run_task 换成假的：按任务名给出费用；记下跑了哪些。"""
    ran: list[str] = []
    costs: dict[str, tuple[float | None, float | None]] = {}

    def run_task(task, make_agent, sim_user, out_dir, **kw):
        ran.append(task["id"])
        cost, sim_cost = costs.get(task["id"], (0.5, 0.1))
        return fake_result(task["id"], cost, sim_cost)

    monkeypatch.setattr(bench, "run_task", run_task)
    return ran, costs


def run(tmp_path, names=NAMES, budget=None, repeat=1):
    out: list[str] = []
    results = bench.run_benchmarks(names, lambda root: None, lambda spec: None, tmp_path / "r", budget=budget, repeat=repeat,
                                   print_fn=lambda *a, **k: out.append(" ".join(map(str, a))))
    return results, out


def write_config(tmp_path, pricing: bool) -> str:
    p = tmp_path / "c.toml"
    text = '[llm]\nbase_url = "https://example.invalid/v1"\nmodel = "m"\napi_key_env = "CALIPER_TEST_BENCH_KEY"\n'
    if pricing:
        text += "[llm.pricing]\ninput_hit = 0.2\ninput_miss = 2.0\noutput = 8.0\n"
    p.write_text(text, encoding="utf-8")
    return str(p)


def test_budget_requires_pricing(tmp_path, monkeypatch):
    monkeypatch.setenv("CALIPER_TEST_BENCH_KEY", "test-key-0000")
    called = []
    monkeypatch.setattr(bench, "run_benchmarks", lambda *a, **k: called.append(1) or [])
    out: list[str] = []
    code = bench.main(["--config", write_config(tmp_path, pricing=False), "--out", str(tmp_path / "r"), "--budget", "15"],
                      print_fn=lambda *a, **k: out.append(" ".join(map(str, a))))
    assert code == 2 and called == [] and not (tmp_path / "r").exists()
    assert "价目表" in "\n".join(out)
    out.clear()
    code = bench.main(["--config", write_config(tmp_path, pricing=True), "--out", str(tmp_path / "r"), "--budget", "0"],
                      print_fn=lambda *a, **k: out.append(" ".join(map(str, a))))
    assert code == 2 and called == [] and "大于 0" in "\n".join(out)


def test_budget_is_passed_through(tmp_path, monkeypatch):
    monkeypatch.setenv("CALIPER_TEST_BENCH_KEY", "test-key-0000")
    captured = {}
    monkeypatch.setattr(bench, "run_benchmarks", lambda names, *a, **k: captured.update(k) or [])
    assert bench.main(["--config", write_config(tmp_path, pricing=True), "--out", str(tmp_path / "r"), "--budget", "15"],
                      print_fn=lambda *a, **k: None) == 0
    assert captured["budget"] == 15.0
    assert bench.main(["--config", write_config(tmp_path, pricing=True), "--out", str(tmp_path / "r")], print_fn=lambda *a, **k: None) == 0
    assert captured["budget"] is None


def test_budget_stops_between_tasks(tmp_path, fake_tasks):
    ran, costs = fake_tasks
    results, out = run(tmp_path, budget=1.0)
    assert ran == ["phone_stand", "flange"]
    assert [r["task"] for r in results] == NAMES
    assert results[2] == {"task": "l_bracket", "skipped_for_budget": True}
    saved = json.loads((tmp_path / "r" / "results.json").read_text(encoding="utf-8"))
    assert [r["task"] for r in saved] == NAMES and saved[2]["skipped_for_budget"] is True
    assert out[-1] == "已花费 ¥1.20，上限 ¥1.00"
    md = (tmp_path / "r" / "results.md").read_text(encoding="utf-8")
    assert "因预算跳过" in md


def test_budget_counts_sim_user_cost(tmp_path, fake_tasks):
    ran, costs = fake_tasks
    for n in NAMES:
        costs[n] = (0.3, 0.5)   # 只算智能体的话三个都跑得完（0.9），加上模拟用户的就不行
    results, out = run(tmp_path, budget=1.0)
    assert ran == ["phone_stand", "flange"] and results[2]["skipped_for_budget"] is True
    assert out[-1] == "已花费 ¥1.60，上限 ¥1.00"


def test_budget_with_repeat_skips_remaining_runs(tmp_path, fake_tasks):
    ran, costs = fake_tasks
    results, out = run(tmp_path, names=["phone_stand", "flange"], budget=1.0, repeat=2)
    assert ran == ["phone_stand", "phone_stand"]
    assert results[2:] == [{"task": "flange", "skipped_for_budget": True, "run": 1}, {"task": "flange", "skipped_for_budget": True, "run": 2}]


def test_missing_cost_counts_as_zero_and_is_reported(tmp_path, fake_tasks):
    ran, costs = fake_tasks
    costs["phone_stand"] = (None, None)
    results, out = run(tmp_path, budget=1.0)
    assert ran == NAMES   # 0 + 0.6 + 0.6 = 1.2，第三个开始前只花了 0.6
    assert any("没有算出费用" in line for line in out)


def test_without_budget_nothing_changes(tmp_path, fake_tasks):
    ran, costs = fake_tasks
    for n in NAMES:
        costs[n] = (5.0, 5.0)
    results, out = run(tmp_path)
    assert ran == NAMES and not any("skipped_for_budget" in r for r in results)
    assert not any("已花费" in line for line in out)
    assert "因预算跳过" not in (tmp_path / "r" / "results.md").read_text(encoding="utf-8")


def test_cases_flag_turns_gate_off(tmp_path, monkeypatch):
    monkeypatch.setenv("CALIPER_TEST_BENCH_KEY", "test-key-0000")
    built = []

    def fake_run_benchmarks(names, make_agent, make_sim_user, results_dir, **kw):
        built.append(make_agent(tmp_path / f"a{len(built)}"))
        return []

    monkeypatch.setattr(bench, "run_benchmarks", fake_run_benchmarks)
    cfg = write_config(tmp_path, pricing=False)
    assert bench.main(["--config", cfg, "--out", str(tmp_path / "r"), "--cases", "off"], print_fn=lambda *a, **k: None) == 0
    assert bench.main(["--config", cfg, "--out", str(tmp_path / "r")], print_fn=lambda *a, **k: None) == 0
    assert bench.main(["--config", cfg, "--out", str(tmp_path / "r"), "--cases", "on"], print_fn=lambda *a, **k: None) == 0
    assert [a.toolbox.gates.cases for a in built] == [False, True, True]
    assert all(a.toolbox.gates.staged for a in built)   # 别的开关不动
    with pytest.raises(SystemExit):
        bench.main(["--config", cfg, "--cases", "maybe"], print_fn=lambda *a, **k: None)


def test_summary_shows_skipped_for_budget():
    results = [fake_result("phone_stand", 0.5, 0.1), {"task": "flange", "skipped_for_budget": True}]
    summary = bench.render_summary_md(results)
    rows = {line.split("|")[1].strip(): line for line in summary.splitlines()[2:]}
    assert "| 因预算跳过 |" in rows["flange"] and "1/1" in rows["phone_stand"]
    assert "0.5000" in rows["合计"]   # 合计只算跑了的
    detail = bench.render_results_md(results)
    assert "| flange | 因预算跳过 |" in detail
