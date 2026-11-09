import json
import sys
from pathlib import Path

import pytest

import cad_agent.cli as cli
from cad_agent.agent.loop import AgentTurn
from cad_agent.brief import Brief, Param
from cad_agent.checks.spec import CheckResult
from cad_agent.session import Session

EXAMPLE = Path(__file__).resolve().parent.parent / "config.example.toml"
HINT = "回复「确认」开始建模，或直接说要改什么"


class StubAgent:
    def __init__(self, *turns: AgentTurn) -> None:
        self.turns = list(turns)
        self.inputs: list[str] = []

    def handle_user(self, text: str) -> AgentTurn:
        self.inputs.append(text)
        return self.turns.pop(0)


class FakeEditor:
    """代替 subprocess.Popen：记录命令，记录有没有被结束。"""

    started: list["FakeEditor"] = []

    def __init__(self, cmd, **kw):
        self.cmd, self.terminated = cmd, False
        FakeEditor.started.append(self)

    def poll(self):
        return None if not self.terminated else 0

    def terminate(self):
        self.terminated = True

    def wait(self, timeout=None):
        return 0


def drive(monkeypatch, tmp_path, inputs, *turns, agent=None):
    """跑一遍命令行：返回 (返回码, 输出文本, 假智能体, 会话)。"""
    stub = agent or StubAgent(*turns)
    session = Session(tmp_path / "sessions")
    monkeypatch.setattr(cli, "build_agent", lambda config: (stub, session))
    feed = iter(inputs)

    def input_fn(prompt: str = "") -> str:
        try:
            return next(feed)
        except StopIteration:
            raise EOFError from None

    out: list[str] = []
    code = cli.main(["--config", str(EXAMPLE)], input_fn=input_fn, print_fn=lambda *a, **k: out.append(" ".join(map(str, a))))
    return code, "\n".join(out), stub, session


def add_version(session: Session, tmp_path: Path, tilt: float, changes: list[str]) -> Path:
    step, png = tmp_path / "x.step", tmp_path / "x.png"
    step.write_bytes(b"S")
    png.write_bytes(b"P")
    brief = Brief(part_name="手机支架", params=[Param("tilt_deg", tilt, "deg", "user"), Param("phone_w", 78, "mm", "user")], confirmed=True)
    return session.new_version(notebook_text="# m\n", brief=brief, check_results=[CheckResult("valid", "valid", True, None, None, None, "")],
                               changes=changes, step_src=step, png_src=png)


def test_quit_returns_0_and_logs_versions(monkeypatch, tmp_path):
    code, out, agent, session = drive(monkeypatch, tmp_path, ["/quit"])
    assert code == 0 and agent.inputs == []
    assert "Python" in out and "simplecadapi" in out and "deepseek-chat" in out and str(session.dir) in out
    startup = [json.loads(line) for line in (session.dir / "log.jsonl").read_text(encoding="utf-8").splitlines()][0]
    assert startup["kind"] == "startup" and startup["model"] == "deepseek-chat" and startup["simplecadapi"] == "2.2.7"
    assert startup["python"].startswith("3.")
    assert "key" not in json.dumps(startup).lower().replace("api_key_env", "")


def test_eof_exits_cleanly(monkeypatch, tmp_path):
    code, out, *_ = drive(monkeypatch, tmp_path, [])
    assert code == 0


def test_missing_key_returns_1(monkeypatch, tmp_path):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    cfg = tmp_path / "c.toml"
    cfg.write_text(f'[llm]\nbase_url = "http://x"\nmodel = "m"\n[agent]\nsessions_dir = "{(tmp_path / "s").as_posix()}"\n', encoding="utf-8")
    out: list[str] = []
    code = cli.main(["--config", str(cfg)], input_fn=lambda p="": "/quit", print_fn=lambda *a, **k: out.append(" ".join(map(str, a))))
    assert code == 1 and "请先设置环境变量 DEEPSEEK_API_KEY" in "\n".join(out)
    assert not (tmp_path / "s").exists()  # 没有 key 就不创建会话目录


