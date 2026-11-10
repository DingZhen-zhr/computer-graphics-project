# 卡尺第二版 · 计划 1：内核 · 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal：** 给内核加上分阶段流程：先出计划，每个阶段先写检查再建模，程序实测通过才进下一阶段，最后做终检（参数扰动验证）才交付；并加上试验代码、查阅文档、案例库、参数直改。

**Architecture：** 新流程全部写在新模块里（`cad_agent/staged/` 等），由开关 `Gates.staged` 决定走哪条路。1.2 版的流程、提示词、工具说明原样保留：`ToolBox` 不传 `gates` 时就是旧流程，所以现有测试不用改。分阶段的 build 是"每个阶段各跑一次截断的 notebook"；终检的扰动验证是"改一个参数重建、检查的期望值冻结"。全部用沙盒，不调用大模型。

**Tech Stack：** 和 1.2 版相同：Python 3.13、simplecadapi 2.2.7、openai SDK、PyYAML、pytest。本计划不新增依赖。

**Spec：** `docs/superpowers/specs/2026-11-10-caliper-v2-design.md`（第 3、7 节）。

**原文照抄的内容：** `docs/superpowers/plans/2026-11-10-caliper-1-kernel-prompts.md`（下面简称"提示词文档"）。

**执行规则：** 见项目根目录 `CLAUDE.md`。每开始一个任务前，先重读该任务和 Global Constraints。

## Global Constraints

- 第一版、1.1 版、1.2 版计划的 Global Constraints 全部继续有效：`.venv\Scripts\python`、UTF-8、key 只从环境变量读、不打印不记录 key、坐标约定、单位、每个文件不超过 300 行。
- **本计划不调用任何大模型，不花钱。** 所有测试用 `ScriptedLLM` 和沙盒。
- **旧测试一律不动。** 本计划没有"要改的旧测试"清单：旧流程（`gates` 为 `None` 或 `Gates.legacy()`）的行为必须和 1.2 版逐字相同。如果哪条旧测试因为本计划的改动变红，说明改动泄漏到了旧流程，改实现，不改测试；确实绕不开时停下来问用户。
- 提示词文档里 ```text、```json 框起来的内容逐字照抄。
- SCA 的写法只用 `docs/sca-api-notes.md` 里实测过的；没有的先在 `scripts/probe_v2.py` 里跑通、补进笔记，再用。
- 新流程的常量：每阶段 build 失败上限沿用 `max_build_failures`（3）；每阶段工具调用上限 25；每轮工具调用总上限 200；每阶段 probe 上限 10；阶段数 1 到 12；扰动验证最多 12 个参数、最多 4 个进程并行；probe 输出最多 2000 字符；`read_reference` 不带小节时最多 3000 字符、带小节时最多 6000 字符；案例每个最多 3000 字符、最多给 2 个。
- 需要真实 SCA 的测试标记 `sca`。
- 偏离记录接着编号，从 D10 开始，写进 `docs/deviations.md`。
- 每个任务收尾：全部测试通过 → 提交（提交信息用任务里给的）→ 在 `docs/progress.md` 追加一段（标题写"第二版 计划 1 Task N"）。

## Review Focus

1. 模型给还没轮到的阶段、或不存在的阶段写检查：返回提示词文档 7.3 的报错，现有检查和计划都不变。→ Task 6 `test_set_checks_rejects_unknown_and_future_stage`
2. 用户参数是 0，或者是个数为 1 的整数：扰动后的值不能是 0 个、负的长度，也不能和原值相同。→ Task 8 `test_perturbations_for_zero_and_small_counts`
3. 某个参数往两个方向改都建不出来（参数之间有约束）：记为"无法扰动"，不挡交付，交付文字里写明。→ Task 8 `test_unbuildable_does_not_block`、Task 10 `test_delivery_text_lists_unbuildable`
4. 阶段 2 通过之后，模型回头改了阶段 1 的特征：阶段 1、2 都变回未通过，build 从阶段 1 重新验证；阶段 1 的 `here_only` 检查只对截到阶段 1 的模型测，不对最终模型测。→ Task 7 `test_editing_earlier_stage_reverifies_from_there`
5. 一轮因为阶段工具调用上限停下，用户说"继续"：新一轮的快照里有计划和当前阶段，计数从 0 开始，模型接得上。→ Task 10 `test_continue_after_stage_cap`
6. probe 的代码死循环或打印几十万字符：超时后正常返回错误、输出被截断到 2000 字符，不拖垮本轮。→ Task 5 `test_probe_timeout`、`test_probe_output_truncated`

---

## 文件结构（新增和改动）

```
scripts/probe_v2.py                       第二版的 SCA 探测（Task 1）
docs/sca-api-notes.md                     新增第 17–22 节（Task 1）
cad_agent/agent/prompts/sca_cheatsheet_more.md   速查表补充（Task 1）
cad_agent/gates.py                        四个开关（Task 2）
cad_agent/config.py                       读开关和新上限（Task 2）
cad_agent/brief.py                        relations（Task 3）
cad_agent/plan.py                         计划与阶段，纯数据（Task 4）
cad_agent/notebook.py                     Feature.stage、probe 单元（Task 4、5）
cad_agent/checks/spec.py                  Check.stage / holds（Task 4）
cad_agent/staged/__init__.py
cad_agent/staged/select.py                某个阶段该用哪些特征和检查（Task 4）
cad_agent/sandbox/execute.py  runner.py   check_values、probe 模式（Task 5）
cad_agent/staged/specs.py                 12 个工具说明（Task 6）
cad_agent/staged/messages.py              关卡报错和 hint 的原文（Task 6）
cad_agent/staged/tools.py                 set_plan、分阶段的 upsert / remove / set_checks（Task 6）
cad_agent/agent/prompts/system_v2.md      系统提示词（Task 6）
cad_agent/staged/build.py                 分阶段推进和 build 工具（Task 7）
cad_agent/staged/mutation.py              参数扰动（Task 8）
cad_agent/staged/final_gate.py            终检（Task 8）
cad_agent/references.py                   读官方文档（Task 9）
cad_agent/staged/extras.py                probe、read_reference 两个工具（Task 9）
cad_agent/agent/prompts/references_index.md   文档目录（Task 9）
cad_agent/staged/summary.py               阶段小结文字（Task 10）
cad_agent/agent/state.py  context.py  loop.py  delivery.py   接入新流程（Task 10）
cad_agent/session.py                      plan.json、gate.json、part_dir（Task 10）
cad_agent/cases.py                        案例库（Task 11）
cad_agent/agent/manual.py                 参数直改（Task 12）
benchmarks/tasks/*.yaml（6 个新任务）  benchmarks/run.py（Task 13）
cad_agent/case_data/<8 个案例>/case.yaml  （Task 14）
cad_agent/cli.py  cad_agent/web/__main__.py  cad_agent/web/events.py  README.md（Task 15）
tests/helpers_staged.py                   分阶段测试共用的假 run_job（Task 7）
```

`cad_agent/tools.py` 现在 278 行。本计划往里加的只有"按开关选处理函数"的几行；超过 300 行时，把旧流程的 `_upsert_feature`、`_remove_feature`、`_set_checks`、`_build`、`_build_without_run`、`_inspect` 原样移到新文件 `cad_agent/tools_legacy.py`（行为不变，`ToolBox` 的公开成员不变）。

---

### Task 1：SCA 探测与速查表补充

**Files：** Create `scripts/probe_v2.py`、`cad_agent/agent/prompts/sca_cheatsheet_more.md`、`tests/test_prompts_v2.py`；Modify `docs/sca-api-notes.md`、`docs/sca-probe-output.txt`（追加）、`pyproject.toml`

**Interfaces：**
- Produces：`docs/sca-api-notes.md` 第 17–22 节，后面的 Task 5、13、14 和计划 2 的看图审查都以它为准；`sca_cheatsheet_more.md`。

- [ ] **Step 1：** 写 `scripts/probe_v2.py`（沿用 `scripts/probe_common.py` 的写法，先 `chdir` 到英文临时目录）。每个实验单独 try/except，出错记下异常类型和前 300 个字符后继续。依次做：
  1. **probe 单元**：手写一个 notebook，有参数单元、一个建方块的特征单元、一个 Task 5 Step 3 里那种包装过的 probe 单元、产品单元。用 `run_notebook` 运行，确认：`probe_out.txt` 写出来了，内容是 probe 里打印的文字；probe 里能读到参数和特征变量；probe 里抛异常时文件里仍有异常之前打印的内容，并记下 traceback 里 probe 单元的帧长什么样（Task 5 要靠它把出错位置标成 `probe`）。
  2. **没有特征时的占位**：notebook 里只有参数单元、probe 单元和一个产品单元，产品的实体是程序写的 `scad.make_box_rsolid(width=1, height=1, depth=1, bottom_face_center=(0, 0, 0))`。确认能运行。
  3. **一次运行取各阶段末尾的实体**：试 `run_notebook` 的返回里能不能按变量名取到中间特征的实体。只记录结论，本计划不用。
  4. **草图**：用 `make_sketch_rsketch` 加线段画一个 L 形闭合轮廓（顶点 (−60,0)、(60,0)、(60,8)、(−40,8)、(−40,60)、(−60,60)，画在 xz 平面），转成面，沿 y 拉伸 30，并让结果在 y 方向以 0 为中心。记下最短的可行写法、草图平面怎么指定、求解状态怎么看。
  5. **抽壳**：80×50×30 的盒子，去掉顶面，壁厚 2。记下 `shell_rsolid` 的写法和怎么选要去掉的面。同时试"先建外形、再减去一个小一圈的盒子"的写法，比较哪种得到的内腔尺寸更可控。
  6. **扫掠**：圆截面沿一条"直线—圆弧—直线"的路径扫掠成弯管。记下路径和截面的写法。
  7. **标准件**：`make_spur_gear_rsolid` 模数 2、齿数 30、齿宽 12。记下：参数名、轴线方向、z 的起止、包围盒三个方向的尺寸（验收里齿顶圆按 64 算）、能不能和圆柱直接 `union_rsolid`、`cut_rsolid`。`make_spur_rack_rsolid` 也试一个最小例子。
  8. **沉头孔**：通孔加一个更粗更浅的同轴圆柱减料，确认结果是一个实体。
  9. **多视角渲染**：`render_screenshot_rpath` 的 `view` 用角度元组，找出正视（从 −y 看）、俯视（从 +z 看）、右视（从 +x 看）各对应的 `(仰角, 方位角)`，各渲染一张确认。
