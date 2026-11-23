# Datum 3.0 补充：向老师平台学的三处 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 学老师平台（test.aiad.physpace.tech）做得好的三处：多零件时也能一眼看到做到哪一步、智能体工作时可以插话、问答一次问完；顺带修掉 toolbox 出题不清（F7），最后花一次小钱验证。

**Architecture:** 进度清单是纯界面：在 `stage-logic.js` 里加一个可测的 `stepsView`，单零件照旧列阶段，多零件改列零件和"装起来"。插话走现有的发消息接口：忙的时候不再回 409，而是把话放进智能体的"补充"信箱，主循环每次调用模型前取出来，作为一条 user 消息追加进本轮上下文；一轮结束时还没取走的，接着开新的一轮。一次问完只改提示词和"都按建议"按钮。

**Tech Stack:** Python 3.12、pytest、原生 JS（node 测试）、DeepSeek（只在 Task 6 用，先问用户）。

**Spec:** 本计划开头"简短设计"一节（小改动，不另写设计文档）；背景是 `docs/results-v3.md` 的 F7 和 2026-11-23 对老师平台的实测。

## 简短设计

- **为什么：** 2026-11-23 在老师平台上实测同一个齿轮需求：它 31 分钟没做出来，我们并不比它慢；但它有三处用起来更顺：①输入框上方一直有一张"2/6"的勾选清单；②工作中输入框照样能用（"Enter 插话"）；③只问一轮，问题都带推荐值，回"按推荐值"就行。我们的 toolbox 第二轮正是死在问答轮数上（F7）。
- **做什么：**
  1. 进度清单：左边的步骤栏多零件时也显示（现在多零件时整个隐藏），列出每个零件和最后的"装起来"，顶上一行"已完成 k/n"。
  2. 插话：工作中输入框不禁用；有字时按 Enter 或点按钮是"补充"，没字时按钮仍是"停止"。补充的话在智能体下一次调用模型前送到，界面上作为用户的一句话出现在记录里。
  3. 一次问完：提示词要求把所有没定的东西放进同一次提问、每个给建议值，用户回答后只在矛盾或缺了做不下去的东西时才再问；问题里有建议值时界面给一个"都按建议"按钮。
  4. toolbox 的隐藏需求写清楚提手"跨距"的量法（照参考答案），只改出题说明，不改验收。
- **不做：** 不把原始报错、JSON、英文角色名摆给用户（老师平台这样做了，和我们设计文档第 7.9 节冲突）；不做云端、API、图片输入；不动视觉风格。
- **方案取舍：** 插话也考虑过"先停再发新一轮"，但会丢掉这一轮正在做的事、还要重新调用模型，比追加一条消息贵；"追加 user 消息"在我们的上下文里已有先例（阶段小结就是轮内的 user 消息），所以选它。

## Global Constraints

- 照 `CLAUDE.md`：严格先写测试并亲眼看到失败；每个任务单独提交，提交信息用计划给的，末尾加 `[skip ci]` 和 `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`。
- 文件超过 300 行就拆分；`cad_agent/agent/loop.py` 现在正好 300 行。
- 面向用户的文字用中文平常话，不出现程序内部的词。
- 读写文件显式 `encoding="utf-8"`。
- 改提示词时，同步改原文照抄文档里同一句，并运行 `scripts/export_prompts.py` 重新导出 `docs/prompts-and-tools.md`。
- 真实模型只在 Task 6 用，运行前单独问用户，用户本人说"可以"才跑；总实际花费不超过 ¥20（现在约 ¥14.75）。
- 每个任务收尾跑快速全量 `.venv\Scripts\python -m pytest -q -m "not sca"`；在 Bash 里跑（PowerShell 工具的终端输出编码会让两个安装脚本测试误报）。完整全量只在 Task 7 跑一次。

## 要改的旧测试

