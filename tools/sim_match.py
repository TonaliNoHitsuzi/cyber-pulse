# -*- coding: utf-8 -*-
"""模板匹配测心率（matched filter）—— 与峰值法对比。

原理：
  1. 模板 T = 一个心搏周期的归一化波形（零均值、单位能量）
  2. 相关分 score(t) = 归一化互相关（NCC），在期望相位附近搜索
  3. 拍 = score 的局部极大且 > 阈值（形态不像心搏的一律不进）
  4. 模板在线更新：只用高分的段（防止伪迹污染模板）
  5. 间隔 → 卡尔曼（与前面同款 CV 模型）

为什么不靠"峰值幅度"：
  重搏波/纹波/撞击都有峰，但只有真正的心搏在一个完整周期上与模板相似。
"""
import math, random, statistics
import sim_tracker as S
import sim_robust as R

FS = 200

# ---------- 参数化心搏模板（可被在线数据修正） ----------
def parametric_template(n=200):
    """0~1 一个周期：收缩期主峰 + 重搏波 + 舒张衰减"""
    t = [i / n for i in range(n)]
    out = []
    for x in t:
        a = math.exp(-((x - 0.14) ** 2) / (2 * 0.055 ** 2))            # 收缩期
        b = 0.42 * math.exp(-((x - 0.42) ** 2) / (2 * 0.075 ** 2))     # 重搏波
        c = 0.10 * math.exp(-max(0.0, x - 0.45) / 0.22)                # 舒张拖尾
        out.append(a + b + c)
    return norm(out)

def norm(v):
    m = sum(v) / len(v)
    v = [x - m for x in v]
    e = math.sqrt(sum(x * x for x in v)) + 1e-9
    return [x / e for x in v]

def resample(v, m):
    n = len(v)
    return [v[min(n - 1, int(i * n / m))] for i in range(m)]

class Matcher:
    """周期搜索式模板匹配：在预测心率附近枚举周期，取 NCC 最高者作为测量值。"""
    def __init__(self, thr=0.50, adapt=True, gate_abs=35.0, sa=3.0, vmax=10.0, span=0.45):
        self.thr, self.adapt, self.gate_abs = thr, adapt, gate_abs
        self.sa, self.vmax, self.span = sa, vmax, span
        self.hr = None
        self.v = 0.0
        self.p00 = self.p01 = self.p11 = 0.0
        self.rejects = 0
        self.buf = []
        self.last_score = 0.0
        self.template_src = parametric_template()

    def score_at(self, hr):
        P = 60.0 / hr
        m = int(P * FS)
        if m < 40 or len(self.buf) < m + 4:
            return -2.0
        seg = norm(self.buf[-m:])
        tmpl = norm(resample(self.template_src, m))
        return sum(x * y for x, y in zip(seg, tmpl))

    def search(self, center, ratio=0.45, n=19):
        lo, hi = center * (1 - ratio), center * (1 + ratio)
        best_hr, best_sc = center, -2.0
        for k in range(n):
            hr = lo + (hi - lo) * k / (n - 1)
            hr = max(35.0, min(210.0, hr))
            sc = self.score_at(hr)
            if sc > best_sc:
                best_sc, best_hr = sc, hr
        return best_hr, best_sc

    def feed(self, t, dev):
        self.buf.append(dev)
        if len(self.buf) > 4000:
            self.buf.pop(0)
        # 每 0.5s 做一次估计
        if int(t * FS) % 100 != 0 or len(self.buf) < 600:
            return
        if self.hr is None:
            best_hr, best_sc = 80.0, -2.0
            for hr in range(40, 201, 4):
                sc = self.score_at(hr)
                if sc > best_sc:
                    best_sc, best_hr = sc, hr
            if best_sc > self.thr:
                self.hr = best_hr
                self.p00, self.p01, self.p11 = 400.0, 0.0, 4.0
                self.last_score = best_sc
            return
        hr_obs, sc = self.search(self.hr, self.span)
        self.last_score = sc
        if sc < self.thr:
            # 形态不像心搏：不测，只外推
            self.kf_predict(0.5)
            self.rejects += 1
            if self.rejects >= 6:
                self.hr = None; self.buf = []
            return
        self.rejects = 0
        z = hr_obs
        self.kf_predict(0.5)
        r = (self.hr * 0.02 / 60.0) ** 2 + 4.0
        Sc = self.p00 + r
        nis = (z - self.hr) ** 2 / max(Sc, 1e-6)
        if abs(z - self.hr) <= self.gate_abs and nis <= 16:
            self.kf_update(z, r)
            if self.adapt and sc > 0.8:
                self.update_template()
        else:
            self.rejects += 1

    def kf_predict(self, dt):
        self.hr += self.v * dt
        p00 = self.p00 + dt * (2 * self.p01 + dt * self.p11)
        p01 = self.p01 + dt * self.p11
        sa2 = self.sa ** 2
        self.p00 = p00 + sa2 * dt ** 4 / 4
        self.p01 = p01 + sa2 * dt ** 3 / 2
        self.p11 = self.p11 + sa2 * dt ** 2

    def kf_update(self, z, r):
        s = max(self.p00 + r, 1e-6)
        k0, k1 = self.p00 / s, self.p01 / s
        inn = z - self.hr
        self.hr += k0 * inn; self.v += k1 * inn
        p00 = (1 - k0) * self.p00; p01 = (1 - k0) * self.p01
        self.p11 = self.p11 - k1 * self.p01
        self.p00, self.p01 = p00, p01
        self.v = max(-self.vmax, min(self.vmax, self.v))
        self.hr = max(35.0, min(210.0, self.hr))

    def update_template(self):
        m = int(60.0 / self.hr * FS)
        if len(self.buf) < m:
            return
        seg = norm(self.buf[-m:])
        self.template_src = [0.9 * a + 0.1 * b for a, b in zip(resample(self.template_src, m), seg)]

# ---------- 测试 ----------
def run(devs, fs=FS):
    tr = Matcher()
    out = []
    for i, d in enumerate(devs):
        tr.feed(i / fs, d)
        if i % 100 == 99:
            out.append((i / fs, int(tr.hr + 0.5) if tr.hr else 0, tr.last_score))
    return out

if __name__ == '__main__':
    cases = [
        ('理想 80', lambda t: 80, 0.0),
        ('理想 150', lambda t: 150, 0.0),
        ('纹波 80', lambda t: 80, 50.0),
        ('加速 80→160', lambda t: 80 + 80 * min(1.0, t / 20), 50.0),
    ]
    for name, fn, rip in cases:
        dev = [v + 12 for v in S.synth_dev(fn, 40, noise=4, ripple_hz=5.0, ripple_amp=rip)]
        out = run(dev)
        vals = [(t, b) for t, b, _ in out if b > 0]
        if vals:
            err = [abs(b - fn(t)) for t, b in vals]
            print(f'{name:12s} 帧={len(vals)}/{len(out)} 中位误差={statistics.median(err):5.1f} '
                  f'p90={R.pct(err,0.9):5.1f} 最终={vals[-1][1]}')
        else:
            print(f'{name:12s} 无输出')
