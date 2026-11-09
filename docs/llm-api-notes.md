# 模型接口实测笔记（DeepSeek，OpenAI 兼容接口）

> 本文件是第 1.1 版 Task 2、6、7、11 用到模型接口时的依据。所有数字来自 `scripts/probe_llm.py` 的一次完整运行，
> 原始输出在 `docs/llm-probe-output.txt`（Windows 11、Python 3.13.7、openai 3.46.0、`https://api.deepseek.com`、`deepseek-flash`、temperature 0.2、2026-11-09）。
> 大模型的回答每次略有不同，但各结论依据的是字段名、接口是否接受、数字的量级，不依赖某一次的具体数值。
> 笔记里没有的写法，先写探测代码跑通，再补进这里，然后才能用。

## 1. 可用模型

`client.models.list()` 返回两个：`deepseek-flash`、`deepseek-v4-pro`。

## 2. 用量字段（原样）

`resp.usage.model_dump()`，固定问题、默认参数（思考是开着的）：

```json
{
 "completion_tokens": 177,
 "prompt_tokens": 80,
 "total_tokens": 257,
 "completion_tokens_details": {"accepted_prediction_tokens": null, "audio_tokens": null, "reasoning_tokens": 152, "rejected_prediction_tokens": null, "text_tokens": null},
 "prompt_tokens_details": {"audio_tokens": null, "cache_write_tokens": null, "cached_tokens": 0, "image_tokens": null, "text_tokens": null},
 "prompt_cache_hit_tokens": 0,
 "prompt_cache_miss_tokens": 80
}
```

- `prompt_cache_hit_tokens`（DeepSeek 自己的字段）和 `prompt_tokens_details.cached_tokens`（OpenAI 风格）**同时存在，数相等**（实验 3 里每次都相等）。`prompt_cache_miss_tokens` = `prompt_tokens` − 命中数。
- `completion_tokens_details.reasoning_tokens` 是思考 token，**包含在 `completion_tokens` 里**（199 个输出里有 174 个是思考）。
- **关掉思考时 `completion_tokens_details` 整个是 `null`**（不是各项为 0），所以取 `reasoning_tokens` 时要先判断它是不是 `None`，没有就记 0。`prompt_tokens_details` 在测到的每次调用里都在。
- message 上有 `reasoning_content`（思考原文，约 3 个字符一个 token）；关掉思考时没有这个属性。
- 这些多出来的字段不在 openai 官方的类型定义里，SDK 把它们当额外字段保留，`getattr(usage, "prompt_cache_hit_tokens")` 能读到（探测脚本里用 `model_dump()` 见到的）。

## 3. 缓存实测

系统提示词全文（`load_system_prompt()`，9829 个字符）约 4600 个 token。命中数都是 **64 的整数倍**（128、4608、4992、5376），缓存按 64 个 token 一块。

| 实验 | 第一次：prompt / 命中 | 第二次：prompt / 命中 | 说明 |
|---|---|---|---|
| 3a 完全相同，连发两次 | 4787 / 4608 | 4787 / 4608 | 第一次就命中 4608，是因为前一次探测运行已经缓存了这段系统提示词 |
| 3b 第一版布局（系统提示词 + 状态消息 + 对话），只改状态里的计数 | 4803 / 4608 | 4803 / 4608 | 命中的只有最前面的系统提示词 |
| 3c 第 1.1 版布局，第二次在后面追加两条消息 | 4797 / 4608 | 4805 / 4608 | 追加的只有几十个 token，不够一块，看不出差别 |
| 3d（补充）前缀全新；每次追加约 300 token | 5087 / 0 | 间隔 10 秒：5385 / **4992** | 第一次的内容被缓存了 |
| 3d 第三次（再隔 30 秒，再追加约 300 token） | | 5681 / **5376** | 第二次的全部内容（5385，取整到 64 的倍数是 5376）都命中了 |

3d 是计划之外加的补充实验（3a~3c 追加的内容太少、间隔只有 3 秒，回答不了"追加的历史能不能被缓存"）。结论：
- 追加在后面的对话内容**会被缓存**，下一次调用时命中；这就是第 1.1 版"轮内只追加、开头不变"的收益来源。
- 间隔 3 秒（3c）没看到追加部分被缓存，间隔 10 秒（3d）就看到了，所以缓存不是即时生效的。主循环里两次调用之间隔着模型生成的时间，一般远超 10 秒。
- 3b 的第一版布局没有单独测出"大段历史被状态消息中间改动而失效"：它只测到命中停在系统提示词为止（4608），后面是按前缀缓存的原理推出来的，不是实测。

## 4. 思考控制参数实测

固定问题（四角孔坐标），每组 2 次，都通过 `extra_body` 传。**所有候选都被接口接受（状态码 200），没有一个报错；不认识的参数被悄悄忽略**，所以"被接受"不等于"有效"。

| extra_body | 输出 token（两次） | 思考 token（两次） | 平均思考 / 默认 | 回答 |
|---|---|---|---|---|
| 默认（不传） | 199、137 | 174、112 | （基准：平均 143） | 有 |
| `{"thinking": {"type": "disabled"}}` | 24、24 | 取不到（`completion_tokens_details` 为 null） | 24 ÷ 143 = **17%**（取不到思考数，用输出 token 代替） | 有 |
| `{"thinking": {"type": "enabled"}}` | 146、244 | 121、219 | 119%（和默认一样） | 有 |
| `{"reasoning_effort": "low"}` | 122、168 | 97、143 | 84% | 有 |
| `{"reasoning_effort": "minimal"}` | 166、182 | 141、157 | 104% | 有 |
| `{"enable_thinking": false}` | 131、137 | 106、116 | 78% | 有 |

