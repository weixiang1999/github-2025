@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Tempus 守护进程

echo ========================================
echo   Tempus 守护进程 启动器 (Windows)
echo ========================================
echo.

REM 检查 python 是否可用
where python >nul 2>&1
if errorlevel 1 (
    where py >nul 2>&1
    if errorlevel 1 (
        echo [错误] 未检测到 Python，请先安装 Python 3.8+ 并加入 PATH
        echo 下载：https://www.python.org/downloads/
        pause
        exit /b 1
    )
    set PYTHON=py
) else (
    set PYTHON=python
)

REM 检查 pynput 是否安装
%PYTHON% -c "import pynput" 2>nul
if errorlevel 1 (
    echo [安装] 首次运行，正在安装 pynput...
    %PYTHON% -m pip install pynput
    if errorlevel 1 (
        echo [错误] pynput 安装失败，请手动运行：pip install pynput
        pause
        exit /b 1
    )
)

echo [启动] 守护进程运行中...
echo [信息] HTTP 端点: http://127.0.0.1:8791
echo [信息] 日志文件: %USERPROFILE%\.atelier_tempus\log.jsonl
echo.
echo 按 Ctrl+C 退出
echo.

%PYTHON% tempus_daemon.py %*
