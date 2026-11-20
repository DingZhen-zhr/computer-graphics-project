# uv 与安装：实测笔记（第二版计划 4 Task 3）

安装脚本 `install.ps1`、`install.sh` 里所有 uv 的用法都以这份笔记为准。每一条写明来源：官方文档（docs.astral.sh/uv，2026-11-19 读）或本机实测（Windows 11 家庭中文版 10.0.26200，uv 0.13.9）。

## 1. uv 的官方安装脚本

- 文档（Installation 页）给的命令：
  - Windows：`powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`
  - Mac：`curl -LsSf https://astral.sh/uv/install.sh | sh`
  - 可以在地址里写死版本：`https://astral.sh/uv/0.13.9/install.ps1`。我们不写死，跟着官方的最新版走。
- 装到哪里（Storage 页、环境变量页）：用户的可执行目录，默认 `~/.local/bin`（Windows 是 `%USERPROFILE%\.local\bin`）。环境变量 `UV_INSTALL_DIR` 可以改。
- 改不改 PATH：文档说安装脚本"可能会改 shell 的配置文件，让 uv 进 PATH"，设 `UV_NO_MODIFY_PATH` 可以不改。我们不设：用户以后要在新终端里直接用 `caliper`，需要这个目录在 PATH 里。
- 本机实测（2026-11-19）：`irm https://astral.sh/uv/install.ps1 -TimeoutSec 20 | iex` 用了 12.7 秒，装了 `uv.exe`、`uvx.exe`、`uvw.exe` 到 `C:\Users\18258\.local\bin`，版本 `uv 0.13.9 (6b2d39dcc 2026-11-17)`。它把这个目录加进了当前用户的 PATH，但**当前这个 PowerShell 窗口里还没有**（它自己提示"重开终端或运行 `$env:Path = ...`"），所以安装脚本装完 uv 后要自己把 `~/.local/bin` 加进本次的 PATH。
- 安装脚本本身从哪里下载 uv：文档说默认是 uv 的 GitHub Releases，可用 `UV_INSTALLER_GITHUB_BASE_URL` 或 `UV_DOWNLOAD_URL` 换地址。国内没有找到可靠的 uv 发布镜像，所以 `CALIPER_MIRROR=1` 不管这一步；这一步下不下来时，README"装不上怎么办"里写了先自己装好 uv 的办法。

## 2. `uv tool install`

- 文档：`uv tool install [OPTIONS] <PACKAGE>`；`--python`（`-p`）指定建工具环境用的 Python；`--force` 在可执行文件已存在时覆盖；`--reinstall` 重装全部包。
- 本机 `uv tool install --help` 确认有 `--force`、`--python`、`--reinstall`、`--reinstall-package`、`--default-index`（环境变量 `UV_DEFAULT_INDEX`）。
- 指定 Python 版本：`--python 3.12`。文档说找不到合适的 Python 时 uv 默认会自动下载；本机实测第一次用 `--python 3.12` 时它下载了 `cpython-3.12.16-windows-x86_64-none`（21.3 MiB）。所以用户电脑上不需要预先有 Python。
- **从 git 地址装需要电脑上有 git 程序。** 文档没写这一点；本机实测：把 git 从 PATH 里拿掉后，`uv tool install --python 3.12 "git+https://github.com/pypa/sampleproject@v4.0.0"` 报 `error: Git operation failed`、`cause: Git executable not found. Ensure that Git is installed and available.`，返回码 2。一台干净的 Windows 电脑通常没有 git，Mac 上没装命令行工具时 `/usr/bin/git` 只是个会弹窗的占位。所以安装脚本在默认来源、又找不到 git 时，改用同一个标签的压缩包：`caliper-cad @ https://github.com/DingZhen-zhr/computer-graphics-project/archive/refs/tags/v2.0.0.zip`（偏离 D16）。
- 从本地目录装：`uv tool install --python 3.12 --force <目录>`（见第 5 节的实测）。

## 3. 镜像和超时

