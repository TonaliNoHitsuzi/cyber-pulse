# -*- coding: utf-8 -*-
"""
CYBER-PULSE 课堂演示桥
=====================
一条命令跑起整个演示站：
    python serial_bridge.py

职责：
  1. HTTP 静态服务本目录（index.html），端口 8100，只绑 127.0.0.1
  2. WebSocket 推流端口 8765：串口数据 → 网页
  3. 串口管理：自动枚举 USB-Serial-JTAG (VID:PID=303A:1001)，
     DTR/RTS 在 open 之前置 False（防复位），timeout=0.2（防阻塞）

协议（JSON 文本帧）：
  S→C  {"type":"hello",  "port":"COM6", "serial":"open"}
  S→C  {"type":"status", "serial":"open|closed|error", "detail":"..."}
  S→C  {"type":"data",   "wave":[[seq,lo,hi],...], "ui":{...}, "rps":197}
  S→C  {"type":"log",    "line":"CFG|..."}          # 非 R/UI 行，含命令回显
  C→S  {"type":"cmd",    "line":"raw 1"}            # 原样写串口（自动补 \n）
  C→S  {"type":"rescan"}                            # 强制重扫串口
"""
import asyncio
import collections
import json
import os
import sys
import threading
import time

import serial
import serial.tools.list_ports
import websockets

VID_PID = (0x303A, 0x1001)          # Espressif USB-Serial-JTAG
BAUD = 115200
HTTP_PORT = 8100
WS_PORT = 8765
WAVE_BUF = 4000                      # 20 秒 @200Hz
BROADCAST_PERIOD = 0.05              # 50ms
QUIET_WAKE_AFTER = 8.0               # 静默 N 秒后自动 rec wake

# ---------------------------------------------------------------- 串口管理

class SerialLink:
    def __init__(self, verbose=False):
        self.verbose = verbose
        self.s = None
        self.port_name = None
        self.lock = threading.Lock()
        self.wave = collections.deque(maxlen=WAVE_BUF)   # (seq, lo, hi)
        self.ui = {}
        self.lines_out = collections.deque(maxlen=64)    # 给广播线程的 log 队列
        self.r_count = 0
        self.rps = 0
        self.rps_window = collections.deque()
        self.status = 'closed'
        self.detail = ''
        self._last_line_ts = 0.0
        self._wake_sent = False
        self._stop = False
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    # ---- 公共接口（任意线程） ----
    def list_ports(self):
        return list(serial.tools.list_ports.comports())

    def find_port(self):
        exact = []
        for p in self.list_ports():
            if (p.vid, p.pid) == VID_PID:
                exact.append(p.device)
        if len(exact) == 1:
            return exact[0]
        if len(exact) > 1:
            self.lines_out.append(f'!! 发现多个 USB-Serial-JTAG：{",".join(exact)}，使用第一个 {exact[0]}')
            return exact[0]
        return None

    def send_cmd(self, line):
        line = line.strip()
        if not line:
            return
        with self.lock:
            if self.s and self.s.is_open:
                try:
                    self.s.write((line + '\n').encode('utf-8'))
                    self.lines_out.append(f'» {line}')
                except Exception as e:
                    self.lines_out.append(f'» 写入失败: {e}')
            else:
                self.lines_out.append('» 串口未打开，命令被丢弃')

    def rescan(self):
        self._force_reopen = True

    def close(self):
        self._stop = True

    # ---- 内部 ----
    def _open(self):
        port = self.find_port()
        if not port:
            others = [f'{p.device}({p.description})' for p in self.list_ports()
                      if '蓝牙' not in p.description and 'Bluetooth' not in p.description]
            if others:
                self.status, self.detail = 'closed', '未找到 303A:1001，候选: ' + ' '.join(others)
            else:
                self.status, self.detail = 'closed', '未找到任何串口设备'
            return False
        # 唯一正确姿势：先 dtr/rts=False 再 open（否则复位板子）
        s = serial.Serial()
        s.port = port
        s.baudrate = BAUD
        s.bytesize = 8
        s.parity = 'N'
        s.stopbits = 1
        s.dtr = False
        s.rts = False
        s.timeout = 0.2
        try:
            s.open()
        except Exception as e:
            self.status, self.detail = 'error', f'{port} 打开失败: {e}'
            try:
                s.close()
            except Exception:
                pass
            return False
        with self.lock:
            self.s = s
            self.port_name = port
        self.status, self.detail = 'open', port
        self._last_line_ts = time.time()
        self._wake_sent = False
        self.lines_out.append(f'== 已连接 {port} @115200 (dtr/rts=False) ==')
        return True

    def _shutdown_port(self):
        with self.lock:
            if self.s:
                try:
                    self.s.close()
                except Exception:
                    pass
                self.s = None
        self.status = 'closed'
        self.ui = {}

    def _run(self):
        buf = b''
        while not self._stop:
            if not (self.s and self.s.is_open):
                self._shutdown_port()
                if not self._open():
                    time.sleep(2.0)        # 每 2s 重试枚举
                buf = b''
                continue
            try:
                chunk = self.s.read(4096)
            except Exception as e:
                self.status, self.detail = 'error', f'读取异常: {e}'
                self.lines_out.append(f'!! 串口异常: {e}')
                self._shutdown_port()
                continue
            if chunk:
                buf += chunk
                while b'\n' in buf:
                    raw, buf = buf.split(b'\n', 1)
                    self._handle_line(raw.decode('utf-8', 'replace').strip())
            # 静默自恢复：g_quiet 残留时设备全部输出消失
            if self.status == 'open' and self._last_line_ts and \
               time.time() - self._last_line_ts > QUIET_WAKE_AFTER and not self._wake_sent:
                self._wake_sent = True
                self.lines_out.append('!! 设备静默 >8s，自动发送 rec wake')
                self.send_cmd('rec wake')
            # 1s 滑窗算 R 行速率
            now = time.time()
            while self.rps_window and self.rps_window[0] < now - 1.0:
                self.rps_window.popleft()
            self.rps = len(self.rps_window)

    def _handle_line(self, line):
        if not line:
            return
        self._last_line_ts = time.time()
        self._wake_sent = False
        if line.startswith('R,'):
            try:
                _, seq, lo, hi = line.split(',')
                self.wave.append((int(seq), int(lo), int(hi)))
                self.r_count += 1
                self.rps_window.append(time.time())
            except ValueError:
                pass
        elif line.startswith('UI|'):
            for kv in line[3:].split(' '):
                if '=' in kv:
                    k, v = kv.split('=', 1)
                    self.ui[k] = v
        else:
            # ESP_LOG / CFG / FX / CONS / 回显 → 日志（节流：TRK 行丢弃）
            if line.startswith('TRK|'):
                return
            self.lines_out.append(line)
            if self.verbose:
                print('[ser]', line)

