# 3.0 · 计划 1：改名为 Datum · 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal：** 把产品从"卡尺 Caliper"改名为"Datum 基准"，版本 3.0.0；老用户升级时数据目录和密钥自动带过来；桌面端会话补记软件和模型版本（作业要求）。

**Architecture：** 名字集中放进一个新模块 `cad_agent/brand.py`，其余代码一律从它取名字，不再到处写死。升级迁移只做"复制"，从不删除旧的东西。Python 包目录仍是 `cad_agent`，不改任何导入。

**Tech Stack：** 不新增依赖。

**Spec：** `docs/superpowers/specs/2026-11-20-datum-v3-design.md`（第 11 节、第 9 节"记录软件及模型版本"一行）。

## Global Constraints

- 前几版计划的规矩全部继续有效（见 `CLAUDE.md`）：`.venv\Scripts\python`、UTF-8、先写测试、key 不打印不记录、每个文件不超过 300 行。
- **不调用任何真实的模型接口。** 钥匙串的测试用内存里的假后端。
- 名字一律从 `cad_agent/brand.py` 取：产品名 `Datum`、中文名 `基准`、显示名 `Datum 基准`、命令 `datum`、窗口命令 `datum-app`、发行包名 `datum-cad`、版本 `3.0.0`、数据目录名 `Datum`、环境变量前缀 `DATUM_`、钥匙串服务名 `datum`、自检用的钥匙串服务名 `datum-doctor`、本机接口的令牌请求头 `X-Datum-Token`。
- 旧名字只出现在两处：迁移代码（读旧目录 `Caliper`、旧钥匙串服务名 `caliper`）和安装脚本里"发现旧版 `caliper-cad`"的提示。
- 迁移只复制，不删除旧数据目录、不删除旧钥匙串里的 key。
- **要改的旧测试**：只有下面"要改的旧测试"清单里的，而且只把旧名字换成新名字、旧版本号换成新版本号，断言的其余部分不动。清单之外的旧测试一律不动。
- 偏离记录接着编号（从 D21 之后），写进 `docs/deviations.md`。每个任务收尾：全部测试通过 → 提交 → `docs/progress.md` 追加一段（标题写"3.0 计划 1 Task N"）。

## 要改的旧测试

只改名字和版本号这两类字面值：

| 文件 | 改什么 |
|---|---|
| `tests/test_app.py` | `CALIPER_HOME` → `DATUM_HOME`；`"卡尺 Caliper"` → `"Datum 基准"`；`"caliper doctor"` → `"datum doctor"`；钥匙串服务名 `"caliper"` → `"datum"`；入口 `caliper`/`caliper-app` → `datum`/`datum-app` |
| `tests/test_desk_export.py` | 标题里的 `卡尺 Caliper` → `Datum 基准` |
| `tests/test_desk_server.py` | 请求头 `X-Caliper-Token` → `X-Datum-Token` |
| `tests/test_desk_settings_api.py` | `CALIPER_HOME` → `DATUM_HOME`；钥匙串服务名 `"caliper"` → `"datum"` |
| `tests/test_doctor.py` | `CALIPER_HOME` → `DATUM_HOME`；`caliper --browser` → `datum --browser`；`caliper-doctor` → `datum-doctor`；服务名 `"caliper"` → `"datum"` |
| `tests/test_install_scripts.py` | 环境变量 `CALIPER_SOURCE/MIRROR/NO_SHORTCUT/DRY_RUN` → `DATUM_…`；`test_ps1_stops_when_caliper_is_running` 里的进程名换成 `datum`（测试名不变） |
| `tests/test_maintenance.py` | 数据目录 `Caliper` → `Datum`；`CALIPER_HOME` → `DATUM_HOME`；服务名；`卡尺 Caliper 2.0.0` → `Datum 基准 3.0.0`；包名 `caliper-cad` → `datum-cad`；快捷方式名 `卡尺 Caliper.lnk` → `Datum 基准.lnk` |
| `tests/test_paths.py` | `CALIPER_HOME` → `DATUM_HOME`；目录名 `Caliper` → `Datum`、`.caliper` → `.datum` |
| `tests/test_settings.py` | `CALIPER_HOME` → `DATUM_HOME`；`CALIPER_API_KEY` → `DATUM_API_KEY` |
| `tests/test_ci_workflow.py` | `CALIPER_SOURCE` → `DATUM_SOURCE` |
| `tests/test_readme.py` | 第一个标题 `# 卡尺 Caliper` → `# Datum 基准`；命令名、环境变量名里的 `caliper`/`CALIPER` → `datum`/`DATUM` |

