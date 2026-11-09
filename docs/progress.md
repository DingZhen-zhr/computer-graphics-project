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

## Task 3：特征列表 → notebook 文件 —— 完成

- 做了什么：`cad_agent/notebook.py`（`ROLES`、`Feature`、`FeatureList`、`RenderedNotebook`、`render_notebook`、`NotebookError`）、`tests/test_notebook.py`。
- 测试数量：新增 32 个（含 1 个 `sca` 标记的真实运行测试），全部测试 58 个全部通过。
- 说明：
  1. `NotebookError` 多了一个可选属性 `feature`（相关 slug，不确定时为 None），Task 9 的 build 返回要用它；构造方式 `NotebookError(message, feature=None)`，对计划里的 `NotebookError(ValueError)` 是兼容的。
  2. 除计划列出的检查外，还拦了：特征变量名与参数名/前面特征重名、slug 对应的变量名是保留名或 Python 关键字（`model`、`scad`、`if` 等）、语法错误（带行号和 slug）、顶层循环变量没有下划线。
  3. 输入推断用 `ast`，函数、lambda、推导式里的局部名字不算最外层赋值；没有参数时不生成参数 cell。
  4. notebook 末尾带标准的 `if __name__ == "__main__": app.run()`，方便直接 `python model.py`；`cell_lines` 的范围是从 `@app.cell` 到该 cell 的 `return` 行。

## Task 4：检查项格式 —— 完成

- 做了什么：`cad_agent/checks/__init__.py`、`cad_agent/checks/spec.py`（`CHECK_TYPES`、`Check`、`CheckResult`、`parse_checks`、`eval_expr`、`missing_coverage`、`CheckSpecError`，另有 `expr_names`）、`tests/test_check_spec.py`。
- 测试数量：新增 37 个，全部测试 95 个全部通过。
- 说明：
  1. `Check.args` 里放各类型自己的字段（bbox: `axis`；count: `kind`、`where`；angle: `a`、`b`；点: `point`；distance: `a`、`b`），`expected`/`tol`/`op` 在 `Check` 自己的字段里。`volume` 的 `tol` 存的是相对容差（默认 0.01）。必做检查的 `type` 等于它自己的 id（`valid`、`single_solid`、`positive_volume`）。
  2. 校验比计划更严的地方（都是为了让模型少走弯路）：`where` 的属性必须在已实测存在的 9 个里（`geom.radius` 这类不存在的属性在 SCA 里不会报错只是选不到，见笔记第 5 节）；出现不认识的字段会报错并列出可用字段；`bbox/angle/volume` 写了非 `==` 的 `op` 会报错。共用 schema 里有、但对该类型无关的字段（如 bbox 上的 `kind`）直接忽略。
  3. 表达式乘方次数超过 100 会拒绝，防止 `9**9**9` 卡死。

## Task 5：测量引擎 —— 完成

- 做了什么：`cad_agent/checks/engine.py`（`run_checks`、`query`、`body_facts`）、`tests/test_engine.py`（全部标记 `sca`）；`checks/spec.py` 里补了一个公开函数 `parse_where`（校验单独的一组 where 条件，`query` 和后面的 `inspect` 工具用）。
- 测试数量：新增 19 个，全部测试 114 个全部通过。
- 说明：
  1. 所有测量写法来自笔记第 4、5、6、14 节：包围盒/体积/有效性/实体个数用 `inspect_shape_rbrepinspection`；点分类用 `BRepClass3d_SolidClassifier`；两组几何的最小距离先把选中的实体各拼成一个 compound 再算一次 `BRepExtrema_DistShapeShape`，避免两两配对；法向夹角用 `get_normal_at()`（平面法向朝材料外）。
  2. `point_inside` 把“正好在表面上”也算在材料上，`point_outside` 只认“在材料外”（笔记第 14 节的约定）。
  3. 面/边的类型名来自 OCP 的枚举（去掉 `GeomAbs_` 前缀转大写，如 `PLANE`、`CYLINDER`、`LINE`、`CIRCLE`），和 QL 里 `geom.type` 的写法一致。
  4. `detail` 里最多列 8 个被选中几何（类型、中心、面积或长度、平面法向）；选中 0 个时写“选中 0 个”。每条检查各自捕获异常，出错的检查算不通过，原因写进 `detail`。

## Task 6：运行沙盒 —— 完成

- 做了什么：`cad_agent/sandbox/__init__.py`、`guard.py`（`check_code`、`clean_env`）、`runner.py`（子进程入口）、`execute.py`（`RunResult`、`run_job`）、`tests/test_guard.py`、`tests/test_execute.py`（后者标记 `sca`）。
- 测试数量：新增 37 个（guard 22 + execute 15），全部测试 151 个全部通过。
- 说明：
  1. 出错特征的定位按笔记第 9 节：用 `linecache` 读 marimo 临时 cell 的源码找特征注释；`cell_lines` 只作兜底。参数 cell、产品 cell 出错时 `error.cell` 为 None。
  2. 超时有两层：子进程里 `run_notebook(timeout=timeout_s)`，外层 `Popen.communicate(timeout=timeout_s+30)` 兜底，超时用 `taskkill /T` 结束整个进程树。子进程写完 `result.json` 后用 `os._exit(0)` 退出，不等跑不完的线程。
  3. 计划之外的小改动：guard 还拒绝最外层的 `return`/`yield`/`await`（会让 marimo 的 cell 提前返回）和所有双下划线开头的名字（挡住 `__builtins__['eval']` 这类绕法）；环境清理的名字匹配不区分大小写。偏离记录见 `docs/deviations.md` 的 D2（报错翻译）、D3（`-X utf8`）。
  4. 测试里有一个故意绕过 guard 的 notebook（在特征里 `import os as _os`），用来从子进程内部确认：密钥类环境变量已清掉、`PYTHONUTF8=1`、工作目录是 `cad-agent-*` 临时目录。

## Task 7：会话目录与日志 —— 完成

- 做了什么：`cad_agent/session.py`（`Session`：`dir`、`log`、`save_state`、`new_version`、`versions`）、`tests/test_session.py`。
- 测试数量：新增 8 个，全部测试 159 个全部通过。
- 说明：目录名同一秒内重名时加 `-2`、`-3`（测试里用可替换的 `_now()` 固定时间来验证）；`log` 的中文不转义，路径等非 JSON 类型转成字符串；`new_version` 的编号取现有最大编号加 1（有 v10 时下一个是 v11）；没有参数变化时 `changes.md` 写“（需求单参数没有变化）”。
