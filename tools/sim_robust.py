# -*- coding: utf-8 -*-
"""稳健性蒙特卡洛：用真实录音拼接出极端场景，重复随机采样量化指标。

场景 = 静息段（真实） + 加速段（真实波形时间伸缩） + 运动伪迹（步频冲击+臂摆）
       + 掉线（传感器抬起） + 重锁定
指标 = 稳态误差 / 加速段误差 / 首次锁定时间 / 空白期误报率 / 掉线恢复时间
"""
import os, glob, math, random, statistics, sys
import sim_tracker as S

FS = 200

# ---------------- 参数（与固件 v2 同步） ----------------
PEAK_MIN_GAP = 0.20
PAIR_LO, PAIR_HI = 0.55, 1.35
IV_MIN_S, IV_MAX_S = 0.30, 1.40
KF_SIGMA_T = 0.020
KF_GATE = 4.0
GATE_OK_P95, GATE_OK_P50 = 45.0, 18.0

def pct(buf, q):
    if not buf:
        return 0.0
    s = sorted(buf)
    return s[min(len(s) - 1, int(len(s) * q))]

# ---------------- 素材 ----------------
BAD_WORDS = ('悬空', '空白', '对照', '裸引脚', '伪迹', '待机', '崩溃')

def autocorr_hr(seg, lo=45.0, hi=120.0, fs=FS):
    """用自相关估源段落的心率，返回 (hr, 置信度)"""
    n = len(seg)
    if n < 600:
        return 0.0, 0.0
    m = sum(seg) / n
    x = [v - m for v in seg]
    vals = []
    for lag in range(int(fs * 60 / hi), int(fs * 60 / lo) + 1):
        acc = sum(x[i] * x[i + lag] for i in range(n - lag)) / (n - lag)
        vals.append((lag, acc))
    vals.sort(key=lambda z: -z[1])
    best_lag, best_v = vals[0]
    # 置信度：主峰 / 全程均值（越大越像周期信号）
    mean_abs = sum(abs(v) for _, v in vals) / len(vals) + 1e-9
    conf = best_v / mean_abs
    return 60000.0 / (best_lag * 1000.0 / fs), conf

def load_pool():
    """素材：真实搏动段（10s），带源心率估计"""
    pool = []
    for f in sorted(glob.glob(os.path.join(os.path.dirname(__file__), 'logs', '*', 'raw_r.log'))):
        d = os.path.dirname(f)
        note = ''
        nf = os.path.join(d, 'NOTE.txt')
        if os.path.exists(nf):
            note = open(nf, encoding='utf-8', errors='ignore').read()
        if any(w in note for w in BAD_WORDS):
            continue
        try:
            rows = S.load_windows(f)
            if len(rows) < 2400:
                continue
            devs, spans = S.to_dev(rows)
            win = 2000                                  # 10s
            best, bi = -1, 0
            for i in range(0, len(devs) - win, 500):
                e = sum(devs[i:i + win])
                if e > best:
                    best, bi = e, i
            seg, spg = devs[bi:bi + win], spans[bi:bi + win]
            hr, conf = autocorr_hr(seg)
            if conf < 1.6 or not (45 <= hr <= 120):
                continue
            if extract_beat(seg, hr) is None:      # 单主峰校验
                continue
            pool.append((os.path.basename(d), seg, spg, hr, conf))
        except Exception:
            pass
    return pool


