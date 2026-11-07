#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
流式拉取闪存文件：设备自动连发，PC 只收（收完再统一解析）

用法:
    python stream_pull.py --port COM6 --index 4 --out ../数据/数据-闪存/rec004.raw
"""
import argparse
import struct
import time

import serial


def crc16(data):
    c = 0xFFFF
    for x in data:
        c ^= x << 8
        for _ in range(8):
            c = ((c << 1) ^ 0x1021) & 0xFFFF if c & 0x8000 else (c << 1) & 0xFFFF
    return c


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
    time.sleep(1.2)
    for c in ("dump 0", "raw 0", "dbg 0"):
        s.write((c + "\n").encode())
        time.sleep(0.25)
    s.reset_input_buffer()

    size = None
    head = b""
    for attempt in range(15):
        s.write(("rec stream %d\n" % a.index).encode())
        buf = b""
        t0 = time.time()
        while time.time() - t0 < 1.5:
            buf += s.read(16384) or b""
            if b"STREAM|START" in buf:
                break
        if b"STREAM|START" in buf:
            rest = buf.split(b"STREAM|START", 1)[1]
            parts = rest.split(b"\n")
            for idx, ln in enumerate(parts[:4]):
                t = ln.strip()
                if t.isdigit():
                    size = int(t)
                    head = b"\n".join(parts[idx + 1:])
                    break
            if size:
                break
        time.sleep(0.3)

    if not size:
        print("启动流式导出失败（命令没被接收）")
        return
    print("文件 %d 字节（%.1f 分钟），接收中…" % (size, size / 2006 / 60))

    # 纯收取，不做解析，避免拖慢导致丢包
    buf = bytearray(head)
    t0 = time.time()
    last = 0
    while time.time() - t0 < 40:
        chunk = s.read(262144)
        if chunk:
            buf += chunk
            t0 = time.time()   # 有数据就续期
        if b"\xaa\x55\xff\xff" in buf[-64:]:
            break
        if time.time() - last > 2:
            last = time.time()
            print("  %.2f / %.2f MB" % (len(buf) / 1048576, size / 1048576))

    # 先把原始流存盘，便于事后恢复
    open(a.out + ".wire", "wb").write(bytes(buf))

    # 统一解析
    frames = {}
    data = bytes(buf)
    i, n = 0, len(data)
    while i + 8 <= n:
        j = data.find(b"\xaa\x55", i)
        if j < 0 or j + 8 > n:
            break
        ln = data[j + 4] | (data[j + 5] << 8)
        crc = data[j + 6] | (data[j + 7] << 8)
        seq = data[j + 2] | (data[j + 3] << 8)
        if ln == 0xFFFF:
            i = j + 8
            continue
        if 0 < ln <= 512 and j + 8 + ln <= n:
            d = data[j + 8:j + 8 + ln]
            if crc16(d) == crc:
                frames[seq] = d
                i = j + 8 + ln          # 只有 CRC 通过才跳过整帧
                continue
        i = j + 1                        # 否则只前进 1 字节，继续找真帧

    out = b"".join(frames[k] for k in sorted(frames))
    open(a.out, "wb").write(out)
    ok = len(out) == size
    print("%s %s：%d/%d 字节，%d 块" % ("OK" if ok else "PART", a.out, len(out), size, len(frames)))
    if not ok and frames:
        missing = [k for k in range(max(frames) + 1) if k not in frames]
        print("   缺失 %d 块：%s" % (len(missing), missing[:8]))
    if len(out) >= 16:
        t0b, task = struct.unpack_from("<II", out, 8)
        print("   头: %s ver=%d 起始=%dms 任务号=%d" % (out[:4], out[4], t0b, task))
    s.write(b"rec close\n")
    s.close()


if __name__ == "__main__":
    main()
