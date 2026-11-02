# -*- coding: utf-8 -*-
"""小波 minimax 阈值去伪迹验证：能否区分"冲击"与"脉搏"？

用已有真实数据构造混合信号：
  - 脉搏：session_20261030_224652（★最佳数据，含真实重搏波）
  - 冲击：dangle_test 里的孤立尖峰（实测的足底撞击替代品）
量化：去噪前后 (a) 脉搏峰保留率 (b) 尖峰抑制比 (c) BPM 反演误差
"""
import os, sys, math, statistics
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sim_tracker as S

# ---------- 极简 db4 离散小波（3 层, 无依赖实现） ----------
DB4 = [0.4829629131445341, 0.8365163037378199, 0.2241438680420134, -0.1294095225512604]

def dwt1(x):
    """单层 Haar 风格但用 db2(db4系数) —— 返回 (近似, 细节)"""
    n = len(x) // 2
    a = [0.0] * n; d = [0.0] * n
    for i in range(n):
        s = x[2*i] * DB4[0] + x[2*i+1] * DB4[1] + x[(2*i+2) % len(x)] * DB4[2] + x[(2*i+3) % len(x)] * DB4[3]
        t = x[2*i] * DB4[3] - x[2*i+1] * DB4[2] + x[(2*i+2) % len(x)] * DB4[1] - x[(2*i+3) % len(x)] * DB4[0]
        a[i] = s; d[i] = t
    return a, d

def wavelet_shrink(x, levels=3, thresh=None):
    """分解→细节系数软收缩→重构。minimax 阈值（Donoho）：0.3936+0.1829·log2(n)"""
    n = len(x)
    sigma_est = statistics.median([abs(v) for v in x]) / 0.6745
    t = thresh if thresh else sigma_est * (0.3936 + 0.1829 * math.log2(max(n, 2)))
    detail_stack = []
    cur = x[:]
    for _ in range(levels):
        half = len(cur) // 2 * 2
        a, d = dwt1(cur[:half])
        detail_stack.append(d)
        cur = a
    # 软收缩
    for d in detail_stack:
        for i in range(len(d)):
            if abs(d[i]) <= t: d[i] = 0.0
            elif d[i] > t:     d[i] -= t
            else:              d[i] += t
    # 重构（这里用近似+细节逐层上采样）
    approx = cur[:]
    for d in reversed(detail_stack):
        up = [0.0] * (len(approx) + len(d))
        for i in range(len(approx)):
            up[2*i]   += approx[i] * DB4[0] + d[i % len(d)] * DB4[3]
            up[2*i+1] += approx[i] * DB4[1] - d[i % len(d)] * DB4[2]
        approx = up
    return approx, t

# ---------- 载入真实素材 ----------
def load(path):
    rows = S.load_windows(path)
    devs, _ = S.to_dev(rows)
    return devs

def peak_list(dev, thr=40, gap=0.35):
    out = []; last = -1e9
    for i in range(2, len(dev)):
        if dev[i-1] > thr and dev[i-1] >= dev[i] and dev[i-1] >= dev[i-2]:
            t = i * 0.005
            if t - last >= gap: out.append(t); last = t
    return out

if __name__ == '__main__':
    pulse = load('logs/session_20261030_224652/raw_r.log')   # 真脉搏
    dangle = load('logs/dangle_test/raw_r.log')              # 真尖峰库

    # 取脉搏 20 秒 + 从悬空库随机抽尖峰（每 0.36s 一个，模拟步频 165 spm）
    seg = pulse[4000:8000]
    import random
    rng = random.Random(7)
    mixed = list(seg)
    impacts = []
    for k in range(0, len(mixed), 72):                     # 200Hz/72 ≈ 2.8Hz
        amp = rng.uniform(250, 600)
        mixed[k] += amp
        impacts.append(k)

    # 去噪
    denoised, thr = wavelet_shrink(mixed, levels=3)

    # 评估
    def eval_sig(sig, name):
        pk = peak_list(sig)
        # 脉搏峰保留：离真脉搏峰 ±60ms 内算命中
        truth = peak_list(seg)
        hit = sum(1 for t in pk if any(abs(t-u) <= 0.06 for u in truth))
        # 尖峰残留：位于撞击点 ±10ms 的检出
        imp = sum(1 for t in pk if any(abs(t - k*0.005) <= 0.01 for k in impacts))
        med_iv2 = 0
        if len(pk) >= 3:
            iv2 = [pk[i+2]-pk[i] for i in range(len(pk)-2)]
            iv2 = [x for x in iv2 if 0.5 <= x <= 1.4]
            if iv2: med_iv2 = statistics.median(iv2)
        bpm = 60000/med_iv2 if med_iv2 else 0
        print(f'{name:10s} 峰数={len(pk):3d} 脉搏命中={hit:3d}/{len(truth)} 尖峰误检={imp:3d} '
              f'BPM={bpm:5.1f} (真值≈78)')
        return hit, imp

    print(f'minimax 阈值 t={thr:.1f}')
    eval_sig(seg, '纯脉搏')
    eval_sig(mixed, '混合(未去)')
    eval_sig(denoised[:len(seg)], '去噪后')
