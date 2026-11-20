# 3.0 · 计划 4：用真实模型把建模质量做实 · 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal：** 用 `deepseek-flash` 把 14 个评测任务真实地跑两轮：第一轮找出失败，按用户批准的修改清单对症修改，第二轮复测；全部花费按实际扣费不超过 ¥20；如实写出结果。

**Architecture：** 先把评测脚本改成"按实际价格累计、到上限立刻停、所有真实调用记进同一个账本、默认只在空闲时段跑"，再加"说人话"的提示词。然后是四个**必须停下来等用户本人回答**的节点：第一轮开跑前、修改清单批准前、第二轮开跑前、可选对照开跑前。

**Tech Stack：** 不新增依赖。

**Spec：** `docs/superpowers/specs/2026-11-20-datum-v3-design.md`（第 8 节、第 9 节的测试分析几行）。

**前置：** 计划 1、2 完成（第一轮评测要用多零件内核）。计划 3 不是前置，可以同时进行，但两份计划不能改同一个文件（本计划不碰 `cad_agent/desk/`、`cad_agent/checks/`、`cad_agent/staged/`、`cad_agent/product/`，修改清单批准的条目除外）。

## Global Constraints

- 前几版计划的规矩全部继续有效（见 `CLAUDE.md`）。
- **真实模型只在本计划写明的几处调用，每一处都要先停下来问用户，用户本人回答"可以"才跑。** 不能拿别处、别次的同意代替。
- key：只用环境变量或 Datum 设置里存进钥匙串的 key（`keystore.get_key`）；不打印、不写进任何文件、日志、结果文档；提交前对结果文档做一次搜索，确认没有 key 的任何片段。
- 价格：代码里不写任何价格；用户照 DeepSeek 官网自己填。
- **花费上限 ¥20，按实际扣费算**，包括：两轮评测、可选对照、计划 5 的录演示视频；智能体和模拟用户的调用都算。
- 只用 `deepseek-flash`。如果第一轮显示它在困难任务或多零件上基本做不出来，停下来和用户商量，不自己换模型。
- 修改只做用户批准过的修改清单里的条目；不放宽检查、不删检查、不针对评测任务写死内容；留出任务的对话记录不读。
- 偏离记录接着编号。每个任务收尾：全部测试通过 → 提交 → `docs/progress.md` 追加一段（标题写"3.0 计划 4 Task N"）。

## 要改的旧测试

| 测试 | 怎么改 |
|---|---|
| 计划 2 的 `test_system_prompt_order` | 分阶段的系统提示词在 `system_multipart.md` 之后多一段 `system_voice.md`（Task 3） |
| `tests/test_benchmarks_budget.py` 里断言"任务开始前才检查上限"的测试 | 改成"每次调用后检查"：上限到了，正在跑的任务也立刻停（Task 1） |

## Review Focus

1. 跑到一半到了上限：当前任务立刻停，已经跑完的任务和这个任务已有的结果照常写出，账本记下停在哪里；下次运行时账本里的余额是对的。→ Task 1 `test_hard_cap_stops_mid_task_and_keeps_results`
2. 跑的时候跨过了空闲时段的结束时间：从那一刻起按高峰价累计，正在跑的任务跑完，下一个任务不再开始。→ Task 1 `test_offpeak_window_ends_mid_run`
3. 用户没填空闲价格或空闲时段：脚本拒绝开跑，说明要填什么、照哪里填。→ Task 1 `test_missing_offpeak_pricing_refuses`
4. 账本文件被删掉或损坏：拒绝开跑并说明，不当作"一分钱没花"重新开始。→ Task 1 `test_corrupt_ledger_refuses`
5. 某个任务里模拟用户自己调用出错：这个任务记为失败、原因写清，其余任务照常跑，花费照常记。→ Task 1 `test_sim_user_error_is_recorded`

---

### Task 1：账本、按时段计价、真正的硬上限

**Files：** Create `benchmarks/ledger.py`、`tests/test_ledger.py`；Modify `cad_agent/config.py`、`config.example.toml`、`benchmarks/run.py`、`benchmarks/sim_user.py`、`.gitignore`；Test `tests/test_benchmarks_budget.py`（按清单改）

