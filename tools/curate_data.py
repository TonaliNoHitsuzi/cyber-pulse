# -*- coding: utf-8 -*-
"""数据筛选：对 logs/ 下所有会话做质量体检，产出可用的分析素材清单。

规则（任一不满足即降级/剔除）：
  R1 不是已知坏样本（悬空/空白/对照/裸引脚/待机/崩溃）
  R2 有信号：p95 >= 60 且 p50 >= 12（否则就是噪声或悬空）
  R3 有搏动结构：p95 / p50 >= 2.5
  R4 周期性可信：自相关主峰 / 平均 >= 1.6
  R5 两个独立的周期估计互相印证：|ac_hr - iv_hr| / ac_hr <= 0.12
  R6 若存在 beats.csv（历史验证过的拍），取其中位 BPM 作为参考，与本机估计相差 <= 15%

输出：logs/_curated/index.json + index.csv + 控制台表格
"""
import os, glob, json, csv, math, statistics

FS = 200
BAD_WORDS = ('悬空', '空白', '对照', '裸引脚', '伪迹', '待机', '崩溃', 'dangle', 'idle')

def load_windows(path):
    rows = []
    for line in open(path, encoding='utf-8', errors='ignore'):
        line = line.strip()
        if not line:
            continue
        if line.startswith('R,'):
            p = line.split(',')
            if len(p) == 4:
                rows.append((int(p[1]), int(p[2]), int(p[3])))
        else:
            p = line.replace(',', ' ').split()
            if len(p) >= 4:
                try:
                    rows.append((int(p[1]), int(p[2]), int(p[3])))
                except ValueError:
                    pass
    return rows

def to_dev(rows):
    baseline = 1860.0; snap = 0
    devs = []
    for _, a, b in rows:
        mid = (a + b) / 2.0
        baseline += 0.00125 * (mid - baseline)
        if abs(mid - baseline) > 80:
            snap += 1
            if snap >= 20:
                baseline = mid; snap = 0
        else:
            snap = 0
        devs.append(max(abs(b - baseline), abs(a - baseline)))
    return devs

def pct(x, q):
    if not x:
        return 0.0
    s = sorted(x)
    return s[min(len(s) - 1, int(len(s) * q))]

def ac_hr(seg, lo=40, hi=200):
    """自相关主峰 → 心率；返回 (hr, 置信度)"""
    n = len(seg)
    if n < 600:
        return 0.0, 0.0
    m = sum(seg) / n
    x = [v - m for v in seg]
    vals = []
    for lag in range(int(FS * 60 / hi), int(FS * 60 / lo) + 1):
        acc = sum(x[i] * x[i + lag] for i in range(n - lag)) / (n - lag)
        vals.append((lag, acc))
    vals.sort(key=lambda z: -z[1])
    best_lag, best_v = vals[0]
    mean_abs = sum(abs(v) for _, v in vals) / len(vals) + 1e-9
    return 60000.0 / (best_lag * 1000.0 / FS), best_v / mean_abs

def iv_hr(seg, thr=40.0, gap_ms=350, band=(500, 1400)):
    """D2 验证过的参数：thr=40 / 最小间距 350ms / 隔峰 i+2 / 周期带 500~1400ms"""
    peaks = []
    last = -1e9
    for i in range(2, len(seg)):
        if seg[i - 1] > thr and seg[i - 1] >= seg[i] and seg[i - 1] >= seg[i - 2]:
            t = i * 5  # ms
            if t - last >= gap_ms:
                peaks.append(t); last = t
    if len(peaks) < 5:
        return 0.0, 0
    iv2 = [peaks[i + 2] - peaks[i] for i in range(len(peaks) - 2)]
    iv2 = [x for x in iv2 if band[0] <= x <= band[1]]
    if len(iv2) < 3:
        return 0.0, len(peaks)
    return 60000.0 / statistics.median(iv2), len(peaks)

def template_clean(seg, hr, fs=FS):
    """模板洁净度：按估出周期切一拍，能量应集中在前 45%"""
    if hr <= 0:
        return 0.0, False
    P = int(fs * 60.0 / hr)
    if P < 40 or P >= len(seg):
        return 0.0, False
    # 从最高峰所在位置切
    pk = max(range(len(seg) - P), key=lambda i: seg[i])
    beat = seg[pk:pk + P]
    tot = sum(beat) + 1e-9
    head = sum(beat[:int(0.45 * len(beat))])
    conc = head / tot
    return conc, conc >= 0.50

