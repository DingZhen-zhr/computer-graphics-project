# 3.0 · 计划 2：多零件与运动（内核）· 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal：** 让内核能做由多个零件组成、能动的产品：需求单写清零件、连接和运动；一个零件一个零件地做；装起来检查对齐和穿模；每个关节从头到尾取样检查碰撞；交付每个零件和整个产品的参数化源文件与 STEP；同时让零件默认有设计感，并为界面准备好数据。

**Architecture：** 新代码放在 `cad_agent/product/`。多零件时，工作区里"当前零件"的特征、检查、计划，在切换零件时整体换进换出，所以第二版的分阶段工具和 build 一行都不用改。装配由模型写成声明（连接点、配合、关节、联动），我们的代码负责：把配合算成摆放位置、算各关节在各取样位置的姿态（纯 Python，可单元测试）、在沙盒子进程里用 SCA 量穿模和对齐、导出产品。界面播放的运动数据和碰撞检查用的是同一份姿态。

**Tech Stack：** 不新增依赖。SCA 2.2.7 的装配、约束、材料、导出功能；numpy（SCA 已经依赖它）。

**Spec：** `docs/superpowers/specs/2026-11-20-datum-v3-design.md`（第 5、6 节，第 7.6、7.7、7.10 节里涉及内核的部分，第 8.1 节的三个多零件任务）。

**原文照抄：** `docs/superpowers/plans/2026-11-20-datum-2-multipart-prompts.md`（下面简称"提示词文档"）。

**前置：** 计划 1 完成。

## Global Constraints

- 前几版计划的规矩全部继续有效（见 `CLAUDE.md`）。
- **不调用任何真实的模型接口。** 全部测试用 `ScriptedLLM` 和沙盒。
- **单零件的行为一个字不变**：需求单里没有 `parts`（或少于 2 个）时，走第二版的流程；单零件 notebook 的文本、工具返回、日志都和现在相同。
- SCA 的写法只用 `docs/sca-api-notes.md` 里实测过的；Task 1 探测的结果先写进笔记再用。
- 坐标约定：每个零件在它自己的坐标里建模（底面贴 z=0、大致以原点为中心）；装好后的坐标是 ground 零件的坐标。三维变换一律用 4×4 矩阵，按行展开成 16 个数存储。
- 默认值：每个关节取样 24 个位置（配置项 `motion_samples`，不少于 12）；"接触"配对允许的重叠体积 = Task 1 实测值的 2 倍，向上取到 0.5 的整数倍，写成常量 `CONTACT_TOL_MM3`；普通"不穿模"的容差 0.01 立方毫米；同轴、贴平的距离容差 0.05 毫米、角度容差 0.2 度。
- 上限：多零件时，每轮工具调用总上限 = 200 × 零件数 + 100（配置项 `max_tool_calls_total` 作为每个零件的份额，装配额外 100）。每一步失败 3 次、每步工具调用 25 次的规则不变。
- 文件不超过 300 行；前端文件本计划不碰（界面是计划 3）。
- **要改的旧测试**：见下面的清单，清单之外一律不动。
- 偏离记录接着计划 1 的编号。每个任务收尾：全部测试通过 → 提交 → `docs/progress.md` 追加一段（标题写"3.0 计划 2 Task N"）。

## 要改的旧测试

| 测试 | 怎么改 | 原因 |
|---|---|---|
| `tests/test_staged_tools.py::test_specs_v2_are_verbatim` | update_brief 改为对照本计划提示词文档第 3 节；工具总数从 12 改为 17，末尾 5 个对照第 3 节 | 多零件要在需求单里写零件和运动 |
| `tests/test_staged_extras.py::test_full_system_prompt_v2` | 分阶段的系统提示词由 4 段变成 5 段，第 2 段是 `system_multipart.md` | 提示词文档第 1 节 |
| `tests/test_check_spec.py` 里断言 `CheckResult.to_dict()` 等于某个字典的测试 | 不改：`selected` 为空时不出现在 `to_dict()` 里（Task 12） | — |
| `tests/test_review.py::test_reviewer_prompt_is_verbatim`、`test_review_targets` | 见 Task 11 | 看图审查多问"整体做工" |

## Review Focus

1. 模型把两个真撞上的零件的连接点写成同轴、想让它们"接触"豁免：只有程序从"转动关节的轴和孔""齿轮联动"推出来的配对才豁免，其余照常算穿模。→ Task 8 `test_contact_pairs_only_from_joints_and_gears`
2. 连接点的 where 选中了 0 个或 3 个面：报提示词文档 4.2 的原文，不猜一个用。→ Task 7 `test_connector_must_select_exactly_one`
3. 装配关系里有零件没连上，或者 A 连 B、B 又连 A：在 `set_assembly` 时就报错，不等到运行。→ Task 3 `test_mates_must_form_a_tree`
4. 关节范围写反（110 到 0）或者范围是 0：前者按从小到大处理并在返回里说明，后者报错。→ Task 3 `test_joint_range_normalized_and_zero_rejected`
5. 一个零件做完、切到下一个零件之后，用户回头说"第一个零件的孔大一点"：`select_part` 回去改，改完那个零件从它被改的步骤重新验证，装配和运动检查也要重跑，不能沿用旧结果。→ Task 10 `test_editing_finished_part_invalidates_assembly`
6. 运动取样时某个位置 SCA 出错（比如布尔运算失败）：记为这个位置"没量成"，当作没通过，返回里写明是哪个位置，不吞掉。→ Task 7 `test_sample_error_is_reported_not_ignored`

---

## 文件结构

```
scripts/probe_assembly.py               装配相关的探测（Task 1）
docs/sca-api-notes.md                   新增第 23–27 节（Task 1）
cad_agent/brief.py                      parts、motions、参数的 part（Task 2）
cad_agent/product/__init__.py
cad_agent/product/materials.py          材料表（Task 3）
cad_agent/product/spec.py               零件、连接点、配合、关节、联动的声明和校验（Task 3）
cad_agent/product/workspace.py          多零件工作区：切换零件（Task 4）
cad_agent/product/render.py             零件 notebook、装配 notebook（Task 5）
cad_agent/product/kinematics.py         摆放、关节姿态、取样、炸开方向，纯 Python（Task 6）
cad_agent/sandbox/runner_assembly.py    子进程里装配、量、导出（Task 7）
cad_agent/sandbox/execute.py            run_assembly（Task 7）
cad_agent/product/checks.py             装配和运动的检查（Task 8）
cad_agent/product/tools.py              5 个新工具（Task 9）
cad_agent/product/flow.py               零件做完、换下一个、装配、产品终检（Task 10）
cad_agent/product/delivery.py           多零件的版本导出（Task 10）
cad_agent/agent/prompts/system_multipart.md   （Task 11）
cad_agent/checks/engine.py  spec.py     检查结果的 selected（Task 12）
cad_agent/product/preview.py            只生成模型不检查的预览（Task 12）
cad_agent/agent/manual.py               多零件的参数直改（Task 12）
cad_agent/desk/view.py  events          给界面的状态（Task 13）
benchmarks/tasks/toolbox.yaml  drawer_cabinet.yaml  gear_pair.yaml（Task 14）
benchmarks/assembly_accept.py           多零件验收（Task 14）
cad_agent/case_data/<3 个多零件案例>/case.yaml（Task 15）
scripts/demo_script_multi.json          多零件的走查剧本（Task 16）
```