**Interfaces：**
- 配置：`[llm.pricing]` 仍是高峰价；新增 `[llm.offpeak]`：`start`、`end`（本机时间 `"HH:MM"`，可以跨午夜）、`input_hit`、`input_miss`、`output`。`Config.price_at(now: datetime) -> Pricing`：在空闲时段内返回空闲价，否则返回高峰价。两段都没填时 `price_at` 抛 `ConfigError`。
- `benchmarks/ledger.py`：
  ```python
  LEDGER = Path("benchmarks/results/ledger-v3.json")
  class LedgerError(Exception): ...
  class BudgetExceeded(Exception): ...
  @dataclass
  class Ledger:
      cap: float; spent: float; entries: list[dict]     # entry：{"ts","label","task","who","cost","priced_as"}
      @classmethod
      def load(cls, path: Path, cap: float) -> "Ledger": ...    # 文件不存在就新建；存在但读不出来抛 LedgerError
      def add(self, label: str, task: str, who: Literal["agent","sim_user"], cost: float, priced_as: Literal["peak","offpeak"]) -> None: ...
                                                                # 写盘；累计后 >= cap 时抛 BudgetExceeded
      def remaining(self) -> float: ...
  def metered(llm: LLM, ledger: Ledger, config: Config, label: str, task: str, who: str) -> LLM: ...
      # 包一层：每次调用后按 config.price_at(调用结束的时刻) 重新算这次的费用并记账
  ```
- `benchmarks/run.py`：
  - `--budget` 换成 `--cap 20`（默认 20）和必填的 `--label`（如 `round1`、`round2`、`ab`）；账本固定是 `LEDGER`，所有标签共用一个上限。
  - 开跑前：账本读不出来 → 拒绝；`config.price_at` 抛错 → 拒绝并说明要在配置里填哪两段；当前不在空闲时段且没有 `--allow-peak` → 拒绝并打印空闲时段。
  - 每个任务开始前：不在空闲时段（且没有 `--allow-peak`）就不再开始新任务。
  - `BudgetExceeded`：当前任务立刻停（记 `{"stopped_for_cap": true}` 和已有的阶段结果），后面的任务记 `skipped_for_cap`，结果文件照常写出，最后打印 `已花费 ¥<x>，上限 ¥<y>，剩 ¥<z>`。
  - key 的取法：环境变量，没有就 `keystore.get_key("deepseek", "DEEPSEEK_API_KEY")`；都没有就提示用户在 Datum 设置里填或设环境变量，并退出。
- `.gitignore` 里 `benchmarks/results/` 已经忽略，账本不进 git；`docs/results-v3.md` 里抄写账本的汇总。

- [ ] **Step 1：** 按清单改 `test_benchmarks_budget.py`；写 `tests/test_ledger.py`（假 LLM、可替换的"现在几点"）：`test_price_at_window_and_midnight_wrap`；`test_hard_cap_stops_mid_task_and_keeps_results`（Review Focus 1）；`test_offpeak_window_ends_mid_run`（Review Focus 2）；`test_missing_offpeak_pricing_refuses`（Review Focus 3）；`test_corrupt_ledger_refuses`（Review Focus 4）；`test_sim_user_cost_is_metered`；`test_sim_user_error_is_recorded`（Review Focus 5）；`test_labels_share_one_cap`；`test_key_from_keystore_when_no_env`（内存假后端）；`test_results_have_no_key`。
- [ ] **Step 2：** 运行，确认失败；实现；运行全部测试，提交：`feat: 评测的账本、按时段计价和硬上限`。

---

### Task 2：任务分组和作业要求的统计

**Files：** Modify `benchmarks/run.py`、`benchmarks/report.py`；Test `tests/test_benchmarks_v3.py`