| 测试 | 怎么改 |
|---|---|
| `tests/test_desk_workbench.py::test_busy_rejects_params_message_and_delete` | 去掉"忙时 `submit` 抛 Busy"那一句，改成断言返回 `"note"`；`apply_params` 抛 Busy 不变（Task 2） |
| `tests/test_desk_server.py::test_busy_is_409` | 循环里去掉 `/message` 那一项，另加断言：忙时 POST `/message` 回 200、`{"ok": true, "note": true}`；`/params`、DELETE 仍是 409（Task 2） |

## Review Focus

1. 补充的话刚好在一轮结束的那一刻送到（模型已经回完纯文字）：不能丢，要接着开一轮处理它。→ Task 2 `test_note_left_at_turn_end_starts_next_turn`
2. 阶段结束时上下文会折叠成小结：补充的话不能随折叠消失。→ Task 2 `test_note_survives_fold`
3. 工作中输入框空着点按钮：仍然是停止，不能变成发一条空补充。→ Task 3 `sendMode` 测试
4. 示例会话（只能看）：工作中也不能补充。→ Task 2 `test_demo_session_cannot_add_note`
5. 问答阶段（不是建模）也能补充，补充的话和原话一起进需求整理。→ Task 2 `test_note_during_clarify_reaches_model`

---

### Task 1：多零件时也显示进度清单

**Files:**
- Modify: `cad_agent/desk/static/js/stage-logic.js`（加 `stepsView`、文字常量）
- Modify: `cad_agent/desk/static/js/stage.js`（`renderSteps` 改用 `stepsView`）
- Modify: `cad_agent/desk/static/css/stage.css`（`.steps` 一节：顶上"已完成 k/n"一行、不可点的项、"没过"的颜色用现有的 `status-` 颜色）
- Test: `cad_agent/desk/static/js/tests/stage.test.js`

**Interfaces:**
- Produces: `stepsView(state) -> { total: number, done: number, items: Array<{ id: string, title: string, status: "done" | "run" | "todo" | "failed", note: string, clickable: boolean }> } | null`

- [ ] **Step 1：写失败的测试**（加在 `stage.test.js`）
  - `stepsView single part lists stages`：`plan.stages` 两个、第一个 `passed`、`current` 是第二个、`busy: true` → `items` 的 `status` 依次 `done`、`run`，`note` 依次 `✓ 1/1`（该阶段检查 1 个通过）、`进行中`；`clickable` 都是 `true`；`done` 1、`total` 2。
  - `stepsView multi part lists parts then assembly`：`product.parts` 三个，状态 `done`、`current`、`todo`，`product.assembly` 是 `todo`，`busy: true` → 4 项，标题依次是三个零件名和 `装起来`，`status` 依次 `done`、`run`、`todo`、`todo`；`clickable` 都是 `false`；`done` 1、`total` 4。
  - `stepsView assembly failed shows failed`：零件都 `done`、`assembly` 是 `failed` → 最后一项 `status: "failed"`、`note: "没过，在改"`。
  - `stepsView hides when nothing to show`：没有 `plan` 也没有 `product` → `null`。
  - `stepsView multi part hides after delivery`：多零件、`phase: "delivered"`、`busy: false` → `null`（交付后左边是现有的"零件，点一个单独看"面板，两个不能叠在同一个位置）。
- [ ] **Step 2：运行，看到失败**：`node --test cad_agent/desk/static/js/tests/stage.test.js`，预期 `stepsView` 未导出。
- [ ] **Step 3：实现。**
  - `TEXT` 里加 `assemble: "装起来"`、`stepFailed: "没过，在改"`、`stepsDone: "已完成"`。
  - 单零件：沿用 `renderSteps` 现在的判断（`passed` → `done`，`busy` 且是 `current` → `run`），`note` 文字也照旧。
  - 多零件：零件 `status` 映射 `done→done`、`current→`（`busy` 时 `run`，否则 `todo`）、`todo→todo`；最后加一项 `{id: "assembly", title: "装起来"}`，`assembly` 为 `passed` 时 `done`，`failed` 时 `failed`，零件都 `done` 且 `busy` 时 `run`，其余 `todo`。零件的 `note` 用 `✓ 通过数/总数`（`done` 时，取 `p.checks`）、`进行中`、`没开始`。
  - 多零件只在"正忙或还没交付过"时返回清单，否则 `null`。
  - `renderSteps`：`stepsView` 为 `null` 时隐藏；多零件清单显示时给 `#parts` 加 `gone`（同一个位置），清单隐藏时去掉；顶上加一行 `已完成 {done}/{total}`；`clickable` 的项是按钮（行为照旧），不可点的项用 `div`，样式和按钮一致。去掉"有 `state.product` 就隐藏"的那一句。