- [ ] **Step 2：** 运行 `.venv\Scripts\python scripts\probe_v2.py`，把输出追加到 `docs/sca-probe-output.txt`。
- [ ] **Step 3：** 在 `docs/sca-api-notes.md` 追加六节，标题照抄：`## 17. probe 单元与占位产品`、`## 18. 草图轮廓`、`## 19. 抽壳`、`## 20. 扫掠`、`## 21. 标准件：齿轮与齿条`、`## 22. 多视角渲染`。实验 3 的结论写在第 17 节末尾，实验 8 写在第 19 节末尾。每节写：最短可行写法、实测到的数值、踩到的坑。
- [ ] **Step 4：** 写测试 `tests/test_prompts_v2.py`：
  - `test_cheatsheet_more_sections`：`sca_cheatsheet_more.md` 的第一行和 `## ` 标题，依次等于提示词文档第 8 节第一个 text 块的各行。
  - `test_cheatsheet_more_staged_rules_verbatim`：提示词文档第 8 节第二个 text 块的三行都原样出现在文件里。
  - `test_cheatsheet_more_examples_pass_the_guard`：文件里每个 `例：` 后面反引号里的代码是合法的单行 Python、能通过 `check_code`，用到的 `scad.xxx` 都在 `api_names()` 里（写法照 `tests/test_prompts.py::test_cheatsheet_examples_use_real_functions_and_pass_the_guard`）。
- [ ] **Step 5：** 运行这三个测试，确认失败（文件不存在）。
- [ ] **Step 6：** 写 `sca_cheatsheet_more.md`：前四节各至少 2 个条目，全部来自 Step 3 的笔记；第五节照抄三条。`pyproject.toml` 的 `package-data` 已经是 `agent/prompts/*.md`，不用改。
- [ ] **Step 7：** 运行全部测试，通过后提交：`chore: 第二版 SCA 探测与速查表补充`。

如果实验 1 或 2 行不通（probe 单元写不出文件、占位产品跑不起来），先记偏离，把可行的替代写法写进第 17 节，并同步改 Task 5 的 Step 3。

---

### Task 2：开关与配置

**Files：** Create `cad_agent/gates.py`、`tests/test_gates.py`；Modify `cad_agent/config.py`、`config.example.toml`、`tests/test_config.py`（只加测试）

**Interfaces：**
- Produces：
  ```python
  @dataclass(frozen=True)
  class Gates:
      staged: bool = True          # 分阶段流程
      mutation_check: bool = True  # 参数扰动验证
      visual_review: bool = True   # 看图审查（计划 2 实现）
      cases: bool = True           # 案例库
      @classmethod
      def legacy(cls) -> "Gates": ...   # 四项全 False
  ```
  `Config` 新增字段：`gates: Gates = field(default_factory=Gates)`、`max_tool_calls_per_stage: int = 25`、`max_tool_calls_total: int = 200`、`cases_dir: Path = Path("cases")`。配置文件里都写在 `[agent]` 下：`staged`、`mutation_check`、`visual_review`、`cases`（布尔）、`max_tool_calls_per_stage`、`max_tool_calls_total`（整数）、`cases_dir`（文字）。

- [ ] **Step 1：** 写测试：
  - `test_gates_default_all_on`、`test_gates_legacy_all_off`。
  - `test_config_defaults_have_gates_on`：没写这些键的配置文件，`config.gates == Gates()`，两个上限是 25 和 200。
  - `test_config_reads_gates`：`[agent]` 里写 `staged = false`、`mutation_check = false`、`max_tool_calls_per_stage = 10`，读出来对应。
  - `test_config_bad_gate_type`：`staged = "yes"` 抛 `ConfigError`，信息里有 `staged` 和"应该是"。
  - `test_config_limits_must_be_positive`：两个上限写 0 或负数抛 `ConfigError`，信息里有键名。
- [ ] **Step 2：** 运行，确认失败。
- [ ] **Step 3：** 实现。`config.example.toml` 的 `[agent]` 里用注释写出这几项和默认值，各一句说明。
- [ ] **Step 4：** 运行全部测试，通过后提交：`feat: 四个流程开关和分阶段的上限配置`。

---

### Task 3：需求单的位置关系

**Files：** Modify `cad_agent/brief.py`、`cad_agent/tools.py`；Test `tests/test_brief_relations.py`

**Interfaces：**
- Produces：
  - `Brief.relations: list[str]`（默认空）；`Brief.require_relations: bool = False`（不写进 `to_dict`，由 `ToolBox` 按开关设置）。
  - `PATCH_KEYS` 末尾加 `"relations"`。
  - `feature_name(text: str) -> str`：取 `，,；;：:（(` 中最早出现的那个之前的部分，去掉首尾空白。
  - `Brief.missing_relations() -> list[str]`：`require_relations` 为假或 `features` 不到两项时返回空表；否则返回 `features[1:]` 里，名字（`feature_name`）没有在任何一条 `relations` 里出现的那些名字。
  - `Brief.to_dict()`：`relations` 非空时才有 `"relations"` 这个键，放在 `features` 后面。`from_dict` 读它。`render_text()`：`relations` 非空时，在"组成部分"之后加一块 `位置关系：`，每条一行 `  - <原文>`。
  - `apply_patch`：`relations` 只要传了就整体替换；必须是非空文字组成的数组；确认之后改了它，确认状态清零（和 `features` 的规则相同）；变化行写 `位置关系有改动`。
  - `ToolBox._request_confirmation`：`missing_relations()` 非空时拒绝，报错原文 `这些部分还没有写明怎么相接：<名字，用顿号连接>。在 relations 里各写一句，要原样写出它的名字`。
  - `ToolBox._update_brief` 的返回：`missing_relations()` 非空时多一个键 `"relations_missing": [...]`。

- [ ] **Step 1：** 写测试：
  - `test_feature_name`：`"底板，放在最下面"` → `"底板"`；`"立板（左端）"` → `"立板"`；`"加强筋"` → `"加强筋"`。
  - `test_missing_relations_off_by_default`：`require_relations` 为假时永远是空表。
  - `test_missing_relations`：`features=["底板", "立板，在左端", "加强筋"]`、`relations=["立板的下端和底板的一端重叠"]`、`require_relations=True` → `["加强筋"]`；只有一个组成部分 → `[]`。
  - `test_to_dict_has_relations_only_when_set`：空的时候 `"relations" not in b.to_dict()`；有的时候键的顺序里它紧跟 `features`；`from_dict(to_dict())` 还原。
  - `test_render_text_shows_relations`。
  - `test_patch_relations_replaces_and_resets_confirmation`、`test_patch_relations_rejects_bad_values`（不是数组、有空文字 → `BriefError`，需求单不变）。
  - `test_confirmation_refused_until_relations_complete`（`ToolBox` + `require_relations=True`）：报错等于上面的原文；补全后能请确认。
  - `test_update_brief_reports_relations_missing`。
- [ ] **Step 2：** 运行，确认失败。
- [ ] **Step 3：** 实现。
- [ ] **Step 4：** 运行全部测试（旧的 `test_brief.py` 必须原样通过），提交：`feat: 需求单加位置关系`。

---

### Task 4：计划、阶段归属、阶段选取

**Files：** Create `cad_agent/plan.py`、`cad_agent/staged/__init__.py`、`cad_agent/staged/select.py`、`tests/test_plan.py`、`tests/test_select.py`；Modify `cad_agent/notebook.py`、`cad_agent/checks/spec.py`、`cad_agent/tools.py`（只给 `Workspace` 加字段）

**Interfaces：**
- Produces（`cad_agent/plan.py`，不依赖 SCA，也不依赖 `tools.py`）：
  ```python
  MAX_STAGES = 12
  class PlanError(ValueError): ...            # 信息是中文，直接返回给模型
  @dataclass
  class Stage:
      id: str            # "s1"、"s2"……按位置编号
      title: str
      done_when: str
      passed: bool = False
  @dataclass
  class Plan:
      stages: list[Stage]
      def current(self) -> Stage | None: ...            # 第一个未通过的；全部通过时 None
      def complete(self) -> bool: ...
      def ids(self) -> list[str]: ...
      def index(self, stage_id: str) -> int: ...        # 不存在抛 PlanError
      def get(self, stage_id: str) -> Stage: ...
      def mark_passed(self, stage_id: str) -> None: ...
      def invalidate_from(self, stage_id: str) -> None: ...   # 这个阶段和后面的都变回未通过
      def invalidate_all(self) -> None: ...
      def to_list(self) -> list[dict]: ...              # [{"id","title","done_when","passed"}]
      @classmethod
      def from_list(cls, raw: list[dict]) -> "Plan": ...
  def revise(old: Plan | None, raw: object, slugs_by_stage: dict[str, list[str]]) -> Plan: ...
  ```
  `revise` 是 `set_plan` 的校验与合并：`raw` 必须是 1 到 12 个 `{"title", "done_when"}`（都是非空文字）；`old` 里已通过的阶段必须原样（`title`、`done_when` 都相同）排在新计划的最前面，否则抛 `PlanError`，信息用提示词文档 7.3"改动了已通过的阶段"的原文；新计划比旧计划短、被去掉的阶段在 `slugs_by_stage` 里还有特征时抛 `PlanError`，信息用 7.3"删掉了还有特征的阶段"的原文；其余的格式问题各给一句中文。返回的新计划里，保留下来的已通过阶段仍是已通过。
- Produces（其他文件）：
  - `Feature` 加字段 `stage: str = ""`；`to_list` 在 `stage` 非空时才写出这个键；`from_list` 读它。
  - `FeatureList.in_stage(stage_id: str) -> list[Feature]`；`FeatureList.insert(f: Feature, index: int) -> None`（已有同名 slug 时抛 `NotebookError`）。
  - `checks/spec.py`：`HOLDS = ("from_here", "here_only")`；`KNOWN_KEYS` 加 `"stage"`、`"holds"`；`Check` 加字段 `stage: str | None = None`、`holds: str = "from_here"`；`holds` 写了别的值抛 `CheckSpecError`；`stage` 必须是文字。
  - `Workspace` 加字段 `plan: Plan | None = None`、`probes_used: int = 0`。
  - `cad_agent/staged/select.py`：
    ```python
    def features_upto(ws: Workspace, stage_id: str) -> list[Feature]: ...   # 这个阶段和它前面各阶段的特征，保持原顺序
    def checks_for_stage(checks_raw: list[dict], plan: Plan, stage_id: str) -> list[dict]: ...
    def final_checks(ws: Workspace) -> list[dict]: ...
    def stage_ready(ws: Workspace, stage_id: str) -> bool: ...              # 这个阶段既有特征又有检查
    def insert_index(ws: Workspace, stage_id: str) -> int: ...              # 这个阶段新特征默认插在哪里
    ```
    - `checks_for_stage`：`stage` 排在这个阶段之前或就是它、且 `holds` 是 `from_here`（没写也算）的检查，加上 `stage` 就是它的 `here_only` 检查；保持原顺序。
    - `final_checks`：`ws.plan` 是 `None` 时原样返回 `ws.checks_raw`；否则等于对最后一个阶段调用 `checks_for_stage`。
    - `insert_index`：这个阶段已有特征时，是它最后一个特征的后面；没有时，是排在它前面的各阶段里最后一个特征的后面；都没有时是 0。

