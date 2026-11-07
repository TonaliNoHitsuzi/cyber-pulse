#!/usr/bin/env python3
"""OLED 帧缓冲复刻 + 风格化 SVG 导出.

字模与绘制逻辑全部从固件源码读出:
  D:/Espressif/workspace/pulse_meter/main/ssd1306.c
  D:/Espressif/workspace/pulse_meter/main/font8x8_basic.h

复刻的函数: ssd1306_clear / px / text / bar / bignum_scaled / flush(页格式)
外加 main.c 里的 draw_status_dot 与 oled_task 的 UI 绘制顺序。

用法:
  python oled_render.py            # 渲染 GOOD / WEAK / IDLE 三张 svg
  python oled_render.py --ascii    # 额外打印帧缓冲 ASCII, 便于核对
"""
import argparse
import re
import sys
from pathlib import Path

FW = Path(r"D:/Espressif/workspace/pulse_meter/main")
OUT = Path(r"D:/FileCenter/10-学期/大三上/单片机课程作业/汇报讲稿/pages/d2-08-gates/assets")

W, H = 128, 32
PAGES = H // 8


def load_font8x8(path):
    """从 C 源里抽出 font8x8_basic[96][8] 的字节, 不做任何修改."""
    src = path.read_text(encoding="utf-8", errors="replace")
    body = src[src.index("font8x8_basic[96][8]") :]
    body = body[body.index("{") + 1 :]
    rows = re.findall(r"\{([^{}]*)\}", body)
    font = []
    for r in rows:
        vals = [int(v, 0) for v in re.findall(r"0x[0-9a-fA-F]+|\b\d+\b", r)]
        if len(vals) == 8 and len(font) < 96:
            font.append(vals)
    assert len(font) >= 95, f"字库解析失败, 得到 {len(font)} 个字形"
    # 固件声明 [96][8] 但只显式写了 95 个, 末尾由 C 语言零初始化补齐
    while len(font) < 96:
        font.append([0] * 8)
    return font


def load_bigdigits(path):
    """从 ssd1306.c 抽出 bigdigits[10][5]."""
    src = path.read_text(encoding="utf-8", errors="replace")
    seg = src[src.index("bigdigits[10][5]") :]
    seg = seg[seg.index("{") + 1 :]
    seg = seg[: seg.index("};")]
    rows = re.findall(r"\{([^{}]*)\}", seg)
    digs = []
    for r in rows:
        vals = [int(v, 0) for v in re.findall(r"0x[0-9a-fA-F]+|\b\d+\b", r)]
        if len(vals) == 5:
            digs.append(vals)
    assert len(digs) == 10, f"大数字解析失败, 得到 {len(digs)} 个"
    return digs


FONT = load_font8x8(FW / "font8x8_basic.h")
BIGDIGITS = load_bigdigits(FW / "ssd1306.c")


