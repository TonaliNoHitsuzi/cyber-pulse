# -*- coding: utf-8 -*-
"""
把「可穿戴系统拓扑图.html」里的照片与拓扑关系，重排成幻灯片尺度（1300×520）。
原图 2080×1560，缩到投影片上是 6px 字，所以只借它的照片与连接关系，版式重画。
"""
import re, os, html

SRC = os.path.join(os.path.dirname(__file__), '..', '..', '可穿戴系统拓扑图.html')
OUT = os.path.join(os.path.dirname(__file__), '..', 'pages', 'd1-02-wiring', 'assets', 'topology.svg')

def load_images():
    s = open(SRC, encoding='utf-8').read()
    out = {}
    for m in re.finditer(r'<image\b([^>]*)>', s):
        a = m.group(1)
        x = float(re.search(r'\sx="([\d.]+)"', a).group(1))
        y = float(re.search(r'\sy="([\d.]+)"', a).group(1))
        href = re.search(r'href="([^"]+)"', a).group(1)
        if y < 500 and x < 700:        out['sen'] = href
        elif y < 500 and x > 1400:     out['oled'] = href
        elif 500 < y < 1000 and x < 700:   out['bat'] = href
        elif 500 < y < 1000 and 700 < x < 1400: out['mcu'] = href
        elif 1000 < y and x > 1400:    out['btn'] = href
        elif y < 1000 and x > 1400:    out['ring'] = href
    return out

# ---- 文本宽度粗估（中文 1em，数字/字母 .58em） ----
def tw(s, fs):
    w = 0
    for ch in s:
        w += fs * (1.0 if ord(ch) > 0x2E80 else 0.58)
    return w

def pill(x, y, text, color, fs=13.5):
    w = tw(text, fs) + 18
    return (f'<rect x="{x-w/2:.1f}" y="{y-15:.1f}" width="{w:.1f}" height="24" rx="6" '
            f'fill="#ffffff" stroke="{color}" stroke-width="1.1"/>'
            f'<text x="{x:.1f}" y="{y+2:.1f}" text-anchor="middle" font-size="{fs}" '
            f'font-family="Consolas, monospace" fill="{color}" font-weight="600">{html.escape(text)}</text>')

def card(x, y, w, name, sub, href, name_fs=20, h_photo=110):
    cid = f'c{abs(hash((x,y,name)))%99999}'
    return f'''<clipPath id="{cid}"><rect x="{x+10}" y="{y+10}" width="{w-20}" height="{h_photo}" rx="9"/></clipPath>
<rect x="{x}" y="{y}" width="{w}" height="200" rx="14" fill="#ffffff" stroke="#dbe3ec" stroke-width="1.4"/>
<image x="{x+10}" y="{y+10}" width="{w-20}" height="{h_photo}" preserveAspectRatio="xMidYMid slice" clip-path="url(#{cid})" href="{href}"/>
<text x="{x+14}" y="{y+h_photo+38}" font-size="{name_fs}" font-weight="600" fill="#0f172a">{name}</text>
<text x="{x+14}" y="{y+h_photo+59}" font-size="12" fill="#94a3b8">{sub}</text>'''

def wire(x1,y1,x2,y2,color,sw=2.2,dash=''):
    d = f' stroke-dasharray="{dash}"' if dash else ''
    return f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" stroke-width="{sw}" stroke-linecap="round"{d}/>'

def path(d,color,sw=2.2,arrow=True):
    mk = f' marker-end="url(#ar-{color[1:]})"' if arrow else ''
    return f'<path d="{d}" fill="none" stroke="{color}" stroke-width="{sw}" stroke-linecap="round" stroke-linejoin="round"{mk}/>'

IM = load_images()
BLUE, SLATE, VIOLET, INK, DIM = '#1d4ed8', '#94a3b8', '#6d28d9', '#0f172a', '#64748b'

parts = []
# 箭头标记
for c in (BLUE, SLATE, VIOLET):
    parts.append(f'<marker id="ar-{c[1:]}" viewBox="0 0 12 12" refX="9.5" refY="6" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M1 1 L11 6 L1 11 z" fill="{c}"/></marker>')

# ---------- 连线（先画，压在卡片下面） ----------
parts.append(wire(240, 105, 505, 92, BLUE))
parts.append(wire(240, 375, 505, 252, SLATE))
parts.append(wire(795, 92, 1060, 105, SLATE))
parts.append(wire(795, 252, 1060, 375, SLATE))
# 供电：两路汇到一根 5V 母线
parts.append(wire(450, 360, 450, 345, VIOLET))
parts.append(wire(850, 360, 850, 345, VIOLET))
parts.append(wire(450, 345, 850, 345, VIOLET))
parts.append(path('M 650 345 L 650 333', VIOLET))

