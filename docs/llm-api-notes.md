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

- （第二版计划 2 补充，查 SDK 文档，未实测）流式请求的用量：请求里加 `stream_options={"include_usage": True}`，服务端在 `data: [DONE]` 之前多发一个 `choices` 为空、`usage` 是整次用量的片段，字段和上面相同，取法不变。出处和细节见第 9 节末尾。DeepSeek 是否支持没有实测。

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

## 8. Claude 接口（查文档，未用真实接口验证）

> 第二版计划 2 Task 1 写的。下面每一条都来自 Anthropic 官方文档（2026-11-11 查阅），**没有用真实接口验证过**：没有用户提供的 Anthropic key，本计划也不允许调用付费接口。
> 出处缩写：[M] = Messages 接口参考 https://platform.claude.com/docs/en/api/messages ；[C] = 提示词缓存 https://platform.claude.com/docs/en/build-with-claude/prompt-caching ；[S] = 流式 https://platform.claude.com/docs/en/build-with-claude/streaming ；[T] = 思考 https://platform.claude.com/docs/en/build-with-claude/thinking ；[E] = 报错 https://platform.claude.com/docs/en/api/errors ；[O] = 模型总览 https://platform.claude.com/docs/en/about-claude/models/overview 。

1. **系统提示词**：请求体顶层的 `system`，可以是文字，也可以是文字块数组 `[{"type": "text", "text": "…"}]`。`messages` 里只放 `user` 和 `assistant`。[M]（要加缓存标记时必须用文字块数组的写法，标记写在块上。[C]）
2. **工具定义**：`tools` 数组，每项 `{"name", "description", "input_schema"}`；`input_schema` 是 JSON Schema，`type` 必须是 `"object"`。名字只能用字母、数字、`_`、`-`，最长 128。和 OpenAI 写法的差别：没有外层的 `{"type": "function", "function": …}`，参数格式的键叫 `input_schema` 不叫 `parameters`。[M]
3. **模型发起工具调用**：assistant 消息的 `content` 里有 `{"type": "tool_use", "id", "name", "input"}` 块，`input` 是对象（不是 JSON 文字）。回复的 `stop_reason` 是 `"tool_use"`。[M][S]
4. **程序回工具结果**：放在下一条 **user** 消息的 `content` 里，块是 `{"type": "tool_result", "tool_use_id": <对应 tool_use 的 id>, "content": 文字或块数组, "is_error": 可选布尔}`。[M]
5. **一次回复里多个工具调用**：一条 assistant 消息里可以有多个 `tool_use` 块（文字块一般在前面）；对应的多个 `tool_result` 要放进**同一条** user 消息，分开放会让模型以后不再并行调用。[S 的工具示例；SDK 说明里的 Parallel tool use 一节]
6. **user 和 assistant 交替**：第一条必须是 user；连续的同角色消息接口会合并成一轮。[SDK 说明 Multi-Turn 一节] 适配层仍然自己合并，让发出去的请求和文档示例一致。
7. **图片块**：`{"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "<base64，不带 data: 前缀>"}}`，`media_type` 只能是 `image/jpeg`、`image/png`、`image/gif`、`image/webp`；也支持 `{"type": "url", "url"}` 来源。图片块放在 user 消息的 `content` 数组里。[M]
8. **用量字段**：`usage.input_tokens`、`usage.output_tokens`、`usage.cache_read_input_tokens`（命中缓存）、`usage.cache_creation_input_tokens`（写入缓存），另有 `cache_creation` 对象按 5 分钟、1 小时分开。**`input_tokens` 不含缓存部分**："tokens after the last cache breakpoint"。总输入 = `cache_read_input_tokens + cache_creation_input_tokens + input_tokens`。[C] 文档没有单独给出"思考 token 数"字段，思考算在 `output_tokens` 里，所以内部的 `reasoning_tokens` 记 0。
9. **缓存标记**：在块上加 `"cache_control": {"type": "ephemeral"}`（可选 `"ttl": "1h"`，默认 5 分钟）。能加在 `tools` 的工具定义、`system` 的文字块、`messages` 里的内容块上；**最多 4 个**，超过返回 400。前缀短于模型的最小长度时不缓存也不报错（Opus 5.5、Sonnet 5.5、Haiku 5.5 是 512 token）。价格倍数：5 分钟写入 1.25 倍、读取一般 0.1 倍（Opus 5.5、Sonnet 5.5 是 0.05 倍）——代码里不写价格，这里只是说明"缓存写入按没命中算"是偏低的估计。[C]
10. **流式事件**（请求体 `"stream": true`）：依次是 `message_start`（`message.usage` 里有 `input_tokens` 等输入用量）→ 每个内容块一组 `content_block_start`（工具调用块在这里给出 `id`、`name`，`input` 是 `{}`）、若干 `content_block_delta`、`content_block_stop` → 一个或多个 `message_delta`（`delta.stop_reason`，`usage.output_tokens` **是累计值**）→ `message_stop`。中间可能有 `ping`。[S]
    - 文字片段：`content_block_delta` 的 `delta = {"type": "text_delta", "text": …}`。
    - 工具参数片段：`delta = {"type": "input_json_delta", "partial_json": …}`，是 JSON 文字的片段，拼起来在 `content_block_stop` 时解析成对象；第一个片段可能是空文字。
    - 思考片段：`thinking_delta`（字段 `thinking`）和块结束前的一个 `signature_delta`（字段 `signature`）。
    - 流中途的错误：HTTP 已经是 200，之后来一个 `event: error`，如 `{"type": "error", "error": {"type": "overloaded_error", "message": "Overloaded"}}`。[S][E]