---

### Task 1：探测 SCA 的装配

**Files：** Create `scripts/probe_assembly.py`；Modify `docs/sca-api-notes.md`、`docs/sca-probe-output.txt`（追加）

本任务是探测，不写单元测试；收尾照常跑全部测试。每个实验单独 try/except，出错记下异常类型和前 300 个字符后继续。

- [ ] **Step 1：** 写探测脚本，依次做：
  1. **零件 notebook 各用自己的编号、被 `scad.use` 组装**：两个零件 notebook（编号 `body`、`lid`，各有单独的参数 cell），一个装配 notebook 用 `scad.use("body.py", ...)`、`scad.use("lid.py", ...)` 引用，并传覆盖值。记下：覆盖值要怎么传（整个参数 cell 的变量都要传）；编号写死成 `model` 时的报错原文；装配 notebook 的产品是什么类型。
  2. **把实体放到任意位置**：给一个 4×4 矩阵（先绕任意轴转、再平移），用 `rotate_shape`、`translate_shape` 组合实现；量变换前后的包围盒确认对。
  3. **重叠体积**：两个放好的实体 `intersect_rsolid` 后量体积；完全不重叠、刚好贴面、重叠 1 毫米三种情况的结果和报错；记下每次要多久。再量一次"两个包围盒不相交时直接跳过"能省多少时间。
  4. **装配与导出**：`make_assembly_rassembly`、`add_component_rassembly`、`place_component_rassembly` 摆好 3 个零件，导出整个产品的 STEP 和每个零件的 STL；`assign_material_rpart` 写颜色后导出的文件里是否带颜色。
  5. **约束驱动**：一个转动约束用 `drive_angle_degrees` 驱动到 30、60、90 度，一个滑动约束用 `drive_distance` 驱动；解出来的零件位置是否和我们自己算的矩阵一致（误差多少）。
  6. **闭环**：曲柄滑块（曲柄、连杆、滑块、机架）用 SCA 求解，在 12 个曲柄角上看约束误差，以及同一个输入两次求解是否一致。按设计文档第 5.7 节第 4 条的标准下结论。
  7. **齿轮接触**：模数 2、齿数 20 和 40 的两个标准件直齿轮，按中心距 60 装好，量重叠体积；把其中一个转半个齿再量。
  8. **连接点的几何**：选一个圆柱面，取它的轴线方向和中心（法向、中心的取法，以及轴线方向的正负怎么定）；选一个平面取中心和朝外的法向；选一条圆形的边取圆心和法向。
- [ ] **Step 2：** 运行脚本，把输出追加到 `docs/sca-probe-output.txt`。
- [ ] **Step 3：** 在 `docs/sca-api-notes.md` 追加五节，标题照抄：`## 23. 零件 notebook 的组装`、`## 24. 摆放与重叠体积`、`## 25. 装配、材料与导出`、`## 26. 约束驱动与闭环`、`## 27. 连接点取几何`。
- [ ] **Step 4：** 根据结果定下三个常量并写进笔记：`CONTACT_TOL_MM3`（按 Global Constraints 的规则）、默认取样数（每个关节一次碰撞检查不超过 20 秒时用 24，否则减到能做到的值但不少于 12）、闭环是否支持（只写结论，本计划不做闭环，结论是"支持"时在 `docs/progress.md` 里提醒用户可以另起计划）。
- [ ] **Step 5：** 运行全部测试，提交：`chore: 3.0 装配相关的 SCA 探测`。

如果实验 1 或 2 做不通（零件 notebook 组装不了、实体放不到任意位置），停下来问用户。

---

### Task 2：需求单写零件和运动

**Files：** Modify `cad_agent/brief.py`；Test `tests/test_brief_parts.py`

**Interfaces：**
- Produces：
  - `Param` 加字段 `part: str | None = None`；`to_dict` 里只有不为 None 时才有这个键。
  - `PartInfo`（dataclass）：`id: str`、`name: str`、`material: str`、`color: str | None`、`features: list[str]`。
  - `Brief` 加字段 `parts: list[PartInfo]`、`motions: list[str]`；`PATCH_KEYS` 末尾加 `"parts"`、`"motions"`。
  - `Brief.is_multipart() -> bool`：`len(parts) >= 2`。
  - `Brief.params_of(part_id: str | None) -> list[Param]`：`None` 返回产品参数（`part` 为 None 的）；否则返回这个零件自己的参数。
  - `Brief.missing_relations()`：多零件时，除第一个零件外，每个零件的**名字**都要在至少一条 relations 里原样出现（规则和第二版对组成部分的规则一样）。
- 校验（`apply_patch`，出错抛 `BriefError`，需求单不变）：零件编号是小写英文加下划线且不重复；材料必须是材料表里的键（Task 3 的 `MATERIALS`，这里先按提示词文档第 2 节的 7 个键校验）；颜色是 `#` 加 6 位十六进制；参数的 `part` 必须是已有的零件编号；只有 1 个零件时 `parts` 必须为空（单零件不写 parts）；改了 `parts` 或 `motions`，确认状态清零。
- `render_text()`：多零件时，在参数之后列"零件"（编号、名字、材料、组成部分）和"会动的地方"；参数按产品参数、各零件分组列出。
- `to_dict` / `from_dict`：`parts`、`motions` 为空时不写这两个键（单零件的 `brief.json` 和现在一样）。

- [ ] **Step 1：** 写测试 `tests/test_brief_parts.py`：`test_single_part_brief_unchanged`（没有 parts 时 `to_dict` 和第二版的键完全相同）；`test_parts_round_trip`；`test_part_ids_and_materials_validated`（重复编号、大写编号、不认识的材料、坏颜色各抛 `BriefError`，需求单不变）；`test_param_part_must_exist`；`test_one_part_in_parts_rejected`；`test_changing_parts_resets_confirmation`；`test_missing_relations_uses_part_names`；`test_params_of`；`test_render_text_lists_parts_and_motions`。
- [ ] **Step 2：** 运行，确认失败；实现；运行全部测试，提交：`feat: 需求单写零件、材料和运动`。

