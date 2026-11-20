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

## D9（1.2 版 Task 3）新增的"纯文字结束前先 build"规则和两处旧测试/计划字面要求冲突

- 原计划：1.2 计划说旧测试一律不动；`update_brief` 成功后 `unbuilt_edits` 设为 True。
- 实际情况：
  1. 1.1 Task 6 的 `test_no_auto_build_when_param_added`（交付后 update_brief 新增一个 user 参数，接着纯文字回复 → reply，llm_calls == 2）正好是新规则要拦的情形：有没 build 的改动、模型用纯文字结束。新规则下程序会先 build 一次（新参数没有检查，不能交付），模型要再回复一次，脚本只有 2 条回复，`ScriptedLLM` 报"脚本已用完"。
  2. `test_no_auto_build_when_nothing_changed`（update_brief 写入相同的值，接着纯文字回复 → reply，没有 v2）：如果 update_brief 一律设 `unbuilt_edits = True`，这条也会被新规则触发并交付 v2。
- 怎么改：
  1. `update_brief` 只在 `changes` 不为空（真的改了东西）时设 `unbuilt_edits = True`；什么都没改的调用不算改动。其余三个工具（upsert_feature、remove_feature、set_checks）成功就设 True，和计划一致。第 2 条旧测试不用改。
  2. 第 1 条旧测试 `test_no_auto_build_when_param_added` 只改了最小的两处：脚本多加一条纯文字回复（`LLMReply("补上检查后再 build", [], {})`），断言从 `llm_calls == 2` 改成 `== 3`；"没有自动重建"的断言保留强度，改成"自动重建记录只有一条，reason 是 turn_end（没有 param_change）"。测试名不变；"没有 v2、结果是 reply"的断言没动。
- 影响：只影响 1.2 Task 3；Task 4 评测不受影响。

## D10（第二版计划 1 Task 1）probe 里量包围盒不能用笔记第 4 节的写法

- 原计划：Task 5 的测试 `test_probe_prints_facts` 里，probe 打印 `model` 的包围盒尺寸，"写法取自笔记第 4 节"（`brep.inspect_shape_rbrepinspection`）。
- 实际情况：Task 1 探测（笔记第 17 节）发现，`simplecadapi.inspect.brep` 的检视函数在 notebook 里一律报 `RuntimeError: simplecadapi.inspect.brep tools cannot run inside an active GraphSession`，probe 代码运行在 notebook 里，所以第 4 节的写法在 probe 里用不了。官方文档 `geometric-validation.md` 也写明检视函数只能在 GraphSession 之外用。
- 怎么改：probe 里量尺寸改用笔记第 17 节实测过的写法：体积 `model.get_volume()`，包围盒取 `ql.vertices().resolve(model)` 全部顶点坐标的范围（平面围成的零件是准的）。`test_probe_prints_facts` 照这个写，断言（输出里有 `78`、`error is None`）不变。速查表补充的"分阶段时的写法"一节多写一条这个用法，提醒模型不要在 probe 里用检视函数。计划 1 Task 5 的测试描述已同步改成"写法取自笔记第 17 节"。
- 影响：只影响 Task 5 的这一条测试的 probe 代码；接口不变。

## D11（第二版计划 1 Task 9）`test_long_section_truncated` 找不到超过 6000 字符的小节

- 原计划：`test_long_section_truncated`：对 `ql-playbook` 里最长的一节，`len(text) <= 6000 + len("
…（后面的内容省略）")` 且 `truncated` 为真。
- 实际情况：SCA 2.2.7 安装包里的 `ql-playbook.md` 共 20537 字符、12 个二级小节，最长的一节（Pattern A）只有约 3216 字符；白名单 10 篇里最长的一节是 `failure-and-repair` 的 Failure classes，约 5678 字符，也不到 6000。所以按真实上限读任何一节都不会截断，"`truncated` 为真"这条断言不可能成立。
- 怎么改：接口和上限（`SECTION_CHARS = 6000`）都不变。测试改成两步：先按真实上限读最长的一节，断言没有截断、长度不超过 6000；再用 `monkeypatch` 把 `SECTION_CHARS` 临时调成 1000，断言 `truncated` 为真、长度不超过 1000 加末尾那一行、以"…（后面的内容省略）"结尾、开头和完整内容一致。截断逻辑照样被检查到，没有放松。
- 影响：只影响这一条测试。

## D12（第二版计划 1 Task 10）阶段小结的折叠时机：最近一次 build 没有干净地停下时先不折叠

