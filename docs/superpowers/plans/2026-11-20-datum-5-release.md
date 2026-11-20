# 3.0 · 计划 5：提交材料与发布 · 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal：** 把作业要交的东西一次备齐（提交材料一键整理、提示词与工具定义文档、演示脚本、实验报告初稿），主页和 README 换成 Datum 3.0，持续集成和 Mac 清单跟上，最后发布 `v3.0.0`。

**Architecture：** 提交材料由一个新模块从会话目录和仓库里收集，命令行和桌面端菜单共用它。提示词与工具定义文档由脚本从代码生成，测试保证它和代码一致。

**Tech Stack：** 不新增依赖。

**Spec：** `docs/superpowers/specs/2026-11-20-datum-v3-design.md`（第 9、10、11 节）。

**前置：** 计划 1–4 全部完成。

## Global Constraints

- 前几版计划的规矩全部继续有效（见 `CLAUDE.md`）。
- **停下来问用户的地方**（每次单独问，不能拿别处、别次的同意代替）：真实模型的演示预演（花钱）、推送到 GitHub、更新 GitHub Pages、打 `v3.0.0` 标签、在一台新电脑上实际安装。
- 提交材料、文档、主页里**没有任何 key**，也没有用户名、本机绝对路径。
- 报告和 README 里的数字只引用 `docs/results-v3.md` 里有的；没有数据的地方照实写"没有测"。
- 偏离记录接着编号。每个任务收尾：全部测试通过 → 提交 → `docs/progress.md` 追加一段（标题写"3.0 计划 5 Task N"）。

## Review Focus

1. 用户选的会话里有一个还没交付过任何版本：提交材料里照样带上它的对话记录，但在清单里标明"这个会话没有交付版本"，不报错退出。→ Task 1 `test_session_without_versions_is_listed`
2. 提交材料的目标文件夹已经存在：不覆盖，新建一个带序号的文件夹。→ Task 1 `test_existing_target_is_not_overwritten`
3. 会话日志里混进了 key（比如以前的某个错误信息）：整理时发现就停下，说明是哪个文件哪一行，不生成提交包。→ Task 1 `test_key_in_session_blocks_export`
4. 代码里的提示词改了、文档没重新生成：测试失败并提示重新运行生成脚本。→ Task 2 `test_prompts_doc_up_to_date`

---

### Task 1：一键整理提交材料

**Files：** Create `cad_agent/submission.py`、`tests/test_submission.py`；Modify `cad_agent/app.py`（子命令）、`cad_agent/desk/routes.py`、`cad_agent/desk/static/js/menu.js`（菜单项和勾选会话的对话框）

**Interfaces：**
- `build_submission(sessions: list[Path], target: Path, *, repo_root: Path) -> SubmissionReport`；`SubmissionReport`：`folder: Path`、`items: list[dict]`（每项：要求、放在哪里、状态）、`warnings: list[str]`。
- 命令 `datum submission <目录> [--session <会话编号> ...]`（不给会话就带上全部有交付版本的会话）。桌面端菜单"整理提交材料"：勾选会话，点"整理"后在数据目录的 `submissions/<时间>/` 生成，并在文件管理器里打开。
- 文件夹结构（名字照抄）：
  ```
  01-代码/                 仓库里 cad_agent、benchmarks、scripts、tests 的副本（不含 .venv、__pycache__、sessions、benchmarks/results）
  02-提示词与工具定义/      docs/prompts-and-tools.md（Task 2）
  03-测试需求与验收结果/    benchmarks/tasks/*.yaml、docs/results-v3.md、各轮的 results.json 和 results.md
  04-参数化源文件与STEP/    每个选中会话的每个版本：model.py 或 parts/*/model.py 和 assembly.py、*.step、*.stl、view.png
  05-运行日志/             每个选中会话的 log.jsonl、brief.json、checks.json
  06-配置和运行说明/        config.example.toml、README.md、docs/install-notes.md
  清单.md                  逐条对照设计文档第 9 节"提交"几行：要求、放在哪个文件夹、状态
  ```
