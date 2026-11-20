# 卡尺第二版 · 计划 4：安装与分发 · 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal：** 让别人在终端粘一行命令就能把卡尺装到自己的 Windows 或 Mac 上；提供自检、更新、卸载命令；GitHub Actions 在两个平台上自动验证；GitHub Pages 变成产品主页并带一个在线回放；旧网页界面退役；README 重写。

**Architecture：** 安装脚本（`install.ps1`、`install.sh`）用 uv 准备独立的 Python 3.12 环境，并用 `uv tool install` 从本仓库的发布标签安装，得到 `caliper` 和 `caliper-app` 两个命令，再建快捷方式。脚本的所有选项都用环境变量传（因为"下载后直接管道执行"的用法传不了参数）。在线回放是把新界面连同一个会话的状态导出成一组静态文件。

**Tech Stack：** PowerShell 5.1 以上、POSIX sh、uv、GitHub Actions。Python 侧不新增依赖。

**Spec：** `docs/superpowers/specs/2026-11-10-caliper-v2-design.md`（第 6 节、第 8 节、第 1.3 节的成功标准 1、4、6）。

**前置：** 计划 1、2、3 全部完成。

**执行规则：** 见项目根目录 `CLAUDE.md`。

## Global Constraints

- 前三份计划的 Global Constraints 全部继续有效。**本计划不调用任何付费的模型接口。**
- **推送到 GitHub、打标签、改仓库设置之前，停下来问用户。** Task 4（持续集成）、Task 5（主页）、Task 8（发布）都要推送后才能看到结果，各自问一次，不能拿前一次的同意当这一次的同意。
- 支持的平台：Windows 10/11 x64；Apple 芯片的 Mac、macOS 14 及以上。安装脚本在不支持的平台上要说清原因并以非 0 退出，不做任何改动。
- 安装脚本不需要管理员权限，不改系统设置，只往用户目录里写东西。它下载并执行的外部脚本只有 uv 的官方安装脚本一个，地址写之前对照 uv 官方文档核实。
- 安装脚本和 `caliper update`、`caliper uninstall` 会改用户电脑上的东西：每一步做之前先打印要做什么。
- 包的发行名是 `caliper-cad`，版本 `2.0.0`；包目录名仍是 `cad_agent`，不改任何导入。
- uv 的命令和参数（`uv tool install`、指定 Python 版本、镜像相关的环境变量、`uv tool dir`）先查官方文档，写进 `docs/install-notes.md`，再用。
- 旧测试：Task 6 的清单里列出的可以删除或搬家；另外，**只在 Mac 上失败、原因是测试本身写死了 Windows 的写法**（路径分隔符、`.bat`、`taskkill`、`.exe`）的旧测试，可以改成按平台分支，断言不放松，逐条记进 `docs/progress.md`。除此之外不动。
- 偏离记录接着编号。每个任务收尾：全部测试通过 → 提交 → 在 `docs/progress.md` 追加一段（标题写"第二版 计划 4 Task N"）。

## Review Focus

1. 用户名是中文的 Windows 电脑：系统临时目录带中文。自检要查出来并说明程序已经自动改用纯英文的工作目录；这个目录建不了时，明确报出来。→ Task 1 `test_non_ascii_temp_is_reported_with_fallback`、`test_fallback_dir_not_writable_is_a_failure`
2. 国内网络连不上 GitHub 或 PyPI：安装脚本不能无限等，要在超时后说明原因，并提示镜像开关和"下载压缩包本地安装"的办法。→ Task 3 `test_install_script_mentions_mirror_and_offline_path`，以及脚本里每次下载都带超时
3. 已经装过旧版本再运行安装命令：覆盖安装，数据目录、设置、钥匙串里的 key 都不受影响。→ Task 3 `test_reinstall_keeps_data`（持续集成里再装一次验证）
4. 卸载时用户没有回答"要不要删数据"（非交互环境）：默认不删数据。→ Task 2 `test_uninstall_keeps_data_by_default_when_not_interactive`
5. Windows 10 上没有 WebView2 运行时：自检给出"缺什么、去哪里装"，并说明可以先用 `caliper --browser`。→ Task 1 `test_missing_webview2_is_a_warning_with_advice`
6. 一个 Intel 芯片的 Mac，或者 macOS 13：安装脚本第一步就停下说明原因，什么都没装。→ Task 3 `test_install_sh_platform_gate`

---

## 文件结构