- 原计划：一次回复里的工具全部执行完之后（以及程序自动 build 之后），只要 `toolbox.last_advance` 里有还没折叠过的新通过阶段，就调用 `context.fold(stage_summary(...))`，把本轮上一个折叠点之后的全部消息换成小结。
- 实际情况：一次 build 可以先通过 s1、再在 s2 失败（s2 也写好了时），或者通过最后一个阶段、但终检没过（缺检查或参数没被约束）。这时那次 build 的返回里有模型接下来必须改的内容（哪条检查没过、实测数值、哪些参数没被约束、hint），而小结的格式（提示词文档第 4 节）里没有这些；快照又要到下一轮才更新。照计划立刻折叠，模型在这一轮里就看不到失败原因了，只能瞎改。
- 怎么改：只在最近一次 build 的结果是"新通过了阶段、停在一个还没写的阶段"（`reason == "not_ready"`）时折叠；其他情况先不折叠，通过的阶段记下来，等下一次干净地停下时一起写进小结（只写那时仍是"已通过"的阶段，按计划里的顺序）。小结的文字格式不变，测试 `test_passed_stage_is_folded`、`test_fold_keeps_prefix_stable_inside_a_stage` 都照计划写、照常通过；`test_gate_failure_goes_back_to_model` 能在第 4 次调用模型时看到终检没过的 build 返回，就是靠这一条。stage 日志在 build 当时就写，不受折叠时机影响。
- 影响：只影响 Task 10 的折叠时机，没有改任何接口和原文。

## D13（第二版计划 1 Task 14）自带案例 gear-rack 换成 ring-gear（内齿圈）

- 原计划：Task 14 的 8 个自带案例里有 `gear-rack`：标准件直齿条加两个安装孔，示范"标准件"。
- 实际情况：Task 1 探测（笔记第 21 节）发现 SCA 2.2.7 的 `make_spur_rack_rsolid` 做出的齿条 `valid=False`（三组参数都一样，`BRepCheck_Analyzer` 也判无效），减孔后仍无效，和方块 `union_rsolid` 60 秒内不返回；Task 14 补测 `make_helical_rack_rsolid` 也是 `valid=False`。用它做的案例过不了"实体有效"这条必做检查，不是我们能修的。
- 怎么改：这是计划修订，由写计划的规划会话决定（选项 A），不是执行时自己定的。案例换成 `ring-gear`「内齿圈：标准件内齿圈加外圈上一圈安装孔」，做法仍是"标准件"（`make_spur_ring_gear_rsolid`，实测有效，写法补进笔记第 21 节）；它和评测任务的直齿轮不是同一个零件。没选的两种：自己用草图画齿条齿形（和提示词"标准件不要自己画齿形"冲突）、换成斜齿轮（离评测的直齿轮太近）。
- 影响：计划 1 Task 14 的 id 表那一行已同步修改；`tests/test_builtin_cases.py::test_there_are_eight_builtin_cases` 的 id 集合用 `ring-gear` 代替 `gear-rack`，`test_builtin_cases_are_not_benchmark_tasks` 照常要过，断言没有放松。

## D14（第二版计划 2 Task 1）Claude 适配层：不发 temperature；工具调用那一轮原样放回思考块

- 原计划：`AnthropicLLM.__init__` 有 `temperature: float = 0.2`（Task 4 的 Interfaces），转换规则里没有提到思考块；内部的 assistant 消息只有 `content` 和 `tool_calls`。
- 实际情况（查文档，笔记第 8 节第 11、13 条）：
  1. 新模型（Opus 5.5、Sonnet 5.5、Haiku 5.5 等）上非默认的 `temperature` 一律 400；API 版本 `2026-10-21` 起带上 `temperature` 就 400，不论取值。
  2. Claude 5 系列默认开着思考；工具调用那一轮里，assistant 消息的思考块必须原样放回，不能改、不能只放一部分。内部的 OpenAI 写法没有地方放思考块，照计划转换会丢掉它们。
- 怎么改：接口一字不改。
  1. `temperature` 参数照收，保存在实例上，但不放进请求体；笔记里写明原因。
  2. `AnthropicLLM` 自己记住最近几次回复的原始内容块（按这次回复里工具调用的 id 记）；转换消息时，`tool_calls` 的 id 和记下的某次回复完全一致的 assistant 消息，换成那次回复的全部原始块（思考块、文字块、工具调用块，原样）。对不上的（比如从日志恢复的会话）照计划的规则转换。模块级的 `to_anthropic_messages` 不变，只做计划写的转换。
