#!/bin/sh
# Datum 基准 一行安装脚本（Mac）
#
# 用法（在"终端"里粘贴这一行）：
#   curl -fsSL https://raw.githubusercontent.com/DingZhen-zhr/computer-graphics-project/master/install.sh | sh
#
# 选项都用环境变量传（"下载后直接执行"的用法传不了参数），写在 sh 前面：
#   DATUM_SOURCE           从哪里装：一个 git 地址，或本地目录。默认是本仓库的发布标签 v3.0.0
#   DATUM_MIRROR=1         PyPI 和 Python 的下载走国内镜像
#   DATUM_NO_SHORTCUT=1    不建"应用程序"里的 Datum
#   DATUM_DRY_RUN=1        只打印每一步要做什么，不执行
# 例如：curl -fsSL https://raw.githubusercontent.com/DingZhen-zhr/computer-graphics-project/master/install.sh | DATUM_MIRROR=1 sh
#
# 这个脚本只往当前用户的目录里写东西，不需要管理员权限，不改系统设置。
# 除了 uv 的官方安装脚本，它不下载执行任何别的脚本。每一步做之前先打印要做什么。

set -u

DEFAULT_SOURCE="git+https://github.com/DingZhen-zhr/computer-graphics-project@v3.0.0"
ARCHIVE_SOURCE="datum-cad @ https://github.com/DingZhen-zhr/computer-graphics-project/archive/refs/tags/v3.0.0.zip"
UV_INSTALLER="https://astral.sh/uv/install.sh"
PYPI_MIRROR="https://pypi.tuna.tsinghua.edu.cn/simple"
PYTHON_MIRROR="https://registry.npmmirror.com/-/binary/python-build-standalone"
HELP_URL="https://github.com/DingZhen-zhr/computer-graphics-project#装不上怎么办"
OLD_VERSION_HINT='检测到旧版"卡尺"（caliper-cad）。它可以和 Datum 同时存在；不需要的话运行：uv tool uninstall caliper-cad'
RANGE="支持的范围：Apple 芯片的 Mac，macOS 14 及以上；或 Windows 10/11（64 位）。"

SOURCE="${DATUM_SOURCE:-${DEFAULT_SOURCE}}"
DRY_RUN="${DATUM_DRY_RUN:-}"

say() { printf '%s\n' "$*"; }
step() { printf '[%s/5] %s\n' "$1" "$2"; }
is_dry() { [ "${DRY_RUN}" = "1" ]; }
show_help() {
    say ""
    say "装不上的话可以这样试："
    say "  1. 检查网络：能不能打开 github.com 和 pypi.org；用代理的话确认代理开着。"
    say "  2. 改走国内镜像再装一次：把安装命令最后的 sh 换成 DATUM_MIRROR=1 sh。"
    say "  3. 看 README 的“装不上怎么办”一节（里面有下载压缩包本地安装的办法）：${HELP_URL}"
}
fail() { say "$2" >&2; [ "${3:-}" = "help" ] && show_help >&2; exit "$1"; }
find_uv() {
    if command -v uv >/dev/null 2>&1; then command -v uv; return 0; fi
    if [ -x "${HOME}/.local/bin/uv" ]; then say "${HOME}/.local/bin/uv"; return 0; fi
    return 1
}
has_real_git() {
    # macOS 自带的 /usr/bin/git 在没装命令行工具时只是个占位，一运行就弹窗，不算
    command -v git >/dev/null 2>&1 || return 1
    [ "$(command -v git)" != "/usr/bin/git" ] && return 0
    xcode-select -p >/dev/null 2>&1
}

# ---------------------------------------------------------------- 1
step 1 "检查这台电脑是否支持"
OS_NAME="$(uname -s 2>/dev/null || echo unknown)"
ARCH="$(uname -m 2>/dev/null || echo unknown)"
if [ "${OS_NAME}" != "Darwin" ]; then
    fail 2 "这台电脑的系统是 ${OS_NAME}，Datum 不支持。${RANGE} Windows 请用 install.ps1。"
