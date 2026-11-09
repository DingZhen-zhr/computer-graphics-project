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

## 1.1 版 Task 1：模型接口探测 —— 完成

- 做了什么：`scripts/probe_llm.py`（6 个实验，外加 3d、5c~5e、6b 三组计划之外的补充）、`docs/llm-probe-output.txt`（原始输出）、`docs/llm-api-notes.md`（7 节，结论 (a)~(e) 逐条回答）。
- 测试数量：没有新增（本任务是探测），全部测试保持 309 个。
- 结论摘要：(a) 缓存命中取 `prompt_cache_hit_tokens`，与 `prompt_tokens_details.cached_tokens` 相等；(b) 思考取 `completion_tokens_details.reasoning_tokens`，关思考时整个 details 是 `null`；(c) 只有 `{"thinking": {"type": "disabled"}}` 能关思考（输出约为默认思考量的 17%），E2 要跑；(d) 程序补的 `build` 调用开着思考时被服务端 400 拒绝，只能用 `user_message` 写法，记为偏离 D6，计划里 Task 6 的相关描述已同步；(e) 3b、3c 都只命中系统提示词（4608），补充的 3d 证明追加约 300 token、间隔 10 秒以上后会被缓存。
- 遇到的问题和处理：
  1. 应用进程的环境里读不到 `DEEPSEEK_API_KEY`（应用启动时变量还没设），但用户级环境变量里有。探测命令里只在该命令的进程内把它从用户级环境变量读进 `$env:DEEPSEEK_API_KEY`，不打印、不写文件；探测脚本输出前会把 key 替换成 `<已隐藏>`。
  2. 3a~3c 追加内容太少、间隔太短，回答不了"追加的历史能不能被缓存"；6 里思考只有十几个 token，分不清思考有没有计入输入。所以补了 3d（全新前缀、追加约 300 token、间隔 10/30 秒）和 6b（让模型想久一点，并对比放回 `reasoning_content` 与否），第一次运行的输出被带补充实验的第二次完整运行覆盖，提交的输出文件和提交的脚本一致。
  3. 同一轮里思考会计入下一次输入，且放不放回 `reasoning_content` 数字一样（下一次 prompt 比上一次多出"上一次全部输出 + 16"），写进了笔记第 6 节。

## 1.1 版 Task 2：模型客户端与配置 —— 完成

- 做了什么：`cad_agent/llm/client.py`（`USAGE_KEYS`、`Pricing`、`normalize_usage`、`call_cost`、`LLMReply.cost`、`OpenAICompatLLM` 的 `extra_body`/`pricing`）、`cad_agent/llm/factory.py`（`make_llm`）、`cad_agent/config.py`（`Phase`、`PhaseOverride`、`LLMSettings`、`Config.llm_settings`、`[llm.pricing]`/`[llm.clarify]`/`[llm.modeling]`/`extra_body` 的读取和中文报错）、`config.example.toml`（新段用注释写出，不含任何价格数字）；`cli.build_agent` 和评测的模拟用户改用 `make_llm(config, "base", key)`。
- 测试数量：新增 25 个，全部测试 334 个全部通过。按清单改了 `test_llm.py` 的 `test_parse_tool_calls`、`test_plain_reply_without_usage_or_content`（usage 期望值加两项为 0），其余第一版测试没动。
- 说明：
  1. 用量字段名和 `docs/llm-api-notes.md` 一致（`prompt_cache_hit_tokens`、`prompt_tokens_details.cached_tokens`、`completion_tokens_details.reasoning_tokens`），没有偏离。关思考时 `completion_tokens_details` 是 `null`，取值时已处理；另有一个用真实 `openai.types.CompletionUsage` 对象的测试，确认 SDK 保留的额外字段 `prompt_cache_hit_tokens` 读得到。
  2. 计划之外加的小保护：命中数大于输入数时，没命中的部分按 0 算（不会变成负费用），有测试。
  3. 配置里 `[llm.clarify.pricing]`、`[llm.modeling.pricing]` 也支持（设计文档第 7 节说覆盖段可以覆盖 pricing），规则和 `[llm.pricing]` 相同，报错里写明段名。
  4. 第一次用 Python heredoc 往测试文件里写 `\n` 时被转成了真换行，测试文件语法错误；用 `git checkout` 还原这两个文件（只有我自己没提交的改动）后，改用 Edit 工具重写。

## 1.1 版 Task 3：计量接入主循环、命令行和评测 —— 完成

