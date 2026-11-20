# 3.0 · 计划 3：展台界面 · 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal：** 把桌面端整个换成"展台"：零件或产品是画面的主角，浅色影棚、深色黑曜；需求单、对话记录、检查、版本、调参数都收在菜单和抽屉里；能转到底下看、有坐标轴小图；多零件能单独看、炸开、透视、剖开、播放运动；能对比修改前后的两个版本。

**Architecture：** 后端（本机服务、事件推送、会话、工作台）基本不动，只加预览和对比两个接口。前端 `cad_agent/desk/static/` 重写：保留纯逻辑的 `api.js`、`store.js`、`format.js`、`dom.js`、`params-logic.js`，其余换成新模块。三维部分拆成场景、坐标轴、看图工具、多零件、运动几个模块，各自不超过 300 行。

**Tech Stack：** 原生 JavaScript 模块、three.js r160（已在项目里）、Archivo 字体（新放进项目，SIL 开源许可）。不引入框架和构建步骤。

**Spec：** `docs/superpowers/specs/2026-11-20-datum-v3-design.md`（第 7 节全部）。视觉以两个小样为准：`docs/design/v3-stage-prototype.html`、`docs/design/v3-assembly-prototype.html`。

**前置：** 计划 2 完成（本计划读计划 2 Task 13 定下的状态格式、Task 10 定下的 `motion.json` 格式）。

## Global Constraints

- 前几版计划的规矩全部继续有效（见 `CLAUDE.md`）。**不调用任何真实的模型接口**；走查用 `--demo-script` 的剧本加真实沙盒。
- 页面离线可用，不加载任何网络资源。
- 颜色（照抄设计文档第 7.2 节）：
  - 浅色影棚：背景径向渐变 `#FFFFFF` → `#EEEDF1` → `#D9D8DE`；文字 `#17151B`；次要文字 `#77727F`；强调 `#17151B`；会动的零件 `#4767E8`；通过 `#1F8A4C`。
  - 深色黑曜：背景 `#1C2230` → `#0A0D13` → `#030405`；文字 `#EEF1F6`；次要文字 `#8A93A6`；强调 `#A9CBFF`；会动的零件 `#7FB2FF`；通过 `#7FE0A8`。
  - 颜色只出现在 `tokens.css`；三维材质的颜色从 `motion.json` 的材料颜色或 `tokens.css` 的变量读。
- 字体：中文用系统字体（`"Microsoft YaHei UI", "PingFang SC", system-ui`）；拉丁字母和数字用 Archivo（项目里的字体文件）。
- 浮在舞台上的东西用半透明加背景模糊；圆角为胶囊形或 16–22px；不用方框套方框；不用投影阴影做卡片。
- 动效：抽屉、面板约 300ms；视角切换约 450ms；遵守"减少动态效果"（关掉过渡，运动不自动播放）。
- 界面文字：一律平常话；本计划末尾"界面文字"一节里的原文逐字照抄；不出现设计文档第 7.9 节"不要写"那一列的词。
- 最小窗口 1100×700，在它和 1600×1000 下都不截断、不重叠。
- 每个文件不超过 300 行；纯逻辑模块要有 `node --test` 的测试。
- **开工前**：当前会话里有 `ui-consistency:finding-patterns` 技能就先运行它；把结果和下面"界面清单"合并，写进 `docs/ui-checklist.md`（替换第二版的那份）。每做完一个画面逐条对照；有 `ui-consistency:verifying` 技能时用它检查。
- **要改的旧测试**：见清单，清单之外一律不动。
- 偏离记录接着编号。每个任务收尾：全部测试通过 → 提交 → `docs/progress.md` 追加一段（标题写"3.0 计划 3 Task N"）。

