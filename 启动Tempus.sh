#!/bin/bash
# Tempus 守护进程启动器（Linux/macOS）
cd "$(dirname "$0")" || exit 1

echo "========================================"
echo "  Tempus 守护进程 启动器 (Linux)"
echo "========================================"
echo

# 选择 Python 解释器
PYTHON=""
for cmd in python3 python; do
    if command -v "$cmd" >/dev/null 2>&1; then
        PYTHON="$cmd"
        break
    fi
done

if [ -z "$PYTHON" ]; then
    echo "[错误] 未检测到 Python，请先安装 Python 3.8+"
    echo "  Debian/Ubuntu: sudo apt install python3 python3-pip python3-tk python3-xlib"
    echo "  Fedora/RHEL:  sudo dnf install python3 python3-tkinter python3-Xlib"
    exit 1
fi

# 检查 pynput
if ! $PYTHON -c "import pynput" >/dev/null 2>&1; then
    echo "[安装] 首次运行，正在安装 pynput..."
    if ! $PYTHON -m pip install --user pynput; then
        echo "[错误] pynput 安装失败"
        echo "  请尝试：sudo apt install python3-xlib python3-tk"
        echo "  然后：pip3 install --user pynput"
        exit 1
    fi
fi

# X11 环境检查
if [ -z "$DISPLAY" ] && [ -z "$WAYLAND_DISPLAY" ]; then
    echo "[警告] 未检测到图形会话（DISPLAY/WAYLAND_DISPLAY），鼠标监听可能不可用"
elif [ -n "$WAYLAND_DISPLAY" ] && [ -z "$XDG_SESSION_TYPE" = "x11" ]; then
    echo "[警告] 当前可能是 Wayland 会话，pynput 在 Wayland 下键盘监听可能受限"
    echo "       建议使用 X11 会话或在登录时选择 'Xorg/X11'"
fi

echo "[启动] 守护进程运行中..."
echo "[信息] HTTP 端点: http://127.0.0.1:8791"
echo "[信息] 日志文件: $HOME/.atelier_tempus/log.jsonl"
echo
echo "按 Ctrl+C 退出"
echo

exec $PYTHON tempus_daemon.py "$@"