- [ ] **Step 1：** 写测试 `tests/test_plan.py`：`test_current_and_complete`、`test_invalidate_from`、`test_round_trip`、`test_revise_first_plan_numbers_stages`（`s1`…`sn`）、`test_revise_limits`（0 个、13 个、缺 `title`、空文字各抛 `PlanError`）、`test_revise_keeps_passed_prefix`、`test_revise_rejects_changing_passed_stage`（信息等于 7.3 原文，`<id>` 填实际编号）、`test_revise_rejects_dropping_stage_with_features`、`test_revise_can_append_after_all_passed`。
- [ ] **Step 2：** 写测试 `tests/test_select.py`：
  - `test_feature_stage_round_trip_and_default`：旧格式（没有 `stage`）读写不变。
  - `test_check_holds_validation`：`holds: "sometimes"` 抛 `CheckSpecError`；`stage`、`holds` 不再被当成不认识的字段。
  - `test_checks_for_stage`：三个阶段、五条检查（s1 `from_here`、s1 `here_only`、s2 `from_here`、s2 `here_only`、s3 `from_here`）→ s1 得到前两条；s2 得到第 1、3、4 条；s3 得到第 1、3、5 条。
  - `test_final_checks_without_plan_returns_everything`。
  - `test_features_upto_and_insert_index`：特征归属 s1、s1、s2 时，`insert_index(ws, "s1") == 2`、`insert_index(ws, "s2") == 3`、`insert_index(ws, "s3") == 3`；全空时是 0。
  - `test_stage_ready`。
- [ ] **Step 3：** 运行，确认失败。
- [ ] **Step 4：** 实现。
- [ ] **Step 5：** 运行全部测试，提交：`feat: 计划与阶段的数据结构`。

---

### Task 5：沙盒支持 probe 和冻结期望值

**Files：** Modify `cad_agent/notebook.py`、`cad_agent/sandbox/execute.py`、`cad_agent/sandbox/runner.py`；Test `tests/test_probe_notebook.py`、`tests/test_execute_v2.py`（标记 `sca`）

**Interfaces：**
- Produces：
  - `render_notebook(params, features, probe: str | None = None) -> RenderedNotebook`。`probe` 为 `None` 时输出和现在逐字相同。
  - `run_job(..., mode: Literal["build", "inspect", "probe"] = "build", check_values: dict[str, float] | None = None, ...)`。
  - `RunResult` 加字段 `probe_output: str | None = None`。
  - `PROBE_OUTPUT_LIMIT = 2000`（放在 `execute.py`）。

- [ ] **Step 1：** 写测试 `tests/test_probe_notebook.py`（不需要 SCA）：
  - `test_no_probe_output_is_unchanged`：`render_notebook(p, f) .text == render_notebook(p, f, None).text`，且文字里没有 `# ---- probe ----`。
  - `test_probe_cell_reads_params_and_features`：probe 代码用到参数 `phone_w` 和特征变量 `base` 时，probe 单元的函数签名里有这两个名字；单元在最后一个特征之后、产品单元之前；`cell_lines` 里没有多出条目。
  - `test_probe_assignments_do_not_leak`：probe 里写 `x = 1`（不带下划线）不报错，也不出现在任何单元的返回值里。
  - `test_probe_without_features_uses_placeholder`：没有特征但有 probe 时不抛 `NotebookError`，产品单元的实体来自占位方块。
  - `test_no_features_and_no_probe_still_raises`。
- [ ] **Step 2：** 写测试 `tests/test_execute_v2.py`（`sca`）：
  - `test_probe_prints_facts`：一个方块特征，probe 是 `print(phone_w)` 和打印 `model` 的包围盒尺寸（写法取自笔记第 4 节）；`result.probe_output` 里有 `78`，`result.error is None`。
  - `test_probe_model_is_none_without_features`：probe `print(model is None)` → 输出 `True`。
  - `test_probe_error_is_reported_with_partial_output`：probe 先 `print("到这里")` 再用一个未定义的名字；`error["cell"] == "probe"`、`error["type"] == "NameError"`，输出里有 `到这里`。
  - `test_probe_output_truncated`：打印 5000 个字符 → 输出长度不超过 `PROBE_OUTPUT_LIMIT` 加上末尾一行 `…（后面的输出省略）`。
  - `test_probe_timeout`：`while True: pass`，`timeout_s=3` → `timed_out` 为真，不抛异常。
  - `test_check_values_freeze_expected`：方块宽度用参数 `phone_w`，检查 `PHONE_W`（期望值写 `phone_w`）。参数给 93.6、`check_values={"phone_w": 78.0, ...}` → 这条检查不通过，`expected == 78.0`、`measured` 约 93.6；同样的模型不传 `check_values` → 通过。
  - `test_check_values_also_freeze_where`：一条 `count` 检查的 `where` 里用了参数表达式，冻结后选不到面 → 不通过。
- [ ] **Step 3：** 实现 `render_notebook` 的 probe 单元。单元内容固定为下面的形状（`<…>` 是程序填的；probe 代码已经先过 `check_code`，这段包装是程序写的，不过 guard）：
  ```python
  # ---- probe ----
  import contextlib as _ctx
  import io as _io
  def _probe(model):
      <probe 代码，整体缩进一层>
  _buf = _io.StringIO()
  try:
      with _ctx.redirect_stdout(_buf):
          _probe(<最后一个特征的变量名，没有特征时写 None>)
  finally:
      with open("probe_out.txt", "w", encoding="utf-8") as _f:
          _f.write(_buf.getvalue())
  return ()
  ```
  单元的输入 = probe 代码里读到的、且是参数名或前面特征变量名的那些名字，再加上最后一个特征的变量名。没有特征时，在 probe 单元前面加一个程序写的单元，内容是 `placeholder_body = scad.make_box_rsolid(width=1, height=1, depth=1, bottom_face_center=(0, 0, 0))`，产品单元用它。
- [ ] **Step 4：** 实现 `runner.py`：`mode == "probe"` 时不跑检查、不导出；无论运行成功还是抛异常，都读工作目录里的 `probe_out.txt`（没有就当空），截断后放进结果的 `probe_output`；出错的帧在 probe 单元里时 `error["cell"]` 写 `"probe"`（判断办法用 Task 1 第 17 节记下的）。`check_values` 不为空时，`run_checks` 和 `query` 用它代替运行得到的参数值。`execute.py` 把这两项传进 job、读回结果。
- [ ] **Step 5：** 运行全部测试（`tests/test_execute.py`、`tests/test_notebook.py` 原样通过），提交：`feat: 沙盒支持试验代码和冻结检查期望值`。

---

### Task 6：分阶段的工具（一）：计划、特征、检查的关卡

**Files：** Create `scripts/gen_staged_specs.py`、`cad_agent/staged/specs.py`、`cad_agent/staged/messages.py`、`cad_agent/staged/tools.py`、`cad_agent/agent/prompts/system_v2.md`、`tests/test_staged_tools.py`；Modify `cad_agent/tools.py`

**Interfaces：**
- Consumes：`Gates`（Task 2）、`Brief.require_relations`（Task 3）、`Plan`、`revise`、`select.*`（Task 4）。
- Produces：
  - `ToolBox.__init__(self, ws, run_job=execute.run_job, timeout_s=60, secret_names=(), gates: Gates | None = None)`；`self.gates = gates or Gates.legacy()`；`gates.staged` 为真时把 `ws.brief.require_relations` 设为真。
  - `staged/specs.py`：`TOOL_SPECS_V2: list[dict]`、`TOOL_NAMES_V2: list[str]`（12 个，顺序见提示词文档第 6 节）、`PRE_CONFIRM_TOOLS_V2 = ["update_brief", "ask_user", "request_confirmation", "api_help", "read_reference"]`。由 `scripts/gen_staged_specs.py` 从两份提示词文档生成，文件头注明"由脚本生成，不要手改"。
  - `staged/messages.py`：提示词文档 7.2、7.3、7.4 的每条原文各一个常量或一个带参数的函数，例如 `NO_PLAN`、`need_checks(stage_id)`、`all_passed()`、`plan_locked(stage_id)`、`unknown_stage(stage, ids)`、`future_stage(stage, current_id)`、`before_other_stage(stage_id)`、`hint_stage_passed(passed_ids, next_stage)`、`hint_unconstrained(names)`。
  - `staged/tools.py`：
    ```python
    class StagedTools:
        def __init__(self, box: "ToolBox") -> None: ...
        def handlers(self) -> dict[str, Callable[[dict], ToolOutcome]]: ...
    ```
    本任务提供 `set_plan`、`upsert_feature`、`remove_feature`、`set_checks` 四个；`build`（Task 7）、`probe`、`read_reference`（Task 9）先返回 `{"error": "这个工具还没有接上"}`，由后面的任务换掉。`update_brief`、`ask_user`、`request_confirmation`、`inspect`、`api_help` 沿用 `ToolBox` 原来的处理函数。
  - 分阶段时 `ToolBox.available()` / `schemas()` / 参数必填检查都用 V2 的表；`_update_brief` 在分阶段、`changes` 非空且已有计划时调用 `ws.plan.invalidate_all()`。

规则（都在 `StagedTools` 里；报错不计失败次数，状态不变）：
- 需求单可以建模但 `ws.plan is None` 时，`upsert_feature`、`remove_feature`、`set_checks`、`build`、`probe` 返回 `NO_PLAN`。
- `set_plan`：调用 `revise`；成功后返回 `{"ok": true, "stages": [{"id", "title", "passed"}…], "current": <id 或 null>}`，`unbuilt_edits` 设为真。
- `upsert_feature`：
  - slug 已存在：原地替换，归属阶段不变；那个阶段原来是已通过的，就 `invalidate_from` 它。
  - slug 不存在：没有当前阶段（全部通过）→ `all_passed()`；当前阶段没有检查 → `need_checks(id)`；否则归属当前阶段，插在 `insert_index`；传了 `before` 时必须是同一阶段里的特征，否则 `before_other_stage(id)`。
  - 代码仍先过 `check_code`，报错文字和旧流程相同。
  - 返回 `{"ok": true, "stage": <id>, "features": ["base(build, s1)", …]}`。
- `remove_feature`：删掉后，对它原来所在的阶段 `invalidate_from`。
- `set_checks`：`stage` 不存在 → `unknown_stage`；排在当前阶段之后 → `future_stage`；通过 `parse_checks` 校验（失败的文字和旧流程相同）；只替换 `ws.checks_raw` 里 `stage` 等于它的那些，新检查逐条写上 `"stage": <id>`，放在原来这个阶段的检查所在的位置（原来没有就接在末尾）；这个阶段原来是已通过的就 `invalidate_from`。返回 `{"ok": true, "stage": <id>, "count": <这个阶段的条数>, "missing_coverage": [...]}`，`missing_coverage` 只按全部 `from_here` 检查算。