# ---------------------------------------------------------------- HTTP 静态服务

def run_http(root):
    import http.server
    import socketserver

    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **kw):
            super().__init__(*a, directory=root, **kw)

        def log_message(self, fmt, *args):
            pass

    with socketserver.ThreadingTCPServer(('127.0.0.1', HTTP_PORT), Handler) as httpd:
        print(f'[http] http://127.0.0.1:{HTTP_PORT}/  (仅本机)')
        httpd.serve_forever()

# ---------------------------------------------------------------- WebSocket 广播

async def ws_loop(link):
    clients = set()
    last_seq = None

    async def handler(ws):
        nonlocal last_seq
        clients.add(ws)
        try:
            await ws.send(json.dumps({
                'type': 'hello', 'port': link.port_name or '',
                'serial': link.status, 'detail': link.detail,
            }, ensure_ascii=False))
            async for raw in ws:
                try:
                    msg = json.loads(raw)
                except Exception:
                    continue
                if msg.get('type') == 'cmd':
                    link.send_cmd(msg.get('line', ''))
                elif msg.get('type') == 'rescan':
                    link.rescan()
        except websockets.ConnectionClosed:
            pass
        finally:
            clients.discard(ws)

    async def broadcaster():
        nonlocal last_seq
        last_status = None
        last_ui = None
        while True:
            await asyncio.sleep(BROADCAST_PERIOD)
            # 状态变化通知
            if link.status != last_status:
                last_status = link.status
                if clients:
                    await asyncio.gather(*[c.send(json.dumps(
                        {'type': 'status', 'serial': link.status,
                         'detail': link.detail, 'port': link.port_name or ''},
                        ensure_ascii=False)) for c in clients], return_exceptions=True)
            if not clients:
                last_seq = None
                continue
            # 增量波形
            wave = list(link.wave)
            new = []
            if wave:
                if last_seq is None:
                    new = wave[-800:]           # 新客户端先给 4s 历史
                else:
                    for item in wave:
                        if item[0] > last_seq:
                            new.append(item)
                        elif item[0] < last_seq - 5000:   # 板子复位 seq 归零
                            new.append(item)
                    last_seq = wave[-1][0]
                if last_seq is None and wave:
                    last_seq = wave[-1][0]
            ui_changed = link.ui != last_ui
            if new or ui_changed:
                last_ui = dict(link.ui)
                payload = {
                    'type': 'data',
                    'wave': new,
                    'ui': link.ui,
                    'rps': link.rps,
                }
                await asyncio.gather(*[c.send(json.dumps(
                    payload, separators=(',', ':'))) for c in clients],
                    return_exceptions=True)
            # 日志
            while link.lines_out:
                line = link.lines_out.popleft()
                if clients:
                    await asyncio.gather(*[c.send(json.dumps(
                        {'type': 'log', 'line': line},
                        ensure_ascii=False)) for c in clients],
                        return_exceptions=True)

    async with websockets.serve(handler, '127.0.0.1', WS_PORT,
                                ping_interval=10, ping_timeout=10,
                                max_queue=256):
        print(f'[ws]   ws://127.0.0.1:{WS_PORT}')
        await broadcaster()

# ---------------------------------------------------------------- main

def main():
    root = os.path.dirname(os.path.abspath(__file__))
    verbose = '--verbose' in sys.argv or '-v' in sys.argv
    link = SerialLink(verbose=verbose)
    print('[bridge] CYBER-PULSE 演示桥启动（Ctrl+C 退出）')
    http_thread = threading.Thread(target=run_http, args=(root,), daemon=True)
    http_thread.start()
    try:
        asyncio.run(ws_loop(link))
    except KeyboardInterrupt:
        pass
    finally:
        link.close()
        print('\n[bridge] 已退出')

if __name__ == '__main__':
    main()