- 整理前对所有要复制的文本文件搜一遍：环境变量里所有名字含 `KEY`、`TOKEN` 的变量的值、以及钥匙串里存的 key（用 `keystore.get_key` 取，只在内存里比较）。搜到就停下，`warnings` 里写文件和行号，不生成（Review Focus 3）。

- [ ] **Step 1：** 写测试：`test_layout_and_checklist`；`test_session_without_versions_is_listed`（Review Focus 1）；`test_existing_target_is_not_overwritten`（Review Focus 2）；`test_key_in_session_blocks_export`（Review Focus 3）；`test_no_absolute_paths_in_checklist`；`test_multipart_session_files`；`test_command_line`；`test_desk_endpoint`。
- [ ] **Step 2：** 运行，确认失败；实现；在应用内置浏览器里走一遍菜单的勾选和整理；运行全部测试，提交：`feat: 一键整理作业提交材料`。

---

### Task 2：提示词与工具定义文档

**Files：** Create `scripts/export_prompts.py`、`docs/prompts-and-tools.md`（生成）、`tests/test_prompts_doc.py`

- 文档结构（标题照抄）：`# 提示词与工具定义`、`## 系统提示词`（按 `load_system_prompt(True)` 的顺序，每段一个小节，标出来源文件）、`## 工具定义`（17 个工具，每个：名字、说明、参数的 JSON）、`## 程序生成给模型的消息`（快照、阶段小结、零件小结、build 和 build_assembly 的返回格式和提示原文，从代码里的常量取）、`## 模拟用户的提示词`。
- [ ] **Step 1：** 写测试：`test_prompts_doc_up_to_date`（Review Focus 4：重新生成一遍和仓库里的逐字相同）；`test_doc_has_all_tools`；`test_doc_has_no_key`。
- [ ] **Step 2：** 运行，确认失败；实现并生成；运行全部测试，提交：`docs: 从代码生成提示词与工具定义文档`。

---

### Task 3：演示脚本和实验报告初稿

**Files：** Create `docs/demo-script.md`、`docs/report-draft.md`、`tests/test_report_docs.py`

- `docs/demo-script.md`：按作业要求的四个镜头，每个镜头写：要说的话、要点哪里、预计看到什么、大概多少秒。
  1. 需求输入：从一句模糊的话开始（用"带铰链盖的工具盒"），展示模型提问、需求单在舞台中间填起来、区分"你给的"和"建议"。
  2. 自动建模：确认后零件一个个做出来，左边零件清单逐个打勾，装起来，运动条从头播放到尾。
  3. 反馈修正：打开对话记录，展开一次"量出来不对 → 自己改好"的过程。说明：如果这次录制刚好没有出现修复，就打开第二轮评测里一次真实的修复记录（写明是哪个结果目录、哪个任务）。
  4. 多轮修改：对话里说"盖子最多翻到 95 度"，再用调参数改一次盒子高度，最后用对比看 v1 和 v3。
  另写一段"单零件版"（手机支架），时间不够时用。最后写录制前的检查清单（key 已存、价目表已填、空闲时段、网络、窗口大小）。
- `docs/report-draft.md`：按 4–6 页的篇幅写（约 4000–6000 字加图）。标题照抄：`## 1 系统设计`（流程、程序管关卡、分阶段、终检、沙盒、检查、多零件与运动、界面；配一张流程图，用 Markdown 里的文字框图）、`## 2 测试与结果`（引用 `docs/results-v3.md` 的表，写失败分析的结论）、`## 3 自主完成的工作`（逐个模块列出：做了什么、对应哪些文件、参考了什么——SCA 官方 skill 的方法、teardown 的展示方式，都写明是参考不是照搬）、`## 4 成员分工`（只留表头和"请填写"，不编内容）、`## 5 不足与后续`。
- [ ] **Step 1：** 写测试：两份文档的标题齐全；报告里出现的每一个"x/y"形式的成功数，都能在 `docs/results-v3.md` 里找到；成员分工一节没有人名；没有 key。
- [ ] **Step 2：** 运行，确认失败；写文档；运行全部测试，提交：`docs: 演示脚本和实验报告初稿`。

---

### Task 4：演示预演（花钱，先问用户）

