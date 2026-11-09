@echo off
chcp 65001 >nul
cd /d "%~dp0"
rem 公网测试：在这台电脑上开服务，用 Cloudflare 临时隧道给一个公网网址。要访问密码，累计花费到上限（默认 5 元）后自动不再接消息。
rem 关掉这个窗口和弹出的服务窗口，就停止公开。
if not exist tools\cloudflared.exe (
  echo 缺少 tools\cloudflared.exe，请先下载：https://github.com/cloudflare/cloudflared/releases
  pause
  exit /b 1
)
if "%CAD_WEB_PASSWORD%"=="" set /p CAD_WEB_PASSWORD=给这次测试设一个访问密码（至少 6 位）： 
start "CAD 建模助手 - 服务" cmd /k .venv\Scripts\python -m cad_agent.web --config config.toml --public --no-browser --budget 5
timeout /t 4 >nul
echo.
echo 稍等几秒，下面会出现 https://xxxx.trycloudflare.com 这样的网址，把它和密码发给队员。
echo.
tools\cloudflared.exe tunnel --no-autoupdate --url http://127.0.0.1:8765
pause