```
cad_agent/__init__.py              __version__ = "2.0.0"（Task 2）
cad_agent/doctor.py                自检（Task 1）
cad_agent/maintenance.py           更新、卸载、快捷方式的位置（Task 2）
cad_agent/app.py                   接上 doctor / update / uninstall 子命令和 --smoke（Task 1、2）
install.ps1  install.sh            安装脚本（Task 3）
scripts/make_icon.py               生成图标（Task 3）
cad_agent/desk/static/icon.ico  icon.icns  icon.png
docs/install-notes.md              uv 用法的实测笔记（Task 3）
.github/workflows/ci.yml           两个平台的自动验证（Task 4）
cad_agent/desk/export.py           把一个会话导出成静态回放（Task 5）
site/                              产品主页和在线回放（Task 5）
.github/workflows/pages.yml        （Task 5）
cad_agent/desk/replay.py           从旧网页搬过来的回放读取（Task 6）
tests/test_desk_legacy.py          从 tests/test_web.py 搬过来的测试（Task 6）
README.md                          重写（Task 7）
docs/mac-checklist.md              Mac 人工清单（Task 7）
```

---

### Task 1：自检命令

**Files：** Create `cad_agent/doctor.py`、`tests/test_doctor.py`；Modify `cad_agent/app.py`

**Interfaces：**
- Produces：
  ```python
  @dataclass(frozen=True)
  class CheckItem:
      id: str
      name: str                                   # 中文名
      status: Literal["ok", "warn", "fail", "skip"]
      detail: str                                 # 一句中文：看到了什么
      advice: str = ""                            # 不是 ok 时：怎么办
  def run_doctor(*, offline: bool = False) -> list[CheckItem]: ...
  def render_doctor(items: list[CheckItem]) -> str: ...
  def doctor_exit_code(items: list[CheckItem]) -> int: ...     # 有 fail 返回 1，否则 0
  ```
  - 命令：`caliper doctor [--offline] [--json]`。`--json` 输出 `[{id, name, status, detail, advice}]`。
  - 检查项，按顺序（`id`）：

    | id | 查什么 | 不通过时 |
    |---|---|---|
    | `platform` | 系统和芯片在不在支持范围里 | fail |
    | `python` | Python 版本在 3.10 到 3.13 之间 | fail |
    | `sca` | 能定位到 simplecadapi，版本是 2.2.7 | fail |
    | `sandbox` | 用沙盒建一个方块并测量，结果正确 | fail |
    | `workdir` | 沙盒的工作目录是纯英文路径：系统临时目录本身是，就 ok；不是但备用目录能用，就 warn 并说明已自动改用；备用目录也不行，fail | 见左 |
    | `window` | 窗口后端能用：能导入 `webview`；Windows 上还要查到 WebView2 运行时（查法先探测，写进 `docs/install-notes.md`）；查不到是 warn，建议先用 `caliper --browser` | warn |
    | `keyring` | 能往钥匙串写一条测试项、读回来、再删掉（服务名 `caliper-doctor`） | warn，建议改用环境变量 |
    | `data` | 数据目录能建、能写 | fail |
    | `provider` | 当前设置的模型服务地址能连上（只建立连接，5 秒超时，不发请求内容）；`--offline` 时 skip | warn |
    | `key` | 有没有可用的 key，只说来源（环境变量 / 钥匙串 / 没有），不显示任何一位 | warn |

  - `render_doctor`：每项一行，`✓`、`!`、`✗`、`—` 开头，后面是名字和 `detail`；不是 ok 的下面缩进一行写 `advice`；最后一行是总结（`全部正常` / `有 <n> 项需要注意` / `有 <n> 项不能用`）。
  - 每一项自己捕获异常：某一项查的过程中出错，这一项记 fail、`detail` 写异常类型和一句话，其余项照常查。
  - `caliper --smoke`（隐藏参数，持续集成用）：不开窗口，起服务，自己请求一次首页和 `/api/boot`，都是 200 就打印 `smoke ok` 并返回 0。

