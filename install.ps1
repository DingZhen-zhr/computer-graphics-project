# 卡尺 Caliper 一行安装脚本（Windows）
#
# 用法（在 PowerShell 里粘贴这一行）：
#   irm https://raw.githubusercontent.com/DingZhen-zhr/computer-graphics-project/master/install.ps1 | iex
#
# 选项都用环境变量传（"下载后直接执行"的用法传不了参数），先设好再运行上面那一行：
#   CALIPER_SOURCE       从哪里装：一个 git 地址，或本地目录。默认是本仓库的发布标签 v2.0.0
#   CALIPER_MIRROR=1     PyPI 和 Python 的下载走国内镜像
#   CALIPER_NO_SHORTCUT=1  不建开始菜单和桌面的快捷方式
#   CALIPER_DRY_RUN=1    只打印每一步要做什么，不执行
# 例如：$env:CALIPER_MIRROR = "1"; irm https://raw.githubusercontent.com/DingZhen-zhr/computer-graphics-project/master/install.ps1 | iex
#
# 这个脚本只往当前用户的目录里写东西，不需要管理员权限，不改系统设置。
# 除了 uv 的官方安装脚本，它不下载执行任何别的脚本。每一步做之前先打印要做什么。
#
# 这个文件是不带 BOM 的 UTF-8（带 BOM 的话 irm | iex 会把 BOM 当成命令名报错）。
# 下载到本地再运行时，要明确按 UTF-8 读，不要用 -File（Windows PowerShell 5.1 会按系统编码读，中文会乱）：
#   Get-Content -Raw -Encoding UTF8 .\install.ps1 | iex