- [ ] **Step 4：运行测试通过**，再跑快速全量。
- [ ] **Step 5：提交** `feat: 多零件时也显示进度清单 [skip ci]`

### Task 2：工作中可以补充（后端）

**Files:**
- Create: `cad_agent/agent/notes.py`（`NoteBox`）
- Modify: `cad_agent/agent/context.py`（`add_note`、折叠和结束时保留补充）
- Modify: `cad_agent/agent/loop.py`（每次调用模型前取补充；为了不超过 300 行，把 `_assistant_message` 移到 `context.py`，改名 `assistant_message`）
- Modify: `cad_agent/desk/workbench.py`（忙时 `submit` 投进信箱；一轮结束有剩的就再开一轮）
- Modify: `cad_agent/desk/routes.py`（`/message` 回 `{"ok": true, "note": true}`）
- Modify: `cad_agent/desk/transcript.py`（日志里的 `note` 显示成用户说的话）
- Test: `tests/test_context.py`、`tests/test_loop.py`、`tests/test_desk_workbench.py`、`tests/test_desk_server.py`

**Interfaces:**
- Produces:
  - `class NoteBox`: `put(text: str) -> None`（线程安全）、`drain() -> list[str]`（取出并清空，按先后顺序）
  - `Agent.notes: NoteBox`；`Agent.add_note(text: str) -> None`
  - `Context.add_note(text: str) -> None`；常量 `NOTE_HEADER = "【你工作时用户补充的话，先看这条再继续】"`
  - `Workbench.submit(text: str) -> str`：返回 `"turn"`（开了新的一轮）或 `"note"`（正忙，作为补充送进去）
  - 会话日志新增一种：`session.log("note", text=...)`；总线事件 `note`（`text`）
- 偏离：`Workbench.submit` 原来没有返回值、忙时抛 `Busy`。在 `docs/deviations.md` 记一条 D46。

- [ ] **Step 1：写失败的测试**
  - `test_context.py::test_note_is_user_message_in_turn`：`start_turn` 后 `add_note("改成 95 度")` → `messages()` 最后一条是 `role: user`，内容以 `NOTE_HEADER` 开头、含原话。
  - `test_context.py::test_note_survives_fold`：`add_note` 后 `fold("小结")` → `messages()` 里仍有这条补充，且在小结之后。
  - `test_context.py::test_note_kept_when_turn_ends`：`end_turn` 后，折叠进历史的那条 user 内容同时含原话和补充。
  - `test_loop.py::test_note_reaches_model_before_next_call`：假模型第一次回一个工具调用，在工具执行时 `agent.add_note("加高到 70")`；断言第二次调用模型时收到的消息里有这句补充，且日志有一条 `note`。
  - `test_loop.py::test_note_during_clarify_reaches_model`：问答阶段（需求单没确认）同样的流程，补充送到模型。
  - `test_desk_workbench.py::test_submit_while_busy_becomes_note`：`GateLLM` 卡住第一轮，`submit("第二条")` 返回 `"note"`；放行后整轮结束，`state()["transcript"]` 里有"第二条"，并且是用户的话。
  - `test_desk_workbench.py::test_note_left_at_turn_end_starts_next_turn`：补充在模型最后一次回复（纯文字）之后才送到 → 这一轮结束后自动再开一轮，`turn_end` 共 2 个，第二轮模型收到"第二条"。
  - `test_desk_workbench.py::test_demo_session_cannot_add_note`：示例会话忙时 `submit` 抛 `PermissionError`。
  - 照"要改的旧测试"表改两个旧测试。