测试里只用来放假 key 的环境变量名（`CALIPER_TEST_KEY`、`CALIPER_TEST_BENCH_KEY`、`CALIPER_TEST_REVIEW_KEY`）不改，它们不是产品名。测试里引用的旧计划文档路径（`2026-11-10-caliper-…md`）不改，那些文件还在。

## Review Focus

1. 新旧两个数据目录都在（用户已经用过 Datum 又打开了旧卡尺）：不复制、不覆盖，新目录原样使用。→ Task 2 `test_migration_skips_when_new_home_exists`
2. 旧数据目录复制到一半失败（磁盘满、文件被占用）：新目录不能留下半截，下次启动还能重试；启动不因此失败，只在日志里记一条。→ Task 2 `test_migration_failure_leaves_no_partial_home`
3. 环境变量 `DATUM_HOME` 已经设了：完全不碰旧目录。→ Task 2 `test_migration_skipped_when_datum_home_set`
4. 新钥匙串里没有 key、旧的里有：取出来用，并复制一份到新服务名；旧的不删。新旧都有时用新的。→ Task 3 `test_key_falls_back_to_old_service_and_copies`、`test_new_service_wins`
5. 用户电脑上同时装着旧的 `caliper-cad`：安装脚本照常装 `datum-cad`，只打印一句说明和卸载命令，不自动卸载；旧快捷方式删掉。→ Task 5 `test_install_scripts_mention_old_caliper`

---

### Task 1：名字集中到一处

**Files：** Create `cad_agent/brand.py`、`tests/test_brand.py`；Modify `cad_agent/__init__.py`、`pyproject.toml`、所有写死旧名字的源文件

**Interfaces：**
- Produces（`cad_agent/brand.py`）：
  ```python
  PRODUCT = "Datum"; PRODUCT_ZH = "基准"; DISPLAY = "Datum 基准"
  COMMAND = "datum"; GUI_COMMAND = "datum-app"; DIST = "datum-cad"; VERSION = "3.0.0"
  HOME_DIR = "Datum"; HOME_ENV = "DATUM_HOME"; ENV_PREFIX = "DATUM_"
  KEYRING_SERVICE = "datum"; DOCTOR_SERVICE = "datum-doctor"; TOKEN_HEADER = "X-Datum-Token"
  OLD_HOME_DIR = "Caliper"; OLD_KEYRING_SERVICE = "caliper"; OLD_DIST = "caliper-cad"
  ```
  `cad_agent.__version__ = brand.VERSION`。`pyproject.toml`：`name = "datum-cad"`、`version = "3.0.0"`，`[project.scripts] datum = "cad_agent.app:main"`，`[project.gui-scripts] datum-app = "cad_agent.app:gui_main"`，描述改成 Datum 的一句话。

- [ ] **Step 1：** 写测试 `tests/test_brand.py`：
  - `test_brand_values`：上面每个常量的值。
  - `test_version_matches_pyproject`：`cad_agent.__version__ == brand.VERSION ==` pyproject 里的版本。
  - `test_no_old_name_outside_migration`：在 `cad_agent/` 下所有 `.py`、`.js`、`.css`、`.html`、`.toml` 里搜 `caliper`、`Caliper`、`CALIPER`、`卡尺`，只允许出现在 `cad_agent/brand.py`（`OLD_` 开头的三个常量）和 `cad_agent/migrate.py`（Task 2 新建）里。`static/vendor/` 下的第三方文件跳过。
