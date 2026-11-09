# CAD 建模智能体 · 网页前端（设计 + 实施计划）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal：** 给智能体加一个本地网页界面，演示时用它代替命令行：
- 左边是对话；
- 右边四块：01 模型（页面里能转的 3D）、02 检查、03 需求单、04 版本。

演示时必须稳：出任何错，页面都不能卡死，服务也不能退出。

**用户定的：** 风格是"苹果风 + 瑞士风，简约，但有设计感和构成感"；3D 要在页面里能转。

**做法：**
- 后端只用 Python 标准库（`http.server`），不加新的 Python 依赖。
- 前端是原生 HTML/CSS/JS，没有构建步骤。
- three.js 下载到项目里（固定版本，MIT 许可），演示时不依赖外网 CDN。
- 字体用系统字体，不用 Google Fonts（国内经常打不开）。
- 智能体的核心流程不改。只加两样：交付时多导出一份 STL；会话日志多一个"有人在听"的钩子。

**执行规则：** 照 `CLAUDE.md`。第 1.1 版计划的 Global Constraints 继续有效。偏离记录接着当时的最大编号往下编。旧测试一律不动。

---

## 设计

### 视觉规范（写进 `cad_agent/web/static/style.css` 的 `:root`）

| 用途 | 值 |
|---|---|
| 背景 / 块底 | `--bg: #FFFFFF`、`--surface: #F5F5F7` |
| 文字 / 次要文字 | `--ink: #1D1D1F`、`--ink-2: #6E6E73` |
| 细线 | `--hairline: #D2D2D7` |
| 可点的东西（按钮、链接、焦点框） | `--accent: #0071E3` |
| 通过 / 没通过 / 提醒 | `--pass: #188038`、`--fail: #D70015`、`--warn: #B25000`（在白底上对比度都 ≥ 4.5:1） |
| 构成色块（只用在品牌方块和当前版本标记） | `--mark: #E5322D` |
| 字体 | `-apple-system, BlinkMacSystemFont, "SF Pro Text", "PingFang SC", "Helvetica Neue", "Microsoft YaHei", sans-serif`；参数和代码用 `"SF Mono", "Cascadia Mono", Consolas, monospace` |
| 字号阶梯 | 12 / 14 / 16 / 20 / 28 / 56 px；正文 16px、行高 1.5；数字用 `font-variant-numeric: tabular-nums` |
| 间距阶梯 | 4 / 8 / 12 / 16 / 24 / 32 / 48 px |
| 圆角 | 块 16px，按钮和标签 10px |
| 动效 | 悬停和切换 200ms ease-out；遵守 `prefers-reduced-motion` |

"构成感"靠这几样做出来：
- 每块顶上一条 2px 的 `--ink` 粗线；左上角是瑞士风编号 `01 模型`、`02 检查`、`03 需求单`、`04 版本`（12px，字距 0.08em）。
- 检查块里有一个 56px 的大数字，比如 `12/12`。
- 标题前有一个 10px 的 `--mark` 红色小方块，作为品牌标记。
- 严格的 12 栏网格，不用阴影。

图标用内联 SVG（线条风格，1.5px 描边），不用 emoji。

### 布局

- 页面最大宽 1440px，12 栏，栏间距 24px。
- 顶栏一行：红方块 + "CAD 建模助手"；右边是模型名，再加一个用量标签，例如"本次会话 ¥0.42 · 缓存命中 89%"（省钱的亮点放在这里）。
- **左栏（4 栏，最小 360px）对话：**
  - 用户的话靠右，底色 `--surface`；助手的话靠左。
  - 每条助手消息下面有一行小灰字："模型调用 3 次 · ¥0.05"。
  - 提问时，问题按编号列出。
  - 请确认时：显示需求单摘要和两个按钮，"确认"（直接发送"确认"）和"我要修改"（把光标放进输入框）。
  - 交付时：一张卡片，写着版本号、检查通过数，并有"下载 STEP"和"下载 STL"两个链接。
  - 智能体工作时：底部显示实时进度（"正在思考…""写特征 base-plate""运行检查：12/12 通过"），发送按钮变灰。
  - 输入框按 Enter 发送，Shift+Enter 换行。