def test_missing_config_returns_1(tmp_path):
    out: list[str] = []
    code = cli.main(["--config", str(tmp_path / "nope.toml")], input_fn=lambda p="": "/quit", print_fn=lambda *a, **k: out.append(" ".join(map(str, a))))
    assert code == 1 and "找不到配置文件" in "\n".join(out)


def test_message_goes_to_agent_and_reply_is_printed(monkeypatch, tmp_path):
    code, out, agent, _ = drive(monkeypatch, tmp_path, ["", "  ", "做一个支架", "/quit"], AgentTurn("reply", "好的，先问你几个问题"))
    assert code == 0 and agent.inputs == ["做一个支架"] and "好的，先问你几个问题" in out and HINT not in out


def test_confirm_hint_printed(monkeypatch, tmp_path):
    _, out, *_ = drive(monkeypatch, tmp_path, ["做一个支架", "/quit"], AgentTurn("confirm", "【需求单】\n零件：手机支架"))
    assert "【需求单】" in out and HINT in out
    assert out.index("【需求单】") < out.index(HINT)


def test_question_failed_and_delivered_turns_are_printed(monkeypatch, tmp_path):
    turns = [AgentTurn("question", "1. 手机多厚？"), AgentTurn("failed", "建模已经连续没通过 3 次"),
             AgentTurn("delivered", "已交付 v1。", version_dir=tmp_path, llm_calls=4, tokens=1234)]
    _, out, *_ = drive(monkeypatch, tmp_path, ["a", "b", "c", "/quit"], *turns)
    assert "1. 手机多厚？" in out and "建模已经连续没通过 3 次" in out and "已交付 v1。" in out
    assert HINT not in out and "1234" in out  # 交付后顺带显示模型调用次数和 token 数


def test_turn_line_with_cost(monkeypatch, tmp_path):
    turn = AgentTurn("reply", "好", llm_calls=2, tokens=300, prompt_tokens=250, cached_tokens=200, completion_tokens=50,
                     reasoning_tokens=40, cost=0.0123)
    _, out, *_ = drive(monkeypatch, tmp_path, ["a", "/quit"], turn)
    assert "（本轮模型调用 2 次，共 300 token：输入 250（命中缓存 200），输出 50（其中思考 40），约 ¥0.0123）" in out


def test_turn_line_without_cost(monkeypatch, tmp_path):
    turn = AgentTurn("reply", "好", llm_calls=1, tokens=300, prompt_tokens=250, cached_tokens=0, completion_tokens=50, reasoning_tokens=0)
    _, out, *_ = drive(monkeypatch, tmp_path, ["a", "/quit"], turn)
    assert "（本轮模型调用 1 次，共 300 token：输入 250（命中缓存 0），输出 50（其中思考 0））" in out
    assert "¥" not in out


def test_no_turn_line_without_model_calls(monkeypatch, tmp_path):
    _, out, *_ = drive(monkeypatch, tmp_path, ["a", "/quit"], AgentTurn("reply", "好"))
    assert "本轮模型调用" not in out


def test_diff_needs_two_versions(monkeypatch, tmp_path):
    session_inputs = ["/diff", "/quit"]
    _, out, *_ = drive(monkeypatch, tmp_path, session_inputs)
    assert "还没有可对比的两个版本" in out


def test_diff_with_one_version_still_needs_two(monkeypatch, tmp_path):
    agent = StubAgent()
    session = Session(tmp_path / "sessions")
    add_version(session, tmp_path, 65, [])
    monkeypatch.setattr(cli, "build_agent", lambda config: (agent, session))
    out: list[str] = []
    feed = iter(["/diff", "/quit"])
    cli.main(["--config", str(EXAMPLE)], input_fn=lambda p="": next(feed), print_fn=lambda *a, **k: out.append(" ".join(map(str, a))))
    assert "还没有可对比的两个版本" in "\n".join(out)


def drive_with_versions(monkeypatch, tmp_path, inputs):
    agent = StubAgent()
    session = Session(tmp_path / "sessions")
    v1 = add_version(session, tmp_path, 65, ["tilt_deg: 新增 65 deg（用户给的）"])
    v2 = add_version(session, tmp_path, 70, ["tilt_deg: 65 → 70 (deg)"])
    monkeypatch.setattr(cli, "build_agent", lambda config: (agent, session))
    feed = iter(inputs)
    out: list[str] = []
    code = cli.main(["--config", str(EXAMPLE)], input_fn=lambda p="": next(feed), print_fn=lambda *a, **k: out.append(" ".join(map(str, a))))
    return code, "\n".join(out), session, v1, v2