**界面清单（每个画面都要满足）：**
1. 颜色只用 `tokens.css` 的变量。
2. 零件或产品始终是画面最大的东西；浮层不挡住它的中心。
3. 主要按钮一个画面最多一个（强调色实心）；其余是玻璃质感的普通按钮或文字按钮。
4. 数字用 Archivo、等宽数字、带单位。
5. 状态不只靠颜色：通过、没通过、没做都有文字。
6. 空状态有一句说明和一个下一步。
7. 出错时说清发生了什么、可以怎么做；不显示原始异常。
8. 键盘能到达所有能点的东西；焦点有清楚的描边；Esc 收起浮层。
9. 浅色、深色都看过；文字对比度不低于 4.5:1。
10. 1100×700、1600×1000 都看过。

## 要改的旧测试

| 测试 | 怎么改 |
|---|---|
| `tests/test_desk_style.py` 的 8 条 | 换成 Task 1 的同名新测试（检查的是新的颜色和规则） |
| `tests/test_desk_static.py::test_index_has_three_columns_and_import_map` | 换成 `test_index_has_stage_and_import_map` |
| `tests/test_desk_static.py::test_page_texts_are_verbatim` | 改为对照本计划末尾"界面文字"一节 |
| `cad_agent/desk/static/js/tests/tooltree.test.js`、`viewer-dims.test.js` | 随着 `tooltree.js`、`viewer-dims.js` 一起删除，由 Task 3、Task 5 的新测试接替 |
| `tests/test_desk_server.py` 里检查页面内容的断言 | 只改页面结构相关的字面值（比如容器的 id），不改令牌、白名单、错误码的断言 |

## Review Focus

1. 运动播放中用户拖动视角、切换零件、打开抽屉：播放不中断、不卡顿；切换版本时停止播放并回到初始位置。→ Task 7 `test_motion_player_state_machine`
2. 一个版本的 `motion.json` 读取失败或格式不对：产品照样按初始位置显示，运动条显示原因，不白屏。→ Task 7 `test_bad_motion_file_falls_back_to_rest`
3. 调参数时连续快速拖滑条：只保留最后一次的预览请求，前面的取消；预览回来时如果用户已经点了"应用"或关掉了面板，就丢掉这个预览。→ Task 6 `test_preview_debounce_and_stale_result`
4. 转到零件正下方再点"前"：视角平滑转过去，不翻转、不出现上下颠倒。→ Task 4 `test_view_snap_from_below_keeps_up_vector`
5. 两个版本对比时其中一个版本没有 STL（旧会话）：对比视图里那一边退回截图，并说明原因。→ Task 8 `test_compare_falls_back_to_png`
6. 窗口只有 1100×700 时，多零件的零件清单、运动条、底部输入框、右侧小卡片互不重叠。→ Task 10 走查第 7 步

---

## 文件结构

```
cad_agent/desk/static/fonts/Archivo.ttf  OFL.txt          （Task 1）
cad_agent/desk/static/css/tokens.css  base.css  stage.css  overlays.css  pages.css
cad_agent/desk/static/js/
  api.js  store.js  format.js  dom.js  params-logic.js     保留（按需小改）
  main.js          启动、路由（重写）
  theme.js         深浅色（保留，改变量）
  stage.js         舞台外壳：标题、进度、字幕、选项、输入框（Task 2）
  brief-card.js    舞台中间的需求单（Task 3）
  drawers.js       抽屉的开关、Esc、遮罩（Task 3）
  menu.js  history.js                                       （Task 3）
  inspector.js  inspector-checks.js  inspector-versions.js  （Task 3）
  view3d/scene.js  view3d/materials.js  view3d/gizmo.js  view3d/tools.js   （Task 4）
  view3d/assembly.js  view3d/labels.js                      （Task 5）
  tune.js          调参数面板（Task 6）
  motion.js        运动条和播放（Task 7）
  compare.js       修改前后对比（Task 8）
  pages/onboarding.js  pages/settings.js  pages/cases.js    （Task 9）
  tests/*.test.js
cad_agent/desk/routes.py   预览、对比两个接口（Task 6、Task 8）
docs/ui-checklist.md  docs/walkthrough-v3.md  docs/walkthrough-v3/*.png  （Task 10）
```