11. **思考内容要不要原样放回**：**要**。"within a tool-use turn, pass thinking blocks back"，而且最近一条 assistant 消息里的 `thinking`、`redacted_thinking` 块不能改、不能重排、不能只放一部分，否则 400；"outside tool use, omit prior turns' thinking" 是允许的。[T][E] Claude 5 系列默认就开着思考，`display` 默认是 `"omitted"`（思考块的 `thinking` 是空文字，只带 `signature`）。[T][O] 我们内部的消息格式（OpenAI 写法）不带思考块，所以适配层自己记住每次回复的原始内容块，转换消息时，凡是 `tool_calls` 和记下的某次回复一致的 assistant 消息，原样换成那次的全部内容块（见偏离 D14）。
12. **`max_tokens`**：参考文档里它是唯一没标"optional"的数值参数（另两个必填是 `model`、`messages`），按必填处理。[M]
13. **`temperature`**：思考文档写明，Opus 5.5、Sonnet 5.5、Haiku 5.5 等新模型上非默认的 `temperature`、`top_p`、`top_k` 一律 400；从 API 版本 `2026-10-21` 起，**带上 `temperature` 就 400，不论取值、不论模型**。[T] 所以适配层不发 `temperature`（构造参数保留，只是不用，见偏离 D14）。
14. **限流和服务端错误的状态码**：400 `invalid_request_error`、401 `authentication_error`、402 `billing_error`、403 `permission_error`、404 `not_found_error`、409 `conflict_error`、413 `request_too_large`、429 `rate_limit_error`、500 `api_error`、504 `timeout_error`、529 `overloaded_error`。错误体是 `{"type": "error", "error": {"type", "message"}, "request_id"}`。官方 SDK 默认对连接错误、408、409、429、5xx 重试两次。[E] 适配层和 `OpenAICompatLLM` 一样自己重试（429 和 5xx、连接错误、超时重试；401、403 和其他 4xx 不重试），SDK 自带的重试关掉。
15. **请求头**：`x-api-key`、`anthropic-version`（由 SDK 自动带上）。默认地址 `https://api.anthropic.com`。[E 里的 curl 示例]

## 9. 各服务的地址和模型名（查文档）

2026-11-11 对照各家官方文档核实，写进 `cad_agent/providers.toml`。除 DeepSeek 外**都没有用真实接口验证过**（DeepSeek 的地址和两个模型名在第 1 节实测过）。识图一栏：只有官方文档写明"这些模型都能看图"的写 `yes`，其余写 `unknown`（程序按不能识图处理，用户可以自己点"测试识图"）。