class SSD1306:
    def __init__(self, height=32):
        self.height = height
        self.fb = bytearray(W * PAGES)

    def clear(self):
        self.fb = bytearray(W * PAGES)

    def px(self, x, y, on):
        if x < 0 or x >= W or y < 0 or y >= self.height:
            return
        page = y // 8
        i = page * W + x
        if on:
            self.fb[i] |= 1 << (y % 8)
        else:
            self.fb[i] &= ~(1 << (y % 8)) & 0xFF

    def text(self, s, x, row):
        """ssd1306_text: glyph[col] 整字节覆写该列 (注意是覆写, 不是 OR)."""
        cx = x
        for ch in s:
            c = ord(ch)
            if c < 32 or c > 127:
                c = ord("?")
            glyph = FONT[c - 32]
            for col in range(8):
                if cx + col >= W:
                    break
                self.fb[row * W + cx + col] = glyph[col] & 0xFF
            cx += 8
        return cx - x

    def bar(self, x, y, w, h, ratio):
        ratio = max(0.0, min(1.0, ratio))
        fill = int(w * ratio)
        for yy in range(h):
            for xx in range(w):
                on = 1 if xx < fill else (
                    1 if (xx == fill or yy == 0 or yy == h - 1 or xx == w - 1) else 0
                )
                self.px(x + xx, y + yy, on)

    def bignum_scaled(self, digit, x, y, scale):
        if digit < 0 or digit > 9:
            return
        for r in range(5):
            for c in range(3):
                if BIGDIGITS[digit][r] & (4 >> c):
                    for a in range(scale):
                        for b in range(scale):
                            self.px(x + c * scale + b, y + r * scale + a, 1)

    def status_dot(self, cx, cy, r, fill):
        for dy in range(-r, r + 1):
            for dx in range(-r, r + 1):
                d2 = dx * dx + dy * dy
                if d2 <= r * r:
                    if fill or d2 > (r - 1) * (r - 1):
                        self.px(cx + dx, cy + dy, 1)

    def pixel_matrix(self):
        m = [[0] * W for _ in range(self.height)]
        for y in range(self.height):
            for x in range(W):
                if self.fb[(y // 8) * W + x] & (1 << (y % 8)):
                    m[y][x] = 1
        return m


def render_state(state, p95, bpm, connected=True, beat_flash=False, hold=False):
    """严格按 main.c oled_task() 的顺序复刻 (行号见 1391-1428)."""
    s = SSD1306(32)
    s.clear()

    # Row0: 标题 + 心跳指示
    s.text(">> PULSE <<" if beat_flash else "   PULSE  ", 0, 0)

    # Row1: 佩戴状态
    s.text(state, 0, 1)

    # Row2: p95
    s.text("p95=%.0f" % p95, 0, 2)

    # BLE 状态灯 (80, 11, r=4): 实心=已连接
    dot_fill = 1 if connected else 0
    s.status_dot(80, 11, 4, dot_fill)

    # Row3: 信号条 88x8 @ y=24
    ratio = p95 / 200.0
    if ratio > 1:
        ratio = 1
    s.bar(0, 24, 88, 8, ratio)

    # 右侧 40px
    if bpm > 0:
        d1, d2, d3 = bpm // 100, (bpm // 10) % 10, bpm % 10
        # 固件是 92/105/118：第三位到 x=129，超出 128 会被裁掉右缘 2~3 列。
        # 展示时整体左移 3px（89/102/115），让三位数字完整；其余像素与固件一致。
        s.bignum_scaled(d1, 89, 0, 4)
        s.bignum_scaled(d2, 102, 0, 4)
        s.bignum_scaled(d3, 115, 0, 4)
        s.text("~" if hold else "BPM", 98, 3)
    else:
        s.text("---", 98, 1)
        s.text("BPM", 98, 2)
    return s


# ---------- 风格化 SVG ----------

SCALE = 6          # 6x → 768 x 192
BG = "#071019"
FG = "#d6ecff"
EDGE = "#12202e"


def to_svg(s, scale=SCALE):
    m = s.pixel_matrix()
    pad = 12                       # 屏幕四周留一圈黑边，避免首列像素贴边
    vw, vh = W * scale + 2 * pad, H * scale + 2 * pad
    cell = scale
    gap = 0.45
    size = cell - gap
    off = gap / 2.0
    rx = size * 0.16
    radius = 5

    uses = []
    for y in range(H):
        for x in range(W):
            if m[y][x]:
                uses.append('<use href="#p" x="%.1f" y="%.1f"/>' % (x * cell + off + pad, y * cell + off + pad))
    body = "\n".join(uses)

    return "\n".join([
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %d %d" width="%d" height="%d" '
        'shape-rendering="geometricPrecision" role="img" aria-label="128x32 SSD1306 OLED">' % (vw, vh, vw, vh),
        "<defs>",
        '<rect id="p" width="%.2f" height="%.2f" rx="%.2f" fill="url(#lit)"/>' % (size, size, rx),
        '<linearGradient id="lit" x1="0" y1="0" x2="0" y2="1">',
        '<stop offset="0" stop-color="#f2faff"/><stop offset="1" stop-color="%s"/>' % FG,
        "</linearGradient>",
        '<radialGradient id="bg" cx="50%" cy="42%" r="78%">',
        '<stop offset="0" stop-color="#0b1a26"/><stop offset="1" stop-color="%s"/>' % BG,
        "</radialGradient>",
        '<filter id="bloom" x="-8%" y="-30%" width="116%" height="160%">',
        '<feDropShadow dx="0" dy="0" stdDeviation="%.2f" flood-color="#8ec8ff" flood-opacity="0.60"/>'
        % (scale * 0.70),
        "</filter>",
        "</defs>",
        '<rect x="0" y="0" width="%d" height="%d" rx="%d" fill="url(#bg)"/>' % (vw, vh, radius),
        '<rect x="0.75" y="0.75" width="%.1f" height="%.1f" rx="%d" fill="none" stroke="%s" '
        'stroke-opacity="0.9" stroke-width="1.5"/>' % (vw - 1.5, vh - 1.5, radius, EDGE),
        '<g filter="url(#bloom)" transform="translate(%d,%d)">' % (0, 0),
        body,
        "</g>",
        "</svg>",
    ])



def ascii_dump(s):
    m = s.pixel_matrix()
    lines = []
    for y in range(H):
        lines.append("".join("#" if m[y][x] else "." for x in range(W)))
    return "\n".join(lines)


CASES = [
    ("oled_good", dict(state="GOOD", p95=62, bpm=78, connected=True, beat_flash=False)),
    ("oled_weak", dict(state="WEAK", p95=41, bpm=0, connected=True, beat_flash=False)),
    ("oled_idle", dict(state="IDLE", p95=12, bpm=0, connected=True, beat_flash=False)),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ascii", action="store_true")
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args()

    outdir = Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)
    for name, kw in CASES:
        s = render_state(**kw)
        (outdir / (name + ".svg")).write_text(to_svg(s), encoding="utf-8")
        lit = sum(sum(row) for row in s.pixel_matrix())
        print(f"{name}: {lit} 个点亮像素 -> {outdir / (name + '.svg')}")
        if args.ascii:
            print(ascii_dump(s))


if __name__ == "__main__":
    main()
