# 进度记录

## Task 1：环境搭建与 SCA 摸底 —— 完成

- 做了什么：`git init`、`.gitignore`、`pyproject.toml`、`.venv`（Python 3.13.7）、`scripts/probe_sca.py`（+ `probe_common.py`、`probe_sca_cheatsheet.py`）、`docs/sca-api-notes.md`、`docs/sca-probe-output.txt`、`tests/test_smoke.py`。
- 测试数量：1 个（`test_smoke.py`），全部通过。
- 结果：`simplecadapi[editor,verify]==2.2.7` 一次装成功，verify 附加包没问题，依赖不用改。提示词文档第 6 节的速查表条目全部实测跑通；4 种常见报错（另加 3 种）的原文都记在笔记第 13 节。
- 遇到的问题和处理：
  1. 中文路径：文件名是中文的 notebook 无法运行（`artifact paths must be ASCII`），目录是中文、文件名英文则可以；截图和 STEP 写进中文目录都成功。结论是 notebook 文件名恒用 `model.py`，仍在英文临时目录运行。
  2. SCA 会往当前目录写 `.simplecad/`，记为偏离 D1。
  3. 出错特征不能用行号对照 `cell_lines`：traceback 里的帧是 marimo 的临时 cell 文件，行号是 cell 内部行号。改用 `linecache` 读 cell 源码里的特征注释（笔记第 9 节）。Task 6 按这个做，`cell_lines` 仅作兜底。
  4. `sca` 命令不在 PATH 上，用 `Path(sys.executable).parent / "sca.exe"`。
  5. 圆柱面也有 `geom.normal.*`，按法向选面必须同时限定 `PLANE`；没有 `geom.radius`。

## Task 2：需求单 —— 完成

- 做了什么：`cad_agent/brief.py`（`Param`、`Brief`、`BriefError`）、`tests/test_brief.py`。
- 测试数量：新增 25 个（计划列出的 10 个，加上未改动的建议值不清零、非法来源/数值、未知字段、失败的 patch 不改任何东西、保留名、to_dict 格式等），全部测试 26 个全部通过。
- 说明：`apply_patch` 先在副本上做完全部检查再一次性生效，所以失败时需求单保持原样。参数名除了“小写合法标识符”，还拒绝 Python 关键字和 `scad/ql/math/model/sin/pi` 等会与 notebook 或检查表达式冲突的保留名（计划之外的输入校验，没有改任何接口）。
