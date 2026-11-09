"""模型接口探测（1.1 版 Task 1）：用量字段、缓存、思考控制、程序补的工具调用。

只给开发时探测用，不属于 cad_agent 包。直接用 openai SDK 调接口，不经过 OpenAICompatLLM。
API key 只从环境变量读，不打印、不写进输出；任何要记录的文字都会先把 key 换成 <已隐藏>。

用法：python scripts/probe_llm.py --config config.toml --out docs/llm-probe-output.txt
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import openai

from cad_agent.agent.state import load_system_prompt
from cad_agent.config import load_config
from cad_agent.tool_specs import TOOL_SPECS

QUESTION = "一块 80×60×5 的板，以板中心为原点，四角各开一个孔，孔中心离相邻两边各 10 mm。写出四个孔中心的 (x, y) 坐标，只给答案。"
THINKING_CANDIDATES: list[dict | None] = [
    None,
    {"thinking": {"type": "disabled"}},
    {"thinking": {"type": "enabled"}},
    {"reasoning_effort": "low"},
    {"reasoning_effort": "minimal"},
    {"enable_thinking": False},
]
BUILD_TOOL = [t for t in TOOL_SPECS if t["function"]["name"] == "build"]
AUTO_CALL = {"id": "auto-build-1", "type": "function", "function": {"name": "build", "arguments": "{}"}}
AUTO_PAIR = [
    {"role": "assistant", "content": "", "tool_calls": [AUTO_CALL]},
    {"role": "tool", "tool_call_id": "auto-build-1", "content": '{"passed": true}'},
]
WAIT_S = 3


@dataclass
class Call:
    ok: bool
    error: str = ""
    usage: dict = field(default_factory=dict)
    answer: str = ""
    reasoning_len: int | None = None
    reasoning_text: str = ""
    tool_calls: list[dict] = field(default_factory=list)
    finish: str = ""
    seconds: float = 0.0

    def brief(self) -> dict:
        d: dict[str, Any] = {"ok": self.ok}
        if self.error:
            d["error"] = self.error
        else:
            d |= {"usage": self.usage, "reasoning_content长度": self.reasoning_len, "finish": self.finish,
                  "回答前60字": self.answer[:60], "工具调用": [c["function"]["name"] for c in self.tool_calls],
                  "耗时s": round(self.seconds, 1)}
        return d


class Prober:
    def __init__(self, base_url: str, model: str, temperature: float, key: str) -> None:
        self.model, self.temperature, self._key = model, temperature, key
        self.client = openai.OpenAI(base_url=base_url, api_key=key, max_retries=0, timeout=180)
        self.lines: list[str] = []

    def scrub(self, text: str) -> str:
        return text.replace(self._key, "<已隐藏>")

    def say(self, text: str = "") -> None:
        self.lines.append(self.scrub(text))

    def kv(self, label: str, obj: Any) -> None:
        self.say(f"{label}：" + json.dumps(obj, ensure_ascii=False, default=str))

    def chat(self, messages: list[dict], tools: list[dict] | None = None, extra_body: dict | None = None) -> Call:
        kwargs: dict[str, Any] = {"model": self.model, "messages": messages, "temperature": self.temperature}
        if tools:
            kwargs["tools"] = tools
        if extra_body:
            kwargs["extra_body"] = extra_body
        started = time.monotonic()
        try:
            resp = self.client.chat.completions.create(**kwargs)
        except openai.APIStatusError as e:
            return Call(False, self.scrub(f"状态码 {e.status_code}：{' '.join(str(e).split())[:200]}"))
        except Exception as e:  # 探测脚本：出错记下类型和前 200 个字符
            return Call(False, self.scrub(f"{type(e).__name__}：{' '.join(str(e).split())[:200]}"))
        msg = resp.choices[0].message
        reasoning = getattr(msg, "reasoning_content", None)
        calls = [
            {"id": tc.id, "type": "function", "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
            for tc in (msg.tool_calls or [])
        ]
        usage = resp.usage.model_dump() if resp.usage is not None else {}
        return Call(True, usage=usage, answer=msg.content or "", tool_calls=calls, finish=resp.choices[0].finish_reason or "",
                    reasoning_len=None if reasoning is None else len(reasoning), reasoning_text=reasoning or "",
                    seconds=time.monotonic() - started)


def assistant_message(call: Call) -> dict:
    """和第一版主循环一样的写法：content 加 tool_calls，不带 reasoning_content。"""
    return {"role": "assistant", "content": call.answer, "tool_calls": call.tool_calls}


def exp1_models(p: Prober) -> None:
    p.kv("模型 id", sorted(m.id for m in p.client.models.list()))


def exp2_usage(p: Prober) -> None:
    c = p.chat([{"role": "user", "content": QUESTION}])
    p.kv("调用", c.brief())
    p.say(f"回答全文：{c.answer}")
    p.say(f"message 是否有 reasoning_content 属性：{c.reasoning_len is not None}（长度 {c.reasoning_len}）")


def exp3_cache(p: Prober) -> None:
    system = {"role": "system", "content": load_system_prompt()}
    p.say(f"（系统提示词字符数 {len(system['content'])}；3a、3b、3c 的系统提示词相同，所以后面的组第一次调用也可能命中前面组缓存下来的系统提示词）")
    ping = {"role": "user", "content": "只回答：好"}
    a1 = p.chat([system, ping]); time.sleep(WAIT_S); a2 = p.chat([system, ping])
    p.kv("3a 第一次", a1.brief()); p.kv("3a 第二次", a2.brief())
    tail = [{"role": "user", "content": "只回答：好"}, {"role": "assistant", "content": "好"}, {"role": "user", "content": "再回答一次：好"}]
    b1 = p.chat([system, {"role": "system", "content": "状态：计数 1"}, *tail]); time.sleep(WAIT_S)
    b2 = p.chat([system, {"role": "system", "content": "状态：计数 2"}, *tail])
    p.kv("3b 第一次（第一版布局）", b1.brief()); p.kv("3b 第二次（只改计数）", b2.brief())
    c1 = p.chat([system, *tail]); time.sleep(WAIT_S)
    c2 = p.chat([system, *tail, {"role": "assistant", "content": "好"}, {"role": "user", "content": "第三次：好"}])
    p.kv("3c 第一次（1.1 版布局）", c1.brief()); p.kv("3c 第二次（后面追加）", c2.brief())
    # 3d（计划之外的补充）：3a~3c 追加的内容不足一个缓存块、间隔也只有 3 秒，看不出追加部分能不能被缓存。
    # 这里系统提示词前加一个唯一编号（不和前面的实验共用缓存），每次追加约两三百 token，间隔 10 秒和 30 秒。
    filler = "以下是无关的背景材料，不用理会：" + "这是一段用来凑长度的文字。" * 40
    msgs: list[dict] = [{"role": "system", "content": f"（探测编号 {time.time_ns()}）\n" + system["content"]},
                        {"role": "user", "content": f"{filler}\n只回答：好"}]
    d1 = p.chat(msgs); time.sleep(10)
    msgs += [{"role": "assistant", "content": "好"}, {"role": "user", "content": f"{filler}\n再回答一次：好"}]
    d2 = p.chat(msgs); time.sleep(30)
    msgs += [{"role": "assistant", "content": "好"}, {"role": "user", "content": f"{filler}\n第三次：好"}]
    d3 = p.chat(msgs)
    p.kv("3d 第一次（全新前缀）", d1.brief()); p.kv("3d 第二次（间隔 10 秒，追加约 300 token）", d2.brief())
    p.kv("3d 第三次（再隔 30 秒，再追加约 300 token）", d3.brief())


def exp4_thinking(p: Prober) -> None:
    for extra in THINKING_CANDIDATES:
        for n in (1, 2):
            c = p.chat([{"role": "user", "content": QUESTION}], extra_body=extra)
            p.kv(f"extra_body={json.dumps(extra, ensure_ascii=False)} 第 {n} 次", c.brief())


def exp5_auto_call(p: Prober) -> None:
    base = [{"role": "system", "content": "你是助手。"}, {"role": "user", "content": "检查一下模型。"}]
    c5a = p.chat([*base, *AUTO_PAIR], BUILD_TOOL)
    p.kv("5a 只有程序补的一对", c5a.brief())
    first = p.chat([{"role": "user", "content": "请调用 build 工具"}], BUILD_TOOL)
    p.kv("5b 先让模型真调用 build", first.brief())
    if not first.tool_calls:
        p.say("5b 没做成：模型没有调用 build")
        return
    real = [{"role": "tool", "tool_call_id": tc["id"], "content": '{"passed": true}'} for tc in first.tool_calls]
    c5b = p.chat([{"role": "user", "content": "请调用 build 工具"}, assistant_message(first), *real, *AUTO_PAIR], BUILD_TOOL)
    p.kv("5b 真调用之后再追加程序补的一对", c5b.brief())
    # 5c~5e（计划之外的补充）：5a、5b 被拒绝时，看看是什么条件下被拒绝，以及备用的 user 消息写法能不能用
    p.kv("5c 同 5a，但关掉思考", p.chat([*base, *AUTO_PAIR], BUILD_TOOL, extra_body={"thinking": {"type": "disabled"}}).brief())
    p.kv("5d 同 5a，补的 assistant 消息带空的 reasoning_content",
         p.chat([*base, {**AUTO_PAIR[0], "reasoning_content": ""}, AUTO_PAIR[1]], BUILD_TOOL).brief())
    note = {"role": "user", "content": '【程序自动运行了 build，结果如下】\n{"passed": true}'}
    p.kv("5e 备用写法：真调用之后追加 user 消息",
         p.chat([{"role": "user", "content": "请调用 build 工具"}, assistant_message(first), *real, note], BUILD_TOOL).brief())


def exp6_reasoning_in_input(p: Prober) -> None:
    ask = {"role": "user", "content": "请调用 build 工具"}
    one = p.chat([ask], BUILD_TOOL)
    p.kv("第 1 次", one.brief())
    if not one.tool_calls:
        p.say("没做成：模型没有调用 build")
        return
    real = [{"role": "tool", "tool_call_id": tc["id"], "content": '{"passed": true}'} for tc in one.tool_calls]
    two = p.chat([ask, assistant_message(one), *real], BUILD_TOOL)
    p.kv("第 2 次", two.brief())
    if one.ok and two.ok:
        p1, c1, p2 = one.usage.get("prompt_tokens", 0), one.usage.get("completion_tokens", 0), two.usage.get("prompt_tokens", 0)
        p.say(f"第 2 次 prompt_tokens − 第 1 次 prompt_tokens − 第 1 次 completion_tokens = {p2} − {p1} − {c1} = {p2 - p1 - c1}")
    # 6b（计划之外的补充）：上面只思考了十几个 token，差值分不清。换一个会想久一点的问题，
    # 再多发一次把 reasoning_content 放回去（只在探测里这样做），比较三次的 prompt_tokens。
    ask = {"role": "user", "content": "先心算 (17*23+19)*7，逐步验算两遍，然后调用 build 工具。"}
    one = p.chat([ask], BUILD_TOOL)
    p.kv("6b 第 1 次", one.brief())
    if not one.tool_calls:
        p.say("6b 没做成：模型没有调用 build")
        return
    real = [{"role": "tool", "tool_call_id": tc["id"], "content": '{"passed": true}'} for tc in one.tool_calls]
    two = p.chat([ask, assistant_message(one), *real], BUILD_TOOL)
    three = p.chat([ask, {**assistant_message(one), "reasoning_content": one.reasoning_text}, *real], BUILD_TOOL)
    p.kv("6b 第 2 次（不放回 reasoning_content）", two.brief())
    p.kv("6b 第 2 次（放回 reasoning_content）", three.brief())
    if one.ok and two.ok and three.ok:
        u1, u2, u3 = (x.usage.get("prompt_tokens", 0) for x in (one, two, three))
        r1 = (one.usage.get("completion_tokens_details") or {}).get("reasoning_tokens")
        p.say(f"第 1 次 completion_tokens={one.usage.get('completion_tokens')}，其中 reasoning_tokens={r1}")
        p.say(f"prompt_tokens：第 1 次 {u1}；第 2 次不放回 {u2}（差 {u2 - u1}）；第 2 次放回 {u3}（差 {u3 - u1}）")


EXPERIMENTS: list[tuple[str, Callable[[Prober], None]]] = [
    ("1. 模型列表", exp1_models),
    ("2. 用量字段", exp2_usage),
    ("3. 缓存", exp3_cache),
    ("4. 思考控制", exp4_thinking),
    ("5. 程序补的工具调用", exp5_auto_call),
    ("6. 同一轮里思考是否计入输入", exp6_reasoning_in_input),
]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="探测模型接口")
    ap.add_argument("--config", default="config.toml")
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    cfg = load_config(Path(args.config))
    key = os.environ.get(cfg.api_key_env, "").strip()
    if not key:
        print(f"请先设置环境变量 {cfg.api_key_env}")
        return 1
    p = Prober(cfg.base_url, cfg.model, cfg.temperature, key)
    out = Path(args.out)
    p.say(f"# 模型接口探测输出\nbase_url：{cfg.base_url}\nmodel：{cfg.model}\ntemperature：{cfg.temperature}\n")
    for title, fn in EXPERIMENTS:
        p.say(f"## 实验 {title}")
        try:
            fn(p)
        except Exception as e:  # 单个实验出错不影响后面的
            p.say(f"实验出错：{type(e).__name__}：{' '.join(str(e).split())[:200]}")
        p.say()
        out.write_text("\n".join(p.lines) + "\n", encoding="utf-8")
        print(f"完成实验 {title}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