- [ ] **Step 1：** 写测试 `tests/test_doctor.py`（各项的探测函数都能被替换）：
  - `test_all_ok_on_this_machine`（标记 `sca`）：`run_doctor(offline=True)` 里没有 fail。
  - `test_order_and_ids`。
  - `test_non_ascii_temp_is_reported_with_fallback`、`test_fallback_dir_not_writable_is_a_failure`（Review Focus 1）。
  - `test_missing_webview2_is_a_warning_with_advice`（Review Focus 5）：`advice` 里有 `WebView2` 和 `caliper --browser`。
  - `test_keyring_probe_cleans_up`、`test_keyring_unavailable_is_warn`。
  - `test_provider_unreachable_is_warn`、`test_offline_skips_provider`。
  - `test_key_item_never_shows_key`：环境变量里放假 key，`render_doctor` 和 `--json` 的输出里都搜不到它的任何 4 位以上的片段。
  - `test_one_crashing_check_does_not_stop_the_rest`。
  - `test_exit_code`、`test_render_format`、`test_json_output`。
  - `test_smoke_flag`。
- [ ] **Step 2：** 运行，确认失败；实现；运行全部测试，提交：`feat: caliper doctor 自检`。

---

### Task 2：版本号、更新和卸载

**Files：** Create `cad_agent/maintenance.py`、`tests/test_maintenance.py`；Modify `cad_agent/__init__.py`、`cad_agent/app.py`、`pyproject.toml`

**Interfaces：**
- Produces：
  ```python
  # cad_agent/__init__.py
  __version__ = "2.0.0"
  # maintenance.py
  REPO = "DingZhen-zhr/computer-graphics-project"
  INSTALL_PS1 = f"https://raw.githubusercontent.com/{REPO}/master/install.ps1"
  INSTALL_SH = f"https://raw.githubusercontent.com/{REPO}/master/install.sh"
  def shortcut_paths() -> list[Path]: ...        # 这个平台上安装脚本会建的快捷方式
  def update_command() -> list[str]: ...         # 这个平台上重新运行安装脚本的命令
  def run_update(run: Callable = subprocess.call, say: Callable = print) -> int: ...
  def run_uninstall(*, delete_data: bool | None, ask: Callable[[str], str] = input, say: Callable = print,
                    run: Callable = subprocess.Popen) -> int: ...
  ```
  - `pyproject.toml`：`name = "caliper-cad"`、`version = "2.0.0"`，描述改成卡尺的一句话。
  - `caliper --version` 打印 `卡尺 Caliper 2.0.0`。
  - `caliper update`：打印将要运行的命令，然后运行它（就是重新执行最新的安装脚本，由它覆盖安装）。
  - `caliper uninstall [--delete-data | --keep-data]`：依次做，每一步先打印：
    1. 删快捷方式（不存在就跳过）。
    2. 删钥匙串里每个预设对应的 key（没有就跳过）。
    3. 数据目录：给了 `--delete-data` 就删；给了 `--keep-data` 就留；都没给时问一句 `要把会话、案例和设置也一起删掉吗？输入 yes 确认删除，直接回车保留：`，只有回答 `yes` 才删；标准输入不是终端时不问，按保留处理。
    4. 最后让 uv 卸载程序本身：新开一个不依附当前进程的进程去运行 `uv tool uninstall caliper-cad`；开不了就打印这条命令让用户自己运行。
  - 快捷方式的位置：Windows 是"开始菜单 \ 程序 \ 卡尺 Caliper.lnk"和"桌面 \ 卡尺 Caliper.lnk"；Mac 是 `~/Applications/Caliper.app`。

- [ ] **Step 1：** 写测试（文件操作都在临时目录里，钥匙串用内存后端，`run` 用假函数）：
  - `test_version_string`、`test_pyproject_name_and_version`。
  - `test_update_runs_install_script_command`（两个平台各一例）、`test_update_prints_before_running`。
  - `test_uninstall_removes_shortcuts_and_keys`。
  - `test_uninstall_delete_data_flag`、`test_uninstall_keep_data_flag`、`test_uninstall_asks_and_only_yes_deletes`。
  - `test_uninstall_keeps_data_by_default_when_not_interactive`（Review Focus 4）。
  - `test_uninstall_prints_command_when_spawn_fails`。
  - `test_uninstall_never_touches_paths_outside_home`：数据目录被环境变量指到一个不含 `Caliper`、`caliper` 字样的路径时，拒绝删除并说明。
- [ ] **Step 2：** 运行，确认失败；实现；运行全部测试，提交：`feat: 版本号、更新和卸载命令`。

---

### Task 3：安装脚本

**Files：** Create `install.ps1`、`install.sh`、`scripts/make_icon.py`、`cad_agent/desk/static/icon.ico`、`icon.icns`、`icon.png`、`docs/install-notes.md`、`tests/test_install_scripts.py`