---

### Task 3：产品的声明：连接点、配合、关节、联动

**Files：** Create `cad_agent/product/__init__.py`、`cad_agent/product/materials.py`、`cad_agent/product/spec.py`、`tests/test_product_spec.py`

**Interfaces：**
- Produces（`materials.py`）：`MATERIALS: dict[str, Material]`，`Material`（frozen dataclass）：`key`、`name`、`color`、`finish`；内容照抄提示词文档第 2 节。
- Produces（`spec.py`）：
  ```python
  class ProductError(ValueError): ...          # 中文信息，直接返回给模型
  @dataclass(frozen=True)
  class Connector:
      part: str; name: str; kind: Literal["faces","edges"]; where: list[list]; offset: str | float = 0; flip: bool = False
  @dataclass(frozen=True)
  class Mate:
      id: str; fixed: str; moving: str; align: Literal["same","opposite"]; gap: str | float = 0; angle: str | float = 0
      # fixed、moving 是 "零件.连接点"
  @dataclass(frozen=True)
  class Joint:
      id: str; mate: str; type: Literal["revolute","prismatic"]; lo: str | float; hi: str | float
      direction: tuple[float, float, float] | None; label: str
  @dataclass(frozen=True)
  class Coupling:
      driver: str; driven: str; ratio: str | float; kind: Literal["gear","belt"]
  @dataclass
  class Assembly:
      ground: str; mates: list[Mate]; joints: list[Joint]; couplings: list[Coupling]
  def parse_connectors(part: str, raw: object, param_names: set[str]) -> list[Connector]: ...
  def parse_assembly(raw: object, part_ids: list[str], connectors: dict[str, list[Connector]], param_names: set[str]) -> Assembly: ...
  def mate_tree(asm: Assembly) -> dict[str, tuple[str, str]]: ...   # 每个非 ground 零件 → (它的父零件, 配合 id)
  def moving_parts(asm: Assembly, joint_id: str) -> set[str]: ...    # 这个关节动时一起动的零件（子树）
  def contact_pairs(asm: Assembly) -> set[frozenset[str]]: ...
  ```
- 规则：
  - `where` 用 `checks/spec.py` 的 `parse_where` 校验；表达式里只能用参数名。
  - `parse_assembly`：ground 必须是已有零件；每个配合两端的"零件.连接点"都要存在、两端是不同零件；除 ground 外每个零件恰好被一个配合作为 moving 端连上，从 ground 出发能走到所有零件，不成圈（`mate_tree` 能建出来）——不满足就抛 `ProductError`，信息用提示词文档 4.2"配合连成了一圈"的原文，`<具体原因>` 写哪个零件没连上或哪几个零件成了圈。
  - 关节：`mate` 必须存在；同一个配合最多一个关节；`prismatic` 必须有 `direction`（非零向量，存成单位向量）；`range` 两端可以是表达式；两端相等抛 `ProductError`；`lo > hi` 时交换，并在返回给模型的结果里加一句"关节 <id> 的范围写反了，已经按从小到大处理"。
  - 联动：driver、driven 都是已有关节且不相同；不能成圈。
  - `contact_pairs`：每个转动关节所在配合的两个零件；每个 `kind == "gear"` 的联动，两个关节各自的 moving 零件。**只有这两种**，其他一概不算。

- [ ] **Step 1：** 写测试：`test_materials_verbatim`（等于提示词文档第 2 节的 json）；`test_parse_connectors_ok_and_errors`；`test_mates_must_form_a_tree`（Review Focus 3：漏连、成圈、两端同一个零件各一例）；`test_joint_range_normalized_and_zero_rejected`（Review Focus 4）；`test_prismatic_needs_direction`；`test_couplings_validated`；`test_moving_parts_is_subtree`（盒体 → 盖子 → 提手，盖子的关节动时盖子和提手一起动）；`test_contact_pairs_only_from_joints_and_gears`（Review Focus 1：一个普通固定配合的两端不在里面）。
- [ ] **Step 2：** 运行，确认失败；实现；运行全部测试，提交：`feat: 多零件产品的连接点、配合、关节和联动`。

---

### Task 4：多零件工作区

**Files：** Create `cad_agent/product/workspace.py`、`tests/test_product_workspace.py`；Modify `cad_agent/tools.py`（`Workspace` 加字段）、`cad_agent/session.py`

**Interfaces：**
- Consumes：Task 2、3。
- Produces：
  ```python
  @dataclass
  class PartState:
      features: FeatureList; checks_raw: list[dict]; plan: Plan | None = None
      probes_used: int = 0; last_build_content: str | None = None; done: bool = False
      connectors: list[Connector] = field(default_factory=list)
  # tools.py 的 Workspace 加字段（单零件时都保持默认）：
  #   parts: dict[str, PartState] = {}     active: str | None = None
  #   assembly: Assembly | None = None     assembly_checks_raw: list[dict] = []
  #   assembly_passed: bool = False        last_assembly: "AssemblyRun | None" = None
  def select_part(ws: Workspace, part_id: str) -> None: ...   # 把 ws.features/checks_raw/plan/probes_used/last_build_content 存回 parts[active]，再换成 parts[part_id]
  def ensure_parts(ws: Workspace) -> None: ...                # 按 ws.brief.parts 建好 parts，多的删掉（只删没有特征的），active 设成第一个没做完的
  def part_param_names(ws: Workspace, part_id: str) -> list[str]: ...  # 产品参数 + 这个零件的参数
  ```
  - 切换后，第二版的分阶段工具、build、probe 照常作用于 `ws.features` 等字段，就是当前零件。
  - `Session.part_dir(part_id)`：单零件（`part_id == "main"`）返回会话目录本身（不变）；否则返回 `会话目录/parts/<part_id>`（不存在就建）。
  - `Session.save_state`：多零件时把每个零件的 features、checks、plan、connectors 写进各自的 `part_dir`，产品的装配声明写会话目录下的 `assembly.json`、装配检查写 `assembly_checks.json`；需求单仍在会话目录。`agent/resume.py` 的 `load_workspace` 能读回来。