**Interfaces：**
- `V3_DEV = ["phone_stand", "flange", "l_bracket", "enclosure", "bearing_block", "spur_gear", "heatsink", "tee_fitting", "toolbox", "drawer_cabinet"]`；`V3_HOLDOUT = ["stepped_shaft", "battery_box", "bracket_arm", "gear_pair"]`；`TASK_SETS` 加 `"v3dev"`、`"v3holdout"`、`"v3all"`（前两个依次相接）。原有集合不变。
- 结果表（`results.md`）分四张：开发 / 留出 × 单零件 / 多零件。每张的列：任务、是否成功、最大尺寸偏差、耗时、修复次数、模型调用、花费。
- 另加一张"覆盖情况"：每个任务这一遍里有没有经过需求澄清（模型至少提过一次问题）、多轮修改（有修改阶段且交付了）、错误反馈修正（修复次数 ≥ 1），以及三项都覆盖到的任务数。作业要求的"至少 3 组、覆盖澄清、多轮修改、错误反馈修正"直接从这张表看。
- 多零件任务的"最大尺寸偏差"只统计装好后的外形和点检查里的长度类条目。

- [ ] **Step 1：** 写测试：`test_v3_sets`；`test_four_tables`；`test_coverage_table`（手造三种结果：只澄清、只修复、三项都有）；`test_multipart_deviation_only_lengths`。
- [ ] **Step 2：** 运行，确认失败；实现；运行全部测试，提交：`feat: 3.0 评测的任务分组和覆盖统计`。

---

### Task 3：说人话的提示词

**Files：** Create `cad_agent/agent/prompts/system_voice.md`；Modify `cad_agent/agent/state.py`；Test `tests/test_prompts_voice.py`、计划 2 的 `test_system_prompt_order`（按清单改）

**Interfaces：**
- `load_system_prompt(True)` 在 `system_multipart.md` 之后、`references_index.md` 之前接 `system_voice.md`。
- `system_voice.md` 的内容照抄下面的 text 块。

```text
## 和用户说话的口气
- 用平常话，短句，像一个靠谱的同事在当面说。
- 不要说程序内部的词：不说"阶段 s2"，说"第 2 步"；不说检查的 id、工具的名字、build、gate、interference、revolute 这类词；不说"终检""参数扰动"，说"最后再检查一遍""每个尺寸都确认过真的起作用"。
- 说结果先说结论，再说一个最关键的数，比如"做好了，盖子能翻到 110 度，全程没碰到盒子"。
- 提问时说明为什么要问，能给建议值就给，方便用户直接回"可以"。
- 出了问题直接说哪里不对、打算怎么改，不道歉，不说空话。
```

- [ ] **Step 1：** 按清单改 `test_system_prompt_order`；写新测试：`test_system_voice_verbatim`；`test_voice_comes_after_multipart`。
- [ ] **Step 2：** 运行，确认失败；实现；运行全部测试，提交：`feat: 提示词加上说人话的要求`。

---

### Task 4：第一轮评测（花钱，先问用户）

- [ ] **Step 1：** 确认：全部测试通过；`config.toml` 里两段价格和空闲时段都已填（没填就停下，请用户照 DeepSeek 官网自己填，不要自己编）；账本里已花多少。
- [ ] **Step 2：** **停下来问用户**，原话包括：要跑的命令、14 个任务、预计 ¥7–13、上限 ¥20、账本里已花多少、现在是不是空闲时段。用户本人回答"可以"才继续。
- [ ] **Step 3：** 运行：

```powershell
.venv\Scripts\python -m benchmarks.run --config config.toml --set v3all --label round1 --cap 20
```

- [ ] **Step 4：** 把结果目录、四张表、覆盖表、账本汇总写进 `docs/results-v3.md` 的"第一轮"一节。提交：`docs: 3.0 第一轮评测结果`。

如果第一轮显示困难任务和多零件任务基本都没做成，在这一步停下来，把数字和对话记录里看到的主要原因告诉用户，问要不要换更强的模型；不自己换。

---

### Task 5：失败分析和修改清单（停下来等批准）

