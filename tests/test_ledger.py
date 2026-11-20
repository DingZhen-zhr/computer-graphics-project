"""3.0 计划 4 Task 1：账本、按时段计价、真正的硬上限（假模型、可替换的"现在几点"，不调用真实接口）。"""

from __future__ import annotations

import json
from datetime import datetime, time, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from benchmarks.ledger import BudgetExceeded, Ledger, LedgerError, metered
from benchmarks.metered_run import find_key, run_metered
from benchmarks.run import run_task
from cad_agent.config import Config, ConfigError, Offpeak
from cad_agent.llm.client import LLMError, LLMReply, Pricing
from helpers import Runner, good_result

PEAK = Pricing(input_hit=0.1, input_miss=2.0, output=0.0)       # 一次调用 100 万输入 token：高峰 ¥2
OFF = Pricing(input_hit=0.05, input_miss=1.0, output=0.0)       # 空闲 ¥1
WINDOW = Offpeak("00:30", "08:30", OFF)
USAGE = {"prompt_tokens": 1_000_000, "completion_tokens": 0, "total_tokens": 1_000_000, "cached_tokens": 0}
SECRET = "sk-test-0123456789abcdef"


def cfg(**kw) -> Config:
    return Config(base_url="http://x", model="m", pricing=PEAK, offpeak=WINDOW, **kw)


class Clock:
    def __init__(self, start: datetime) -> None:
        self.t = start

    def __call__(self) -> datetime:
        return self.t


class FakeLLM:
    def __init__(self, fail: bool = False) -> None:
        self.calls, self.fail = 0, fail

    def chat(self, messages, tools, **kw):  # noqa: ANN001, ANN003
        self.calls += 1
        if self.fail:
            raise LLMError("模拟用户那边的模型调用出错了")
        return LLMReply("确认", [], dict(USAGE))


def fake_task(agent_calls: int = 1, sim_calls: int = 1, tick: timedelta = timedelta(0), clock: Clock | None = None):
    """代替 run_task：智能体调用 agent_calls 次、模拟用户调用 sim_calls 次。"""
    def run(task, make_agent, sim_user, out_dir):  # noqa: ANN001
        agent = make_agent(out_dir)
        for _ in range(agent_calls):
            agent.llm.chat([], [])
            if clock is not None:
                clock.t += tick
        for _ in range(sim_calls):
            sim_user.reply("助手说的话", "question")
        return {"task": task["id"], "success": True, "stages": [], "repairs": 0, "duration_s": 1.0, "llm_calls": agent_calls,
                "tokens": 0, "user_turns": 1}
    return run


def factories(sim_fail: bool = False):
    from benchmarks.sim_user import SimUser

    return (lambda root, wrap: SimpleNamespace(llm=wrap(FakeLLM(), "agent")),
            lambda spec, wrap: SimUser(wrap(FakeLLM(fail=sim_fail), "sim_user"), spec))


def go(tmp_path, names, clock, *, cap=20.0, label="round1", run_task_fn=None, allow_peak=False, sim_fail=False, config=None):
    make_agent, make_sim = factories(sim_fail)
    msgs: list[str] = []
    res = run_metered(names, config=config or cfg(), label=label, cap=cap, allow_peak=allow_peak, results_dir=tmp_path / label,
                      make_agent=make_agent, make_sim_user=make_sim, run_task_fn=run_task_fn or fake_task(), print_fn=msgs.append,
                      now=clock, ledger_path=tmp_path / "ledger.json")
    return res, msgs


NIGHT = datetime(2026, 11, 21, 1, 0)


def test_price_at_window_and_midnight_wrap():
    c = cfg()
    assert c.price_at(datetime(2026, 1, 1, 1, 0)) == OFF and c.is_offpeak(datetime(2026, 1, 1, 8, 29))
    assert c.price_at(datetime(2026, 1, 1, 8, 30)) == PEAK and c.price_at(datetime(2026, 1, 1, 12, 0)) == PEAK
    wrap = cfg().__class__(base_url="x", model="m", pricing=PEAK, offpeak=Offpeak("22:00", "06:00", OFF))
    assert wrap.price_at(datetime(2026, 1, 1, 23, 0)) == OFF and wrap.price_at(datetime(2026, 1, 1, 5, 59)) == OFF
    assert wrap.price_at(datetime(2026, 1, 1, 6, 0)) == PEAK
    assert WINDOW.contains(time(0, 30)) and not WINDOW.contains(time(8, 30))


def test_hard_cap_stops_mid_task_and_keeps_results(tmp_path):
    # 用真正的 run_task：第一阶段交付并验收，修改阶段一调用就到上限
    vdir = tmp_path / "v1"
    vdir.mkdir()
    (vdir / "model.py").write_text("# 假的", encoding="utf-8")

    class Agent:
        def __init__(self, llm):  # noqa: ANN001
            self.llm = llm

        def handle_user(self, text):  # noqa: ANN001, ANN201
            self.llm.chat([], [])
            return SimpleNamespace(kind="delivered", version_dir=vdir, repairs=0, llm_calls=1, tokens=0, prompt_tokens=0,
                                   completion_tokens=0, cached_tokens=0, reasoning_tokens=0, cost=1.0)

    def real(task, make_agent, sim_user, out_dir):  # noqa: ANN001
        return run_task(task, make_agent, sim_user, out_dir, run_job=Runner(good_result()))

    make_sim = factories()[1]
    msgs: list[str] = []
    res = run_metered(["battery_box", "flange"], config=cfg(), label="round1", cap=1.5, allow_peak=False, results_dir=tmp_path / "r",
                      make_agent=lambda root, wrap: Agent(wrap(FakeLLM(), "agent")), make_sim_user=make_sim, run_task_fn=real,
                      print_fn=msgs.append, now=Clock(NIGHT), ledger_path=tmp_path / "ledger.json")
    first = res[0]
    assert first["stopped_for_cap"] and first["stages"][0]["stage"] == "after_initial" and first["stages"][0]["delivered"]
    assert first["stages"][-1]["reason"] == "到了花费上限"
    assert res[1] == {"task": "flange", "skipped_for_cap": True}
    saved = json.loads((tmp_path / "r" / "results.json").read_text(encoding="utf-8"))
    assert saved[0]["stopped_for_cap"] and saved[1]["skipped_for_cap"]
    led = Ledger.load(tmp_path / "ledger.json", 1.5)
    assert led.spent == 2.0 and len(led.entries) == 2 and led.remaining() == 0
    assert msgs[-1] == "已花费 ¥2.00，上限 ¥1.50，剩 ¥0.00"


