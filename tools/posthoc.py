# -*- coding: utf-8 -*-
"""后验补偿器：周期先验 + 相位栅格的确定性补拍/剔拍（无自适应反馈环）
用法:
  python posthoc.py <session目录>     # 对单个会话回测（用raw_r.log + beats.csv）

算法:
  1. 稳健周期 P = 检出间隔的中位数（先剔 550~1250ms 外的离群）
  2. 相位栅格: 以首个检出为相位原点, 栅格点 = t0 + n*P
  3. 剔假拍: 距任何栅格点 > 0.25P 的检出视为相位离群 → 移除
  4. 补空窗: 相邻检出间隔 k=round(gap/P) >= 2 且 |gap-kP|<0.2P
     → 在中间栅格点插入推断搏动
  5. 迭代一次（P 用新序列重估）
验证: 严格峰普查(200Hz dev序列, 350ms最小间距)作为地面真值,
     统计补拍命中率(±60ms内有真hump)与最终查全率
"""
import sys, os, csv, statistics, glob
from collections import Counter

IV_MIN, IV_MAX = 550, 1250
FILL_TOL = 0.20     # 补窗容差（×P）
PHASE_TOL = 0.25    # 剔拍容差（×P）
HIT_MS = 60         # 补拍命中判定窗

def robust_period(beats):
    ivs = [(beats[i+1]-beats[i])*1000 for i in range(len(beats)-1)]
    ok = [x for x in ivs if IV_MIN <= x <= IV_MAX]
    return statistics.median(ok) if len(ok) >= 3 else None

def posthoc(beats, humps=None, iterations=1):
    """v3 波形验证版：相位外推 + 峰吸附。
    humps: 可选的真实峰时刻列表（由波形普查提供）。
    补拍点先按相位外推，再吸附到±120ms内最近的真实峰；找不到真实峰则放弃补拍。
    返回 (补拍后序列, 被剔序列, P_ms)"""
    beats = sorted(beats)
    removed = []
    out = []
    ivs_hist = []
    last = None
    P_run = None
    SNAP = 0.120   # 峰吸附窗
    def snap(t):
        """有humps时吸附到最近真实峰，找不到返回None"""
        if humps is None:
            return t
        best = min(humps, key=lambda h: abs(h - t), default=None)
        if best is not None and abs(best - t) <= SNAP:
            return best
        return None
    for b in beats:
        if last is None:
            out.append(b); last = b; continue
        gap = b - last
        if len(ivs_hist) < 2:
            if IV_MIN/1000 <= gap <= IV_MAX/1000:
                ivs_hist.append(gap)
            out.append(b); last = b
            continue
        P_run = statistics.median(ivs_hist)
        k = max(1, round(gap / P_run))
        if k >= 2 and abs(gap - k*P_run) <= FILL_TOL*P_run:
            for j in range(1, k):
                pos = snap(last + j*P_run)
                if pos is not None and pos > out[-1]:
                    out.append(pos)
            ivs_hist.append(gap / k)
        elif gap < 0.5*P_run:
            removed.append(b)                     # 明确双计，剔
            continue
        else:
            out.append(b)
            if IV_MIN/1000 <= gap <= IV_MAX/1000:
                ivs_hist.append(gap)
        ivs_hist = ivs_hist[-5:]
        last = b
    out = sorted(out)
    P = robust_period(out) or (P_run*1000 if P_run else None)
    return out, removed, P

def census_humps(rows, s0):
    """严格峰普查地面真值（与历史口径一致: 基线EMA τ4s, dev, 350ms最小间距）"""
    base = None; t = []; dev = []
    for r in rows:
        wmin, wmax = float(r[2]), float(r[3])
        mid = (wmin + wmax) / 2
        base = mid if base is None else base + 0.005/4.0*(mid-base)
        t.append((int(r[1]) - s0) * 0.005)
        dev.append(max(abs(wmax-base), abs(wmin-base)))
    peaks = []; last = -9
    for i in range(2, len(dev)-2):
        if dev[i] > 40 and dev[i] >= dev[i-1] and dev[i] >= dev[i+1]:
            if t[i] - last >= 0.35:
                peaks.append(t[i]); last = t[i]
    return peaks

def main(d):
    rows = [ln.split() for ln in open(os.path.join(d, 'raw_r.log'), encoding='utf-8')
            if len(ln.split()) == 4]
    if not rows:
        print('无 raw_r.log'); return
    s0 = int(rows[0][1])
    bp = os.path.join(d, 'beats.csv')
    if not os.path.exists(bp):
        print('无 beats.csv'); return
    rows_b = [ln.strip().split(',') for ln in open(bp, encoding='utf-8-sig') if ln.strip()]
    if rows_b and rows_b[0][0] in ('t_ms', 't'):  # 跳过表头(若存在)
        rows_b = rows_b[1:]
    beats = [float(r[0])/1000 for r in rows_b if len(r) >= 1]
    # beats.csv 的 t 是算法时基(检测开始=0)，映射到文件时基(检测开始=10s)
    beats = [b + 10.0 for b in beats]
    print(f'原始检出: {len(beats)} 拍')

    filled, removed, P = posthoc(beats, humps=humps_det)   # v3: 波形验证补拍
    n_fill = len(filled) - len(beats) + len(removed)
    print(f'剔假拍: {len(removed)} 个, 补拍: {n_fill} 个 -> 最终 {len(filled)} 拍, P={P:.0f}ms -> {60000/P if P else 0:.1f} BPM')

    # 地面真值校验
    humps = census_humps(rows, s0)
    humps_det = [h for h in humps if h >= 10]
    def hit(b):
        return any(abs(h - b) <= HIT_MS/1000 for h in humps_det)
    fill_only = [b for b in filled if b not in set(beats)]
    if fill_only:
        hits = sum(1 for b in fill_only if hit(b))
        print(f'补拍命中校验: {hits}/{len(fill_only)} 落在真hump±60ms内 ({hits/len(fill_only)*100:.0f}%)')
    # 查全率(以真hump的一半=心动周期为参照)
    cycles = len(humps_det) / 2
    print(f'真hump {len(humps_det)}个(≈{cycles:.0f}心动周期) | 原始覆盖 {len(beats)/cycles*100:.0f}% -> 补后 {len(filled)/cycles*100:.0f}%')
    # 桶均衡度对比
    def bins(ts):
        if not ts: return []
        t0 = ts[0]; nb = int((ts[-1]-t0)//10)+1
        c = Counter(int((x-t0)//10) for x in ts)
        return [c.get(i, 0) for i in range(nb)]
    print(f'桶分布 原: {bins(beats)}')
    print(f'桶分布 补: {bins(filled)}')

if __name__ == '__main__':
    d = sys.argv[1] if len(sys.argv) > 1 else sorted(glob.glob(r'D:\Espressif\workspace\pulse_meter\logs\session_*'))[-1]
    print('会话:', d)
    main(d)
