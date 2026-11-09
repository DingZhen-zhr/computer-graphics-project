"""模拟用户：扮演手里拿着“隐藏需求”的普通用户，只回答助手问到的内容。

提示词逐字取自 docs/superpowers/plans/2026-11-09-cad-agent-v1-prompts.md 第 5 节，不要改写；
tests/test_benchmarks.py 里有测试会和提示词文档逐字比对。
"""

from __future__ import annotations

from cad_agent.llm.client import LLM

SYSTEM_TEMPLATE = r'''你在扮演一个想做零件的普通用户，正在和一个 CAD 建模助手对话。
你心里的完整需求如下（助手看不到）：
<hidden_spec>

规则：
1. 只回答助手问到的内容，用一两句口语化的中文，不要主动把全部需求说出来。
2. 问到的内容在你的需求里有，就照实回答，数值要准确。
3. 问到的内容你的需求里没有，就回答"你定吧"，或者接受助手给的建议值。
4. 助手请你确认需求单时，逐条对照你的需求：全部一致（你的需求里没提到的、助手自己定的合理值也算一致），只回复"确认"两个字；有不一致的，指出哪一条不对、应该是多少，不要说"确认"。
5. 助手交付模型后，如果你没有别的要求，回复"好的"。
6. 不要编造需求里没有的新要求。'''

USER_TEMPLATE = r'''助手说：
<agent_text>'''

CONFIRM_LINE = r'''（助手正在请你确认需求单）'''

FALLBACK_REPLY = "你定吧"


class SimUser:
    """每次调用都是独立的：系统提示词里有隐藏需求，用户消息只有助手刚说的话（见提示词文档）。"""

    def __init__(self, llm: LLM, hidden_spec: str) -> None:
        self.llm = llm
        self.system = SYSTEM_TEMPLATE.replace("<hidden_spec>", hidden_spec.strip())
        self.calls = 0
        self.tokens = 0

    def reply(self, agent_text: str, kind: str) -> str:
        user = USER_TEMPLATE.replace("<agent_text>", agent_text)
        if kind == "confirm":
            user += "\n" + CONFIRM_LINE
        reply = self.llm.chat([{"role": "system", "content": self.system}, {"role": "user", "content": user}], [])
        self.calls += 1
        self.tokens += int(reply.usage.get("total_tokens", 0) or 0)
        return reply.content.strip() or FALLBACK_REPLY