def test_offpeak_window_ends_mid_run(tmp_path):
    clock = Clock(datetime(2026, 11, 21, 8, 29))
    res, msgs = go(tmp_path, ["phone_stand", "flange"], clock, run_task_fn=fake_task(agent_calls=2, sim_calls=0, tick=timedelta(minutes=1), clock=clock))
    led = Ledger.load(tmp_path / "ledger.json", 20)
    assert [e["priced_as"] for e in led.entries] == ["offpeak", "peak"]      # 8:29 空闲价，8:30 起按高峰价
    assert led.spent == 3.0
    assert res[0]["success"] and res[1] == {"task": "flange", "skipped_for_offpeak": True}


def test_missing_offpeak_pricing_refuses(tmp_path):
    res, msgs = go(tmp_path, ["flange"], Clock(NIGHT), config=Config(base_url="x", model="m", pricing=PEAK))
    assert res is None and "[llm.offpeak]" in msgs[0] and "DeepSeek 官网" in msgs[0]
    with pytest.raises(ConfigError):
        Config(base_url="x", model="m").price_at(NIGHT)
    res, msgs = go(tmp_path, ["flange"], Clock(datetime(2026, 11, 21, 12, 0)))
    assert res is None and "00:30–08:30" in msgs[0] and "--allow-peak" in msgs[0]
    res, _ = go(tmp_path, ["flange"], Clock(datetime(2026, 11, 21, 12, 0)), allow_peak=True)
    assert res is not None


def test_corrupt_ledger_refuses(tmp_path):
    (tmp_path / "ledger.json").write_text("{坏掉了", encoding="utf-8")
    res, msgs = go(tmp_path, ["flange"], Clock(NIGHT))
    assert res is None and "读不出来" in msgs[0]
    with pytest.raises(LedgerError):
        Ledger.load(tmp_path / "ledger.json", 20)


def test_sim_user_cost_is_metered(tmp_path):
    go(tmp_path, ["flange"], Clock(NIGHT), run_task_fn=fake_task(agent_calls=1, sim_calls=2))
    led = Ledger.load(tmp_path / "ledger.json", 20)
    assert [e["who"] for e in led.entries] == ["agent", "sim_user", "sim_user"] and led.spent == 3.0


def test_sim_user_error_is_recorded(tmp_path):
    res, _ = go(tmp_path, ["flange", "phone_stand"], Clock(NIGHT), sim_fail=True)
    assert not res[0]["success"] and "LLMError" in res[0]["error"] and "模拟用户" in res[0]["error"]
    assert "error" in res[1]          # 第二个任务照样跑了（模拟用户还是出错）
    led = Ledger.load(tmp_path / "ledger.json", 20)
    assert led.spent == 2.0           # 智能体那两次调用照常记账


def test_labels_share_one_cap(tmp_path):
    go(tmp_path, ["flange"], Clock(NIGHT), label="round1", cap=3)
    res, msgs = go(tmp_path, ["flange", "phone_stand"], Clock(NIGHT), label="round2", cap=3)
    led = Ledger.load(tmp_path / "ledger.json", 3)
    assert led.by_label() == {"round1": 2.0, "round2": 1.0}
    assert res[0]["stopped_for_cap"] and res[1]["skipped_for_cap"]
    res3, msgs3 = go(tmp_path, ["flange"], Clock(NIGHT), label="ab", cap=3)
    assert res3 is None and "到了上限" in msgs3[0]


def test_key_from_keystore_when_no_env(monkeypatch):
    import keyring
    import keyring.backend

    class Mem(keyring.backend.KeyringBackend):
        priority = 1
        store: dict = {}

        def get_password(self, s, u):  # noqa: ANN001, ANN201
            return self.store.get((s, u))

        def set_password(self, s, u, p):  # noqa: ANN001
            self.store[(s, u)] = p

        def delete_password(self, s, u):  # noqa: ANN001
            self.store.pop((s, u), None)

    old = keyring.get_keyring()
    keyring.set_keyring(Mem())
    try:
        monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
        from cad_agent.keystore import set_key

        assert find_key(cfg()) is None
        set_key("deepseek", SECRET)
        assert find_key(cfg()) == SECRET
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-from-env")
        assert find_key(cfg()) == "sk-from-env"
    finally:
        keyring.set_keyring(old)


def test_results_have_no_key(tmp_path, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", SECRET)
    go(tmp_path, ["flange"], Clock(NIGHT))
    for p in Path(tmp_path).rglob("*"):
        if p.is_file():
            assert SECRET not in p.read_text(encoding="utf-8", errors="replace"), p.name
    assert metered and BudgetExceeded   # 保持导入