- 影响：只影响计划 2 Task 4；没有用真实接口验证过（笔记第 8 节）。

## D15（第二版计划 3 Task 1）`test_public_mode_is_gone` 搜关键词时跳过 three.js
- 原计划：`cad_agent/web/` 和 `site/` 下的文件里搜不到 `password`、`live.json`、`budget` 这三个词。
- 实际情况：`static/vendor/three/three.module.js`（three.js r160 原样，第三方文件）第 20610 行有一句代码注释 `(not to blow over maxLights budget)`，和公网隧道无关；这个文件不能改。
- 怎么改：测试跳过 `vendor/` 目录下的第三方文件，其余文件照计划搜。另外 argparse 自带的报错是英文，`python -m cad_agent.web` 的参数解析器把 "unrecognized arguments" 换成"不认识的参数"，让计划写的那句提示成立。
- 影响：只影响这一条测试；后面的任务不受影响。

## D16（第二版计划 4 Task 3）默认来源是 git 地址，但电脑上没有 git 时改用同一标签的压缩包
- 原计划：`CALIPER_SOURCE` 的默认值是 `git+https://github.com/DingZhen-zhr/computer-graphics-project@v2.0.0`，安装就是 `uv tool install --python 3.12 --force <来源>`。
- 实际情况：uv 从 git 地址安装时要调用电脑上的 git 程序（文档没写；本机实测把 git 从 PATH 拿掉后报 `Git executable not found`，见 `docs/install-notes.md` 第 2 节）。干净的 Windows 电脑通常没有 git；Mac 没装命令行工具时 `/usr/bin/git` 只是个一运行就弹窗的占位。照原样做，成功标准 4（干净的 Windows 机器一行命令装好）达不成。
- 怎么改：默认值和变量名一字不改（`test_default_source_is_the_release_tag` 照计划断言）。只多一步：来源是默认的 git 地址、而且找不到可用的 git 时，脚本打印一句说明，改用同一个标签的压缩包 `caliper-cad @ https://github.com/DingZhen-zhr/computer-graphics-project/archive/refs/tags/v2.0.0.zip`；用户自己设的 git 地址找不到 git 时，说明原因并停下。
- 影响：Task 3 的两个脚本；Task 7 README"装不上怎么办"一节提一句；Task 8 发布时这个压缩包地址随标签自动生效，不用另外上传。

## D17（第二版计划 4 Task 3）install.ps1 不带 BOM；本地运行改用"按 UTF-8 读进来再执行"，不用 -File
- 原计划：Task 3 Step 4 在本机用 `powershell -ExecutionPolicy Bypass -File install.ps1` 实测；`test_ps1_parses` 用 PowerShell 的语法解析器解析 `install.ps1`。
- 实际情况（本机实测，Windows PowerShell 5.1，中文系统）：
  1. 文件带 UTF-8 BOM 时，用户的用法 `irm … | iex` 会把 BOM 和第一个词连在一起当成命令名，开头先报一行红字"The term '﻿#' is not recognized"，后面才照常运行。试了五种第一行的写法都躲不开。
  2. 文件不带 BOM 时，`-File` 和 `Parser::ParseFile` 会按系统编码（中文 Windows 是 936）读，中文全乱，直接报语法错误。
  两者不能兼得。主要的用法（README 的一行命令、`caliper update`）都是 `irm | iex`，它按服务器给的 `charset=utf-8` 解码，不带 BOM 时完全正常。
- 怎么改：`install.ps1` 存成不带 BOM 的 UTF-8（文件开头写明原因和本地运行的办法）。本地运行一律用 `Get-Content -Raw -Encoding UTF8 .\install.ps1 | iex`：本机实测（Task 3 Step 4）、持续集成（Task 4）、README 的离线安装办法（Task 7）都这样写。`test_ps1_parses` 改成按 UTF-8 读出文字后交给同一个解析器的 `ParseInput`；演示模式的测试也用这种方式运行。另外加一条测试：`install.ps1` 不能带 BOM；经 `iex` 运行时标准错误输出必须是空的。
- 影响：Task 3 的测试和本机实测命令；Task 4 的 `ci.yml`；Task 7 README"装不上怎么办"。PowerShell 7（pwsh）默认按 UTF-8 读，`-File` 在那里没有这个问题。

