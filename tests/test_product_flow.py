"""3.0 计划 2 Task 10：多零件的流程、终检和交付（剧本模型 + 假的 run_job、run_assembly）。"""

from __future__ import annotations

import json

from cad_agent.agent.loop import Agent
from cad_agent.brief import Brief
from cad_agent.config import Config
from cad_agent.gates import Gates
from cad_agent.llm.fake import ScriptedLLM, scripted_call
from cad_agent.notebook import FeatureList
from cad_agent.sandbox.runner_assembly import AssemblyRun
from cad_agent.session import Session
from cad_agent.tools import ToolBox, Workspace
from helpers_staged import StageRunner

GATES_OFF = Gates(mutation_check=False, visual_review=False, cases=False)
I4 = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]
TOP = [["geom.type", "==", "PLANE"], ["geom.normal.z", ">=", 0.99]]
BOT = [["geom.type", "==", "PLANE"], ["geom.normal.z", "<=", -0.99]]
AX = [["geom.type", "==", "CYLINDER"]]
SHELL = "shell = scad.make_box_rsolid(width=w, height=w, depth=body_h, bottom_face_center=(0, 0, 0))"
RIM = "rim = scad.fillet_rsolid(shell, ql.edges(), 1)"
PLATE = "plate = scad.make_box_rsolid(width=w, height=w, depth=lid_t, bottom_face_center=(0, 0, 0))"


def _p(name, value, part=None):
    d = {"name": name, "value": value, "unit": "mm", "source": "user", "note": ""}
    return {**d, "part": part} if part else d


def multi_brief() -> Brief:
    b = Brief()
    b.apply_patch({"part": {"name": "盒子"},
                   "parts": [{"id": "body", "name": "盒体", "material": "abs", "features": ["盒体"]},
                             {"id": "lid", "name": "盖子", "material": "aluminum", "features": ["盖板"]}],
                   "relations": ["盖子用铰链装在盒体后边"],
                   "motions": ["盖子绕后边翻开 0 到 110 度"],
                   "set_params": [_p("w", 40), _p("body_h", 10, "body"), _p("lid_t", 4, "lid")]})
    b.confirmed = True
    return b


class FakeAssembly:
    """代替 run_assembly：返回给定的结果；mode 是 export 时在 out_dir 里写出要交付的文件。"""

    def __init__(self, run: AssemblyRun | None = None) -> None:
        self.run = run or AssemblyRun(
            ok=True, error=None,
            connectors={"body.hinge": {"selected": 1, "type": "CYLINDER", "center": [0, 20, 10], "direction": [1, 0, 0]},
                        "lid.hinge": {"selected": 1, "type": "CYLINDER", "center": [0, 20, 0], "direction": [1, 0, 0]}},
            rest={"body": I4, "lid": [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 10, 0, 0, 0, 1]}, overlaps=[], measures={},
            samples={"open": [{"value": v, "poses": {"body": I4, "lid": I4}, "hits": [], "error": None, "joints": {"open": v}}
                              for v in (0, 55, 110)]})
        self.calls: list[dict] = []

    def __call__(self, ws, **kw):  # noqa: ANN001
        self.calls.append(kw)
        if kw.get("mode") == "export":
            out = kw["out_dir"]
            names = ["assembly.py", "product.step", "view.png"] + [f"parts/{p}/model.{e}" for p in ("body", "lid") for e in ("step", "stl")]
            for n in names:
                (out / n).parent.mkdir(parents=True, exist_ok=True)
                (out / n).write_bytes(b"x")
        return self.run


def plan(*titles):
    return ("set_plan", {"stages": [{"title": t, "done_when": f"有{t}"} for t in titles]})


def checks(stage, cid, axis, expected):
    return ("set_checks", {"stage": stage, "checks": [{"id": cid, "type": "bbox", "axis": axis, "expected": expected}]})


def up(slug, role, code):
    return ("upsert_feature", {"slug": slug, "role": role, "code": code})


BUILD = ("build", {})
BODY = [scripted_call(*plan("外形", "边角处理")),
        scripted_call(*checks("s1", "body-w", "x", "w"), "", up("shell", "build", SHELL), BUILD),
        scripted_call(*checks("s2", "body-h", "z", "body_h"), "", up("rim", "modify", RIM), BUILD)]
LID_CHECKS = ("set_checks", {"stage": "s1", "checks": [{"id": "lid-t", "type": "bbox", "axis": "z", "expected": "lid_t"},
                                                      {"id": "lid-w", "type": "bbox", "axis": "x", "expected": "w"}]})
