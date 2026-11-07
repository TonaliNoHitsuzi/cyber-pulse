#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""闪存记录取数脚本（请求-应答协议，对应固件 rec open/rd/close）。

用法：
  python tools/rec_fetch.py --list                 # 只列闪存内文件
  python tools/rec_fetch.py --file 4               # 取 rec004.raw
  python tools/rec_fetch.py --file 4 5 6           # 取多个
  python tools/rec_fetch.py --all                  # 取全部（含测试残留 001-003）
  python tools/rec_fetch.py --erase                # 清空闪存（谨慎）

输出：数据-闪存导出-<日期>/recNNN.raw + 摘要行
协议帧：AA 55 seq(2,LE) len(2,LE) crc16(2,LE) data(<=512B)，CRC-16/CCITT-FALSE
"""
import argparse
import datetime as _dt
import glob
import os
import re
import struct
import sys
import time

import serial
from serial.tools import list_ports

VID_PID = (0x303A, 0x1001)  # Espressif USB-Serial-JTAG
BAUD = 115200
CHUNK = 512
RETRY = 4


def crc16_ccitt(data: bytes) -> int:
    crc = 0xFFFF
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) if (crc & 0x8000) else (crc << 1)
            crc &= 0xFFFF
    return crc


def find_port() -> str:
    exact = [p.device for p in list_ports.comports() if (p.vid, p.pid) == VID_PID]
    if not exact:
        sys.exit("!! 未发现 USB-Serial-JTAG (303A:1001)，请插设备")
    if len(exact) > 1:
        print(f"!! 多个候选 {exact}，使用第一个 {exact[0]}")
    return exact[0]


class Dev:
    def __init__(self, port: str):
        self.s = serial.Serial(port=port, baudrate=BAUD, timeout=0.2)
        self.buf = bytearray()

    def cmd(self, line: str) -> None:
        self.s.reset_input_buffer()
        self.buf.clear()
        self.s.write((line + "\n").encode())

    def read_line(self, sec: float = 1.0) -> str:
        """读到一行（\n 结尾），超时返回已有内容。"""
        deadline = time.time() + sec
        while time.time() < deadline:
            i = self.buf.find(b"\n")
            if i >= 0:
                out = bytes(self.buf[: i + 1])
                del self.buf[: i + 1]
                return out.decode(errors="replace").strip()
            n = self.s.read(256)
            if n:
                self.buf += n
        return ""

    def read_bytes(self, n: int, sec: float = 1.0) -> bytes:
        deadline = time.time() + sec
        while time.time() < deadline:
            if len(self.buf) >= n:
                out = bytes(self.buf[:n])
                del self.buf[:n]
                return out
            n_avail = self.s.read(max(1, n - len(self.buf)))
            if n_avail:
                self.buf += n_avail
        out = bytes(self.buf[:n])
        del self.buf[:n]
        return out

    def sync_wake(self):
        """开跑前先解除可能的静默残留（上次断连）。"""
        self.cmd("rec wake")
        for _ in range(10):
            ln = self.read_line(0.3)
            if "FILE|WAKE" in ln:
                return
            if ln == "" and not self.s.in_waiting:
                break
        print("   (wake 未回显，可能本就未静默，继续)")

    def list_files(self):
        self.cmd("rec list")
        files = []
        pat = re.compile(r"(rec\d{3})\.raw")
        deadline = time.time() + 2.0
        while time.time() < deadline:
            ln = self.read_line(0.3)
            if not ln and not self.s.in_waiting:
                break
            m = pat.search(ln)
            if m:
                files.append(int(m.group(1)[3:]))
        return sorted(set(files))

    def open_file(self, n: int):
        """返回文件大小，失败 sys.exit。"""
        for attempt in range(3):
            self.cmd(f"rec open {n}")
            deadline = time.time() + 1.5
            while time.time() < deadline:
                ln = self.read_line(0.3)
                if "FILE|OK|" in ln:
                    return int(ln.split("FILE|OK|")[1].strip())
                if "FILE|ERR" in ln:
                    sys.exit(f"!! rec open {n} 失败：FILE|ERR（文件不存在？先 --list）")
        sys.exit(f"!! rec open {n} 三次无回应（试 rec wake / 重新插拔）")

    def read_chunk(self, seq: int):
        """请求一块，返回 data 或 None（失败）。"""
        self.cmd(f"rec rd {seq}")
        # 流同步：找 AA 55 头
        for _ in range(RETRY * 2):
            # 先确保缓冲里有东西
            if len(self.buf) < 2:
                self.buf += self.s.read(CHUNK)
            # 丢掉帧头前的杂字节
            while len(self.buf) >= 2 and self.buf[:2] != b"\xAA\x55":
                del self.buf[:1]
            if len(self.buf) < 10:
                self.buf += self.s.read(64)
                continue
            hdr = bytes(self.buf[:10])
            fseq, flen, fcrc = struct.unpack("<HHH", hdr[2:8])
            if flen == 0 or flen > CHUNK:
                del self.buf[:2]  # 假头，继续同步
                continue
            need = 10 + flen
            while len(self.buf) < need:
                got = self.s.read(need - len(self.buf))
                if not got:
                    break
                self.buf += got
            if len(self.buf) < need:
                continue
            data = bytes(self.buf[10:need])
            del self.buf[:need]
            if fseq != seq:
                print(f"   !! seq 不匹配: 期望 {seq} 收到 {fseq}，丢弃重试")
                return None
            if crc16_ccitt(data) != fcrc:
                print(f"   !! 块 {seq} CRC 错，重试")
                return None
            return data
        return None

    def close_file(self):
        self.cmd("rec close")
        for _ in range(10):
            ln = self.read_line(0.3)
            if "FILE|CLOSED" in ln:
                return
            if not ln and not self.s.in_waiting:
                break

    def fetch(self, n: int, out_dir: str) -> str:
        size = self.open_file(n)
        nblk = (size + CHUNK - 1) // CHUNK
        eta = size / 1024 / 10.0
        print(f"-> rec{n:03d}.raw  {size} B ({size/1e6:.2f} MB ≈ {size/2000/60:.1f} 分钟数据)，{nblk} 块，预计 {eta:.0f}s")
        path = os.path.join(out_dir, f"rec{n:03d}.raw")
        blob = bytearray()
        t0 = time.time()
        misses = 0
        for seq in range(nblk):
            data = None
            for _ in range(RETRY):
                data = self.read_chunk(seq)
                if data is not None:
                    break
            if data is None:
                print(f"   !! 块 {seq} 重试 {RETRY} 次仍失败，用 0x00 填充占位（文件已损坏段）")
                misses += 1
                data = b"\x00" * min(CHUNK, size - seq * CHUNK)
            blob += data
            if seq % 20 == 0 or seq == nblk - 1:
                rate = (len(blob) / 1024) / max(0.1, time.time() - t0)
                print(f"   块 {seq+1}/{nblk}  {len(blob)/1024:.0f} KB  {rate:.1f} KB/s")
        self.close_file()
        with open(path, "wb") as f:
            f.write(blob)
        print(f"   完成: {path}  (坏块 {misses})")
        return path


def summarize(path: str):
    """读文件头给摘要。v2: 12-15B 为 App 会话 id。"""
    with open(path, "rb") as f:
        hdr = f.read(16)
    if len(hdr) < 16 or hdr[:4] != b"CPLS":
        print(f"   [摘要] 头异常: {hdr[:8]!r}")
        return
    ver = hdr[4]
    fs = struct.unpack("<H", hdr[6:8])[0]
    t0 = struct.unpack("<I", hdr[8:12])[0]
    sid = struct.unpack("<I", hdr[12:16])[0]
    size = os.path.getsize(path)
    nblk = max(0, (size - 16) // 2006)
    sid_s = f" 会话id={sid}" if (ver >= 2 and sid) else (" 会话id=0(手动)" if ver >= 2 else "")
    print(f"   [摘要] ver={ver} fs={fs} 起始板载毫秒={t0}{sid_s} 数据块≈{nblk} ≈{nblk/60:.1f} 分钟")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true", help="只列文件")
    ap.add_argument("--file", type=int, nargs="+", help="取指定编号")
    ap.add_argument("--all", action="store_true", help="取全部")
    ap.add_argument("--erase", action="store_true", help="清空闪存")
    ap.add_argument("--out", default=None, help="输出目录（默认 数据-闪存导出-<日期>）")
    args = ap.parse_args()

    if not (args.list or args.file or args.all or args.erase):
        ap.print_help()
        return

    port = find_port()
    print(f"串口: {port} @ {BAUD}")
    dev = Dev(port)
    time.sleep(0.3)
    dev.sync_wake()

    if args.erase:
        r = input("确认清空闪存全部记录？(y/N) ").strip().lower()
        if r == "y":
            dev.cmd("rec erase")
            time.sleep(1.0)
            print("已清空")
        return

    files = dev.list_files()
    print(f"闪存内文件: {[f'rec{f:03d}.raw' for f in files] if files else '（空）'}")
    if args.list:
        return

    targets = files if args.all else [f for f in (args.file or []) if f in files]
    missing = [f for f in (args.file or []) if f not in files]
    if missing:
        print(f"!! 不存在的编号被跳过: {missing}")
    if not targets:
        print("无可取文件")
        return

    out_dir = args.out or f"数据-闪存导出-{_dt.date.today().isoformat()}"
    os.makedirs(out_dir, exist_ok=True)
    for n in targets:
        p = dev.fetch(n, out_dir)
        summarize(p)
    print(f"\n全部完成 → {out_dir}/")
    print("提醒: 确认电脑里文件完好后再考虑 rec erase 清闪存")


if __name__ == "__main__":
    main()
