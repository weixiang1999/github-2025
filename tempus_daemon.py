#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tempus 守护进程 — 全局键盘鼠标监听 + 本地 JSONL 存储 + HTTP 端点
================================================================
跨平台支持：Windows / Linux（X11）
依赖：pynput, python3-xlib（Linux）

安装：
    pip install pynput
    # Linux 还需要：sudo apt install python3-xlib python3-tk
    #               （或 pip install Xlib）

运行：
    python3 tempus_daemon.py            # 前台运行
    python3 tempus_daemon.py --quiet    # 静默（不打印事件）

HTTP 端点（127.0.0.1:8791）：
    GET  /status                  -> {"running":true,"events":N,"started_at":...,"platform":"..."}
    GET  /events?since=<ts>       -> [{ts,type,...},...]
    GET  /events?limit=<n>        -> 最近 n 条
    POST /clear                   -> 清空已记录事件
    POST /shutdown                -> 关闭守护进程

数据存储：
    ~/.atelier_tempus/log.jsonl   （追加写入，每行一条 JSON）
    ~/.atelier_tempus/pid         （PID 文件，方便关闭）

事件结构：
    {"ts": 1234567890.123, "type": "word",   "text": "hello"}
    {"ts": 1234567890.123, "type": "key",    "text": "<enter>"}
    {"ts": 1234567890.123, "type": "click",  "button": "left",   "x":100, "y":200}
    {"ts": 1234567890.123, "type": "scroll", "dx":0,  "dy":-3}
