#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
版式预检：在放图之前先算一遍，避免溢出/重叠

用法:
    python check_layout.py                # 检查 content/*.js 里所有图片
    python check_layout.py --json         # 机器可读

输出:
    每张图的原始尺寸、比例、在页面中的建议显示尺寸、是否溢出/过小
"""
import os
import re
import sys
import json

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

# 画布与安全区（与 style.css 一致）
CANVAS_W, CANVAS_H = 1600, 900
PAD_X, PAD_TOP, PAD_BOTTOM = 96, 64, 56
HEADER_H = 150        # 页头（坐标 + 标题 + 间距）
FOOTER_H = 44         # 页脚灰字
GAP = 24              # figrow 间距

BODY_W = CANVAS_W - PAD_X * 2
BODY_H = CANVAS_H - PAD_TOP - PAD_BOTTOM - HEADER_H - FOOTER_H

# 低于这个宽度视为"在教室后排看不清"
MIN_USABLE_W = 380
# 低于这个高度视为"图太小"
MIN_USABLE_H = 300


def img_size(path):
    try:
        from PIL import Image
        with Image.open(path) as im:
            return im.size
    except Exception:
        return None


def scan_contents():
    """扫描 pages/*/content.json，找出图片块与其所在布局"""
    found = []
    pages_dir = os.path.join(ROOT, 'pages')
    for slug in sorted(os.listdir(pages_dir)):
        cj = os.path.join(pages_dir, slug, 'content.json')
        if not os.path.isfile(cj):
            continue
        try:
            data = json.load(open(cj, encoding='utf-8'))
        except Exception as e:
            print(f"  ! {slug}/content.json 解析失败: {e}")
            continue

        def walk(blocks, in_split=False):
            for b in blocks or []:
                if not isinstance(b, dict):
                    continue
                t = b.get('t')
                if t == 'figure' and b.get('src'):
                    found.append({'slug': slug, 'layout': 'single', 'srcs': [b['src']]})
                elif t == 'figures' and b.get('items'):
                    found.append({'slug': slug, 'layout': 'column' if in_split else 'row',
                                  'srcs': [i['src'] for i in b['items'] if i.get('src')]})
                elif t == 'split':
                    walk(b.get('left'), True)
                    walk(b.get('right'), True)

        walk(data.get('blocks'))
    return found


def fit(w, h, max_w, max_h):
    """contain 缩放"""
    s = min(max_w / w, max_h / h)
    return round(w * s), round(h * s)


def main():
    rows_out = []
    issues = []

    for grp in scan_contents():
        n = len(grp['srcs'])
        if grp['layout'] == 'column':
            max_w, max_h = BODY_W * 0.55, BODY_H / n - 30
        elif grp['layout'] == 'row':
            max_w, max_h = (BODY_W - GAP * (n - 1)) / n if n > 1 else BODY_W, BODY_H
        else:
            max_w, max_h = BODY_W * 0.6, BODY_H
        for src in grp['srcs']:
            p = os.path.join(ROOT, 'pages', grp['slug'], src)
            size = img_size(p)
            if not size:
                issues.append(f"{grp['slug']}: 找不到或无法读取 {src}")
                rows_out.append({'src': src, 'err': 'missing'})
                continue
            w, h = size
            rw, rh = fit(w, h, max_w, max_h)
            ok = rw >= MIN_USABLE_W and rh >= MIN_USABLE_H
            rows_out.append({
                'file': grp['slug'], 'layout': grp['layout'], 'src': src,
                'orig': [w, h], 'ratio': round(w / h, 2),
                'render': [rw, rh], 'ok': ok,
                'note': '' if ok else ('偏小：后排可能看不清' if rh < MIN_USABLE_H else '过窄'),
            })
            if not ok:
                issues.append(f"{src}: 显示 {rw}×{rh}，偏小（建议换高分辨率或减少同排图片）")

    # 文本体量粗估（按块类型）
    print(f"画布 {CANVAS_W}×{CANVAS_H}，正文可用 {int(BODY_W)}×{int(BODY_H)}\n")
    if not rows_out:
        print('未找到图片引用。')
    for r in rows_out:
        if r.get('err'):
            print(f"  ✗ {r['src']}  (找不到)")
            continue
        flag = '✓' if r['ok'] else '!'
        print(f"  {flag} {r['file']}/{r['src']:<30} 原图 {r['orig'][0]}×{r['orig'][1]} "
              f"({r['ratio']}x) → 显示 {r['render'][0]}×{r['render'][1]}  {r['note']}")

    print()
    if issues:
        print('需要处理：')
        for i in issues:
            print('  ·', i)
    else:
        print('图片尺寸检查通过。')

    if '--json' in sys.argv:
        print(json.dumps({'body': [BODY_W, BODY_H], 'items': rows_out, 'issues': issues},
                         ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