**Interfaces：**
- 两个脚本的选项都用环境变量：

  | 变量 | 作用 | 默认 |
  |---|---|---|
  | `CALIPER_SOURCE` | 从哪里装：一个 git 地址，或本地目录 | `git+https://github.com/DingZhen-zhr/computer-graphics-project@v2.0.0` |
  | `CALIPER_MIRROR` | 设成 `1` 时，PyPI 和 Python 的下载走国内镜像 | 不设 |
  | `CALIPER_NO_SHORTCUT` | 设成 `1` 时不建快捷方式 | 不设 |
  | `CALIPER_DRY_RUN` | 设成 `1` 时只打印每一步要做什么，不执行 | 不设 |

- 脚本的步骤，每一步开头打印一行 `[n/5] <做什么>`：
  1. 检查平台。Windows：必须是 64 位、Windows 10 及以上。Mac：`uname -m` 必须是 `arm64`，`sw_vers -productVersion` 的主版本必须不小于 14。不满足就打印原因和支持的范围，以返回码 2 退出。
  2. 准备 uv：`uv` 命令已经有就用现成的；没有就运行 uv 的官方安装脚本，并把它的安装目录加进本次脚本的 PATH。
  3. 安装：`uv tool install --python 3.12 --force <来源>`（镜像相关的参数按 `docs/install-notes.md`）。失败时打印原因，并打印三条提示：检查网络；设 `CALIPER_MIRROR=1` 再试；README"装不上怎么办"一节。
  4. 快捷方式：Windows 用 `WScript.Shell` 建两个 `.lnk`（执行时改成了 IShellLinkW，见 `docs/deviations.md` D20：`WScript.Shell` 在英文 Windows 上存不了中文名字的快捷方式），目标是 uv 工具目录里的 `caliper-app.exe`，图标用包里的 `icon.ico`；Mac 建 `~/Applications/Caliper.app`（`Info.plist`、一个调用 `caliper-app` 的启动脚本、`icon.icns`）。
  5. 运行 `caliper doctor`，把结果原样打印；最后一行告诉用户怎么启动（Windows：桌面上的"卡尺 Caliper"，或在终端输入 `caliper`；Mac：在"应用程序"里找 Caliper，或在终端输入 `caliper`；如果 PATH 还没生效，提示重开终端）。
- 每一次网络下载都带超时（连接 20 秒）。脚本出错就停，不继续往下做。
- 图标：`scripts/make_icon.py` 用 Pillow 画一个卡尺的简笔图形（米白底、墨色线、一处制图蓝），输出 256×256 的 `icon.png`、多尺寸的 `icon.ico`、`icon.icns`。生成的三个文件提交进仓库。

- [ ] **Step 1：** 查 uv 官方文档并在本机实测，写 `docs/install-notes.md`：uv 官方安装脚本的地址（两个平台）；`uv tool install` 从 git 标签和从本地目录安装的写法；怎么指定 Python 版本；镜像用哪些参数和环境变量；`uv tool dir` 怎么得到可执行文件的目录；`uv tool update-shell` 的作用；本机用本地目录装一次要多久、占多少空间；`caliper-app.exe` 双击时有没有黑窗口；Windows 上怎么查 WebView2 运行时（Task 1 用）。
- [ ] **Step 2：** 写测试 `tests/test_install_scripts.py`：
  - `test_ps1_parses`：用 PowerShell 的语法解析器解析 `install.ps1`，没有错误（只在 Windows 上跑）。
  - `test_sh_parses`：`sh -n install.sh` 返回 0（有 `sh` 时跑）。
  - `test_ps1_dry_run_prints_five_steps`（Windows）、`test_sh_dry_run_prints_five_steps`（有 `sh` 时）：设 `CALIPER_DRY_RUN=1` 运行，输出里依次有 `[1/5]` 到 `[5/5]`，没有真的调用 uv（用一个假的 `uv` 放在 PATH 最前面来确认）。
  - `test_default_source_is_the_release_tag`：两个脚本里的默认来源都以 `@v` 加 `cad_agent.__version__` 结尾。
  - `test_only_one_external_script_is_executed`：两个脚本里出现的网址，除了本仓库的，只有 uv 官方安装脚本一个和镜像地址。
  - `test_install_script_mentions_mirror_and_offline_path`（Review Focus 2）：失败时打印的文字里有 `CALIPER_MIRROR` 和 `装不上怎么办`；脚本里每个下载命令都带了超时参数。
  - `test_install_sh_platform_gate`（Review Focus 6，有 `sh` 时）：用假的 `uname`、`sw_vers` 放在 PATH 最前面，分别模拟 x86_64 和 macOS 13 → 返回码 2，输出里有原因，没有调用 uv。
  - `test_icons_exist_and_are_valid`：三个图标文件能被 Pillow 读出来，`icon.png` 是 256×256。
  - `test_scripts_have_no_admin_or_system_changes`：`install.ps1` 里没有 `RunAs`、`HKLM`、`Set-ExecutionPolicy`；`install.sh` 里没有 `sudo`。
