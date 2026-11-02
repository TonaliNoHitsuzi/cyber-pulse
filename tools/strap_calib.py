# -*- coding: utf-8 -*-
"""绑带耦合校准器 —— 组装/佩戴时确保松紧度落在可靠档
依据: 交接文档实证分级 —— p95>=100=可靠(±2), 55~100=接近, 40~55=弱档(精度无保证), <40=未贴合
判定: 连续5秒 p95>=100 → 校准通过(打印报告并落盘)

用法: python strap_calib.py          (Ctrl+C 退出)
      python strap_calib.py --csv    # 额外逐秒CSV
"""
import serial, time, os, sys, statistics
from collections import deque
from host_rounds import classify_wearing, PORT, BAUD

LOGROOT = r'D:\Espressif\workspace\pulse_meter\logs'
PASS_HOLD_S = 5.0        # 连续达标时长
TARGET = 100             # 可靠档门槛(实证)
OK2, WEAK = 55, 40       # 接近/弱档门槛

def band(p95, mid=None):
    if mid is not None and mid >= 2600 and p95 < 55:
        return '过压:放松'
    if p95 >= TARGET: return '合适'
    if p95 >= OK2:    return '接近'
    if p95 >= WEAK:   return '太松'
    return '未贴合'

def main():
    csv_mode = '--csv' in sys.argv
    outdir = os.path.join(LOGROOT, 'calib_' + time.strftime('%Y%m%d_%H%M%S'))
    os.makedirs(outdir, exist_ok=True)
    log = open(os.path.join(outdir, 'calib.log'), 'w', encoding='utf-8')

    s = serial.Serial(PORT, BAUD, timeout=0.05)
    s.reset_input_buffer()
    buf = deque(maxlen=800)       # 4s滚动窗
    pending = ''
    t0 = time.time()
    good_since = None
    passed = False
    history = []                  # (t, p95, band)
    print('绑带耦合校准器: 调整松紧, 达标后保持5秒自动通过 (Ctrl+C退出)')

    while True:
        d = s.read(4096)
        if not d: continue
        text = pending + d.decode('ascii', errors='replace')
        lines = text.split('\n'); pending = lines.pop()
        for ln in lines:
            ln = ln.strip()
            if not ln.startswith('R,'): continue
            f = ln.split(',')
            if len(f) != 4: continue
            try:
                wmin, wmax = int(f[2]), int(f[3])
            except ValueError: continue
            t = time.time() - t0
            mid = (wmin + wmax) / 2
            base = getattr(main, '_base', None)
            main._base = mid if base is None else base + 0.005/4.0*(mid-base)
            # 跳变跟随(持续性判据)：偏离>80须持续100ms才吸附，脉搏振荡不触发
            main._snap = getattr(main, '_snap', 0)
            if abs(mid - main._base) > 80:
                main._snap += 1
                if main._snap >= 20:
                    main._base = mid
                    main._snap = 0
            else:
                main._snap = 0
            dev = max(abs(wmax - main._base), abs(wmin - main._base))
            buf.append((t, dev))
        if not buf: continue
        t_now = buf[-1][0]
        recent = [(tt, dd) for tt, dd in buf if t_now - tt <= 4.0]
        if len(recent) < 200: continue
        p95 = sorted(d for _, d in recent)[int(0.95*(len(recent)-1))]
        b = band(p95, mid=getattr(main, '_base', None))
        history.append((round(t_now,1), round(p95), b))
        log.write(f'{t_now:.1f} {p95:.0f} {b}\n')
        log.flush()

        # 通过逻辑
        if b == '合适':
            if good_since is None: good_since = t_now
            hold = t_now - good_since
            if hold >= PASS_HOLD_S and not passed:
                passed = True
                p95s = [p for _,p,_ in history[-40:] if p >= TARGET]
                rpt = (f'=== 校准通过 === 最近档位统计: 合适{sum(1 for _,_,x in history if x=="合适")}s | '
                       f'接近{sum(1 for _,_,x in history if x=="接近")}s | '
                       f'太松{sum(1 for _,_,x in history if x=="太松")}s | '
                       f'达标段p95中位{statistics.median(p95s):.0f}')
                print('\n' + rpt)
                open(os.path.join(outdir, 'PASSED.txt'), 'w', encoding='utf-8').write(rpt + '\n')
        else:
            good_since = None
            if passed and b != '合适':
                pass  # 通过后掉档继续监测但不撤销(报告里有时长统计)

        meter = int(min(p95, 200) / 200 * 50)
        bar = '█' * meter + '·' * (50 - meter)
        marks = '  ↑40   ↑55        ↑100目标'
        status = f'[{b}]' if b != '合适' else f'[✓合适 保持{max(0, PASS_HOLD_S-(0 if good_since is None else t_now-good_since)):.0f}s]'
        print(f'\r p95={p95:4.0f} |{bar}| {status}   ', end='', flush=True)
        time.sleep(0.2)

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('\n校准器退出')