## D18（第二版计划 4 Task 4）持续集成的 Mac 机器从 macos-14 改成 macos-15（用户定的）
- 原计划：Task 4 的 Interfaces 写明矩阵是 `windows-latest`、`macos-14`；设计文档第 6.4 节也写的 `macos-14`。
- 实际情况：第一次推送后（运行 44530868432），Mac 那一台没有开始就被取消，GitHub 的报错是 `The configuration 'macos-14-arm64-us-default' is not supported`。查 GitHub 官方的 runner-images 说明（2026-11-20）：macOS 14 标着已弃用，只剩 x64（Intel）版；Apple 芯片的只有 `macos-15`、`macos-26`（也就是 `macos-latest`）。
- 怎么改：这是 Interfaces 里的内容，所以先问了用户；用户选了 `macos-15`（还能用的 Apple 芯片镜像里版本最低的，最接近我们支持的下限 macOS 14，而且写死版本不会自己变）。`ci.yml` 的矩阵和 `test_matrix_has_both_platforms` 的断言一起改成 `["windows-latest", "macos-15"]`。
- 影响：持续集成不再覆盖 macOS 14 本身；macOS 14 只靠组员按 `docs/mac-checklist.md` 人工验证（如果组员的 Mac 是 14）。README"验证到什么程度"一节照这个写（Task 7）。

## D19（第二版计划 4 Task 6）`tests/test_desk_static.py` 的"自己写的文件"不算 three.js
- 原计划：Task 6 把 three.js 的四个文件搬到 `cad_agent/desk/static/vendor/three/`；旧测试只有计划表格里列出的才能改。
- 实际情况：`test_desk_static.py` 用一个小函数 `_own_files` 收集 `desk/static/` 下面的全部文件，再检查"没有网址""不超过 300 行""脚本里没有颜色字面值"。three.js 搬进来以后，它这几条都不满足（第三方文件里有网址注释、上万行、颜色常量），而这些规矩本来就只管我们自己写的文件。three.js 原样保存，不能改。
- 怎么改：只改 `_own_files` 一处，跳过 `vendor/` 下面的文件；三条测试的断言一个字没动。和 D15 是同一个道理。另外 `test_desk_export.py` 和 `test_desk_legacy.py::test_old_web_package_is_gone` 会检查 three.js 确实在新位置、`REVISION` 仍是 `'160'`。
- 影响：只影响这一个测试文件。

## D20（第二版计划 4 Task 4，持续集成第三次运行）Windows 的快捷方式改用 IShellLinkW，不用 WScript.Shell
- 原计划：Task 3 第 4 步"Windows 用 `WScript.Shell` 建两个 `.lnk`"。
- 实际情况：持续集成的 Windows 机器是英文系统，`WScript.Shell` 把"卡尺 Caliper.lnk"存成了"?? Caliper.lnk"，报"Unable to save shortcut"，安装停在第 4 步。本机用系统编码（GBK）表示不了的泰文复现：文件名里有这种字时存不了；目标路径里有这种字时设置目标就报错。也就是说，凡是系统编码表示不了的字都会出问题：英文 Windows 上的"卡尺"、用户名里有这种字时的目标路径。中文 Windows 上用"卡尺"这个名字不会出问题，所以之前本机实测没发现。
- 怎么改：`install.ps1` 里加一个函数 `New-CaliperShortcut`，用 Windows PowerShell 5.1 自带的 `Add-Type` 编译一小段 C#，直接调 Windows 的 Unicode 接口 IShellLinkW 建快捷方式（目标、工作目录、说明、图标和以前一样）。不需要新的依赖。快捷方式的名字和位置不变，`maintenance.shortcut_paths()` 不用改。
- 测试：加了 `test_ps1_shortcut_handles_characters_outside_the_code_page`，名字、目标、工作目录、说明、图标路径全用泰文，建好后用 Shell.Application 读回来逐项核对。先看到它失败，再改。
- 影响：只影响 `install.ps1` 的第 4 步。计划 4 后面的任务不受影响。

## D21（第二版计划 4 Task 8）先发布 v2.0.0，Mac 人工清单之后补

