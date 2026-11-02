# -*- coding: utf-8 -*-
"""多轮自动测试器：自动衔接无限轮
每轮: 10s贴膜缓冲 -> --dur检测 -> 自动判定(合格/不合格+原因) -> 写latest_result.json -> 5s后下一轮
用法: python host_rounds.py --dur 30        (Ctrl+C 结束全部)
"""
import serial, time, os, sys, statistics, json
from collections import Counter
from host_pulse import PulseV2, LiveView, PORT, BAUD, LOGROOT
from posthoc import posthoc as posthoc_run

WARMUP_S = 10
PAUSE_S = 5

def classify_wearing(series):
    """佩戴三分类: series=[(t,dev)] 最近≥3s窗口
    正确佩戴(规律搏动) / 错位(有接触无搏动) / 悬空(无接触)
    返回 (状态, p95, iv_cv)"""
    if len(series) < 200:
        return '数据不足', 0, 0
    tt = [a for a, _ in series]; dd = [b for _, b in series]
    p95 = sorted(dd)[int(0.95*(len(dd)-1))]
    if p95 < 40:
        return '悬空', p95, -1
    # 峰间隔规律性 + 生理带校验
    peaks = []; last = -9
    for i in range(1, len(dd)-1):
        if dd[i] > 40 and dd[i] >= dd[i-1] and dd[i] >= dd[i+1] and tt[i]-last >= 0.35:
            peaks.append(i); last = tt[i]
    if len(peaks) < 4:
        return '错位', p95, 9.9
    # 隔峰间隔(双峰感知,与主检测器同口径)做规律性
    cyc = [(tt[peaks[j+2]]-tt[peaks[j]])*1000 for j in range(len(peaks)-2)]
    if not cyc:
        return '错位', p95, 9.9
    cyc_ok = [x for x in cyc if 500 <= x <= 1400]
    # 鲁棒CV：只对带内间隔算MAD/中位（偶发漏检长间隙不稀释规律性）
    if len(cyc_ok) >= 3:
        med_c = statistics.median(cyc_ok)
        mad = statistics.median([abs(x - med_c) for x in cyc_ok])
        iv_cv = 1.4826 * mad / med_c if med_c else 9.9
    else:
        iv_cv = 9.9
    regular = (iv_cv <= 0.22 and len(cyc_ok) >= max(2, len(cyc)//3))
    if regular:
        amp_note = '(弱)' if p95 < 55 else ''
        return f'正确佩戴{amp_note}', p95, iv_cv
    return '错位', p95, iv_cv

def verdict(dur, beats):
    """自动判定本轮质量"""
    reasons, ok = [], True
    if not beats:
        return False, ['零检出']
    ivs = [iv for _, iv in beats]
    med = statistics.median(ivs)
    bpm = 60000 / med
    expected = dur * 1.3          # ~78BPM期望
    if len(beats) < 0.8 * expected:
        ok = False; reasons.append(f'检出不足({len(beats)}/{int(expected)})')
    t0b = beats[0][0]
    nb = int((beats[-1][0] - t0b) // 10) + 1
    hist = Counter(int((bt - t0b) // 10) for bt, _ in beats)
    bins = [hist.get(i, 0) for i in range(max(nb, 1))]
    if nb >= 3 and (max(bins) > 2 * max(min(bins), 1)):
        ok = False; reasons.append(f'桶不均衡{bins}')
    if not (550 <= med <= 1250):
        ok = False; reasons.append(f'间隔中位越界{med:.0f}ms')
    if min(ivs) < 550:
        reasons.append(f'疑似重搏波双计{int(min(ivs))}ms')
    if max(ivs) > 1250:
        reasons.append(f'疑似漏检{int(max(ivs))}ms')
    reasons.insert(0, f'{bpm:.0f}BPM {len(beats)}拍 中位{med:.0f}ms 桶{bins}')
    return ok, reasons

def band(p95, mid=None):
    """耦合档位提示（与strap_calib同源阈值）。
    mid: 当前中线电平(可选)——过压判别: 中线>=2600且摆幅低=压闭血管,指引应为放松而非收紧"""
    if mid is not None and mid >= 2600 and p95 < 55:
        return '过压:放松'
    if p95 >= 100: return '合适'
    if p95 >= 55:  return '接近'
    if p95 >= 40:  return '太松'
    return '未贴合'

def run_round(s, idx, dur, outroot):
    session = time.strftime('%Y%m%d_%H%M%S')
    outdir = os.path.join(outroot, f'round_{idx:02d}_' + session)
    os.makedirs(outdir, exist_ok=True)
    f_raw = open(os.path.join(outdir, 'raw_r.log'), 'w', encoding='utf-8')
    f_beats = open(os.path.join(outdir, 'beats.csv'), 'w', encoding='utf-8')
    f_ui = open(os.path.join(outdir, 'ui_log.csv'), 'w', encoding='utf-8-sig')
    f_ui.write('t_s,env,thr,swing,state,bpm_raw,beats_raw,bpm_ph,beats_ph,fills,bpm_census,humps\n')
    det = None
    view = LiveView(n=12)
    t0 = time.time()
    pending = ''
    seq0 = None
    last_view = 0
    # 波形峰普查（供posthoc v3吸附）
    humps = []
    last_pk = -9.0
    base_m = None
    d_prev = 0.0; d_prev2 = 0.0; t_prev = 0.0
    snap_cnt = 0
    # 贴膜质量门控：滚动dev统计
    from collections import deque
    qc_buf = deque(maxlen=800)      # 最近4s(200Hz)的(t,dev)
    qc_quality = '未知'
    good_cyc = []                   # 质量好窗口的隔峰周期累计（分段门控BPM用）
    last_gate_t = -9.0

    def on_beat(t, iv, bpm):
        f_beats.write(f'{t*1000:.0f},{iv:.0f},{bpm:.0f}\n'); f_beats.flush()
    while True:
        d = s.read(4096)
        if not d: continue
        text = pending + d.decode('ascii', errors='replace')
        lines = text.split('\n')
        pending = lines.pop()   # 尾部可能是半行，留到下一轮拼接
        for line in lines:
            line = line.strip()
            if not line.startswith('R,'): continue
            try:
                parts = line.split(',')
                if len(parts) == 4:
                    _, sq, a, b = parts; seq, wmin, wmax = int(sq), int(a), int(b)
                else:
                    _, a, b = parts; seq, wmin, wmax = -1, int(a), int(b)
            except ValueError:
                continue
            t = time.time() - t0
            f_raw.write(f'{t:.4f} {seq} {wmin} {wmax}\n')

            # 信号链统一预处理：中线EMA + 整流dev
            mid = (wmin + wmax) / 2
            base_m = mid if base_m is None else base_m + 0.005/4.0*(mid - base_m)
            # 跳变跟随(持续性判据)：中线偏离>80须持续100ms(20窗)才吸附——脉搏的振荡性摆动会回位，不触发；真实位置移动持续偏移，触发
            if abs(mid - base_m) > 80:
                snap_cnt += 1
                if snap_cnt >= 20:
                    base_m = mid
                    snap_cnt = 0
            else:
                snap_cnt = 0
            dev_now = max(abs(wmax - base_m), abs(wmin - base_m))

            if t < WARMUP_S:
                if seq >= 0: seq0 = seq
                qc_buf.append((t, dev_now))
                if t - last_view >= 0.5:
                    last_view = t
                    recent = [(tt, d) for tt, d in qc_buf if t - tt <= 4.0]
                    qc_quality, qc_p95, qc_ivcv = classify_wearing(recent)
                    print(f'\r[{idx}] 贴膜倒计时 {WARMUP_S - int(t)} 秒  佩戴:{qc_quality} p95={qc_p95:.0f}   ',
                          end='', flush=True)
                continue

            if det is None:
                det = PulseV2(); det.beat_cb = on_beat
                if seq >= 0: seq0 = seq
                print(f'\n[{idx}] === 检测开始({dur:.0f}s) 贴膜质量:{qc_quality} ===')

            t_alg = ((seq - seq0) * 0.005) if (seq >= 0 and seq0 is not None) else (t - WARMUP_S)
            if t_alg >= dur:
                f_raw.close(); f_beats.close(); f_ui.close()
                return det.beats, outdir, qc_quality
            # 增量峰普查（3点局部极大, 350ms最小间距）
            dev = dev_now
            qc_buf.append((t_alg, dev))
            if d_prev > 40 and d_prev >= dev and d_prev >= d_prev2 and t_prev - last_pk >= 0.35:
                humps.append(t_prev); last_pk = t_prev
            d_prev2, d_prev, t_prev = d_prev, dev, t_alg
            det.feed(t_alg, wmin, wmax)
            if t - last_view >= 0.5:
                last_view = t
                snap = det.snapshot()
                # 主检测器=峰普查隔峰中值（双峰形态免疫）；PulseV2仅参考
                bpm_census = 0.0
                if len(humps) >= 3:
                    cyc = [(humps[i+2]-humps[i])*1000 for i in range(len(humps)-2)]
                    okc = [x for x in cyc if 500 <= x <= 1400]
                    if len(okc) >= 3:
                        bpm_census = 60000/statistics.median(okc[-15:])
                # posthoc v3 实时补偿（波形验证补拍：吸附到真实峰）
                raw_ts = [bt for bt, _ in det.beats]
                ph_ts, ph_rm, ph_p = posthoc_run(raw_ts, humps=humps)
                fills = len(ph_ts) - len(raw_ts) + len(ph_rm)
                bpm_ph = 60000/ph_p if ph_p else 0
                f_ui.write(f"{t_alg:.1f},{snap['env']:.0f},{snap['thr']:.0f},{snap['swing']:.0f},"
                           f"{snap['state']},{snap['bpm']:.1f},{snap['nbeats']},"
                           f"{bpm_ph:.1f},{len(ph_ts)},{fills},{bpm_census:.1f},{len(humps)}\n")
                if int(t_alg) != int(t_alg - (t - last_view)):
                    f_ui.flush()
                wear_now, p95_now, _ = classify_wearing([(tt, d) for tt, d in qc_buf if t_alg - tt <= 4.0])
                # 快窗p95(2s)：档位提示响应减半；分类决策仍用4s稳窗
                fast = [d for tt, d in qc_buf if t_alg - tt <= 2.0]
                p95_fast = sorted(fast)[int(0.95*(len(fast)-1))] if len(fast) > 100 else p95_now
                bd = band(p95_fast, mid=base_m)
                # 分段门控：每5s把好窗的隔峰周期并入good_cyc
                if t_alg - last_gate_t >= 5.0:
                    last_gate_t = t_alg
                    if '正确佩戴' in wear_now and '弱' not in wear_now and len(humps) >= 3:
                        seg_h = [h for h in humps if h > t_alg - 5.5]
                        for j in range(len(seg_h)-2):
                            c = (seg_h[j+2]-seg_h[j])*1000
                            if 500 <= c <= 1400:
                                good_cyc.append(c)
                        good_cyc = good_cyc[-40:]
                bpm_gated = 60000/statistics.median(good_cyc) if len(good_cyc) >= 4 else 0
                print(f"\r[{idx}] {dur - t_alg:5.1f}s剩 普查={bpm_census:.0f} 好段={bpm_gated:.0f}({len(good_cyc)}样本) "
                      f"p95={p95_fast:.0f}[{bd}] {wear_now}   ",
                      end='', flush=True)

def main():
    dur = 30.0
    pause = PAUSE_S
    note = ''
    i = 0
    while i < len(sys.argv):
        a = sys.argv[i]
        if a == '--dur' and i + 1 < len(sys.argv):
            dur = float(sys.argv[i + 1])
        elif a == '--pause' and i + 1 < len(sys.argv):
            pause = float(sys.argv[i + 1])
        elif a == '--note' and i + 1 < len(sys.argv):
            note = sys.argv[i + 1]
        i += 1
    safe = ''.join(c for c in note if c not in r'\/:*?"<>|').strip()
    outroot = os.path.join(LOGROOT, 'rounds_' + time.strftime('%Y%m%d_%H%M%S') + ('_' + safe if safe else ''))
    os.makedirs(outroot, exist_ok=True)
    rounds_csv = os.path.join(outroot, 'rounds_log.csv')
    if not os.path.exists(rounds_csv):
        open(rounds_csv, 'w', encoding='utf-8-sig').write('round,bpm,beats,med_ms,ok,note,reasons\n')
    open(os.path.join(outroot, 'NOTE.txt'), 'w', encoding='utf-8').write(
        f'标注: {note or "(无)"}\n协议: 每轮{dur:.0f}s检测+{WARMUP_S}s贴膜缓冲, 轮间隔{pause:.0f}s\n'
        f'开始: {time.strftime("%Y-%m-%d %H:%M:%S")}\n')
    print(f'多轮测试器: 每轮{dur:.0f}s检测+{WARMUP_S}s缓冲, Ctrl+C退出。')
    print(f'标注: {note or "(无)"}')
    print(f'结果目录: {outroot}')

    s = serial.Serial(PORT, BAUD, timeout=0.05)
    s.reset_input_buffer()
    idx = 0
    while True:
        idx += 1
        beats, outdir, qc = run_round(s, idx, dur, outroot)
        ok, reasons = verdict(dur, beats)
        reasons.insert(0, f'贴膜质量:{qc}')
        # 轮末posthoc终值（与实时显示同源；humps需从该轮数据重算）
        humps_end = []
        last_pk = -9.0; base_m = None; d_p = 0.0; d_p2 = 0.0; t_p = 0.0
        for ln in open(os.path.join(outdir, 'raw_r.log'), encoding='utf-8'):
            parts = ln.split()
            if len(parts) != 4: continue
            try:
                sq, wmn, wmx = int(parts[1]), float(parts[2]), float(parts[3])
            except ValueError:
                continue
            tt = (sq - int(open(os.path.join(outdir,'raw_r.log'), encoding='utf-8').readline().split()[1])) * 0.005
            if tt < 10: continue
            mid = (wmn + wmx) / 2
            base_m = mid if base_m is None else base_m + 0.005/4.0*(mid - base_m)
            dv = max(abs(wmx - base_m), abs(wmn - base_m))
            if d_p > 40 and d_p >= dv and d_p >= d_p2 and t_p - last_pk >= 0.35:
                humps_end.append(t_p - 10.0); last_pk = t_p
            d_p2, d_p, t_p = d_p, dv, tt
        ph_ts, ph_rm, ph_p = posthoc_run([bt for bt, _ in beats], humps=humps_end)
        bpm_ph = 60000 / ph_p if ph_p else 0
        fills = len(ph_ts) - len(beats) + len(ph_rm)
        reasons.append(f'补偿后{bpm_ph:.1f}BPM({len(ph_ts)}拍,补{fills}剔{len(ph_rm)})')
        tag = '合格' if ok else '不合格'
        print(f'\n[{idx}] ===== {tag} ===== ' + ' | '.join(reasons))
        med = statistics.median([iv for _, iv in beats]) if beats else 0
        bpm = 60000 / med if med else 0
        with open(rounds_csv, 'a', encoding='utf-8-sig') as f:
            f.write(f'{idx},{bpm:.1f},{len(beats)},{med:.0f},{1 if ok else 0},{note};{";".join(reasons)}\n')
        result = {'round': idx, 'ok': ok, 'bpm': round(bpm, 1), 'beats': len(beats),
                  'median_iv_ms': round(med), 'coupling_qc': qc,
                  'bpm_posthoc': round(bpm_ph, 1), 'beats_posthoc': len(ph_ts), 'fills': fills,
                  'reasons': reasons,
                  'note': note, 'outdir': outdir, 'stamp': time.strftime('%H:%M:%S')}
        with open(os.path.join(outroot, 'latest_result.json'), 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=1)
        print(f'[{idx}] {pause:.0f}s后自动开始第{idx+1}轮（保持贴膜/调整姿势，看倒计时"信号:好"再准备）...')
        time.sleep(pause)

if __name__ == '__main__':
    main()