- [ ] **Step 3：** 运行，确认失败；写两个脚本和图标脚本。
- [ ] **Step 4：** 在本机实测 Windows 的安装：`$env:CALIPER_SOURCE = "."; powershell -ExecutionPolicy Bypass -File install.ps1`。确认：`caliper --version` 能用；开始菜单和桌面有快捷方式，双击能开窗口且没有黑窗口；`caliper doctor` 全部正常。然后**再装一次**（Review Focus 3，`test_reinstall_keeps_data` 是这一步的人工版）：之前建的会话和设置还在。把过程和看到的结果写进 `docs/install-notes.md`。实测完保留安装，后面的任务要用。
- [ ] **Step 5：** 运行全部测试，提交：`feat: Windows 和 Mac 的一行安装脚本`。

---

### Task 4：持续集成

**Files：** Create `.github/workflows/ci.yml`、`tests/test_ci_workflow.py`；可能 Modify 少数旧测试（只按 Global Constraints 允许的那一种改法）

**Interfaces：**
- Produces：工作流 `持续集成`，在推送到 `master` 和有拉取请求时运行；矩阵 `windows-latest`、`macos-15`（偏离 D18：原为 `macos-14`，GitHub 已不提供 Apple 芯片的 macos-14），Python 3.12。步骤：
  1. 检出代码；装 uv（官方的 setup action）；装 Node（给 `node --test` 用）。
  2. `uv venv --python 3.12`，装 `-e ".[dev]"`。
  3. 跑全部测试（设 `PYTHONUTF8=1`）。
  4. 用本地源码跑安装脚本（`CALIPER_SOURCE` 指到检出的目录）。
  5. `caliper doctor --offline`（返回码必须是 0）。
  6. `caliper --smoke`。
  7. 再跑一次安装脚本，确认第二次也成功（Review Focus 3）。
  - 工作流不需要任何密钥，也不调用任何模型接口。

- [ ] **Step 1：** 写测试 `tests/test_ci_workflow.py`：`test_matrix_has_both_platforms`、`test_workflow_runs_tests_install_doctor_smoke`（按顺序找到这几步）、`test_workflow_uses_no_secrets`（文件里没有 `secrets.`）。
- [ ] **Step 2：** 运行，确认失败；写 `ci.yml`；运行全部测试，提交：`ci: 在 Windows 和 Mac 上自动验证`。
- [ ] **Step 3：** **停下来问用户：可以推送到 GitHub 吗？** 说明这次推送会带上哪些提交、会触发哪个工作流。得到同意后推送。
- [ ] **Step 4：** 请用户在仓库的 Actions 页面看结果，或者把失败的日志贴回来。按日志修：
  - Mac 上失败的旧测试：只是测试写死了 Windows 写法的，按平台分支改，逐条记进 `docs/progress.md`；程序在 Mac 上确实有问题的，修程序并补一条测试。
  - 每修一轮都要再问一次才能推送。
- [ ] **Step 5：** 两个平台都通过后，把运行的链接和通过的测试数写进 `docs/progress.md`。两个平台里有一个一直过不了时，如实写明卡在哪里，停下来问用户。

---

### Task 5：在线回放和产品主页

**Files：** Create `cad_agent/desk/export.py`、`tests/test_desk_export.py`、`site/`（重新生成）；Modify `cad_agent/desk/static/js/api.js`、`.github/workflows/pages.yml`

**Interfaces：**
- Produces：
  ```python
  def export_static(session_dir: Path, out_dir: Path, *, title: str) -> None: ...
  ```
  - 命令：`python -m cad_agent.desk.export <会话目录> <输出目录>`。
  - 输出目录里有：`index.html`（新界面的页面，页面里带一个标记表明这是静态回放）、`static/`（样式、脚本、three.js）、`state.json`（这个会话的完整状态，`demo` 为真）、`files/<版本>/…`（白名单里的文件）。
  - 静态回放时，`api.js` 的 `get` 从 `state.json` 和 `files/` 读；`post`、`del`、`subscribe` 什么都不做；界面按示例会话处理（只读），不显示侧栏的会话列表、设置和引导。
  - 导出的内容里不能有绝对路径、用户名、key。
