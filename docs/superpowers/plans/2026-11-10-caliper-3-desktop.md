# 卡尺第二版 · 计划 3：桌面端 · 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal：** 做出卡尺的桌面窗口：左边会话历史，中间对话（逐字输出、可停止、工具调用树、阶段进度），右边工作台（3D、检查、参数直改、版本对比），加上首次引导、设置、案例库和示例会话；视觉是"图纸 / 蓝图"。

**Architecture：** 新界面放在新的包 `cad_agent/desk/` 里：一个只监听本机的 HTTP 服务（页面、接口、SSE 推送）加一套不用构建的原生 JavaScript 页面；`pywebview` 开一个原生窗口加载它。每个打开的会话是一个 `Workbench`（智能体 + 事件流 + 一个工作线程）。旧的 `cad_agent/web/` 这一份计划里只删掉公网隧道，其余原样保留，到计划 4 再退役。

**Tech Stack：** 在计划 2 的基础上新增一个依赖：`pywebview`。用户已同意。three.js r160 已在项目里（`cad_agent/web/static/vendor/three/`），不再下载别的前端库。

**Spec：** `docs/superpowers/specs/2026-11-10-caliper-v2-design.md`（第 3.8 节、第 5 节、第 8 节）。

**前置：** 计划 1、计划 2 全部完成。

**执行规则：** 见项目根目录 `CLAUDE.md`。

## Global Constraints

- 计划 1、2 的 Global Constraints 全部继续有效。**本计划不调用任何付费的模型接口**：界面的走查用假模型剧本加真实沙盒。
- 服务只监听 `127.0.0.1`。所有 `/api/` 和 `/files/` 请求必须带本次启动的随机令牌（请求头 `X-Caliper-Token`，或查询参数 `t`，后者只给 SSE 和文件下载用）；`Host` 必须是 `127.0.0.1:<端口>` 或 `localhost:<端口>`；带了 `Origin` 时必须是这两个之一。不满足一律 403。
- key 只经过这一条路：界面的输入框 → `POST /api/key` → 钥匙串。任何接口的返回、任何事件、任何日志里都不出现 key，只出现来源和后四位提示。
- 页面离线可用：不加载任何外部的脚本、样式、字体、图片。
- 视觉规范（设计文档 5.3）的数值照抄：
  - 浅色：底 `#F4F1EA`、主线和正文 `#1B1B1B`、次要文字 `#6B675E`、强调 `#1F4FD8`、通过 `#2E6B3F`、不通过 `#B3261E`。
  - 深色：底 `#0F2A4A`、主线和正文 `#E6EEF8`、次要文字 `#9DB7D6`、强调 `#FFD166`、通过 `#8FD6A3`、不通过 `#FF8A80`。
  - 分隔全部用 1px 实线；圆角不超过 2px；不用阴影、渐变、模糊。
  - 界面文字用系统字体；数字、参数名、工具调用、代码用等宽字体。
  - 动效只有逐字输出和阶段刻度的推进；遵守系统的"减少动态效果"设置。
- 界面文字用简体中文、平常话。本计划末尾"界面文字"一节里的原文逐字照抄。
- 前端不引入框架和构建步骤；每个文件只做一件事，不超过 300 行。纯逻辑的模块（不碰 DOM 的）要有 `node --test` 的测试。
- 窗口最小 1100×700；这个宽度以上布局不能错位，文字不能被截断到看不懂。
- 偏离记录接着编号。每个任务收尾：全部测试通过 → 提交 → 在 `docs/progress.md` 追加一段（标题写"第二版 计划 3 Task N"）。

## 界面这部分开工之前

Task 8 是第一个改动用户所见内容的任务。开始它之前：当前会话里如果有 `ui-consistency:finding-patterns` 技能，先运行它，把它产出的清单和下面"界面清单"合并，写进 `docs/ui-checklist.md`；没有这个技能，就直接把"界面清单"写成 `docs/ui-checklist.md`。Task 8 到 Task 12 每做完一个画面，都逐条对照这份清单；有 `ui-consistency:verifying` 技能时用它检查。

**界面清单（每个画面都要满足）：**
1. 颜色只用 `tokens.css` 里的变量，页面和脚本里不出现颜色的字面值（3D 材质的颜色也从变量读）。
2. 每个小节的标题是同一个写法：等宽的小号编号加标题，下面一条带两端短竖线的尺寸线。
3. 按钮只有三种：主要（强调色描边加强调色文字）、普通（主线色描边）、文字按钮（无边框）。一个画面里主要按钮最多一个。
4. 数字一律等宽、右对齐，带单位；长度保留到小数点后最多 2 位，去掉末尾的 0。
5. 状态用文字加符号表示（`✓ 通过`、`✗ 没通过`、`— 没做`），颜色只是辅助，不单靠颜色区分。
6. 空状态写一句说明加一个可以点的下一步，不留白。
7. 出错时说清发生了什么、接下来可以怎么做；不显示原始的异常文字和堆栈。
8. 可以点的东西都能用键盘到达，焦点有看得见的描边（强调色，2px）。
9. 浅色和深色都看过；文字和底色的对比度不低于 4.5:1。
10. 1100×700 和 1600×1000 两个窗口大小都看过。

## Review Focus

1. 模型正在输出时用户切到另一个会话再切回来：回来后看到的是完整的当前状态，正在输出的文字接着往下走，不重复、不丢。→ Task 4 `test_resubscribe_since_seq_gets_only_newer_events`、Task 8 `store` 的 `test_state_event_replaces_everything`
2. 页面的 SSE 连接断了（电脑睡眠后醒来）：自动重连，重连后先取一次完整状态再接事件；界面上有一行"连接断开，正在重试"。→ Task 6 `test_sse_reconnect_with_since`、Task 8 `test_reconnect_backoff_sequence`
3. 别的网页试图调用本机接口（没有令牌、`Origin` 不对、`Host` 是别的域名）：全部 403，写 key 的接口也一样。→ Task 6 `test_requests_without_token_are_rejected`、`test_foreign_origin_and_host_are_rejected`
4. 打开一个 1.2 版留下的旧会话（没有 `plan.json`、没有阶段）：能看、能看 3D 和版本；要接着做时按单阶段处理，不崩。→ Task 3 `test_open_legacy_session`
5. 智能体正在运行时用户去改参数面板、删除这个会话、或者再发一条消息：都被拒绝并给出一句说明，正在跑的这一轮不受影响。→ Task 4 `test_busy_rejects_params_message_and_delete`
6. 用户粘贴的 key 前后带空格或换行；或者测试连接时网络不通：前者自动去掉再存，后者给出"连不上"的说明而不是一直转圈（15 秒超时）。→ Task 7 `test_key_is_trimmed`、`test_connection_timeout_message`
7. 3D 文件加载失败或 WebGL 不可用（远程桌面、老显卡）：模型页签退回显示截图，并说明原因。→ Task 10 `test_viewer_fallback_decision`

---

## 文件结构

