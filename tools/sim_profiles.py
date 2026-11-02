# -*- coding: utf-8 -*-
"""心率轨迹形态扫描：不同"速度模式"下跟踪器的响应与收敛。

覆盖：
  L   线性上升 80→160（20s）
  E   指数上升 80→160（τ=5s）
  S   阶跃（瞬时 80→160，生理上不可能，用于压力测试）
  D   阶跃下降 160→80
  T   双段：80→110（10s）→ 保持 5s → 110→160（10s）
  W   冲刺循环：90↔170 往复
  O   正弦调制 100±30（周期 20s）
  R   随机游走 ±10（模拟 HRV 抖动）
"""
import math, random, statistics
import sim_tracker as S
import sim_robust as R

FS = 200
DUR = 60.0

def profile(name, t):
    if name == 'L':
        return 80 + 80 * min(1.0, t / 20)
    if name == 'E':
        return 80 + 80 * (1 - math.exp(-t / 5))
    if name == 'S':
        return 80 if t < 20 else 160
    if name == 'D':
        return 160 if t < 20 else 80
    if name == 'T':
        if t < 10: return 80 + 30 * (t / 10)
        if t < 15: return 110
        return 110 + 50 * min(1.0, (t - 15) / 10)
    if name == 'W':
        ph = t % 28
        if ph < 8: return 90 + 80 * (ph / 8)     # 冲刺
        return 170 - 80 * min(1.0, (ph - 8) / 20)  # 恢复
    if name == 'O':
        return 100 + 30 * math.sin(2 * math.pi * t / 20)
    if name == 'R':
        return None   # 单独处理（随机游走）
    return 100

def build(name, seed, noise=4.0, ripple=40.0, floor=12.0, sa=2.0, vmax=8.0, extend=True, gate=4.0, coast=1.0, k_p95=0.0, sigma_win=True, hrv=0.05, gate_abs=45.0, fading=True, chi2=16.0):
    rng = random.Random(seed)
    if name == 'R':
        # 随机游走心率（带恢复力）
        hrs = []; h = 100.0
        for k in range(int(DUR * FS)):
            if k % 100 == 0:
                h += rng.gauss(0, 3.0) + 0.05 * (100 - h)
                h = max(60, min(170, h))
            hrs.append(h)
        fn = lambda t: hrs[min(len(hrs) - 1, int(t * FS))]
    else:
        fn = lambda t: profile(name, t)
    dev = S.synth_dev(fn, DUR, noise=noise, ripple_hz=5.0, ripple_amp=ripple, seed=seed)
    dev = [v + floor for v in dev]
    tr = R.V2(sa, vmax, extend=extend, gate=gate, coast=coast, k_p95=k_p95, sigma_win=sigma_win, hrv=hrv, gate_abs=gate_abs, fading=fading, chi2=chi2)
    rows = []
    for i, d in enumerate(dev):
        t = i / FS
        tr.feed(t, d)
        if i % 100 == 99:
            rows.append((t, tr.out()))
    return rows, fn

def metrics(rows, fn, skip=5.0):
    est = [(t, b) for t, b in rows if b > 0 and t >= skip]
    if len(est) < 20:
        return dict(cov=len(est) / max(1, len(rows)), mae=999, p90=999, mx=999,
                    lag=999, step_t=999)
    err = [abs(b - fn(t)) for t, b in est]
    # 滞后：把估计序列与真值做互相关，找最佳位移
    ts = [t for t, _ in est]
    best_lag, best_cost = 0, 1e18
    for lag in range(0, 30):           # 0~15s
        cost = 0; n = 0
        for i in range(lag, len(est)):
            cost += abs(est[i][1] - fn(ts[i] - lag * 0.5))
            n += 1
        cost /= max(1, n)
        if cost < best_cost:
            best_cost, best_lag = cost, lag * 0.5
    # 阶跃收敛（只对 S/D 有意义）：阶跃后回到 ±5 的时间
    step_t = 999
    for t, b in est:
        if t > 20 and abs(b - fn(t)) <= 5:
            # 要求之后 2s 都在带内
            ok = all(abs(bb - fn(tt)) <= 8 for tt, bb in est if t <= tt <= t + 2)
            if ok:
                step_t = t - 20
                break
    return dict(cov=len(est) / max(1, len(rows)),
                mae=statistics.mean(err), p90=R.pct(err, 0.9), mx=max(err),
                lag=best_lag, step_t=step_t)

if __name__ == '__main__':
    names = [('L', '线性 80→160/20s'), ('E', '指数 80→160(τ5s)'), ('S', '阶跃 80→160'),
             ('D', '阶跃 160→80'), ('T', '双段 80→110→160'), ('W', '冲刺循环 90↔170'),
             ('O', '正弦 100±30'), ('R', '随机游走 ±10')]
    for sa, vmax in ((2.0, 8.0), (4.0, 12.0), (8.0, 20.0)):
        print(f'\n===== σ_a={sa}  v_max={vmax} =====')
        print(f'{"轨迹":22s} {"覆盖率":>6s} {"MAE":>6s} {"p90":>6s} {"最大":>6s} {"滞后s":>6s} {"阶跃收敛s":>8s}')
        for key, label in names:
            ms = []
            for seed in range(6):
                rows, fn = build(key, seed, sa=sa, vmax=vmax)
                ms.append(metrics(rows, fn))
            agg = {k: statistics.median([m[k] for m in ms]) for k in ms[0]}
            print(f'{label:22s} {agg["cov"]*100:5.0f}% {agg["mae"]:6.1f} {agg["p90"]:6.1f} '
                  f'{agg["mx"]:6.1f} {agg["lag"]:6.1f} {agg["step_t"]:8.1f}')
