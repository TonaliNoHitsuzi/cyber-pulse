# -*- coding: utf-8 -*-
"""上位机脉搏算法引擎 —— v2自适应算法复活版
用法:
  实时:  python host_pulse.py            (读COM6, 窗口显示+落盘)
  回放:  python host_pulse.py --replay <session目录>

算法(v2参数, 历史表现: 74/82BPM):
  输入: 200Hz的[min,max]窗口对
  基线: 中线(min+max)/2 的EMA τ4s
  整流: dev = max(|max-基线|, |min-基线|)   峰值保持整流
  包络: dev 的 120ms 滑动平均 (24点)
  自适应: env_max瞬时上冲/τ8s回落, env_min瞬时下探/τ8s回升
  阈值: thr = env_min + 0.45*(env_max-env_min)
  状态机: SEARCH(触发env>thr且距上搏>=280ms) -> IN_PEAK(峰跟踪,回落<70%峰确认)
          -> REFRACT(等env < env_min+0.22*摆幅) -> SEARCH
  BPM: 最近5个有效间隔(550~1250ms)的中值
"""
import serial, time, os, sys, statistics, threading
from collections import deque

PORT = 'COM6'
BAUD = 921600
LOGROOT = r'D:\Espressif\workspace\pulse_meter\logs'

# ---- v2 参数 ----
BASELINE_TAU = 4.0      # s
ENV_TAU = 8.0           # s
ENV_MA_WIN = 24         # 120ms @200Hz
THR_FRAC = 0.45
ARM_FRAC = 0.22
REFRACT_MS = 280
IV_MIN, IV_MAX = 550, 1250
BPM_MED_N = 5
MIN_SWING = 25     # 最小信号摆幅门：低于此判定无信号，禁止检测（防噪声上自适应塌陷误触发）

ST_SEARCH, ST_IN_PEAK, ST_REFRACT = 0, 1, 2

class PulseV2:
    """v2自适应检测器，逐窗口喂 (t_s, win_min, win_max)"""
    def __init__(self):
        self.baseline = None
        self.env_ma = deque(maxlen=ENV_MA_WIN)
        self.env_sum = 0.0
        self.env_max = None; self.env_min = None
        self.state = ST_SEARCH
        self.peak = 0.0
        self.refract_enter_t = None   # REFRACT进入时刻（超时逃生用）
        self.last_beat_t = None
        self.beats = []           # [(t, iv_ms)]
        self.ivs = []
        self.t_prev = None
        self.beat_cb = None       # 回调 (t, iv_ms, bpm)

    def feed(self, t, wmin, wmax):
        dt = (t - self.t_prev) if self.t_prev is not None else 0.005
        self.t_prev = t
        dt = max(dt, 1e-3)

        mid = (wmin + wmax) / 2.0
        if self.baseline is None: self.baseline = mid
        a = min(dt / BASELINE_TAU, 1.0)
        self.baseline += a * (mid - self.baseline)

        dev = max(abs(wmax - self.baseline), abs(wmin - self.baseline))

        if len(self.env_ma) == self.env_ma.maxlen:
            self.env_sum -= self.env_ma[0]
        self.env_ma.append(dev); self.env_sum += dev
        env = self.env_sum / len(self.env_ma)

        if self.env_max is None: self.env_max = self.env_min = env
        a_s = min(dt / ENV_TAU, 1.0)
        if env > self.env_max: self.env_max = env
        else: self.env_max += a_s * (env - self.env_max)
        if env < self.env_min: self.env_min = env
        else: self.env_min += a_s * (env - self.env_min)
        swing = max(self.env_max - self.env_min, 1.0)

        if self.state == ST_SEARCH:
            swing_now = self.env_max - self.env_min
            thr = self.env_min + THR_FRAC * swing
            # 固定280ms不应期（good46验证62拍配置；自适应版本在双峰数据上引发拒绝级联已回滚）
            ok_t = self.last_beat_t is None or (t - self.last_beat_t) * 1000 >= REFRACT_MS
            if env > thr and ok_t and swing_now >= MIN_SWING:
                self.state = ST_IN_PEAK; self.peak = env
        elif self.state == ST_IN_PEAK:
            if env > self.peak: self.peak = env
            if env < self.peak * 0.7:
                if self.last_beat_t is not None:
                    iv = (t - self.last_beat_t) * 1000
                    if IV_MIN <= iv <= IV_MAX:
                        self.ivs.append(iv)
                        self.ivs = self.ivs[-BPM_MED_N*2:]
                        bpm = 60000 / statistics.median(self.ivs[-BPM_MED_N:])
                        self.beats.append((t, iv))
                        if self.beat_cb: self.beat_cb(t, iv, bpm)
                self.last_beat_t = t
                self.refract_enter_t = t
                self.state = ST_REFRACT
        else:  # REFRACT：等包络落回复位电平（无超时逃生——实验证明假触发会挡住真搏动，连续无谷信号属耦合问题应物理解决）
            if env < self.env_min + ARM_FRAC * swing:
                self.state = ST_SEARCH

    def bpm(self):
        if len(self.ivs) >= 3:
            return 60000 / statistics.median(self.ivs[-BPM_MED_N:])
        return 0

    def snapshot(self):
        swing = max((self.env_max or 0) - (self.env_min or 0), 1.0)
        env = self.env_sum / max(len(self.env_ma), 1)
        thr = (self.env_min or 0) + THR_FRAC * swing
        return dict(base=self.baseline or 0, env=env, thr=thr,
                    swing=swing, state=self.state,
                    bpm=self.bpm(), nbeats=len(self.beats))