fi
if [ "${ARCH}" != "arm64" ]; then
    fail 2 "这台 Mac 的处理器是 ${ARCH}（Intel 芯片），Datum 只支持 Apple 芯片的 Mac：SCA 没有 Intel Mac 的安装包。${RANGE}
如果你的 Mac 其实是 Apple 芯片，可能是终端开了 Rosetta：在“访达”里找到“终端”，显示简介，取消勾选“使用 Rosetta 打开”，再试一次。"
fi
MAC_VERSION="$(sw_vers -productVersion 2>/dev/null || echo 0)"
MAC_MAJOR="${MAC_VERSION%%.*}"
case "${MAC_MAJOR}" in ''|*[!0-9]*) MAC_MAJOR=0 ;; esac
if [ "${MAC_MAJOR}" -lt 14 ]; then
    fail 2 "这台 Mac 的系统是 macOS ${MAC_VERSION}，Datum 需要 macOS 14 及以上。${RANGE}"
fi
say "  macOS ${MAC_VERSION}，Apple 芯片（${ARCH}），可以安装。"

# ---------------------------------------------------------------- 2
step 2 "准备 uv（用来准备独立的 Python 3.12 环境）"
if UV="$(find_uv)"; then
    say "  已经有 uv：${UV}"
elif is_dry; then
    say "  （只打印，不执行）没有找到 uv，会运行 uv 的官方安装脚本：${UV_INSTALLER}"
    UV="uv"
else
    say "  没有找到 uv，运行 uv 的官方安装脚本：${UV_INSTALLER}"
    TMP_SCRIPT="$(mktemp)" || fail 1 "建不了临时文件。" help
    if ! curl -LsSf --connect-timeout 20 -o "${TMP_SCRIPT}" "${UV_INSTALLER}"; then
        rm -f "${TMP_SCRIPT}"
        fail 1 "uv 的安装脚本下载失败。" help
    fi
    if ! sh "${TMP_SCRIPT}"; then
        rm -f "${TMP_SCRIPT}"
        fail 1 "uv 没装上，原因见上面的输出。" help
    fi
    rm -f "${TMP_SCRIPT}"
    PATH="${HOME}/.local/bin:${PATH}"
    export PATH
    UV="$(find_uv)" || fail 1 "uv 的安装脚本运行完了，但还是找不到 uv。" help
    say "  uv 装好了：${UV}"
fi

# ---------------------------------------------------------------- 3
step 3 "安装 Datum（第一次要下载 Python 和 SCA，大约几百 MB，请耐心等）"
UV_HTTP_CONNECT_TIMEOUT=20
export UV_HTTP_CONNECT_TIMEOUT
if [ "${DATUM_MIRROR:-}" = "1" ]; then
    say "  走国内镜像：PyPI 用 ${PYPI_MIRROR}，Python 用 ${PYTHON_MIRROR}"
    UV_DEFAULT_INDEX="${PYPI_MIRROR}"
    UV_PYTHON_INSTALL_MIRROR="${PYTHON_MIRROR}"
    export UV_DEFAULT_INDEX UV_PYTHON_INSTALL_MIRROR
fi
if [ -d "${SOURCE}" ]; then
    SOURCE="$(cd "${SOURCE}" && pwd)"
else
    case "${SOURCE}" in
        git+*)
            if ! has_real_git; then
                if [ "${SOURCE}" = "${DEFAULT_SOURCE}" ]; then
                    say "  这台电脑没有 git，改从 GitHub 下载同一个版本的压缩包来装。"
                    SOURCE="${ARCHIVE_SOURCE}"
                else
                    fail 1 "从 git 地址安装需要先装 git：${SOURCE}" help
                fi
            fi
            ;;
    esac
fi
if is_dry; then
    say '  （只打印，不执行）uv tool list：看有没有装着旧版"卡尺"（caliper-cad），有的话只提示，不卸载'
elif "${UV}" tool list 2>/dev/null | grep -q '^caliper-cad '; then
    say "  ${OLD_VERSION_HINT}"
