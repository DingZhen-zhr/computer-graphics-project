# 偏离计划的记录

格式：原计划是什么 / 实际情况 / 怎么改 / 影响哪些后续任务。

## D1（Task 1）`.gitignore` 多加一行 `.simplecad/`

- 原计划：`.gitignore` 写入 `.venv/`、`__pycache__/`、`sessions/`、`__marimo__/`、`config.toml`、`benchmarks/results/`、`*.egg-info/`。
- 实际情况：SCA 在出错时会往**当前工作目录**写 `.simplecad/diagnostics/*.png`（诊断图）。在项目目录里跑探测脚本后发现多出了 `.simplecad/`。
- 怎么改：`.gitignore` 多加 `.simplecad/`；探测脚本先 `chdir` 到临时目录再运行。
- 影响：Task 6 的子进程工作目录本来就是临时目录，不受影响；不改任何接口。

## D2（Task 6）报错翻译不是“只保留最后 800 个字符”

- 原计划：`runner` 里“错误信息只保留异常类型 + 最后 800 个字符”。
- 实际情况：SCA 的 `SimpleCADError` 是分段的长文本，最有用的 `What happened`、`Measurements` 在开头，最后 800 个字符反而是 `Inventory`、`Technical details`；`Evidence` 里还有诊断图的临时路径。pybind 的 `TypeError`（关键字参数名写错）则是开头的函数签名有用，结尾是一大串 `Var(name=...)` 噪声。照计划截取会把有用的部分丢掉，也违背设计文档第 2 节第 3 条“报错要翻译”。
- 怎么改：`runner.summarize_exception` 对 `SimpleCADError` 取 `Operation`、`What happened`、`Measurements`、`How to fix` 前 2 条、`Inventory` 前 6 条；对 pybind 的 `TypeError` 保留函数签名并去掉 `Invoked with` 之后的内容；其余异常仍按计划取“最后 800 个字符”。总长度都不超过 800 字符。`RunResult.error` 的格式 `{"cell", "type", "message"}` 没有变。
- 影响：Task 9 的 build 返回里 `error.message` 就是这个精简后的文字，不需要再处理。

## D3（Task 6）子进程命令多了 `-X utf8`

- 原计划：执行 `[sys.executable, "-I", "-m", "cad_agent.sandbox.runner", job.json]`，环境变量里设 `PYTHONUTF8=1`。
- 实际情况：`-I`（隔离模式）会忽略所有 `PYTHON*` 环境变量，包括 `PYTHONUTF8`，子进程的标准输出会退回本机的 GBK 编码。
- 怎么改：命令改为 `[sys.executable, "-I", "-X", "utf8", "-m", "cad_agent.sandbox.runner", job.json]`，环境变量里仍然设 `PYTHONUTF8=1`（给渲染进程等孙进程用）。结果文件本来就显式用 utf-8 读写，所以这只是让子进程输出不乱码。
- 影响：无。

## D4（Task 9）缺检查时，build 返回里多一个字段 `coverage_note`

- 原计划：build 返回的 JSON 格式和 `hint` 文字照抄提示词文档第 4 节；同时计划的测试 `test_build_coverage_gap_not_deliverable` 要求 content 含“缺少检查”和参数名。
- 实际情况：提示词文档第 4 节“缺检查”那一行的 `hint` 原文是“模型和检查都通过了，但这些用户参数还没有检查：…”，写的是“还没有检查”，不含“缺少检查”。两处要求对不上。
- 怎么改：`hint` 保持逐字不动；只在**缺检查时**多放一个字段 `"coverage_note": "缺少检查的用户参数：a、b"`。其他情况下返回的 JSON 字段和提示词文档完全一致。
- 影响：只影响 Task 9 的 build 返回内容；Task 10 的状态消息和评测不依赖这个字段。

## D5（Task 9）`ToolBox` 多了几个成员，`tools.py` 旁边多了一个 `tool_specs.py`

- 原计划：`ToolBox(ws, run_job, timeout_s, secret_names)` 只有 `schemas()` 和 `call()`；工具说明在 `cad_agent/tools.py` 里组装。
- 实际情况：build 返回里的 `failures_left` 需要“本轮已失败几次”和“上限”，而 `ToolBox` 的构造参数里没有这两个；`tools.py` 加上九个工具的说明会超过 300 行。
- 怎么改：`ToolBox` 增加公开成员 `max_build_failures`（默认 3，主循环按配置设置）、`build_failures`（本轮 build 没通过的次数）、`begin_turn()`（每条新的用户消息前清零）、`available()`（当前可用的工具名）。构造函数签名和 `schemas()`、`call()` 不变。九个工具说明放进新文件 `cad_agent/tool_specs.py`：由脚本直接从提示词文档第 3 节的 json 块生成，保证逐字一致，`tests/test_tools.py::test_schemas_are_verbatim_copy_of_prompts_doc` 会逐项比对。
- 影响：Task 10 的主循环要在每条用户消息开始时调用 `toolbox.begin_turn()`，并在启动时设置 `toolbox.max_build_failures = config.max_build_failures`。