---

### Task 1：字体、颜色和基础样式

**Files：** Create `cad_agent/desk/static/fonts/Archivo.ttf`、`OFL.txt`、`css/stage.css`、`css/overlays.css`；Rewrite `css/tokens.css`、`css/base.css`、`css/pages.css`；Delete `css/layout.css`、`chat.css`、`bench.css`；Test `tests/test_desk_style.py`（按清单换）

- 字体：从 Google Fonts 的官方 GitHub 仓库下载 Archivo 的可变字体（宽度和粗细两个轴）和它的 `OFL.txt`。下载前把地址告诉用户；下载后在 `docs/progress.md` 里记下地址和文件的 SHA256。`@font-face` 用 `format("truetype")`，`font-display: swap`。
- `tokens.css` 的变量名（后面所有样式和脚本只用这些）：`--bg`（背景渐变）、`--ink`、`--mute`、`--acc`、`--acc-ink`（强调色上的文字色）、`--move`、`--ok`、`--bad`、`--glass`（玻璃底色）、`--line`（玻璃描边）、`--panel`（抽屉底色）、`--font-ui`、`--font-num`、`--r-pill`（999px）、`--r-card`（20px）、`--t`（过渡时长和曲线）。浅色写在 `:root`，深色写在 `:root[data-theme="dark"]`，`data-theme="system"` 时按 `prefers-color-scheme`。`--bad`：浅色 `#C93A2E`，深色 `#FF8A80`。
- `base.css`：正文 15px；按钮三种（`.btn-primary` 强调色实心、`.btn-glass` 玻璃、`.btn-text`）；输入框；焦点描边 2px `--acc`；`prefers-reduced-motion` 关过渡。

- [ ] **Step 1：** 写新的 `tests/test_desk_style.py`：
  - `test_token_values`：两套颜色等于 Global Constraints 的值；两套定义的变量名集合相同。
  - `test_contrast_at_least_4_5`：两套下 `--ink`、`--mute` 对背景最亮处和最暗处的对比度都不低于 4.5；`--acc-ink` 对 `--acc` 不低于 4.5。
  - `test_no_external_resources_and_font_is_local`：样式里没有 `http`；`@font-face` 指向 `fonts/Archivo.ttf`；`OFL.txt` 存在。
  - `test_colors_only_in_tokens`：除 `tokens.css` 外没有颜色字面值（`#xxx`、`rgb(`、`hsl(`）。
  - `test_no_box_shadow_cards`：没有 `box-shadow`（焦点描边除外，焦点描边只能写在 `:focus-visible` 规则里）。
  - `test_reduced_motion_rule_exists`。
  - `test_radius_values`：`border-radius` 只能是 `0`、`50%`、`var(--r-pill)`、`var(--r-card)`、`8px`–`12px`（小控件）。
  - `test_buttons_defined`：三种按钮类都有。
- [ ] **Step 2：** 运行，确认失败；实现；运行全部测试，提交：`feat: 展台的字体、颜色和基础样式`。

---

### Task 2：舞台外壳

**Files：** Rewrite `static/index.html`、`js/main.js`；Create `js/stage.js`、`js/tests/stage.test.js`；Modify `js/store.js`（新事件）、`tests/test_desk_static.py`（按清单换一条）

**Interfaces：**
- `stage.js` 导出：`phaseView(state) -> {title, subtitle, caption, choices, center}`（纯逻辑，可测），`mountStage(root, actions)`、`renderStage(state)`。
  - `center` 取值：`"welcome" | "brief" | "confirm" | "model" | "failed"`，按设计文档第 7.3 节的表从 `state.phase`、`state.brief`、`state.versions`、最后一条助手消息推出来。
  - `title`：没有零件名时是界面文字里的"新零件"；`subtitle` 按表和界面文字。
  - `choices`：最后一条助手消息是提问且只有一个问题、并且问题里给了选项（"A 还是 B"、带"建议"的数值）时，给出按钮；否则为空，靠输入框回答。