- [ ] **Step 2：** 运行，确认失败。
- [ ] **Step 3：** 建 `brand.py`；把 `cad_agent/` 里写死的旧名字全部换成从 `brand` 取（`app.py` 的窗口标题、`--version` 输出、`doctor.py`、`doctor_probes.py`、`keystore.py` 的服务名、`maintenance.py` 的包名和快捷方式名、`paths.py` 的目录名和环境变量、`settings.py`、`desk/server.py` 的令牌请求头、`desk/hub.py`、`desk/settings_api.py`、`desk/workbench.py`、`desk/export.py`、`cli.py`、`agent/resume.py`、`providers.toml` 里自定义服务的 `CALIPER_API_KEY` → `DATUM_API_KEY`）。前端 `static/` 里的名字：页面标题和顶栏写成 `Datum`，脚本里的令牌请求头从启动信息里取，不写死。按"要改的旧测试"清单改测试。
- [ ] **Step 4：** 运行全部测试，提交：`chore: 改名为 Datum 基准，版本 3.0.0`。

---

### Task 2：数据目录的迁移

**Files：** Create `cad_agent/migrate.py`、`tests/test_migrate.py`；Modify `cad_agent/paths.py`、`cad_agent/app.py`

**Interfaces：**
- Produces：
  ```python
  # paths.py
  def app_home() -> Path: ...        # DATUM_HOME；否则 Windows %LOCALAPPDATA%\Datum，Mac ~/Library/Application Support/Datum，其他 ~/.datum
  def old_app_home() -> Path: ...    # 同样的规则，目录名用 Caliper（其他系统 ~/.caliper）
  # migrate.py
  @dataclass(frozen=True)
  class MigrationResult:
      done: bool          # 这次复制了
      reason: str         # 中文：复制了 / 新目录已存在 / 没有旧目录 / 设置了 DATUM_HOME / 复制失败（原因）
  def migrate_home() -> MigrationResult: ...
  ```
  - 只有这三个条件同时成立才复制：没有设置 `DATUM_HOME`；新目录不存在；旧目录存在。
  - 先复制到新目录旁边的临时目录（`Datum.migrating`），全部成功后再改名成 `Datum`；失败就删掉临时目录，返回 `done=False`，原因写进 `reason`。
  - 复制时把 `settings.toml` 里提到旧名字的值（比如自定义服务的 `CALIPER_API_KEY`）原样保留，不改用户的设置。
  - `app.main` 和 `gui_main` 一启动就调用一次，结果写进程序日志（`paths.logs_dir()` 下），不打断启动。

- [ ] **Step 1：** 写测试 `tests/test_migrate.py`（用 monkeypatch 改 `sys.platform`、`LOCALAPPDATA`、`HOME`，全在临时目录里）：
  - `test_copies_old_home_once`：旧目录里有 `settings.toml`、`sessions/x/log.jsonl`、`cases/y/case.yaml` → 新目录里都有、内容相同；旧目录原样还在；再调用一次返回 `done=False`、原因是"新目录已存在"。
  - `test_migration_skips_when_new_home_exists`（Review Focus 1）。
  - `test_migration_skipped_when_datum_home_set`（Review Focus 3）。
  - `test_no_old_home_is_fine`。
  - `test_migration_failure_leaves_no_partial_home`（Review Focus 2）：让复制函数在第二个文件时抛 `OSError` → 新目录和临时目录都不存在，`done=False`，原因里有"复制失败"。
  - `test_app_start_migrates_and_logs`。
  - `test_old_app_home_per_platform`。
- [ ] **Step 2：** 运行，确认失败；实现；运行全部测试，提交：`feat: 从卡尺升级时复制数据目录`。

---

### Task 3：钥匙串的迁移

**Files：** Modify `cad_agent/keystore.py`；Test `tests/test_keystore_migrate.py`

**Interfaces：**
- Produces：`get_key(provider_id, env_name)` 和 `key_source(...)` 的规则变为：环境变量 → 新服务名 `datum` → 旧服务名 `caliper`。从旧服务名取到时，复制一份到新服务名（复制失败不影响这次取到的 key，只是下次还从旧的取）。`key_source` 对旧服务名里的 key 也返回 `"keyring"`。`set_key`、`delete_key` 只动新服务名。

