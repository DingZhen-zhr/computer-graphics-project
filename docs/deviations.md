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