```
cad_agent/desk/__init__.py
cad_agent/desk/bus.py              事件流（Task 4）
cad_agent/desk/view.py             把会话目录和日志变成界面要的状态（Task 4）
cad_agent/desk/workbench.py        一个打开的会话：智能体、事件、工作线程（Task 4）
cad_agent/desk/hub.py              会话列表、新建、打开、改名、删除（Task 5）
cad_agent/desk/server.py           HTTP 服务：路由、令牌、SSE、文件（Task 6）
cad_agent/desk/settings_api.py     启动信息、设置、key、测试连接、案例（Task 7）
cad_agent/desk/demo_data/phone_stand/   示例会话（Task 12）
cad_agent/desk/static/index.html
cad_agent/desk/static/css/tokens.css  base.css  layout.css  chat.css  bench.css  pages.css
cad_agent/desk/static/js/main.js      启动、路由（Task 8）
cad_agent/desk/static/js/api.js       请求、令牌、SSE 重连（Task 8）
cad_agent/desk/static/js/store.js     状态和事件归并，纯逻辑（Task 8）
cad_agent/desk/static/js/format.js    数字、时间、费用的格式，纯逻辑（Task 8）
cad_agent/desk/static/js/dom.js  theme.js  sidebar.js（Task 8）
cad_agent/desk/static/js/chat.js  tooltree.js  cards.js（Task 9）
cad_agent/desk/static/js/viewer.js  viewer-dims.js  bench-model.js（Task 10）
cad_agent/desk/static/js/bench-checks.js  bench-params.js  bench-versions.js  titleblock.js（Task 11）
cad_agent/desk/static/js/onboarding.js  settings.js  cases.js（Task 12）
cad_agent/desk/static/js/tests/*.test.js   node --test 的测试
cad_agent/agent/resume.py          从会话目录恢复（Task 3）
cad_agent/app.py                   caliper 命令的入口和窗口（Task 13）
scripts/demo_script.json           走查用的假模型剧本（Task 13）
docs/ui-checklist.md               界面清单（Task 8 之前）
```

---

### Task 1：删除公网隧道

**Files：** Delete `start_public.bat`、`scripts/go_public.py`、`cad_agent/web/pool.py`；Modify `cad_agent/web/__main__.py`、`cad_agent/web/server.py`、`cad_agent/web/app.py`、`cad_agent/web/export.py`、`cad_agent/web/static/app.js`、`cad_agent/web/static/index.html`、`site/`（重新导出）、`README.md`、`.gitignore`、`tests/test_web.py`

这是设计文档第 8 节批准的删除。**只删下面这 8 条测试**，`tests/test_web.py` 里其余的测试不动、必须通过：
`test_password_gate`、`test_budget_stops_new_messages`、`test_main_public_needs_password_and_pricing`、`test_public_launcher_and_gitignore`、`test_each_visitor_gets_their_own_session`、`test_too_many_busy_visitors_wait`、`test_visitor_limit_and_health`、`test_export_keeps_live_json`。

- [ ] **Step 1：** 加一条新测试 `tests/test_web.py::test_public_mode_is_gone`：`python -m cad_agent.web --public` 报"不认识的参数"并返回非 0；仓库里没有 `start_public.bat`、`scripts/go_public.py`、`cad_agent/web/pool.py`、`site/live.json`；`cad_agent/web/` 和 `site/` 下的文件里搜不到 `password`、`live.json`、`budget` 这三个词；`/api/login` 返回 404。
- [ ] **Step 2：** 运行，确认失败。
- [ ] **Step 3：** 删掉上面列的 8 条测试和三个文件；去掉 `--public`、`--budget`、`--max-busy` 三个参数和访问密码、共用花费上限、多访客的全部代码；页面上去掉登录框、"开始实时体验"入口和测试额度的显示；删掉 `site/live.json`；用 `.venv\Scripts\python -m cad_agent.web.export demo\phone_stand site` 重新导出 `site/`（`test_committed_site_is_up_to_date` 要通过）；README 删掉"公网实时体验"一节；`.gitignore` 里的 `tools/` 留着。
- [ ] **Step 4：** 运行全部测试，提交：`chore: 删除公网隧道实时体验`。`tools\cloudflared.exe` 不在仓库里，在 `docs/progress.md` 里提醒用户可以自己删掉。

---

### Task 2：窗口探测，视觉规范落成文件

**Files：** Create `scripts/probe_webview.py`、`cad_agent/desk/__init__.py`、`cad_agent/desk/static/css/tokens.css`、`cad_agent/desk/static/css/base.css`、`tests/test_desk_style.py`；Modify `pyproject.toml`

**Interfaces：**
- Produces：`tokens.css` 里的变量名（后面所有样式和脚本只用这些）：
  `--paper`（底）、`--ink`（主线和正文）、`--ink-2`（次要文字）、`--accent`、`--ok`、`--bad`、`--line`（1px 分隔线，等于 `--ink`）、`--line-soft`（次要分隔线，等于 `--ink-2`）、`--part`（3D 实体色）、`--part-edge`（3D 轮廓线色）、`--font-ui`、`--font-mono`、`--s-1` 到 `--s-6`（间距 4、8、12、16、24、32 px）、`--radius`（2px）。
  浅色写在 `:root`，深色写在 `:root[data-theme="dark"]`；`:root[data-theme="system"]` 时用 `prefers-color-scheme` 选。`--part`：浅色 `#D9D5CB`，深色 `#7FA3CC`；`--part-edge` 等于 `--ink`。
  `--font-ui`：`"Microsoft YaHei UI", "PingFang SC", system-ui, sans-serif`；`--font-mono`：`"Cascadia Mono", "SF Mono", Consolas, monospace`。
- `base.css`：重置、正文字号 14px、三种按钮（`.btn-primary`、`.btn`、`.btn-text`）、输入框、焦点描边、小节标题（`.section-head`：编号、标题、尺寸线）、状态文字（`.ok`、`.bad`、`.none`）、`prefers-reduced-motion` 下关掉过渡。

- [ ] **Step 0（探测，先做）：** 写一个一次性的小脚本 `scripts/probe_webview.py`：起一个本机的 HTTP 服务，页面里用 three.js 画一个会转的方块，并用 `EventSource` 每秒收一条服务端推来的消息显示在页面上；用 `pywebview` 开窗口加载它。确认三件事：窗口能开、方块在转（WebGL 可用）、消息在跳（SSE 可用）；再确认关掉窗口后进程能正常退出。把结果、pywebview 的版本、用的后端写进 `docs/progress.md`。三件事里有一件不行，就停下来问用户（退路是只做 `--browser` 方式）。
- [ ] **Step 1：** 写测试 `tests/test_desk_style.py`：
  - `test_token_values`：两套配色的 6 个颜色等于 Global Constraints 里的值；两套配色定义的变量名集合相同。
  - `test_contrast_at_least_4_5`：在测试里按 WCAG 公式算，两套配色下 `--ink`、`--ink-2`、`--accent`、`--ok`、`--bad` 对 `--paper` 的对比度都不低于 4.5。
  - `test_no_shadow_gradient_blur_webfont`：`cad_agent/desk/static/css/` 下所有文件里没有 `box-shadow`、`text-shadow`、`gradient(`、`blur(`、`@font-face`、`@import`、`http://`、`https://`。
  - `test_radius_at_most_2px`：所有 `border-radius` 的值是 `0`、`var(--radius)`、`1px`、`2px` 或 `50%`（只给圆点用）。
  - `test_colors_only_in_tokens`：除 `tokens.css` 外，其他样式文件里没有 `#` 开头的颜色值，也没有 `rgb(`、`hsl(`。
  - `test_reduced_motion_rule_exists`。
- [ ] **Step 2：** 运行，确认失败；实现；`pyproject.toml` 的 `package-data` 加 `"desk/static/**/*"`、`"desk/demo_data/**/*"`，依赖加 `pywebview`，安装。
- [ ] **Step 3：** 运行全部测试，提交：`feat: 图纸与蓝图的视觉规范`。

---

### Task 3：从会话目录恢复

**Files：** Create `cad_agent/agent/resume.py`、`tests/test_resume.py`；Modify `cad_agent/session.py`、`cad_agent/agent/context.py`、`cad_agent/agent/loop.py`

