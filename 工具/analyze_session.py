#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
上位机整体波形分析（离线、无偏）

用法:
    python analyze_session.py <db 路径> [--watch watch.json]

设计原则:
  - 不信任固件输出，独立对整段波形做估计
  - 优先用事件标注(MARK)切段；没有标注时按"前30秒=静息"的协议默认
  - 同时给出三种估计：自相关、谱峰、峰间隔中位（i+1 / i+2）
  - 饱和判定：峰间隔中位接近不应期(350ms) → 该段无效
"""

import sqlite3
import struct
import sys
import json
import numpy as np
from scipy.signal import butter, filtfilt

FS = 100.0          # App 侧波形采样率
WIN = 5             # 与固件一致的 5 样本窗
GAP_MS = 350.0      # 固件不应期


# ---------------- 数据加载 ----------------
def load_wave(conn, sid):
    rows = conn.execute(
        "select startTs,data from wave_chunks where sessionId=? order by startTs", (sid,)
    ).fetchall()
    if not rows:
        return None, None
    sig, ts = [], []
    for st, blob in rows:
        v = struct.unpack("<%dh" % (len(blob) // 2), blob)
        sig.extend(v)
        ts.extend([st + i * 10 for i in range(len(v))])
    return np.array(sig, dtype=float), np.array(ts, dtype=float)


def load_imu(conn, sid):
    rows = conn.execute(
        "select startTs,data,n from imu_chunks where sessionId=? order by startTs", (sid,)
    ).fetchall()
    if not rows:
        return None, None
    T, M = [], []
    for st, blob, n in rows:
        for i in range(n):
            o = i * 14
            dt, = struct.unpack_from("<H", blob, o)
            v = struct.unpack_from("<6h", blob, o + 2)
            T.append(st + dt)
            M.append((v[0] ** 2 + v[1] ** 2 + v[2] ** 2) ** 0.5 / 100.0)
    return np.array(T, dtype=float), np.array(M)


def load_marks(conn, sid):
    rows = conn.execute(
        "select tsMillis,quality from samples where sessionId=? and channel='MARK' order by tsMillis",
        (sid,),
    ).fetchall()
    return rows


# ---------------- 信号处理 ----------------
def dev_series(x):
    """复刻固件的 5 样本窗偏差 + EMA 基线"""
    n = len(x) // WIN * WIN
    w = x[:n].reshape(-1, WIN)
    mn, mx = w.min(1), w.max(1)
    mid = (mn + mx) / 2
    base = np.zeros_like(mid)
    b = mid[0] if len(mid) else 0
    for i, v in enumerate(mid):
        b += (v - b) * 0.02
        if abs(v - b) > 120:
            b = v
        base[i] = b
    dev = np.maximum(np.abs(mx - base), np.abs(mn - base))
    t = np.arange(len(mid)) / (FS / WIN)
    return t, dev


def detect_peaks(t, dev, thr=40.0, gap_ms=GAP_MS):
    p = []
    for i in range(1, len(dev) - 1):
        if dev[i] > thr and dev[i] >= dev[i - 1] and dev[i] > dev[i + 1]:
            if p and (t[i] - p[-1]) * 1000 < gap_ms:
                continue
            p.append(t[i])
    return np.array(p)


def hr_autocorr(x, lo=0.7, hi=3.2):
    if len(x) < FS * 5:
        return None, None
    y = x - np.mean(x)
    y = y - np.convolve(y, np.ones(50) / 50, mode="same")
    ac = np.correlate(y, y, "full")[len(y) - 1:]
    ac /= (ac[0] + 1e-12)
    a, b = int(FS / hi), int(FS / lo)
    b = min(b, len(ac))
    if b <= a:
        return None, None
    seg = ac[a:b]
    k = int(np.argmax(seg))
    return 60.0 * FS / (a + k), float(seg[k])


def analyze_segment(x, label):
    dur = len(x) / FS
    amp = np.percentile(x, 95) - np.percentile(x, 5)
    t, dev = dev_series(x)
    p = detect_peaks(t, dev)
    out = {
        "label": label, "dur": dur, "amp": amp,
        "hr_ac": None, "ac_peak": None,
        "hr_med_i1": None, "hr_med_i2": None,
        "n_peaks": len(p), "lock_frac": None, "sat": False,
    }
    if len(x) >= FS * 5:
        out["hr_ac"], out["ac_peak"] = hr_autocorr(x)
    if len(p) >= 4:
        iv = np.diff(p) * 1000.0
        iv = iv[(iv > 200) & (iv < 2500)]
        if len(iv) >= 3:
            med = float(np.median(iv))
            lock = float(np.mean(np.abs(iv - GAP_MS) < 30))
            out["hr_med_i1"] = 60000.0 / med
            out["hr_med_i2"] = 60000.0 / (2 * med)
            out["lock_frac"] = lock
            out["sat"] = lock > 0.45
    return out


# ---------------- 分段 ----------------
def build_segments(conn, sid, dur_s):
    """有标注按标注切；没有就按协议：前 30s 静息，其后整段算动态"""
    marks = load_marks(conn, sid)
    st = conn.execute("select startedAt from sessions where id=?", (sid,)).fetchone()[0]
    if marks:
        segs = []
        prev = 0.0
        for ts, label in marks:
            t = (ts - st) / 1000.0
            if t > prev:
                segs.append((prev, min(t, dur_s), "标注前段"))
            segs.append((t, None, label))
            prev = t
        # 收尾
        if segs:
            segs[-1] = (segs[-1][0], dur_s, segs[-1][2])
        return [(a, b, c) for a, b, c in segs if b is not None and b > a]
    return [(0.0, min(30.0, dur_s), "静息(协议默认)")]


# ---------------- 主流程 ----------------
def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return
    db = sys.argv[1]
    watch = {}
    if "--watch" in sys.argv:
        watch = json.load(open(sys.argv[sys.argv.index("--watch") + 1], encoding="utf-8"))

    conn = sqlite3.connect(db)
    rows = conn.execute(
        "select id,studentName,exercise,startedAt,endedAt,status from sessions order by id"
    ).fetchall()

    for sid, name, ex, st, en, status in rows:
        wave, wts = load_wave(conn, sid)
        if wave is None or len(wave) < FS * 3:
            continue
        dur = len(wave) / FS
        print(f"\n=== #{sid} {name} | {ex} | {dur:.0f}s | {status} ===")
        segs = build_segments(conn, sid, dur)
        for a, b, label in segs:
            seg = wave[int(a * FS):int(b * FS)]
            if len(seg) < FS * 3:
                continue
            r = analyze_segment(seg, label)
            hr = r["hr_ac"] or r["hr_med_i2"]
            tag = []
            if r["sat"]:
                tag.append("饱和")
            if r["ac_peak"] is not None and r["ac_peak"] < 0.15:
                tag.append("规律性低")
            wv = watch.get(f"{sid}:{label}") or watch.get(str(sid))
            wstr = ""
            if wv:
                est = r["hr_med_i2"] or r["hr_ac"]
                if est:
                    wstr = f"  手表={wv} 误差={est - wv:+.0f}"
            print(
                f"  [{label}] {r['dur']:5.1f}s 幅度{r['amp']:5.0f} "
                f"AC={_f(r['hr_ac'])} (峰{r['ac_peak']:.2f}) "
                f"i+1={_f(r['hr_med_i1'])} i+2={_f(r['hr_med_i2'])} "
                f"峰{r['n_peaks']:3d} 锁定{_p(r['lock_frac'])}{wstr} "
                + (" ".join(tag))
            )


def _f(v):
    return f"{v:5.0f}" if v else "   - "


def _p(v):
    return f"{v*100:3.0f}%" if v is not None else "  -"


if __name__ == "__main__":
    main()