## D6（1.1 版 Task 1）程序补的 build 调用被服务端拒绝，Task 6 改用 `user_message` 备用写法

- 原计划：Task 6 的 C2 自动重建，在历史里追加一条 `assistant` 消息（`tool_calls` 里只有一个 id 为 `auto-build-<n>` 的 `build`）和对应的 `tool` 消息，和模型自己调用 `build` 完全一样处理。
- 实际情况：Task 1 探测（`docs/llm-api-notes.md` 第 5 节）发现，开着思考时，服务端对这种没有 `reasoning_content` 的程序补的调用返回 400：`The reasoning_content in the thinking mode must be passed back to the API.`（5a、5b 都被拒）。追加 `user` 消息的写法（5e）被接受。补 `reasoning_content` 能绕过（5d），但那是厂商专用的字段，Global Constraints 不许代码里出现。
- 怎么改：Task 6 采用设计文档第 6 节 C2、提示词文档第 5 节的备用写法：直接调用 `build`，往历史里追加一条 `user` 消息，内容是 `"【程序自动运行了 build，结果如下】\n" + build 返回的 JSON`，之后交付、计失败、到上限停下都和模型自己调用 `build` 一样。`automation.py` 另加常量 `AUTO_BUILD_NOTE = "【程序自动运行了 build，结果如下】"`（只增不改 Interfaces 里已有的名字）；日志里仍记 `{"kind": "auto", "action": "build", "id": "auto-build-<n>"}`，所以 `AUTO_BUILD_PREFIX` 仍然用得上。
- 影响：Task 6 的主循环 C2 一条，以及测试 `test_auto_build_failure_lets_model_repair`（原来断言 `llm.calls[4]` 里有 `tool_call_id == "auto-build-1"` 的 tool 消息，改为断言里面有一条以 `AUTO_BUILD_NOTE + "\n"` 开头的 user 消息）。计划文档里这两处已同步修改。用量字段名（`prompt_cache_hit_tokens`、`reasoning_tokens`）和设计文档第 4 节一致，Task 2 不受影响。

## D7（1.1 版 Task 5）第一版测试 `test_every_tool_call_gets_a_tool_message_even_when_turn_ends_early` 改了断言

- 原计划：Task 5"要改的第一版测试"清单里没有这条测试，要求一律不动。
- 实际情况：这条测试让一次回复里同时调用 `ask_user` 和 `build`，本轮在 `ask_user` 处结束；然后在第 2 轮检查 `llm.calls[1]` 里第 1 轮的 assistant 消息有 `tool_calls`、每个调用都有 `tool` 消息。第 1.1 版一轮结束就整轮折叠（只留用户原话和一条纯文字 assistant 消息），旧轮里根本不再有 `tool_calls` 和 `tool` 消息，原断言必然失败（`KeyError: 'tool_calls'`）。设计文档第 5 节就是要这样折叠，不是实现错了。
- 怎么改：主循环里本轮提前结束时不再给后面没执行的调用补"本轮已经结束"的 `tool` 消息（整轮都折叠掉，补了也看不到），删掉了常量 `TURN_ENDED_MESSAGE`。测试断言改成这个测试真正想保证的事：第 2 轮发给模型的消息里没有悬空的 `tool_calls`、也没有 `tool` 消息，role 依次是 `system, user, assistant, user`。测试名没变。
- 影响：之后的任务不受影响。Task 6 的"程序补的调用"也都在同一轮里，不涉及跨轮的悬空调用。

## D8（1.1 版 Task 9）`test_old_turns_are_compacted` 数"【当前状态"的写法要改成数完整标题

- 原计划：Task 5 的 `test_old_turns_are_compacted` 断言"整个列表里只有一处含 `【当前状态`"。
- 实际情况：Task 9 把第 1.1 版系统提示词逐字写进 `system.md` 之后，系统提示词的"当前状态"一节里自己就写了两次"【当前状态】"，所以按 `【当前状态` 数，system 消息和快照各一处，共 2 处，计划里的这条断言和计划要求逐字照抄的系统提示词互相矛盾（Task 5 时 `system.md` 还是第一版，所以当时是对的）。
- 怎么改：只改这条我在 Task 5 新加的测试，数完整的快照标题 `【当前状态（程序生成，不是用户说的话）】`（系统提示词里没有这个完整标题）。要保证的事没变：旧轮折叠后整个消息列表里恰好只有一张快照；断言没有放松。
- 影响：无。