**Interfaces：**
- Produces：
  ```python
  # session.py
  @classmethod
  def Session.open(cls, path: Path) -> "Session": ...         # 打开已有的会话目录，不新建；目录不存在抛 FileNotFoundError
  def Session.read_log(self) -> list[dict]: ...               # 读 log.jsonl；坏行跳过
  def Session.meta(self) -> dict: ...                         # 读 meta.json；没有时返回 {}
  def Session.set_meta(self, **fields) -> None: ...           # 合并写入 meta.json（title、created、updated）
  # context.py
  def Context.restore(self, past: list[dict]) -> None: ...    # 直接设置"之前各轮的折叠版"
  # resume.py
  def load_workspace(session: Session) -> Workspace: ...
  def past_turns(rows: list[dict]) -> list[dict]: ...
  def resume_agent(agent: Agent) -> None: ...                 # 用 agent.session 目录里的内容填好 agent 的工作区和上下文
  ```
  - `load_workspace`：读 `brief.json`、`features.json`、`checks.json`、`plan.json`（都通过 `Session.part_dir()`）；没有的文件按空处理。没有 `plan.json` 但有特征时（旧会话）：造一个只有一个阶段的计划（标题 `整体`，`done_when` 写 `零件完成`），全部特征和检查归到 `s1`，有版本时标成已通过。
  - `past_turns`：从日志里取每一轮的用户原话（`user` 记录的 `sent_as`）和这一轮结束记录的文字，按 `compact_text` 的规则折叠，得到 user、assistant 交替的消息列表。没有结束记录的最后一轮（上次异常退出）丢掉。
  - `resume_agent` 之后：`ws.last_build_content` 是 `None`；需求单的确认状态以文件为准；`awaiting_confirmation` 按最后一轮的结局是不是 `confirm` 设置。

- [ ] **Step 1：** 写测试 `tests/test_resume.py`：
  - `test_round_trip_after_delivery`：用假流程交付 v1，再 `Session.open` + `resume_agent` 到一个新的智能体；需求单、计划（各阶段已通过）、特征、检查都相同；再发一条修改消息能走完并交付 v2（放在同一个会话目录里）。
  - `test_past_turns_are_compacted`：恢复后第一次调用模型的消息是 system、之前各轮的 user / assistant、带快照的本轮 user，没有任何 `tool` 消息。
  - `test_resume_while_waiting_for_confirmation`：上一轮是 `confirm`，恢复后回"确认"能进入规划。
  - `test_unfinished_last_turn_is_dropped`。
  - `test_open_legacy_session`（Review Focus 4）：用仓库里的 `demo/phone_stand` → 得到一个阶段的计划、全部特征归 `s1`、已通过；不抛异常。
  - `test_meta_round_trip`、`test_read_log_skips_broken_lines`。
- [ ] **Step 2：** 运行，确认失败；实现；运行全部测试，提交：`feat: 从会话目录恢复智能体`。

---

### Task 4：事件流和工作台

**Files：** Create `cad_agent/desk/bus.py`、`cad_agent/desk/view.py`、`cad_agent/desk/workbench.py`、`tests/test_desk_bus.py`、`tests/test_desk_workbench.py`

**Interfaces：**
- Produces：
  ```python
  # bus.py
  class EventBus:
      def publish(self, type: str, **data) -> int: ...                        # 返回这条事件的 seq（从 1 递增）
      def since(self, seq: int) -> list[dict]: ...                            # seq 之后的全部事件
      def wait(self, seq: int, timeout: float) -> list[dict]: ...             # 没有新事件就等，超时返回空表
      def last_seq(self) -> int: ...
  # 只保留最近 2000 条；请求的 seq 比保留的最早一条还早时，返回一条 {"type": "resync"}
  # view.py
  def build_state(session: Session, ws: Workspace | None, *, busy: bool, demo: bool) -> dict: ...
  # workbench.py
  class Busy(Exception): ...
  class Workbench:
      def __init__(self, agent: Agent, session: Session, *, demo: bool = False) -> None: ...
      bus: EventBus
      def state(self) -> dict: ...
      def submit(self, text: str) -> None: ...                # 正忙抛 Busy；空文字抛 ValueError
      def stop(self) -> None: ...
      def apply_params(self, values: dict[str, float]) -> ManualResult: ...   # 正忙抛 Busy
      def save_case(self, title: str, tags: list[str], cases_dir: Path) -> str: ...
      def is_busy(self) -> bool: ...
      def close(self, timeout: float = 5) -> None: ...        # 请求停止并等工作线程结束
  ```
- **事件类型**（每条都有 `seq` 和 `type`）：

  | type | 其余字段 | 什么时候发 |
  |---|---|---|
  | `turn_start` | `text` | 开始处理一条用户消息 |
  | `delta` | `text` | 模型的一个文字片段 |
  | `delta_reset` | — | 收到 `"\x00"`：前面的片段作废 |
  | `assistant` | `content` | 模型一次回复的完整文字（取代这次回复的全部片段） |
  | `tool_start` | `id`、`name`、`label` | 一个工具开始执行；`label` 是中文说明 |
  | `tool_end` | `id`、`name`、`ok`、`summary` | 执行完；`summary` 是一句给人看的结果 |
  | `plan` | `stages`、`current` | 计划有变化 |
  | `stage` | `id`、`title`、`checks`、`size`、`volume` | 一个阶段通过 |
  | `build` | 日志里 `build` 记录的全部字段 | 每次 build |
  | `gate`、`review`、`cases`、`manual` | 日志里对应记录的字段 | 对应的时刻 |
  | `turn_end` | `kind`、`text`、`extra`、`usage`、`cost` | 一轮结束 |
  | `state` | `state` | 一轮结束后、手动改参数后，发一次完整状态 |
  | `error` | `message` | 工作线程里出了没预料到的异常（中文说明，不带堆栈） |

- **完整状态**（`build_state` 的返回）的键：`session`（`id`、`title`、`demo`）、`busy`、`phase`（`clarify`、`confirm`、`planning`、`modeling`、`delivered` 之一）、`transcript`、`brief`（`Brief.to_dict()`）、`plan`（`{"stages", "current"}` 或 `null`）、`checks`（最近一次验证的每条检查结果）、`gate`、`review`、`versions`（每个版本：`name`、`changes`、`size`、`volume`、`has_stl`、`stages`、`gate`、`review`）、`stage_files`（当前还没交付的各阶段 STL 的阶段编号）、`usage`（本会话累计的六项用量）、`cost`、`last_seq`。
  - `transcript` 的每一项是下面几种之一：`{"role": "user", "text"}`；`{"role": "assistant", "kind": "reply"|"question"|"confirm"|"delivered"|"failed"|"stopped"|"error", "text", …各自的结构化字段}`；`{"role": "work", "stages": [{"id", "title", "passed", "tools": [{"name", "label", "ok", "summary"}]}], "loose": [不属于任何阶段的工具]}`（一轮里的工具调用树）。
  - `question` 带 `questions`；`confirm` 带 `brief`；`delivered` 带 `version`、`passed`、`total`、`changes`、`gate`、`review`。
  - 可以复用 `cad_agent/web/events.py` 里的 `describe_event`、`_describe_tool` 来生成 `label` 和 `summary`。

- 工作台把主循环接到事件流上：给会话的 `log` 包一层（做法同 `web/app.py` 的 `LiveSession`），把日志记录翻译成上表的事件；`agent.on_delta` 发 `delta`。监听器自己出错只记到程序日志，不打断智能体。
- 示例会话（`demo=True`）：`submit`、`apply_params`、`save_case` 一律抛 `PermissionError`。