- [ ] **Step 1：** 写测试 `tests/test_staged_tools.py`（共用的 `make_box(confirmed=True, plan=None)` 建一个 `ToolBox(ws, run_job=Runner(), gates=Gates())`）：
  - `test_system_v2_is_verbatim_copy`：`system_v2.md` 等于提示词文档第 1 节的 text 块。
  - `test_specs_v2_are_verbatim`：7 个新写的工具等于提示词文档第 6 节的 json 块；5 个沿用的等于 1.1 版提示词文档第 4 节的同名 json 块；`set_checks` 的 `description` 和 `parameters` 按第 6 节写的拼法算出来后相等；`TOOL_NAMES_V2` 的顺序等于文档里列的顺序。
  - `test_legacy_toolbox_is_untouched`：`ToolBox(ws, run_job=Runner())` 的 `schemas()` 仍是旧的 9 个，`gates == Gates.legacy()`，`ws.brief.require_relations` 为假。
  - `test_schemas_by_phase_v2`：未确认时 5 个，确认后 12 个。
  - `test_modeling_tools_need_a_plan`：四个工具各返回 `NO_PLAN`。
  - `test_set_plan_ok`、`test_set_plan_errors_come_from_revise`。
  - `test_new_feature_needs_checks_first`（等于 `need_checks("s1")`）、`test_new_feature_goes_to_current_stage`、`test_before_must_be_in_same_stage`、`test_new_feature_when_all_passed`。
  - `test_replacing_feature_invalidates_its_stage_and_later`：三个阶段都已通过，替换 s2 的特征 → s1 仍通过，s2、s3 未通过，特征的归属和位置不变。
  - `test_remove_feature_invalidates`。
  - `test_set_checks_replaces_only_that_stage`：先写 s1 两条、s2 一条，再写 s1 一条 → 剩两条，s2 那条还在，每条都带 `stage`。
  - `test_set_checks_rejects_unknown_and_future_stage`（Review Focus 1）：两种报错等于原文；`ws.checks_raw` 和各阶段的状态不变。
  - `test_set_checks_on_passed_stage_invalidates`。
  - `test_guard_and_spec_errors_keep_state`。
  - `test_update_brief_change_invalidates_all`、`test_update_brief_without_change_does_not`。
  - `test_unbuilt_edits_set_by_each_edit`。
- [ ] **Step 2：** 运行，确认失败。
- [ ] **Step 3：** 写 `scripts/gen_staged_specs.py` 并运行生成 `staged/specs.py`；把提示词文档第 1 节写进 `system_v2.md`；实现 `messages.py`、`staged/tools.py`，改 `ToolBox`。
- [ ] **Step 4：** 运行全部测试（`tests/test_tools.py` 原样通过），提交：`feat: 分阶段流程的计划、特征和检查关卡`。

---

### Task 7：分阶段的 build

**Files：** Create `cad_agent/staged/build.py`、`tests/helpers_staged.py`、`tests/test_staged_build.py`；Modify `cad_agent/staged/tools.py`、`cad_agent/tools.py`

**Interfaces：**
- Consumes：`select.*`（Task 4）、`run_job`（Task 5）、`messages.*`（Task 6）。
- Produces：
  ```python
  @dataclass
  class StageRun:
      stage_id: str
      run: RunResult
  @dataclass
  class Advance:
      runs: list[StageRun]                 # 这次实际验证过的阶段，按顺序
      passed: list[str]                    # 这次新通过的阶段编号
      stopped: str | None                  # 停在哪个阶段；全部通过时 None
      reason: Literal["failed", "not_ready", "complete"]
  def advance(ws: Workspace, run_job: Callable[..., RunResult], *, timeout_s: float, secret_names: Iterable[str],
              stl_dir: Path | None = None, workers: int = 4) -> Advance: ...
  def build_tool(box: ToolBox) -> ToolOutcome: ...
  ```
  `ToolBox` 新增公开成员：`stage_dir: Path | None = None`（主循环设成会话目录下的 `stages`）、`last_advance: Advance | None = None`、`last_gate: GateResult | None = None`（Task 8 填）。
  `tests/helpers_staged.py`：`StageRunner(results: dict[str, RunResult | list[RunResult]], default: RunResult | None = None)`——可调用，按"渲染出的 notebook 里最后一个特征的 slug"取结果（列表时依次取、用完重复最后一个）；`calls` 记下每次的最后一个特征 slug、检查的 id 列表、全部关键字参数；带 `export_step` 的调用像 `Runner` 一样写出假文件；带 `export_stl` 的调用写出假 STL。它必须能被多个线程同时调用。

`advance` 的做法：
1. 从当前阶段起，取连续的、`stage_ready` 的阶段；一个都没有就返回 `reason="not_ready"`、`stopped` 是当前阶段、`runs` 为空。
2. 这些阶段各跑一次：`render_notebook(ws.brief.params, features_upto(ws, id))`，检查用 `checks_for_stage`，`mode="build"`；`stl_dir` 不为空时带 `export_stl=stl_dir / f"{id}.stl"`。最多 `workers` 个同时跑。渲染或解析出错时不运行，结果记成和旧流程 `_build_without_run` 一样的 `RunResult`。
3. 按顺序看结果：`run.ok` 就 `mark_passed`、把 `ws.probes_used` 清零，接着看下一个；遇到第一个不通过的就停，`reason="failed"`，它后面已经跑完的结果丢掉。
4. 全部通过后：计划已经 `complete()` 就是 `reason="complete"`；否则 `reason="not_ready"`、`stopped` 是下一个阶段。

`build_tool` 的做法：
- 当前阶段没有特征 / 没有检查：返回 7.3 的两条报错，不运行，不计失败。计划已经全部通过时再调用 build：把最后一个阶段重新验证一次（先 `invalidate_from` 它），再往下走。
- 调用 `advance`，存进 `box.last_advance`；`ws.last_run` 设为最后一个 `StageRun.run`；`unbuilt_edits` 清掉。
- 这次有阶段新通过时，先把 `box.build_failures` 清零。
- `reason == "failed"`：`build_failures += 1`。
- `reason == "complete"`：调用 Task 8 的 `run_final_gate`（本任务先用"只算缺检查"的临时版本，Task 8 换掉）。有 `unconstrained` 时 `build_failures += 1`；只缺检查不计失败。
- 返回体按提示词文档 7.1、7.2 组装；`failed_checks`、`error`、`facts`、`passed_checks` 取自这次最后一个 `StageRun`；`deliverable` 只在终检通过时为真。`ws.last_build_content` 设为返回体。

- [ ] **Step 1：** 写 `tests/helpers_staged.py`，以及共用的小工具 `two_stage_ws()`（已确认的需求单、两个阶段的计划、每个阶段一个特征一条检查）。
- [ ] **Step 2：** 写测试 `tests/test_staged_build.py`：
  - `test_advance_runs_ready_stages_in_order`：两个阶段都写好 → `passed == ["s1", "s2"]`、`reason == "complete"`；`StageRunner.calls` 里 s1 那次只有 s1 的特征。
  - `test_advance_stops_at_first_failure`：s1 失败 → `passed == []`、`stopped == "s1"`，s2 仍未通过。
  - `test_advance_not_ready`：只写了 s1 → `passed == ["s1"]`、`reason == "not_ready"`、`stopped == "s2"`。
  - `test_here_only_checks_only_run_in_their_stage`：看两次调用里检查的 id。
  - `test_stage_stl_is_exported`：给了 `stl_dir` 时两次调用的 `export_stl` 分别是 `s1.stl`、`s2.stl`。
  - `test_render_error_counts_as_failed_stage`：特征变量名不对 → 不调用 `run_job`，`reason == "failed"`，`error.type == "NotebookError"`。
  - `test_build_body_is_superset`：返回体有旧的 8 个键和 `stage`、`stages_passed`、`final_gate`。
  - `test_build_hint_after_stage_passed`：等于 `hint_stage_passed(["s1"], s2)`，`passed` 为假，`failures_left == 3`。
  - `test_build_failure_counting_resets_when_a_stage_passes`：s1 连续失败两次 → `build_failures == 2`；第三次 s1 通过、s2 失败 → `build_failures == 1`。
  - `test_build_without_features_or_checks_is_not_a_failure`：两条报错等于原文，`build_failures == 0`，`run_job` 没被调用。
  - `test_build_deliverable_when_complete`（`Gates(mutation_check=False)`）：两个阶段通过、不缺检查 → `deliverable` 为真，hint 是"全部通过"的原文，`final_gate == {"missing_coverage": [], "unconstrained": [], "unbuildable": []}`。
  - `test_build_coverage_gap_at_final_gate_is_not_a_failure`。
  - `test_build_again_when_complete_reverifies_last_stage`。
  - `test_editing_earlier_stage_reverifies_from_there`（Review Focus 4）：两个阶段通过后替换 s1 的特征再 build → `StageRunner.calls` 依次是 s1、s2；s1 那次的检查里有 s1 的 `here_only`，s2 那次没有。
  - `test_probes_used_resets_on_pass`。
- [ ] **Step 3：** 运行，确认失败。
- [ ] **Step 4：** 实现，把 `StagedTools` 里 `build` 的占位换成 `build_tool`。
- [ ] **Step 5：** 运行全部测试，提交：`feat: 分阶段的 build`。

---

### Task 8：参数扰动验证与终检

**Files：** Create `cad_agent/staged/mutation.py`、`cad_agent/staged/final_gate.py`、`tests/test_mutation.py`、`tests/test_final_gate.py`、`tests/test_final_gate_sca.py`（标记 `sca`）；Modify `cad_agent/staged/build.py`

**Interfaces：**
- Consumes：`run_job(check_values=...)`（Task 5）、`final_checks`（Task 4）、`MANDATORY_IDS`（`checks/spec.py`）。
- Produces：
  ```python
  # mutation.py
  LIMIT = 12
  @dataclass(frozen=True)
  class MutationResult:
      param: str
      verdict: Literal["constrained", "unconstrained", "unbuildable"]
      tried: tuple[float, ...]        # 实际试过的数值
      caught_by: tuple[str, ...]      # constrained 时：是哪些检查发现的
  def perturbations(p: Param) -> list[float]: ...
  def run_mutation(ws: Workspace, run_job: Callable[..., RunResult], *, timeout_s: float,
                   secret_names: Iterable[str], workers: int = 4) -> tuple[list[MutationResult], list[str]]: ...
  # final_gate.py
  @dataclass
  class GateResult:
      passed: bool
      missing_coverage: list[str]
      mutation: list[MutationResult]
      skipped: list[str]              # 超过 12 个而没有扰动的参数
      @property
      def unconstrained(self) -> list[str]: ...
      @property
      def unbuildable(self) -> list[str]: ...
      def to_dict(self) -> dict: ...  # 提示词文档 7.1 的 final_gate 三个键，外加 "skipped" 和每个参数的 "mutation" 明细
  def run_final_gate(ws: Workspace, run_job: Callable[..., RunResult], gates: Gates, *,
                     timeout_s: float, secret_names: Iterable[str]) -> GateResult: ...
  ```