LID = [scripted_call(*plan("盖板")), scripted_call(*LID_CHECKS, "", up("plate", "build", PLATE), BUILD)]
CONNECT = scripted_call("set_connectors", {"part": "body", "connectors": [{"name": "hinge", "kind": "faces", "where": AX}]}, "",
                        ("set_connectors", {"part": "lid", "connectors": [{"name": "hinge", "kind": "faces", "where": AX}]}),
                        ("set_assembly", {"ground": "body", "mates": [{"id": "lid_on", "fixed": "body.hinge", "moving": "lid.hinge", "align": "same"}],
                                          "joints": [{"id": "open", "mate": "lid_on", "type": "revolute", "range": [0, 110], "label": "盖子翻开"}]}),
                        ("build_assembly", {}))


def make_agent(tmp_path, replies, gates=GATES_OFF, assembly=None, **config):
    ws = Workspace(multi_brief(), FeatureList(), [])
    box = ToolBox(ws, run_job=StageRunner(), gates=gates)
    box.run_assembly = assembly or FakeAssembly()
    llm = ScriptedLLM(replies)
    session = Session(tmp_path / "sessions")
    agent = Agent(llm, box, session, Config(base_url="http://x", model="m", **config))
    return agent, ws, llm, box, session


def test_two_part_flow_delivers(tmp_path):
    agent, ws, llm, box, session = make_agent(tmp_path, BODY + LID + [CONNECT])
    turn = agent.handle_user("开始")
    assert turn.kind == "delivered", turn.text
    assert turn.text.startswith("做好了，2 个零件，存成第 1 版。")
    assert "盖子翻开：从 0 到 110°，取了 3 个位置，都没有碰到别的零件。" in turn.text
    v = session.dir / "versions" / "v1"
    for name in ("brief.json", "assembly.json", "assembly.py", "product.step", "view.png", "motion.json", "checks.json", "gate.json",
                 "changes.md", "parts/body/model.py", "parts/body/model.step", "parts/body/model.stl", "parts/body/checks.json",
                 "parts/lid/model.py", "parts/lid/model.stl", "parts/lid/checks.json", "parts/lid/connectors.json"):
        assert (v / name).is_file(), name
    motion = json.loads((v / "motion.json").read_text(encoding="utf-8"))
    assert set(motion) == {"parts", "rest", "explode", "joints"}
    assert motion["parts"]["lid"] == {"name": "盖子", "material": "aluminum", "color": "#C9CDD3", "finish": "metal", "stl": "parts/lid/model.stl"}
    assert len(motion["rest"]["lid"]) == 16 and motion["explode"]["body"] == [0, 0, 0]
    j = motion["joints"][0]
    assert (j["id"], j["label"], j["type"], j["unit"], j["lo"], j["hi"]) == ("open", "盖子翻开", "revolute", "deg", 0, 110)
    assert set(j["samples"][0]) == {"value", "poses", "hits"}
    allc = json.loads((v / "checks.json").read_text(encoding="utf-8"))
    assert {c["part"] for c in allc} == {"body", "lid", "assembly"}
    assert 'id = "lid"' in (v / "parts/lid/model.py").read_text(encoding="utf-8")
    assert all(st.done for st in ws.parts.values()) and ws.assembly_passed


def test_finished_part_is_folded(tmp_path):
    agent, ws, llm, *_ = make_agent(tmp_path, BODY + LID + [CONNECT])
    agent.handle_user("开始")
    lid_call = llm.calls[3]      # 第 4 次调用模型：body 做完之后，给 lid 写计划
    folded = [m for m in lid_call if m["role"] == "user" and m["content"].startswith("【零件已做完（程序生成）】body")]
    assert len(folded) == 1
    text = folded[0]["content"]
    assert text.startswith("【零件已做完（程序生成）】body 盒体\n步骤：外形、边角处理\n检查：")
    assert text.endswith("现在做零件 lid 盖子。先用 set_plan 把它拆成几步。")
    assert not any(m["role"] == "tool" for m in lid_call)
    last = llm.calls[5]
    assert any(m["role"] == "user" and m["content"].endswith("最后 build_assembly。") for m in last)


def test_limits_scale_with_parts(tmp_path):
    agent, *_ = make_agent(tmp_path, [], max_tool_calls_total=50)
    assert agent.product.total_cap(50) == 50 * 2 + 100
    single, *_ = make_agent(tmp_path, [])
    single.ws.brief.parts = []
    assert single.product.total_cap(50) == 50