- [ ] **Step 1：** 写测试 `tests/test_desk_bus.py`：`test_seq_increments`、`test_since`、`test_wait_returns_when_published`（另一个线程 0.1 秒后发事件）、`test_wait_times_out_empty`、`test_resubscribe_since_seq_gets_only_newer_events`（Review Focus 1）、`test_old_seq_gets_resync`（发 2100 条后请求 `since(5)`）。
- [ ] **Step 2：** 写测试 `tests/test_desk_workbench.py`（分阶段的假流程）：
  - `test_events_for_a_full_turn`：事件类型的顺序里依次出现 `turn_start`、若干 `delta`、`assistant`、`tool_start`/`tool_end` 成对、`plan`、`stage`、`build`、`gate`、`turn_end`、`state`。
  - `test_delta_reset_is_forwarded`。
  - `test_state_after_delivery`：`phase == "delivered"`，`versions` 有一项且 `has_stl`、`stages == ["s1", "s2"]`，`transcript` 里有一项 `role == "work"`，它的 `stages` 有两个且各有工具。
  - `test_state_phases`（澄清、等确认、规划、建模各一例）。
  - `test_busy_rejects_params_message_and_delete`（Review Focus 5 的前两项）：正忙时 `submit`、`apply_params` 抛 `Busy`，正在跑的这一轮照常结束。
  - `test_stop_ends_turn_with_stopped`。
  - `test_agent_crash_becomes_error_event`：智能体抛异常 → 有一条 `error` 事件，`busy` 变回假，还能接下一条消息。
  - `test_apply_params_publishes_state`、`test_save_case_writes_user_case`。
  - `test_demo_workbench_is_read_only`。
  - `test_no_key_in_events_or_state`：整个流程的事件和状态转成文字后搜不到测试用的假 key。
- [ ] **Step 3：** 运行，确认失败；实现；运行全部测试，提交：`feat: 桌面端的事件流和工作台`。

---

### Task 5：会话管理

**Files：** Create `cad_agent/desk/hub.py`、`tests/test_desk_hub.py`

**Interfaces：**
- Produces：
  ```python
  class Hub:
      def __init__(self, *, make_agent: Callable[[Session], Agent], sessions_dir: Path, cases_dir: Path, demo_dir: Path | None) -> None: ...
      def list(self) -> list[dict]: ...            # 每项：id、title、updated、versions、demo；按 updated 从新到旧，示例排在最后
      def create(self) -> str: ...                 # 新建一个空会话，返回 id（就是会话目录名）
      def open(self, session_id: str) -> Workbench: ...     # 已经打开的直接返回；否则恢复
      def rename(self, session_id: str, title: str) -> None: ...
      def delete(self, session_id: str) -> None: ...        # 正忙抛 Busy；示例会话抛 PermissionError；目录整个删掉
      def refresh_agents(self) -> None: ...        # 设置改了之后调用：空闲的工作台下次开工时用新的模型设置
      def close(self) -> None: ...                 # 关掉所有工作台
  ```
  - 会话 id 只能是字母、数字、短横线；别的一律当作不存在（防止路径穿越）。
  - 标题：`meta.json` 里有就用它；没有就用需求单的零件名；都没有是 `新会话`。交付或一轮结束时更新 `updated`。
  - 示例会话的 id 是 `demo-<目录名>`，只读，用 `cad_agent/web/app.py` 的回放读取办法得到状态。
  - 同时打开的工作台最多 8 个；超过时关掉最久没用且空闲的那个。

- [ ] **Step 1：** 写测试：`test_create_open_list`、`test_title_falls_back_to_part_name`、`test_rename_persists`、`test_delete_removes_directory`、`test_delete_busy_is_refused`（Review Focus 5 的第三项）、`test_bad_ids_are_not_found`（`..`、`a/b`、空文字）、`test_reopen_after_restart_resumes`（新的 `Hub` 打开旧会话，状态相同）、`test_demo_session_listed_last_and_read_only`、`test_lru_closes_idle_workbench`、`test_refresh_agents_swaps_llm_for_idle_only`。
- [ ] **Step 2：** 运行，确认失败；实现；运行全部测试，提交：`feat: 桌面端的会话管理`。

---

### Task 6：HTTP 服务

**Files：** Create `cad_agent/desk/server.py`、`tests/test_desk_server.py`

**Interfaces：**
- Produces：`make_desk_server(hub: Hub, extra: Callable | None, *, port: int = 0, token: str | None = None) -> tuple[ThreadingHTTPServer, str]`（返回服务和令牌；`port=0` 让系统挑端口；`extra` 是 Task 7 的路由处理函数）。
- 路由：

  | 方法和路径 | 作用 | 返回 |
  |---|---|---|
  | `GET /` | 页面。只有带正确的 `?t=` 才给，否则 403 | HTML |
  | `GET /static/<路径>` | 静态文件；`/static/vendor/three/<文件>` 取自 `cad_agent/web/static/vendor/three/` | 文件 |
  | `GET /api/sessions` | 列表 | `[…]` |
  | `POST /api/sessions` | 新建 | `{"id"}` |
  | `POST /api/sessions/<id>/rename` | `{"title"}` | `{"ok": true}` |
  | `DELETE /api/sessions/<id>` | 删除 | `{"ok": true}` |
  | `GET /api/sessions/<id>/state` | 完整状态 | 状态 |
  | `GET /api/sessions/<id>/events?since=<seq>` | SSE | 事件流 |
  | `POST /api/sessions/<id>/message` | `{"text"}` | `{"ok": true}` |
  | `POST /api/sessions/<id>/stop` | 停止 | `{"ok": true}` |
  | `POST /api/sessions/<id>/params` | `{"values": {…}}` | `ManualResult` 的字段（路径只给版本名） |
  | `POST /api/sessions/<id>/case` | `{"title", "tags"}` | `{"id"}` |
  | `GET /api/sessions/<id>/diff?a=&b=` | 两个版本的参数差异 | `{"lines": […]}` |
  | `POST /api/sessions/<id>/reveal` | `{"version"}`：在系统的文件管理器里显示这个版本的目录 | `{"ok": true}` |
  | `GET /files/<id>/<版本>/<文件>` | 版本里的文件 | 文件 |

  - 文件白名单：`view.png`、`model.step`、`model.stl`、`model.py`、`checks.json`、`gate.json`、`review.json`、`stages/<阶段编号>.stl`；`<版本>` 是 `v<数字>` 或 `current`（`current` 只能取 `stages/<阶段编号>.stl` 和 `review/round-<数字>/<视角>.png`）。别的一律 404。
  - 错误的返回都是 `{"error": "<中文说明>"}`：不存在 404、正忙 409、参数不对 400、示例会话只读 403、令牌或来源不对 403。
  - SSE：每条事件写成 `id: <seq>` 和 `data: <JSON>`；每 15 秒发一行注释保持连接；客户端断开后线程退出。
  - 请求体最大 200 KB。

- [ ] **Step 1：** 写测试 `tests/test_desk_server.py`（起一个真的本机服务，假的 `Hub` 或假流程的真 `Hub`）：
  - `test_requests_without_token_are_rejected`（Review Focus 3）：页面、接口、文件、SSE 各一例，都是 403。
  - `test_foreign_origin_and_host_are_rejected`（Review Focus 3）：带对的令牌但 `Origin: https://evil.example` → 403；`Host: evil.example` → 403；`Origin` 是本机地址 → 200。
  - `test_token_in_header_or_query`。
  - `test_session_crud_over_http`。
  - `test_message_then_events_then_state`：发消息后从 SSE 读到 `turn_end`，再取状态。
  - `test_sse_reconnect_with_since`（Review Focus 2）：读到 seq 5 后断开，带 `since=5` 重连，只收到更新的事件，没有重复。
  - `test_busy_is_409`、`test_bad_json_is_400`、`test_unknown_session_is_404`、`test_demo_is_403_for_writes`。
  - `test_files_whitelist`：白名单里的能取到；`brief.json`、`../log.jsonl`、`%2e%2e`、`stages/../../log.jsonl`、多一层路径都是 404。
  - `test_params_endpoint_returns_manual_result`、`test_diff_endpoint`。
  - `test_binds_localhost_only`。
  - `test_error_bodies_are_chinese_json`。