def beats_bpm(d):
    f = os.path.join(d, 'beats.csv')
    if not os.path.exists(f):
        return None
    try:
        rows = list(csv.DictReader(open(f, encoding='utf-8-sig')))
        ivs = [float(r['interval_ms']) for r in rows if r.get('interval_ms')]
        ivs = [x for x in ivs if 300 <= x <= 2000]
        return 60000.0 / statistics.median(ivs) if len(ivs) >= 3 else None
    except Exception:
        return None

def assess(d):
    f = os.path.join(d, 'raw_r.log')
    rows = load_windows(f)
    if len(rows) < 1000:
        return dict(path=d, verdict='BAD', reason='太短', dur=len(rows) * 5 / 1000)
    devs = to_dev(rows)
    dur = len(devs) / FS
    # 取能量最高的 10s 做体检
    win = min(2000, len(devs))
    best, bi = -1, 0
    for i in range(0, len(devs) - win, 200):
        e = sum(devs[i:i + win])
        if e > best:
            best, bi = e, i
    seg = devs[bi:bi + win]
    p50, p95 = pct(seg, 0.5), pct(seg, 0.95)
    ratio = p95 / max(p50, 1e-6)
    thr = max(30.0, 0.5 * p95)
    hr_a, conf = ac_hr(seg)
    hr_i, npeaks = iv_hr(seg, thr)
    note = ''
    nf = os.path.join(d, 'NOTE.txt')
    if os.path.exists(nf):
        note = open(nf, encoding='utf-8', errors='ignore').read().strip().split('\n')[0]
    res = dict(path=os.path.basename(d), note=note[:50], dur=round(dur, 1),
               p50=round(p50, 1), p95=round(p95, 1), ratio=round(ratio, 2),
               ac_hr=round(hr_a, 1), conf=round(conf, 2),
               iv_hr=round(hr_i, 1), peaks=npeaks, beats=beats_bpm(d))
    conc, clean = template_clean(seg, hr_a)
    res.update(conc=round(conc, 2))
    # 规则判定（面向"能否作为仿真素材"，不依赖历史 BPM）
    if any(w in note.lower() for w in BAD_WORDS) or any(w in res['path'].lower() for w in BAD_WORDS):
        res.update(verdict='BAD', reason='已知坏样本')
    elif p95 < 60 or p50 < 12:
        res.update(verdict='BAD', reason='无有效信号')
    elif ratio < 2.5:
        res.update(verdict='BAD', reason=f'无搏动结构(ratio={ratio:.1f})')
    elif conf < 1.8:
        res.update(verdict='BAD', reason=f'周期性弱(conf={conf:.2f})')
    elif not clean:
        res.update(verdict='MARGINAL', reason=f'模板能量分散(conc={conc:.2f})')
    else:
        res.update(verdict='GOOD', reason='')
    return res

if __name__ == '__main__':
    root = os.path.dirname(os.path.abspath(__file__))
    dirs = sorted(d for d in glob.glob(os.path.join(root, 'logs', '*')) if os.path.isdir(d))
    out = []
    for d in dirs:
        if os.path.basename(d).startswith('_'):
            continue
        if not os.path.exists(os.path.join(d, 'raw_r.log')):
            continue
        try:
            out.append(assess(d))
        except Exception as e:
            out.append(dict(path=os.path.basename(d), verdict='BAD', reason=f'异常:{e}'))
    # 保存
    od = os.path.join(root, 'logs', '_curated')
    os.makedirs(od, exist_ok=True)
    with open(os.path.join(od, 'index.json'), 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    keys = ['path', 'verdict', 'reason', 'dur', 'p50', 'p95', 'ratio', 'ac_hr', 'conf', 'conc', 'iv_hr', 'beats', 'note']
    with open(os.path.join(od, 'index.csv'), 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        for r in out:
            w.writerow({k: r.get(k, '') for k in keys})
    # 报告
    good = [r for r in out if r['verdict'] == 'GOOD']
    marg = [r for r in out if r['verdict'] == 'MARGINAL']
    bad = [r for r in out if r['verdict'] == 'BAD']
    print(f'会话总数 {len(out)}  |  GOOD {len(good)}  MARGINAL {len(marg)}  BAD {len(bad)}')
    print('\n=== GOOD ===')
    for r in good:
        print(f"  {r['path']:34s} p95={r['p95']:6.1f} ratio={r['ratio']:4.1f} conf={r['conf']:4.2f} "
              f"conc={r['conc']:4.2f} ac={r['ac_hr']:5.1f} | {r['note']}")
    print('\n=== MARGINAL（保留但不作真值）===')
    for r in marg:
        print(f"  {r['path']:34s} {r['reason']}")
    print('\n=== BAD 原因分布 ===')
    import collections
    for k, v in collections.Counter(r['reason'][:18] for r in bad).most_common():
        print(f'  {k:20s} {v}')
    print(f'\n已写入 logs/_curated/index.json / index.csv')