- [ ] **Step 1：** 写测试：`test_select_part_swaps_state`（在 lid 上写的特征切回 body 后不在 body 里，再切回 lid 还在）；`test_ensure_parts_follows_brief`；`test_single_part_workspace_unchanged`；`test_part_dir_layout`；`test_save_and_resume_multipart`（存了再用 `resume` 读回，各零件的特征、计划、连接点都在）；`test_part_param_names`。
- [ ] **Step 2：** 运行，确认失败；实现；运行全部测试，提交：`feat: 多零件的工作区和会话目录`。

---

### Task 5：零件 notebook 与装配 notebook

**Files：** Create `cad_agent/product/render.py`、`tests/test_product_render.py`；Modify `cad_agent/notebook.py`（只加可选参数）

**Interfaces：**
- Produces：
  - `render_notebook(params, features, probe=None, *, notebook_id: str = "model", material: Material | None = None) -> RenderedNotebook`：默认值时输出和现在逐字相同；`notebook_id` 写进文件头和 `scad.Part(part_id=...)`；给了材料时，产品 cell 用笔记第 25 节的写法把颜色写进零件。
  - `render_part_notebook(ws: Workspace, part_id: str) -> RenderedNotebook`：用这个零件的特征和 `part_param_names` 的参数，编号是零件编号，材料来自需求单。
  - `render_assembly_notebook(ws: Workspace, placements: dict[str, list[float]]) -> str`：按笔记第 23 节的写法，用 `scad.use` 引用 `parts/<编号>.py`、传全部参数作为覆盖值，按 `placements`（每个零件的 4×4 矩阵）摆好，产品是整个装配。文件头的编号用需求单里的产品名对应的拼音以外的固定值 `product`。

- [ ] **Step 1：** 写测试：`test_default_render_is_unchanged`（随便取三个第二版测试里用过的特征列表，新旧输出逐字相同）；`test_part_notebook_uses_part_id_and_params`；`test_part_notebook_has_material_color`；`test_assembly_notebook_uses_all_parts_and_placements`；`test_assembly_notebook_passes_whole_param_cell`；`test_rendered_notebooks_parse`（`ast.parse` 能过）；以及一个标记 `sca` 的 `test_assembly_notebook_runs`：两个方块零件和一个装配 notebook，在真实沙盒里能跑通。
- [ ] **Step 2：** 运行，确认失败；实现；运行全部测试，提交：`feat: 零件 notebook 带编号和材料，生成装配 notebook`。

---

### Task 6：摆放、关节姿态与取样（纯 Python）

**Files：** Create `cad_agent/product/kinematics.py`、`tests/test_kinematics.py`

**Interfaces：**
- Produces：
  ```python
  Mat = list[float]   # 16 个数，按行
  @dataclass(frozen=True)
  class Frame: origin: tuple[float,float,float]; z: tuple[float,float,float]; x: tuple[float,float,float]
  def frame_from_geometry(kind: str, center, direction, offset: float, flip: bool) -> Frame: ...
  def rest_placements(asm: Assembly, frames: dict[str, Frame], values: dict[str, float]) -> dict[str, Mat]: ...
  def joint_value_samples(lo: float, hi: float, n: int) -> list[float]: ...   # 均匀，含两端
  def poses_at(asm: Assembly, frames: dict[str, Frame], rest: dict[str, Mat], joint_values: dict[str, float], values: dict[str, float]) -> dict[str, Mat]: ...
  def explode_directions(asm: Assembly, frames: dict[str, Frame], rest: dict[str, Mat]) -> dict[str, tuple[float,float,float]]: ...
  ```
  - `frames` 的键是 `"零件.连接点"`，坐标是零件自己的坐标。`frame_from_geometry`：`z` 是方向（flip 时取反）；原点沿 `z` 移 `offset`；`x` 是世界 X 投影到垂直于 `z` 的平面上，`z` 和世界 X 几乎平行时改用世界 Y；单位化。
  - `rest_placements`：ground 是单位矩阵；其余按 `mate_tree` 从 ground 往下：让 moving 端的坐标系和 fixed 端的坐标系重合——`align == "opposite"` 时 moving 的 `z` 和 fixed 的 `z` 反向，原点沿 fixed 的 `z` 再移 `gap`，绕 fixed 的 `z` 转 `angle` 度。
  - `poses_at`：先按联动把被带动关节的值算出来（`driven = ratio × driver`，不在 joint_values 里的关节取 `lo` 和 0 中在范围里的那个，都不在就取 `lo`）；转动关节绕它所在配合在世界坐标里的轴转，滑动关节沿 `direction` 平移；关节的子树一起动。
  - `explode_directions`：非 ground 零件沿它的配合的 fixed 端 `z` 方向（在世界坐标里）；方向和"从 ground 中心指向这个零件中心"的夹角超过 90 度时取反；ground 是零向量。

- [ ] **Step 1：** 写测试（全用手算得出的数）：`test_frame_from_cylinder_and_plane`；`test_rest_opposite_and_same_align`（两个 10 毫米方块面对面贴上、同向叠放、加 gap、加 angle 各一例，矩阵逐项对）；`test_revolute_pose`（盖子绕 x 轴转 90 度后，盖子上一点 (0, 50, 6) 到了手算的位置）；`test_prismatic_pose`；`test_subtree_moves_together`；`test_gear_coupling`（driver 转 36 度、ratio −0.5 → driven −18 度）；`test_samples_include_both_ends`；`test_explode_directions`。
- [ ] **Step 2：** 运行，确认失败；实现；运行全部测试，提交：`feat: 装配摆放和关节姿态的计算`。

---

### Task 7：沙盒里的装配运行

**Files：** Create `cad_agent/sandbox/runner_assembly.py`、`tests/test_runner_assembly.py`（标记 `sca`）；Modify `cad_agent/sandbox/execute.py`、`cad_agent/sandbox/runner.py`（按模式分发）

