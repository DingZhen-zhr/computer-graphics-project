# Datum 基准（AICG Project 3）· 给 AI 编程工具的执行规则（Mac 版）

这份文件给 Codex、Antigravity 等工具读。`CLAUDE.md` 是之前在 Windows 上用 Claude Code 时的同一套规则；**在 Mac 上以这份为准**，两份冲突时听这份。

## 这是什么项目

课程作业：用 SimpleCADAPI（SCA）2.2.7 做一个 CAD 建模智能体，做成了一行命令安装的桌面应用。第二版叫"卡尺 Caliper"（已发布 v2.0.0），**3.0 版改名为 Datum 基准**。用户用一句中文描述零件，智能体问清需求、分阶段建模、自己量尺寸检查、交付 STEP/STL；3.0 支持多个零件装配和会动的关节。

设计和计划都已经定好，你的任务是**严格照计划把剩下的做完**，不重新设计、不加计划之外的功能。

## 现在做到哪了（2026-11-23 从 Windows 迁到 Mac 时）

- 计划 1–4 全部做完；计划 5 的 Task 1、2、3、5 做完；计划 6 的 Task 1–5 做完。代码已全部推到 GitHub `master`。
- 最近一次完整全量（含真实 SCA）在 Windows 上是 1323 个通过；快速全量 1170 个通过（计划 6 之后数量会更多，以实际为准）。
- 真实模型花费：实际扣费约 ¥14.75，上限 ¥20，**只剩约 ¥5.25**。账本 `benchmarks/results/ledger-v3.json` 记的是 22.26（第一轮按高峰价多记了），所以计划 6 Task 6 的命令用 `--cap 27.5`。
- 详细记录在 `docs/progress.md` 最后几节。

## 怎么接着做（用户只会说一句"继续"）

用户不会每次告诉你做哪一件。每次开始时：

1. 看下面"剩下的事"清单，**第一个还是 `- [ ]` 的就是现在要做的**。
2. 照那一项做。做完、提交以后，把那一项改成 `- [x]`，后面写上日期和一句结果，和那件事的提交放在一起（或单独提交 `docs: 更新剩下的事清单 [skip ci]`）。
3. **不用等用户，直接接着做下一项。** 只在三种地方停下来：清单里写着"停下来问"的；下面"遇到这些情况，停下来问用户"列出的；需要用户本人动手的（点界面、点系统弹窗、设 key）。停下来时用一两句话说清楚：现在在第几项、要用户做什么或回答什么。
4. 用户回答后，从停下的地方接着做。用户说"跳过"，就把那一项写成 `- [x] 跳过（用户决定）`，接着做下一项。

**剩下的事（按顺序）：**

- [x] 1. **搭开发环境。**（2026-11-25 完成：git 2.53.0、uv 0.13.5、node v25.8.2，建好 Python 3.12.15 `.venv` 并安装全部依赖，已解压 `mac-transfer.zip` 至仓库根目录，`config.toml` 与 `ledger-v3.json` 就位） 如果 `.venv/bin/python` 不存在：检查 `git --version`、`uv --version`、`node -v`（要 22 开头）。缺 git 就让用户运行 `xcode-select --install` 并在弹窗里点"安装"；缺 uv 就运行 `curl -LsSf https://astral.sh/uv/install.sh | sh`（之后用 `~/.local/bin/uv`）；缺 Node 22 就停下来，请用户去 https://nodejs.org 下载 22 版的 macOS 安装包装上。然后运行 `uv venv --python 3.12` 和 `uv pip install -e ".[dev]"`。再确认 `config.toml` 和 `benchmarks/results/ledger-v3.json` 在；不在的话，用户说过压缩包在哪（默认 `~/Downloads/mac-transfer.zip`）就自己解压到仓库根目录（`unzip <zip 的路径> -d .`）；找不到压缩包就停下来问。
- [x] 2. **确认迁移没问题。**（2026-11-28 完成：经用户同意应用 1A+2A+3 修复并记 D47，快速全量 1175 passed / 5 skipped，完整全量 1328 passed / 5 skipped，全部通过） 跑一次快速全量和一次完整全量（见下面"Mac 上的命令"）。都通过：在 `docs/progress.md` 末尾加一节"迁到 Mac"（测试数量、macOS 版本），提交 `docs: 迁到 Mac，测试全部通过 [skip ci]`。有失败：不要改代码，**停下来问**，把失败的测试名和报错原样列给用户，说明是 Mac 特有的问题还是代码问题、打算怎么改，用户同意再改。
- [x] 3. **计划 6 Task 6**：跳过（用户决定，2026-11-28；不再花钱跑第三轮真实模型验证）
- [x] 4. **计划 6 Task 7**：收尾（2026-11-28 完成：完整全量 1328 passed / 5 skipped 无代码改动沿用同日结果，`docs/progress.md` 已写计划 6 小结并提交 `docs: 向老师平台学的三处做完 [skip ci]`；待用户确认是否推送） 完整全量、progress 小结、提交。最后**停下来问**要不要推送。
- [ ] 5. **Mac 人工清单** `docs/mac-checklist.md`：要**用户本人**点界面。一项一项带着用户做：每次只说下一项运行什么命令、点哪里、看什么，等用户说看到了什么，再把那一项改成 `[x]` 并写上用户说的话。用户没说看到的项不要勾。全部做完后照计划 5 Task 6 Step 5 更新 README 里关于 Mac 的那一句，提交 `docs: Mac 人工清单做完 [skip ci]`。
- [ ] 6. **计划 5 Task 4**：演示预演（花钱，约 ¥1）。**停下来问**要不要做、告诉用户账本余额；用户不要就在 progress 里记"跳过"。
- [ ] 7. **计划 5 Task 6**：发布。推送、打 `v3.0.0` 标签、更新主页，**每一步之前都单独停下来问**。安装验证就用这台 Mac：用 README 里 Mac 那一行命令从 GitHub 实际装一次，`datum doctor` 全部正常、能打开窗口。最后照 Step 6 写"3.0 小结"并提交。
- [ ] 8. **告诉用户全部做完了**，列出：最终测试数量、花了多少钱、还有哪些没验证。