- [ ] **Step 2：** 运行，确认失败；实现；运行全部测试，提交：`feat: 桌面端的本机服务`。

---

### Task 7：启动信息、设置、key、测试连接、案例的接口

**Files：** Create `cad_agent/desk/settings_api.py`、`tests/test_desk_settings_api.py`

**Interfaces：**
- Consumes：`settings.py`、`keystore.py`、`providers.py`、`test_vision`（计划 2）；`load_cases`（计划 1）。
- Produces：`make_settings_routes(hub: Hub, *, make_llm_for: Callable[[Settings, str], LLM]) -> Callable`，提供：

  | 方法和路径 | 作用 | 返回 |
  |---|---|---|
  | `GET /api/boot` | 页面启动时取一次 | `version`、`platform`、`providers`（预设列表）、`settings`、`key`（`{"source", "hint"}`）、`ready`（有没有可用的 key）、`sca_version` |
  | `GET /api/settings` / `POST /api/settings` | 读、写设置（写的时候只接受 `Settings` 里有的键） | 设置 |
  | `POST /api/key` | `{"provider", "key"}`：去掉首尾空白后存进钥匙串 | `{"source", "hint"}` |
  | `DELETE /api/key?provider=` | 从钥匙串删除 | `{"source", "hint"}` |
  | `POST /api/test-connection` | 用当前设置发一句"只回答：好" | `{"ok", "message"}` |
  | `POST /api/test-vision` | 调用 `test_vision`；成功时把设置里的 `vision` 改成 `on` 并保存 | `{"ok", "message"}` |
  | `GET /api/cases` | 自带的和用户的案例 | 每项：`id`、`title`、`tags`、`request`、`builtin`、`stages`（阶段标题列表） |
  | `DELETE /api/cases/<id>` | 只能删用户的 | `{"ok": true}` |

  - 写设置、存 key、删 key 之后调用 `hub.refresh_agents()`。
  - `test-connection`、`test-vision` 的超时是 15 秒；`message` 用"界面文字"一节里的原文。
  - 任何返回里都没有 key。

- [ ] **Step 1：** 写测试：`test_boot_shape`；`test_boot_ready_reflects_key`；`test_save_settings_round_trip`、`test_unknown_setting_is_400`；`test_set_key_then_hint`、`test_key_is_trimmed`（Review Focus 6）、`test_blank_key_is_400`、`test_delete_key`；`test_env_key_is_reported_as_env`；`test_no_keyring_backend_message`（返回 400，信息是中文、提到环境变量）；`test_connection_ok`、`test_connection_auth_error_message`、`test_connection_timeout_message`（Review Focus 6：假客户端 20 秒才返回 → 15 秒内得到"连不上"的说明）；`test_vision_success_turns_setting_on`、`test_vision_failure_keeps_setting`；`test_cases_list_and_delete`、`test_builtin_case_cannot_be_deleted`；`test_no_key_in_any_response`（把所有接口的返回连起来搜假 key）。
- [ ] **Step 2：** 运行，确认失败；实现；运行全部测试，提交：`feat: 设置、密钥和案例的接口`。

---

### Task 8：页面骨架、状态管理、侧栏、主题

**Files：** Create `cad_agent/desk/static/index.html`、`css/layout.css`、`js/main.js`、`js/api.js`、`js/store.js`、`js/format.js`、`js/dom.js`、`js/theme.js`、`js/sidebar.js`、`js/tests/store.test.js`、`js/tests/format.test.js`、`js/tests/api.test.js`、`docs/ui-checklist.md`、`tests/test_desk_static.py`

开始前先做"界面这部分开工之前"一节说的事。

**Interfaces：**
- Produces（前端模块之间的约定）：
  ```js
  // api.js
  export function configure({token})                      // 令牌从页面地址的 ?t= 取出后放内存，并从地址栏里去掉
  export async function get(path), post(path, body), del(path)   // 返回 {status, body}
  export function subscribe(sessionId, since, onEvent, onStatus) // 返回 unsubscribe；onStatus("open"|"retrying")
  export function backoffDelays()                         // [1000, 2000, 4000, 8000, 8000, …] 毫秒
  // store.js（纯逻辑，不碰 DOM）
  export function emptyState()
  export function applyEvent(state, event)                // 返回新状态；见下面的规则
  export function onChange(listener)                      // main.js 用
  // format.js（纯逻辑）
  export function fmtNum(v), fmtLen(v, unit), fmtCost(v), fmtTokens(n), fmtTime(iso), fmtPct(a, b)
  ```
  `applyEvent` 的规则：
  - `state` 事件：整个状态换成事件里的 `state`，清掉临时的输出文字。
  - `resync` 事件：标记需要重新取一次完整状态。
  - `turn_start`：往 `transcript` 末尾加用户消息和一个空的"进行中"项；`busy` 变真。
  - `delta`：把文字接到"进行中"项的 `streaming` 上；`delta_reset`：把 `streaming` 清空；`assistant`：`streaming` 清空，文字记为这次回复的定稿。
  - `tool_start` / `tool_end`：在"进行中"项的工具树里加一个节点 / 更新它。属于哪个阶段：按当时 `plan.current` 归入；还没有计划时归到 `loose`。
  - `plan`、`stage`：更新 `plan`；`stage` 同时把工具树里对应的阶段标成通过。
  - `turn_end`：`busy` 变假（之后总会跟一条 `state`）。
  - `error`：加一条 `kind: "error"` 的助手消息，`busy` 变假。
  - 不认识的事件类型：原样返回状态，不报错。
- 页面结构：顶栏（产品名、当前会话标题、设置入口、主题切换）；下面三栏——左 240px 会话列表，中间对话（最小 420px），右边工作台（占剩余宽度，最小 440px）；三栏之间是 1px 的线。右下角是标题栏（Task 11）。
- 侧栏：`新会话` 按钮；会话列表（标题、相对时间、版本数）；当前项用强调色的左边线；每项可以改名、删除（删除前要确认）；示例会话单独一组，标着 `示例`。
- 主题：`theme.js` 按设置把 `data-theme` 写到根元素上；切换后立刻保存到设置。
- 连接状态：SSE 断开时在顶栏下面显示一行 `连接断开，正在重试`；重连成功后先取一次完整状态，再从它的 `last_seq` 接着订阅。
- 没有可用的 key 且没有任何会话时，启动后直接进引导页（Task 12）；这一任务先放一个占位。