# ---------- 卡片 ----------
parts.append(card(20,  30, 220, '压电薄膜', 'S · 贴拇指指腹', IM['sen']))
parts.append(card(20, 290, 220, '轻触按钮', 'SIG · 手背可及', IM['btn']))
parts.append(card(1060, 30, 220, 'OLED 0.91″', 'I2C · 128×32', IM['oled']))
parts.append(card(1060, 290, 220, 'WS2812 灯环', '16 珠 · 4.5V 串 1N4148', IM['ring']))

# 主控卡
mcu = f'''<clipPath id="cmcu"><rect x="532" y="32" width="236" height="150" rx="9"/></clipPath>
<rect x="520" y="20" width="260" height="310" rx="16" fill="#ffffff" stroke="#bfd0e6" stroke-width="1.8"/>
<image x="532" y="32" width="236" height="150" preserveAspectRatio="xMidYMid slice" clip-path="url(#cmcu)" href="{IM['mcu']}"/>
<text x="534" y="212" font-size="20" font-weight="700" fill="{INK}">ESP32-C3 SuperMini</text>
<text x="534" y="233" font-size="12" fill="#94a3b8">1 kHz 采样 · BLE 5 · 4 MB</text>
<line x1="534" y1="248" x2="766" y2="248" stroke="#eef2f7"/>
<text x="534" y="272" font-size="13" fill="{BLUE}" font-weight="600">ADC1 只有 GPIO0–4</text>
<text x="534" y="295" font-size="13" font-family="Consolas, monospace" fill="{DIM}">用掉 0 · 4 · 5 · 8 · 10</text>
<text x="534" y="317" font-size="11" fill="#94a3b8">GND 全系统一棵树共地</text>'''
parts.append(mcu)

# ---------- 两套供电 ----------
def power_chip(x, title, sub, color, icon):
    return f'''<rect x="{x}" y="360" width="300" height="80" rx="12" fill="#ffffff" stroke="{color}" stroke-width="1.4"/>
{icon}
<text x="{x+76}" y="388" font-size="15" font-weight="600" fill="{INK}">{title}</text>
<text x="{x+76}" y="410" font-size="11.5" fill="#94a3b8">{sub}</text>'''

bat_icon = f'''<rect x="316" y="380" width="13" height="40" rx="3" fill="#f5f3ff" stroke="#c4b5fd"/>
<rect x="332" y="380" width="13" height="40" rx="3" fill="#f5f3ff" stroke="#c4b5fd"/>
<rect x="348" y="380" width="13" height="40" rx="3" fill="#f5f3ff" stroke="#c4b5fd"/>'''
# 开关符号（画在标题右侧）
switch = f'''<rect x="482" y="377" width="32" height="18" rx="9" fill="#ede9fe" stroke="{VIOLET}" stroke-width="1.2"/>
<circle cx="504" cy="386" r="5.6" fill="{VIOLET}"/>'''

pb_icon = f'''<rect x="716" y="380" width="44" height="40" rx="8" fill="#f5f3ff" stroke="#c4b5fd"/>
<rect x="725" y="392" width="26" height="6" rx="3" fill="{VIOLET}" opacity=".8"/>
<rect x="725" y="404" width="16" height="4" rx="2" fill="{VIOLET}" opacity=".35"/>'''

parts.append(power_chip(300, '电池盒 3×AAA', '4.5V · 带开关 · 轻，可穿戴', VIOLET, bat_icon + switch))
parts.append(power_chip(700, '充电宝 + 电源模块', '5V · 稳，采集时用这套', VIOLET, pb_icon))

# 二选一
parts.append(f'<text x="650" y="390" text-anchor="middle" font-size="14" font-weight="600" fill="{VIOLET}">二选一 → 5V</text>')
parts.append(f'<text x="650" y="412" text-anchor="middle" font-size="11" fill="#94a3b8">同一时刻只接一路</text>')

# ---------- 线上的标签 ----------
parts.append(pill(372, 78,  'S → GPIO0', BLUE))
parts.append(pill(372, 300, 'SIG → GPIO4', SLATE))
parts.append(pill(928, 78,  'I2C · 8/10', SLATE))
parts.append(pill(928, 300, 'DIN → GPIO5', SLATE))


svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1300 520" width="1300" height="520"
     font-family="Noto Sans SC, Microsoft YaHei UI, sans-serif">
<defs>{''.join(p for p in parts if p.startswith('<marker'))}</defs>
{''.join(p for p in parts if not p.startswith('<marker'))}
</svg>'''

os.makedirs(os.path.dirname(OUT), exist_ok=True)
open(OUT, 'w', encoding='utf-8').write(svg)
print('written', OUT, os.path.getsize(OUT)//1024, 'KB')