- [ ] **Step 2：运行，看到失败。**
- [ ] **Step 3：实现。**
  - `NoteBox` 用 `threading.Lock` 和列表。
  - `Context`：`_notes` 在 `start_turn` 清空；`add_note` 同时追加进 `_current` 和 `_notes`；`fold` 在小结后面把 `_notes` 对应的消息再接上；`end_turn` 折叠时 user 内容 = 原话 + 每条补充前加"（中途补充）"。
  - `loop.handle_user`：`while True` 里调用 `_chat` 之前，把 `self.notes.drain()` 的每一条 `context.add_note` 并 `session.log("note", text=t)`。
  - `Workbench.submit`：示例会话照旧抛 `PermissionError`；正忙时 `agent.add_note(text)`、`bus.publish("note", text=text)`、返回 `"note"`；否则照旧开一轮、返回 `"turn"`。`_work` 在 `handle_user` 返回后，`agent.notes.drain()` 有剩的就用 `"\n".join(剩下的)` 再调一次 `handle_user`（同一个线程，期间仍算正忙），直到没有剩的。
  - `transcript.py`：`note` 和 `user` 一样显示成用户的话。
  - 记 D46。
- [ ] **Step 4：运行测试通过**，再跑快速全量。
- [ ] **Step 5：提交** `feat: 智能体工作时可以补充要求 [skip ci]`

### Task 3：工作中可以补充（界面）

**Files:**
- Modify: `cad_agent/desk/static/js/stage-logic.js`（`sendMode`、文字）
- Modify: `cad_agent/desk/static/js/stage.js`（输入框不再因为忙而禁用，按钮按 `sendMode` 走）
- Modify: `cad_agent/desk/static/js/main.js`（`sendMessage` 收到 `note: true` 时在字幕上显示"记下了"）
- Test: `cad_agent/desk/static/js/tests/stage.test.js`

**Interfaces:**
- Consumes: Task 2 的 `/message` 返回 `{"ok": true, "note": true}`
- Produces: `sendMode(state, hasText: boolean) -> "send" | "note" | "stop" | "none"`

- [ ] **Step 1：写失败的测试**
  - `sendMode` 四种情况：不忙有字 → `send`；忙且有字 → `note`；忙且没字 → `stop`；示例会话 → `none`（忙不忙、有没有字都是）。
  - `TEXT.notePlaceholder` 是 `"正在做。想补充或改什么，直接说，它做完手上这一步就会看"`；`TEXT.noted` 是 `"记下了，它做完手上这一步就会看"`。
- [ ] **Step 2：运行，看到失败。**
- [ ] **Step 3：实现。**
  - 输入框只在示例会话或没有会话时禁用；忙时占位文字换成 `TEXT.notePlaceholder`。
  - 按钮：输入框有字时显示 `↑`、`aria-label` 是"补充"（忙时）或"发送"；忙且没字时显示 `■`、"停止这一轮"。点按钮和按 Enter 都按 `sendMode` 走，`stop` 只由点按钮触发（空输入框按 Enter 什么都不做）。
  - 发出补充后清空输入框，字幕显示 `TEXT.noted`，直到下一次状态更新。
- [ ] **Step 4：运行测试通过**，再跑快速全量；用 `.venv\Scripts\datum` 打开桌面端，用示例会话看一眼输入框和按钮（只看，不发真实消息）。
- [ ] **Step 5：提交** `feat: 界面上工作中也能输入补充 [skip ci]`

### Task 4：问答一次问完、"都按建议"按钮

**Files:**
- Modify: 问答规则所在的提示词（`cad_agent/agent/prompts/system_v2.md` 第 1 步"澄清"那一段）和它的原文照抄文档（`docs/superpowers/plans/2026-11-10-caliper-1-kernel-prompts.md`）
- Modify: `cad_agent/desk/static/js/stage-logic.js`（`choicesFor`）
- Test: `tests/test_staged_tools.py`（`test_system_v2_is_verbatim_copy` 会自动跟着原文照抄文档走，不用改；新测试加在同一文件）、`stage.test.js`