- **右栏（8 栏）卡片网格：**
  - 01 模型：占满 8 栏、高 420px。
  - 02 检查（4 栏）、03 需求单（4 栏）并排。
  - 04 版本：占满 8 栏。
- 窗口宽度小于 1100px 时，左右两栏改成上下排；小于 700px 时，卡片全部单栏。

### 各块内容

- **01 模型：**
  - 用 three.js 显示当前版本的 `model.stl`。z 轴朝上（`camera.up = (0, 0, 1)`），z=0 平面画一个淡网格，相机自动对准模型。
  - 可以拖动旋转、滚轮缩放、右键平移。
  - 工具栏三个按钮：重置视角、线框开关、切换到截图。
  - 没有 STL、WebGL 不可用、或加载出错时，自动改成显示 `view.png`，并提示"3D 预览不可用，显示的是截图"。
  - 还没交付时显示空状态"交付后在这里显示模型"。
- **02 检查：**
  - 大数字显示"通过数/总数"。
  - 下面逐条列出：通过或没通过、检查名、实测值和期望值。没通过的排在前面，用 `--fail` 标出。
  - 数据来自最近一次 build。
- **03 需求单：**
  - 参数表三列：名称（等宽字体）、数值 + 单位、来源标签（"用户"实心，"建议"描边）。
  - 下面是组成部分的列表。
  - 有待问问题时，用 `--warn` 标出。
- **04 版本：**
  - 版本号排成一行标签（v1、v2…），当前版本带红色小方块。
  - 选两个版本，会显示参数变化（用 `cli.diff_briefs` 的结果）和两张截图并排；每个版本都有下载链接。

### 后端接口

服务只监听 `127.0.0.1`。

| 接口 | 作用 |
|---|---|
| `GET /` 和 `GET /static/<文件>` | 页面和静态文件；只能取 `static` 目录里的文件，路径里有 `..` 或指到目录外的一律 404 |
| `GET /api/state` | 页面需要的全部状态，见下 |
| `POST /api/message`，body `{"text": "..."}` | 开始处理一条消息，立即返回 202；空消息返回 400；正在忙返回 409 |
| `POST /api/reset` | 开一个新会话（忙时返回 409） |
| `GET /api/diff?a=v1&b=v2` | 两个版本的参数变化 |
| `GET /files/<版本>/<文件名>` | 只允许 `view.png`、`model.step`、`model.stl`、`model.py`、`checks.json`，从当前会话的版本目录读；其余一律 404 |

`/api/state` 返回的 JSON：

```text
busy: bool
model: str
transcript: [{role: "user"|"assistant", kind, text, version, llm_calls, cost}]
activity: [str]          # 当前这一轮的实时进度，一轮结束就清空
brief: brief.to_dict() 的结果
checks: [{id, type, passed, measured, expected, detail}]   # 最近一次 build
versions: [{name, has_stl, has_png}]
stats: {cost, prompt_tokens, cached_tokens}                # 本次会话累计；cost 可以是 null
error: str | null        # 上一轮出的意外错误（中文），没有就是 null
```

**线程：**
- 一条消息放在一个后台线程里处理，同一时间只处理一条。
- 状态快照由后台线程在每次写日志时生成，存进有锁保护的变量，`/api/state` 只读这份快照。这样网页读状态时，不会和智能体同时改同一份数据。
- 后台线程里的任何异常都要接住，写进 `error` 并显示在对话里，服务不退出。

---

## 文件

```
cad_agent/web/__init__.py
cad_agent/web/__main__.py      启动：python -m cad_agent.web --config config.toml [--port 8765] [--no-browser]
cad_agent/web/app.py           AppState、LiveSession、describe_event、快照
cad_agent/web/server.py        HTTP 路由
cad_agent/web/static/index.html  style.css  app.js  viewer.js
cad_agent/web/static/vendor/three/three.module.js  OrbitControls.js  STLLoader.js  LICENSE
start_web.bat                  双击启动（演示用）
tests/test_web.py
```

---

### Task 1：交付时多导出一份 STL

**Files：** Modify `cad_agent/sandbox/runner.py`、`cad_agent/sandbox/execute.py`、`cad_agent/session.py`、`cad_agent/agent/loop.py`（或 `delivery.py`）、`docs/sca-api-notes.md`；Test `tests/test_execute.py`、`tests/test_session.py`、`tests/test_loop.py`