- 页面骨架：`#view`（三维画布，占满窗口）、`.title`、`.caption`、`.choices`、`.prompt`（输入框和发送 / 停止按钮）、左上菜单按钮、左下对话记录按钮、右下调参数按钮、右边大数字、右上坐标轴区域、多零件时左侧零件清单和底部运动条的容器。
- `store.js`：处理计划 2 Task 13 新增的事件 `part_done`、`assembly`；`state` 事件照旧整体替换。

- [ ] **Step 1：** 写测试 `js/tests/stage.test.js`：`phaseView` 的六种情况各一例（标题、副标题、center 的值对）；`test_choices_only_for_single_question_with_options`；`test_multipart_subtitle_counts_parts`。`store.test.js` 加 `part_done`、`assembly` 两个事件的测试。`tests/test_desk_static.py::test_index_has_stage_and_import_map`：页面里有上面列的容器；import map 把 `three` 指到本地文件。
- [ ] **Step 2：** 运行，确认失败；实现。
- [ ] **Step 3：** 用 `datum --demo-script scripts/demo_script.json --browser` 在应用内置浏览器里看：刚打开、提问、确认、正在做、做好了五个时刻，标题、字幕、选项、输入框的位置和小样一致。对照界面清单。
- [ ] **Step 4：** 运行全部测试，提交：`feat: 展台的外壳和进度`。

---

### Task 3：需求单、抽屉、对话记录、检查和版本面板

**Files：** Create `js/brief-card.js`、`js/drawers.js`、`js/menu.js`、`js/history.js`、`js/inspector.js`、`js/inspector-checks.js`、`js/inspector-versions.js`、`js/tests/inspector.test.js`；Delete `js/chat.js`、`js/tooltree.js`、`js/cards.js`、`js/sidebar.js`、`js/bench*.js`、`js/titleblock.js`、`js/tests/tooltree.test.js`

**Interfaces：**
- `brief-card.js`：`briefRows(brief) -> [{label, value, unit, tag: "你给的"|"建议"|null, waiting: bool}]`（纯逻辑）；需求单卡片在 `center` 为 `brief` 或 `confirm` 时显示在舞台中间；`confirm` 时下面是"没问题，开始做"（主要按钮，发送"确认"）和"我还要改"（把焦点放到输入框）；多零件时分"零件""共用的尺寸""各零件的尺寸""怎么连""会动的地方"几块。确认后卡片向上飞走、缩小、淡出（减少动态效果时直接消失）。
- `drawers.js`：`openDrawer(id)`、`closeAll()`；同一时间只开一个；遮罩点一下关；Esc 关；打开时焦点移进去，关闭时回到打开它的按钮。
- `menu.js`：做一个新的、最近做过的（名字、时间、几个版本；改名、删除前确认）、案例库、设置。
- `history.js`：完整对话；每一轮里每一步做了什么可以展开（写了几条检查、做了什么、量了几项、通过没有），多零件时按零件分组。
- `inspector-checks.js`：`groupChecks(checks) -> [{group, items}]`（纯逻辑：单零件按步骤、多零件按零件，装配一组放最后）；每条：状态文字、名字、实测、期望、容差；"每个尺寸都确认过真的起作用"一块；看图审查一块。
- `inspector-versions.js`：每个版本：缩略图、第几版、时间、变化；按钮：对比（Task 8）、下载 STEP、下载 STL、在文件夹中显示、存为案例；多零件时下载区分"整个产品"和各零件。

- [ ] **Step 1：** 写测试 `js/tests/inspector.test.js`：`briefRows` 的来源标签和"等你回答"；`groupChecks` 单零件、多零件各一例；`test_check_status_has_text`（每条都有"量过，对"/"没过"/"没做"之一的文字）。
- [ ] **Step 2：** 运行，确认失败；实现；删除旧模块和它们的测试。
- [ ] **Step 3：** 在应用内置浏览器里走一遍剧本：需求单在舞台中间填起来、确认后飞走；三个抽屉都能开关、Esc 能关、键盘能到达；检查和版本面板的内容对。浅色、深色各一遍。
- [ ] **Step 4：** 运行全部测试，提交：`feat: 需求单、抽屉、检查和版本面板`。