| 服务 | 接口类型 | 地址 | 建议的模型名 | key 的环境变量 | 识图 | 出处 |
|---|---|---|---|---|---|---|
| DeepSeek | openai | `https://api.deepseek.com` | `deepseek-flash`、`deepseek-v4-pro` | `DEEPSEEK_API_KEY`（沿用第一版） | unknown | https://api-docs.deepseek.com/ ：只列这两个模型；带图片的 `deepseek-v4-flash-vision-exp` 已经下线，文档没写怎么传图 |
| 智谱 GLM | openai | `https://open.bigmodel.cn/api/paas/v4/` | `glm-5.3` | `ZAI_API_KEY`（文档"环境变量"示例的写法） | unknown | https://docs.bigmodel.cn/cn/guide/develop/openai/introduction ：对话示例用 `glm-5.3`，看图示例用的是另一个模型 `glm-5.3-flash`，所以默认模型能不能看图没核实 |
| Kimi | openai | `https://api.moonshot.cn/v1` | `kimi-k3.1-pro` | `MOONSHOT_API_KEY` | unknown | https://platform.kimi.com/docs/api/chat ：示例里 `kimi-k3.1-pro` 带了 `image_url`，但文档没写哪些模型能看图，先不标 yes |
| 通义千问 | openai | `https://dashscope.aliyuncs.com/compatible-mode/v1` | `qwen-plus` | `DASHSCOPE_API_KEY` | unknown | https://help.aliyun.com/zh/model-studio/compatibility-of-openai-with-dashscope 、https://help.aliyun.com/model-studio/base-url ：这是北京地域的共享域名，文档说"当前可继续使用，建议迁移至业务空间专属域名"（`https://{WorkspaceId}.cn-beijing.maas.aliyuncs.com/compatible-mode/v1`）；地址要和 key 同一地域。`qwen-plus` 是示例注释里的名字；看图要用 Qwen-VL 系列，文档没给具体名字 |
| OpenAI | openai | `https://api.openai.com/v1` | `gpt-6-astra`、`gpt-6.1-sol`、`gpt-6.1-terra`、`gpt-6-luna` | `OPENAI_API_KEY` | yes | https://developers.openai.com/api/docs/models ：四个旗舰模型，"不确定就从 gpt-6-astra 开始"，"all latest OpenAI models support text and image input"；地址取自已安装的 openai SDK（`openai/_data_residency.py` 的 `global`） |
| Claude | anthropic | `https://api.anthropic.com` | `claude-opus-5-5`、`claude-sonnet-5-5`、`claude-haiku-5-5` | `ANTHROPIC_API_KEY` | yes | https://platform.claude.com/docs/en/about-claude/models/overview ："All current models support text and image input"；Opus 5.5 是文档推荐的默认 |
| 自定义地址 | openai | （空，用户填） | （空，用户填） | `CALIPER_API_KEY`（我们自己起的名字） | unknown | — |

补充（OpenAI 兼容接口的流式用量）：已安装的 openai SDK 里 `stream_options={"include_usage": True}` 的说明是"在 `data: [DONE]` 之前多发一个片段，它的 `usage` 是整次请求的用量，`choices` 是空数组；其余片段的 `usage` 是 null；流中途断开就可能收不到这个片段"（`openai/types/chat/chat_completion_stream_options_param.py`）。Task 2 的流式请求照这个写。DeepSeek 等兼容服务是否支持这个选项**没有实测**。

本机装的版本（2026-11-11，`pip index versions` 当时的最新稳定版）：`anthropic` 2.8.0、`keyring` 25.7.0；`pyproject.toml` 的下限照这两个写。已安装的 `anthropic` 2.8.0 用 `httpx2`（和 openai 3.46 一样），默认地址 `https://api.anthropic.com`，自动带的 `anthropic-version` 是 **`2026-10-21`**（`anthropic/_constants.py`），`messages.create` 已经没有 `temperature` 参数，和第 8 节第 13 条一致。