- `site/` 的结构：`site/index.html` 是产品主页；`site/demo/` 是 `export_static` 导出的手机支架示例。
- 主页（一页，图纸风格，用 `tokens.css` 的同一套变量，支持深浅色，不加载任何外部资源）：
  1. 标题区：`卡尺 Caliper` 和一句话——`说出你要的零件，它来建模，每一步都实测。`
  2. 安装：两个代码框（Windows、Mac），各带一个 `复制` 按钮；下面一行系统要求——`Windows 10/11（64 位），或 Apple 芯片的 Mac（macOS 14 及以上）。需要一个大模型服务的 API key，推荐 DeepSeek。`
  3. 它怎么工作：五步流程（澄清、确认、规划、逐阶段建模与实测、终检与交付），每步一句话。
  4. `在线看一个示例` 链接到 `demo/`；`在 GitHub 上看源码和说明` 链接到仓库。
  5. 页脚：课程作业的说明、SCA 和 three.js 的许可证。
  主页上不写任何成功率数字。

- [ ] **Step 1：** 写测试 `tests/test_desk_export.py`：
  - `test_export_layout`：四样东西都在；`state.json` 能解析、`demo` 为真、有版本。
  - `test_export_has_no_absolute_paths_or_secrets`：全部导出文件里搜不到盘符路径、`Users`、用户主目录、`sk-`。
  - `test_export_only_whitelisted_files`。
  - `test_static_mode_api`（`node --test`）：静态模式下 `get("/api/sessions/x/state")` 返回 `state.json` 的内容，`post` 返回"只读"。
  - `test_site_is_up_to_date`：对 `cad_agent/desk/demo_data/phone_stand` 重新导出，和仓库里的 `site/demo/` 逐文件相同。
  - `test_homepage_content`：`site/index.html` 里有两条安装命令（和 `maintenance.INSTALL_PS1`、`INSTALL_SH` 的地址一致）、系统要求那一行的原文、指向 `demo/` 的链接；没有外部脚本、样式、字体；没有 `%` 结尾的成功率数字。
  - `test_pages_workflow_publishes_site`。
- [ ] **Step 2：** 运行，确认失败；实现；导出 `site/demo/`，写 `site/index.html`；`pages.yml` 的注释更新成新的导出命令。
- [ ] **Step 3：** 本地看一遍：用 Python 自带的静态文件服务打开 `site/`，主页的复制按钮能用，示例能转 3D、能切阶段、能看检查和版本。浅色、深色各看一遍。
- [ ] **Step 4：** 运行全部测试，提交：`feat: 产品主页和在线回放`。这时旧的 `test_committed_site_is_up_to_date`、`test_export_static_site` 会因为 `site/` 变了而失败——它们在 Task 6 的删除清单里，所以 **Task 5 和 Task 6 合成一次提交**：先做完 Task 6 再跑全部测试、再提交。
- [ ] **Step 5：** **停下来问用户：可以推送并更新 GitHub Pages 吗？** 推送后请用户打开主页确认。

---

### Task 6：旧网页界面退役

**Files：** Delete `cad_agent/web/server.py`、`cad_agent/web/__main__.py`、`cad_agent/web/export.py`、`cad_agent/web/static/`（three.js 先搬走）、`start_web.bat`、`start_replay.bat`、`tests/test_web.py`；Create `cad_agent/desk/replay.py`、`tests/test_desk_legacy.py`；Modify `cad_agent/desk/hub.py`、`cad_agent/desk/server.py`、`cad_agent/desk/view.py`、`pyproject.toml`、`README.md`

这是设计文档第 8 节批准的退役。做法：
- three.js 的四个文件搬到 `cad_agent/desk/static/vendor/three/`，新界面的服务改从这里取。
- 仍在使用的代码搬家，行为不变：`cad_agent/web/events.py` → `cad_agent/desk/events.py`；`cad_agent/web/app.py` 里的 `LiveSession`、`version_summary`、`ReplayApp` 读日志的部分 → `cad_agent/desk/replay.py`。搬完后删掉 `cad_agent/web/` 整个目录，所有引用改到新位置。
- `scripts/backfill_stl.py` 留着。`demo/phone_stand` 留着（`cad_agent/desk/demo_data/` 里是它的副本）。

