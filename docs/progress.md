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

## Task 8：配置与模型接口 —— 完成

- 做了什么：`cad_agent/config.py`（`Config`、`ConfigError`、`load_config`）、`cad_agent/llm/__init__.py`、`llm/client.py`（`ToolCall`、`LLMReply`、`LLM`、`LLMError`、`OpenAICompatLLM`）、`llm/fake.py`（`ScriptedLLM`，另有测试辅助函数 `scripted_call`）、`config.example.toml`、`tests/test_config.py`、`tests/test_llm.py`。
- 测试数量：新增 29 个，全部测试 188 个全部通过。
- 说明：
  1. 本机装到的是 openai 3.46.0，它底层用 `httpx2`（不是 `httpx`），所以测试里造请求/响应对象时优先导入 `httpx2`；生产代码只用 `openai` 自己的异常类，两种版本都能用。
  2. 重试由 `OpenAICompatLLM` 自己做（SDK 自带的重试关掉）：网络断开、超时、429、5xx 重试，间隔 1 秒、2 秒，共 3 次调用；401/403 和其他 4xx 不重试，直接报错，信息里不含 API key。重试用完抛 `LLMError`，信息不带“模型调用失败”前缀（由 Task 10 的主循环加）。
  3. `ScriptedLLM` 的脚本里除了回复，也可以放异常对象（轮到时抛出），Task 10 测试 `LLMError` 时要用；`calls` 记录的是 messages 的拷贝。
  4. `load_config` 对未知的段、未知的项、类型错误、缺少 `base_url`/`model` 都给出中文信息；配置文件读写显式用 utf-8。

## Task 9：工具层 —— 完成

- 做了什么：`cad_agent/tools.py`（`Workspace`、`ToolOutcome`、`ToolBox`）、`cad_agent/tool_specs.py`（九个工具说明，逐字取自提示词文档）、`cad_agent/agent/__init__.py`、`agent/api_docs.py`（`lookup_api`、`api_names`）、`tests/test_tools.py`。
- 测试数量：新增 39 个，全部测试 227 个全部通过。
- 说明：
  1. 需求单不能建模时，`schemas()` 只给 `update_brief`、`ask_user`、`request_confirmation`、`api_help`；直接调用建模工具会得到含“需求单”的错误，不会运行 `run_job`。
  2. `call()` 从不抛异常：参数不是合法 JSON、工具不存在、缺必填参数、处理函数内部出错，都变成中文错误；`ask_user` 限 1–5 个非空问题；有待确认问题时 `request_confirmation` 会被拒绝。
  3. build 的计数：渲染 notebook 或解析检查项时就出错（没运行）也算一次失败；缺检查（模型和检查都通过但用户参数没被覆盖）同样算一次失败，因为不能交付。
  4. `api_help` 只定位 SCA 包路径不导入包；名字允许带 `scad.`、`ql.` 前缀，只接受标识符，防止路径穿越；文档超过 4000 字符会截断。
  5. 偏离记录：`docs/deviations.md` 的 D4（缺检查时多一个 `coverage_note` 字段）、D5（`ToolBox` 多了几个成员、多了 `tool_specs.py`）。

## Task 10：主循环与提示词 —— 完成

- 做了什么：`cad_agent/agent/loop.py`（`AFFIRMATIVE`、`is_affirmative`、`AgentTurn`、`Agent`）、`agent/state.py`（`load_system_prompt`、`render_state`）、`agent/prompts/system.md`（从提示词文档第 1 节脚本提取，逐字一致）、`agent/prompts/sca_cheatsheet.md`、`tests/test_loop.py`、`tests/test_prompts.py`、`tests/helpers.py`（假 `run_job` 等测试工具）。
- 测试数量：新增 35 个（含 1 个 `sca` 标记的真实端到端测试：脚本里写出带孔板的完整流程，用真实 `run_job`，`v1` 里有 `model.step` 和 `view.png`），全部测试 262 个全部通过。
- 说明：
  1. 测试会逐字比对：`system.md` 与提示词文档第 1 节一致；速查表的分节与提示词文档第 6 节一致；速查表里每个“例：`…`”都是合法的单行 Python、能通过 guard，且用到的 `scad.xxx` 都在包内 API 文档里存在。
  2. 速查表的每条写法都来自笔记第 12、13 节的实测。写速查表时发现减孔带 `skip_non_intersecting=False` 的几种组合（多个工具体、圆周/线性阵列、循环列表）和“按坐标范围选侧面 + exactly(1)”笔记里没有，已先补进探测脚本并跑通，补进笔记第 12.5、12.7、12.9 节，`docs/sca-probe-output.txt` 重新生成。速查表标题下多了一小段说明（参数名可直接运算、用关键字参数），分节标题没动。
  3. 主循环的约定：一条用户消息一轮；每轮开始 `toolbox.begin_turn()`；确认只认整句在 `AFFIRMATIVE` 里（“可以，但角度改成70”会原样转给模型，且无论怎么回都清掉“等待确认”）；一条回复里有多个工具调用时，每个调用都有对应的 `tool` 消息（本轮提前结束时，后面的调用回“没有执行”）；参数不是合法 JSON 的调用，原文原样放回对话历史。
  4. 结束条件的先后：build 通过（交付）→ 失败次数达到上限 → 要等用户的工具（提问/确认）→ 工具调用次数达到上限。交付时用 `export_step`/`render_png` 再跑一次 `run_job`，导出到临时目录再由 `session.new_version` 复制；`changes` 取自上次交付以来每次 `update_brief` 返回的变化行。每轮结束都保存当前状态（计划只要求交付和失败后保存，多存不影响）。
  5. 日志的 `kind`：`user`、`assistant`、`tool`、`build`（每次 build 一条，含是否通过、出错特征、没通过的检查 id）、以及每轮结束的 `reply`/`question`/`confirm`/`delivered`/`failed`。