**Interfaces：**
- Produces：
  ```python
  @dataclass
  class AssemblyRun:
      ok: bool; error: dict | None
      connectors: dict[str, dict]           # "零件.连接点" → {"selected": n, "type": ..., "center": [...], "direction": [...]}
      rest: dict[str, list[float]]          # 每个零件装好后的矩阵
      overlaps: list[dict]                  # 装好时：{"a","b","volume"}，只列体积 > 0 的
      measures: dict[str, dict]             # 装配检查 id → 量到的数
      samples: dict[str, list[dict]]        # 关节 id → [{"value", "poses": {part: Mat}, "hits": [{"a","b","volume"}], "error": str | None}]
      files: dict[str, Path]                # "product.step"、"parts/<id>/model.step|model.stl"、"view.png"
      duration_s: float; timed_out: bool
  def run_assembly(ws: Workspace, *, mode: Literal["check", "export"], samples: int, timeout_s: float,
                   secret_names: Iterable[str], out_dir: Path | None = None, should_stop=None,
                   values: dict[str, float] | None = None) -> AssemblyRun: ...
  ```
  - 子进程里：逐个运行零件 notebook 得到实体；按每个连接点的 where 选几何（`engine._select`），**选中数不是 1 或类型不是圆柱面、平面、圆形的边，就记进 `connectors` 并让 `ok=False`**，错误信息用提示词文档 4.2 的两条原文；用 Task 6 的函数算 `rest`；量装好时两两重叠（包围盒不相交就跳过）；按装配检查量 `measures`（同轴、贴平量的是检查里 `a`、`b` 选中的真实几何，不是连接点）；对每个关节取样，每个位置算姿态、量会动的零件和其余零件之间的重叠。
  - `values` 给了时用这组参数值（参数直改、扰动验证用）。
  - `mode="export"` 时再导出：每个零件的 STEP 和 STL（零件自己的坐标）、整个产品的 STEP（按 `rest` 摆好）、一张产品的等轴测截图。
  - 某个取样位置 SCA 出错：这个位置的 `error` 写异常类型和精简后的信息（用 `runner.summarize_exception`），不跳过、不吞掉。
  - 超时、停止的处理和 `run_job` 一样（两层超时、结束进程树、`should_stop`）。

- [ ] **Step 1：** 写测试（真实沙盒，零件用最简单的方块和圆柱，一个测试不超过 60 秒）：`test_two_blocks_rest_and_no_overlap`；`test_overlap_detected`（故意让 gap 为负）；`test_connector_must_select_exactly_one`（Review Focus 2：选中 0 个、2 个各一例，信息等于原文）；`test_connector_wrong_type`；`test_hinge_sweep_detects_hit`（一块板绕轴转，转过 90 度后撞到一堵墙，`hits` 在后半段出现）；`test_sample_error_is_reported_not_ignored`（Review Focus 6：用一个会让 SCA 在某个位置出错的替身，`error` 不为空且 `ok` 为假）；`test_export_writes_product_and_part_files`；`test_values_override`。
- [ ] **Step 2：** 运行，确认失败；实现；运行全部测试，提交：`feat: 沙盒里装配、量穿模、关节取样`。

---

### Task 8：装配和运动的检查

**Files：** Create `cad_agent/product/checks.py`、`tests/test_product_checks.py`

**Interfaces：**
- Produces：
  ```python
  ASSEMBLY_TYPES = ("interference", "clearance", "coaxial", "flush", "motion_clear", "reach", "ratio")
  def parse_assembly_checks(raw: object, asm: Assembly, part_ids: list[str], param_names: set[str]) -> list[dict]: ...
  def mandatory_checks(asm: Assembly, part_ids: list[str]) -> list[dict]: ...
  def evaluate(run: AssemblyRun, checks: list[dict], asm: Assembly, values: dict[str, float]) -> list[CheckResult]: ...
  ```
  - 必做检查的 id 和顺序：`connectors_anchored`、`no_overlap_at_rest`、每个关节一条 `motion_clear_<关节 id>`。
  - `no_overlap_at_rest`：任意两个零件重叠体积 ≤ 0.01；`contact_pairs` 里的配对 ≤ `CONTACT_TOL_MM3`。`motion_clear` 同理；任何取样位置 `error` 不为空，这条检查就不通过，detail 写"<关节名字> 在 <值> 时没量成：<错误>"。
  - 每条结果的 `detail` 用中文写清哪两个零件、哪个位置、重叠多少；`motion_clear` 不通过时 detail 里写第一个撞上的位置。
  - `ratio` 用两个关节在取样里的变化量之比。`reach` 看取样里有没有到 `value` 的位置（±0.5 度或 ±0.05 毫米）且那里没有 `error`。

- [ ] **Step 1：** 写测试（用手造的 `AssemblyRun`，不跑沙盒）：每种类型通过、不通过各一例；`test_mandatory_checks_order`；`test_contact_pairs_only_from_joints_and_gears`（Review Focus 1）；`test_sample_error_fails_motion_clear`；`test_unknown_part_or_joint_rejected`；`test_details_are_chinese_and_specific`。
- [ ] **Step 2：** 运行，确认失败；实现；运行全部测试，提交：`feat: 装配和运动的检查`。

---

### Task 9：五个新工具

**Files：** Create `cad_agent/product/tools.py`、`tests/test_product_tools.py`；Modify `scripts/gen_staged_specs.py`、`cad_agent/staged/specs.py`（重新生成）、`cad_agent/tools.py`、`cad_agent/staged/tools.py`（update_brief 的处理挪到能处理 parts）

**Interfaces：**
- Produces：`ProductTools(box).handlers() -> dict[str, Handler]`，提供 `select_part`、`set_connectors`、`set_assembly`、`set_assembly_checks`、`build_assembly`。分阶段时 `ToolBox` 把它们并进处理函数表；工具说明 17 个（提示词文档第 3 节）。
- 可用性：需求单不是多零件时，这 5 个工具调用都返回 `{"error": "这个需求只有一个零件，用不到这个工具。"}`（这句原文照抄），不出现在 `schemas()` 里；多零件且已确认时出现。
- `select_part`：零件不存在 → 中文报错；切换（Task 4）；返回这个零件的计划和进度。
- `set_connectors`：只校验格式（Task 3），不跑沙盒；成功后 `assembly_passed = False`。
- `set_assembly`：调用 `parse_assembly`；写进 `ws.assembly`；成功后 `assembly_passed = False`；返回里带上范围写反之类的说明。
- `set_assembly_checks`：`parse_assembly_checks`；整体替换。
- `build_assembly`：还有零件没做完 → 提示词文档 4.2 的原文；没有 `ws.assembly` → `{"error": "还没有装配关系。先用 set_connectors 和 set_assembly 写好。"}`（原文照抄）；否则 `run_assembly(mode="check")` → `evaluate`（必做 + 模型写的）→ 全过就做产品终检（Task 10 的 `run_product_gate`）→ 返回体：`passed`、`connectors`、`failed_checks`、`hits`（每个关节第一个撞上的位置）、`final_gate`、`failures_left`、`hint`（提示词文档 4.3）。没通过计一次失败（计在"装配"这一步上）。
- 第二版的 `update_brief` 处理函数改成能处理 parts、motions、参数的 part（Task 2 的 `apply_patch` 已经能处理，这里只是确认返回里多一个 `parts_missing_relations`，规则同 `relations_missing`）。