- [ ] **Step 1：** 写测试 `js/tests/store.test.js`、`format.test.js`、`api.test.js`（`node --test`）：
  - `test_state_event_replaces_everything`（Review Focus 1）、`test_turn_start_adds_user_and_pending`、`test_delta_appends_and_reset_clears`、`test_assistant_replaces_streaming`、`test_tools_grouped_by_current_stage`、`test_tools_before_plan_are_loose`、`test_stage_event_marks_passed`、`test_error_event_adds_message`、`test_unknown_event_is_ignored`、`test_resync_sets_flag`。
  - `fmtNum(60) === "60"`、`fmtNum(12.50) === "12.5"`、`fmtNum(3.14159) === "3.14"`；`fmtLen(60, "mm") === "60 mm"`、`fmtLen(65, "deg") === "65°"`、`fmtLen(4, "1") === "4"`；`fmtCost(0.1234) === "¥0.12"`、`fmtCost(null) === ""`；`fmtTokens(1234567) === "1.23M"`、`fmtTokens(8200) === "8.2k"`；`fmtPct(89, 100) === "89%"`、`fmtPct(1, 0) === ""`。
  - `test_reconnect_backoff_sequence`（Review Focus 2）：前六项是 1000、2000、4000、8000、8000、8000。
- [ ] **Step 2：** 写测试 `tests/test_desk_static.py`：`test_node_tests_pass`（运行 `node --test cad_agent/desk/static/js/tests/`，返回 0）；`test_all_modules_parse`（每个 `.js` 用 `node --check`）；`test_no_external_resources`（HTML、JS、CSS 里没有 `http://`、`https://`，除了注释里的许可证说明）；`test_index_has_three_columns_and_import_map`（import map 把 `three` 指到 `/static/vendor/three/three.module.js`）；`test_every_file_under_300_lines`；`test_no_color_literals_in_js`。
- [ ] **Step 3：** 运行，确认失败；实现。
- [ ] **Step 4：** 用假模型剧本起服务（做法见 Task 13 的 `--demo-script`；这一步可以先用一个临时的启动脚本），在应用内置的浏览器里看：三栏布局、新建和切换会话、主题切换、断开服务后出现"连接断开"、恢复后自动接上。对照 `docs/ui-checklist.md` 逐条过。
- [ ] **Step 5：** 运行全部测试，提交：`feat: 桌面端页面骨架、状态管理和会话侧栏`。

---

### Task 9：对话栏

**Files：** Create `css/chat.css`、`js/chat.js`、`js/tooltree.js`、`js/cards.js`、`js/tests/tooltree.test.js`

**Interfaces：**
- Consumes：`store`、`api`、`format`、`dom`。
- Produces：
  ```js
  // tooltree.js（纯逻辑）
  export function treeLines(work)   // 把一轮的工具树变成要显示的行：[{depth, mark, text, state}]
  ```
  `mark` 用制图的树形线：阶段行是 `S1` 这样的编号；阶段下的工具行，不是最后一个用 `├`，最后一个用 `└`；`state` 是 `running`、`ok`、`bad`。一个阶段通过后默认折叠成一行（`S1 底板 ✓ 检查 5 条`），点开可以看里面的工具。

- 对话栏的内容：
  - 用户消息：靠右，正文色的 1px 边框。
  - 助手文字：靠左，没有边框；正在输出时末尾有一个闪动的竖线（"减少动态效果"时不闪）。
  - 工具调用树：等宽字体；正在运行的那一行前面是一个转动的短线。
  - 阶段进度：对话栏顶部一条尺寸线，刻度是 `S1`…`Sn`，通过的刻度是实心，当前的用强调色，后面跟当前阶段的标题。没有计划时显示五步流程（澄清、确认、规划、建模、交付）走到哪一步。
  - 提问卡片：问题带编号；每个问题下面一个输入框；`发送回答` 把各条回答拼成 `1. …\n2. …` 发出去；也可以直接在底部输入框里回答。
  - 确认卡片：零件名和用途；参数表（名字、数值、单位、来源标签 `用户` 实心 / `建议` 描边、说明）；组成部分；位置关系；`确认，开始建模` 是主要按钮，发出去的文字是 `确认`。
  - 交付卡片：版本号；`检查 <通过>/<总数>`；参数扰动验证的一行；看图审查的一行（有异议时逐条列出）；本版变化；`下载 STEP`、`下载 STL`、`在文件夹中显示`。
  - 失败、停止、出错：各一种卡片，文字用后端给的，下面给出下一步可以做什么。
  - 底部输入框：回车发送，Shift+回车换行；运行中发送按钮变成 `停止`；示例会话里输入框不可用并说明原因。
  - 新会话的空状态：一句引导和三个可以点的例子（原文见"界面文字"）。
  - 新内容出现时，只有当用户本来就在底部才自动滚到底。

- [ ] **Step 1：** 写测试 `js/tests/tooltree.test.js`：`test_last_tool_uses_corner_mark`、`test_passed_stage_collapses_to_one_line`、`test_running_tool_state`、`test_loose_tools_have_no_stage_row`、`test_failed_tool_is_bad`。
- [ ] **Step 2：** 运行，确认失败；实现。
- [ ] **Step 3：** 用假模型剧本走一遍：提问 → 回答 → 确认 → 规划 → 两个阶段 → 交付；中途点一次停止；每种卡片都看到。浅色、深色各看一遍，对照界面清单。
- [ ] **Step 4：** 运行全部测试，提交：`feat: 桌面端对话栏`。

---

### Task 10：工作台·模型

**Files：** Create `css/bench.css`、`js/viewer.js`、`js/viewer-dims.js`、`js/bench-model.js`、`js/tests/viewer-dims.test.js`

**Interfaces：**
- Produces：
  ```js
  // viewer.js
  export function createViewer(container, {onFallback})   // 返回 {load(url), setWireframe(on), resetView(), setTheme(), dispose()}
  export function webglAvailable()
  // viewer-dims.js（纯逻辑）
  export function dimSegments(bbox)        // 给包围盒算三条尺寸线各自的端点和文字位置（世界坐标）
  export function fallbackReason({webgl, stlOk})   // 返回 null 或要显示的一句说明
  ```
- 模型页签：
  - 3D：STL 加载后 z 轴朝上；实体用 `--part`；用 `EdgesGeometry`（夹角阈值 30°）画轮廓线，颜色 `--part-edge`；z=0 平面上一层淡网格（`--line-soft`）。可以旋转、缩放、平移。
  - 外形尺寸标注：沿包围盒的三条棱各画一条尺寸线（强调色），文字是 `fmtNum` 后的数值；文字是叠在画布上的 HTML 元素，每一帧按投影位置更新，不引入新的 three.js 附加库。
  - 工具条：`线框`、`重置视角`、`截图`（切换成显示 `view.png`）。
  - 阶段刻度：模型下面一条尺寸线，刻度是这个版本的各个阶段加一个 `完成`；点某个刻度就加载那个阶段的 STL。正在建模、还没有版本时，加载 `current` 的各阶段 STL，新阶段通过时自动切过去。
  - 版本切换：页签右上角一个下拉，默认最新版本。
  - 换模型时释放旧的几何体和材质；窗口大小变化时调整画布；切主题时更新材质颜色。
  - WebGL 不可用，或 STL 加载失败：显示 `view.png`，上面一行说明（原文见"界面文字"）。两者都没有时显示空状态。

- [ ] **Step 1：** 写测试 `js/tests/viewer-dims.test.js`：`test_dim_segments_lengths`（包围盒 `[−40,−25,0, 40,25,30]` → 三条线的长度是 80、50、30，都贴在包围盒外侧）；`test_viewer_fallback_decision`（Review Focus 7：没有 WebGL → 第一种说明；有 WebGL 但 STL 失败 → 第二种说明；都正常 → `null`）。
- [ ] **Step 2：** 运行，确认失败；实现。
- [ ] **Step 3：** 用真实沙盒产出的 STL 看：转动、缩放、线框、重置、尺寸数字和检查里的包围盒一致、拖阶段刻度能看到零件一步步长出来、切主题后颜色跟着变、把 STL 地址改错后退回截图。
- [ ] **Step 4：** 运行全部测试，提交：`feat: 工作台的三维视图`。