---

### Task 4：三维舞台和看的方式

**Files：** Create `js/view3d/scene.js`、`js/view3d/materials.js`、`js/view3d/gizmo.js`、`js/view3d/tools.js`、`js/tests/gizmo.test.js`、`js/tests/materials.test.js`；Delete `js/viewer.js`、`js/viewer-dims.js`、`js/tests/viewer-dims.test.js`

**Interfaces：**
- `scene.js`：`createScene(container, {theme})` 返回 `{showParts(parts), setTheme(t), flyTo(dir), setOrtho(on), resize(), dispose(), camera, renderer, root}`。`parts` 是 `[{id, url, matrix, material, color, finish}]`（单零件就是一个）。轨道控制不限制上下角度，能平移；相机在地面以下时阴影和网格隐藏；加载 STL 失败时退回显示截图并给出界面文字里的说明。
- `materials.js`：`materialFor(finish, color, theme) -> {color, roughness, metalness}`（纯逻辑）：`matte`、`metal`、`polished` 三种质感，深色时整体略提亮。
- `gizmo.js`：`axisLayout(cameraQuaternion) -> [{axis, x, y, depth, positive}]`（纯逻辑，X 红、Y 绿、Z 蓝，Z 朝上——建模坐标的 Z 对应 three.js 的 Y）；`snapDirection(axis, positive) -> [x,y,z]`；点轴或"前、上、右、立体、底"平滑转过去。转到正上或正下时给相机的 up 向量加一个很小的偏移，避免翻转。
- `tools.js`：剖开（开关 + 滑条，沿 X、Y、Z 选一个方向）、尺寸标注（外形尺寸线；调参数面板里鼠标停在参数上时，按检查的 `selected` 在零件上标点，多零件时点要乘上零件的摆放矩阵）、正交视图开关。
- 每一步做完时，零件切到这一步的 STL，新旧淡入淡出（约 400ms）。

- [ ] **Step 1：** 写测试：`gizmo.test.js`：正视、俯视、底视三个相机朝向下各轴的位置；`test_view_snap_from_below_keeps_up_vector`（Review Focus 4）；`materials.test.js`：三种质感、深浅色。
- [ ] **Step 2：** 运行，确认失败；实现；删除旧模块。
- [ ] **Step 3：** 在应用内置浏览器里看：拖着转到底下、地面网格消失；点坐标轴每个轴和五个按钮；剖开、尺寸标注、正交各开一次；把 STL 地址改错后退回截图。浅色、深色各一遍。
- [ ] **Step 4：** 运行全部测试，提交：`feat: 三维舞台、坐标轴和看图工具`。

---

### Task 5：多零件的看法

**Files：** Create `js/view3d/assembly.js`、`js/view3d/labels.js`、`js/tests/assembly.test.js`

**Interfaces：**
- `assembly.js`：`explodedMatrix(rest, direction, amount, scale) -> matrix`（纯逻辑：沿方向平移 `amount × scale`，`scale` 取产品包围盒对角线的 0.6 倍）；`isolateOpacity(partId, focusId, xray) -> number`（纯逻辑：不透视时，聚焦零件 1、其余 0.12；透视时，聚焦零件 0.9、其余 0.22；没有聚焦时透视全部 0.35、不透视全部 1）。
- 左侧零件清单：每行材料色块、名字、检查数；点一行聚焦，右边出现小卡片（尺寸、材料、检查数，界面文字里的格式）；"看全部"取消聚焦。正在做时当前零件在闪、做完的打勾。
- 左下：炸开滑条、透视、剖开、名字三个开关。
- `labels.js`：零件名字带引线，标签放在零件屏幕位置的左上或右上（看零件在屏幕的哪一半），标签之间重叠时依次往上错开；聚焦时只显示聚焦零件的名字；零件在相机后面时隐藏。