def test_editing_finished_part_invalidates_assembly(tmp_path):
    agent, ws, llm, box, session = make_agent(tmp_path, BODY + LID + [CONNECT])
    assert agent.handle_user("开始").kind == "delivered"
    again = [scripted_call("select_part", {"part": "body"}),
             scripted_call(*up("shell", "build", SHELL.replace("depth=body_h", "depth=body_h + 1"))),
             scripted_call("build", {}), scripted_call("build_assembly", {})]
    llm.replies.extend(again)
    turn = agent.handle_user("第一个零件高一点")
    assert box.run_assembly.calls[-1]["mode"] == "export"
    assert turn.kind == "delivered" and (session.dir / "versions" / "v2").is_dir()
    # 改的时候：零件变回没做完，装配结果作废
    agent2, ws2, llm2, box2, _ = make_agent(tmp_path, BODY + LID + [CONNECT])
    agent2.handle_user("开始")
    box2.call("select_part", {"part": "body"})
    assert ws2.parts["body"].done
    out = json.loads(box2.call("upsert_feature", {"slug": "shell", "role": "build", "code": SHELL}).content)
    agent2.product.after_call("upsert_feature", "error" not in out)
    assert not ws2.parts["body"].done and not ws2.assembly_passed and ws2.last_assembly is None
    assert "还有零件没做完：body" in box2.call("build_assembly", {}).content


def test_product_gate_rebuilds_dependent_parts(tmp_path):
    from cad_agent.product.gate import run_product_gate

    agent, ws, llm, box, session = make_agent(tmp_path, BODY + LID + [CONNECT])
    assert agent.handle_user("开始").kind == "delivered"
    box.gates = Gates(mutation_check=True, visual_review=False, cases=False)
    runner = StageRunner()
    box.run_job = runner
    asm = FakeAssembly()
    box.run_assembly = asm
    gate = run_product_gate(box, workers=1)
    by = {m.param: m for m in gate.mutation}
    assert set(by) == {"w", "body_h", "lid_t"}
    calls = [(c["slug"], c["param_names"]) for c in runner.calls]
    # w 是两个零件都用的产品参数：两个零件都重做；lid_t 只属于 lid：只重做 lid；每次都重做装配
    # 假的运行器让检查全过，所以每个参数试第一个数就判为"没管住"
    assert [s for s, _ in calls] == ["rim", "plate", "rim", "plate"]
    assert [c["values"] for c in asm.calls] == [{"w": 48.0}, {"body_h": 12.0}, {"lid_t": 4.8}]
    assert all(c["check_values"] == {"w": 40.0, "body_h": 10.0, "lid_t": 4.0} for c in runner.calls)
    assert gate.unconstrained == ["w", "body_h", "lid_t"] and not gate.passed


def test_single_part_flow_unchanged(tmp_path):
    from test_staged_loop import PLAN, S1, S2, make_staged_agent

    agent, ws, llm, runner, session = make_staged_agent(tmp_path, [PLAN, S1, S2])
    turn = agent.handle_user("开始建模吧")
    assert turn.kind == "delivered" and turn.llm_calls == 3
    assert ws.parts == {} and ws.active is None
    assert (session.dir / "versions" / "v1" / "model.step").is_file()
    assert not (session.dir / "assembly.json").exists()


def test_range_only_param_is_not_mutated(tmp_path):
    """偏离 D33：只在关节范围里的参数（盖子最多翻多少度）不扰动，算作管住了；也不算缺检查。"""
    from cad_agent.product.gate import product_coverage_gaps, range_only, run_product_gate

    agent, ws, llm, box, session = make_agent(tmp_path, BODY + LID + [CONNECT])
    assert agent.handle_user("开始").kind == "delivered"
    ws.brief.apply_patch({"set_params": [_p("lid_max", 110)]})
    box.call("set_assembly", {"ground": "body", "mates": [{"id": "lid_on", "fixed": "body.hinge", "moving": "lid.hinge", "align": "same"}],
                              "joints": [{"id": "open", "mate": "lid_on", "type": "revolute", "range": [0, "lid_max"], "label": "盖子翻开"}]})
    assert range_only(ws) == {"lid_max"} and "lid_max" not in product_coverage_gaps(ws)
    box.gates = Gates(mutation_check=True, visual_review=False, cases=False)
    asm = FakeAssembly()
    box.run_assembly = asm
    gate = run_product_gate(box, workers=1)
    m = next(x for x in gate.mutation if x.param == "lid_max")
    assert m.verdict == "constrained" and m.caught_by == ("motion_range",) and m.tried == ()
    assert all("lid_max" not in c["values"] for c in asm.calls)