"""

import os
import sys
import json
import time
import signal
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

# ---------- 配置 ----------
HOST = "127.0.0.1"
PORT = 8791
LOG_DIR = os.path.expanduser("~/.atelier_tempus")
LOG_FILE = os.path.join(LOG_DIR, "log.jsonl")
PID_FILE = os.path.join(LOG_DIR, "pid")
MAX_EVENTS_IN_MEM = 5000          # 内存中保留最近 5000 条（文件已持久化全部）
WORD_TIMEOUT = 1.5                # 1.5 秒无新按键则 flush 当前词
MAX_WORD_LEN = 80                 # 单词最长 80 字符
SENSITIVE_KEYWORDS = [           # 检测到这些关键词的整段输入替换为 ***
    "password", "passwd", "pwd", "secret", "token", "api_key", "apikey",
    "apikey", "access_key", "private_key", "credential",
]

# ---------- 全局状态 ----------
events = []                       # 内存中的事件列表
events_lock = threading.Lock()
current_word = []                  # 当前正在累积的输入缓冲
word_last_ts = 0
word_lock = threading.Lock()
started_at = time.time()
keyboard_ctrl = None
mouse_ctrl = None
keyboard_listener = None
mouse_listener = None
server_thread = None
httpd = None
quiet = False

# ---------- 工具 ----------
def log(msg):
    if not quiet:
        print(f"[tempus] {msg}", flush=True)

def ensure_dir():
    os.makedirs(LOG_DIR, exist_ok=True)

def append_event(ev):
    """写入内存 + 追加到 JSONL 文件"""
    global events
    with events_lock:
        events.append(ev)
        if len(events) > MAX_EVENTS_IN_MEM:
            events = events[-MAX_EVENTS_IN_MEM:]
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(ev, ensure_ascii=False) + "\n")
    except Exception as e:
        log(f"写入日志失败：{e}")

def is_sensitive(s):
    """检测字符串是否像密钥/密码"""
    low = s.lower()
    for kw in SENSITIVE_KEYWORDS:
        if kw in low:
            return True
    # sk- 开头（OpenAI/DeepSeek 风格 API key）
    if s.startswith("sk-") and len(s) >= 8:
        return True
    # 32+ 位连续字母数字（像 hash/token）
    if len(s) >= 32 and s.isalnum():
        return True
    # 16+ 位连续数字（像卡号）
    if len(s) >= 16 and s.isdigit():
        return True
    return False

def mask_if_sensitive(s):
    """脱敏：敏感串替换为 ***"""
    if is_sensitive(s):
        return "***"
    return s

def flush_word(force=False):
    """把累积的 current_word 作为一个 word 事件保存"""
    global current_word, word_last_ts
    with word_lock:
        if not current_word:
            return
        # 超时或强制 flush
        if not force and (time.time() - word_last_ts) < WORD_TIMEOUT:
            return
        word = "".join(current_word)
        current_word = []
        word_last_ts = 0
    if not word.strip():
        return
    word = word.strip()
    if len(word) > MAX_WORD_LEN:
        word = word[:MAX_WORD_LEN] + "..."
    word = mask_if_sensitive(word)
    append_event({
        "ts": time.time(),
        "type": "word",
        "text": word,
    })
    log(f"word: {word}")

# ---------- 键盘监听 ----------
def on_key_press(key):
    """键盘按下事件"""
    global current_word, word_last_ts
    try:
        # 普通字符
        if hasattr(key, "char") and key.char:
            ch = key.char
            with word_lock:
                current_word.append(ch)
                word_last_ts = time.time()
            return
        # 特殊键
        from pynput.keyboard import Key
        key_name = None
        if key == Key.space:
            flush_word(force=True)  # 空格 flush
            return
        elif key == Key.enter:
            flush_word(force=True)
            key_name = "<enter>"
        elif key == Key.backspace:
            # 退格：移除最后一个字符
            with word_lock:
                if current_word:
                    current_word.pop()
            return
        elif key == Key.tab:
            flush_word(force=True)
            key_name = "<tab>"
        elif key == Key.esc:
            flush_word(force=True)
            key_name = "<esc>"
        elif key in (Key.ctrl_l, Key.ctrl_r):
            key_name = "<ctrl>"
        elif key in (Key.alt_l, Key.alt_r):
            key_name = "<alt>"
        elif key in (Key.shift, Key.shift_l, Key.shift_r):
            return  # shift 不记录
        elif key == Key.caps_lock:
            key_name = "<caps>"
        elif key == Key.delete:
            flush_word(force=True)
            key_name = "<del>"
        else:
            # 其它特殊键（F1-F12、方向键等）
            name = str(key).replace("Key.", "").replace("'", "")
            if name and len(name) < 20:
                key_name = f"<{name}>"
        if key_name:
            append_event({
                "ts": time.time(),
                "type": "key",
                "text": key_name,
            })
            log(f"key: {key_name}")
    except Exception as e:
        log(f"键盘事件处理错误：{e}")

# ---------- 鼠标监听 ----------
def on_click(x, y, button, pressed):
    if not pressed:
        return
    flush_word(force=True)
    btn = "left" if "left" in str(button).lower() else \
          "right" if "right" in str(button).lower() else \
          "middle"
    append_event({
        "ts": time.time(),
        "type": "click",
        "button": btn,
        "x": int(x), "y": int(y),
    })
    log(f"click {btn} @ ({int(x)},{int(y)})")

def on_scroll(x, y, dx, dy):
    flush_word(force=True)
    append_event({
        "ts": time.time(),
        "type": "scroll",
        "dx": int(dx), "dy": int(dy),
    })

# ---------- HTTP 服务器 ----------
class Handler(BaseHTTPRequestHandler):
    def _send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        # CORS：允许 file:// 打开的 HTML 跨域访问
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self._send_json({"ok": True})

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)
        if path == "/status":
            with events_lock:
                count = len(events)
            self._send_json({
                "running": True,
                "events": count,
                "started_at": started_at,
                "platform": sys.platform,
                "log_file": LOG_FILE,
                "pid": os.getpid(),
            })
        elif path == "/events":
            with events_lock:
                snap = list(events)
            since = float(qs.get("since", [0])[0])
            limit = int(qs.get("limit", [0])[0]) if qs.get("limit") else 0
            filtered = [e for e in snap if e["ts"] > since]
            if limit > 0:
                filtered = filtered[-limit:]
            self._send_json({"events": filtered, "count": len(filtered)})
        else:
            self._send_json({"error": "not found"}, 404)

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/clear":
            global events
            with events_lock:
                events = []
            try:
                if os.path.exists(LOG_FILE):
                    os.remove(LOG_FILE)
            except Exception as e:
                log(f"清空日志文件失败：{e}")
            self._send_json({"ok": True})
            log("日志已清空")
        elif path == "/shutdown":
            self._send_json({"ok": True})
            log("收到关闭请求")
            # 异步关闭，确保响应先返回
            threading.Timer(0.3, shutdown).start()
        else:
            self._send_json({"error": "not found"}, 404)

    def log_message(self, format, *args):
        pass  # 静默 HTTP 访问日志

# ---------- 周期性 flush（避免输入悬而未决） ----------
def word_flush_loop():
    """后台线程：每 0.5 秒检查是否有超时的 word 需要 flush"""
    while True:
        time.sleep(0.5)
        try:
            if current_word and (time.time() - word_last_ts) >= WORD_TIMEOUT:
                flush_word(force=True)
        except Exception:
            pass

# ---------- 生命周期 ----------
def start_listeners():
    global keyboard_listener, mouse_listener
    try:
        from pynput.keyboard import Listener as KListener
        keyboard_listener = KListener(on_press=on_key_press)
        keyboard_listener.daemon = True
        keyboard_listener.start()
        log("键盘监听已启动")
    except Exception as e:
        log(f"键盘监听启动失败：{e}")
        log("Linux 用户请确保：sudo apt install python3-xlib python3-tk")
        log("Windows 用户请以管理员权限运行（部分场景需要）")
    try:
        from pynput.mouse import Listener as MListener
        mouse_listener = MListener(on_click=on_click, on_scroll=on_scroll)
        mouse_listener.daemon = True
        mouse_listener.start()
        log("鼠标监听已启动")
    except Exception as e:
        log(f"鼠标监听启动失败：{e}")

def start_http():
    global httpd, server_thread
    try:
        httpd = HTTPServer((HOST, PORT), Handler)
        server_thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        server_thread.start()
        log(f"HTTP 端点已启动：http://{HOST}:{PORT}")
    except OSError as e:
        if "Address already in use" in str(e):
            log(f"端口 {PORT} 已被占用，可能已有 Tempus 守护进程在运行")
        else:
            log(f"HTTP 启动失败：{e}")
        sys.exit(1)

def write_pid():
    try:
        with open(PID_FILE, "w") as f:
            f.write(str(os.getpid()))
    except Exception as e:
        log(f"写 PID 文件失败：{e}")

def shutdown():
    log("正在关闭...")
    try:
        flush_word(force=True)
        if keyboard_listener: keyboard_listener.stop()
        if mouse_listener: mouse_listener.stop()
        if httpd: httpd.shutdown()
    except Exception:
        pass
    try:
        if os.path.exists(PID_FILE):
            os.remove(PID_FILE)
    except Exception:
        pass
    os._exit(0)

def signal_handler(signum, frame):
    shutdown()

# ---------- 主入口 ----------
def main():
    global quiet
    quiet = "--quiet" in sys.argv
    ensure_dir()
    write_pid()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    log("=" * 56)
    log("Tempus 守护进程启动")
    log(f"平台：{sys.platform}")
    log(f"日志文件：{LOG_FILE}")
    log(f"HTTP 端点：http://{HOST}:{PORT}")
    log(f"PID：{os.getpid()}")
    log("按 Ctrl+C 退出")
    log("=" * 56)
    log("")

    start_listeners()
    start_http()

    # 启动周期 flush 线程
    threading.Thread(target=word_flush_loop, daemon=True).start()

    # 主线程：保持运行
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        shutdown()

if __name__ == "__main__":
    main()
