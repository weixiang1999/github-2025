#!/usr/bin/env bash
# Atelier 智能Agent工作台 启动脚本 (Linux / macOS)
set -e

# 切换到脚本所在目录
cd "$(dirname "$(readlink -f "$0" 2>/dev/null || echo "$0")")"

echo ""
echo "  ╔══════════════════════════════════════════════╗"
echo "  ║       Atelier · 智能Agent工作台 v2.0         ║"
echo "  ║       多模态生成 · 多Agent并行 · 自主交付     ║"
echo "  ╚══════════════════════════════════════════════╝"
echo ""
echo "  正在启动..."
echo ""

HTML="智能Agent.html"
URL="file://$(pwd)/$HTML"

if [ ! -f "$HTML" ]; then
    echo "  ✕ 未找到「$HTML」"
    echo "    请确认文件位于同一文件夹内"
    exit 1
fi

# 依次尝试常见浏览器
open_browser() {
    local url="$1"
    # Linux
    if command -v xdg-open >/dev/null 2>&1; then
        xdg-open "$url" >/dev/null 2>&1 && return 0
    fi
    # macOS
    if command -v open >/dev/null 2>&1; then
        open "$url" >/dev/null 2>&1 && return 0
    fi
    # 各浏览器直接调用
    for bin in google-chrome chromium chromium-browser firefox microsoft-edge; do
        if command -v "$bin" >/dev/null 2>&1; then
            "$bin" "$url" >/dev/null 2>&1 &
            return 0
        fi
    done
    return 1
}

if open_browser "$URL"; then
    echo "  ✓ 已在默认浏览器中打开"
else
    echo "  ! 无法自动打开浏览器，请手动访问："
    echo "    $URL"
fi

echo ""
echo "  提示："
echo "    • 首次使用需配置 DeepSeek API（详见使用说明.txt）"
echo "    • 技能压缩包请放入「示例技能包」文件夹"
echo ""