- PyPI 镜像：文档里现在的写法是 `--default-index` / 环境变量 `UV_DEFAULT_INDEX`；`--index-url` / `UV_INDEX_URL` 标着"已弃用，改用 `UV_DEFAULT_INDEX`"。我们用 `UV_DEFAULT_INDEX=https://pypi.tuna.tsinghua.edu.cn/simple`（清华）。
- Python 下载镜像：环境变量 `UV_PYTHON_INSTALL_MIRROR`，值是一个基础地址，替换掉下载地址里 `.../python-build-standalone/releases/download` 这一段。本机 `uv python list 3.12 --show-urls` 显示 uv 0.13.9 默认从 `https://releases.astral.sh/github/python-build-standalone/releases/download/20261110/cpython-3.12.16%2B20261110-x86_64-pc-windows-msvc-install_only_stripped.tar.gz` 下载。把前缀换成 `https://registry.npmmirror.com/-/binary/python-build-standalone` 后，同一个文件的 HEAD 请求返回 200（0.5 秒）。南京大学的 `https://mirror.nju.edu.cn/github-release/astral-sh/python-build-standalone` 也是 200。我们用 npmmirror。
- 清华 PyPI 镜像上 `simple/simplecadapi/` 返回 200（0.4 秒），阿里云的也是 200。
- 超时：文档里 `UV_HTTP_CONNECT_TIMEOUT` 是"连接服务器的超时（秒），默认 10"，`UV_HTTP_TIMEOUT` 是"读的超时（秒），默认 30"，`UV_HTTP_RETRIES` 默认 3。安装脚本设 `UV_HTTP_CONNECT_TIMEOUT=20`（计划要求连接 20 秒）；读超时用 uv 的默认值。脚本自己下载 uv 安装脚本时：PowerShell 用 `Invoke-RestMethod -TimeoutSec 20`，Mac 用 `curl --connect-timeout 20`。

## 4. `uv tool dir`、`uv tool update-shell`、`uv tool uninstall`

