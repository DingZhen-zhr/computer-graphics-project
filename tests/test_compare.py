import json

import pytest

from benchmarks.compare import main, render_compare_md, task_means

HEADER = "| 任务 | 成功（旧→新） | 费用（旧→新） | 耗时（旧→新） | 调用（旧→新） | 输入（旧→新） | 输出（旧→新） |"


def run(task, success=True, cost=1.0, **extra):
    return {"task": task, "success": success, "duration_s": 10.0, "llm_calls": 5, "prompt_tokens": 1000, "cached_tokens": 500,
            "completion_tokens": 100, "reasoning_tokens": 50, "cost": cost, **extra}


def test_task_means():
    m = task_means([run("a", True, 1.0), run("a", False, 3.0, duration_s=20.0), run("b", True, 2.0)])
    assert list(m) == ["a", "b"]
    assert (m["a"]["runs"], m["a"]["successes"]) == (2, 1) and (m["b"]["runs"], m["b"]["successes"]) == (1, 1)
    assert m["a"]["cost"] == pytest.approx(2.0) and m["a"]["duration_s"] == pytest.approx(15.0)
    assert m["a"]["llm_calls"] == 5 and m["a"]["prompt_tokens"] == 1000 and m["a"]["cached_tokens"] == 500
    assert m["a"]["completion_tokens"] == 100 and m["a"]["reasoning_tokens"] == 50


def test_task_means_is_none_when_any_run_lacks_the_field():
    broken = run("a")
    del broken["prompt_tokens"]
    m = task_means([run("a"), broken, run("a", cost=None)])
    assert m["a"]["prompt_tokens"] is None and m["a"]["cost"] is None
    assert m["a"]["llm_calls"] == 5 and m["a"]["runs"] == 3


def test_compare_md_rows_and_ratio():
    old = [run("a", cost=1.0), run("b", cost=2.0)]   # 费用合计 3.0
    new = [run("a", cost=0.3, duration_s=5.0), run("b", cost=0.6)]   # 费用合计 0.9
    md = render_compare_md(old, new)
    assert HEADER in md
    assert "| a | 1/1 → 1/1 | 1.0000 → 0.3000 | 10.0 → 5.0 | 5.0 → 5.0 | 1000 → 1000 | 100 → 100 |" in md
    assert "| 合计 | 2/2 → 2/2 | 3.0000 → 0.9000 |" in md
    assert "费用比（新/旧）：0.30" in md
    lines = md.splitlines()
    assert lines[lines.index("费用比（新/旧）：0.30") - 1] == ""   # 和表之间空一行，免得被当成表的一行


def test_compare_handles_v1_results():
    old = [{"task": "a", "success": True, "duration_s": 100.0, "llm_calls": 20, "tokens": 5000, "repairs": 0, "stages": []}]
    new = [run("a", cost=0.3)]
    md = render_compare_md(old, new)
    assert "| a | 1/1 → 1/1 | - → 0.3000 | 100.0 → 10.0 | 20.0 → 5.0 | - → 1000 | - → 100 |" in md
    assert "| 合计 | 1/1 → 1/1 | - → 0.3000 |" in md
    assert "费用比（新/旧）：-" in md


def test_compare_task_only_on_one_side():
    md = render_compare_md([run("a")], [run("a"), run("b", cost=0.5)])
    assert "| b | - → 1/1 | - → 0.5000 |" in md


def test_main_writes_the_table(tmp_path):
    old, new, out = tmp_path / "old.json", tmp_path / "new.json", tmp_path / "compare.md"
    old.write_text(json.dumps([run("a", cost=1.0)]), encoding="utf-8")
    new.write_text(json.dumps([run("a", cost=0.25)]), encoding="utf-8")
    printed: list[str] = []
    assert main([str(old), str(new), "--out", str(out)], print_fn=lambda *a, **k: printed.append(" ".join(map(str, a)))) == 0
    text = out.read_text(encoding="utf-8")
    assert "费用比（新/旧）：0.25" in text and text.strip() in "\n".join(printed)


def test_main_reports_a_missing_file(tmp_path):
    printed: list[str] = []
    assert main([str(tmp_path / "no.json"), str(tmp_path / "no2.json")], print_fn=lambda *a, **k: printed.append(" ".join(map(str, a)))) == 1
    assert "no.json" in "\n".join(printed)