规则：
- `perturbations`：数值是 0 → `[1.0]`；单位是 `1` 且数值是整数 → `[v + 1]`，`v - 1 >= 1` 时再加 `v - 1`；其余 → `[v * 1.2, v * 0.8]`。
- `run_mutation`：只取 `source == "user"` 的参数，按需求单里的顺序取前 12 个，多出来的名字放进返回的第二项。对每个参数，按 `perturbations` 的顺序试：用改后的参数渲染全部特征、检查用 `final_checks(ws)`、`check_values` 传改之前的全部参数值。
  - 运行出错、超时、或者有必做检查（`MANDATORY_IDS`）不通过：这一次算"建不出来"，试下一个数值；都试完了就是 `unbuildable`。
  - 没出错、必做检查都过、有别的检查不通过：`constrained`，`caught_by` 是这些检查的 id，不再试。
  - 没出错、全部检查都过：`unconstrained`，不再试。
  - 各参数之间并行，最多 `workers` 个。
- `run_final_gate`：先算 `missing_coverage`（只看 `from_here` 的检查）；有缺的就直接返回 `passed=False`，不做扰动。`gates.mutation_check` 为假时不做扰动。否则做扰动；`passed` = 没有缺检查且没有 `unconstrained`。
- `build_tool` 改用它，结果存进 `box.last_gate`。

- [ ] **Step 1：** 写测试 `tests/test_mutation.py`（假 `run_job`，按传进来的参数值决定结果）：
  - `test_perturbations_for_zero_and_small_counts`（Review Focus 2）：`0 mm → [1.0]`；`1 个 → [2.0]`；`4 个 → [5.0, 3.0]`；`30 mm → [36.0, 24.0]`；`2.5`（单位 `1` 但不是整数）→ `[3.0, 2.0]`。
  - `test_constrained_when_a_check_fails`、`test_unconstrained_when_everything_passes`（只试了第一个数值）、`test_unbuildable_after_both_directions_fail`、`test_mandatory_failure_counts_as_unbuildable`、`test_second_direction_is_tried_after_error`。
  - `test_check_values_are_the_original_values`：传给 `run_job` 的 `check_values` 等于改之前的参数值，渲染出的 notebook 里是改之后的数值。
  - `test_only_user_params_and_limit`：`suggested` 的参数不扰动；15 个用户参数时扰动前 12 个，后 3 个的名字在第二项里。
- [ ] **Step 2：** 写测试 `tests/test_final_gate.py`：`test_coverage_gap_skips_mutation`、`test_mutation_off`、`test_passed_when_all_constrained`、`test_unbuildable_does_not_block`（Review Focus 3）、`test_to_dict_keys`；以及 `tests/test_staged_build.py` 里补两条：`test_build_unconstrained_counts_as_failure`（hint 等于 `hint_unconstrained([...])`，`build_failures == 1`，`deliverable` 为假）、`test_build_deliverable_after_gate`。
- [ ] **Step 3：** 写测试 `tests/test_final_gate_sca.py`（真实 SCA，对应设计文档成功标准 3）：
  - `test_dead_param_is_caught`：一个小盒子，需求单里有用户参数 `wall = 2`，但内腔的代码把壁厚写死成 2；检查用 `wall` 的表达式写了外形和壁上的点。终检结果 `unconstrained == ["wall"]`。
  - `test_weak_check_is_caught`：带孔的板，孔径用了参数 `hole_d`，唯一用到 `hole_d` 的检查期望值是 `hole_d * 0 + 80`（和孔径无关）。终检结果 `unconstrained == ["hole_d"]`。
  - `test_good_model_passes`：同一块板，孔径的检查照速查表"孔径"一条写。`passed` 为真，每个参数都是 `constrained`。
- [ ] **Step 4：** 运行，确认失败；实现；运行全部测试，提交：`feat: 参数扰动验证与终检`。

---

### Task 9：probe 与 read_reference

**Files：** Create `cad_agent/references.py`、`cad_agent/staged/extras.py`、`cad_agent/agent/prompts/references_index.md`、`tests/test_references.py`、`tests/test_staged_extras.py`；Modify `cad_agent/staged/tools.py`、`cad_agent/agent/state.py`

**Interfaces：**
- Produces：
  ```python
  # references.py
  REFERENCES: dict[str, str]          # 10 个名字 → 相对 skill 文档目录的路径，如 "feature-ordering": "discipline/feature-ordering.md"
  HEAD_CHARS = 3000
  SECTION_CHARS = 6000
  class RefError(ValueError): ...     # 信息用提示词文档 7.3 的两条原文
  def read_reference(name: str, section: str | None = None) -> dict: ...
  # 返回 {"name", "sections": [二级标题原文…], "text": str, "truncated": bool}
  # staged/extras.py
  PROBE_LIMIT = 10
  def probe_tool(box: ToolBox, args: dict) -> ToolOutcome: ...
  def read_reference_tool(box: ToolBox, args: dict) -> ToolOutcome: ...
  # state.py
  def load_system_prompt(staged: bool = False) -> str: ...
  ```
  - 文档目录的定位办法和 `api_docs._api_dir` 相同（只定位，不导入 SCA），根目录是 `…/skill/resources/docs/skill/references`。
  - `sections` 是以 `## ` 开头的行去掉 `## ` 后的文字；`section` 要和其中一项完全相同（首尾空白不计）；一节的范围是从它的标题行到下一个 `## ` 之前。
  - `load_system_prompt(False)` 的结果和现在逐字相同；`load_system_prompt(True)` = `system_v2.md` + `references_index.md` + `sca_cheatsheet.md` + `sca_cheatsheet_more.md`，各段去掉末尾换行后用一个空行连接，最后一个换行。
  - `probe_tool`：`ws.probes_used >= PROBE_LIMIT` → 7.3 的原文；代码先过 `check_code`；渲染 `render_notebook(params, features_upto(ws, 当前阶段或最后一个阶段), probe=code)`，`mode="probe"`；成功后 `probes_used += 1`；返回 `{"output": <文字>, "error": <和 build 相同格式，没有就是 null>, "probes_left": <n>}`。不改 `build_failures`、`unbuilt_edits`、`last_run`。
  - `read_reference` 在需求单确认之前也能用。

- [ ] **Step 1：** 写测试 `tests/test_references.py`：
  - `test_whitelist_matches_the_index`：`REFERENCES` 的 10 个名字，等于 `references_index.md` 里每个 `- ` 条目冒号前的名字，顺序不限；`references_index.md` 等于提示词文档第 2 节的 text 块。
  - `test_every_reference_file_exists`：10 个文件都在安装包里。
  - `test_head_lists_sections`：`read_reference("part-modeling")` 的 `sections` 里有 `Boolean discipline`，`text` 不超过 3000 字符。
  - `test_section_text`：`read_reference("part-modeling", "Boolean discipline")` 的 `text` 以 `## Boolean discipline` 开头，不含下一节的标题。
  - `test_long_section_truncated`：对 `ql-playbook` 里最长的一节，`len(text) <= 6000 + len("\n…（后面的内容省略）")` 且 `truncated` 为真。
  - `test_unknown_name_and_section`：两条报错等于原文；`name` 写成 `../SKILL` 也只得到"没有叫……的文档"。
- [ ] **Step 2：** 写测试 `tests/test_staged_extras.py`：
  - `test_probe_runs_and_counts`：`StageRunner` 返回带 `probe_output` 的结果 → 返回体有 `output`、`probes_left == 9`；`build_failures`、`last_run`、`unbuilt_edits` 都没变；`run_job` 收到的 `mode == "probe"`。
  - `test_probe_limit`：第 11 次返回原文，`run_job` 没再被调用。
  - `test_probe_guard`：代码里有 `import os` → 报错，次数不增加。
  - `test_probe_uses_features_up_to_current_stage`。
  - `test_read_reference_before_confirmation`。
  - `test_full_system_prompt_v2`：`load_system_prompt(True)` 依次包含四段；`load_system_prompt()` 和 `load_system_prompt(False)` 相同，且不含 `set_plan`。
- [ ] **Step 3：** 运行，确认失败；实现；运行全部测试，提交：`feat: 试验代码和查阅文档两个工具`。

---

### Task 10：主循环接入分阶段流程

**Files：** Create `cad_agent/staged/summary.py`、`tests/test_staged_loop.py`、`tests/test_snapshot_v2.py`；Modify `cad_agent/agent/loop.py`、`cad_agent/agent/context.py`、`cad_agent/agent/state.py`、`cad_agent/agent/delivery.py`、`cad_agent/agent/automation.py`、`cad_agent/session.py`

**Interfaces：**
- Consumes：前面各任务。
- Produces：
  - `render_snapshot(ws: Workspace, staged: bool = False) -> str`：`staged` 为假时和现在逐字相同；为真时按提示词文档第 3 节。
  - `Context.fold(summary: str) -> None`：把本轮里上一个折叠点之后的全部 assistant / tool / user 消息换成一条 `{"role": "user", "content": summary}`，并把折叠点移到它后面。
  - `staged/summary.py`：`stage_summary(ws: Workspace, adv: Advance) -> str`（提示词文档第 4 节）。
  - `Session.part_dir(self, part_id: str = "main") -> Path`（这一版返回 `self.dir`）；`save_state(..., plan: list[dict] | None = None)`：给了就写 `plan.json`；`new_version(..., extra_json: dict[str, Any] | None = None, stages_src: Path | None = None)`：`extra_json` 的每一项写成版本目录里的 `<键>.json`，`stages_src` 整个目录复制成版本目录里的 `stages/`。`save_state`、`versions`、`new_version` 里的路径都从 `part_dir()` 出发。
  - `delivery_text(version, checks, changes, repairs, gate: GateResult | None = None) -> str`：`gate` 不为空且做了扰动时，按提示词文档第 9 节加一行。
  - `Agent.__init__` 的签名不变。分阶段与否看 `self.toolbox.gates.staged`。
  - 日志新增：每个新通过的阶段一条 `{"kind": "stage", "id", "title", "checks": <条数>, "size", "volume"}`；做了终检时一条 `{"kind": "gate", **GateResult.to_dict()}`；`build` 记录多出 `stage`、`stages_passed`。

