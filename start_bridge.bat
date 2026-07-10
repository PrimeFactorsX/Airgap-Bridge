@echo off
chcp 65001 > nul
title 桥接服务器
echo ========================================
echo      桥接服务器 - 启动中
echo ========================================

cd /d "%~dp0"

python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 未找到 Python，请先安装 Python 3.8+，并确保已勾选“Add Python to PATH”
    pause
    exit /b 1
)

for /f "tokens=*" %%i in ('python --version 2^>^&1') do echo [信息] 使用 Python: %%i

if not exist cache mkdir cache

echo [信息] 启动服务器...
python bridge_server.py

if %errorlevel% neq 0 (
    echo.
    echo [错误] 服务器异常退出，请检查上方日志。
    pause
)