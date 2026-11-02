# -*- coding: utf-8 -*-
"""脉搏试次离线对比分析：v6(峰保持衰减) vs PulseSensor-Amped(原版移植)
用法: python analyze_pulses.py
输入: logs/session_*/samples.csv (10Hz 包络流)
输出: 每会话两种算法的 BPM/检出数/弃数/10s桶均衡度(CV) 对比表
"""
import csv, glob, os, re, statistics
from collections import Counter

ROOT = r'D:\Espressif\workspace\pulse_meter\logs'
TRIM_S = 3          # 头尾各裁3s
DT = 0.1            # 10Hz

def load_sessions():
    out = {}
    for s in sorted(glob.glob(os.path.join(ROOT, 'session_*'))):
        name = os.path.basename(s)[-6:]
        rows = list(csv.DictReader(open(os.path.join(s, 'samples.csv'), encoding='utf-8-sig')))
        env = [float(r['env']) for r in rows if r.get('env', '').strip()]
        raw = open(os.path.join(s, 'raw.log'), encoding='utf-8').read()
        fw = re.search(r'摆幅 ([\d.]+)，死区 ([\d.]+)', raw)
        info = f'校准摆幅{fw.group(1)}死区{fw.group(2)}' if fw else '无校准(旧固件)'
        out[name] = (env, info)
    return out

def metrics(peaks, total_s):
    ivs = [(peaks[i+1]-peaks[i])*1000 for i in range(len(peaks)-1)]
    ok = [x for x in ivs if 550 <= x <= 1250]
    bpm = 60000/statistics.median(ok) if len(ok) >= 3 else 0
    # 10s桶均衡度
    if peaks and total_s > 10:
        nb = int(total_s // 10)
        cnt = Counter(int(p//10) for p in peaks if p < nb*10)
        arr = [cnt.get(i, 0) for i in range(nb)]
        mean = statistics.mean(arr)
        cv = statistics.pstdev(arr)/mean if mean > 0 else 9.0
    else:
        cv = 9.0
    return bpm, len(ok), len(ivs)-len(ok), cv

def sim_v6(env, peak_tau=8.0, trig_frac=0.50, arm_frac=0.40, dz_frac=0.40):
    """v6: 谷底慢跟踪+校准死区+峰保持衰减+相对滞后"""
    n = len(env)
    if n < 100: return []
    cal = env[25:50]                      # 2.5~5s段当校准
    if not cal: cal = env[:25]
    lo = sorted(cal)[int(0.1*(len(cal)-1))]
    hi = sorted(cal)[int(0.95*(len(cal)-1))]
    dz = max(30.0, dz_frac*(hi-lo))
    seg = env[TRIM_S*10:n-TRIM_S*10]
    valley = lo; state = 0; peak = 0; last_peak = 0.0
    last = -10.0; peaks = []
    for i, e in enumerate(seg):
        t = i*DT
        if e < valley: valley = e
        else: valley += (e-valley)*(DT/30.0)      # τ30s上爬
        if state != 1:
            last_peak -= last_peak*DT/peak_tau     # 保持-衰减
            if last_peak < e: last_peak = e
        trig = valley + dz
        if last_peak*trig_frac > trig: trig = last_peak*trig_frac
        if state == 0:
            if e > trig and t-last >= 0.4:
                state = 1; peak = e
        elif state == 1:
            if e > peak: peak = e
            if e < peak*0.7:
                peaks.append(t); last = t; last_peak = peak; state = 2
        else:
            if e < last_peak*arm_frac: state = 0
    return peaks

def sim_amped(env, default_level=None):
    """PulseSensor-Amped 原版逻辑移植（作用在包络流上）
    thresh=T+amp/2 每拍更新；3/5 IBI 不应期；2.5s 无搏重置"""
    n = len(env)
    if n < 100: return []
    seg = env[TRIM_S*10:n-TRIM_S*10]
    mid = statistics.median(seg[:50]) if len(seg) > 50 else statistics.median(seg)
    P = T = thresh = mid; amp = 100.0
    ibi = 800.0; last_beat = -10.0; pulse = False; peaks = []
    for i, sig in enumerate(seg):
        t = i*DT
        Nms = (t - last_beat)*1000
        if sig < thresh and Nms > (ibi/5)*3:        # 搏间窗内才跟踪谷
            if sig < T: T = sig
        if sig > thresh and sig > P:                # 阈上才跟踪峰
            P = sig
        if Nms > 250 and sig > thresh and not pulse and Nms > (ibi/5)*3:
            pulse = True
            peaks.append(t)
            if last_beat > -5:
                ibi = Nms                            # 更新IBI
            last_beat = t
        if sig < thresh and pulse:                   # 搏动结束
            pulse = False
            amp = P - T
            if amp < 5: amp = 5
            thresh = T + amp/2
            P = thresh; T = thresh
        if Nms > 2500:                               # 信号丢失重置
            thresh = mid; P = mid; T = mid
            last_beat = t
    return peaks

def main():
    sessions = load_sessions()
    print('%-8s %-28s' % ('会话', '校准信息'))
    for name, (env, info) in sessions.items():
        print('%-8s %-28s 包络时长~%ds 强度p50/p90=%0.0f/%0.0f' %
              (name, info, len(env)/10,
               statistics.median(env), sorted(env)[int(0.9*(len(env)-1))]))
    print()
    hdr = '%-8s | %-22s | %-22s' % ('会话', 'v6峰保持(8s,0.50)', 'Amped原版')
    print(hdr)
    print('-'*len(hdr))
    v6_bpms, am_bpms = [], []
    for name, (env, info) in sessions.items():
        seg_len = len(env)/10 - 2*TRIM_S
        p1 = sim_v6(list(env))
        p2 = sim_amped(list(env))
        b1 = metrics(p1, seg_len) if p1 else (0,0,0,9)
        b2 = metrics(p2, seg_len) if p2 else (0,0,0,9)
        if b1[0]: v6_bpms.append(b1[0])
        if b2[0]: am_bpms.append(b2[0])
        s1 = f'{b1[0]:.0f}BPM[{b1[1]}有效/{b1[2]}弃] CV{b1[3]:.2f}' if b1[0] else f'-- [{b1[1]}/{b1[2]}] CV{b1[3]:.2f}'
        s2 = f'{b2[0]:.0f}BPM[{b2[1]}有效/{b2[2]}弃] CV{b2[3]:.2f}' if b2[0] else f'-- [{b2[1]}/{b2[2]}] CV{b2[3]:.2f}'
        print('%-8s | %-22s | %-22s' % (name, s1, s2))
    def summ(tag, arr):
        if len(arr) >= 2:
            hit = sum(1 for b in arr if 70 <= b <= 90)
            print(f'{tag}: 命中70-90 {hit}/{len(arr)}  span={max(arr)-min(arr):.0f}  中位={statistics.median(arr):.0f}')
        else:
            print(f'{tag}: 有效试次不足({len(arr)})')
    print()
    summ('v6', v6_bpms)
    summ('Amped', am_bpms)

if __name__ == '__main__':
    main()
