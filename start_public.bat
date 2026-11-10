@echo off
chcp 65001 >nul
cd /d "%~dp0"
rem 一键开放实时体验：开服务 + 临时隧道，并把网址发布到演示站（https://dingzhen-zhr.github.io/computer-graphics-project/）。
rem 要访问密码；每人独立会话；所有人共用花费上限（默认 5 元）。按 Ctrl+C 或关掉窗口结束开放。
.venv\Scripts\python scripts\go_public.py --budget 5 --max-busy 3
pause