def extract_beat(seg, hr, fs=FS):
    """从真实段落里切一个完整心搏波形（按估出的心率切），归一化到单位周期"""
    P = int(fs * 60.0 / hr)
    if P < 30 or P >= len(seg):
        return None
    # 找能量最高的完整周期
    best, bi = -1, 0
    for i in range(0, len(seg) - P, max(1, P // 4)):
        e = sum(seg[i:i + P])
        if e > best:
            best, bi = e, i
    beat = seg[bi:bi + P]
    mx = max(beat) or 1.0
    nb = [v / mx for v in beat]
    # 模板必须"单主峰"：若有第二个显著峰（>0.55），说明切到了两个心搏，丢弃
    peaks = [i for i in range(1, len(nb) - 1) if nb[i] > 0.55 and nb[i] >= nb[i-1] and nb[i] >= nb[i+1]]
    if len(peaks) > 1:
        # 允许两个峰但间距必须很小（重搏波 < 0.25 周期）
        if (peaks[-1] - peaks[0]) > 0.5 * len(nb):
            return None
    return nb

def build_from_beat(beat, hr_fn, dur_s, fs=FS, amp=150.0, noise=4.0, floor=0.0,
                    ripple_hz=0.0, ripple_amp=0.0, rng=None):
    """按心率曲线把真实心搏波形重排成时间序列（真值精确）"""
    rng = rng or random.Random(0)
    n = int(dur_s * fs)
    out = [floor] * n
    t = 0.0
    while t < dur_s:
        hr = hr_fn(t)
        P = 60.0 / hr
        i0 = int(t * fs)
        m = max(1, int(P * fs))
        a = amp * rng.uniform(0.85, 1.15)
        for k in range(m):
            i = i0 + k
            if i >= n:
                break
            src = beat[int(k * len(beat) / m)]
            out[i] += a * src
        t += P
    res = []
    for i in range(n):
        v = out[i] + rng.gauss(0, noise)
        if ripple_hz > 0:
            v += ripple_amp * max(0.0, math.sin(2 * math.pi * ripple_hz * (i / fs)))
        res.append(max(0.0, v))
    return res

# ---------------- 场景合成 ----------------
def stretch(devs, factor_fn, out_len):
    """时间伸缩：factor_fn(t)->每秒源数据推进倍率"""
    out = []
    pos = 0.0
    for k in range(out_len):
        i = int(pos) % len(devs)
        out.append(devs[i])
        pos += factor_fn(k / FS)
        if pos >= len(devs) * 4:          # 循环使用
            pos -= len(devs)
    return out

def add_artifacts(devs, spans, stride_hz, stride_amp, swing_hz, swing_amp, phase=0.0):
    d2, s2 = list(devs), list(spans)
    period = int(FS / stride_hz)
    for k in range(len(d2)):
        t = k / FS
        if period > 0 and (k + int(phase * period)) % period == 0:
            d2[k] += stride_amp
            s2[k] = max(s2[k], stride_amp * 2)
        d2[k] += swing_amp * (0.5 + 0.5 * math.sin(2 * math.pi * swing_hz * t))
    return d2, s2

def add_noise_floor(devs, floor):
    return [v + floor for v in devs]

# ---------------- 跟踪器（固件 v2 镜像） ----------------
class V2:
    def __init__(self, sigma_a=2.0, v_max=8.0, extend=True, gate=4.0, coast=1.0, k_p95=0.0, sigma_win=True, hrv=0.05, gate_abs=45.0, fading=True, chi2=16.0, nis_hi=4.0):
        self.coast = coast
        self.k_p95 = k_p95
        self.sigma_win = sigma_win
        self.hrv = hrv
        self.gate_abs = gate_abs
        self.fading = fading
        self.chi2 = chi2
        self.nis_hi = nis_hi
        self.nis_ema = 1.0
        self.p95 = 0.0
        self.extend = extend
        self.gate = gate
        self.sigma_a, self.v_max = sigma_a, v_max
        self.hr = None; self.v = 0.0
        self.p00 = self.p01 = self.p11 = 0.0
        self.last_beat = None
        self.rejects = 0
        self.boot = []
        self.win = None
        self.buf = []
        self.thr = 30.0
        self.q_cnt = 2; self.q_ok = True
        self.bpm_out = 0
        self.track_start = None

    def predict(self, dt):
        # 衰减记忆：新息持续偏大 → 放大 P（等价提高 Q），让滤波器"敢跟"
        if self.fading:
            lam = 1.0
            if self.nis_ema > self.nis_hi:
                lam = 1.0 + min(0.5, 0.08 * (self.nis_ema - self.nis_hi))
            self.p00 *= lam; self.p01 *= lam; self.p11 *= lam
        self.hr += self.v * dt
        p00 = self.p00 + dt * (2 * self.p01 + dt * self.p11)
        p01 = self.p01 + dt * self.p11
        p11 = self.p11
        sa2 = self.sigma_a ** 2
        self.p00 = p00 + sa2 * dt**4 / 4
        self.p01 = p01 + sa2 * dt**3 / 2
        self.p11 = p11 + sa2 * dt**2

    def update(self, z, r):
        s = max(self.p00 + r, 1e-6)
        k0, k1 = self.p00 / s, self.p01 / s
        innov = z - self.hr
        self.hr += k0 * innov; self.v += k1 * innov
        p00 = (1 - k0) * self.p00; p01 = (1 - k0) * self.p01
        p11 = self.p11 - k1 * self.p01
        self.p00, self.p01, self.p11 = p00, p01, p11
        self.v = max(-self.v_max, min(self.v_max, self.v))
        self.hr = max(35.0, min(210.0, self.hr))

    def ac_period(self, lo=40.0, hi=200.0):
        x = self.buf
        n = len(x)
        if n < 600:
            return 0.0
        m = sum(x) / n
        y = [v - m for v in x]
        vals = []
        for lag in range(int(FS * 60 / hi), int(FS * 60 / lo) + 1):
            if lag >= n - 5:
                break
            acc = sum(y[i] * y[i + lag] for i in range(n - lag)) / (n - lag)
            vals.append((lag, acc))
        if not vals:
            return 0.0
        best_lag, best_v = max(vals, key=lambda z: z[1])
        mean_abs = sum(abs(v) for _, v in vals) / len(vals) + 1e-9
        if best_v / mean_abs < 1.6:          # 周期性不足，不启动
            return 0.0
        return best_lag * 1000.0 / FS

    def feed(self, t, dev):
        self.buf.append(dev)
        if len(self.buf) > 800:
            self.buf.pop(0)
        if len(self.buf) >= 200 and int(t * FS) % 100 == 0:
            p50 = pct(self.buf, 0.5); p95 = pct(self.buf, 0.95)
            self.thr = max(20.0, 1.2 * p50)   # 低门限：拍只做'有没有'判定，真伪交给新息门
            self.p95 = p95
            ok = (p95 >= GATE_OK_P95 and p50 >= GATE_OK_P50)
            self.q_cnt = min(4, self.q_cnt + 1) if ok else max(0, self.q_cnt - 1)
            self.q_ok = self.q_cnt >= 2
        thr = self.thr
        if self.hr is None:
            p95b = pct(self.buf, 0.95) if len(self.buf) >= 200 else 0
            need = max(thr, 0.6 * p95b)
            if dev > need and (not self.boot or (t - self.boot[-1]) >= 0.25):
                self.boot.append(t)
            if len(self.boot) >= 5:
                # 启动：主峰（>=0.6*p95）+ 相邻间隔中值（生理区间 0.3~1.4s）
                p95 = pct(self.buf, 0.95) if len(self.buf) >= 200 else 0
                strong = [bt for bt in self.boot if bt]      # boot 已按 thr 收集
                if p95 > 0:
                    # 用间隔中值估计（boot 里已过滤过低峰）
                    ivs = [strong[i + 1] - strong[i] for i in range(len(strong) - 1)]
                    ivs = [x for x in ivs if IV_MIN_S <= x <= IV_MAX_S]
                    if len(ivs) >= 3:
                        self.hr = 60000.0 / (sorted(ivs)[len(ivs) // 2] * 1000.0)
                        self.v = 0.0; self.p00, self.p01, self.p11 = 400.0, 0.0, 4.0
                        self.last_beat = t; self.rejects = 0; self.win = None
                        if self.track_start is None:
                            self.track_start = t
            return
        P = 60.0 / self.hr
        if self.win is None:
            if self.sigma_win:
                # 预测下一拍时刻的 3σ 不确定度（含速度项 p01/p11）+ HRV 生理下限
                var_hr = max(1.0, self.p00 + 2 * P * self.p01 + P * P * self.p11)
                sd_hr = math.sqrt(var_hr)
                sd_P = math.sqrt((P * sd_hr / self.hr) ** 2 + (self.hrv * P) ** 2 + 0.02 ** 2)
                lo = max(0.30 * P, P - 3 * sd_P)
                hi = min(1.95 * P, P + 3 * sd_P)
            else:
                lo, hi = PAIR_LO * P, PAIR_HI * P
            self.win = [self.last_beat + lo, self.last_beat + hi, None, 0.0]
        w = self.win
        if not self.extend:
            w[1] = self.last_beat + PAIR_HI * P
        if w[0] <= t <= w[1] and dev > w[3]:
            w[3] = dev; w[2] = t
        # 落空 → 逐步延长窗口（心率变慢时真实拍会更晚出现）
        if t >= w[1] and w[3] <= max(thr, self.k_p95 * self.p95) and self.extend and w[1] < self.last_beat + 1.95 * P:
            w[1] += 0.25 * P
            return
        if t >= w[1]:
            need = max(thr, self.k_p95 * self.p95)
            if w[2] is not None and w[3] > need:
                dms = (w[2] - self.last_beat) * 1000.0
                z = 60000.0 / dms
                self.predict(dms / 1000.0)
                r = (self.hr * KF_SIGMA_T / 60.0) ** 2 + 1.0
                Sc = self.p00 + r
                nis = (z - self.hr) ** 2 / max(Sc, 1e-6)
                self.nis_ema = 0.7 * self.nis_ema + 0.3 * min(nis, 100.0)
                if abs(z - self.hr) <= self.gate_abs and nis <= self.chi2:
                    self.update(z, r); self.rejects = 0
                else:
                    self.rejects += 1
                    if self.rejects >= 5:
                        self.hr = z; self.v = 0.0
                        self.p00, self.p01, self.p11 = 400.0, 0.0, 4.0
                        self.rejects = 0
                self.last_beat = w[2]
            else:
                self.rejects += 1
                if self.rejects >= 3:
                    self.hr = None; self.boot = []
                elif self.coast:
                    # 落空 → 判定为心率变慢（周期变长），逐步下修估计
                    self.hr = max(35.0, self.hr * self.coast)
            self.win = None

    def out(self):
        return int(self.hr + 0.5) if (self.hr and self.q_ok) else 0

# ---------------- 场景 ----------------
def make_scenario(pool, rng):
    """静息20s → 加速(80→160,15s) → 保持(160,10s) → 伪迹(10s) → 掉线(2s) → 恢复(15s)"""
    name, devs, spans, src_hr, _conf = pool[rng.randrange(len(pool))]
    beat = extract_beat(devs, src_hr)
    if beat is None:
        return None
    gain = rng.uniform(0.8, 1.6)           # 幅度变化
    floor = rng.uniform(0, 25)             # 噪声底变化
    seg = [v * gain + floor for v in devs]

    dur_rest, dur_up, dur_hold, dur_art, dur_drop, dur_rec = 20, 15, 10, 10, 2, 15
    # 静息：80 BPM 播放（源素材约 1 拍/0.77s）
    amp = rng.uniform(120, 300)
    nz  = rng.uniform(2, 10)
    fl  = rng.uniform(0, 30)
    rip = rng.uniform(30, 90)
    rest = build_from_beat(beat, lambda t: 80.0, dur_rest, amp=amp, noise=nz, floor=fl, ripple_hz=5.0, ripple_amp=rip, rng=rng)
    up   = build_from_beat(beat, lambda t: 80.0 + 80.0 * (t / dur_up), dur_up, amp=amp, noise=nz, floor=fl, ripple_hz=5.0, ripple_amp=rip, rng=rng)
    hold = build_from_beat(beat, lambda t: 160.0, dur_hold, amp=amp, noise=nz, floor=fl, ripple_hz=5.0, ripple_amp=rip, rng=rng)
    art_base = build_from_beat(beat, lambda t: 160.0, dur_art, amp=amp, noise=nz, floor=fl, ripple_hz=5.0, ripple_amp=rip, rng=rng)
    art, art_span = add_artifacts(art_base, [0] * len(art_base),
                                  stride_hz=rng.uniform(2.4, 3.2),
                                  stride_amp=rng.uniform(300, 1200),
                                  swing_hz=rng.uniform(0.8, 1.6),
                                  swing_amp=rng.uniform(50, 300),
                                  phase=rng.random())
    # 掉线 → 恢复
    drop = [0.0] * (dur_drop * FS)
    rec = build_from_beat(beat, lambda t: 160.0, dur_rec, amp=amp, noise=nz, floor=fl, ripple_hz=5.0, ripple_amp=rip, rng=rng)

    dev = rest + up + hold + art + drop + rec
    # 时间轴
    t_rest = [i / FS for i in range(len(rest))]
    t_up = [(dur_rest * FS + i) / FS for i in range(len(up))]
    t_hold = [((dur_rest + dur_up) * FS + i) / FS for i in range(len(hold))]
    t_art = [((dur_rest + dur_up + dur_hold) * FS + i) / FS for i in range(len(art))]
    t_drop = [((dur_rest + dur_up + dur_hold + dur_art) * FS + i) / FS for i in range(len(drop))]
    t_rec = [((dur_rest + dur_up + dur_hold + dur_art + dur_drop) * FS + i) / FS for i in range(len(rec))]
    times = t_rest + t_up + t_hold + t_art + t_drop + t_rec

    def truth(t):
        if t < dur_rest: return 80.0
        if t < dur_rest + dur_up: return 80.0 + 80.0 * (t - dur_rest) / dur_up
        if t < dur_rest + dur_up + dur_hold: return 160.0
        if t < dur_rest + dur_up + dur_hold + dur_art: return 160.0
        if t < dur_rest + dur_up + dur_hold + dur_art + dur_drop: return 0.0
        return 160.0
    return dev, times, truth, dict(rest=dur_rest, up=dur_up, hold=dur_hold,
                                   art=dur_art, drop=dur_drop, rec=dur_rec, name=name)

def run_once(pool, rng, sigma_a=2.0, v_max=8.0):
    sc = make_scenario(pool, rng)
    if sc is None:
        return None
    dev, times, truth, seg = sc
    tr = V2(sigma_a, v_max)
    rows = []
    for i, d in enumerate(dev):
        t = times[i]
        tr.feed(t, d)
        if i % 100 == 99:
            rows.append((t, tr.out()))
    T = seg['rest'] + seg['up'] + seg['hold'] + seg['art']
    # 指标
    lock_t = None
    for (t, b) in rows:
        if b > 0:
            lock_t = t
            break
    steady = [abs(b - truth(t)) for (t, b) in rows
              if b > 0 and (seg['rest'] * 0.6) <= t < seg['rest']]
    ramp = [abs(b - truth(t)) for (t, b) in rows
            if b > 0 and seg['rest'] <= t < seg['rest'] + seg['up']]
    hold = [abs(b - truth(t)) for (t, b) in rows
            if b > 0 and seg['rest'] + seg['up'] <= t < seg['rest'] + seg['up'] + seg['hold']]
    art_out = [b for (t, b) in rows if seg['rest'] + seg['up'] + seg['hold'] <= t < T]
    drop_out = [b for (t, b) in rows if T <= t < T + seg['drop']]
    # 恢复时间：掉线结束后首个有效输出
    relock = None
    for (t, b) in rows:
        if b > 0 and t >= T + seg['drop']:
            relock = t - (T + seg['drop']); break
    return dict(
        lock=lock_t,
        steady_med=statistics.median(steady) if steady else 999,
        steady_p90=pct(steady, 0.9) if steady else 999,
        ramp_med=statistics.median(ramp) if ramp else 999,
        ramp_p90=pct(ramp, 0.9) if ramp else 999,
        hold_med=statistics.median(hold) if hold else 999,
        art_false=sum(1 for b in art_out if b > 0) / max(1, len(art_out)),
        art_err=statistics.median([abs(b - 160) for b in art_out if b > 0]) if any(b > 0 for b in art_out) else 999,
        drop_false=sum(1 for b in drop_out if b > 0) / max(1, len(drop_out)),
        relock=relock if relock is not None else 999,
    )

def summarize(rs):
    keys = ['lock', 'steady_med', 'steady_p90', 'ramp_med', 'ramp_p90', 'hold_med',
            'art_false', 'art_err', 'drop_false', 'relock']
    print(f'{"指标":10s} {"中位":>8s} {"p90":>8s} {"最差":>8s}')
    for k in keys:
        vals = [r[k] for r in rs]
        print(f'{k:12s} {statistics.median(vals):8.2f} {pct(vals,0.9):8.2f} {max(vals):8.2f}')

if __name__ == '__main__':
    pool = load_pool()
    print(f'素材池: {len(pool)} 段')
    for name, *_ in pool:
        print('   -', name)
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    rng = random.Random(42)
    rs = []
    for i in range(N):
        r = run_once(pool, rng)
        if r:
            rs.append(r)
    print(f'\n=== 蒙特卡洛 N={N} ===')
    summarize(rs)

    print('\n=== 参数对比 (sigma_a × v_max) ===')
    for sa in (1.0, 2.0, 4.0):
        for vm in (6.0, 8.0, 12.0):
            rng2 = random.Random(42)
            rr = [x for x in (run_once(pool, rng2, sa, vm) for _ in range(max(10, N // 2))) if x]
            print(f'  sa={sa:4.1f} vmax={vm:4.1f} | '
                  f'稳态p90={statistics.median([x["steady_p90"] for x in rr]):5.1f} '
                  f'加速p90={statistics.median([x["ramp_p90"] for x in rr]):5.1f} '
                  f'保持p90={statistics.median([x["hold_med"] for x in rr]):5.1f} '
                  f'伪迹误报={statistics.median([x["art_false"] for x in rr]):.2f} '
                  f'掉线误报={statistics.median([x["drop_false"] for x in rr]):.2f} '
                  f'重锁={statistics.median([x["relock"] for x in rr]):5.1f}s')