fi
if is_dry; then
    say "  （只打印，不执行）uv tool install --python 3.12 --force \"${SOURCE}\""
    BIN="<uv 工具目录>"
    TOOL_DIR="<uv 工具目录>"
else
    say "  运行：uv tool install --python 3.12 --force \"${SOURCE}\""
    "${UV}" tool install --python 3.12 --force "${SOURCE}" || fail 1 "安装没有成功，原因见上面 uv 的输出。" help
    BIN="$("${UV}" tool dir --bin)"
    TOOL_DIR="$("${UV}" tool dir)"
    case ":${PATH}:" in
        *":${BIN}:"*) ;;
        *)
            say "  ${BIN} 还不在 PATH 里，运行 uv tool update-shell 把它加进终端的配置文件"
            "${UV}" tool update-shell || say "  没能自动加上；可以自己把 ${BIN} 加进 PATH。"
            PATH="${BIN}:${PATH}"
            export PATH
            ;;
    esac
fi

# ---------------------------------------------------------------- 4
step 4 "在“应用程序”里建 Datum"
APP="${HOME}/Applications/Datum.app"
OLD_APP="${HOME}/Applications/Caliper.app"
# 第二版的 Caliper.app 指向旧程序，删掉，免得点错
if is_dry; then
    say "  （只打印，不执行）有旧版的 ${OLD_APP} 的话删掉它"
elif [ -d "${OLD_APP}" ]; then
    say "  删除旧版的 ${OLD_APP}"
    rm -rf "${OLD_APP}"
fi
if [ "${DATUM_NO_SHORTCUT:-}" = "1" ]; then
    say "  设了 DATUM_NO_SHORTCUT=1，不建。"
elif is_dry; then
    say "  （只打印，不执行）建 ${APP}，双击时运行 ${BIN}/datum-app"
else
    say "  建 ${APP}，双击时运行 ${BIN}/datum-app"
    rm -rf "${APP}"
    mkdir -p "${APP}/Contents/MacOS" "${APP}/Contents/Resources" || fail 1 "建不了 ${APP}。"
    cat > "${APP}/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>Datum</string>
  <key>CFBundleDisplayName</key><string>Datum 基准</string>
  <key>CFBundleIdentifier</key><string>io.github.dingzhen-zhr.datum</string>
  <key>CFBundleExecutable</key><string>Datum</string>
  <key>CFBundleIconFile</key><string>icon</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>3.0.0</string>
  <key>LSMinimumSystemVersion</key><string>14.0</string>
  <key>NSHighResolutionCapable</key><true/>
</dict>
</plist>
PLIST
    cat > "${APP}/Contents/MacOS/Datum" <<LAUNCH
#!/bin/sh
exec "${BIN}/datum-app" "\$@"
LAUNCH
    chmod +x "${APP}/Contents/MacOS/Datum"
    ICON="$("${TOOL_DIR}/datum-cad/bin/python" -I -c "import cad_agent, pathlib; print(pathlib.Path(cad_agent.__file__).parent / 'desk' / 'static' / 'icon.icns')" 2>/dev/null || true)"
    if [ -n "${ICON}" ] && [ -f "${ICON}" ]; then
        cp "${ICON}" "${APP}/Contents/Resources/icon.icns"
    fi
    touch "${APP}"
fi

# ---------------------------------------------------------------- 5
step 5 "自检（datum doctor）"
if is_dry; then
    say "  （只打印，不执行）${BIN}/datum doctor"
else
    "${BIN}/datum" doctor || fail 1 "自检里有不能用的项（标着 ✗ 的），按它下面的提示处理；处理不了可以看 README 的“装不上怎么办”一节。"
fi
say ""
if is_dry; then
    say "这是演示模式（DATUM_DRY_RUN=1）：上面每一步都只打印了，没有真的安装。"
else
    say "装好了。打开方法：在“应用程序”里找 Datum（在访达的“前往 > 个人 > 应用程序”里），或者在终端里输入 datum。"
    say "如果终端里提示找不到 datum，关掉这个终端窗口再开一个新的。"
fi