主循环在分阶段时的不同之处（旧流程一行都不变）：
1. 系统提示词用 `load_system_prompt(True)`，快照用 `render_snapshot(ws, True)`；主循环启动时把 `toolbox.stage_dir` 设成 `session.dir / "stages"`。
2. 计数：`_Counters` 加 `stage_tool_calls`。每次工具调用两个计数都加 1；有阶段新通过时 `stage_tool_calls` 清零。`stage_tool_calls >= config.max_tool_calls_per_stage` → 本轮以 `failed` 结束，文字用提示词文档 7.4 的第二个 text 块；`tool_calls >= config.max_tool_calls_total` → 用旧的"达到上限"文字，数字写 200。提醒字段按阶段剩余次数算，文字用 7.4 的第一个 text 块。
3. 折叠：一次回复里的工具全部执行完之后（`_after_reply` 开头）以及程序自动 build 之后，如果 `toolbox.last_advance` 里有还没折叠过的新通过阶段，调用 `context.fold(stage_summary(...))`，并写 `stage` 日志。交付或本轮结束时不需要再折叠。
4. 自动重建（C2）沿用 `should_auto_build`；Task 6 已经让改参数时全部阶段变回未通过，所以 build 会从 s1 起重新验证。
5. 纯文字结束前的兜底 build（`should_build_before_reply`）：分阶段时再加一个条件——当前阶段 `stage_ready`，或者计划已全部通过；否则不兜底。
6. 交付：`export_version` 改用 `final_checks(ws)`（旧流程下它原样返回全部检查）；分阶段时把 `gate=toolbox.last_gate` 传给 `delivery_text`，`new_version` 带上 `extra_json={"gate": gate.to_dict(), "plan": ws.plan.to_list()}` 和 `stages_src=toolbox.stage_dir`。
7. `_save` 把 `ws.plan.to_list()` 传给 `save_state`。

- [ ] **Step 1：** 写测试 `tests/test_snapshot_v2.py`：`test_snapshot_legacy_unchanged`；`test_snapshot_phases`（四种"阶段"文字各一例）；`test_snapshot_plan_lines`（`s1 底板：…… —— 已通过` / `当前` / `未开始`）；`test_snapshot_feature_header_has_stage`；`test_stage_summary_format`（一个阶段、两个阶段、后面还有阶段三种情况，逐行等于提示词文档第 4 节）。
- [ ] **Step 2：** 写测试 `tests/test_staged_loop.py`（`make_staged_agent(tmp_path, replies, runner, **config)`：`ToolBox(..., gates=Gates(mutation_check=False, visual_review=False, cases=False))`，已确认的需求单；脚本里的回复用 `scripted_call`）：
  - `test_full_two_stage_flow_delivers`：回复 1 `set_plan`；回复 2 `set_checks(s1)`、`upsert_feature`、`build`；回复 3 `set_checks(s2)`、`upsert_feature`、`build` → `turn.kind == "delivered"`，`llm_calls == 3`，版本目录里有 `gate.json`、`plan.json`、`stages/s1.stl`、`stages/s2.stl`，会话目录里有 `plan.json`。
  - `test_passed_stage_is_folded`：第 3 次调用模型时，消息里有一条以 `【阶段已通过（程序生成）】s1` 开头的 user 消息，没有任何 `role == "tool"` 的消息，前两条仍是 system 和带快照的 user。
  - `test_fold_keeps_prefix_stable_inside_a_stage`：同一阶段里连续两次调用模型，后一次的消息以前一次的全部消息开头。
  - `test_stage_failure_limit_ends_turn`：s1 连续 3 次不通过 → `failed`；`test_failure_count_is_per_stage`：s1 失败 2 次后通过，s2 再失败 2 次，本轮不结束。
  - `test_stage_tool_cap`（`max_tool_calls_per_stage=4`）：文字等于 7.4 的原文；`test_total_tool_cap`（`max_tool_calls_total=5`）。
  - `test_continue_after_stage_cap`（Review Focus 5）：上一条之后用户说"继续" → 新一轮第一条 user 消息的快照里有 `计划：` 和 `建模中（当前阶段 s1）`，本轮还能再调用 4 次工具。
  - `test_warning_counts_stage_calls`。
  - `test_param_change_reverifies_all_stages`：交付后只改参数 → 程序自动 build，`StageRunner.calls` 依次是 s1、s2，交付 v2，`llm_calls == 1`。
  - `test_gate_failure_goes_back_to_model`（`mutation_check=True`，假 `run_job` 让某个参数 `unconstrained`）：build 的返回里有 `final_gate`，本轮没交付；模型补检查后再 build → 交付。
  - `test_delivery_text_lists_unbuildable`（Review Focus 3）：交付文字里有提示词文档第 9 节第二种写法的那一行。
  - `test_turn_end_safety_build_only_when_ready`：当前阶段只有检查没有特征时，模型用纯文字结束 → 不自动 build，`kind == "reply"`。
  - `test_logs_have_stage_and_gate`。
  - `test_legacy_agent_is_unchanged`：`ToolBox` 不带 `gates` 时，系统提示词是旧的，日志里没有 `stage`、`gate`，会话目录里没有 `plan.json`。
- [ ] **Step 3：** 运行，确认失败；实现。`loop.py` 超过 300 行时，把分阶段特有的部分（计数、折叠、日志）放进新文件 `cad_agent/agent/staged_hooks.py`，由 `loop.py` 调用。
- [ ] **Step 4：** 运行全部测试（`tests/test_loop.py`、`tests/test_session.py`、`tests/test_web.py` 原样通过），提交：`feat: 主循环接入分阶段流程`。

---

### Task 11：案例库

**Files：** Create `cad_agent/cases.py`、`tests/test_cases.py`；Modify `cad_agent/agent/loop.py`、`pyproject.toml`

**Interfaces：**
- Produces：
  ```python
  BUILTIN_DIR = Path(__file__).parent / "case_data"
  TAG_BONUS = 0.15
  THRESHOLD = 0.10
  MAX_CASE_CHARS = 3000
  class CaseError(ValueError): ...
  @dataclass(frozen=True)
  class Case:
      id: str                 # 目录名
      title: str
      tags: tuple[str, ...]
      request: str            # 一句话需求
      brief: dict             # Brief.to_dict() 的格式
      plan: list[dict]        # [{"title", "done_when"}]
      features: list[dict]    # [{"slug", "role", "stage", "code"}]
      checks: list[dict]      # 每条带 "stage"
      builtin: bool
  def load_case(path: Path, builtin: bool) -> Case: ...                          # path 是案例目录；格式不对抛 CaseError
  def load_cases(user_dir: Path | None) -> tuple[list[Case], list[str]]: ...     # 自带的在前；读不了的案例跳过，原因放进第二项
  def score(query: str, case: Case) -> float: ...
  def pick_cases(brief: Brief, cases: list[Case], k: int = 2) -> list[Case]: ...
  def render_cases(cases: list[Case]) -> str: ...                                # 提示词文档第 5 节；空表返回 ""
  def save_case(user_dir: Path, title: str, tags: list[str], ws: Workspace) -> Path: ...
  def case_workspace(case: Case) -> Workspace: ...                               # 需求单已确认、计划各阶段未通过
  ```
  - `case.yaml` 的键：`title`、`tags`、`request`、`brief`、`plan`、`features`、`checks`。
  - `score`：把两边的文字去掉空白和标点后取相邻两个字符的组合，算交集大小除以并集大小；`query` 是需求单的零件名、用途、各组成部分连起来，案例这边是标题、需求、需求单里的各组成部分连起来；再加上 `TAG_BONUS ×（在 query 里原样出现的标签个数）`。
  - `pick_cases`：分数不低于 `THRESHOLD` 的，按分数从高到低取前 `k` 个；分数相同时自带的在前、再按 id。
  - `save_case`：目录名是 `user-<时间戳>`（已存在就加 `-2`、`-3`）；标题不能为空；`ws` 必须有计划且全部通过，否则抛 `CaseError`。
  - `Agent.__init__` 加一个仅限关键字的参数 `cases: list[Case] | None = None`。分阶段、`gates.cases` 为真、本轮开始时需求单可以建模且 `ws.plan is None` 时：`picked = pick_cases(ws.brief, cases or [])`，非空就把 `render_cases(picked)` 接在快照后面（中间空一行），并写日志 `{"kind": "cases", "ids": [...]}`。
  - `pyproject.toml` 的 `package-data` 加 `"case_data/*/case.yaml"`。

- [ ] **Step 1：** 写测试 `tests/test_cases.py`（案例用测试里临时写出的 YAML）：
  - `test_load_case_round_trip`、`test_load_case_errors`（缺键、`plan` 为空、特征的 `stage` 不在计划里 → `CaseError`，信息里有文件位置）。
  - `test_load_cases_skips_bad_ones_and_reports`。
  - `test_score_orders_similar_first`：需求是"法兰盘，圆盘上一圈螺栓孔"时，标题"法兰盖"、标签 `["法兰", "螺栓孔"]` 的案例分数高于标题"手机支架"的案例；完全无关的案例分数低于 `THRESHOLD`。
  - `test_score_tag_bonus`：其他相同，多命中一个标签就多 0.15。
  - `test_pick_cases_limit_and_threshold`。
  - `test_render_cases_format_and_truncation`：逐行等于提示词文档第 5 节；特征代码很长时一段不超过 3000 字符，以 `…（后面的内容省略）` 结尾；两个案例时标题行只出现一次。
  - `test_save_case_and_reload`、`test_save_case_requires_finished_plan`。
  - `test_case_workspace`。
  - `test_cases_are_injected_at_planning`（`tests/test_staged_loop.py` 里）：规划那一轮的 user 消息里，快照和 `【用户说】` 之间有 `【参考案例`；下一轮（已有计划）没有；`gates.cases` 为假时没有；日志里有 `cases`。
- [ ] **Step 2：** 运行，确认失败；实现；运行全部测试，提交：`feat: 案例库的读取、检索和保存`。

---

### Task 12：参数直改（内核部分）

**Files：** Create `cad_agent/agent/manual.py`、`tests/test_manual.py`

**Interfaces：**
- Consumes：`advance`（Task 7）、`run_final_gate`（Task 8，只用它的缺检查那一项）、`export_version`（Task 10）。
- Produces：
  ```python
  @dataclass
  class ManualResult:
      ok: bool
      text: str                       # 给界面显示的一句话
      version_dir: Path | None = None
      changes: list[str] = field(default_factory=list)
      failed_checks: list[dict] = field(default_factory=list)   # 和 build 返回里的 failed_checks 相同格式
      error: dict | None = None
  def apply_params(agent: Agent, values: dict[str, float]) -> ManualResult: ...
  ```

规则：
- 只在分阶段、计划全部通过、已经有至少一个版本时可用；否则 `ok=False`，`text` 是 `现在还不能直接改参数：要先交付过一个版本。`
- `values` 里有不认识的参数名、不是有限的数、和现在的数值全都相同：`ok=False`，各给一句中文，什么都不改。
- 先备份需求单和各阶段的通过状态。把改过的参数写进需求单（单位和备注不变，来源改成 `user`），全部阶段变回未通过，调用 `advance`（带 `stl_dir`）。
- 没有走到 `complete`，或者缺检查：恢复备份，`ok=False`，`text` 用提示词文档第 9 节最后一个 text 块，`failed_checks` 和 `error` 取自停下的那个阶段。
- 走到 `complete` 且不缺检查：不做扰动验证；`export_version`，变化行按提示词文档第 9 节"手动修改参数"的格式；`ok=True`，`text` 是 `已按新的参数重建，存为 <版本名>。`
- 两种结果都写一条日志 `{"kind": "manual", "values", "ok", "version"}`。全程不调用模型。