`tests/test_web.py` 里每条测试的去向（计划 1、计划 3 往这个文件里加的测试也在内）：

| 去向 | 测试 |
|---|---|
| 搬到 `tests/test_desk_legacy.py`，只改导入路径，断言不动 | `test_describe_event_cases`、`test_describe_new_events`、`test_fold_structured_entries_and_stage`、`test_fold_parses_old_logs_without_structured_fields`、`test_fold_live_turn_shows_activity_and_stage`、`test_live_session_notifies_listener_and_survives_its_errors`、`test_replay_skips_broken_lines_and_needs_a_log`、`test_demo_session_is_in_the_repo`、`test_version_summary_tolerates_missing_files`、`test_backfill_stl` |
| 删除；由计划 3 的 `tests/test_desk_server.py`、`test_desk_workbench.py` 里的测试接替 | `test_question_flow`、`test_confirm_flow_carries_the_brief`、`test_delivery_fills_checks_versions_and_stage`、`test_busy_returns_409_and_reports_progress`、`test_bad_messages_400`、`test_agent_crash_is_reported_and_service_keeps_going`、`test_failed_build_turn_shows_failure`、`test_files_whitelist`、`test_diff_endpoint`、`test_reset_starts_a_clean_session`、`test_unknown_route_and_localhost_only`、`test_web_state_with_staged_session` |
| 删除；由 `tests/test_desk_hub.py`、`test_desk_demo.py` 接替 | `test_replay_matches_the_live_session`、`test_replay_is_read_only_over_http`、`test_main_replay` |
| 删除；由 `tests/test_app.py`、`test_cli.py` 接替 | `test_main_reports_a_missing_key`、`test_main_reports_a_missing_config`、`test_bind_server_tries_the_next_port`、`test_build_live_agent_uses_a_live_session` |
| 删除；由 `tests/test_desk_static.py`、`test_desk_style.py` 接替 | `test_static_files_offline_ready`、`test_stylesheet_follows_the_visual_spec`、`test_page_scripts_are_valid_modules`、`test_pages_are_served_with_the_right_types` |
| 删除；由 `tests/test_desk_export.py` 接替 | `test_export_static_site`、`test_committed_site_is_up_to_date` |
| 删除；功能没有了 | `test_start_scripts_and_readme`、`test_public_mode_is_gone` |

- [ ] **Step 1：** 删之前，逐条核对上表"接替"一栏：打开被删的测试，确认它断言的每一件事在新测试里都有；新测试里缺的，先补到对应的新测试文件里。把核对结果（每条旧测试对应哪条新测试）写进 `docs/progress.md`。
- [ ] **Step 2：** 加一条测试 `tests/test_desk_legacy.py::test_old_web_package_is_gone`：`cad_agent.web` 不能导入；仓库里没有 `start_web.bat`、`start_replay.bat`；`three.module.js` 在新位置；`REVISION` 仍是 `'160'`。
- [ ] **Step 3：** 按上面的做法搬家和删除；`pyproject.toml` 的 `package-data` 去掉旧网页的条目。
- [ ] **Step 4：** 运行全部测试；和 Task 5 一起提交：`feat: 产品主页和在线回放；旧网页界面退役`。

---

### Task 7：README 重写和 Mac 清单

**Files：** Modify `README.md`、`CLAUDE.md`（只改"命令环境"里和启动有关的一句）；Create `docs/mac-checklist.md`、`tests/test_readme.py`