- [ ] **Step 1：** 按"要改的旧测试"清单改 `test_specs_v2_are_verbatim`；写新测试：`test_new_specs_verbatim`；`test_tools_hidden_for_single_part`；`test_select_part`；`test_set_connectors_and_assembly_reset_passed`；`test_build_assembly_refused_until_parts_done`；`test_build_assembly_body_and_hints`（用假的 `run_assembly`，三种 hint 各一例，原文逐字相同）；`test_assembly_failure_counts`。
- [ ] **Step 2：** 运行，确认失败；实现；运行全部测试，提交：`feat: 多零件的五个工具`。

---

### Task 10：多零件的流程：零件做完、换下一个、装配、终检、交付

**Files：** Create `cad_agent/product/flow.py`、`cad_agent/product/delivery.py`、`tests/test_product_flow.py`；Modify `cad_agent/agent/loop.py`、`cad_agent/agent/staged_hooks.py`、`cad_agent/staged/final_gate.py`（只加多零件分支）

**Interfaces：**
- Produces：
  ```python
  def part_finished(box: ToolBox) -> bool: ...        # 当前零件计划全部通过且它自己的终检通过
  def finish_part(agent: Agent) -> str: ...           # 标记 done，生成提示词文档 4.1 的小结（含下一句），切到下一个没做完的零件；返回小结
  def run_product_gate(box: ToolBox) -> GateResult: ... # 产品参数和各零件参数的扰动验证：改一个参数，重做所有用到它的零件和装配，冻结期望值；规则同第二版终检
  def export_product_version(agent: Agent, changes: list[str]) -> Path: ...
  ```
  - 主循环：多零件时，每个零件的 build 最后一个阶段通过后，做这个零件自己的终检（只扰动这个零件的参数和它用到的产品参数，检查只用这个零件自己的）；通过就 `finish_part`，把本轮从上一个折叠点到现在的消息换成小结（用第二版的 `Context.fold`），继续调用模型。
  - 上限：工具调用总上限按 Global Constraints 放大；`stage_tool_calls` 在切换零件时清零。
  - `select_part` 回到一个已经 done 的零件并改了它（任何 upsert/remove/set_checks）：这个零件 `done = False`，`assembly_passed = False`，`ws.last_assembly = None`（Review Focus 5）。
  - 产品终检通过就交付：`export_product_version` 用 `run_assembly(mode="export")`，版本目录：`brief.json`、`assembly.json`、`assembly.py`、`product.step`、`view.png`、`motion.json`、`checks.json`（全部零件的检查 + 装配检查，每条带 `part` 字段，装配检查是 `"assembly"`）、`gate.json`、`changes.md`、`parts/<id>/model.py|model.step|model.stl|checks.json`。
  - `motion.json` 的格式（Task 13 和计划 3 都按它读）：
    ```json
    {"parts": {"<id>": {"name": "...", "material": "...", "color": "#...", "finish": "...", "stl": "parts/<id>/model.stl"}},
     "rest": {"<id>": [16 个数]},
     "explode": {"<id>": [x, y, z]},
     "joints": [{"id": "...", "label": "...", "type": "revolute", "unit": "deg", "lo": 0, "hi": 110,
                 "samples": [{"value": 0, "poses": {"<id>": [16 个数]}, "hits": []}]}]}
    ```
  - 交付文字：在第二版交付文字的基础上，多零件时第一行写"做好了，<n> 个零件，存成第 <k> 版。"，检查表按零件分组；有关节时加一行"<关节名字>：从 <lo> 到 <hi><单位>，取了 <n> 个位置，都没有碰到别的零件。"

- [ ] **Step 1：** 写测试 `tests/test_product_flow.py`（`ScriptedLLM` + 假的 `run_job`、假的 `run_assembly`）：
  - `test_two_part_flow_delivers`：确认 → 零件 body 两步 → 自动换到 lid → lid 一步 → set_connectors × 2 → set_assembly → build_assembly → 交付；版本目录里的文件齐全，`motion.json` 符合上面的格式。
  - `test_finished_part_is_folded`：做 lid 时发给模型的消息里有一条以 `【零件已做完（程序生成）】body` 开头的 user 消息，body 的工具来往都不在了。
  - `test_limits_scale_with_parts`。
  - `test_editing_finished_part_invalidates_assembly`（Review Focus 5）。
  - `test_product_gate_rebuilds_dependent_parts`：改产品参数时，两个零件和装配都重做；只属于 lid 的参数只重做 lid 和装配。
  - `test_single_part_flow_unchanged`：第二版的 `test_full_two_stage_flow_delivers` 那套剧本，在新代码上结果相同。
- [ ] **Step 2：** 运行，确认失败；实现。`loop.py` 超过 300 行时，把多零件的部分放进 `staged_hooks.py` 或 `product/flow.py`。
- [ ] **Step 3：** 运行全部测试，提交：`feat: 多零件的流程、终检和交付`。

---

### Task 11：系统提示词和速查表

**Files：** Create `cad_agent/agent/prompts/system_multipart.md`；Modify `cad_agent/agent/state.py`、`cad_agent/agent/prompts/sca_cheatsheet_more.md`、快照（多零件时多显示零件进度和装配状态）；Test `tests/test_prompts_multipart.py`

**Interfaces：**
- `load_system_prompt(True)` = `system_v2.md` + `system_multipart.md` + `references_index.md` + `sca_cheatsheet.md` + `sca_cheatsheet_more.md`。
- 快照：多零件时，在"计划"之前加一段"零件："每行 `<编号> <名字>（<材料名>）—— 已做完 / 当前 / 未开始`；全部做完后加"装配：未开始 / 没通过 / 已通过"。当前零件之外的零件的特征不列出（只列当前零件的）。
- 看图审查（设计文档第 6 节第 6 条）：`agent/prompts/reviewer.md` 的清单规则后面加一句，原文照抄：`另外，在清单最后加一项"整体做工"：看起来像不像一件做工好的产品（边角有没有处理、比例是否协调、零件之间的缝隙是否均匀），同样给出符合、不符合或看不出。` 程序在审查清单的末尾加一个 target `整体做工`。对应要改的旧测试：第二版计划 2 的 `test_reviewer_prompt_is_verbatim` 改为对照这一版（原文 + 这一句）；`test_review_targets` 的期望末尾多 `整体做工`。
- 速查表补充一节 `## 装配的写法`：至少 4 条，每条一行说明加一行"例："（是 `set_connectors` 或 `set_assembly` 的一个参数对象，JSON 单行）：铰链（转动）、抽屉（滑动）、齿轮联动、两个面贴在一起。每个例子都要在 Task 14 或 Task 15 的真实标准答案里用过。