- [ ] **Step 1：** 写测试 `assembly.test.js`：`explodedMatrix` 的平移量；`isolateOpacity` 六种组合；`test_labels_do_not_overlap`（给四个在屏幕上挤在一起的点，排出来的标签框两两不相交）。
- [ ] **Step 2：** 运行，确认失败；实现。
- [ ] **Step 3：** 用 `scripts/demo_script_multi.json` 走到交付，在应用内置浏览器里看：零件清单聚焦每个零件、小卡片内容对；炸开到底再收回；透视、剖开、名字开关。浅色、深色各一遍。
- [ ] **Step 4：** 运行全部测试，提交：`feat: 多零件的单独看、炸开、透视和名字`。

---

### Task 6：调参数和预览

**Files：** Create `js/tune.js`、`js/tests/tune.test.js`；Modify `js/params-logic.js`、`cad_agent/desk/routes.py`；Test `tests/test_desk_preview.py`

**Interfaces：**
- 接口 `POST /api/sessions/<id>/preview`：`{"values": {...}}` → 计划 2 的 `preview_product`；返回 `{"files": {...}}`（文件地址）。正在跑一轮对话时 409；值不对 400（信息用界面文字里的原文）；同一会话新的预览请求到达时，取消正在跑的那个（`should_stop`）。
- `tune.js`：面板从底部升起，同时舞台往上挪（相机视口偏移，零件保持在可见区域中间）；按 `state.params_view` 的 `group` 分组；每行名字、滑条、数字框、单位、来源标签；改过的行左边有标记线。
  - `previewScheduler(sendFn, delayMs=400)`（纯逻辑，可测）：松开滑条或改完数字框后 400ms 内没有新的改动才发请求；发出新请求时取消上一个；收到结果时如果面板已关闭或已经点了"应用"，丢掉结果。
  - 预览回来后零件换成预览的样子，轮廓用虚线（`LineDashedMaterial`）表示这是预览；"还原"回到当前版本。
  - "应用"调用已有的参数直改接口；成功提示"已存为第 N 版"；失败按界面文字给出原因和"让模型帮我处理"。
- 鼠标停在某一行时，通知 `tools.js` 在零件上标出用到这个参数的检查选中的几何。

- [ ] **Step 1：** 写测试：`tune.test.js`：`test_preview_debounce_and_stale_result`（Review Focus 3）；分组；改过的行。`tests/test_desk_preview.py`：成功返回文件地址、对话进行中 409、坏值 400、第二个请求让第一个被取消（假的 `preview_product` 记录 `should_stop` 被触发）。
- [ ] **Step 2：** 运行，确认失败；实现。
- [ ] **Step 3：** 在应用内置浏览器里：交付后打开调参数，拖孔径滑条、等预览出来、点应用、看到新版本；改一个会让检查失败的值、看到原因和"让模型帮我处理"。
- [ ] **Step 4：** 运行全部测试，提交：`feat: 调参数面板和预览`。

---

### Task 7：运动条

**Files：** Create `js/motion.js`、`js/tests/motion.test.js`

**Interfaces：**
- `motion.js`：
  - `loadMotion(url) -> Promise<Motion | {error}>`：校验格式（计划 2 Task 10 的 `motion.json`）；格式不对返回 `{error}`。
  - `poseAt(joint, value) -> {partId: matrix}`（纯逻辑）：在相邻两个取样位置之间插值（平移线性插值，转动用四元数球面插值）；超出范围取端点。
  - `createPlayer(onFrame) -> {play(), pause(), seek(value), select(jointId), stop()}`：来回播放，一次单程 2.2 秒，缓动 `cubic-bezier(0.65, 0, 0.35, 1)`；减少动态效果时 `play()` 不自动开始，只能拖滑条。
