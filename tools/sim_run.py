# -*- coding: utf-8 -*-
"""明天实测前的最后一轮仿真：跑步抖动 + 弱信号 + 频率混叠

场景设计（全部用真实脉搏形态做底）：
  A 持续抖动     步频 2.6~3.2Hz 正弦型振动叠加（手套耦合版），幅度扫 50~400
  B 弱信号       脉搏幅度压到噪声底的 1.2~3 倍（模拟戴松/低灌注）
  C 频率混叠     心率=步频×2 或 ×1 的危险区间（160BPM=2.67Hz 跑 步频 160spm）
每个场景跑 8 个种子，统计：老方法 BPM 误差分布 / 质量门拦截率 / 新方法(影子)对照
"""
import math, random, statistics, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sim_tracker as S

FS = 200

def synth(hr, dur, seed, pulse_amp=120, noise=4, jitter=0.012,
          vib_hz=0, vib_amp=0, floor=12, dicrotic=0.45):
    rng = random.Random(seed)
    n = int(dur * FS)
    dev = [0.0] * n
    t = 0.5
    beats = []
    while t < dur:
        beats.append(t)
        P = 60.0 / hr
        for k in range(int(-0.3 * P * FS), int(0.3 * P * FS)):
            i = int(t * FS) + k
            if 0 <= i < n:
                dev[i] += pulse_amp * math.exp(-(k / FS) ** 2 / (2 * 0.035 ** 2))
        for k in range(int(-0.25 * P * FS), int(0.35 * P * FS)):
            i = int((t + 0.42 * P) * FS) + k
            if 0 <= i < n:
                dev[i] += dicrotic * pulse_amp * math.exp(-(k / FS) ** 2 / (2 * 0.05 ** 2))
        t += P * (1 + rng.uniform(-jitter, jitter))
    for i in range(n):
        v = dev[i] + rng.gauss(0, noise) + floor
        if vib_hz > 0:
            v += vib_amp * abs(math.sin(math.pi * vib_hz * i / FS))   # |sin|→每周期一个包
        dev[i] = max(0.0, v)
    return dev

# ---------- 老方法复刻（与固件一致） ----------
def old_method(devs):
    P95N = 800; buf = []
    d2 = d1 = 0.0; tp1 = 0.0; last = -1e9
    peaks = []; ivs = []; reject = 0
    q_cnt = 2; q_ok = True; out = []
    for i, dv in enumerate(devs):
        buf.append(dv)
        if len(buf) > P95N: buf.pop(0)
        if i % 100 == 0 and len(buf) >= 200:
            s = sorted(buf); p50 = s[len(s) // 2]; p95 = s[min(len(s) - 1, int(len(s) * 0.95))]
            ok = (p95 >= 45 and p50 >= 18)
            q_cnt = min(4, q_cnt + 1) if ok else max(0, q_cnt - 1)
            q_ok = q_cnt >= 2
        if d1 > 40 and d1 >= dv and d1 >= d2 and tp1 - last >= 0.35:
            last = tp1; peaks.append(tp1)
            if len(peaks) > 27: peaks.pop(0)
            if len(peaks) >= 3:
                iv = int((peaks[-1] - peaks[-3]) * 1000)
                if 300 <= iv <= 1400:
                    acc = True
                    if len(ivs) >= 3:
                        m = sorted(ivs)[len(ivs) // 2]
                        if iv > m * 13 // 10 or iv * 13 // 10 < m: acc = False
                    if acc:
                        reject = 0; ivs = (ivs + [iv])[-9:]
                    else:
                        reject += 1
                        if reject >= 4: ivs = []; reject = 0
        d2, d1 = d1, dv; tp1 = i * 0.005
        if i % 100 == 99:
            out.append(60000 // sorted(ivs)[len(ivs) // 2] if (q_ok and len(ivs) >= 3) else 0)
    return out

def run_case(name, hr, seeds=8, **kw):
    errs, zeros = [], 0
    for sd in range(seeds):
        dev = synth(hr, 30, sd, **kw)
        out = old_method(dev)
        nz = [b for b in out if b > 0]
        if nz:
            errs.append(statistics.median(nz))
        else:
            zeros += 1
    if errs:
        med = statistics.median(errs)
        print(f'{name:34s} 出数={len(errs)}/{seeds} 中位BPM={med:6.1f} 误差={abs(med-hr):6.1f} '
              f'全空={zeros}')
        return abs(med - hr), zeros
    print(f'{name:34s} 全空 {seeds}/{seeds}')
    return 999, seeds

if __name__ == '__main__':
    print('=== A. 持续抖动（步频正弦包，HR=140）===')
    for amp in (0, 50, 100, 200, 400):
        run_case(f'  振动幅度 {amp}', 140, vib_hz=2.8, vib_amp=amp)
    print('=== B. 弱信号（HR=75，幅度压低）===')
    for pa in (120, 80, 60, 40, 25):
        run_case(f'  脉搏幅度 {pa}', 75, pulse_amp=pa)
    print('=== C. 频率混叠（HR=步频×2 / ×1）===')
    run_case('  HR160 + 步频2.67Hz(×1)', 160, vib_hz=2.67, vib_amp=200)
    run_case('  HR160 + 步频1.33Hz(×2)', 160, vib_hz=1.33, vib_amp=200)
    run_case('  HR140 + 步频2.33Hz(×1)', 140, vib_hz=2.33, vib_amp=200)
    run_case('  HR140 + 步频1.17Hz(×2)', 140, vib_hz=1.17, vib_amp=200)
