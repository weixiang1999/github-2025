@echo off
chcp 65001 >nul
title Atelier 智能Agent工作台

cd /d "%~dp0"

echo.
echo  ╔══════════════════════════════════════════════╗
echo  ║       Atelier · 智能Agent工作台 v2.0        ║
echo  ║       多模态生成 · 多Agent并行 · 自主交付     ║
echo  ╚══════════════════════════════════════════════╝
echo.
echo  正在启动...
echo.

if exist "智能Agent.html" (
    start "" "智能Agent.html"
    echo  ✓ 已在默认浏览器中打开
) else (
    echo  ✕ 未找到「智能Agent.html」
    echo    请确认文件位于同一文件夹内
)

echo.
echo  提示：
echo    • 首次使用需配置 DeepSeek API（详见使用说明.txt）
echo    • 技能压缩包请放入「示例技能包」文件夹
echo.
pause