& {
    $DefaultSource = 'git+https://github.com/DingZhen-zhr/computer-graphics-project@v2.0.0'
    $ArchiveSource = 'caliper-cad @ https://github.com/DingZhen-zhr/computer-graphics-project/archive/refs/tags/v2.0.0.zip'
    $UvInstaller = 'https://astral.sh/uv/install.ps1'
    $PypiMirror = 'https://pypi.tuna.tsinghua.edu.cn/simple'
    $PythonMirror = 'https://registry.npmmirror.com/-/binary/python-build-standalone'
    $HelpUrl = 'https://github.com/DingZhen-zhr/computer-graphics-project#装不上怎么办'
    $ShortcutName = '卡尺 Caliper.lnk'

    $DryRun = ($env:CALIPER_DRY_RUN -eq '1')
    $Source = if ($env:CALIPER_SOURCE) { $env:CALIPER_SOURCE.Trim() } else { $DefaultSource }

    function Say([string]$Text) { Write-Host $Text }
    function Step([int]$N, [string]$Text) { Write-Host "[$N/5] $Text" -ForegroundColor Cyan }
    function Show-Help {
        Write-Host ''
        Write-Host '装不上的话可以这样试：' -ForegroundColor Yellow
        Write-Host '  1. 检查网络：能不能打开 github.com 和 pypi.org；用代理的话确认代理开着。'
        Write-Host '  2. 改走国内镜像再装一次：先运行 $env:CALIPER_MIRROR = "1"，再运行安装命令。'
        Write-Host "  3. 看 README 的“装不上怎么办”一节（里面有下载压缩包本地安装的办法）：$HelpUrl"
    }
    function Stop-Install([int]$Code, [string]$Text, [switch]$WithHelp) {
        Write-Host $Text -ForegroundColor Red
        if ($WithHelp) { Show-Help }
        Set-Variable -Name CaliperInstallCode -Value $Code -Scope 2
    }
    function Find-Uv {
        $cmd = Get-Command uv -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($cmd) { return $cmd.Source }
        $local = Join-Path $HOME '.local\bin\uv.exe'
        if (Test-Path $local) { return $local }
        return $null
    }
    function Show-Command([string]$Exe, [string[]]$Arguments) {
        $shown = ($Arguments | ForEach-Object { if ($_ -match '\s') { '"' + $_ + '"' } else { $_ } }) -join ' '
        if ($DryRun) { Say "  （只打印，不执行）$Exe $shown" } else { Say "  运行：$Exe $shown" }
    }
    # >>> 建快捷方式
    # 不用 WScript.Shell：它把路径按系统编码转换，系统编码表示不了的字（英文 Windows 上的"卡尺"、用户名里的生僻字）
    # 会变成问号，快捷方式存不了。这里直接用 Windows 的 Unicode 接口 IShellLinkW（Windows PowerShell 5.1 自带编译 C# 的功能）。
    function New-CaliperShortcut([string]$Path, [string]$Target, [string]$WorkingDirectory, [string]$Description, [string]$Icon) {
        if (-not ('CaliperInstall.Shortcut' -as [type])) {
            Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
using System.Runtime.InteropServices.ComTypes;
using System.Text;
namespace CaliperInstall {
    [ComImport, Guid("000214F9-0000-0000-C000-000000000046"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    interface IShellLinkW {
        void GetPath([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder file, int size, IntPtr findData, int flags);
        void GetIDList(out IntPtr idList);
        void SetIDList(IntPtr idList);
        void GetDescription([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder name, int size);
        void SetDescription([MarshalAs(UnmanagedType.LPWStr)] string name);
        void GetWorkingDirectory([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder dir, int size);
        void SetWorkingDirectory([MarshalAs(UnmanagedType.LPWStr)] string dir);
        void GetArguments([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder args, int size);
        void SetArguments([MarshalAs(UnmanagedType.LPWStr)] string args);
        void GetHotkey(out short hotkey);
        void SetHotkey(short hotkey);
        void GetShowCmd(out int showCmd);
        void SetShowCmd(int showCmd);
        void GetIconLocation([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder iconPath, int size, out int index);
        void SetIconLocation([MarshalAs(UnmanagedType.LPWStr)] string iconPath, int index);
        void SetRelativePath([MarshalAs(UnmanagedType.LPWStr)] string relPath, int reserved);
        void Resolve(IntPtr hwnd, int flags);
        void SetPath([MarshalAs(UnmanagedType.LPWStr)] string file);
    }
    [ComImport, Guid("00021401-0000-0000-C000-000000000046")]
    class ShellLink { }
    public static class Shortcut {
        public static void Save(string path, string target, string workingDirectory, string description, string icon) {
            IShellLinkW link = (IShellLinkW)new ShellLink();
            link.SetPath(target);
            link.SetWorkingDirectory(workingDirectory);
            link.SetDescription(description);
            if (!String.IsNullOrEmpty(icon)) { link.SetIconLocation(icon, 0); }
            ((IPersistFile)link).Save(path, true);
        }
    }
}
'@
        }
        [CaliperInstall.Shortcut]::Save($Path, $Target, $WorkingDirectory, $Description, $Icon)
    }
    # <<< 建快捷方式

    # 这个脚本临时改的 uv 设置，结束时还原（用 irm | iex 运行时，它们在用户自己的 PowerShell 里）；PATH 里加的 uv 目录保留，这个窗口里马上就能用 caliper
    $saved = @{}
    foreach ($name in 'UV_DEFAULT_INDEX', 'UV_PYTHON_INSTALL_MIRROR', 'UV_HTTP_CONNECT_TIMEOUT') {
        $saved[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
    }
    try {
        # ------------------------------------------------------------ 1
        Step 1 '检查这台电脑是否支持'
        $arch = if ($env:PROCESSOR_ARCHITEW6432) { $env:PROCESSOR_ARCHITEW6432 } else { $env:PROCESSOR_ARCHITECTURE }
        $os = [Environment]::OSVersion.Version
        $range = '支持的范围：Windows 10/11（64 位），或 Apple 芯片的 Mac（macOS 14 及以上）。'
        if ([Environment]::OSVersion.Platform -ne 'Win32NT' -or $os.Major -lt 10) {
            Stop-Install 2 "这台电脑的系统是 Windows $os，卡尺需要 Windows 10 或 11。$range"; return
        }
        if ($arch -ne 'AMD64') {
            Stop-Install 2 "这台电脑的处理器是 $arch，卡尺只支持 64 位的 x64 处理器（SCA 没有别的安装包）。$range"; return
        }
        Say "  Windows $os，64 位（$arch），可以安装。"

        # ------------------------------------------------------------ 2
        Step 2 '准备 uv（用来准备独立的 Python 3.12 环境）'
        $uv = Find-Uv
        if ($uv) {
            Say "  已经有 uv：$uv"
        } elseif ($DryRun) {
            Say "  （只打印，不执行）没有找到 uv，会运行 uv 的官方安装脚本：$UvInstaller"
            $uv = 'uv'
        } else {
            Say "  没有找到 uv，运行 uv 的官方安装脚本：$UvInstaller"
            try {
                [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
                $installer = Invoke-RestMethod -Uri $UvInstaller -TimeoutSec 20 -UseBasicParsing -ErrorAction Stop
                & ([scriptblock]::Create($installer))
            } catch {
                Stop-Install 1 "uv 没装上：$($_.Exception.Message)" -WithHelp; return
            }
            $env:Path = (Join-Path $HOME '.local\bin') + ';' + $env:Path
            $uv = Find-Uv
            if (-not $uv) { Stop-Install 1 'uv 的安装脚本运行完了，但还是找不到 uv。' -WithHelp; return }
            Say "  uv 装好了：$uv"
        }

        # ------------------------------------------------------------ 3
        Step 3 '安装卡尺（第一次要下载 Python 和 SCA，大约几百 MB，请耐心等）'
        $env:UV_HTTP_CONNECT_TIMEOUT = '20'
        if ($env:CALIPER_MIRROR -eq '1') {
            Say "  走国内镜像：PyPI 用 $PypiMirror，Python 用 $PythonMirror"
            $env:UV_DEFAULT_INDEX = $PypiMirror
            $env:UV_PYTHON_INSTALL_MIRROR = $PythonMirror
        }
        if (Test-Path -LiteralPath $Source -PathType Container) {
            $Source = (Resolve-Path -LiteralPath $Source).Path
        } elseif ($Source -like 'git+*' -and -not (Get-Command git -CommandType Application -ErrorAction SilentlyContinue)) {
            if ($Source -eq $DefaultSource) {
                Say '  这台电脑没有 git，改从 GitHub 下载同一个版本的压缩包来装。'
                $Source = $ArchiveSource
            } else {
                Stop-Install 1 "从 git 地址安装需要先装 git：$Source" -WithHelp; return
            }
        }
        if (-not $DryRun) {
            # Windows 不让替换正在运行的程序文件：卡尺开着时 uv 会报"拒绝访问"。先查，查到就请用户关掉
            $toolRoot = Join-Path (& $uv tool dir | Select-Object -First 1).Trim() 'caliper-cad'
            $binRoot = (& $uv tool dir --bin | Select-Object -First 1).Trim()
            $running = @(Get-Process -ErrorAction SilentlyContinue | Where-Object {
                $_.Path -and ($_.Path.StartsWith($toolRoot, [StringComparison]::OrdinalIgnoreCase) -or
                    ($_.Path.StartsWith($binRoot, [StringComparison]::OrdinalIgnoreCase) -and $_.ProcessName -like 'caliper*'))
            })
            if ($running.Count -gt 0) {
                $names = ($running | ForEach-Object { "$($_.ProcessName)（$($_.Id)）" }) -join '、'
                Stop-Install 1 "卡尺正在运行：$names。Windows 不让替换正在运行的程序，请先关掉所有卡尺窗口和终端里运行的 caliper，再运行安装命令。"
                return
            }
        }
        $installArgs = @('tool', 'install', '--python', '3.12', '--force', $Source)
        Show-Command 'uv' $installArgs
        if (-not $DryRun) {
            & $uv @installArgs
            if ($LASTEXITCODE -ne 0) { Stop-Install 1 "安装没有成功（uv 返回 $LASTEXITCODE），原因见上面 uv 的输出。" -WithHelp; return }
            $bin = (& $uv tool dir --bin | Select-Object -First 1).Trim()
            $toolDir = (& $uv tool dir | Select-Object -First 1).Trim()
            if (-not ($env:Path -split ';' | Where-Object { $_.TrimEnd('\') -eq $bin.TrimEnd('\') })) {
                Say "  $bin 还不在 PATH 里，运行 uv tool update-shell 把它加进当前用户的 PATH"
                & $uv tool update-shell
                $env:Path = $bin + ';' + $env:Path
            }
        } else {
            $bin = '<uv 工具目录>'
            $toolDir = '<uv 工具目录>'
        }
        $caliper = Join-Path $bin 'caliper.exe'
        $app = Join-Path $bin 'caliper-app.exe'

        # ------------------------------------------------------------ 4
        Step 4 '建开始菜单和桌面的快捷方式'
        if ($env:CALIPER_NO_SHORTCUT -eq '1') {
            Say '  设了 CALIPER_NO_SHORTCUT=1，不建快捷方式。'
        } else {
            $places = @()
            foreach ($folder in 'Programs', 'Desktop') {
                $dir = [Environment]::GetFolderPath($folder)
                if ($dir) { $places += $dir } else { Say "  找不到“$folder”文件夹，这个快捷方式跳过。" }
            }
            if ($DryRun) {
                foreach ($dir in $places) { Say "  （只打印，不执行）建快捷方式 $(Join-Path $dir $ShortcutName) → $app" }
            } else {
                $python = Join-Path $toolDir 'caliper-cad\Scripts\python.exe'
                $icon = (& $python -I -c "import cad_agent, pathlib; print(pathlib.Path(cad_agent.__file__).parent / 'desk' / 'static' / 'icon.ico')" | Select-Object -First 1)
                if (-not ($icon -and (Test-Path -LiteralPath $icon))) { $icon = '' }
                foreach ($dir in $places) {
                    $lnk = Join-Path $dir $ShortcutName
                    Say "  建快捷方式：$lnk → $app"
                    New-CaliperShortcut -Path $lnk -Target $app -WorkingDirectory $HOME -Description '卡尺 Caliper：用平常话做 CAD 零件' -Icon $icon
                }
            }
        }

        # ------------------------------------------------------------ 5
        Step 5 '自检（caliper doctor）'
        if ($DryRun) {
            Say "  （只打印，不执行）$caliper doctor"
        } else {
            & $caliper doctor
            if ($LASTEXITCODE -ne 0) {
                Stop-Install 1 '自检里有不能用的项（标着 ✗ 的），按它下面的提示处理；处理不了可以看 README 的“装不上怎么办”一节。'
                return
            }
        }
        Say ''
        if ($DryRun) {
            Say '这是演示模式（CALIPER_DRY_RUN=1）：上面每一步都只打印了，没有真的安装。'
        } else {
            Say '装好了。打开方法：双击桌面上的“卡尺 Caliper”，或者在终端里输入 caliper。'
            Say '如果终端里提示找不到 caliper，关掉这个终端再开一个新的。'
        }
    } finally {
        foreach ($name in $saved.Keys) { [Environment]::SetEnvironmentVariable($name, $saved[$name], 'Process') }
    }
}
# 用 -File 运行时把返回码交出去；用 irm | iex 运行时不能 exit（那会关掉用户的 PowerShell 窗口）
if ($CaliperInstallCode) {
    $code = $CaliperInstallCode
    Remove-Variable -Name CaliperInstallCode -ErrorAction SilentlyContinue
    if ($PSCommandPath) { exit $code } else { $global:LASTEXITCODE = $code }
}
