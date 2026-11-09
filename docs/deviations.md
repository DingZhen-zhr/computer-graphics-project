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
