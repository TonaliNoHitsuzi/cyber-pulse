#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从设备闪存导出记录（请求-应答 + CRC + 重试）

用法:
    python fetch_flash.py --port COM6 --index 1 --out rec001.raw
    python fetch_flash.py --port COM6 --list

文件格式:
    [16B 头] "CPLS" ver fs start_ms task_id
    [每块]   uint32 ts_ms + uint16 n + int16 × n
"""
import argparse
import struct
import time

import serial


def crc16(data: bytes) -> int:
    c = 0xFFFF
    for x in data:
        c ^= x << 8
        for _ in range(8):
            c = ((c << 1) ^ 0x1021) & 0xFFFF if c & 0x8000 else (c << 1) & 0xFFFF
    return c


class Dev:
    def __init__(self, port, baud=115200):
        self.s = serial.Serial()
        self.s.port = port
        self.s.baudrate = baud
        self.s.dtr = False
        self.s.rts = False
        self.s.timeout = 0.25
        self.s.open()
        time.sleep(1.5)
        # 先关掉周期性日志，否则 R 行（约 4KB/s）会淹没回传帧
        for c in ("dump 0", "raw 0", "dbg 0"):
            self.s.write((c + "\n").encode())
            time.sleep(0.25)
        self.drain(0.5)

    def send(self, cmd):
        self.s.write((cmd + "\n").encode())

    def drain(self, seconds=0.6):
        buf = b""
        t0 = time.time()
        while time.time() - t0 < seconds:
            buf += self.s.read(8192) or b""
        return buf

    def open_file(self, idx):
        for _ in range(6):
            self.send("rec open %d" % idx)
            buf = self.drain(0.8)
            for line in buf.decode("utf-8", "replace").splitlines():
                if "FILE|OK|" in line:
                    return int(line.split("FILE|OK|")[1])
            time.sleep(0.2)
        return None

    def read_chunk(self, seq, tries=8):
        for _ in range(tries):
            self.s.reset_input_buffer()
            self.send("rec rd %d" % seq)
            buf = b""
            t0 = time.time()
            while time.time() - t0 < 1.0:
                buf += self.s.read(8192) or b""
                i = buf.find(b"\xaa\x55")
                if i >= 0 and len(buf) >= i + 8:
                    ln = buf[i + 4] | (buf[i + 5] << 8)
                    crc = buf[i + 6] | (buf[i + 7] << 8)
                    if 0 < ln <= 512 and len(buf) >= i + 8 + ln:
                        d = buf[i + 8:i + 8 + ln]
                        got = buf[i + 2] | (buf[i + 3] << 8)
                        if got == seq and crc16(d) == crc:
                            return d
            time.sleep(0.12)
        return None

    def close(self):
        self.send("rec close")
        time.sleep(0.2)
        self.s.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", default="COM6")
    ap.add_argument("--index", type=int, default=1)
    ap.add_argument("--out", default=None)
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args()

    d = Dev(a.port)
    try:
        if a.list:
            d.send("rec list")
            print(d.drain(1.2).decode("utf-8", "replace"))
            return

        size = d.open_file(a.index)
        if not size:
            print("打开失败（文件不存在？）")
            return
        # 回显一下打开成功的日志（此时已静默，用程序内信息）
        print("文件大小 %d 字节，开始分块读取…" % size)

        chunks = {}
        seq, fails = 0, 0
        total = (size + 511) // 512
        while seq < total:
            c = d.read_chunk(seq)
            if c is None:
                fails += 1
                if fails % 5 == 1:
                    print("  块 %d 失败（重试中，已失败 %d 次）" % (seq, fails))
                if fails > 60:
                    print("连续失败过多，中止")
                    break
                continue
            fails = 0
            chunks[seq] = c
            seq += 1
            if seq % 50 == 0:
                print("  %d/%d" % (seq, total))

        data = b"".join(chunks[k] for k in sorted(chunks))
        out = a.out or ("rec%03d.raw" % a.index)
        open(out, "wb").write(data)
        print("%s 已保存 %s：%d/%d 字节" % ("OK" if len(data) == size else "部分", out, len(data), size))
        if len(data) >= 16:
            t0, task = struct.unpack_from("<II", data, 8)
            print("   头: %s ver=%d 起始=%dms 任务号=%d" % (data[:4], data[4], t0, task))
    finally:
        d.close()


if __name__ == "__main__":
    main()