- 原计划：Task 8 Step 1 要求 Mac 人工清单填好交回之后，才推送并打 `v2.0.0` 标签；清单没交回就停在这里。
- 实际情况：2026-11-20 清单还没有交回（16 项都没勾）。持续集成在 Windows 和 Mac（macOS 15，Apple 芯片）上都已通过。没有标签，README 里公开的那一行安装命令装不上。
- 怎么改：用户本人决定先发布，原话是"先发布，Mac 后补"。由规划会话执行：发布前重跑全部测试，推送 master，打 `v2.0.0` 标签并推送，再从 GitHub 按公开的安装命令实际装一次做验证。README"验证到什么程度"一节本来就写着"Mac 界面还没有人工看过"，不用改。
- 影响：Task 8 Step 2（根据 Mac 清单更新 README）挪到清单交回之后再做；清单里发现的问题按需要发 `v2.0.1` 之类的补丁版本。成功标准里"Mac 清单勾完"这一条暂时没有达成。

## D22（3.0 计划 1 Task 1）清单里两个测试文件多改了一处名字；在线示例跟着重新导出

- 原计划："要改的旧测试"清单里，`tests/test_desk_server.py` 只写了请求头 `X-Caliper-Token` → `X-Datum-Token`；`tests/test_maintenance.py` 写了数据目录、版本号、包名、快捷方式名等。Task 1 的文件清单里没有 `site/demo/`。
- 实际情况：
  1. `test_desk_server.py::test_reload_without_token_gets_recovery_page` 断言恢复页里有"从卡尺的窗口里打开"。Task 1 的新测试 `test_no_old_name_outside_migration` 要求 `cad_agent/` 里除迁移代码外不能有"卡尺"两个字，两条测试不能同时满足。
  2. `test_maintenance.py::test_pyproject_name_and_version` 断言描述里有"卡尺"；计划要求描述改成 Datum 的一句话。Mac 应用名 `Caliper.app` 也在这个文件里，计划没单列。
  3. `test_desk_export.py::test_site_is_up_to_date` 要求 `site/demo/` 和重新导出的结果逐字节相同。页面标题、脚本改了名字以后，不重新导出这条测试必然失败。
- 怎么改：
  1. 恢复页那条断言改成"从 Datum 的窗口里打开"；
  2. 描述那条改成断言有"基准"，`Caliper.app` 改成 `Datum.app`（和 Task 5 的 Interfaces 一致）。
  都只是把旧名字换成新名字，断言的其余部分一个字没动。这两个文件本来就在清单里，只是"改什么"一栏没写全，所以没有停下来问。
  3. 用测试提示的命令 `python -m cad_agent.desk.export cad_agent/desk/demo_data/phone_stand site/demo` 重新导出，变化只有 8 个文件里的名字和令牌请求头的写法。只提交到本地；更新 GitHub Pages 仍是计划 5 的事。
- 影响：计划 5 Task 5 重写主页、README 时还会再导出一次在线示例，不受影响。

## D23（3.0 计划 1 Task 1）安装脚本的默认来源提前改成 v3.0.0

- 原计划：安装脚本的默认来源改成 `@v3.0.0`（压缩包备用地址同步改），写在 Task 5 的 Interfaces 里。
- 实际情况：旧测试 `test_install_scripts.py::test_default_source_is_the_release_tag` 断言默认来源是 `@v{__version__}`。Task 1 把版本号改成 3.0.0 以后，这条测试马上变红。它不在"要改的旧测试"清单里，而且断言本身是对的，只能改实现。
- 怎么改：Task 1 里只改两个脚本的三处：默认来源 `@v3.0.0`、压缩包地址 `datum-cad @ …/v3.0.0.zip`（v3 的压缩包里包名是 `datum-cad`，名字对不上 uv 会报错）、开头注释里的标签。其余（环境变量、快捷方式、进程名、发现旧版）仍在 Task 5 做。
- 影响：Task 1 到 Task 4 的提交里，安装脚本装的是 `datum-cad`，但快捷方式、自检那几步还在找 `caliper` 的文件，真的运行会在第 4 步出问题。这几个提交只在本地，不推送；Task 5 一起改齐。Task 5 的新测试 `test_default_source_is_v3_tag` 写好时就会通过，这是预料之中的，不说明测试没用。

## D24（3.0 计划 1 Task 3）每个服务只从旧服务名回退一次；删 key 后不再复制回来（规划会话修订）