## Task 11：命令行界面与说明文档 —— 完成

- 做了什么：`cad_agent/cli.py`（`main`、`build_agent`、`find_sca`、`diff_briefs`）、`cad_agent/__main__.py`、`README.md`、`tests/test_cli.py`；补测了 `sca` 命令在中文目录下的表现，写进 `docs/sca-api-notes.md` 第 2、11 节。
- 测试数量：新增 19 个，全部测试 281 个全部通过。另外手动跑了 `python -m cad_agent`：有（假的）环境变量时能启动、命令都能用、日志第一行是 `startup`（含 Python、simplecadapi、模型名、地址版本，不含 key）；没设置变量时打印“请先设置环境变量 DEEPSEEK_API_KEY”并返回 1。
- 说明：
  1. 计划里 `main(argv, input_fn, print_fn)` 没有注入智能体的位置，所以另有模块级函数 `build_agent(config) -> (Agent, Session)`，测试里替换它；没有 key 时 `build_agent` 在创建会话目录**之前**就抛 `ConfigError`。
  2. `/view` 用 `Popen([sca 路径, "edit", 会话目录])`，`sca` 路径取与当前 python 同目录的 `sca.exe`（`shutil.which` 找不到）；已经有编辑器在跑就不再启动第二个；退出时统一关掉。实测：`sca ls`、`sca run` 在中文目录下正常，`sca edit --no-browser` 能启动并返回 200。**没有用浏览器点开 notebook 看编辑器里的实际效果**，留给 Task 13 联调时人工看一眼。
  3. 每轮结束后顺带显示“本轮模型调用 N 次，约 M token”；Ctrl+C、输入结束（EOF）都会正常退出。

## Task 12：测试任务与评测脚本 —— 完成

- 做了什么：`benchmarks/__init__.py`、`benchmarks/tasks/phone_stand.yaml`、`flange.yaml`、`l_bracket.yaml`、`benchmarks/sim_user.py`（提示词由脚本从提示词文档第 5 节提取，逐字一致）、`benchmarks/run.py`（`load_task`、`run_task`、`run_benchmarks`、`render_results_md`、`main`）、`tests/test_benchmarks.py`、`tests/test_benchmark_references.py`；`pyproject.toml` 的 pytest 配置加了 `pythonpath = ["."]`，直接运行 `pytest` 也能 import `benchmarks`。
- 测试数量：新增 28 个（`test_benchmarks.py` 18 个 + `test_benchmark_references.py` 10 个，后者标记 `sca`），全部测试 309 个全部通过。
- 说明：
  1. 三个任务的初始需求、隐藏需求、修改请求和验收数字都按计划写进了 YAML（l_bracket 的手算过程写在注释里，flange 的孔面积范围 328.3~362.9 即 π·11·10 的 ±5%）。
  2. **额外加的一道保险**：`test_benchmark_references.py` 用真实 SCA 为三个任务各写了一个“标准答案”模型（手机支架：底板+倾斜板+托唇+充电缺口；法兰盘：旋转体+8/6 个螺栓孔+根部圆角；L 形支架：两块板+加强筋+4 个孔+顶面倒角），分别在初始和修改后两个阶段跑人工验收，全部通过（例如手机支架实测夹角 115.0000°，L 形支架体积 26272，在 26316 的 3% 以内）；另有 4 个反例确认验收能恰好卡住“没改参数的旧模型”。这说明验收条件和坐标约定、检查引擎是对得上的，联调时不会冤枉模型。
  3. `run_task` 在计划的签名后多了两个仅限关键字的可选参数 `run_job`、`acceptance_timeout_s`（测试里用桩替换 `run_job`）；返回的 `acceptance` 条目除计划的 `id/expected/measured/deviation/passed` 外多了 `type`、`detail`，结果里多了 `sim_llm_calls`、`sim_tokens`（模拟用户自己的调用次数和 token）。“最大尺寸偏差”只统计长度类检查（bbox、distance，单位 mm），角度和体积的偏差不算。
  4. 阶段超过 `max_user_turns` 仍未交付：该阶段记 `delivered: false`，后面的阶段标 `skipped`，继续下一个任务；单个任务意外崩溃只记一条失败，不影响其余任务；每跑完一个任务就写一次 `results.json`/`results.md`。
  5. **没有做 Task 13**：没有碰 API key，没有联网调用任何大模型。

## Task 13：接入真实模型联调 —— 完成（由用户提供 key，经环境变量临时使用）

- 用户在对话里提供了 key 并要求先用它测试；key 现在存在用户的 Windows 用户环境变量 `DEEPSEEK_API_KEY` 里，没有写进任何文件、配置、日志或提交。模型名按账号可用列表（`deepseek-flash`、`deepseek-v4-pro`）选了 `deepseek-flash`；`config.toml` 在 `.gitignore` 里。
- 评测一次跑通，3 个任务全部成功，详见 `docs/results-v1.md`。提示词和速查表没有改动。
