/**
 * 转场：全局矩阵 → 聚焦交点 → 十字邻域 → 进入内容
 *
 * 交互：分两步推进（每次按 → 前进一步）
 *   第 1 步：矩阵（等待点击）
 *   第 2 步：镜头推进 900ms → 邻域图（等待点击）
 *   第 3 步：交给 deck 进入下一页
 *
 * 数据：
 * {
 *   focus: { day: 5, line: 'algo' },
 *   titles: { '4:algo': '时基与不应期', ... }   // 可选，格子标题
 * }
 */
import { DAYS, LINES, COUNTS, LINE_COLOR } from '../content/matrix.js';

const NS = 'http://www.w3.org/2000/svg';
const easeInOut = (t) => (t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2);
const radiusOf = (cnt) => 5 + Math.min(cnt, 8) * 0.6;   // 5 ~ 9.8，刻意收敛

export function renderTransition(container, data) {
  const W = Math.max(container.clientWidth || 0, 1400);
  const H = Math.max(container.clientHeight || 0, 560);
  const padL = 110, padT = 56, padR = 30, padB = 40;
  const cw = (W - padL - padR) / DAYS.length;
  const ch = (H - padT - padB) / LINES.length;
  const counts = data.counts || COUNTS;
  const auto = !!data.autoplay;
  const fi = data.focus.day - 1;
  const fj = Math.max(0, LINES.findIndex((l) => l.id === data.focus.line));

  container.innerHTML = '';
  container.style.position = 'relative';
  container.style.height = H + 'px';

  const svg = document.createElementNS(NS, 'svg');
  svg.setAttribute('width', W);
  svg.setAttribute('height', H);
  svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
  svg.style.display = 'block';
  container.appendChild(svg);

  /* ---------- 表格：高亮行列 ---------- */
  const rowH = document.createElementNS(NS, 'rect');
  rowH.setAttribute('x', padL); rowH.setAttribute('y', padT + ch * fj);
  rowH.setAttribute('width', W - padL - padR); rowH.setAttribute('height', ch);
  rowH.setAttribute('fill', '#f1f5f9');
  svg.appendChild(rowH);

  const colH = document.createElementNS(NS, 'rect');
  colH.setAttribute('x', padL + cw * fi); colH.setAttribute('y', padT);
  colH.setAttribute('width', cw); colH.setAttribute('height', H - padT - padB);
  colH.setAttribute('fill', '#f1f5f9');
  svg.appendChild(colH);

  /* ---------- 表格线 ---------- */
  DAYS.forEach((_, i) => {
    const l = document.createElementNS(NS, 'line');
    l.setAttribute('x1', padL + cw * i); l.setAttribute('x2', padL + cw * i);
    l.setAttribute('y1', padT); l.setAttribute('y2', H - padB);
    l.setAttribute('stroke', '#e2e8f0'); l.setAttribute('stroke-width', 1);
    svg.appendChild(l);
  });
  const lr = document.createElementNS(NS, 'line');
  lr.setAttribute('x1', W - padR); lr.setAttribute('x2', W - padR);
  lr.setAttribute('y1', padT); lr.setAttribute('y2', H - padB);
  lr.setAttribute('stroke', '#e2e8f0'); svg.appendChild(lr);

  LINES.forEach((_, j) => {
    const l = document.createElementNS(NS, 'line');
    l.setAttribute('x1', padL); l.setAttribute('x2', W - padR);
    l.setAttribute('y1', padT + ch * j); l.setAttribute('y2', padT + ch * j);
    l.setAttribute('stroke', '#e2e8f0'); l.setAttribute('stroke-width', 1);
    svg.appendChild(l);
  });
  const lb = document.createElementNS(NS, 'line');
  lb.setAttribute('x1', padL); lb.setAttribute('x2', W - padR);
  lb.setAttribute('y1', H - padB); lb.setAttribute('y2', H - padB);
  lb.setAttribute('stroke', '#e2e8f0'); svg.appendChild(lb);

  /* ---------- 表头（随网格一起缩放） ---------- */
  let focusDayText = null, focusLineText = null;
  DAYS.forEach((d, i) => {
    const t = document.createElementNS(NS, 'text');
    t.setAttribute('x', padL + cw * (i + 0.5));
    t.setAttribute('y', padT - 20);
    t.setAttribute('text-anchor', 'middle');
    t.setAttribute('font-size', '16');
    t.setAttribute('font-weight', i === fi ? '700' : '500');
    t.setAttribute('fill', i === fi ? '#0f172a' : '#475569');
    t.textContent = `Day ${d}`;
    if (i === fi) focusDayText = t;
    svg.appendChild(t);
  });
  LINES.forEach((ln, j) => {
    const t = document.createElementNS(NS, 'text');
    t.setAttribute('x', padL - 20);
    t.setAttribute('y', padT + ch * (j + 0.5) + 6);
    t.setAttribute('text-anchor', 'end');
    t.setAttribute('font-size', '16');
    t.setAttribute('font-weight', j === fj ? '700' : '500');
    t.setAttribute('fill', j === fj ? '#0f172a' : '#475569');
    t.textContent = ln.name;
    if (j === fj) focusLineText = t;
    svg.appendChild(t);
  });

  /* ---------- 镜头推进 ---------- */
  const cx = padL + cw * (fi + 0.5);
  const cy = padT + ch * (fj + 0.5);
  const from = { x: 0, y: 0, w: W, h: H };
  /* 取景窗口与容器同宽高比，避免 meet 留黑边导致标签/裁切错位 */
  const ZW = Math.min(cw * 4.2, W - padL - padR);
  const ZH = ZW * (H / W);
  const zx = Math.min(Math.max(cx - ZW / 2, padL), W - padR - ZW);
  const zy = Math.min(Math.max(cy - ZH / 2, padT), H - padB - ZH);
  const to = { x: zx, y: zy, w: ZW, h: ZH };

  /* ---------- 冻结标签：跟着镜头飞到画面边缘 ---------- */
  const ov = document.createElementNS(NS, 'svg');
  ov.setAttribute('width', W); ov.setAttribute('height', H);
  ov.style.cssText = 'position:absolute;left:0;top:0;pointer-events:none;';
  container.appendChild(ov);

  function chip(text, weight, w) {
    const g = document.createElementNS(NS, 'g');
    g.style.opacity = '0';
    const r = document.createElementNS(NS, 'rect');
    r.setAttribute('rx', 10);
    r.setAttribute('width', w); r.setAttribute('height', 30);
    r.setAttribute('fill', '#ffffff');
    r.setAttribute('stroke', '#dbe3ec');
    r.setAttribute('stroke-width', 1.2);
    const t = document.createElementNS(NS, 'text');
    t.setAttribute('text-anchor', 'middle');
    t.setAttribute('font-size', '15');
    t.setAttribute('font-weight', weight);
    t.setAttribute('fill', '#0f172a');
    t.textContent = text;
    g.append(r, t);
    ov.appendChild(g);
    return { g, r, t, w };
  }
  const dayChip = chip(`Day ${data.focus.day}`, '700', 100);
  const lineChip = chip(LINES[fj].name, '600', 78);

  const placeChip = (c, x, y) => {
    c.r.setAttribute('x', x - c.w / 2);
    c.r.setAttribute('y', y - 15);
    c.t.setAttribute('x', x);
    c.t.setAttribute('y', y + 5);
  };
  const dFrom = { x: padL + cw * (fi + 0.5), y: padT - 20 };
  const dTo = { x: ((cx - to.x) / to.w) * W, y: 40 };
  const lFrom = { x: padL - 20, y: padT + ch * (fj + 0.5) };
  const lTo = { x: 58, y: ((cy - to.y) / to.h) * H };
  placeChip(dayChip, dFrom.x, dFrom.y);
  placeChip(lineChip, lFrom.x, lFrom.y);

  const fadeHeader = () => { dayChip.g.style.opacity = '0'; lineChip.g.style.opacity = '0'; };

  /* ---------- 点 ---------- */
  LINES.forEach((ln, j) => {
    DAYS.forEach((d, i) => {
      const key = `${d}:${ln.id}`;
      const cnt = counts[key] || 0;
      const x = padL + cw * (i + 0.5);
      const y = padT + ch * (j + 0.5);
      const isFocus = i === fi && j === fj;
      const r = radiusOf(cnt);

      if (isFocus) {
        // 光晕
        const glow = document.createElementNS(NS, 'circle');
        glow.setAttribute('cx', x); glow.setAttribute('cy', y);
        glow.setAttribute('r', r * 2.6);
        glow.setAttribute('fill', LINE_COLOR[ln.id]);
        glow.setAttribute('opacity', '.16');
        glow.setAttribute('filter', 'blur(6px)');
        svg.appendChild(glow);

        const ring = document.createElementNS(NS, 'circle');
        ring.setAttribute('cx', x); ring.setAttribute('cy', y);
        ring.setAttribute('r', r * 1.8);
        ring.setAttribute('fill', 'none');
        ring.setAttribute('stroke', LINE_COLOR[ln.id]);
        ring.setAttribute('stroke-width', 2);
        ring.setAttribute('opacity', '.55');
        ring.classList.add('pulse');
        svg.appendChild(ring);
      }

      if (!cnt) return;                       // 没有事件的格子不画点
      const c = document.createElementNS(NS, 'circle');
      c.setAttribute('cx', x); c.setAttribute('cy', y);
      c.setAttribute('r', isFocus ? r * 1.5 : r);
      c.setAttribute('fill', isFocus ? LINE_COLOR[ln.id] : LINE_COLOR[ln.id]);
      c.setAttribute('fill-opacity', isFocus ? '1' : '.18');
      c.setAttribute('stroke', LINE_COLOR[ln.id]);
      c.setAttribute('stroke-width', isFocus ? 3 : 1.5);
      c.setAttribute('stroke-opacity', isFocus ? '1' : '.75');
      svg.appendChild(c);
    });
  });


  const localBox = document.createElement('div');
  localBox.style.cssText = 'position:absolute;inset:0;opacity:0;transition:opacity .45s ease;';
  container.appendChild(localBox);

  const badge = document.createElement('div');
  badge.className = 'focusBadge';
  badge.innerHTML = `<i style="background:${LINE_COLOR[data.focus.line]}"></i>
    Day ${data.focus.day} · ${LINES[fj].name}`;
  if (!data.list) {
    badge.style.opacity = '0';
    container.appendChild(badge);
  }

  const hint = document.createElement('div');
  hint.className = 'advanceHint';
  hint.textContent = '按 → 继续';
  if (!auto) container.appendChild(hint);

  let stage = 0;        // 0 矩阵　1 推进中　2 邻域
  const setView = (b) => svg.setAttribute('viewBox', `${b.x} ${b.y} ${b.w} ${b.h}`);

  function animateCamera(dur = 900, done) {
    const t0 = performance.now();
    const tick = (now) => {
      const p = Math.min(1, (now - t0) / dur);
      const e = easeInOut(p);
      setView({
        x: from.x + (to.x - from.x) * e,
        y: from.y + (to.y - from.y) * e,
        w: from.w + (to.w - from.w) * e,
        h: from.h + (to.h - from.h) * e,
      });
      const vw = from.w + (to.w - from.w) * e;
      const vh = from.h + (to.h - from.h) * e;
      const vx = from.x + (to.x - from.x) * e;
      const vy = from.y + (to.y - from.y) * e;
      placeChip(dayChip, ((cx - vx) / vw) * W, 40);
      placeChip(lineChip, 58, ((cy - vy) / vh) * H);
      if (p < 1) requestAnimationFrame(tick);
      else {
        svg.style.transition = 'opacity .3s ease';
        svg.style.opacity = '0';
        fadeHeader();
        if (data.list) drawList(); else drawNeighborhood();
        localBox.style.opacity = '1';
        badge.style.opacity = '1';
        stage = 2;
        if (!auto) hint.textContent = '按 → 进入内容';
        if (data.onArrive) setTimeout(data.onArrive, data.arriveDelay ?? 800);
      }
    };
    requestAnimationFrame(tick);
  }

  /* ---------- 十字邻域：前后上下 ---------- */
  function drawNeighborhood() {
    const lw = container.clientWidth, lh = container.clientHeight;
    const lsvg = document.createElementNS(NS, 'svg');
    lsvg.setAttribute('width', lw); lsvg.setAttribute('height', lh);

    const NW = 250, NH = 78;
    const cx0 = lw / 2, cy0 = lh / 2;
    const dx = lw * 0.30, dy = lh * 0.29;

    const cellLabel = (day, lineId) => data.titles?.[`${day}:${lineId}`] || '';

    const nodes = [];
    const push = (day, lineId, role, x, y) => {
      nodes.push({ day, lineId, role, x, y, label: cellLabel(day, lineId) });
    };

    if (fi > 0) push(fi, data.focus.line, 'prev', cx0 - dx, cy0);
    if (fi < DAYS.length - 1) push(fi + 2, data.focus.line, 'next', cx0 + dx, cy0);
    if (fj > 0) push(fi + 1, LINES[fj - 1].id, 'up', cx0, cy0 - dy);
    if (fj < LINES.length - 1) push(fi + 1, LINES[fj + 1].id, 'down', cx0, cy0 + dy);
    push(fi + 1, data.focus.line, 'cur', cx0, cy0);

    const edge = (x1, y1, x2, y2, color, dash, arrow = true) => {
      const p = document.createElementNS(NS, 'path');
      const mx = (x1 + x2) / 2;
      p.setAttribute('d', `M${x1},${y1} C${mx},${y1} ${mx},${y2} ${x2},${y2}`);
      p.setAttribute('fill', 'none');
      p.setAttribute('stroke', color);
      p.setAttribute('stroke-width', 2.5);
      if (dash) p.setAttribute('stroke-dasharray', '6 6');
      lsvg.appendChild(p);
      if (arrow) {
        const ang = Math.atan2(y2 - y1, x2 - x1);
        const s2 = 9;
        const tri = document.createElementNS(NS, 'polygon');
        tri.setAttribute('points',
          `${x2},${y2} ` +
          `${x2 - s2 * Math.cos(ang - 0.42)},${y2 - s2 * Math.sin(ang - 0.42)} ` +
          `${x2 - s2 * Math.cos(ang + 0.42)},${y2 - s2 * Math.sin(ang + 0.42)}`);
        tri.setAttribute('fill', color);
        lsvg.appendChild(tri);
      }
    };

    nodes.forEach((n) => {
      if (n.role === 'prev') edge(n.x + NW / 2, n.y, cx0 - NW / 2, cy0, '#94a3b8', false, true);
      if (n.role === 'next') edge(cx0 + NW / 2, cy0, n.x - NW / 2, n.y, '#ea580c', false, true);
      if (n.role === 'up') edge(cx0, cy0 - NH / 2, n.x, n.y + NH / 2, '#cbd5e1', true, false);
      if (n.role === 'down') edge(cx0, cy0 + NH / 2, n.x, n.y - NH / 2, '#cbd5e1', true, false);
    });

    nodes.forEach((n) => {
      const isCur = n.role === 'cur';
      const color = LINE_COLOR[n.lineId];
      const g = document.createElementNS(NS, 'g');

      const rect = document.createElementNS(NS, 'rect');
      rect.setAttribute('x', n.x - NW / 2);
      rect.setAttribute('y', n.y - NH / 2);
      rect.setAttribute('width', NW);
      rect.setAttribute('height', NH);
      rect.setAttribute('rx', 14);
      rect.setAttribute('fill', isCur ? '#fff7ed' : '#ffffff');
      rect.setAttribute('stroke', isCur ? color : '#e2e8f0');
      rect.setAttribute('stroke-width', isCur ? 2.5 : 1.5);
      if (isCur) {
        const glow = document.createElementNS(NS, 'rect');
        glow.setAttribute('x', n.x - NW / 2 - 6);
        glow.setAttribute('y', n.y - NH / 2 - 6);
        glow.setAttribute('width', NW + 12);
        glow.setAttribute('height', NH + 12);
        glow.setAttribute('rx', 18);
        glow.setAttribute('fill', color);
        glow.setAttribute('opacity', '.10');
        lsvg.appendChild(glow);
      }
      g.appendChild(rect);

      const t1 = document.createElementNS(NS, 'text');
      t1.setAttribute('x', n.x); t1.setAttribute('y', n.y - 8);
      t1.setAttribute('text-anchor', 'middle');
      t1.setAttribute('font-size', '15');
      t1.setAttribute('fill', isCur ? color : '#94a3b8');
      t1.setAttribute('font-weight', isCur ? '700' : '400');
      t1.textContent = `Day ${n.day} · ${LINES.find((l) => l.id === n.lineId).name}`;
      g.appendChild(t1);

      const t2 = document.createElementNS(NS, 'text');
      t2.setAttribute('x', n.x); t2.setAttribute('y', n.y + 16);
      t2.setAttribute('text-anchor', 'middle');
      t2.setAttribute('font-size', '19');
      t2.setAttribute('font-weight', isCur ? '700' : '500');
      t2.setAttribute('fill', isCur ? '#0f172a' : '#475569');
      t2.textContent = n.label;
      g.appendChild(t2);

      lsvg.appendChild(g);
    });

    localBox.appendChild(lsvg);
  }

  /* ---------- 子目录（本节内容清单） ---------- */
  function drawList() {
    const box = document.createElement('div');
    box.className = 'subAgenda' + ((data.list || []).length > 6 ? ' compact' : '');
    const kick = document.createElement('div');
    kick.className = 'subBadge';
    kick.innerHTML = `<i style="background:${LINE_COLOR[data.focus.line]}"></i>Day ${data.focus.day} · ${LINES[fj].name}`;
    box.appendChild(kick);
    if (data.section) {
      const title = document.createElement('div');
      title.className = 'subTitle';
      title.textContent = data.section;
      box.appendChild(title);
    }
    (data.list || []).forEach((it, i) => {
      const row = document.createElement('div');
      row.className = 'subItem';
      const n = document.createElement('span');
      n.className = 'n';
      n.textContent = it.n || String(i + 1).padStart(2, '0');
      const t = document.createElement('span');
      t.className = 't';
      t.textContent = it.t;
      row.append(n, t);
      if (it.cur) row.classList.add('cur');
      box.appendChild(row);
    });
    localBox.appendChild(box);
  }

  /* ---------- 对外：分步推进 ---------- */
  const api = {
    advance() {
      if (stage === 0) {
        stage = 1; hint.style.opacity = '0';
        dayChip.g.style.opacity = '1'; lineChip.g.style.opacity = '1';
        if (focusDayText) focusDayText.style.opacity = '0';
        if (focusLineText) focusLineText.style.opacity = '0';
        svg.querySelectorAll('text').forEach((t) => { t.style.transition = 'opacity .25s'; t.style.opacity = '0'; });
        animateCamera(900); return true;
      }
      if (stage === 2) return false;      // 交给 deck 翻页
      return true;                        // 推进中，吞掉按键
    },
    get stage() { return stage; },
  };

  if (location.search.includes('stage=zoom')) {
    setView(to);
    placeChip(dayChip, ((cx - to.x) / to.w) * W, 40);
    placeChip(lineChip, 58, ((cy - to.y) / to.h) * H);
    if (focusDayText) focusDayText.style.opacity = '0';
    if (focusLineText) focusLineText.style.opacity = '0';
    dayChip.g.style.opacity = '1';
    lineChip.g.style.opacity = '1';
    hint.style.opacity = '0';
    stage = 1.5;
  }

  const keepMatrix = location.search.includes('stage=matrix');
  if (location.search.includes('anim=0') && !keepMatrix && !location.search.includes('stage=zoom')) {
    setView(to);
    svg.style.opacity = '0';
    fadeHeader();
    if (data.list) drawList(); else drawNeighborhood();
    localBox.style.transition = 'none';
    localBox.style.opacity = '1';
    badge.style.transition = 'none';
    badge.style.opacity = '1';
    hint.style.opacity = '0';
    stage = 2;
  }

  if (location.search.includes('dbg')) {
    document.title = JSON.stringify({ cw: Math.round(cw), ch: Math.round(ch), W, H,
      vb: svg.getAttribute('viewBox'), to, fi, fj });
  }
  container.__comp = api;
  if (auto) setTimeout(() => api.advance(), data.autoDelay ?? 260);
  return api;
}