- [ ] **Step 1：** 只读开发任务（`V3_DEV`）的对话记录。留出任务只看结果表。
- [ ] **Step 2：** 把每个失败归类：没问清需求、计划拆得不对、建模写法不会、检查写错、关卡误伤、装配写错、运动碰撞、流程卡住、上限太小、其他。每个失败写：任务、哪一轮哪一步、看到了什么（引用日志里的关键一句）、归到哪一类。
- [ ] **Step 3：** 写修改清单，每条：编号、对应哪几个失败、准备改什么文件的什么地方、改法、怎么用不花钱的测试证明它有效、会不会影响别的任务。不能出现"放宽检查""删检查""针对某个任务写死"。
- [ ] **Step 4：** 写进 `docs/results-v3.md` 的"失败分析"和"修改清单"两节，提交：`docs: 3.0 第一轮的失败分析和修改清单`。
- [ ] **Step 5：** **停下来**：告诉用户修改清单已经写好，请规划会话核对、用户本人批准（可以删改条目）。批准的结果写进 `docs/results-v3.md`，原样记下用户的话。

---

### Task 6：对症修改

- [ ] 对修改清单里**每一条批准过的条目**，各做一个小循环：先写不花钱的测试（能复现这个失败的剧本、或者针对改动的单元测试）→ 确认失败 → 改 → 全部测试通过 → 提交（提交信息：`fix: 3.0 修改清单第 <编号> 条：<一句话>`）→ `docs/results-v3.md` 里这一条后面写"已改，提交 <哈希>"。
- 改提示词时照旧更新逐字测试。没批准的条目一条都不做。

---

### Task 7：第二轮评测（花钱，先问用户）

- [ ] **Step 1：** 定任务表：第一轮失败的开发任务 + 2–3 个第一轮就成功的开发任务（挑和修改清单关系最近的）+ 全部 4 个留出任务。如果账本余额不够全跑（按第一轮的单价估），按"留出任务优先、失败任务按修改清单覆盖的多少排"截掉，截掉的写明。
- [ ] **Step 2：** **停下来问用户**：任务表、预计花费、账本余额、是不是空闲时段。用户本人回答"可以"才继续。
- [ ] **Step 3：** 运行（`--tasks` 后面是任务表）：

```powershell
.venv\Scripts\python -m benchmarks.run --config config.toml --tasks <任务表> --label round2 --cap 20
```

- [ ] **Step 4：** 用 `benchmarks.compare` 出前后对比，写进 `docs/results-v3.md` 的"第二轮"一节。提交：`docs: 3.0 第二轮评测结果`。

---

### Task 8：可选的经验复用对照（花钱，先问用户）

- [ ] **Step 1：** 账本余额少于 ¥3 就跳过本任务，在结果文档里写"余额不够，没做"。
- [ ] **Step 2：** 否则**问用户**要不要做：在"关掉案例库"的条件下，把 3 个开发任务（第二轮都成功的、和案例库里的案例最像的三个）各跑一遍，和第二轮的同样任务对比。说明预计花费。用户不要就跳过。
- [ ] **Step 3：** 用户同意后运行（`--cases off`、`--label ab`），对比写进 `docs/results-v3.md` 的"经验复用对照"一节。提交：`docs: 3.0 经验复用对照`。

---

### Task 9：结果文档和 README

**Files：** Modify `docs/results-v3.md`、`README.md`（只改"验证到什么程度"一节）

- `docs/results-v3.md` 的结构（标题照抄）：`## 运行信息`（模型、价格口径、软件版本、各轮结果目录、提交哈希）、`## 第一轮`、`## 失败分析`、`## 修改清单`、`## 第二轮`、`## 经验复用对照`、`## 留出任务`、`## 花费`（账本汇总：每个标签花了多少、合计、上限）、`## 对照作业要求`（成功情况、尺寸偏差、耗时、修复次数四项各在哪张表；覆盖情况表的结论）、`## 没做到的地方`。
- README"验证到什么程度"换成真实数字：开发、留出各多少个成功，花了多少，指向 `docs/results-v3.md`。
- [ ] 写完后对两个文件各搜一遍 key（用 `Select-String -SimpleMatch`，结果必须是 False），运行全部测试，提交：`docs: 3.0 评测结果汇总`。

## 做完之后

`docs/progress.md` 写"3.0 计划 4 小结"：各轮花费、目标达到了哪些、没达到的原因。
