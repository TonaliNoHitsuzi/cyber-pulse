#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
闪存导出（十六进制文本通道）—— 唯一推荐方式

用法:
    python pull_hex.py --port COM6 --index 4 --out ../数据/数据-闪存/rec004.raw
    python pull_hex.py --port COM6 --list

原理:
    设备把文件按 512 字节分块，转成 "F<seq>,<len>,<hex>" 文本行发出，
    纯 ASCII 不受串口行尾转换影响。
"""
import argparse
import struct
import time

import serial


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", default="COM6")
    ap.add_argument("--index", type=int, default=0)
    ap.add_argument("--out", default=None)
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args()

    s = serial.Serial()
    s.port = a.port
    s.baudrate = 115200
    s.dtr = False          # 必须先设再 open，否则板子复位
    s.rts = False
    s.timeout = 0.05
    s.open()
    time.sleep(1.2)
    for c in ("dump 0", "raw 0", "dbg 0"):
        s.write((c + "\n").encode())
        time.sleep(0.2)
    s.reset_input_buffer()

    # ---------- 只列文件 ----------
    if a.list:
        for _ in range(10):
            s.write(b"rec list\n")
            time.sleep(0.8)
            buf = b""
            t0 = time.time()
            while time.time() - t0 < 0.6:
                buf += s.read(8192) or b""
            txt = buf.decode("utf-8", "replace")
            if "文件:" in txt:
                for line in txt.splitlines():
                    if "文件:" in line:
                        print(line.split("文件:")[-1].strip())
                break
        s.close()
        return

    if not a.out or a.index <= 0:
        print("用法: --index N --out 路径")
        s.close()
        return

    # ---------- 启动流 ----------
    size = None
    pending = b""
    for _ in range(12):
        s.write(("rec stream %d\n" % a.index).encode())
        buf = b""
        t0 = time.time()
        while time.time() - t0 < 1.2:
            buf += s.read(8192) or b""
            if b"STREAM|START" in buf:
                break
        if b"STREAM|START" in buf:
            txt = buf.split(b"STREAM|START", 1)[1]
            parts = txt.split(b"\n")
            for idx, ln in enumerate(parts[:4]):
                t = ln.strip()
                if t.isdigit():
                    size = int(t)
                    pending = b"\n".join(parts[idx + 1:])   # 保留首批数据
                    break
            if size:
                break
        time.sleep(0.25)

    if not size:
        print("启动失败（命令没被接收）")
        s.close()
        return

    total = (size + 511) // 512
    print("文件 %d 字节，共 %d 块，接收中…" % (size, total))

    # ---------- 收数据 ----------
    chunks = {}
    t0 = time.time()
    last = 0
    while time.time() - t0 < 90:
        data = s.read(131072)
        if data:
            t0 = time.time()
            pending += data
            while True:
                nl = pending.find(b"\n")
                if nl < 0:
                    break
                line = pending[:nl].strip()
                pending = pending[nl + 1:]
                if line.startswith(b"STREAM|END"):
                    t0 = -1
                    break
                if not line.startswith(b"F"):
                    continue
                try:
                    parts = line.split(b",", 2)
                    seq = int(parts[0][1:])
                    ln = int(parts[1])
                    raw = bytes.fromhex(parts[2].decode("ascii"))
                    if len(raw) == ln:
                        chunks[seq] = raw
                except Exception:
                    continue
            if t0 < 0:
                break
        if time.time() - last > 2:
            last = time.time()
            print("  %d/%d 块" % (len(chunks), total))

    out = b"".join(chunks[k] for k in sorted(chunks))
    open(a.out, "wb").write(out)
    ok = len(out) == size
    print("%s %s：%d/%d 字节，%d/%d 块" % ("OK" if ok else "PART", a.out, len(out), size,
                                          len(chunks), total))
    if not ok and chunks:
        missing = [k for k in range(max(chunks) + 1) if k not in chunks]
        print("   缺失块 %d 个：%s" % (len(missing), missing[:8]))
    if len(out) >= 16:
        t0b, task = struct.unpack_from("<II", out, 8)
        print("   头: %s ver=%d 起始=%dms 任务号=%d" % (out[:4], out[4], t0b, task))
    s.write(b"rec close\n")
    time.sleep(0.2)
    s.close()


if __name__ == "__main__":
    main()