**Interfaces：**
- `run_job(...)` 加一个关键字参数 `export_stl: Path | None = None`。
- `RunResult` 加两个字段 `stl_path: Path | None = None`、`stl_error: str | None = None`。
- `Session.new_version(...)` 加一个关键字参数 `stl_src: Path | None = None`；给了就复制成版本目录里的 `model.stl`。
- 交付时把 STL 和 STEP 一起导出。
- STL 导出失败**不影响交付**：版本照常生成，只是没有 `model.stl`，日志记 `stl_error`。

- [ ] **Step 1：** 先写一小段探测脚本，跑通 `exporter.export_product_package_to_stl` 的真实用法（参数、精度选项、返回值），写进 `docs/sca-api-notes.md`，然后才能用。
- [ ] **Step 2：写失败的测试。**
  - `test_exports_stl`（标记 sca）：一个长方体，导出的 STL 非空，路径在中文目录下也行。
  - `test_stl_failure_does_not_block_delivery`：用假的 run_job 返回 `stl_error`，结果照样 delivered，版本目录里没有 `model.stl`。
  - `test_new_version_copies_stl`。
- [ ] **Step 3：** 实现。运行全部测试，预期全部通过。提交 `feat: 交付时导出 STL`。

### Task 2：后端（状态、线程、接口）

**Files：** Create `cad_agent/web/__init__.py`、`app.py`、`server.py`、`__main__.py`；Test `tests/test_web.py`

**Interfaces：**

```python
# app.py
def describe_event(kind: str, data: dict) -> str | None: ...
# 把一条日志变成一句给人看的进度，不需要显示的返回 None。必须覆盖：
#   assistant 带工具调用 → "正在调用：<工具名>、…"，没有工具调用 → "正在整理回复"
#   tool upsert_feature → "写特征 <slug>"；set_checks → "写检查项"；update_brief → "更新需求单"
#   build → "运行检查：<通过数>/<总数> 通过"，没通过 → "运行没通过：<第一条原因>"
#   auto → "程序自动重新 build" 或 "程序自动请你确认"

class LiveSession(Session):        # 重写 log：先调 super().log，再通知 listener
    listener: Callable[[str, dict], None] | None

class AppState:
    def __init__(self, make_agent: Callable[[], tuple[Agent, Session]], model_name: str) -> None: ...
    def snapshot(self) -> dict: ...       # /api/state 的内容（加锁拷贝）
    def submit(self, text: str) -> int: ...   # 202 / 400 / 409
    def reset(self) -> int: ...               # 200 / 409
    def wait_idle(self, timeout: float) -> bool: ...   # 测试用

# server.py
def make_server(state: AppState, host: str = "127.0.0.1", port: int = 8765) -> ThreadingHTTPServer: ...
```

- `__main__.py`：
  - 读配置（出错时打印中文信息，返回 1）；
  - 用 `cli.build_agent` 的组装方式造智能体，但会话换成 `LiveSession`；
  - 启动服务，打印网址，自动打开浏览器（`--no-browser` 时不打开）；
  - 端口被占用时，换下一个端口，最多试 10 个；
  - Ctrl+C 正常退出。

- [ ] **Step 1：写失败的测试**（都用 `ScriptedLLM` 和测试里的假 run_job，不联网；服务开在 0 号端口，跑在后台线程里）。
  - `test_describe_event_cases`：上面列的每一种各一个例子，外加一个返回 None 的。
  - `test_message_flow`：
    - POST 一条消息，得到 202；
    - 等到空闲后，`/api/state` 里 transcript 有用户和助手两条；
    - `activity` 已经清空；
    - `brief` 是需求单的内容。
  - `test_busy_returns_409`：
    - 用一个会等 `threading.Event` 的假模型，让第一条消息卡住；
    - 这时再发一条，返回 409；
    - 等待期间读 `/api/state`，`busy` 为真，`activity` 不为空。
  - `test_empty_message_400`。
  - `test_agent_crash_is_reported`：假模型抛出意外异常 → 状态里 `error` 有中文说明，服务还能接下一条消息。
  - `test_files_whitelist`：
    - 交付 v1 后，`/files/v1/view.png` 返回 200；
    - `/files/v1/../../config.toml`、`/files/v1/brief.json`、`/static/../app.py` 都返回 404。
  - `test_diff_endpoint`：交付 v1、v2 后，返回的变化里有 `65 → 70`。
  - `test_reset`。
  - `test_binds_localhost_only`：`make_server` 默认的 host 是 `127.0.0.1`。