- README 的结构（标题照这个顺序）：
  1. `# 卡尺 Caliper`：一句话、一张界面截图（用计划 3 走查时截的图，放进 `docs/images/`）。
  2. `## 安装`：两条命令；系统要求；第一次打开要做什么（选服务、填 key）。
  3. `## 装不上怎么办`：`CALIPER_MIRROR=1` 的用法；从 GitHub 下载压缩包、解压后把 `CALIPER_SOURCE` 指到那个目录再运行脚本；Windows 缺 WebView2 时怎么办；`caliper doctor` 每一项的含义。
  4. `## 怎么用`：三栏各是什么；一次完整的过程（提需求、回答、确认、规划、逐阶段、交付）；参数面板直接改数；版本对比和导出；存为案例；示例会话。
  5. `## 它是怎么保证质量的`：程序管流程；分阶段、先写检查再建模；终检的参数扰动验证；看图审查；每一条各两三句，并写明它拦得住什么、拦不住什么。
  6. `## 命令`：`caliper`、`--browser`、`--cli`、`doctor`、`update`、`uninstall`。
  7. `## 模型服务和密钥`：支持哪些；key 存在哪、怎么换、怎么删；哪些是"未用真实接口验证"的（Claude、DeepSeek 以外的预设、看图审查）。
  8. `## 数据放在哪`。
  9. `## 给开发者`：从源码运行、跑测试、评测脚本（含 ¥15 套餐的命令和"会花钱"的提醒）、项目结构、四个流程开关。
  10. `## 验证到什么程度`：如实写——全部测试在 Windows 和 Mac 上通过；Mac 的界面由组员按清单人工看过（看过之后才写）；**第二版没有做过真实模型的成功率评测**，1.1 版的数字在哪份文档里；已知的限制（只做单零件、Intel Mac 不支持、中文用户名的 Windows 没有实机测过就写没测过）。
  11. `## 参考与致谢`：SCA 和它的官方 Agent Skill（借鉴了方法，文档在运行时从安装包读取）、three.js、uv、pywebview；课程和作业的链接。
- `docs/mac-checklist.md`：给有 M 芯片 Mac 的组员照着做的清单，每项一个勾选框和一栏"看到了什么"：系统版本和芯片；运行安装命令（记下用了多久）；"应用程序"里有 Caliper、能打开窗口；`caliper doctor` 的输出（贴进来）；引导页三步；用 `caliper --demo-script` 走完整流程（步骤和 `docs/walkthrough-windows.md` 相同）；3D 的旋转、缩放、平移手感；阶段刻度；参数面板改数；深浅色切换；字体有没有显示成方块或回退得很难看；下载 STEP 和"在文件夹中显示"；关掉重开会话还在；`caliper uninstall`。最后是签名和日期。

- [ ] **Step 1：** 写测试 `tests/test_readme.py`：`test_readme_sections_in_order`（上面 11 个标题依次出现）；`test_readme_install_commands_match`（和 `maintenance` 里的地址一致）；`test_readme_has_no_success_rate_for_v2`（"验证到什么程度"一节里有"没有做过真实模型的成功率评测"这句话）；`test_readme_mentions_unverified_parts`；`test_mac_checklist_has_all_items`（每项都有勾选框，最后有签名栏）；`test_readme_has_no_old_commands`（没有 `start_web.bat`、`start_public`、`python -m cad_agent.web`）。
- [ ] **Step 2：** 运行，确认失败；写 README 和清单；运行全部测试，提交：`docs: 重写 README，加 Mac 人工清单`。
- [ ] **Step 3：** 告诉用户：请有 M 芯片 Mac 的组员按 `docs/mac-checklist.md` 做一遍，把填好的清单发回来。清单回来之前，README"验证到什么程度"里关于 Mac 界面的那一句写"还没有人工看过"。

---

### Task 8：发布

- [ ] **Step 1：** 确认：全部测试通过；持续集成在两个平台上通过；`docs/walkthrough-windows.md` 写完；Mac 清单已经填好交回（没交回就停在这里，告诉用户还差什么）。
- [ ] **Step 2：** 根据交回的 Mac 清单更新 README 里关于 Mac 的那一句；清单里发现的问题逐条处理或写进已知限制。提交：`docs: 记录 Mac 人工验证结果`。
- [ ] **Step 3：** **停下来问用户：可以推送并打 `v2.0.0` 标签吗？** 说明安装脚本默认装的就是这个标签，打了之后公开的安装命令才真正可用。
- [ ] **Step 4：** 得到同意后：推送；打标签并推送标签；在一台没有装过卡尺的 Windows 电脑（或一个新的 Windows 用户）上，用 README 里的那一行命令从 GitHub 实际装一次，`caliper doctor` 全部正常、能开窗口。把结果写进 `docs/progress.md`。这一步对应设计文档成功标准 4。
- [ ] **Step 5：** 在 `docs/progress.md` 写"第二版小结"：四份计划各自的测试数、全部偏离的编号、六条成功标准逐条的达成情况（没达成的写明原因）、没有用真实接口验证的部分、付费评测还没有做。

---

## 做完之后

付费评测（README 里的 ¥15 套餐）由用户决定什么时候运行。运行之后把结果写成 `docs/results-v2.md`，并把 README"验证到什么程度"一节里的那句话换成实际的数字。这不在本计划的任务里。