- [ ] **Step 1：** **停下来问用户**：要不要在录视频之前用真实模型把 `docs/demo-script.md` 的工具盒走一遍，确认现场不会卡住；预计约 ¥1，记进计划 4 的账本（标签 `demo`），账本余额多少。用户不要就跳过，在 `docs/progress.md` 里记下。
- [ ] **Step 2：** 用户同意后，在桌面窗口里照脚本走一遍（模型调用经过账本计费的方式见计划 4 Task 1；桌面端没有接账本的话，在开始前后各看一次 DeepSeek 后台的余额，写进进度记录）。走不通的地方记下来，修好后**不再自动重跑**，告诉用户是否需要再预演一次。
- [ ] **Step 3：** 把这次的会话目录编号写进 `docs/demo-script.md` 的末尾，供录制时参考；提交：`docs: 演示预演记录`。

---

### Task 5：主页、在线示例、README、持续集成、Mac 清单

**Files：** Modify `site/index.html`、`site/demo/`（重新导出）、`cad_agent/desk/export.py`（如果新界面的静态模式需要调整）、`README.md`、`.github/workflows/ci.yml`、`docs/mac-checklist.md`、`tests/test_readme.py`、`tests/test_desk_export.py`（只改名字和结构相关的字面值）

- 主页：展台风格（浅色影棚，跟随系统切深色），一句话介绍、两条安装命令（指向 `v3.0.0`）、系统要求、"它怎么工作"（问清楚 → 确认 → 一步步做、每步实测 → 多个零件装起来、动起来检查 → 交付）、在线示例链接。主页上的数字只用 `docs/results-v3.md` 里有的；不写成功率时就不写。
- 在线示例：用计划 4 评测里一次成功的**多零件**真实会话重新导出 `site/demo/`（静态模式只读，能转 3D、播放运动、看检查和版本）；没有成功的多零件会话时，用一次成功的单零件会话，并在 `docs/progress.md` 里写明。
- README：标题 `# Datum 基准`；在"怎么用"里加"多个零件和会动的东西"一节；"它是怎么保证质量的"加装配和运动检查；"验证到什么程度"用计划 4 写好的数字；"参考与致谢"加 teardown。
- 持续集成：两个平台照旧；把多零件的 `sca` 测试也跑上（耗时增加就把超时调大，写明调到多少）。
- Mac 清单：加多零件的几项（零件清单、运动播放、炸开、透视、对比）。
- [ ] **Step 1：** 按需要改 `tests/test_readme.py`、`tests/test_desk_export.py`（只改名字和结构字面值，断言强度不变）；写新测试：主页的安装命令指向 `v3.0.0`；在线示例的状态里有 `product`（多零件时）；README 没有"卡尺"两个字。
- [ ] **Step 2：** 运行，确认失败；实现；在本地用静态文件服务打开 `site/`，主页和在线示例都看一遍（浅色、深色）；运行全部测试，提交：`docs: 主页、在线示例、README 和 Mac 清单换成 3.0`。

---

### Task 6：发布

- [ ] **Step 1：** 确认：全部测试通过；`docs/results-v3.md` 写完；走查记录（计划 3）写完。
- [ ] **Step 2：** **停下来问用户：可以推送吗？** 说明会推送哪些提交、会触发持续集成和主页更新。同意后推送，请用户看持续集成的结果（或把失败日志贴回来）；失败就修，每次重推都再问。
- [ ] **Step 3：** **停下来问用户：可以打 `v3.0.0` 标签吗？** 说明安装脚本默认装的就是这个标签。同意后打标签、推送标签。
- [ ] **Step 4：** **问用户怎么安排新电脑上的安装验证**（组员的电脑，或者在这台电脑上新建一个 Windows 用户）。按用户的安排，用 README 的那一行命令从 GitHub 实际装一次，`datum doctor` 全部正常、能打开窗口。结果写进 `docs/progress.md`。
- [ ] **Step 5：** 提醒用户：Mac 清单（含多零件的新项目）请有 M 芯片 Mac 的组员走一遍；交回后更新 README 里关于 Mac 的那一句。
- [ ] **Step 6：** `docs/progress.md` 写"3.0 小结"：五份计划的测试数、全部偏离编号、设计文档第 9 节每一行的最终状态、花费汇总、没做到的地方。提交：`docs: 3.0 小结`。