## 开工前必读（按顺序）

1. `docs/superpowers/specs/2026-11-20-datum-v3-design.md`：3.0 设计
2. 这次要做的那一份计划：
   - 计划 5：`docs/superpowers/plans/2026-11-20-datum-5-release.md`
   - 计划 6：`docs/superpowers/plans/2026-11-23-datum-6-teacher-lessons.md`
3. `docs/sca-api-notes.md`：所有 SCA 用法都以它为准
4. `docs/llm-api-notes.md`：模型接口的用法都以它为准
5. `docs/install-notes.md`：uv 和安装相关的用法
6. `docs/progress.md`：进度记录（很长，看最后几节就行）
7. `docs/deviations.md`：以前偏离计划的地方（已经到 D46，新的从 D47 开始编号）

更早的计划（`docs/superpowers/plans/` 下 11-09、11-10、11-20 的）是背景资料。

计划开头写着"REQUIRED SUB-SKILL: Use superpowers:executing-plans"——那是 Claude Code 的插件，你这里没有，意思就是：**一个任务一个任务地照计划里的勾选步骤做**。

## Mac 上的命令

计划和文档里的命令都是 Windows 写法，在 Mac 上这样换：

| 文档里写的 | Mac 上用 |
|---|---|
| `.venv\Scripts\python` | `.venv/bin/python` |
| `.venv\Scripts\datum` | `.venv/bin/datum` |
| `%LOCALAPPDATA%\Datum` | `~/Library/Application Support/Datum` |
| Windows 凭据管理器 | Mac 钥匙串 |
| "在 Bash 里跑，别在 PowerShell 里跑" | Mac 上没有这个问题，直接在终端（zsh）里跑 |

- 建开发环境（只做一次）：
  ```sh
  uv venv --python 3.12
  uv pip install -e ".[dev]"
  ```
- 快速全量（约半分钟）：`PYTHONUTF8=1 .venv/bin/python -m pytest -q -m "not sca"`
- 完整全量（含真实 SCA，约 9–10 分钟）：`PYTHONUTF8=1 .venv/bin/python -m pytest -q`
- 界面的 JS 测试由 pytest 顺带跑（`tests/test_desk_static.py`），所以电脑上要有 Node 22；单独跑一个文件：`node --test cad_agent/desk/static/js/tests/stage.test.js`
- 不花钱地看界面：`.venv/bin/datum --demo-script scripts/demo_script.json`（假模型剧本 + 真实沙盒；多零件用 `scripts/demo_script_multi.json`）
- 重新导出提示词文档：`.venv/bin/python scripts/export_prompts.py`
- Python 一律用 `.venv/bin/python`，不要往系统 Python 里装包。终端里直接敲的 `datum` 是用安装脚本装的那一份，改了代码要重新运行安装脚本它才会变。