class LiveView:
    ANSI_CLEAR = '\033[2J\033[H'   # ANSI清屏，不起子进程（cls子进程会卡住串口读取造成USB背压丢数据）
    def __init__(self, n=30):
        self.buf = deque(maxlen=n)
    def show(self, det, t_s, extra=''):
        s = det.snapshot()
        bar_n = 48
        lvl = s['env'] / (s['env'] + 200)
        bar = '#' * int(lvl * bar_n)
        line = (f"t={t_s:6.1f}s BPM={s['bpm']:.0f} 搏={s['nbeats']} "
                f"env={s['env']:5.0f} thr={s['thr']:5.0f} swing={s['swing']:4.0f} "
                f"base={s['base']:.0f} st={s['state']} |{bar:<{bar_n}}| {extra}")
        self.buf.append(line)
        out = [self.ANSI_CLEAR, '=' * 100, '  脉搏算法引擎 v2-adaptive  (Ctrl+C 退出)', '=' * 100]
        out += list(self.buf)[-24:]
        print('\n'.join(out), flush=True)


def live():
    import sys as _s
    DUR_S = 60.0
    for i, a in enumerate(_s.argv):
        if a == '--dur' and i + 1 < len(_s.argv):
            DUR_S = float(_s.argv[i + 1])
    WARMUP_S = 10            # 启动缓冲：贴膜倒计时，期间数据落盘但不进算法
    det = None
    view = LiveView()
    session = time.strftime('%Y%m%d_%H%M%S')
    outdir = os.path.join(LOGROOT, 'session_' + session)
    os.makedirs(outdir, exist_ok=True)
    f_raw = open(os.path.join(outdir, 'raw_r.log'), 'w', encoding='utf-8')
    f_beats = open(os.path.join(outdir, 'beats.csv'), 'w', encoding='utf-8-sig')
    f_beats.write('t_ms,interval_ms,bpm\n')
    print(f'落盘: {outdir}')
    print(f'{WARMUP_S}秒后开始检测，请贴好薄膜并保持静止...')

    s = serial.Serial(PORT, BAUD, timeout=0.05)   # 短超时：Windows下read(size,timeout)会攒满超时才返回，1s长超时曾造成周期性断流假象
    s.reset_input_buffer()
    t0 = time.time()
    pending = ''
    n_win = 0
    last_view = 0
    seq0 = None          # 算法时基锚点：warmup结束后的第一个序号
    while True:
        d = s.read(8192)
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
                    _, seq_s, a, b = parts; wmin, wmax = int(a), int(b); seq = int(seq_s)
                else:
                    _, a, b = parts; wmin, wmax = int(a), int(b); seq = -1
            except ValueError:
                continue
            t = time.time() - t0
            f_raw.write(f'{t:.4f} {seq} {wmin} {wmax}\n')
            n_win += 1

            if t < WARMUP_S:
                remain = WARMUP_S - int(t)
                if t - last_view >= 0.5:
                    last_view = t
                    print(f'  贴膜倒计时 {remain} 秒... (win={n_win})')
                    f_raw.flush()
                seq0 = seq if seq >= 0 else None    # warmup末尾持续更新锚点
                continue

            if det is None:          # 倒计时结束：算法时基锁定到当前序号
                det = PulseV2()
                if seq >= 0:
                    seq0 = seq
                f = f_beats
                def on_beat(t, iv, bpm, f=f):
                    f.write(f'{t*1000:.0f},{iv:.0f},{bpm:.0f}\n'); f.flush()
                det.beat_cb = on_beat
                print(f'=== 开始检测（时长{DUR_S:.0f}秒） ===')

            # 算法时间 = 序号时基（每窗5ms），与主机到达时刻无关
            t_alg = ((seq - seq0) * 0.005) if (seq >= 0 and seq0 is not None) else (t - WARMUP_S)

            if t_alg >= DUR_S:
                # 定时结束：出总结报告
                ivs = [iv for _, iv in det.beats]
                summary = [f'会话: {session}', f'检测时长: {DUR_S:.0f}s (另含{WARMUP_S:.0f}s贴膜缓冲)']
                if ivs:
                    med = statistics.median(ivs)
                    summary.append(f'搏动: {len(ivs)}拍  间隔中位{med:.0f}ms (范围{min(ivs)}~{max(ivs)})')
                    summary.append(f'结论: {60000/med:.1f} BPM')
                    from collections import Counter
                    t0b = det.beats[0][0]
                    hist = Counter(int((bt - t0b) // 10) for bt, _ in det.beats)
                    summary.append('检出/10s: ' + ' '.join(str(hist.get(i, 0)) for i in range(int((det.beats[-1][0]-t0b)//10)+1)))
                else:
                    summary.append('未检出搏动')
                rpt = '\n'.join(summary)
                print('=' * 60); print(rpt); print('=' * 60)
                open(os.path.join(outdir, 'summary.txt'), 'w', encoding='utf-8').write(rpt + '\n')
                f_raw.close(); f_beats.close(); s.close()
                print('报告已写入 summary.txt，测试完成（窗口可关闭）')
                time.sleep(300)
                return

            det.feed(t_alg, wmin, wmax)
            if t - last_view >= 0.5:
                last_view = t
                remain = DUR_S - t_alg
                f_raw.flush()
                view.show(det, t_alg, extra=f'剩{remain:.0f}s win={n_win}')


def replay(session_dir):
    det = PulseV2()
    import glob, re
    files = glob.glob(os.path.join(session_dir, 'raw_r.log'))
    if not files:
        print('无 raw_r.log（该会话不是v9格式）'); return
    beats = []
    det.beat_cb = lambda t, iv, bpm: beats.append((t, iv, bpm))
    for ln in open(files[0], encoding='utf-8'):
        parts = ln.split()
        if len(parts) != 3: continue
        try: t, wmin, wmax = float(parts[0]), int(parts[1]), int(parts[2])
        except ValueError: continue
        det.feed(t, wmin, wmax)
    ivs = [iv for _, iv, _ in beats]
    print(f'回放 {os.path.basename(session_dir)}: 搏={len(beats)}')
    if ivs:
        print(f'  间隔中位={statistics.median(ivs):.0f}ms -> {60000/statistics.median(ivs):.0f}BPM')
        print(f'  离群(<{IV_MIN}或>{IV_MAX}外已滤), 间隔序列前20: {[int(x) for x in ivs[:20]]}')


if __name__ == '__main__':
    if len(sys.argv) > 2 and sys.argv[1] == '--replay':
        replay(sys.argv[2])
    else:
        live()