- 运动条：每个关节一条，几个关节时用左右切换；播放 / 暂停、滑条、当前值（带单位）；下面一排小点，每个取样位置一个，没撞的是 `--ok`，撞了的是 `--bad`；撞了的位置拖到时，零件上用 `--bad` 标出两个零件。状态文字按界面文字。
- 切换版本时停止播放、回到初始位置。

- [ ] **Step 1：** 写测试 `motion.test.js`：`poseAt` 在取样点上、两点中间、超出范围；`test_motion_player_state_machine`（Review Focus 1：播放中 seek 停下；select 换关节回到初始；stop 回到初始）；`test_bad_motion_file_falls_back_to_rest`（Review Focus 2）；`test_reduced_motion_does_not_autoplay`。
- [ ] **Step 2：** 运行，确认失败；实现。
- [ ] **Step 3：** 用多零件剧本走到交付，在应用内置浏览器里播放、拖动、切换版本；手动改坏一个版本的 `motion.json` 看退回效果，看完改回来。
- [ ] **Step 4：** 运行全部测试，提交：`feat: 运动条和播放`。

---

### Task 8：修改前后的对比

**Files：** Create `js/compare.js`、`js/tests/compare.test.js`；Modify `cad_agent/desk/routes.py`；Test `tests/test_desk_compare.py`

**Interfaces：**
- 接口 `GET /api/sessions/<id>/compare?a=<版本>&b=<版本>`：返回 `{"params": [{"name","label","unit","a","b"}], "checks": [{"id","part","a": 状态或 null,"b": 状态或 null}], "files": {"a": {...}, "b": {...}}}`；只列有变化的参数和检查。版本不存在 404。
- `compare.js`：
  - 叠加（默认）：b 是实体，a 是半透明轮廓叠在同一位置（a 的材质：`--mute` 色、透明度 0.25、只画轮廓线和很淡的面）。
  - 并排：画面分左右两个视图，共用一个相机，转一个另一个跟着转。
  - 下方列出参数变化（界面文字里的格式，如"孔径：6 → 8 毫米"）和检查结果的变化。
  - 某一版没有 STL：那一边显示截图，并说明原因。
  - Esc 或"关掉对比"回到当前版本。

- [ ] **Step 1：** 写测试：`compare.test.js`：参数变化的文字格式；`test_compare_falls_back_to_png`（Review Focus 5）。`tests/test_desk_compare.py`：接口返回只含有变化的项；不存在的版本 404；多零件时检查带 `part`。
- [ ] **Step 2：** 运行，确认失败；实现。
- [ ] **Step 3：** 在应用内置浏览器里，单零件和多零件各对比一次 v1、v2，叠加和并排都看。
- [ ] **Step 4：** 运行全部测试，提交：`feat: 修改前后的对比`。

---

### Task 9：引导、设置、案例库换新外观

**Files：** Rewrite `js/pages/onboarding.js`、`js/pages/settings.js`、`js/pages/cases.js`（由原来的 `onboarding.js`、`settings.js`、`cases.js` 挪进 `pages/` 并改样式）；Test 原有这几页的测试只改导入路径

- 内容和行为沿用第二版（引导三步、设置各项、案例库两组），只换外观：整页是同一个舞台背景，内容放在居中的玻璃面板里；按钮、输入框用新的基础样式；文字按界面文字。
- 案例库里多零件的案例显示零件数和"会动"的标记。

- [ ] **Step 1：** 先跑一遍这几页现有的测试，确认挪文件后只需要改导入路径。
- [ ] **Step 2：** 实现；在应用内置浏览器里把引导三步、设置每一项、案例库两组都看一遍，浅色、深色各一遍。
- [ ] **Step 3：** 运行全部测试，提交：`feat: 引导、设置、案例库换成展台外观`。

---

### Task 10：真窗口走查

**Files：** Create `docs/walkthrough-v3.md`、`docs/walkthrough-v3/*.png`；Modify `docs/ui-checklist.md`