- [ ] **Step 1：** 按清单改 `test_full_system_prompt_v2`；写新测试：`test_system_multipart_verbatim`；`test_system_prompt_order`；`test_snapshot_lists_parts`；`test_snapshot_single_part_unchanged`；`test_cheatsheet_has_assembly_section`；`test_assembly_examples_are_valid`（每个"例："能被 `parse_connectors` 或 `parse_assembly` 接受）。
- [ ] **Step 2：** 运行，确认失败；实现；运行全部测试，提交：`feat: 多零件和零件设计感的提示词`。

---

### Task 12：检查结果的选中几何、预览、多零件的参数直改

**Files：** Modify `cad_agent/checks/spec.py`、`cad_agent/checks/engine.py`、`cad_agent/agent/manual.py`；Create `cad_agent/product/preview.py`；Test `tests/test_selected.py`、`tests/test_preview.py`、`tests/test_manual_multipart.py`

**Interfaces：**
- `CheckResult` 加字段 `selected: list[dict] | None = None`；`to_dict` 只在不为 None 时带这个键；`from_dict` 读它。`engine` 在 count、distance、angle 三类检查上填：最多 8 项，每项 `{"type", "center": [x,y,z]}`，平面再加 `"normal"`。其余类型保持 None。
- `preview_product(agent: Agent, values: dict[str, float], *, should_stop=None) -> dict`：只生成模型、不跑检查、不存版本，结果放在会话目录的 `preview/` 下（每次先清空）。单零件返回 `{"stl": "preview/model.stl"}`；多零件返回 `{"parts": {"<id>": "preview/parts/<id>.stl"}, "rest": {...}}`。值的校验规则和 `apply_params` 相同。正在运行一轮对话时由调用方拒绝（计划 3 的接口负责）。
- `apply_params`：多零件时，改过的参数影响到的零件全部重做（各自所有步骤），再 `run_assembly(mode="check")` 和装配检查；全过才 `export_product_version`；不做扰动验证。失败时全部退回，和单零件的规则一样。

- [ ] **Step 1：** 写测试：`test_selected_on_count_distance_angle`（`sca`）；`test_selected_absent_for_bbox_and_old_dicts`；`test_to_dict_unchanged_when_no_selected`；`test_preview_single_part`（`sca`）；`test_preview_multipart_paths`（假的运行）；`test_preview_rejects_bad_values`；`test_manual_multipart_rebuilds_affected_parts`；`test_manual_multipart_failure_restores`。
- [ ] **Step 2：** 运行，确认失败；实现；运行全部测试，提交：`feat: 检查结果带选中的几何、预览、多零件的参数直改`。

---

### Task 13：给界面的状态

**Files：** Modify `cad_agent/desk/view.py`、`cad_agent/desk/workbench.py`、`cad_agent/desk/events.py`、`cad_agent/desk/routes.py`（文件白名单）；Test `tests/test_desk_state_v3.py`

**Interfaces（计划 3 只按这里的格式读）：**
- `build_state` 多出这些键（单零件时 `product` 为 null，其余照样有）：
  - `product`：`{"parts": [{"id","name","material","color","finish","status":"done|current|todo","checks":{"passed","total"}}], "joints": [{"id","label","type","unit","lo","hi"}], "motion": "<当前版本 motion.json 的文件地址或 null>", "assembly": "todo|failed|passed"}`
  - `params_view`：每个参数 `{"name","label","group","unit","value","source","part"}`。`label` 按设计文档第 7.6 节从说明截取；`group`：单零件按组成部分名字匹配说明，多零件按零件名字匹配，都匹配不上是"其他"。
  - `checks` 里每条多 `part`（单零件是 `"main"`、装配是 `"assembly"`）和 `selected`。
- 新的事件类型：`part_done`（`id`、`name`）、`assembly`（`passed`、`failed`、`hits`）。`describe_event` 给它们平常话的说明（"盒体做完了"、"装好了，检查都过了"/"装配没通过：<第一条原因>"）。
- 文件白名单增加：`parts/<id>/model.step|model.stl|model.py|checks.json`、`product.step`、`assembly.py`、`motion.json`、`preview/model.stl`、`preview/parts/<id>.stl`（`<id>` 只能是小写英文、数字、下划线）。

- [ ] **Step 1：** 写测试：`test_state_single_part_has_null_product`；`test_state_multipart_parts_and_joints`；`test_params_view_labels_and_groups`（说明是"盖子厚度（建议）"→ label "盖子厚度"，group "盖子"）；`test_new_events_described`；`test_file_whitelist_multipart`（合法的能取到；`parts/../log.jsonl`、`parts/A/model.stl`、`parts/x/brief.json` 都是 404）。
- [ ] **Step 2：** 运行，确认失败；实现；运行全部测试，提交：`feat: 多零件状态和文件给界面用`。

---

### Task 14：三个多零件评测任务和验收

**Files：** Create `benchmarks/tasks/toolbox.yaml`、`drawer_cabinet.yaml`、`gear_pair.yaml`、`benchmarks/assembly_accept.py`、`tests/test_assembly_tasks.py`、`tests/test_benchmark_references_v3.py`（标记 `sca`）；Modify `benchmarks/run.py`（任务集、验收分发）

**Interfaces：**
- `run.py`：`MULTI_TASKS = ["toolbox", "drawer_cabinet", "gear_pair"]`；`TASK_SETS` 加 `"multi"` 和 `"v3"`（`v2` 的 11 个 + 这 3 个）。原有集合不变。开发 / 留出的划分在计划 4 里做，本任务不动 `HOLDOUT_TASKS`。
- 任务文件的验收多两类条目（单零件条目照旧，作用在装好的产品上，用世界坐标）：
  - `{id, type: joint, kind: revolute|prismatic, axis: [x,y,z], through: [x,y,z], pos_tol, lo, hi}`：在产品里找一个关节，类型相同、方向和 `axis` 平行（±2 度）、（转动时）轴线到 `through` 的距离 ≤ `pos_tol`；它的范围要覆盖 `[lo, hi]`。找不到就不通过。
  - `{id, type: at_pose, joint: <上一条的 id>, value, checks: [单零件验收条目...]}`：把找到的关节放到 `value`，再跑里面的点检查。
