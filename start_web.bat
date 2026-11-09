@echo off
chcp 65001 >nul
cd /d "%~dp0"
.venv\Scripts\python -m cad_agent.web --config config.toml
pause