- [ ] **Step 1：** 写测试 `tests/test_manual.py`：`test_not_available_before_first_delivery`、`test_rejects_unknown_param_nan_and_no_change`、`test_success_creates_version`（`changes == ["手动修改参数：phone_w 78 → 90（mm）"]`，新版本目录里 `brief.json` 的数值是 90、来源是 `user`，模型没有被调用）、`test_failure_restores_everything`（需求单数值、各阶段通过状态、版本数都和之前一样，`failed_checks` 非空）、`test_all_stages_are_reverified`、`test_manual_is_logged`。
- [ ] **Step 2：** 运行，确认失败；实现；运行全部测试，提交：`feat: 不经过模型直接改参数`。

---

### Task 13：六个新评测任务

**Files：** Create `benchmarks/tasks/bearing_block.yaml`、`battery_box.yaml`、`spur_gear.yaml`、`heatsink.yaml`、`tee_fitting.yaml`、`bracket_arm.yaml`、`tests/test_benchmark_references_v2.py`（标记 `sca`）、`tests/test_benchmarks_v2.py`；Modify `benchmarks/run.py`

**Interfaces：**
- Produces：`benchmarks/run.py` 里 `MEDIUM_TASKS = ["bearing_block", "battery_box", "spur_gear"]`、`HARD_TASKS = ["heatsink", "tee_fitting", "bracket_arm"]`；`TASK_SETS` 加三项：`"medium"`、`"hard"`、`"v2"`（开发 3 个 + 留出 2 个 + 这 6 个，按这个顺序）。`"dev"`、`"holdout"`、`"all"` 不变。`main` 里造智能体时把 `gates=config.gates` 传给 `ToolBox`，并把 `load_cases(config.cases_dir)[0]` 传给 `Agent`。

所有任务的坐标约定：底面贴 z=0，xy 以原点为中心，最长的水平方向沿 x。YAML 的格式和现有任务相同；`max_user_turns` 都写 14。bbox 检查的 `tol` 除特别写明外都是 0.5。点检查的 id 按下面列出的顺序编成 `in-1`、`in-2`……和 `out-1`、`out-2`……。每个 YAML 的注释里写明点是怎么选的。

**bearing_block（轴承座）** `initial`：`做一个轴承座`
`hidden_spec`：
```text
- 底板 100×40×10 mm（长×宽×厚），四个竖边倒圆角 R5。
- 底板两端各一个 φ9 的安装通孔，孔心在长度方向离中心 38 mm、宽度方向居中。
- 底板中间上方是一个横放的圆柱座：轴线沿宽度方向，轴心离桌面 40 mm，外径 50 mm，沿轴线方向长 40 mm（和底板同宽）。
- 圆柱座和底板之间是一块实心的支撑块：宽 50 mm（和圆柱外径相同），沿轴线方向长 40 mm，从底板顶面一直到轴心的高度。
- 轴孔 φ25，沿轴线方向贯通。
- 圆柱座顶部正中有一个 φ4 的竖直油孔，从顶面一直打到轴孔。
```
`modifications`：`轴孔直径改成 30 mm`
- `after_initial`：size-x 100、size-y 40、size-z 65；在材料里：[0,0,5]、[45,0,5]、[10,0,60]、[20,0,20]、[48,18,5]、[13.5,0,40]；不在材料里：[0,0,40]、[38,0,5]、[0,0,60]、[40,0,30]、[49.5,19.5,5]。
- `after_mod_1`：尺寸同上；在材料里：[0,0,5]、[45,0,5]、[10,0,60]、[20,0,20]、[48,18,5]、[16.5,0,40]；不在材料里：[0,0,40]、[38,0,5]、[0,0,60]、[40,0,30]、[49.5,19.5,5]、[13.5,0,40]。
- 没改的旧模型对 `after_mod_1` 恰好不通过：`out-6`。

**battery_box（电池盒）** `initial`：`做一个装两节电池的小盒子`
`hidden_spec`：
```text
- 外形 90×60×25 mm（长×宽×高），上面敞口，不做盖子。四面侧壁厚 2 mm，底厚 2 mm。不要圆角。
- 盒子正中间有一块隔板，把内腔沿长度方向分成两格：隔板厚 2 mm，和宽度方向平行，两端连到侧壁，高度到盒口。
- 四个内角各有一根 φ8 的安装柱：柱心离相邻的两面内壁各 4 mm，从盒底内表面往上高 20 mm。每根柱子顶面正中有一个 φ3 的盲孔，深 10 mm。
- 长度方向正的那一端（+x 侧）的侧壁正中有一个走线缺口：宽 10 mm，从盒口往下深 8 mm，穿透壁厚。
```
`modifications`：`安装柱的高度改成 15 mm，孔深不变`
- `after_initial`：size-x 90、size-y 60、size-z 25；在材料里：[0,0,1]、[44,0,10]、[0,10,12]、[39,24,10]、[41.5,24,20]、[-44,0,20]；不在材料里：[20,0,12]、[44,0,20]、[39,24,18]、[-20,0,12]。
- `after_mod_1`：尺寸同上；在材料里：[0,0,1]、[44,0,10]、[0,10,12]、[39,24,5]、[41.5,24,15]、[-44,0,20]；不在材料里：[20,0,12]、[44,0,20]、[39,24,10]、[41.5,24,20]、[-20,0,12]。
- 没改的旧模型对 `after_mod_1` 恰好不通过：`out-3`、`out-4`。

**spur_gear（直齿轮）** `initial`：`做一个直齿轮`
`hidden_spec`：
```text
- 直齿圆柱齿轮：模数 2，齿数 30，齿宽 12 mm。轴线竖直，齿轮的一个端面贴着桌面。
- 朝上的一面有轮毂：外径 24 mm，比齿轮端面再高出 8 mm，所以总厚 20 mm。
- 轴孔 φ10，贯通全厚。
- 轴孔上有一个键槽：宽 3 mm，开在 +y 方向，槽底到孔心 6.4 mm，贯通全厚。
- 齿轮盘上有 6 个 φ8 的减重孔，均匀分布在 φ40 的圆上，贯通齿宽，其中一个孔在 +x 方向上。
```
`modifications`：`减重孔改成 4 个`
- `after_initial`：size-x 64（tol 1.0）、size-y 64（tol 1.0）、size-z 20；在材料里：[8,0,6]、[10,0,16]、[26,0,6]、[0,7.5,6]、[17.32,10,6]、[0,20,6]；不在材料里：[0,0,10]、[20,0,6]、[0,5.8,10]、[15,0,16]、[10,17.32,6]。
- `after_mod_1`：尺寸同上；在材料里：[8,0,6]、[10,0,16]、[26,0,6]、[0,7.5,6]、[10,17.32,6]、[17.32,10,6]；不在材料里：[0,0,10]、[20,0,6]、[0,5.8,10]、[15,0,16]、[0,20,6]。
- 没改的旧模型对 `after_mod_1` 恰好不通过：`in-5`、`out-5`。
- 齿顶圆直径按 模数 ×（齿数 + 2）= 64 算。Task 1 实测的标准件齿顶圆和 64 相差超过 1 时，记偏离，把两个 64 改成实测值取整。

**heatsink（散热器）** `initial`：`做一个铝散热器`
`hidden_spec`：
```text
- 底板 80×60×6 mm（长×宽×厚），四个竖边倒圆角 R3。
- 底板上面立着 9 片鳍片：每片厚 2 mm，沿宽度方向长 44 mm（居中），高 24 mm（顶端离桌面 30 mm）。鳍片沿长度方向均匀排开，最外面两片的中心离底板中心 36 mm。
- 四个角上各一个 φ4.5 的安装通孔，孔心离中心：长度方向 34 mm，宽度方向 26 mm。
- 四根 φ6 的风扇安装柱，立在底板顶面上，顶端和鳍片一样高；柱心离中心：长度方向 20 mm，宽度方向 26 mm。每根柱子顶面正中有一个 φ2.5 的盲孔，深 8 mm。
```
`modifications`：`鳍片改成 11 片，最外面两片的位置不变`
- `after_initial`：size-x 80、size-y 60、size-z 30；`fin-tops`：`count`，`kind: faces`，`where: [["geom.type","==","PLANE"],["geom.normal.z",">=",0.99],["geom.center.z",">=",29.9]]`，`expected: 13`；在材料里：[0,0,3]、[0,0,20]、[9,0,20]、[20,26,20]、[38.5,28.5,3]、[36,0,20]；不在材料里：[4.5,0,20]、[0,25,20]、[20,26,26]、[34,26,3]、[39.5,29.5,3]、[38.5,0,20]。
- `after_mod_1`：尺寸同上；`fin-tops` 的 `expected: 15`；在材料里：[0,0,3]、[0,0,20]、[7.2,0,20]、[20,26,20]、[38.5,28.5,3]、[36,0,20]；不在材料里：[4.5,0,20]、[0,25,20]、[20,26,26]、[34,26,3]、[39.5,29.5,3]、[9,0,20]。
- 没改的旧模型对 `after_mod_1` 恰好不通过：`fin-tops`、`in-3`、`out-6`。

**tee_fitting（三通管接头）** `initial`：`做一个带法兰的三通管接头`
`hidden_spec`：
```text
- 主管水平放，沿长度方向：外径 40 mm，内径 30 mm，全长 120 mm，轴线离桌面 35 mm。
- 主管两端各有一个法兰：外径 70 mm，厚 8 mm，算在 120 mm 全长之内。每个法兰上 4 个 φ7 的螺栓通孔，均匀分布在 φ56 的圆上，孔在斜 45° 的四个方向上。
- 支管从主管正中间竖直向上伸出：外径 30 mm，内径 20 mm，顶端离桌面 85 mm。
- 支管顶端有一个法兰：外径 56 mm，厚 8 mm（顶面就是支管顶端）。上面 4 个 φ6 的螺栓通孔，均匀分布在 φ44 的圆上，孔在斜 45° 的四个方向上。
- 主管的内孔全长贯通；支管的内孔从顶端一直通到主管的内孔里。
```
`modifications`：`支管的内径改成 24 mm`
- `after_initial`：size-x 120、size-y 70、size-z 85；在材料里：[0,17.5,35]、[12.5,0,60]、[58,30,35]、[20,0,81]、[-58,-30,35]、[11,0,60]；不在材料里：[0,0,35]、[0,0,60]、[58,19.8,54.8]、[15.56,15.56,81]、[30,0,60]、[0,0,52]。
- `after_mod_1`：尺寸同上；在材料里：[0,17.5,35]、[13.5,0,60]、[58,30,35]、[20,0,81]、[-58,-30,35]；不在材料里：[0,0,35]、[0,0,60]、[58,19.8,54.8]、[15.56,15.56,81]、[30,0,60]、[0,0,52]、[11,0,60]。
- 没改的旧模型对 `after_mod_1` 恰好不通过：`out-7`。