- 原计划：Task 3 的 Interfaces 写的是：取 key 的顺序是"环境变量 → 新服务名 `datum` → 旧服务名 `caliper`"，从旧的取到就复制一份到新的；`set_key`、`delete_key` 只动新服务名；旧服务名里的 key 不删。
- 发现的问题（实现 Task 3 时发现，报告给了规划会话）：设置页有"删除 key"。升级用户的旧服务名里有 key 时，在 Datum 里删 key 只删掉了新服务名里的那份；设置页紧接着查 key 的来源，又从旧服务名里找到、复制回来。用户看到的是 key 删不掉。
- 怎么改（规划会话给的修订，不是用户本人的回复；规划会话说会告诉用户）：
  1. 数据目录里记一个小文件 `key_migration.json`，内容是 `{预设 id: true}`。`get_key`、`key_source` 只有在这个服务还没记过时，才去旧服务名找；找到并复制到新服务名后记上。复制失败不记，下次还会再试。
  2. `delete_key` 删掉新服务名里的 key；旧服务名里还有这个服务的 key 时，把它记成"回退过"，删掉后不会再复制回来。旧服务名里的 key 照旧不删。
  3. 文件读不出来、内容不对时当作没记过，不抛异常、不挡住取 key（日志里记一条）；写文件失败只在日志里记一条。
  4. 函数签名都不变。
  - 我加的一条：只有旧服务名里确实有这个服务的 key 时，`delete_key` 才写这个文件。这样旧测试里没有设 `DATUM_HOME` 的删 key 调用不会在真实的数据目录里写东西（那会建出 `Datum` 目录，挡住数据目录的迁移）；没有旧 key 时本来也不存在"复制回来"的问题。
- 测试：规划会话要求的 `test_deleted_key_does_not_come_back`、`test_fallback_only_once_per_provider`、`test_marker_file_corrupt_is_ignored`、`test_copy_failure_does_not_mark`，另加 `test_delete_before_any_fallback_also_blocks_it`、`test_marker_write_failure_only_logs`、`test_no_marker_written_without_old_key`。
- 影响：只影响 Task 3 和设置页删 key 的行为。`datum uninstall --delete-data` 会连这个文件一起删掉；之后重新安装，旧服务名里的 key 会再被复制一次，这和"旧的不删"的规矩一致。

## D25（3.0 计划 1 Task 5）改 `test_reinstall_keeps_data` 的辅助函数（计划漏列，用户同意）

- 原计划："要改的旧测试"清单里，`tests/test_install_scripts.py` 只写了环境变量名和 `test_ps1_stops_when_caliper_is_running` 的进程名。
- 实际情况：同一个文件里的 `test_reinstall_keeps_data`（辅助函数 `_reinstall_problems`）要求：`install.sh` 里有 `APP="${HOME}/Applications/Caliper.app"`；`install.ps1` 的代码里不能出现 `Remove-Item`/`del`/`rmdir`；两个脚本的代码行里不能出现 `uv tool uninstall`。而 Task 5 要求 Mac 应用改名 `Datum.app`、删掉旧快捷方式、打印含 `uv tool uninstall caliper-cad` 的提示。不改这条测试就做不了，计划漏列了它。
- 怎么改（规划会话提议，用户本人在本会话里回答"Yes, change it"同意）：
  1. `Caliper.app` → `Datum.app`；
  2. 只额外放行删旧快捷方式这一个目标：`install.ps1` 只允许 `Remove-Item -LiteralPath $OldShortcut -Force` 这一行，`install.sh` 的允许删除集合加 `"${OLD_APP}"`，其余删除照旧不允许；
  3. 先把提示旧版的那句原文（`OLD_VERSION_HINT`）去掉再查，`uv tool uninstall` 不能作为命令执行。查的词从 `uv tool uninstall` 改成 `tool uninstall`，`"${UV}" tool uninstall` 这种写法也能查出来，比原来更严。
  原有两条反向检查不动；新加两条：在脚本里真的执行卸载旧版（PowerShell 和 sh 各一条），要被查出来。
- 影响：只影响这一条测试和 Task 5 的两个安装脚本。

## D26（3.0 计划 2 Task 2）`parts`、`motions` 放在 `PATCH_KEYS` 的 `relations` 前面
- 原计划：`PATCH_KEYS` 末尾加 `"parts"`、`"motions"`。
- 实际：第二版的旧测试 `test_patch_keys_end_with_relations` 要求最后一个是 `relations`，它不在"要改的旧测试"清单里。
- 改法：两个新键插在 `relations` 前面。键的顺序只影响报错里列出可用字段的顺序。
- 另外：`brief.py` 加完会超过 300 行，零件的解析和显示放进新文件 `cad_agent/brief_parts.py`；材料表 `cad_agent/product/materials.py` 提前在本任务建好（Task 3 只加测试）。
- 影响：无。
