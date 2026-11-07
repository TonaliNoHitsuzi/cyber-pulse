# -*- coding: utf-8 -*-
"""检查每页有没有加出现动画（frag）。
用法：python tools/check_anim.py [--quiet]
规则：
  - 页面含 transition 块 = 转场/子目录页，跳过
  - 封面、纯图片展示页（bare 且只有 html）跳过
  - ul / steps / stats 的 frag 要乘条目数（deck.js 是逐条出现的）
"""
import json, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def read(path):
    with open(path, encoding='utf-8') as f:
        return f.read()

def count_frags(blocks):
    n = 0
    for b in blocks:
        if b.get('t') == 'transition':
            return -1
        if b.get('t') == 'split':
            for side in ('left', 'right'):
                sub = b.get(side)
                if isinstance(sub, list):
                    n += count_frags(sub)
            continue
        if not b.get('frag'):
            continue
        if b.get('t') in ('ul', 'steps', 'stats'):
            n += len(b.get('items') or [])
        else:
            n += 1
    return n

def main():
    quiet = '--quiet' in sys.argv
    order = re.findall(r"'([^']+)'", read(os.path.join(ROOT, 'content', 'manifest.js')).split('order = [')[1].split(']')[0])
    rows, missing = [], []
    for slug in order:
        cpath = os.path.join(ROOT, 'pages', slug, 'content.json')
        if not os.path.exists(cpath):
            rows.append((slug, '—', '缺 content.json')); continue
        data = json.loads(read(cpath))
        n = count_frags(data.get('blocks') or [])
        if n == -1:
            rows.append((slug, '转场', 'skip')); continue
        raw = read(cpath)
        if '待补' in raw or 'imgph' in raw:
            rows.append((slug, '0', 'skip(占位)')); continue
        bare = 'bare: true' in read(os.path.join(ROOT, 'pages', slug, 'page.js'))
        if n == 0 and bare:
            rows.append((slug, '0', 'skip(bare)')); continue
        rows.append((slug, str(n), 'OK' if n > 0 else '** 没动画 **'))
        if n == 0:
            missing.append(slug)
    if not quiet:
        for slug, n, st in rows:
            print(f'{slug:<22} {n:>4}  {st}')
    print()
    if missing:
        print('没加动画：', ', '.join(missing))
        sys.exit(1)
    print('全部有动画')

if __name__ == '__main__':
    main()