**运行测试的规矩：**测试在前台跑，把命令超时设到 15 分钟以上；不要放到后台然后结束本轮去等，也不要发"还在跑"之类的消息；等测试的时候不要改源文件。

## 做事的规矩

1. **一次只做一个任务，按计划顺序来。** 开始每个任务前，重读该任务全文和计划里的 Global Constraints。
2. **严格先写测试。** 写测试 → 运行，**亲眼看到失败** → 写实现 → 运行，确认通过 → 提交。每个任务单独提交。
   - 测试名和断言以计划为准。可以多加测试，不能删测试，也不能把断言改松。
   - 旧测试能不能改、能不能删，只看当前这份计划写明的"要改的旧测试"清单；清单之外的一律不动。
3. **接口一字不改。** 计划中 Interfaces 块里的名字、参数、返回类型照抄。实际情况逼得必须改时：先在 `docs/deviations.md` 记一条（原计划、实际情况、怎么改、影响哪些后续任务）→ 只做最小的改动 → 同步修改受影响的后续任务描述。
4. **照抄的内容就照抄。** 计划里 ```text 和 ```json 框起来的内容逐字复制，不改写、不润色。
5. **SCA 用法不凭记忆写。** 只用 `docs/sca-api-notes.md` 里实测过的写法；笔记里没有的，先写一小段探测代码跑通，再补进笔记，然后才能用。模型接口同理。
6. **每个任务收尾：**
   - 跑这个任务自己的测试，再跑快速全量，全部通过才能提交；
   - 完整全量只在这几种时候跑：这份计划的最后一个任务；任务改了 `cad_agent/sandbox/`、`cad_agent/checks/`、`cad_agent/product/`、`cad_agent/staged/`、`benchmarks/` 或任何会真正运行 SCA 的代码；快速全量里有 `sca` 相关的失败需要确认；
   - 提交信息用计划里给的，末尾照计划加 `[skip ci]`。**不要**加 `Co-Authored-By: Claude ...` 那一行（那是给 Claude Code 用的）；
   - 在 `docs/progress.md` 追加几行：完成了哪个任务、测试数量、遇到的问题和处理方法。
7. **省时间、省额度：** 计划写清楚的地方照做，不另外加检查、探测、截图或文档；同一个问题换了两种办法还不行，就停下来问。
8. **编码：** 读写文件都显式写 `encoding="utf-8"`；子进程环境变量加 `PYTHONUTF8=1`。
9. **代码风格：** 一个文件只负责一件事，超过 300 行就拆分；函数写全类型标注；注释和面向用户的文字用中文平常话，界面上不出现程序内部的词（见设计文档第 7.9 节）。

## 绝对不要做的事

- 跳过失败的测试，或用 `skip`、`xfail` 把它藏起来。
- 为了让测试通过而放宽断言、扩大容差、删掉检查；为了让评测好看而针对评测任务写死内容。
- 用 `except: pass` 之类的写法吞掉异常不报。
- **读取、打印、记录 API key**，或把 key 写进代码、配置、日志、测试、结果文档。key 只能在环境变量和 Mac 钥匙串里。不要让用户把 key 发进对话；需要 key 的命令，让用户自己在终端里设好环境变量再运行，或者在 Datum 的设置页里填。
- **调用真实的大模型接口**（DeepSeek 等），除了计划 5 Task 4、计划 6 Task 6 这两处；每一次都要先停下来问用户，用户本人回答"可以"才跑。运行 `benchmarks.run`、点真实的"测试连接"都算调用。全部合计实际花费不超过 ¥20（现在约 ¥14.75）。
- 做计划之外的功能。图片输入、英文界面、打包成安装包都留到以后。
- 说"完成了""通过了"之前，没有亲自运行命令看到结果。没验证过的要照实写"没有验证"。

## 遇到这些情况，停下来问用户

- 计划和实际冲突，而且需要改 Interfaces 块里的接口。
- 同一个测试连续修了 3 次还是失败。
- 需要安装计划之外的依赖，或者下载计划之外的文件。
- 某一步看起来必须调用真实模型（上面两处之外），或必须用到真实的 API key。
- 计划里写明"停下来问用户"的地方：真实模型的评测和演示预演、推送到 GitHub、打标签、更新 GitHub Pages、新电脑上的安装验证。每次都要单独问，不能拿上一次的同意当这一次的同意。
- 需要删除计划清单之外的文件或测试。
- Mac 上出现了 Windows 上没有的失败（比如路径、钥匙串、pywebview 窗口）：先把失败原样告诉用户，说清楚你打算怎么改，再动手。
