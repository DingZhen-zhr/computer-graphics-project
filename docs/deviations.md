# 偏离计划的记录

格式：原计划是什么 / 实际情况 / 怎么改 / 影响哪些后续任务。

## D1（Task 1）`.gitignore` 多加一行 `.simplecad/`

- 原计划：`.gitignore` 写入 `.venv/`、`__pycache__/`、`sessions/`、`__marimo__/`、`config.toml`、`benchmarks/results/`、`*.egg-info/`。
- 实际情况：SCA 在出错时会往**当前工作目录**写 `.simplecad/diagnostics/*.png`（诊断图）。在项目目录里跑探测脚本后发现多出了 `.simplecad/`。
- 怎么改：`.gitignore` 多加 `.simplecad/`；探测脚本先 `chdir` 到临时目录再运行。
- 影响：Task 6 的子进程工作目录本来就是临时目录，不受影响；不改任何接口。