- [ ] **Step 1：写失败的测试**
  - 提示词测试 `test_ask_once_with_suggestions`：`system_v2.md` 含下面这段（逐字）：

```text
   - 要问的一次问完：把还没定的尺寸和做法都放进同一次提问，每个都给建议值，用户回"都按建议"就全部按建议值记下。用户回答以后，只有答案互相矛盾、或者缺了做不下去的东西时才再问；量法、对齐这类小事按常见做法定下，写进需求单，确认时用户能看到，不要为它单独再问一轮。
```

  - `stage.test.js`：`choicesFor` 遇到两个以上问题、其中至少一个含"建议"时返回 `["都按建议"]`；一个问题的老规则不变（老测试照样通过）。
- [ ] **Step 2：运行，看到失败。**
- [ ] **Step 3：实现**：把上面这段放在 `system_v2.md` 第 19 行（"要提问时，在同一次回复里先调用 update_brief……"）后面；原文照抄文档同一位置同步；运行 `scripts/export_prompts.py`；改 `choicesFor`。
- [ ] **Step 4：运行测试通过**（含 `test_prompts_doc_up_to_date`），再跑快速全量。
- [ ] **Step 5：提交** `feat: 问答一次问完，给"都按建议"按钮 [skip ci]`

### Task 5：toolbox 出题写清提手的量法（F7）

**Files:**
- Modify: `benchmarks/tasks/toolbox.yaml`（只改 `hidden_spec` 里提手那一行）
- Test: `tests/test_task_hidden_specs.py`

- [ ] **Step 1：写失败的测试** `test_toolbox_handle_span_is_defined`：toolbox 的 `hidden_spec` 含 `跨距 70 mm 是提手两端外缘之间的总长`、`立柱 8×8 mm 的方柱，外侧和底板两端齐平`。
- [ ] **Step 2：运行，看到失败。**
- [ ] **Step 3：实现**：提手那一行改成（照参考答案 `tests/references_v3.py::_handle`：底板长等于跨距，立柱 8×8、中心在 ±(跨距/2−4)，握把长等于跨距）：

```text
  - 盖子顶面正中一个提手：跨距 70 mm 是提手两端外缘之间的总长。底板 70×14×3 mm 贴在盖子上；两端各一根立柱，立柱 8×8 mm 的方柱，外侧和底板两端齐平；上面横一根沿长度方向的圆柱握把，长 70 mm、直径 8 mm，握把中心离盖子顶面 13 mm，提手总高 17 mm；握把下面是空的，手能伸进去。
```

  验收不改。
- [ ] **Step 4：运行测试通过**，再跑快速全量。
- [ ] **Step 5：提交** `fix: toolbox 写清提手跨距的量法（F7）[skip ci]`

### Task 6：花一次小钱验证（先问用户）

- [ ] **Step 1：停下来问用户**，说清楚：跑 `toolbox`（看问答能不能在 14 轮内走到建模、装配）和 `phone_stand`（看一次问完对单零件有没有副作用）；命令 `benchmarks.run --config config.toml --tasks toolbox phone_stand --label round3 --cap 27.5 --task-cap 2.5`；最多花 ¥5，预计 ¥1.5–3；只在空闲时段跑（不加 `--allow-peak`）。用户本人说"可以"才跑。
- [ ] **Step 2：** 前台跑不完的话放后台，等通知，期间不改源文件。
- [ ] **Step 3：** `docs/results-v3.md` 加 `## 第三轮` 一节（照第二轮的格式：表、和前几轮的对比、花费），"没做到的地方"按结果更新；提交 `docs: 3.0 第三轮评测结果 [skip ci]`。

### Task 7：收尾

- [ ] 跑一次完整全量（在 Bash 里，超过 10 分钟就放后台等通知）。
- [ ] `docs/progress.md` 追加本计划的小结（每个任务、测试数量、问题和处理）。
- [ ] 提交 `docs: 向老师平台学的三处做完 [skip ci]`；问用户要不要推送（单独问）。