- [ ] **Step 1：** 在真的桌面窗口里（`.venv\Scripts\datum --demo-script …`，不是浏览器）走两遍，每一步截图：
  1. 单零件剧本：引导（跳过）→ 新会话 → 提问 → 需求单在中间填起来 → 确认、需求单飞走 → 一步一步长出来 → 做好了 → 检查面板 → 坐标轴转到底下看 → 剖开、标注、正交 → 调参数、预览、应用 → 对比 v1 和 v2（叠加、并排）→ 存为案例 → 切深色 → 关掉重开，会话还在。
  2. 多零件剧本：确认 → 零件清单逐个打勾 → 装配 → 做好了 → 播放运动、拖动、看小点 → 聚焦每个零件 → 炸开、透视、名字 → 修改"盖子最多翻到 95 度" → 对比 v1 和 v2。
- [ ] **Step 2：** 窗口缩到 1100×700，多零件的画面再看一遍（Review Focus 6）；放大到 1600×1000 再看一遍。
- [ ] **Step 3：** 发现的问题当场修，修完重走那一步；修不了的写进文档最后的"已知问题"。逐条对照界面清单，在文档里写每一条的结论。
- [ ] **Step 4：** 运行全部测试，提交：`docs: 3.0 展台界面走查记录`。

---

## 做完之后

`docs/progress.md` 写"3.0 计划 3 小结"：测试数、删掉和替换的旧测试（逐个列出）、走查发现并修掉的问题、已知问题。

---

## 界面文字

逐字照抄。`<…>` 是运行时填入的内容。

新的会话、还没说要做什么时，舞台中间：

```text
说说你想做什么。可以是一个零件，也可以是几个零件装在一起、能动的东西。
```

三个例子（点了就作为第一条消息发出去）：

```text
做一个放在桌上看视频的手机支架
做一个带铰链盖的工具盒，盖子能翻开
做一个法兰盘，外径 120，上面一圈 6 个螺栓孔
```

输入框的提示文字：

```text
说说要做什么，或者要怎么改
```

各时刻的副标题（标题是零件或产品的名字；还没有名字时标题是"新零件"）：

```text
还在问你几个问题
都记下了，你看一下
正在做，第 <k> 步，共 <n> 步
正在做 <零件名>，第 <k> 个零件，共 <n> 个
正在装起来
第 <k> 版，<尺寸> 毫米
第 <k> 版，<n> 个零件
没做完
```

需求单卡片上没问到的值：

```text
等你回答
```

需求单的两个按钮：

```text
没问题，开始做
我还要改
```

右边大数字下面：

```text
项全部量过，都对
项已经量过
```

左侧零件清单的说明和"看全部"：

```text
零件，点一个单独看
看全部
```

零件小卡片（每行一项）：

```text
外形 <尺寸>
材料 <材料名>
<n> 项检查，全部量过
```

运动条的状态：

```text
动到哪里都没有碰到别的零件（量了 <n> 个位置）
在 <值><单位> 附近碰到了：<零件名> 和 <零件名>
动画数据读不出来，先按装好时的样子显示。
```

左下工具：

```text
炸开
透视
剖开
名字
```

调参数面板的说明、按钮和结果：

```text
改好后点"应用"，会从头重做一遍、再量一遍。不花钱。
```

```text
正在预览
还原
应用
已存为第 <k> 版
改成这些数值后没有全部通过，已经退回原来的数值。
让模型帮我处理
```

调参数面板不能用时：

```text
做好第一个版本之后，就可以在这里直接改数值。
正在做，等这一轮结束再改。
```

对比：

```text
对比
叠在一起
左右并排
关掉对比
<参数名>：<旧值> → <新值> <单位>
这个版本没有三维文件，先用截图代替。
```

三维加载失败：

```text
三维模型没有加载出来，先用截图代替。
这台电脑现在显示不了三维画面，先用截图代替。
```

连接断开：

```text
连接断开，正在重试
```

坐标轴下面的五个按钮：

```text
前
上
右
立体
底
```

看图工具的两个开关：

```text
尺寸标注
正交视图
```