def test_diff_shows_param_changes_and_screenshots(monkeypatch, tmp_path):
    _, out, _, v1, v2 = drive_with_versions(monkeypatch, tmp_path, ["/diff", "/quit"])
    assert "v1" in out and "v2" in out and "tilt_deg: 65 → 70 (deg)" in out
    assert "phone_w" not in out.split("参数变化")[1].split("截图")[0]  # 没变的参数不列
    assert str(v1 / "view.png") in out and str(v2 / "view.png") in out


def test_versions_lists(monkeypatch, tmp_path):
    _, out, _, v1, v2 = drive_with_versions(monkeypatch, tmp_path, ["/versions", "/quit"])
    assert "v1" in out and "v2" in out and str(v2) in out and "tilt_deg: 65 → 70 (deg)" in out


def test_versions_empty(monkeypatch, tmp_path):
    _, out, *_ = drive(monkeypatch, tmp_path, ["/versions", "/quit"])
    assert "还没有交付过版本" in out


def test_diff_between_versions_detects_added_and_removed_params():
    old = Brief(params=[Param("a", 1, "mm", "user"), Param("b", 2, "mm", "user")])
    new = Brief(params=[Param("b", 3, "mm", "user"), Param("c", 4, "deg", "suggested")])
    assert cli.diff_briefs(old, new) == ["a: 已删除", "b: 2 → 3 (mm)", "c: 新增 4 deg"]
    assert cli.diff_briefs(new, new) == []


def test_view_starts_sca_edit_on_session_dir(monkeypatch, tmp_path):
    FakeEditor.started.clear()
    monkeypatch.setattr(cli.subprocess, "Popen", FakeEditor)
    monkeypatch.setattr(cli, "find_sca", lambda: "C:/fake/sca.exe")
    _, out, _, session = drive(monkeypatch, tmp_path, ["/view", "/quit"])
    assert [e.cmd for e in FakeEditor.started] == [["C:/fake/sca.exe", "edit", str(session.dir)]]
    assert FakeEditor.started[0].terminated  # 退出时一并结束编辑器
    assert "编辑器" in out


def test_view_without_sca_prints_hint(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "find_sca", lambda: None)
    _, out, *_ = drive(monkeypatch, tmp_path, ["/view", "/quit"])
    assert "找不到 sca" in out


def test_find_sca_prefers_the_venv_next_to_python():
    found = cli.find_sca()
    assert found is not None and Path(found).parent == Path(sys.executable).parent


def test_unknown_command_and_help(monkeypatch, tmp_path):
    _, out, agent, _ = drive(monkeypatch, tmp_path, ["/nope", "/help", "/quit"])
    assert "不认识的命令 /nope" in out and agent.inputs == []
    for cmd in ("/view", "/diff", "/versions", "/quit"):
        assert cmd in out


def test_ctrl_c_exits_cleanly(monkeypatch, tmp_path):
    session = Session(tmp_path / "sessions")
    monkeypatch.setattr(cli, "build_agent", lambda config: (StubAgent(), session))

    def interrupt(prompt: str = "") -> str:
        raise KeyboardInterrupt

    out: list[str] = []
    assert cli.main(["--config", str(EXAMPLE)], input_fn=interrupt, print_fn=lambda *a, **k: out.append(" ".join(map(str, a)))) == 0


def test_build_agent_wires_everything(monkeypatch, tmp_path):
    from cad_agent.config import load_config

    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key-not-real")
    config = load_config(EXAMPLE)
    from dataclasses import replace

    agent, session = cli.build_agent(replace(config, sessions_dir=tmp_path / "s"))
    assert session.dir.parent == tmp_path / "s" and agent.toolbox.max_build_failures == 3
    assert agent.toolbox.secret_names == ("DEEPSEEK_API_KEY",) and agent.toolbox.timeout_s == 60
    assert "test-key-not-real" not in repr(agent.toolbox.secret_names)