- [ ] **Step 1：** 写测试（内存假后端）：`test_key_falls_back_to_old_service_and_copies`（Review Focus 4）；`test_new_service_wins`；`test_env_still_wins`；`test_copy_failure_does_not_break_get`（假后端写入时抛异常 → 仍返回旧的 key）；`test_delete_only_touches_new_service`；`test_errors_never_contain_key`。
- [ ] **Step 2：** 运行，确认失败；实现；运行全部测试，提交：`feat: 从卡尺升级时带上钥匙串里的 key`。

---

### Task 4：桌面端会话记录软件和模型版本

作业要求"记录软件及模型版本"。命令行版启动时已经写了 `startup` 日志，桌面端的会话还没有。

**Files：** Modify `cad_agent/desk/hub.py`（或创建会话的地方）、`cad_agent/cli.py`（把版本信息的收集提成公共函数）；Create `cad_agent/versions_info.py`；Test `tests/test_versions_info.py`

**Interfaces：**
- Produces：`collect_versions(config: Config) -> dict`，键：`datum`（`brand.VERSION`）、`python`、`simplecadapi`、`openai`、`anthropic`、`platform`、`provider`、`model`（基础模型名）、`models_by_phase`（澄清、建模、审查各用哪个模型名）。不含 key、不含地址里的查询参数。命令行和桌面端新建或打开会话时，都往会话日志写一条 `{"kind": "startup", **collect_versions(config)}`；打开旧会话时也写一条（同一个会话可以有多条，按时间看）。

- [ ] **Step 1：** 写测试：`test_collect_versions_keys`；`test_no_key_in_versions`（环境变量里放假 key，结果转成文字后搜不到）；`test_desk_new_session_logs_startup`；`test_desk_reopened_session_logs_startup_again`；`test_cli_still_logs_startup`（原来的行为不变）。
- [ ] **Step 2：** 运行，确认失败；实现；运行全部测试，提交：`feat: 桌面端会话记录软件和模型版本`。

---

### Task 5：安装脚本、更新和卸载

**Files：** Modify `install.ps1`、`install.sh`、`cad_agent/maintenance.py`、`docs/install-notes.md`；Test `tests/test_install_scripts.py`（按清单改）、`tests/test_install_rename.py`（新）

**Interfaces：**
- 安装脚本：装 `datum-cad`，默认来源 `git+https://github.com/DingZhen-zhr/computer-graphics-project@v3.0.0`（压缩包备用地址同步改成 `v3.0.0`）；选项环境变量改成 `DATUM_SOURCE`、`DATUM_MIRROR`、`DATUM_NO_SHORTCUT`、`DATUM_DRY_RUN`；快捷方式名 `Datum 基准`（Mac 是 `~/Applications/Datum.app`）。
- 发现旧版：`uv tool list` 里有 `caliper-cad` 时，打印 `检测到旧版"卡尺"（caliper-cad）。它可以和 Datum 同时存在；不需要的话运行：uv tool uninstall caliper-cad`，不自动卸载。旧快捷方式（`卡尺 Caliper.lnk`、`~/Applications/Caliper.app`）存在就删掉，删之前打印一行。
- 运行中检测：进程名改成 `datum-app` / `datum`。
- `maintenance.py`：`shortcut_paths()`、`update_command()`、卸载里的服务名和包名都从 `brand` 取。

- [ ] **Step 1：** 按清单改 `tests/test_install_scripts.py`；新写 `tests/test_install_rename.py`：`test_default_source_is_v3_tag`；`test_install_scripts_mention_old_caliper`（Review Focus 5：两个脚本里都有那句提示的原文，且没有自动执行 `uv tool uninstall caliper-cad`）；`test_old_shortcuts_are_removed_in_dry_run`（演示模式下打印了删除旧快捷方式的那一步）；`test_uninstall_uses_new_names`。
- [ ] **Step 2：** 运行，确认失败；实现；`docs/install-notes.md` 补一节"从卡尺升级"。运行全部测试，提交：`feat: 安装脚本改用 Datum 并处理旧版卡尺`。

---

## 做完之后

`docs/progress.md` 写"3.0 计划 1 小结"：测试数、改了哪些旧测试（逐个文件）、偏离。**不要推送、不要打标签**，那是计划 5 的事。
