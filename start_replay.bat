@echo off
chcp 65001 >nul
cd /d "%~dp0"
rem 只读回放一个已保存的会话：不需要 API key，不花钱。演示时网络出问题可以用它。
.venv\Scripts\python -m cad_agent.web --replay demo\phone_stand
pause
