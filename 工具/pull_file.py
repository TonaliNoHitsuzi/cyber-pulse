#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
拉取闪存文件：先整段流式收，再补洞

用法:
    python pull_file.py --port COM6 --index 4 --out ../数据/数据-闪存/rec004.raw
"""
import argparse
import struct
import time

import serial


def crc16(d):
    c = 0xFFFF
    for x in d:
        c ^= x << 8
        for _ in range(8):
            c = ((c << 1) ^ 0x1021) & 0xFFFF if c & 0x8000 else (c << 1) & 0xFFFF
    return c


def parse(data):
    frames = {}
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
                i = j + 8 + ln
                continue
        i = j + 1
    return frames


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
        time.sleep(0.2)
    s.reset_input_buffer()

    # ---- 1. 流式收 ----
    size = None
    head = b""
    for _ in range(15):
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
        print("流式启动失败")
        return

    wire = bytearray(head)
    t0 = time.time()
    while time.time() - t0 < 40:
        chunk = s.read(262144)
        if chunk:
            wire += chunk
            t0 = time.time()
        if b"\xaa\x55\xff\xff" in wire[-64:]:
            break
    frames = parse(bytes(wire))
    total = (size + 511) // 512
    print("流式收到 %d/%d 块（%.0f%%）" % (len(frames), total, len(frames) * 100.0 / total))

    # ---- 2. 补洞 ----
    have = [k for k in range(total) if k not in frames]
    if have:
        print("补洞：缺 %d 块" % len(have))
        s.write(b"rec close\n")
        time.sleep(0.3)
        s.write(("rec open %d\n" % a.index).encode())
        time.sleep(0.8)
        s.reset_input_buffer()
        fails = 0
        for idx, seq in enumerate(have):
            got = None
            for _ in range(4):
                s.write(("rec rd %d\n" % seq).encode())
                buf = b""
                t = time.time()
                while time.time() - t < 0.45:
                    buf += s.read(8192) or b""
                    if b"\xaa\x55" in buf:
                        break
                f = parse(buf)
                if seq in f:
                    got = f[seq]
                    break
            if got:
                frames[seq] = got
                fails = 0
            else:
                fails += 1
                if fails >= 15:
                    # 会话可能卡死，重开
                    s.write(b"rec close\n")
                    time.sleep(0.3)
                    s.write(("rec open %d\n" % a.index).encode())
                    time.sleep(0.8)
                    s.reset_input_buffer()
                    fails = 0
            if (idx + 1) % 50 == 0:
                print("  补洞 %d/%d" % (idx + 1, len(have)))

    out = b"".join(frames[k] for k in sorted(frames))
    open(a.out, "wb").write(out)
    ok = len(out) == size
    print("%s %s：%d/%d 字节，%d/%d 块" % ("OK" if ok else "PART", a.out, len(out), size, len(frames), total))
    if len(out) >= 16:
        t0b, task = struct.unpack_from("<II", out, 8)
        print("   头: %s ver=%d 起始=%dms 任务号=%d" % (out[:4], out[4], t0b, task))
    s.write(b"rec close\n")
    s.close()


if __name__ == "__main__":
    main()