- 文档：`uv tool dir` 显示工具的安装目录，`uv tool dir --bin` 显示工具可执行文件的目录；可执行文件在 Unix 上是符号链接，在 Windows 上是复制过去的。
- 本机实测：`uv tool dir` 输出 `C:\Users\18258\AppData\Roaming\uv\tools`，`uv tool dir --bin` 输出 `C:\Users\18258\.local\bin`（各一行，没有别的内容）。工具自己的 Python 环境在 `<tool dir>\caliper-cad\`，Windows 上解释器是 `Scripts\python.exe`，Mac 上是 `bin/python`。
- `uv tool update-shell`：文档说它"把可执行目录加进常见 shell 配置文件里的 PATH"；`--help` 第一行是 "Ensure that the tool executable directory is on the `PATH`"。安装脚本只在 `uv tool dir --bin` 不在当前 PATH 里时才运行它（比如用户以前用别的办法装过 uv）。
- `uv tool uninstall <NAME>...`、`uv tool list`：本机 `--help` 确认了用法。`caliper uninstall` 最后在后台运行 `uv tool uninstall caliper-cad`。

## 5. 本机实测安装（Task 3 Step 4，2026-11-19）

用户同意后在这台电脑上真的装了，装完保留。命令（按 UTF-8 读进来再执行，见第 6 节）：

```
$env:CALIPER_SOURCE = "."
Get-Content -Raw -Encoding UTF8 install.ps1 | iex
```

1. **第一次装**：106 秒，返回码 0。uv 已经在（`~/.local/bin/uv.exe`）；它解析了 77 个包，下载了 Python 3.12.16（21 MiB）和 SCA、OCP（`cadquery-ocp-novtk` 44 MiB）、marimo（38 MiB）等。占用：工具环境 `%APPDATA%\uv\tools\caliper-cad` 约 556 MB，uv 管的 Python `%APPDATA%\uv\python` 约 63 MB，uv 的下载缓存 `%LOCALAPPDATA%\uv\cache` 约 570 MB（缓存可以用 `uv cache clean` 清掉）。
2. **结果**：`caliper --version` 打印 `卡尺 Caliper 2.0.0`。开始菜单和桌面都有"卡尺 Caliper.lnk"，目标是 `C:\Users\18258\.local\bin\caliper-app.exe`。`caliper doctor` 十项全是 ✓（这台电脑设了 `DEEPSEEK_API_KEY` 环境变量，所以"密钥"一项是 ✓；它只说了来源，没有显示 key 的任何一位），最后一行"全部正常"。
3. **双击有没有黑窗口**：从桌面快捷方式打开，进程是 `caliper-app.exe → 工具环境的 pythonw.exe → uv 管的 pythonw.exe`，只有一个标题为"卡尺 Caliper"的窗口，没有控制台窗口。窗口左上角的小图标是 Python 的默认图标（`caliper-app.exe` 是 uv 生成的启动器，不带图标；pywebview 在 Windows 上不能另设窗口图标）。快捷方式本身用的是包里的 `icon.ico`。
4. **实测找出并改掉的两个问题**：
   - 装好的程序打开后三栏是空的。原因是 three.js 放在 `cad_agent/web/static/vendor/three/`，而 `pyproject.toml` 的 `package-data` 只收了 `desk/static`，装出来的包里没有 three.js，页面的脚本模块整个加载失败。从源码运行时看不出来。先加了测试 `test_package_ships_everything_the_page_loads`（看到它失败），再在 `package-data` 里加上 `web/static/vendor/three/*`（Task 6 把 three.js 搬到 `desk/static/vendor/three/` 后去掉这一条，测试照样检查）。重装后打开，界面正常，"安装测试"会话在。
   - 卡尺开着时重装，uv 报 `failed to remove directory ...\caliper-cad\Scripts: 拒绝访问 (os error 5)`：Windows 不让替换正在运行的程序文件。原来脚本接着打印的是网络方面的提示，不对。改成：安装前先查有没有从 uv 工具目录里运行的卡尺进程，有就说"卡尺正在运行：caliper-app（…）、pythonw（…）。……请先关掉所有卡尺窗口和终端里运行的 caliper"，以返回码 1 停下，不给网络提示。实测开着窗口运行安装命令，看到了这句话，什么都没改。同样的原因，`caliper update` 在 Windows 上改成用 `start` 开一个新窗口、先等 3 秒（让 `caliper update` 自己退出）再运行安装脚本，窗口留着看结果。
5. **再装一次（Review Focus 3 的人工版）**：先用装好的程序（剧本模式，假模型，不需要 key）在真实的数据目录里建了一个会话"安装测试"、把设置里的 `run_timeout_s` 改成 61，然后关掉窗口再运行安装命令：返回码 0，自检全部正常；会话还在（打开窗口能看到它和它的提问卡片），`settings.toml` 里仍是 `run_timeout_s = 61`。钥匙串没有动（安装脚本不碰钥匙串）。
6. **没有 git 时的压缩包安装（D16）**：把 git 从 PATH 里拿掉，用 `git archive` 做一个和 GitHub 压缩包一样带顶层目录的 zip，`uv tool install --python 3.12 --force "caliper-cad @ file:///…/caliper-src.zip"` 装进临时目录：返回码 0，`caliper --version` 正常。说明 `caliper-cad @ <压缩包地址>` 这种写法不需要 git。（真正的 GitHub 压缩包地址要等打了 `v2.0.0` 标签才有，Task 8 实测。）
7. **没有实测的**：`CALIPER_MIRROR=1` 只核对了两个镜像上对应文件的 HEAD 请求返回 200（第 3 节），没有在缓存为空的电脑上完整走一遍；`install.sh` 只在这台 Windows 上用 Git 自带的 sh 跑了演示模式和平台检查，真正在 Mac 上安装要等持续集成（Task 4）和组员的 Mac 清单。

## 6. install.ps1 的编码（偏离 D17）

- 本机实测（Windows PowerShell 5.1，中文系统）：文件带 UTF-8 BOM 时，`irm … | iex` 把 BOM 和第一个词连在一起当成命令名，开头报一行红字（试了换行、空格、分号、块注释、赋值五种第一行，都一样）；文件不带 BOM 时，`powershell -File install.ps1` 按系统编码 936 读，中文乱掉、直接语法错误。
- 用一个按 GitHub raw 的方式（`Content-Type: text/plain; charset=utf-8`）提供文件的本机小服务实测：不带 BOM 时 `irm http://127.0.0.1:<端口>/install.ps1 | iex` 中文正常、没有红字，结束后窗口还在。
- 所以 `install.ps1` 是不带 BOM 的 UTF-8；在本地运行时用 `Get-Content -Raw -Encoding UTF8 .\install.ps1 | iex`。
- 用 `irm | iex` 运行时脚本是在用户自己的 PowerShell 里执行的：脚本里不能 `exit`（会关掉用户的窗口），出错时设 `$LASTEXITCODE` 后正常结束；改过的 uv 环境变量结束时还原。整段代码放在 `& { … }` 里，变量不留在用户的会话里。

## 7. Windows 上怎么查 WebView2 运行时（Task 1 用）

- 微软的说法：常青版 WebView2 运行时在 EdgeUpdate 的注册表项 `Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}` 下有一个值 `pv`（版本号）；按机器安装时在 `HKLM\SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\…`，按用户安装时在 `HKCU\Software\Microsoft\EdgeUpdate\Clients\…`。`pv` 为空或 `0.0.0.0` 表示没装好。pywebview 6.2.1 自己判断时（`webview/platforms/winforms.py` 的 `_is_chromium`）也是查这几处。
- 本机实测：HKLM 的 WOW6432Node 下 `pv = 157.0.4341.60`，HKCU 下没有这一项。
- `cad_agent/doctor.py` 的 `_webview2_version` 依次查 HKLM（WOW6432Node）、HKLM、HKCU，只读不写。

## 8. Windows 快捷方式和系统编码（偏离 D20）

- `WScript.Shell` 的 `CreateShortcut` 会把路径按系统编码（ANSI 代码页）转换。系统编码表示不了的字会变成 `?`。
  - 文件名里有这种字：`Save()` 报 "Unable to save shortcut"（持续集成的英文 Windows 上，"卡尺 Caliper.lnk" 就是这样失败的）；
  - 目标路径里有这种字：设置 `TargetPath` 就报"值不在预期的范围内"。
  - 本机实测（中文 Windows，GBK）：用泰文复现了这两种情况；"卡尺"在 GBK 里能表示，所以本机正常。
- 改用 IShellLinkW（`Add-Type` 编译的一小段 C#）后，泰文的名字、目标、工作目录、说明、图标全部正确，用 Shell.Application 读回来核对过。
- 2026-11-20 用改过的脚本在本机重装了一次（`CALIPER_SOURCE=.`）：两个快捷方式都建好了，读回来的目标是 `C:\Users\18258\.local\bin\caliper-app.exe`，图标是包里的 `icon.ico`，自检全部正常。
- 读快捷方式也别用 `WScript.Shell`（同样的问题）；用 `(New-Object -ComObject Shell.Application).NameSpace(目录).ParseName(文件名).GetLink`。

## 9. 从卡尺升级（3.0 计划 1）

- 安装脚本装的是 `datum-cad`，命令是 `datum`、`datum-app`。旧的 `caliper-cad` 是另一个 uv 工具，两者可以同时在。
- 第 3 步先运行 `uv tool list`，里面有 `caliper-cad` 时打印"检测到旧版……不需要的话运行：uv tool uninstall caliper-cad"，**不自动卸载**。演示模式下这一步只打印，不调用 uv。
- 第 4 步删掉旧快捷方式：Windows 是开始菜单和桌面上的 `卡尺 Caliper.lnk`，Mac 是 `~/Applications/Caliper.app`。删之前打印一行，演示模式下只打印。然后照常建 `Datum 基准.lnk` / `~/Applications/Datum.app`。
- 数据和 key 不归安装脚本管：第一次启动（或安装脚本最后的 `datum doctor`）时，程序把 `%LOCALAPPDATA%\Caliper`（Mac `~/Library/Application Support/Caliper`）复制成 `Datum`。钥匙串里新服务名 `datum` 没有 key 时，去旧服务名 `caliper` 找，找到就复制一份；每个服务只回退一次（记在数据目录的 `key_migration.json`）。旧目录、旧 key 都不删。
- 选项环境变量改名：`DATUM_SOURCE`、`DATUM_MIRROR`、`DATUM_NO_SHORTCUT`、`DATUM_DRY_RUN`。旧的 `CALIPER_*` 不再认。
- 没有实测：真的在装着第二版的电脑上从 GitHub 装 v3.0.0（要等打了 `v3.0.0` 标签，计划 5 做）。这次只在本机跑了两个脚本的演示模式。