**bracket_arm（支架臂）** `initial`：`做一个 L 形的支架臂`
`hidden_spec`：
```text
- 从侧面看是一个 L 形：底板长 120 mm、厚 8 mm；左端有一根立臂，宽 20 mm（沿长度方向），从桌面算起总高 60 mm，立臂的外侧面和底板的左端面平齐。整个 L 形的宽度是 30 mm。
- 立臂上有一个 φ12 的耳孔：轴线沿长度方向，穿透立臂，在宽度方向居中，孔心离立臂顶端 15 mm。
- 底板上有一个矩形的减重槽，贯穿底板厚度：沿长度方向从底板中心到中心右边 30 mm，宽 12 mm（居中）。
- 底板上有两个沉头孔，从顶面往下：通孔 φ5，沉头 φ10、深 3 mm。一个孔心在中心右边 48 mm、宽度方向居中；另一个在中心左边 25 mm、宽度方向偏 +y 9 mm。
- 立臂和底板的内角有一块三角形加强筋：厚 6 mm（宽度方向居中），贴着底板顶面的那条边长 30 mm，贴着立臂的那条边高 30 mm。
- 底板右端的上棱倒角 2 mm。
```
`modifications`：`立臂总高改成 70 mm，耳孔离顶端的距离不变`
- `after_initial`：size-x 120、size-y 30、size-z 60；在材料里：[50,10,4]、[48,4,3]、[15,10,4]、[-50,0,20]、[-50,0,55]、[-35,0,12]、[58.5,0,6.5]、[-50,10,45]；不在材料里：[48,0,4]、[48,4,7]、[15,0,4]、[-50,0,45]、[-35,5,12]、[-20,0,30]、[59.5,0,7.5]、[-25,9,4]。
- `after_mod_1`：size-x 120、size-y 30、size-z 70；在材料里：[50,10,4]、[48,4,3]、[15,10,4]、[-50,0,20]、[-50,0,45]、[-50,0,65]、[-35,0,12]、[58.5,0,6.5]；不在材料里：[48,0,4]、[48,4,7]、[15,0,4]、[-50,0,55]、[-35,5,12]、[-20,0,30]、[59.5,0,7.5]、[-25,9,4]。
- 没改的旧模型对 `after_mod_1` 恰好不通过：`size-z`、`in-5`、`in-6`、`out-4`。

- [ ] **Step 1：** 写测试 `tests/test_benchmarks_v2.py`：`test_new_task_sets`（三个新集合的内容和顺序；`dev`、`holdout`、`all` 和原来一样）；`test_new_tasks_load`（6 个都能 `load_task`，`max_user_turns == 14`，各有一条修改）；每个任务一条 `test_<任务>_acceptance_numbers`，断言 bbox 的期望值、`fin-tops` 的期望值、点检查的个数和上面列的相同。
- [ ] **Step 2：** 写测试 `tests/test_benchmark_references_v2.py`。每个任务一个函数，接收修改用的那个参数值，返回一个 `Workspace`：已确认的需求单（参数全部 `source="user"`）、2 到 5 个阶段的计划、归属到阶段的特征、带 `stage` 的检查。参数化两条测试：
  - `test_reference_passes_all_gates_and_acceptance(task_id, stage, build)`：用真实 `run_job` 调用 `advance` 直到 `reason == "complete"`；`run_final_gate(..., Gates())` 的 `passed` 为真且没有 `unconstrained`；再用验收检查跑一次，全部通过。
  - `test_acceptance_catches_an_unmodified_model(task_id, failing)`：初始模型对 `after_mod_1`，不通过的检查 id 集合等于上面各任务写的那个集合。
- [ ] **Step 3：** 运行，确认失败。
- [ ] **Step 4：** 写 6 个 YAML，改 `benchmarks/run.py`。
- [ ] **Step 5：** 写 6 个标准答案模型，SCA 的写法只用笔记里实测过的（草图轮廓、抽壳、标准件齿轮来自 Task 1）。某个验收数字和标准答案对不上时：先核对坐标约定和上面的需求文字；确认是本计划的数字算错了，才记偏离、改数字，并在偏离记录里写出手算过程。某个零件的标准答案确实建不出来时，停下来问用户换哪个零件。
- [ ] **Step 6：** 运行全部测试，提交：`feat: 六个中等和困难的评测任务`。

---

### Task 14：八个自带案例

**Files：** Create `cad_agent/case_data/<id>/case.yaml` 共 8 个、`tests/test_builtin_cases.py`（标记 `sca`）

**Interfaces：**
- Consumes：`load_cases`、`case_workspace`（Task 11）、`advance`、`run_final_gate`。
- Produces：8 个案例，id 和内容：

| id | 零件 | 要示范的做法 |
|---|---|---|
| `mounting-plate` | 安装板：矩形板、四角孔、中间一个大孔 | 拉伸、先做一个孔再线性阵列 |
| `pulley` | V 带轮：带 V 形槽的轮子和轴孔 | 画截面旋转成形 |
| `tray` | 收纳盒：敞口薄壁盒、外竖边圆角 | 抽壳，圆角放在抽壳前还是后 |
| `motor-mount` | 电机座：底板、带大孔的立板、两侧三角筋 | 多次布尔加、筋、位置关系 |
| `cam-plate` | 凸轮板：由直线和圆弧围成的异形板，带轴孔 | 草图轮廓拉伸 |
| `gear-rack` | 齿条：标准件直齿条加两个安装孔 | 标准件 |
| `pull-handle` | 拉手：圆截面沿"直—弯—直"路径的弯管，两端带安装座 | 扫掠 |
| `knob` | 旋钮：圆柱、一圈防滑槽、顶边圆角、底边倒角、轴孔 | 圆周阵列，圆角和倒角的先后 |

每个案例的要求：尺寸自定，写成 3 到 6 个参数，全部 `source: user`；2 到 4 个阶段；每个阶段至少 2 条检查；有两个以上组成部分的写 `relations`；`tags` 3 到 5 个，写零件类别和用到的做法（如 `抽壳`、`圆周阵列`）；`request` 是一句用户口吻的话。这些零件都不能和 11 个评测任务是同一个零件。

- [ ] **Step 1：** 写测试 `tests/test_builtin_cases.py`：
  - `test_there_are_eight_builtin_cases`：`load_cases(None)` 没有问题条目，id 集合等于上表。
  - `test_case_shape(case)`（参数化）：参数 3 到 6 个且都是用户参数；阶段 2 到 4 个；每个阶段至少 2 条检查；标签 3 到 5 个。
  - `test_case_builds_and_passes_gates(case)`（参数化）：`case_workspace` 后用真实 `run_job` 调用 `advance` 到 `complete`；`run_final_gate(..., Gates())` 的 `passed` 为真。
  - `test_builtin_cases_are_not_benchmark_tasks`：案例 id 和标题里不出现 11 个评测任务的 id 和零件名（手机支架、法兰盘、L 形、电路板、阶梯轴、轴承座、电池盒、直齿轮、散热器、三通、支架臂）。
- [ ] **Step 2：** 运行，确认失败。
- [ ] **Step 3：** 逐个写案例。每写完一个就跑它那两条参数化测试。扰动验证报 `unconstrained` 时改检查，不改测试。
- [ ] **Step 4：** 运行全部测试，提交：`feat: 八个自带案例`。

---

### Task 15：接到入口上，并做一次真实沙盒的全流程

**Files：** Modify `cad_agent/cli.py`、`cad_agent/web/__main__.py`、`cad_agent/web/events.py`、`README.md`；Test `tests/test_staged_e2e.py`（标记 `sca`）、`tests/test_cli.py`、`tests/test_web.py`（只加测试）

**Interfaces：**
- Produces：
  - `cli.build_agent(config)`：`ToolBox(..., gates=config.gates)`；`Agent(..., cases=load_cases(config.cases_dir)[0])`；读案例时的问题条目写进启动日志。
  - `web/__main__.py` 的 `build_live_agent` 同样处理。
  - `web/events.py` 的 `describe_event`：`stage` → `阶段 <id>（<title>）通过，检查 <n> 条`；`gate` → 通过时 `终检通过`，否则 `终检没通过：<原因>`（缺检查或列出参数名）；`cases` → `参考了 <n> 个相似案例`；`manual` → `手动修改了参数`；`_TOOL_LABEL` 加 `set_plan: 制定计划`、`probe: 试验代码`、`read_reference: 查阅文档`。现有网页不做别的改动，只保证新流程下不报错、进度文字看得懂。

- [ ] **Step 1：** 写测试：
  - `tests/test_cli.py::test_build_agent_passes_gates_and_cases`、`test_build_agent_legacy_when_staged_off`（配置里 `staged = false` 时 `agent.toolbox.gates.staged` 为假，系统提示词是旧的）。
  - `tests/test_web.py::test_describe_new_events`（上面每种事件各一例）、`test_web_state_with_staged_session`（用分阶段的假会话走一遍，`/api/state` 返回 200，`activity` 里有阶段通过的文字）。
  - `tests/test_staged_e2e.py::test_real_staged_flow`：`ScriptedLLM` 的剧本是"带孔的板"——`set_plan` 两个阶段（板；孔）、每个阶段先检查后特征再 build；用真实 `run_job`，`Gates(visual_review=False, cases=False)`。断言：交付 `v1`，版本目录里有 `model.step`、`view.png`、`model.stl`、`gate.json`、`stages/s1.stl`、`stages/s2.stl`；`gate.json` 里每个用户参数都是 `constrained`。接着调用 `apply_params` 把孔径改大 → 交付 `v2`，模型调用次数没有增加。
- [ ] **Step 2：** 运行，确认失败；实现。
- [ ] **Step 3：** README 的"核心思路"之后加一节"分阶段建模与终检"（流程图、四个开关、怎么关掉）；"评测"一节补 `--set medium|hard|v2`；写明"第二版的成功率要等付费评测之后才有数字"。`CLAUDE.md` 不在这里改（由写计划的人改）。
- [ ] **Step 4：** 手动跑一遍：`.venv\Scripts\python -m cad_agent --config config.toml` 在没有 key 时仍然提示设置环境变量并返回 1；有（假的）key 时能启动，启动日志里有读到的案例个数。不调用真实模型。
- [ ] **Step 5：** 运行全部测试，提交：`feat: 命令行和网页用上分阶段内核`。

---

## 做完之后

- `docs/progress.md` 最后写一段"计划 1 小结"：测试总数、六个新任务和八个案例是否都按计划的数字通过、记了哪些偏离。
- 不要运行 `benchmarks.run`（那会调用真实模型）。付费评测由用户决定什么时候做。