- 做了什么：`cad_agent/agent/loop.py`（`AgentTurn` 加 5 项：`prompt_tokens`、`completion_tokens`、`cached_tokens`、`reasoning_tokens`、`cost`；每次调用的日志记完整用量和本次费用，每轮结束的日志记这 5 项）、`cad_agent/cli.py`（每轮结束显示提示词文档第 6 节的格式，没有费用时不带"约 ¥"）、`benchmarks/sim_user.py`（`SimUser.cost`）、`benchmarks/run.py`（`HOLDOUT_TASKS`、`TASK_SETS`、`--set`、`--repeat`、`render_summary_md`、结果里多出 5 项用量和 `cost`、`sim_cost`、重复运行的 `run` 和 `<任务名>-<r>` 目录）、新文件 `benchmarks/compare.py`（`task_means`、`render_compare_md`、`main`）。
- 测试数量：新增 25 个，全部测试 359 个全部通过。`test_question_failed_and_delivered_turns_are_printed` 没改（新格式里仍有总 token 数）。
- 说明：
  1. `compare.py` 里放了表格数字格式（`COST_FMT` 等）和 `fmt`、`success_text`、`total_row`，`run.py` 的汇总表复用它们，两张表的格式一致。"合计"行 = 各任务平均值相加（有任务缺某项就是 `-`），成功列合计 = 总成功次数 / 总遍数。
  2. 费用比（新/旧）和对比表之间空了一行，免得 Markdown 把它当成表的一行。
  3. 没有成功调用的轮（模型调用失败）不计入评测的费用；一个任务里只要有一轮有调用却缺 `cost`，整个任务的 `cost` 就是 `None`。
  4. 计划里 `test_main_rejects_bad_repeat_and_empty_set` 依赖 `HOLDOUT_TASKS` 现在是空的；为了 Task 10 填上留出任务后它不会变红，测试里用 monkeypatch 把 `TASK_SETS["holdout"]` 固定成空表，断言没有放松。
  5. 往 `benchmarks/run.py` 里用 heredoc 脚本改文件时 `\n` 又被转成真换行（和 Task 2 同样的问题），发现后用 Edit 工具改回；以后改文件一律用 Edit/Write 工具。

## 1.1 版 Task 4：基线评测 —— 完成

- 做了什么：用第一版流程加新计量（commit `252c4f1`）跑了 3 个开发任务各 1 遍，结果目录 `benchmarks/results/20261109-164116`，写进 `docs/results-v1.1.md` 的"基线"一节。`config.toml` 里的 `[llm.pricing]` 由用户填写（0.04 / 2 / 8，高峰时段价），没有 `extra_body` 和阶段覆盖。
- 测试数量：没有新增，全部测试保持 359 个（本任务提交前重新跑过）。
- 结果：phone_stand 成功（修复 5 次，¥2.02）、flange 成功（修复 1 次，¥0.26）、l_bracket 没成功（总体积偏差约 −4.4%，其余验收都过；¥1.53）。三个任务合计 ¥3.81、69 次调用，输入 1,832,794 token（命中缓存 494,336，约 27%）。基线按实际结果记录，没有重跑。
- 说明：命中缓存的比例只有约 27%，和设计文档 P2 的判断一致（状态消息在历史前面，每次调用都变）。

## 1.1 版 Task 5：每轮快照与上下文折叠 —— 完成

- 做了什么：新文件 `cad_agent/agent/context.py`（`USER_HEADER`、`CONFIRM_COMPACT`、`compact_text`、`with_warning`、`Context`）；`state.py` 的 `render_state` 换成 `render_snapshot`（格式见提示词文档第 2 节，删掉 `_last_build`）；`tools.py` 的 `Workspace.last_build_content`（`_build` 和 `_build_without_run` 都设）；`loop.py` 用 `self.context` 代替 `self.messages`，每轮开始 `start_turn(content, render_snapshot(ws))`，`_end` 里 `end_turn`，每条 tool 消息过 `with_warning`，删掉 `_llm_messages`。
- 测试数量：全部测试 370 个全部通过。按清单改了 `test_clarify_then_question`、`test_confirmation_then_delivery`、`test_mixed_confirmation_not_accepted`；`test_state_message_refreshed`、`test_state_message_is_not_kept_in_history` 换成 `test_snapshot_fixed_within_turn`、`test_old_turns_are_compacted`；`test_prompts.py` 的 4 个 `test_state_message_*` 换成 4 个 `test_snapshot_*`。新增 `test_context.py`（5 个）、`test_build_records_last_build_content`、`test_prefix_stable_within_turn`、`test_warning_when_few_tool_calls_left`、`test_llm_error_turn_is_compacted`、`test_snapshot_after_tool_cap_has_last_build`。
- 偏离：清单之外还有一条第一版测试必然失败——`test_every_tool_call_gets_a_tool_message_even_when_turn_ends_early`（它在第 2 轮里检查第 1 轮的 tool 消息，而第 1.1 版整轮折叠掉了）。按 CLAUDE.md 先记了偏离 D7，只改了这条测试的断言（改成"旧轮里没有悬空的 `tool_calls`、也没有 `tool` 消息"），并删掉了不再用的 `TURN_ENDED_MESSAGE`。
- 说明：快照里本轮已经确认的那一轮，阶段在 `start_turn` 之前就按"已确认"算（确认处理在前）；`loop.py` 现在 255 行。

