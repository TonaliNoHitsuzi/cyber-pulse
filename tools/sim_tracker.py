# -*- coding: utf-8 -*-
"""算法孪生仿真：把固件里的跟踪器逻辑在 PC 上复刻，
用真实波形合成「加速区间」与「运动伪迹」来做离线回归。

用法:
  python sim_tracker.py            # 跑全部用例
  python sim_tracker.py <raw_r.log>  # 只回放某个真实会话
"""
import os, sys, glob, math, statistics

# ---------------- 固件参数（与 main.c 保持一致） ----------------
PEAK_THRESH   = 40
PEAK_MIN_GAP  = 0.200     # s
IV_MIN, IV_MAX = 300.0, 1400.0   # ms
PAIR_LO, PAIR_HI = 0.55, 1.80
KF_SIGMA_A = 2.0          # BPM/s^2
KF_SIGMA_T = 0.020        # s
KF_GATE = 4.0
V_MAX = 8.0
SLEW_MAX = 300
AMP_RATIO = 3.0
P95_WIN = 800             # 4s @200Hz
GATE_OK_P95, GATE_OK_P50 = 45.0, 18.0

# ---------------- 载入真实波形（200Hz 窗口序列） ----------------
def load_windows(path):
    """返回 [(seq, min, max)]，seq 以 200Hz 计"""
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
    """按固件同款基线(EMA tau4s + 跳变吸附)得到 dev 序列，并返回 span 序列"""
    baseline = 1860.0; snap = 0
    devs, spans = [], []
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
        spans.append(b - a)
    return devs, spans

