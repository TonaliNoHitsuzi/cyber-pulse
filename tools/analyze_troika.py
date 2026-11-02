# -*- coding: utf-8 -*-
"""用 TROIKA 式谱峰跟踪解算已有跑步数据的 HR

流程（对照 Zhang et al. 2014, "TROIKA", IEEE TBME）：
  1. 带通 0.5~4Hz
  2. 每个滑窗（8s，步进 2s）做 FFT
  3. 候选峰：0.7~3.2Hz（42~192 BPM）
  4. 用 IMU 步频做排除：剔除步频及其谐波 ±0.15Hz 内的候选
  5. 谱峰跟踪：优先选与上次估计最接近的峰（心率不会跳变）
  6. 输出 HR 序列 + 置信度
"""
import sqlite3, struct, sys
import numpy as np

DB = 'run.db'

def load_wave(sid):
    c = sqlite3.connect(DB)
    rows = c.execute('select startTs,count,data from wave_chunks where sessionId=? order by startTs', (sid,)).fetchall()
    ts, v = [], []
    for st, n, data in rows:
        for i, x in enumerate(struct.unpack('<%dh' % n, data)):
            ts.append(st + i * 10); v.append(x)
    c.close()
    return np.array(ts), np.array(v, dtype=float)

def load_imu_cadence(sid):
    """IMU 六轴 → 滑动窗步频（Hz）；时间戳按均匀 50Hz 重建"""
    c = sqlite3.connect(DB)
    rows = c.execute('select startTs,n,data from imu_chunks where sessionId=? order by startTs', (sid,)).fetchall()
    c.close()
    if not rows:
        return None, None
    ts, mag = [], []
    for st, n, data in rows:
        for i in range(n):
            dt, a1, a2, a3, g1, g2, g3 = struct.unpack('<hhhhhhh', data[i*14:(i+1)*14])
            ts.append(st + i * 20)     # 均匀 50Hz 重建（旧数据 dt 有 bug）
            mag.append(np.sqrt((a1/100)**2 + (a2/100)**2 + (a3/100)**2))
    return np.array(ts), np.array(mag)

def bp(x, fs, lo, hi):
    X = np.fft.rfft(x - np.mean(x))
    f = np.fft.rfftfreq(len(x), 1.0/fs)
    X[(f < lo) | (f > hi)] = 0
    return np.fft.irfft(X, len(x))

def cadence_in_window(ti, mg, t0, t1, fs=50):
    m = (ti >= t0) & (ti < t1)
    if m.sum() < fs * 3:
        return 0.0
    y = bp(mg[m], fs, 1.2, 4.0)
    X = np.abs(np.fft.rfft(y))
    f = np.fft.rfftfreq(len(y), 1.0/fs)
    k = (f >= 1.2) & (f <= 4.0)
    if not k.any():
        return 0.0
    return f[np.where(k)[0][np.argmax(X[k])]]

def track_hr(ts, v, ti, mg, win_s=8.0, step_s=2.0):
    fs = 100
    out = []
    prev = None
    t = ts[0]
    end = ts[-1]
    while t + win_s * 1000 <= end:
        m = (ts >= t) & (ts < t + win_s * 1000)
        seg = v[m]
        if len(seg) < fs * 4:
            t += step_s * 1000; continue
        y = bp(seg, fs, 0.5, 4.0)
        X = np.abs(np.fft.rfft(y * np.hanning(len(y))))
        f = np.fft.rfftfreq(len(y), 1.0/fs)
        band = (f >= 0.7) & (f <= 3.2)
        idx = np.where(band)[0]
        if len(idx) == 0:
            t += step_s * 1000; continue
        # 候选峰（局部极大）
        cands = []
        for i in idx:
            if X[i] > X[i-1] and X[i] >= X[i+1]:
                cands.append((f[i], X[i]))
        if not cands:
            t += step_s * 1000; continue
        # 用 IMU 步频排除（步频及其谐波 ±0.15Hz）
        cad = cadence_in_window(ti, mg, t, t + win_s * 1000) if ti is not None else 0
        def excluded(fr):
            if cad <= 0:
                return False
            for h in (1, 2, 3):
                if abs(fr - h * cad) < 0.15 or abs(fr - cad / h) < 0.15:
                    return True
            return False
        filt = [(fr, a) for fr, a in cands if not excluded(fr)]
        pool = filt if filt else cands
        # 谱峰跟踪：优先接近上次估计
        if prev is not None:
            pool.sort(key=lambda z: (abs(z[0] - prev) > 0.15, -z[1]))
        else:
            pool.sort(key=lambda z: -z[1])
        best_f, best_a = pool[0]
        hr = best_f * 60.0
        if 42 <= hr <= 192:
            prev = best_f
            out.append((t, hr, cad * 60 if cad else 0, best_a, len(pool)))
        t += step_s * 1000
    return out

if __name__ == '__main__':
    for sid, name in [(4, '赵国宇'), (5, '张祥')]:
        ts, v = load_wave(sid)
        ti, mg = load_imu_cadence(sid)
        dur = (ts[-1] - ts[0]) / 1000
        print(f'\n=== 会话#{sid} {name} ({dur:.0f}s) ===')
        tr = track_hr(ts, v, ti, mg)
        if not tr:
            print('  无结果'); continue
        hrs = [h for _, h, _, _, _ in tr]
        cads = [c for _, _, c, _, _ in tr if c > 0]
        print(f'  窗口数 {len(tr)}')
        print(f'  HR: 中位={np.median(hrs):.0f} 范围={min(hrs):.0f}~{max(hrs):.0f}')
        if cads:
            print(f'  步频: 中位={np.median(cads):.0f} spm')
        print('  时间线:')
        for k in range(0, len(tr), max(1, len(tr)//10)):
            t, hr, cad, amp, npool = tr[k]
            rel = (t - ts[0]) / 1000
            print(f'   {rel:5.0f}s  HR={hr:5.0f}  步频={cad:5.0f}  候选数={npool}')
