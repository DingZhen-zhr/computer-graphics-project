"""3.0 计划 2 Task 16：多零件走查剧本 + 真实沙盒，从一句话需求走到交付，再改一次。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cad_agent.agent.loop import Agent
from cad_agent.brief import Brief
from cad_agent.config import Config
from cad_agent.gates import Gates
from cad_agent.llm.fake import ScriptedLLM, load_script
from cad_agent.notebook import FeatureList
from cad_agent.sandbox.execute import run_job
from cad_agent.session import Session
from cad_agent.tools import ToolBox, Workspace

pytestmark = pytest.mark.sca
SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "demo_script_multi.json"


def test_script_is_up_to_date():
    import sys

    sys.path.insert(0, str(SCRIPT.parent))
    from gen_demo_multi import build

    assert json.loads(SCRIPT.read_text(encoding="utf-8")) == json.loads(json.dumps(build(), ensure_ascii=False))


def test_toolbox_walkthrough(tmp_path):
    box = ToolBox(Workspace(Brief(), FeatureList(), []), run_job=run_job, gates=Gates(visual_review=False, cases=False), timeout_s=120)
    session = Session(tmp_path / "sessions")
    agent = Agent(ScriptedLLM(load_script(SCRIPT)), box, session, Config(base_url="http://x", model="m", motion_samples=12, run_timeout_s=120))
    kinds = [agent.handle_user(t).kind for t in ("做一个带铰链盖的工具盒", "铰链轴离后壁 5 毫米，盖子最多翻开 110 度", "确认")]
    assert kinds == ["question", "confirm", "delivered"], kinds
    turn = agent.handle_user("盖子最多翻到 95 度")
    assert turn.kind == "delivered", turn.text
    v1, v2 = session.dir / "versions" / "v1", session.dir / "versions" / "v2"
    for name in ("product.step", "view.png", "assembly.py", "motion.json", "checks.json", "gate.json",
                 "parts/body/model.step", "parts/lid/model.stl", "parts/pin/model.py", "parts/handle/checks.json"):
        assert (v1 / name).is_file(), name
    m1, m2 = (json.loads((v / "motion.json").read_text(encoding="utf-8")) for v in (v1, v2))
    assert m1["joints"][0]["hi"] == 110 and m2["joints"][0]["hi"] == 95
    assert all(not s["hits"] for m in (m1, m2) for j in m["joints"] for s in j["samples"])
    assert {p: m1["parts"][p]["color"] for p in m1["parts"]} == {"body": "#3A3F47", "lid": "#4767E8", "pin": "#B8BDC4", "handle": "#1E1F22"}
    assert "本版变化：lid_max: 110 → 95 (deg)" in turn.text