- 只有 `{"thinking": {"type": "disabled"}}` 真正关掉了思考：没有 `reasoning_content`，输出只剩答案本身，回答正确。
- `reasoning_effort`、`enable_thinking` 虽然被接受，但思考量和默认差不多（差别在两次采样的波动范围内），当作无效。
- 这是一个很简单的问题。关掉思考对"澄清、整理需求单"这类任务的质量有没有影响，要靠 Task 11 的 E2 实验回答。

## 5. 程序补的工具调用

工具只给 build。"程序补的一对"指：一条 content 为空、`tool_calls` 里只有 id 为 `auto-build-1` 的 build 调用的 assistant 消息，加一条对应的 tool 消息（内容 `{"passed": true}`）。

| 实验 | 做法 | 结果 |
|---|---|---|
| 5a | [system, user, 程序补的一对] | **400**：`The reasoning_content in the thinking mode must be passed back to the API.` |
| 5b | 模型真调用一次 build，按第一版主循环的写法放回（不带 reasoning_content），再追加程序补的一对 | **400**，同样的信息（真调用的那一对本身没问题，见实验 6，是后面补的那一对被拒） |
| 5c（补充） | 同 5a，但 `extra_body={"thinking": {"type": "disabled"}}` | 接受，回答正常 |
| 5d（补充） | 同 5a，但补的 assistant 消息多带一个空的 `reasoning_content: ""` | 接受，回答正常 |
| 5e（补充） | 模型真调用一次 build 并放回结果，再追加一条 user 消息 `【程序自动运行了 build，结果如下】\n{"passed": true}` | 接受，回答正常 |

- 开着思考时，**服务端要求带工具调用的 assistant 消息有 `reasoning_content`**。模型自己生成的调用没问题（第一版一直是这样放回去的，也能通过，见实验 6），但程序编出来的调用没有对应的思考，会被拒。
- 5d 说明加一个空的 `reasoning_content` 能绕过，但这是厂商专用的字段，计划规定代码里不写厂商专用的参数名，所以不用。5c 的关思考只在 E2 的澄清阶段才会开，而程序代按 build 发生在建模阶段（思考开着），也用不上。
- 5e 说明备用写法（追加 user 消息）可用。

## 6. 同一轮里的思考是否计入输入

按第一版主循环的写法，第 2 次调用只放回 assistant 消息的 content 和 tool_calls，**不带** `reasoning_content`，然后加 tool 消息。

| 实验 | 第 1 次：输出（其中思考） | 第 1 次 prompt | 第 2 次 prompt | 第 2 次 − 第 1 次 − 第 1 次输出 |
|---|---|---|---|---|
| 6（计划里的，要求"请调用 build 工具"） | 34（13） | 330 | 380 | 380 − 330 − 34 = **16** |
| 6b（补充，让模型先心算验算再调用 build） | 232（76） | 349 | 597（不带 reasoning_content）| 597 − 349 − 232 = **16** |
| 6b 对照：把 `reasoning_content` 原样放回 | | | 597（同样） | 同上 |

- 两次实验里，下一次的 prompt 比上一次多出的 token 数，都**恰好等于上一次的全部输出（含思考）再加 16**。如果思考不计入，两个实验的"16"就对不上（思考分别是 13 和 76）。
- 放回和不放回 `reasoning_content`，第 2 次的 `prompt_tokens` 完全一样（都是 597）。这说明服务端会自己补上这一轮里的思考，不管客户端带不带。
- 所以：**同一轮里，上一次的思考会计入下一次的输入**（和设计文档 P4 的判断一致）。省钱要从"少调用几次、少想"入手，不能靠客户端不回传。没有测跨轮（新的 user 消息之后）的情况，旧轮本来就会折叠掉，用不上。

## 7. 结论

- **(a) 命中缓存的 token 数**：取 `usage.prompt_cache_hit_tokens`；没有这个字段时取 `usage.prompt_tokens_details.cached_tokens`（实测两者相等）；都没有记 0。和设计文档第 4 节写的取法一致。
- **(b) 思考 token 数**：取 `usage.completion_tokens_details.reasoning_tokens`，已经包含在 `completion_tokens` 里。关思考时 `completion_tokens_details` 是 `null`，按 0 记（这时确实没有思考）。和设计文档一致。
- **(c) 能关掉 `deepseek-flash` 思考的 `extra_body`**：`{"thinking": {"type": "disabled"}}`。两次平均输出 24 token，是默认平均思考量（143）的 17%，不超过 30%，回答不为空。其余候选（`thinking: enabled`、`reasoning_effort: low / minimal`、`enable_thinking: false`）接口都接受但没有明显降低思考，**没有可行**。所以 Task 11 要跑 E2。
- **(d) 程序补的 build 调用的写法**：`user_message`。开着思考时，程序补的 `tool_call` 写法（5a、5b）被服务端以 400 拒绝；追加 user 消息的写法（5e）可用。Task 6 改用提示词文档第 5 节的备用写法，已记为偏离 D6。
- **(e) 3b 与 3c 的命中数对比**：两者都是 4608（只命中系统提示词），因为 3c 追加的内容不到一个缓存块、间隔只有 3 秒；补充的 3d 显示追加约 300 token、间隔 10 秒以上后，追加的内容会被缓存（第二次命中 4992，第三次命中 5376）。