---

### Task 11：工作台·检查、参数、版本、标题栏

**Files：** Create `js/bench-checks.js`、`js/bench-params.js`、`js/bench-versions.js`、`js/titleblock.js`、`js/params-logic.js`、`js/tests/params-logic.test.js`

**Interfaces：**
- Produces：
  ```js
  // params-logic.js（纯逻辑）
  export function sliderRange(param)          // {min, max, step}
  export function pendingChanges(params, edits)   // 只返回和原值不同的 {name: value}
  export function validateEdit(param, text)   // {ok, value} 或 {ok: false, message}
  ```
  - `sliderRange`：单位是 `1` 且是整数 → `min = max(1, 值 − 3)`、`max = 值 + 3`、`step = 1`；数值是 0 → `min = 0`、`max = 10`、`step = 0.1`；其余 → `min = 值 × 0.5`、`max = 值 × 1.5`、`step` 是让范围分成 100 格的数再取到一位有效数字。
- 检查页签：最上面一个大数字 `通过数 / 总数`；下面三块，每块一个小节标题：
  - `01 检查`：按阶段分组，每条一行：状态符号、检查名、实测、期望、容差。没通过的排在前面。
  - `02 参数扰动验证`：每个用户参数一行：参数名、`被 <检查名> 约束` / `无法单独扰动` / `没有被约束`。没做时写 `— 没做` 和原因。
  - `03 看图审查`：四张小图（点开放大）；每个审查项一行：状态、条目、理由。没做时写原因。
- 参数页签：需求单的参数表。每行：参数名（等宽）、说明、数值输入框、单位、滑块、来源标签。只有 `phase == "delivered"` 且不忙时可以改，否则整张表只读并说明原因。改过的行左边一条强调色的线。底部 `应用`（主要按钮，没有改动时不可点）和 `还原`。点 `应用` → `POST …/params` → 成功：提示 `已存为 <版本>`，模型页签切到新版本；失败：在表格上方显示后端给的文字和没通过的检查，旁边一个按钮 `让助手处理`，点了就把"界面文字"里那句话发给对话。组成部分和位置关系列在参数表下面，只读。
- 版本页签：每个版本一行：缩略图、版本号、时间、变化说明、检查通过数。勾选两个版本后显示对比：参数差异（`/diff` 的返回）和两张截图并排。每个版本有 `下载 STEP`、`下载 STL`、`源文件`、`在文件夹中显示`、`存为案例`（弹出标题和标签的输入）。
- 标题栏：工作台右下角固定的一块表格（像图纸的标题栏，1px 线分格）：`零件`、`版本`、`阶段`、`模型`、`费用`、`缓存`、`日期`。没有价目表时费用写 `—`。

- [ ] **Step 1：** 写测试 `js/tests/params-logic.test.js`：`test_slider_range_for_length`（78 mm → 39 到 117）、`test_slider_range_for_count`（4 个 → 1 到 7，步长 1）、`test_slider_range_for_zero`、`test_pending_changes_only_changed`、`test_validate_rejects_text_and_empty`、`test_validate_count_must_be_integer`。
- [ ] **Step 2：** 运行，确认失败；实现。
- [ ] **Step 3：** 用假模型剧本加真实沙盒看：交付后改一个参数并应用 → 新版本、3D 更新、模型没有被调用（日志里没有新的模型调用）；改成一个会让检查失败的数值 → 看到失败说明和"让助手处理"；版本对比；存为案例后在案例库里能看到。对照界面清单。
- [ ] **Step 4：** 运行全部测试，提交：`feat: 工作台的检查、参数、版本和标题栏`。

---

### Task 12：引导、设置、案例库、示例会话

**Files：** Create `css/pages.css`、`js/onboarding.js`、`js/settings.js`、`js/cases.js`、`cad_agent/desk/demo_data/phone_stand/`、`tests/test_desk_demo.py`

- 引导（三步，顶上一条尺寸线标出走到第几步）：
  1. 选模型服务：预设做成一列可选的行，每行是名字和一句说明；`自定义` 展开地址和模型名两个输入框。
  2. 填 key：一个密码输入框；说明 key 存在哪里（原文见"界面文字"）；`测试连接`；环境变量里已经有 key 时，直接显示"已从环境变量读到"，不用填。
  3. 完成：`开始第一个零件`（主要按钮）和 `先看看示例`。
  任何一步都能点 `先看看示例` 跳过。
- 设置（从顶栏进入，占满工作区的一页，左边小节目录）：
  - 模型服务：服务、模型名（预设里有的做成下拉，也能自己填）、地址。
  - 密钥：来源（`环境变量` / `系统钥匙串` / `还没有`）和后四位；`更换`、`删除`、`测试连接`。来自环境变量时不能在这里删。
  - 看图审查：现在是开还是关、为什么；`测试识图`；可以给审查单独选一个服务和模型。
  - 价格：三个输入框（每百万 token 的元数），说明"照你用的模型的价目页填，不填就只显示 token 数"。
  - 流程：四个开关各一行，每行一句话说明关掉会怎样。
  - 外观：浅色、深色、跟随系统。
  - 数据：数据目录的位置、`打开文件夹`。
  - 关于：卡尺的版本、SCA 的版本、Python 的版本、更新的命令 `caliper update`。
- 案例库（从侧栏底部进入）：两组——`自带` 和 `我保存的`；每个案例一行：标题、标签、一句话需求、阶段标题；用户的可以删除。空状态说明怎么保存案例。
- 示例会话：把 `demo/phone_stand` 里回放需要的文件（`log.jsonl`、`brief.json`、`versions/` 下的全部）复制到 `cad_agent/desk/demo_data/phone_stand/`。界面上标 `录制于 1.1 版`，说明它是只读的真实录制。

- [ ] **Step 1：** 写测试 `tests/test_desk_demo.py`：`test_demo_data_is_packaged`（目录在包里，`log.jsonl` 和 `versions/v1/model.stl` 都在，`pyproject.toml` 的 `package-data` 覆盖到）；`test_demo_session_state`（`Hub` 打开 `demo-phone_stand`，状态里 `demo` 为真、至少一个版本、`transcript` 非空）；`test_demo_log_has_no_secrets`（文件里搜不到 `sk-`、`api_key` 的值）。
- [ ] **Step 2：** 运行，确认失败；实现。
- [ ] **Step 3：** 看一遍：清空数据目录后启动 → 进引导；每一步都走到；填一个假 key 点测试连接 → 看到"key 不对"的说明；跳过去看示例 → 能转 3D、输入框不可用；设置里每一项都能改并在重启后保留；案例库两组都有内容。浅色、深色各一遍，对照界面清单。
- [ ] **Step 4：** 运行全部测试，提交：`feat: 引导、设置、案例库和示例会话`。

---

### Task 13：窗口和 caliper 命令

**Files：** Create `cad_agent/app.py`、`scripts/demo_script.json`、`tests/test_app.py`；Modify `cad_agent/llm/fake.py`、`pyproject.toml`

