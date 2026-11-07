#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
流水线式闪存导出（适配 4KB 输出缓冲的批量应答）

用法:
    python fetch_fast.py --port COM6 --index 4 --out rec004.raw

原理：不再"一问一答"，而是持续把请求灌进去、同时收，
      按序号+CRC 重组，最后把缺失的再补几轮。
"""
import argparse
import time

import serial

WINDOW = 64         # 同时在途的请求数（实测设备应答率约 25%，一次多灌）
ROUND_WAIT = 1.2     # 每轮读取时间


def crc16(data: bytes) -> int:
    c = 0xFFFF
    for x in data:
        c ^= x << 8
        for _ in range(8):
            c = ((c << 1) ^ 0x1021) & 0xFFFF if c & 0x8000 else (c << 1) & 0xFFFF
    return c


def parse_frames(buf, frames):
    i = 0
    n = len(buf)
    while i + 8 <= n:
        j = buf.find(b"\xaa\x55", i)
        if j < 0 or j + 8 > n:
            break
        ln = buf[j + 4] | (buf[j + 5] << 8)
        crc = buf[j + 6] | (buf[j + 7] << 8)
        seq = buf[j + 2] | (buf[j + 3] << 8)
        if 0 < ln <= 512 and j + 8 + ln <= n:
            d = buf[j + 8:j + 8 + ln]
            if crc16(d) == crc:
                frames[seq] = d
            i = j + 8 + ln
        else:
            i = j + 1
    return i


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", default="COM6")
    ap.add_argument("--index", type=int, required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    s = serial.Serial()
    s.port = a.port
    s.baudrate = 115200
    s.dtr = False
    s.rts = False
    s.timeout = 0.05
    s.open()
    time.sleep(2.5)
    for c in ("dump 0", "raw 0", "dbg 0"):
        s.write((c + "\n").encode())
        time.sleep(0.3)

    s.write(("rec open %d\n" % a.index).encode())
    time.sleep(1.0)
    head = b""
    t0 = time.time()
    while time.time() - t0 < 1.0:
        head += s.read(4096) or b""
    size = None
    for line in head.decode("utf-8", "replace").splitlines():
        if "FILE|OK|" in line:
            size = int(line.split("FILE|OK|")[1])
    if not size:
        print("打开失败")
        return
    total = (size + 511) // 512
    print("文件 %d 字节，共 %d 块" % (size, total))

    frames = {}
    buf = b""
    t_start = time.time()
    rounds = 0
    while len(frames) < total and time.time() - t_start < 1200:
        rounds += 1
        missing = [k for k in range(total) if k not in frames]
        batch = missing[:WINDOW]
        for seq in batch:
            s.write(("rec rd %d\n" % seq).encode())
            time.sleep(0.006)
            buf += s.read(8192) or b""
        t = time.time()
        while time.time() - t < ROUND_WAIT:
            buf += s.read(16384) or b""
        # 只保留未解析的尾部
        consumed = parse_frames(buf, frames)
        buf = buf[consumed:]
        if rounds % 2 == 0:
            print("  轮 %d：已收 %d/%d，%.0fs" % (rounds, len(frames), total, time.time() - t_start))

    data = b"".join(frames[k] for k in sorted(frames))
    open(a.out, "wb").write(data)
    ok = len(data) == size
    print("%s %s：%d/%d 字节，%d 块，耗时 %.0fs"
          % ("✅" if ok else "⚠️", a.out, len(data), size, len(frames), time.time() - t_start))
    if len(data) >= 16:
        import struct
        t0b, task = struct.unpack_from("<II", data, 8)
        print("   头: %s ver=%d 起始=%dms 任务号=%d" % (data[:4], data[4], t0b, task))
    s.write(b"rec close\n")
    s.close()


if __name__ == "__main__":
    main()