# ---------------- 算法孪生 ----------------
class Tracker:
    def __init__(self):
        self.init = False; self.hr = 0.0; self.v = 0.0
        self.p00 = 0.0; self.p01 = 0.0; self.p11 = 0.0
        self.rejects = 0
        self.amps = []; self.art = 0
        self.last_beat = None; self.have_beat = False
        import collections
        self.dev_buf = collections.deque()
        self.last_peak = -1e9
        # 判定输出
        self.bpm_out = 0; self.state = 'IDLE'

    # --- 卡尔曼 ---
    def kf_init(self, hr):
        self.init = True; self.hr = hr; self.v = 0.0
        self.p00, self.p01, self.p11 = 400.0, 0.0, 4.0
        self.rejects = 0; self.amps = []; self.art = 0

    def kf_predict(self, dt):
        self.hr += self.v * dt
        p00 = self.p00 + dt * (2 * self.p01 + dt * self.p11)
        p01 = self.p01 + dt * self.p11
        p11 = self.p11
        sa2 = KF_SIGMA_A ** 2
        self.p00 = p00 + sa2 * dt**4 / 4.0
        self.p01 = p01 + sa2 * dt**3 / 2.0
        self.p11 = p11 + sa2 * dt**2

    def kf_update(self, z, r):
        s = max(self.p00 + r, 1e-6)
        k0, k1 = self.p00 / s, self.p01 / s
        innov = z - self.hr
        self.hr += k0 * innov; self.v += k1 * innov
        p00 = (1 - k0) * self.p00
        p01 = (1 - k0) * self.p01
        p11 = self.p11 - k1 * self.p01
        self.p00, self.p01, self.p11 = p00, p01, p11
        self.v = max(-V_MAX, min(V_MAX, self.v))
        self.hr = max(35.0, min(210.0, self.hr))

    def amp_med(self):
        if not self.amps:
            return 0.0
        s = sorted(self.amps)
        return s[len(s) // 2]

    def beat(self, t, amp, slew, clip, width):
        if clip:            self.art += 1; return
        if slew > SLEW_MAX: self.art += 1; return
        med = self.amp_med()
        if med > 1.0 and (amp > AMP_RATIO * med or amp * AMP_RATIO < med):
            self.art += 1; return
        if width <= 1 and med > 1.0 and amp > 1.5 * med:
            self.art += 1; return
        self.art = 0

        if not self.have_beat:
            self.have_beat = True; self.last_beat = t; self.amps.append(amp)
            if len(self.amps) > 5: self.amps.pop(0)
            return

        d = (t - self.last_beat) * 1000.0
        if not self.init:
            if IV_MIN <= d <= IV_MAX:
                self.kf_init(60000.0 / d); self.last_beat = t
                self.amps.append(amp)
            elif d > IV_MAX:
                self.last_beat = t
            return

        period = 60000.0 / self.hr
        if d < PAIR_LO * period:
            return                                  # 重搏波
        if d > PAIR_HI * period:
            self.last_beat = t; self.amps.append(amp)
            if len(self.amps) > 5: self.amps.pop(0)
            return                                  # 漏拍
        z = 60000.0 / d
        if z < 35 or z > 210:
            return
        dt = d / 1000.0
        self.kf_predict(dt)
        r = (self.hr * KF_SIGMA_T / 60.0) ** 2 + 1.0
        S = self.p00 + r
        if abs(z - self.hr) > KF_GATE * math.sqrt(S):
            self.rejects += 1
            if self.rejects >= 5:
                self.kf_init(z)
            self.last_beat = t
            return
        self.rejects = 0
        self.kf_update(z, r)
        self.last_beat = t
        self.amps.append(amp)
        if len(self.amps) > 5: self.amps.pop(0)

    # --- 自相关估周期（抗双峰/抗单峰，用于初始化与重锁） ---
    def estimate_period_ms(self):
        x = list(self.dev_buf)
        n = len(x)
        if n < 300:
            return 0.0
        m = sum(x) / n
        x = [v - m for v in x]
        vals = []
        for lag in range(60, 281):                 # 300~1400ms
            s = 0.0
            for i in range(n - lag):
                s += x[i] * x[i + lag]
            vals.append((lag, s / (n - lag)))
        mx = max(v for _, v in vals)
        if mx <= 0:
            return 0.0
        for lag, v in vals:                        # 取最小且≥90%峰值的 lag，避免谐波锁2P
            if v >= 0.90 * mx:
                return lag * 5.0
        return 0.0

    # --- 每 5ms 喂一个窗口 ---
    def feed(self, t, dev, span, clip_hint=False):
        self.p95_buf.append(dev)
        if len(self.p95_buf) > P95_WIN:
            self.p95_buf.pop(0)
        self.dev_buf.append(dev)
        if len(self.dev_buf) > 800:
            self.dev_buf.popleft()
        if not self.init and len(self.dev_buf) >= 400 and int(dev) % 7 == 0:
            P = self.estimate_period_ms()
            if P > 0:
                self.kf_init(60000.0 / P)
                self.last_beat = t
                self.have_beat = True
        # 峰值检测（3点极大）
        if self.d1 > PEAK_THRESH and self.d1 >= dev and self.d1 >= self.d2:
            if self.t1 - self.last_peak >= PEAK_MIN_GAP:
                self.last_peak = self.t1
                self.beat(self.t1, self.d1, self.prev_slew, self.prev_clip, self.run_prev)
        self.run_now = self.run_prev + 1 if dev > PEAK_THRESH else 0
        self.d2, self.d1 = self.d1, dev
        self.prev_slew = int(span)
        self.prev_clip = clip_hint
        self.run_prev = self.run_now
        self.t1 = t

    # 初始化时需要的字段
    p95_buf = None
    d1 = d2 = 0.0
    prev_slew = 0; prev_clip = False; run_prev = 0; run_now = 0
    t1 = 0.0

    def decide(self, t, p95, p50, q_ok):
        if self.have_beat and self.last_beat is not None and (t - self.last_beat) > 2.5:
            self.have_beat = False; self.init = False
        if not q_ok or not self.init or self.art >= 3:
            self.bpm_out = 0
        else:
            self.bpm_out = int(self.hr + 0.5)

def pct(buf, q):
    if len(buf) < 100:
        return 0.0
    s = sorted(buf)
    return s[min(len(s) - 1, int(len(s) * q))]

def run(devs, spans, throttle_fps=200, artifacts=None, name=''):
    """throttle_fps: 有效 200Hz 的窗口流；decide 每 100 窗口（0.5s）一次"""
    tr = Tracker(); tr.p95_buf = []
    out = []
    for i, (dev, span) in enumerate(zip(devs, spans)):
        t = i / throttle_fps
        tr.feed(t, dev, span)
        if i % 100 == 99:
            p95 = pct(tr.p95_buf, 0.95); p50 = pct(tr.p95_buf, 0.5)
            q_ok = (p95 >= GATE_OK_P95 and p50 >= GATE_OK_P50)
            tr.decide(t, p95, p50, q_ok)
            out.append((t, tr.bpm_out, tr.hr, tr.v, p95, p50, tr.art))
    return out

# ---------------- 合成激励 ----------------
def resample_to_hr(rows, hr_fn, dur_s, fs=200):
    """把真实波形按心率曲线做时间伸缩，生成新的窗口流"""
    devs, spans = to_dev(rows)
    # 取一段最有代表性的（能量最高的 4s）
    win = 800
    best, bi = -1, 0
    for i in range(0, len(devs) - win, win // 2):
        e = sum(devs[i:i + win])
        if e > best:
            best, bi = e, i
    src_d, src_s = devs[bi:bi + win], spans[bi:bi + win]
    out_d, out_s = [], []
    n = int(dur_s * fs)
    # 以 src 的局部相位为索引，按心率比例推进
    phase = 0.0
    idx = 0
    for k in range(n):
        t = k / fs
        hr = hr_fn(t)
        # 每个窗口前进 5ms 对应的源时间
        step = (hr / 80.0)           # 心率越高，波形压缩越快
        phase += step
        i0 = int(phase) % len(src_d)
        out_d.append(src_d[i0]); out_s.append(src_s[i0])
    return out_d, out_s

def add_artifacts(devs, spans, stride_hz=2.8, amp=900, swing_hz=1.2, swing_amp=350, fs=200):
    d2, s2 = list(devs), list(spans)
    n = len(d2)
    for k in range(n):
        t = k / fs
        # 步频冲击：每周期一个尖峰
        if (t * stride_hz) % 1.0 < 1.0 / (fs / stride_hz) / 1.0 and (k % max(1, int(fs / stride_hz))) == 0:
            d2[k] += amp
            s2[k] = max(s2[k], amp * 2)
        # 臂摆低频大幅
        d2[k] += swing_amp * (0.5 + 0.5 * math.sin(2 * math.pi * swing_hz * t))
    return d2, s2

# ---------------- 用例 ----------------
def case_rest(path):
    rows = load_windows(path)
    devs, spans = to_dev(rows)
    out = run(devs, spans)
    return out

def case_ramp(path, t_up=20.0, t_hold=15.0, hr0=80, hr1=155):
    rows = load_windows(path)
    def hr_fn(t):
        if t < t_up:
            return hr0 + (hr1 - hr0) * (t / t_up)
        if t < t_up + t_hold:
            return hr1
        return hr1 - (hr1 - hr0) * min(1.0, (t - t_up - t_hold) / 15.0)
    dur = t_up + t_hold + 15.0
    devs, spans = resample_to_hr(rows, hr_fn, dur)
    return run(devs, spans), hr_fn

def case_artifact(path):
    rows = load_windows(path)
    devs, spans = to_dev(rows)
    d2, s2 = add_artifacts(devs, spans)
    return run(d2, s2)

if __name__ == '__main__':
    root = os.path.dirname(os.path.abspath(__file__))
    good = os.path.join(root, 'logs', 'session_20261030_224518', 'raw_r.log')
    if not os.path.exists(good):
        cands = sorted(glob.glob(os.path.join(root, 'logs', '*', 'raw_r.log')))
        good = cands[0] if cands else None
    print('基准波形:', good)

    print('\n=== A. 静息回归（真实按压波形）===')
    out = case_rest(good)
    bpms = [o[1] for o in out if o[1] > 0]
    if bpms:
        print(f'  输出帧 {len(bpms)}/{len(out)}  BPM 中位={statistics.median(bpms):.0f} '
              f'范围={min(bpms)}~{max(bpms)} σ={statistics.pstdev(bpms):.1f}')
    else:
        print('  无输出（异常）')

    print('\n=== B. 加速段仿真（80→155→80 BPM）===')
    out, hr_fn = case_ramp(good)
    err = []
    for (t, bpm, hr, v, p95, p50, art) in out:
        if bpm > 0:
            err.append(abs(bpm - hr_fn(t)))
    if err:
        print(f'  跟踪误差: 中位={statistics.median(err):.1f} 最大={max(err):.1f} BPM')
        print('  时间线 (每2s):')
        for (t, bpm, hr, v, p95, p50, art) in out[::4]:
            print(f'    t={t:5.1f}s 真值={hr_fn(t):5.1f} 输出={bpm:3d} 估计={hr:5.1f} v={v:+5.2f}')
    else:
        print('  无输出（异常）')

    print('\n=== C. 运动伪迹仿真（步频2.8Hz震幅900 + 臂摆1.2Hz）===')
    out = case_artifact(good)
    bpms = [o[1] for o in out if o[1] > 0]
    arts = [o[6] for o in out]
    print(f'  输出帧 {len(bpms)}/{len(out)}  伪迹计数峰值={max(arts)}')
    if bpms:
        print(f'  BPM 中位={statistics.median(bpms):.0f} 范围={min(bpms)}~{max(bpms)}')
        print('  判定:', '✅ 仍在真值附近' if abs(statistics.median(bpms) - 83) < 12 else '❌ 被伪迹带偏')
    else:
        print('  ✅ 全程拒绝输出（诚实报告测不了）')

# ================= 相位锁定跟踪器（v2 结构） =================
class PhaseTracker:
    """每周期只在预测相位窗口内取一个峰，杜绝双峰/纹波重复计数。"""
    def __init__(self):
        self.hr = None; self.v = 0.0
        self.p00 = 0.0; self.p01 = 0.0; self.p11 = 0.0
        self.last_beat = None
        self.rejects = 0
        self.amps = []
        self.art = 0
        self.pending_window = None   # (start_t, end_t, best_t, best_dev)
        self.bpm_out = 0
        self.boot = []               # 启动期收集的峰时刻

    # --- 初始化 ---
    def init_period(self, P_ms, t):
        self.hr = 60000.0 / P_ms
        self.v = 0.0
        self.p00, self.p01, self.p11 = 400.0, 0.0, 4.0
        self.last_beat = t
        self.rejects = 0

    def predict_dt(self, dt):
        self.hr += self.v * dt
        p00 = self.p00 + dt * (2 * self.p01 + dt * self.p11)
        p01 = self.p01 + dt * self.p11
        p11 = self.p11
        sa2 = KF_SIGMA_A ** 2
        self.p00 = p00 + sa2 * dt**4 / 4.0
        self.p01 = p01 + sa2 * dt**3 / 2.0
        self.p11 = p11 + sa2 * dt**2

    def update(self, z, r):
        s = max(self.p00 + r, 1e-6)
        k0, k1 = self.p00 / s, self.p01 / s
        innov = z - self.hr
        self.hr += k0 * innov; self.v += k1 * innov
        p00 = (1 - k0) * self.p00
        p01 = (1 - k0) * self.p01
        p11 = self.p11 - k1 * self.p01
        self.p00, self.p01, self.p11 = p00, p01, p11
        self.v = max(-V_MAX, min(V_MAX, self.v))
        self.hr = max(35.0, min(210.0, self.hr))

    def feed(self, t, dev, span=0):
        # 未锁定：收集峰，够 3 个后用 i+2 中值初始化
        if self.hr is None:
            if dev > PEAK_THRESH:
                if not self.boot or (t - self.boot[-1]) >= PEAK_MIN_GAP:
                    self.boot.append(t)
            if len(self.boot) >= 4:
                iv2 = [self.boot[i + 2] - self.boot[i] for i in range(len(self.boot) - 2)]
                iv2 = [x for x in iv2 if IV_MIN/1000 <= x <= IV_MAX/1000]
                if iv2:
                    self.init_period(sorted(iv2)[len(iv2)//2] * 1000.0, t)
            return

        P = 60.0 / self.hr          # 周期（秒）
        # 相位窗口：[last+0.55P, last+1.35P]
        if self.pending_window is None:
            self.pending_window = [self.last_beat + 0.55 * P, self.last_beat + 1.35 * P, None, 0.0]
        w = self.pending_window
        w[1] = self.last_beat + 1.35 * P          # 目标随估计更新
        if w[0] <= t <= w[1]:
            if dev > w[3]:
                w[3] = dev; w[2] = t
        if t >= w[1]:
            # 窗口结束，判定
            if w[2] is not None and w[3] > PEAK_THRESH:
                d = (w[2] - self.last_beat) * 1000.0
                z = 60000.0 / d
                self.predict_dt(d / 1000.0)
                r = (self.hr * KF_SIGMA_T / 60.0) ** 2 + 1.0
                S = self.p00 + r
                if abs(z - self.hr) <= KF_GATE * math.sqrt(S):
                    self.update(z, r); self.rejects = 0
                else:
                    self.rejects += 1
                    if self.rejects >= 5:
                        self.init_period(d, t)
                self.last_beat = w[2]
            else:
                self.rejects += 1
                if self.rejects >= 5:            # 丢锁 → 重来
                    self.hr = None; self.boot = []
            self.pending_window = None
        self.t_last = t

    def decide(self, q_ok):
        self.bpm_out = int(self.hr + 0.5) if (q_ok and self.hr is not None) else 0
        return self.bpm_out

# ================= 合成信号 =================
def synth_dev(hr_fn, dur_s, fs=200, noise=3.0, jitter=0.01, ripple_hz=0.0, ripple_amp=0.0,
              amp_scale=1.0, seed=1):
    """按真实脉搏形态合成 dev 序列：主峰 + 重搏波 + 可选纹波"""
    import random
    random.seed(seed)
    n = int(dur_s * fs)
    out = []
    t = 0.0
    next_beat = 0.35
    beat_times = []
    while next_beat < dur_s:
        beat_times.append(next_beat)
        hr = hr_fn(next_beat)
        P = 60.0 / hr
        next_beat += P * (1 + random.uniform(-jitter, jitter))
    dev = [0.0] * n
    for bt in beat_times:
        P = 60.0 / hr_fn(bt)
        a = 100.0 * amp_scale
        # 主峰（高斯）
        for k in range(int(-0.25 * P * fs), int(0.25 * P * fs)):
            i = int(bt * fs) + k
            if 0 <= i < n:
                x = k / fs
                dev[i] += a * math.exp(-(x ** 2) / (2 * (0.035 ** 2)))
        # 重搏波
        for k in range(int(-0.2 * P * fs), int(0.3 * P * fs)):
            i = int((bt + 0.42 * P) * fs) + k
            if 0 <= i < n:
                x = k / fs
                dev[i] += 0.45 * a * math.exp(-(x ** 2) / (2 * (0.05 ** 2)))
    for i in range(n):
        v = dev[i] + random.gauss(0, noise)
        if ripple_hz > 0:
            v += ripple_amp * max(0.0, math.sin(2 * math.pi * ripple_hz * (i / fs)))
        out.append(max(0.0, v))
    return out

def run_phase(devs, fs=200, q_ok_fn=None):
    tr = PhaseTracker()
    out = []
    for i, d in enumerate(devs):
        t = i / fs
        tr.feed(t, d)
        if i % 100 == 99:
            q = True if q_ok_fn is None else q_ok_fn(i)
            out.append((t, tr.decide(q), tr.hr))
    return out