- [ ] **Step 2：** 运行，预期失败。
- [ ] **Step 3：** 实现，每个文件不超过 300 行。运行全部测试，预期全部通过。
- [ ] **Step 4：** 提交 `feat: 网页前端的后端`。

### Task 3：页面

**Files：** Create `cad_agent/web/static/*`、`start_web.bat`；Modify `README.md`；Test `tests/test_web.py`

- [ ] **Step 1：** 把 three.js r160 的三个文件和 LICENSE 下载进 `static/vendor/three/`（这是用户批准过的依赖）：
  - 从 `https://cdn.jsdelivr.net/npm/three@0.160.0/` 下载 `build/three.module.js`、`examples/jsm/controls/OrbitControls.js`、`examples/jsm/loaders/STLLoader.js`、`LICENSE`。
  - `index.html` 用 import map 把 `"three"` 指到本地的 `three.module.js`。
- [ ] **Step 2：写失败的测试。**
  - `test_static_files_offline_ready`：
    - 三个 vendor 文件都在；
    - 所有静态文件里都不出现 `fonts.googleapis`、`cdn.jsdelivr`、`unpkg`；
    - `index.html` 里有 import map；
    - 有 `01 模型`、`02 检查`、`03 需求单`、`04 版本` 四个块的标题。
  - `test_index_served`：`GET /` 返回 200，是 HTML。
- [ ] **Step 3：** 按上面的"设计"写 `index.html`、`style.css`、`app.js`、`viewer.js`。
  - `app.js` 每 1 秒轮询一次 `/api/state`，内容没变就不重画（比较快照的 JSON）。
  - 网络出错时，顶栏显示"连接断开，正在重试"，恢复后自动消失。
  - `viewer.js` 只负责 3D：
    - 换版本时，释放旧模型的几何体和材质；
    - 窗口大小变化时，跟着调整画布；
    - 失败时退回截图。
  - 可以用键盘操作：发送、版本标签、工具栏按钮都能用 Tab 选中，焦点框看得见。
- [ ] **Step 4：** 写 `start_web.bat`：切换到脚本所在目录，运行 `.venv\Scripts\python -m cad_agent.web --config config.toml`，结束后 `pause`。README 加一节"网页演示"：怎么启动，以及演示前要检查的几件事（key 已设置、网络通、先跑一遍手机支架）。
- [ ] **Step 5：** 运行全部测试，预期全部通过。提交 `feat: 网页前端页面`。

### Task 4：实际演示检查（要用真实模型，花费约一个任务的钱）

- [ ] **Step 1：** 检查 key 是否设置（不打印）。用 `start_web.bat` 的同一条命令启动服务（`--no-browser`），在应用内置的浏览器里打开。
- [ ] **Step 2：** 在网页里完整走一遍手机支架：
  - 发"做一个放在桌上看视频的小支架"；
  - 按 `benchmarks/tasks/phone_stand.yaml` 的隐藏需求回答问题；
  - 点"确认"，等交付 v1；
  - 发"支撑角度改成 70 度"，等交付 v2；
  - 在 04 版本里比较 v1 和 v2。
- [ ] **Step 3：** 逐项确认，每项都截图存进 `docs/web-demo/`：
  - 3D 能转，z 轴朝上；
  - 线框开关、重置视角能用；
  - 检查块的大数字和列表对得上；
  - 需求单的来源标签对；
  - 版本对比显示 `65 → 70`，两张截图并排；
  - STEP 和 STL 能下载；
  - 浏览器控制台没有报错；
  - 窗口宽 1440 和 1024 时布局都正常。
- [ ] **Step 4：** 发现问题就修，修完重测出问题的那一项。全部通过后，在 `docs/progress.md` 记一段，提交 `docs: 网页演示检查`。推送前先问用户。