## 1.1 版 Task 6：程序代按按钮 —— 完成

- 做了什么：新文件 `cad_agent/agent/automation.py`（`SKIPPED_BUILD_MESSAGE`、`AUTO_BUILD_PREFIX`、`AUTO_BUILD_NOTE`、`BriefShape`、`brief_shape`、`has_error`、`should_auto_confirm`、`should_auto_build`）；新文件 `cad_agent/agent/delivery.py`（把 `loop.py` 里的失败文字、交付文字、导出版本移过来，行为不变）；`loop.py`：C3 同一次回复里前面出错就跳过后面的 build（tool 消息是 `SKIPPED_BUILD_MESSAGE`，不计失败、计一次工具调用、日志加 `skipped: true`）、C1 一次回复的工具执行完且本轮没结束时自动请确认（日志 `{"kind": "auto", "action": "request_confirmation"}`）、C2 自动重建（日志 `{"kind": "auto", "action": "build", "id": "auto-build-<n>"}`）；`tools._build`：C4 缺检查不计失败。
- 测试数量：全部测试 399 个全部通过（新增 29 个）。按清单改了第一版测试：`test_confirmation_then_delivery`、`test_mixed_confirmation_not_accepted`、`test_non_affirmative_answer_still_clears_waiting_flag`、`test_real_build_end_to_end`、`test_suggested_change_after_delivery_requires_reconfirmation`、`test_modification_keeps_old_checks`、`test_coverage_gap_counts_as_failure`（换成 `test_coverage_gap_does_not_count_as_failure`）、`FULL_SCRIPT`、`test_run_task_with_fakes`（7 → 5）、`test_run_task_counts_repairs`。Review Focus 第 1、2 条分别对应 `test_build_in_same_reply_blocked_then_auto_confirm` 和 `test_no_auto_build_when_nothing_changed`。
- 偏离：自动重建用的是偏离 D6 的备用写法（追加 `user` 消息 `AUTO_BUILD_NOTE + "\n" + build 返回的 JSON`，不追加 `auto-build-<n>` 的 assistant/tool 消息）；`test_auto_build_failure_lets_model_repair` 的断言按计划里已同步的描述写。没有新的偏离。
- 说明：`loop.py` 254 行，没超过 300，但失败文字、交付文字、导出已经按 Global Constraints 的办法放进 `delivery.py`（不拆的话约 310 行）。自动重建也计一次工具调用，参与每轮 40 次的上限。多加的测试：自动请确认保留模型的开头文字、自动重建编号递增、跳过的 build 仍计一次工具调用、缺检查的 build 不结束本轮、真实失败仍计数。

## 1.1 版 Task 7：按阶段选模型 —— 完成

- 做了什么：`Agent.__init__` 多一个参数 `modeling_llm: LLM | None = None`；一轮开始、处理完确认之后按 `ws.brief.can_build()[0]` 决定本轮用哪个模型（建模阶段且有 `modeling_llm` 才用它），这一轮里不再换；日志的 `user` 记录多了 `phase`（`clarify` 或 `modeling`）。`cli.build_agent` 现在用 `make_llm(config, "clarify", key)` 和 `modeling_llm=make_llm(config, "modeling", key)`。README"配置模型"一节补了 `extra_body`、`[llm.pricing]`、`[llm.clarify]`、`[llm.modeling]` 的说明，例子用笔记里实测可行的 `{thinking = {type = "disabled"}}`。
- 测试数量：新增 5 个（`test_phase_picks_llm`、`test_without_modeling_llm_everything_uses_the_default`、`test_llm_fixed_within_turn`、`test_user_log_has_phase`、`test_build_agent_uses_phase_settings`），全部测试 404 个全部通过。测试里的 `make_agent` 多了一个可选参数 `modeling_replies`。
- 说明：模拟用户仍然只用 `[llm]`（评测里用 `make_llm(config, "base", key)`）。没有偏离。