**Interfaces：**
- Produces：
  ```python
  # app.py
  def main(argv: list[str] | None = None) -> int: ...     # caliper
  def gui_main() -> None: ...                             # caliper-app：不带黑窗口的入口，等于 main([])
  def build_hub(settings: Settings, *, script: Path | None = None) -> Hub: ...
  # llm/fake.py
  def load_script(path: Path) -> list[LLMReply]: ...      # JSON：[{"content": "...", "tool_calls": [{"name", "args"}]}]
  ```
  - `caliper`（不带参数）：读设置 → 起本机服务 → 开 `pywebview` 窗口（标题 `卡尺 Caliper`，初始 1360×860，最小 1100×700）加载 `http://127.0.0.1:<端口>/?t=<令牌>`。窗口关掉后停服务、关掉所有工作台，返回 0。
  - `caliper --browser`：不开窗口，用默认浏览器打开同一个地址，终端里按 Ctrl+C 退出。
  - `caliper --cli [--config <文件>]`：进现有的终端对话模式；不给 `--config` 时用设置文件和钥匙串里的 key。
  - `caliper --demo-script <文件>`：开发和走查用，模型换成 `ScriptedLLM(load_script(文件))`，沙盒是真的，不需要 key。不写进 `--help` 的正文，只在最后一行注明"开发用"。
  - `pywebview` 导入或启动失败：打印一句中文说明（原文见"界面文字"），自动改用 `--browser` 的方式。
  - 没有 key 也能启动（界面会进引导页）；智能体在第一次要调用模型时才需要 key，没有就让这一轮以 `failed` 结束并提示去设置里填。
  - `pyproject.toml`：`[project.scripts] caliper = "cad_agent.app:main"`；`[project.gui-scripts] caliper-app = "cad_agent.app:gui_main"`。
- `scripts/demo_script.json`：一份"带孔的安装板"的完整剧本——先提一个问题、整理需求单、规划两个阶段、每个阶段先检查后特征再 build、交付；然后是一次"孔径改成 8"的修改。特征代码只用速查表里的写法。

- [ ] **Step 1：** 写测试 `tests/test_app.py`：
  - `test_load_script`、`test_demo_script_file_is_valid`（能读、每个工具名都在 12 个工具里）。
  - `test_demo_script_runs_end_to_end`（标记 `sca`）：用这份剧本加真实沙盒，不开窗口，按"做一个安装板 / 回答 / 确认 / 孔径改成 8"发四条消息，得到 v1 和 v2。
  - `test_main_browser_mode_starts_server`：把打开浏览器的函数换成记录地址的假函数、把"等待 Ctrl+C"换成立刻返回 → 地址是 `http://127.0.0.1:<端口>/?t=…`，请求它返回 200，退出后端口关了。
  - `test_window_failure_falls_back_to_browser`：把 `webview` 换成一导入就失败的假模块 → 打印了说明、走了浏览器那条路、返回 0。
  - `test_cli_mode_uses_keystore_when_no_config`。
  - `test_missing_key_turn_fails_with_hint`。
  - `test_entry_points_declared`（读 `pyproject.toml`）。
- [ ] **Step 2：** 运行，确认失败；实现；`.venv\Scripts\python -m pip install -e ".[dev]"` 后确认 `.venv\Scripts\caliper --help` 能运行。
- [ ] **Step 3：** 运行全部测试，提交：`feat: 桌面窗口和 caliper 命令`。

---

### Task 14：完整走查

**Files：** Create `docs/walkthrough-windows.md`；Modify `README.md`

- [ ] **Step 1：** 运行 `.venv\Scripts\caliper --demo-script scripts\demo_script.json`，在真的桌面窗口里（不是浏览器）完整走一遍，对应设计文档成功标准 5：引导（跳过）→ 新会话 → 提需求 → 回答问题 → 确认 → 看到规划和阶段进度 → 逐阶段建模、工具树、阶段折叠 → 交付卡片 → 模型页签转 3D、拖阶段刻度 → 检查页签三块 → 参数页签改数并应用 → 版本对比 → 存为案例 → 案例库里看到 → 设置里切深色 → 关掉窗口重开，会话还在、能接着发消息。
- [ ] **Step 2：** 每一步截一张图，连同"看到了什么、和预期是否一致"写进 `docs/walkthrough-windows.md`。发现的问题当场修，修完重走那一步；修不了的如实写在文档最后的"已知问题"里。
- [ ] **Step 3：** 窗口缩到 1100×700 再看一遍三栏布局和各页签；深色下再看一遍对话栏和工作台。
- [ ] **Step 4：** README 的"网页演示"一节前面加一节"桌面端"：怎么启动、三栏各是什么、参数面板怎么用、示例会话；写明现在还没有安装脚本（计划 4），先用 `.venv\Scripts\caliper` 启动。
- [ ] **Step 5：** 运行全部测试，提交：`docs: Windows 桌面端走查记录`。

---

## 做完之后

- `docs/progress.md` 最后写一段"计划 3 小结"：测试总数、走查里发现并修掉的问题、留下的已知问题。
- 旧的 `cad_agent/web/` 这时还在、还能用，计划 4 里才退役。

---

## 界面文字

下面的原文逐字照抄。`<…>` 是运行时填入的内容。

新会话的空状态：

```text
说说你想做什么零件。不用一次说全，缺的尺寸我会问你。
```

三个例子（点了就作为第一条消息发出去）：

```text
做一个放在桌上看视频的手机支架
做一个法兰盘，外径 120，上面一圈 6 个螺栓孔
做一个装电路板的小盒子，外形 80×50×30
```

输入框的提示文字：

```text
说说要做什么，或者要怎么改
```

示例会话里输入框的说明：

```text
这是一段录制好的示例，只能看。想自己做一个，点左上角的"新会话"。
```

连接断开：

```text
连接断开，正在重试
```

参数页签不能改时的说明：

```text
交付第一个版本之后，就可以在这里直接改数值。
```

```text
正在运行，等这一轮结束再改。
```

手动改数失败后，"让助手处理"发出去的话：

```text
我在参数面板里把 <参数名和新旧数值，多个用顿号连接，如 hole_d 从 6 改成 8> 之后，检查没有通过，请帮我处理。
```

3D 退回截图时的说明。没有 WebGL 时：

```text
这台电脑现在显示不了三维画面，先用截图代替。
```

STL 加载失败时：

```text
三维模型没有加载出来，先用截图代替。
```

删除会话的确认：

```text
删除"<标题>"？它的全部版本和文件都会一起删掉，不能恢复。
```

引导第 2 步，key 存在哪里的说明：

```text
密钥只保存在这台电脑的系统钥匙串里（Windows 的凭据管理器、Mac 的钥匙串），不会写进任何文件，也不会发到模型服务以外的地方。
```

环境变量里已经有 key 时：

```text
已经从环境变量 <变量名> 读到密钥，不用再填。
```

测试连接的结果：

```text
连接正常。
```

```text
密钥不对，或者没有权限用这个模型。请检查密钥和模型名。
```

```text
连不上模型服务。请检查网络和地址。
```

```text
模型服务返回了错误：<错误的前 80 个字符>
```

还没有 key 就发了消息：

```text
还没有可用的密钥。到右上角的"设置"里填好密钥，再发一次。
```

窗口打不开时终端里的说明：

```text
桌面窗口打不开（<原因的前 80 个字符>），改用浏览器打开。Windows 上通常是缺少 WebView2 运行时，可以运行 caliper doctor 查看。
```

案例库"我保存的"为空时：

```text
还没有保存过案例。交付一个满意的零件后，在"版本"里点"存为案例"，以后做相似的零件时会拿它当参考。
```

流程开关的说明，依次是分阶段、参数扰动验证、看图审查、案例库：

```text
把零件拆成几个阶段，一个阶段验证通过了再做下一个。关掉后退回到一次做完的老流程。
```

```text
交付前把每个参数改掉 20% 试一次，确认检查真的管得住它。关掉后交付更快，但"参数没起作用"这类问题不会被发现。
```

```text
交付前让模型只看渲染图再核对一遍形状。需要能看图的模型。
```

```text
规划时参考以前做成功的相似零件。
```