- `assembly_accept.py`：**不读内核写的 `motion.json`**。用笔记第 26 节实测可用的 SCA 约束驱动把关节放到位；如果第 26 节的结论是驱动不可用，就在这个文件里独立写一份转动、平移的变换（不 import `cad_agent/product/kinematics.py`）。在文件开头的注释里写明用的是哪一种。
- 三个任务的内容（一句话需求、隐藏的完整需求、修改请求），照抄下表；**验收数字由执行者按隐藏需求手算**，手算过程写在 YAML 注释里。标准答案（测试里写的产品声明和零件特征）必须通过初始和修改后两组验收；另写一个"没按修改改"的反例，确认它恰好卡在修改相关的条目上。标准答案过不了验收时，先查标准答案；确认是手算错了，记偏离、写清新旧算式再改数字。

| 任务 | 一句话需求 | 隐藏的完整需求 | 修改请求 |
|---|---|---|---|
| toolbox | 做一个带铰链盖的工具盒 | 盒体外形 160×100×60（长宽高），壁厚 3，底厚 3，上面敞口；盖子 160×100×6，盖上时正好压在盒体上沿；铰链在后边（+y 那一侧）：轴线沿 x，在盒体后壁外侧 5 毫米、高度 63；盒体后面三段铰链耳、盖子两段，轴直径 3；盖子能向上翻开 0 到 110 度，翻开时不能碰到盒体；盖子顶面正中一个提手（跨距 70）；盒体 ABS 塑料、盖子阳极氧化铝、轴不锈钢、提手橡胶 | 盖子最多翻到 95 度就够了，盒子加高到 70 |
| drawer_cabinet | 做一个带抽屉的小柜子 | 柜体外形 200×150×120，壁厚 4，正面（−y）开口；抽屉外形比柜内空间左右各小 1、上下各小 1，深度 140，壁厚 3，前面板 200×4×120 盖住柜子正面；前面板正中一个拉手（宽 60）；抽屉沿 −y 能拉出 0 到 100 毫米，拉出时不碰柜体；柜体木头、抽屉 ABS 塑料、拉手黄铜 | 抽屉能拉出 120 毫米 |
| gear_pair | 做一对装在支架上能啮合转动的齿轮 | 底板 140×80×8；两根轴直径 8、高 30，竖直装在底板上，中心距 60；小齿轮模数 2、20 齿、齿宽 10，大齿轮模数 2、40 齿、齿宽 10，都套在轴上，下表面离底板上表面 5；轴和齿轮孔之间单边间隙 0.2；小齿轮转动时带动大齿轮反向转、转速是一半；小齿轮转一整圈不卡；底板铝、轴不锈钢、齿轮黄铜 | 大齿轮改成 50 齿，中心距跟着变 |

- [ ] **Step 1：** 写测试 `tests/test_assembly_tasks.py`：三个任务能加载；`MULTI_TASKS`、`TASK_SETS` 的内容；验收条目格式校验（缺 `axis`、`at_pose` 指向不存在的条目都报错）；`test_accept_does_not_import_kernel_kinematics`（读 `assembly_accept.py` 的源码，不包含 `cad_agent.product.kinematics`）。
- [ ] **Step 2：** 写测试 `tests/test_benchmark_references_v3.py`（`sca`）：三个任务的标准答案在初始和修改后都通过验收；反例恰好卡在修改相关的条目上；标准答案在我们的内核里也能通过所有必做检查和产品终检。
- [ ] **Step 3：** 运行，确认失败；写任务文件、验收代码、标准答案；运行全部测试，提交：`feat: 三个多零件评测任务`。

---

### Task 15：三个多零件自带案例

**Files：** Create `cad_agent/case_data/cabinet-door/`、`slide-table/`、`gear-turntable/` 各一个 `case.yaml`；Modify `cad_agent/cases.py`（案例格式支持多零件）；Test `tests/test_builtin_cases.py`（只加测试）、`tests/test_cases_multipart.py`

**Interfaces：**
- 案例文件多零件时多这些键：`parts`（同需求单）、`part_features`（零件编号 → 特征列表，特征带 `stage`）、`part_plans`、`part_checks`、`connectors`（零件编号 → 连接点列表）、`assembly`、`assembly_checks`。单零件案例格式不变。
- `render_cases` 对多零件案例：先列零件和装配声明，再列每个零件的计划（不列特征代码，防止超过 3000 字），整体仍不超过 3000 字。
- 三个案例：带门的小柜子（门绕竖直的铰链转）、滑台（台面沿导轨滑）、小齿轮带动内齿圈转盘（用标准件内齿圈，笔记第 21 节）。都不能和三个评测任务是同一种东西；齿轮案例不能是"两个外齿轮装在板上"。

- [ ] **Step 1：** 写测试：`test_multipart_case_round_trip`；`test_render_multipart_case_under_3000`；`test_builtin_multipart_cases_build_and_pass`（`sca`：每个案例装得起来、动得起来、必做检查和产品终检都过）；`test_multipart_cases_are_not_benchmark_tasks`；`test_there_are_eleven_builtin_cases`（第二版的 8 个加这 3 个）。
- [ ] **Step 2：** 运行，确认失败；实现；运行全部测试，提交：`feat: 三个多零件自带案例`。

---

### Task 16：真实沙盒的端到端和走查剧本

**Files：** Create `scripts/demo_script_multi.json`、`tests/test_multipart_e2e.py`（标记 `sca`）；Modify `cad_agent/app.py`（`--demo-script` 能用多零件剧本，无需改动的话只加测试）

- `demo_script_multi.json`：工具盒的完整剧本——问两个问题、整理出三个零件（盒体、盖子、铰链轴）的需求单、确认、逐个零件做（每个零件 2 到 3 步，最后一步是边角处理）、装配、交付；然后一次修改"盖子最多翻到 95 度"。特征代码只用速查表和笔记里实测过的写法。
- [ ] **Step 1：** 写测试 `tests/test_multipart_e2e.py`：用这份剧本加真实沙盒，按"做一个带铰链盖的工具盒 / 回答 / 确认 / 盖子最多翻到 95 度"四条消息走完，得到 v1、v2；v1 版本目录文件齐全，`motion.json` 里关节的 `hi` 是 110，v2 里是 95；所有取样位置都没有碰撞；三个零件的材料颜色在 `motion.json` 里。
- [ ] **Step 2：** 运行，确认失败；写剧本、修好走不通的地方；运行全部测试，提交：`feat: 多零件端到端走查剧本`。

---

## 做完之后

- `docs/progress.md` 写"3.0 计划 2 小结"：测试数、偏离、Task 1 的三个结论（接触容差、默认取样数、闭环支不支持）、没有用真实模型验证过的部分（全部）。
- 不要运行任何会调用真实模型的命令。
