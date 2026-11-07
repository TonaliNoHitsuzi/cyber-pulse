/**
 * deck.js —— 组装式讲稿引擎
 * 负责：缩放 / 渲染 / 逐条 / 导航 / 总览 / 备注 / 计时 / 打印
 * 不负责：内容（在 content/ 里）、样式（在 style.css 里）
 */
import { order } from './content/manifest.js';
import { DAYS, DAY_DATES, LINES, COUNTS } from './content/matrix.js';
import { CHARTS, CYCLES, RINGS } from './content/charts.js';
import { renderDag } from './renderers/dag.js';
import { renderTransition } from './renderers/transition.js';
import { renderRing } from './renderers/ring.js';

/* ---------- 页面加载（一页一文件夹） ---------- */
async function loadPage(slug) {
  const mod = await import(`./pages/${slug}/page.js`);
  const meta = mod.default || {};
  let content = {};
  try {
    const r = await fetch(`./pages/${slug}/content.json`, { cache: 'no-cache' });
    if (r.ok) content = await r.json();
  } catch (e) { console.warn('content.json 缺失', slug, e); }
  if (meta.css) {
    const sel = `link[data-page="${slug}"]`;
    if (!document.querySelector(sel)) {
      const l = document.createElement('link');
      l.rel = 'stylesheet';
      l.href = `./pages/${slug}/${meta.css}`;
      l.dataset.page = slug;
      document.head.appendChild(l);
    }
  }
  const blocks = content.blocks || meta.blocks || [];
  normalizePaths(blocks, slug);
  return {
    ...meta,
    slug,
    kicker: content.kicker ?? meta.kicker,
    annot: content.annot ?? meta.annot,
    blocks,
  };
}

/* 把页内相对路径改写成 pages/<slug>/xxx */
function normalizePaths(blocks, slug) {
  const abs = (s) => /^(https?:|\/)/.test(s) ? s : `pages/${slug}/${s}`;
  const walk = (b) => {
    if (!b || typeof b !== 'object') return;
    if (b.t === 'figure' && typeof b.src === 'string') b.src = abs(b.src);
    if (b.t === 'figures' && Array.isArray(b.items)) {
      b.items.forEach((it) => { if (it.src) it.src = abs(it.src); });
    }
    if (Array.isArray(b.left)) b.left.forEach(walk);
    if (Array.isArray(b.right)) b.right.forEach(walk);
    if (b.t === 'html' && typeof b.html === 'string')
      b.html = b.html.replace(/src="assets\//g, `src="pages/${slug}/assets/`).replace(/poster="assets\//g, `poster="pages/${slug}/assets/`);
  };
  blocks.forEach(walk);
}

/* 五条线的内联图标 */
const ICONS = {
  hw: '<svg viewBox="0 0 16 16" width="15" height="15"><g fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"><rect x="4.5" y="4.5" width="7" height="7" rx="1.2"/><path d="M8 2v2.5M8 11.5V14M2 8h2.5M11.5 8H14"/></g></svg>',
  algo: '<svg viewBox="0 0 16 16" width="15" height="15"><path d="M1.5 8h2l2-4.5 3 9 2-6.5 1.5 2h2.5" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  exp: '<svg viewBox="0 0 16 16" width="15" height="15"><path d="M6.5 2v4.2L3.2 12.4a1 1 0 0 0 .9 1.6h7.8a1 1 0 0 0 .9-1.6L9.5 6.2V2M5.5 2h5" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  org: '<svg viewBox="0 0 16 16" width="15" height="15"><g fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"><circle cx="6" cy="5.5" r="2.2"/><path d="M2.2 13c0-2.1 1.7-3.4 3.8-3.4S9.8 10.9 9.8 13"/><circle cx="11.6" cy="6" r="1.6"/><path d="M10.3 9.8c1.8 0 3.3 1.2 3.3 3.2"/></g></svg>',
  demo: '<svg viewBox="0 0 16 16" width="15" height="15"><g fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"><rect x="2" y="3" width="12" height="8" rx="1.2"/><path d="M6 14h4M8 11v3"/></g></svg>',
};

const $ = (s, r = document) => r.querySelector(s);
window.CHARTS = CHARTS;
window.CYCLES = CYCLES;
window.RINGS = RINGS;
const deckEl = $('#deck');
const pageNum = $('#pageNum');
const bar = $('#progressBar');
const notesEl = $('#notes');
const notesBody = $('#notesBody');
const ovBtnEl = $('#ovBtn');
if (ovBtnEl) ovBtnEl.addEventListener('click', () => toggleOverview());
const ovToggleEl = $('#ovToggle');
if (ovToggleEl) ovToggleEl.addEventListener('click', (e) => { e.stopPropagation(); switchOverviewView(); });
const ovScrollEl = $('#overview');
if (ovScrollEl) {
  let spyAt = 0;
  ovScrollEl.addEventListener('scroll', () => {
    const now = performance.now();
    if (now - spyAt < 90) return;
    spyAt = now;
    requestAnimationFrame(() => {
      if (ovScrollEl.classList.contains('hidden')) return;
      const top = ovScrollEl.getBoundingClientRect().top + 110;
      let g = null;
      ovScrollEl.querySelectorAll('[data-group]').forEach((n) => {
        if (n.getBoundingClientRect().top <= top) g = n.dataset.group;
      });
      if (g) { ovActiveGroup = g; setActiveChip(g); }
    });
  }, { passive: true });
}

let slides = [];
let cur = -1;
let frags = [];          // 当前页的 fragment 元素
let fragIdx = 0;
let busy = false;
let startedAt = performance.now();

/* ---------------- 缩放 ---------------- */
/* 缩放交给 CSS（min(100vw/1600, 100vh/900)），这里只留空实现兼容旧调用 */
function fit() {}

/* ---------------- 内容渲染 ---------------- */
const esc = (s = '') => String(s);
const fmt = (s = '') => esc(s)
  .replace(/\[\[([^|\]]+)\|([^\]]+)\]\]/g, '<a class="jump" data-go="$1">$2</a>')
  .replace(/\*\*(.+?)\*\*/g, '<b>$1</b>')
  .replace(/`(.+?)`/g, '<code>$1</code>');

function el(tag, cls, html) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (html != null) e.innerHTML = html;
  return e;
}

function renderBlock(b) {
  let node;
  switch (b.t) {
    case 'h': {
      const lv = b.level || 2;
      node = el('div', `h${lv}`, fmt(b.text));
      break;
    }
    case 'p':
      node = el('p', 'p' + (b.small ? ' small' : ''), fmt(b.text));
      break;
    case 'ul': {
      node = el('ul', 'ul' + (b.tight ? ' tight' : ''));
      b.items.forEach((it) => {
        const li = el('li', b.frag ? 'frag' : '', fmt(it));
        node.appendChild(li);
      });
      break;
    }
    case 'quote':
      node = el('div', 'quote ' + (b.color || ''), fmt(b.text));
      break;
    case 'stats': {
      node = el('div', 'stats');
      b.items.forEach((it) => {
        const c = el('div', `stat ${it.color || ''}`);
        c.innerHTML = `<div class="k">${esc(it.k)}</div>
          <div class="v">${esc(it.v)}<span class="u">${esc(it.unit || '')}</span></div>`;
        if (b.frag) c.classList.add('frag');
        node.appendChild(c);
      });
      break;
    }
    case 'table': {
      node = el('table', 'table' + (b.line ? ' tbl-' + b.line : ''));
      const thead = el('thead');
      const trh = el('tr');
      b.head.forEach((h) => trh.appendChild(el('th', '', esc(h))));
      thead.appendChild(trh);
      const tb = el('tbody');
      b.rows.forEach((row, ri) => {
        const tr = el('tr', (b.highlight || []).includes(ri) ? 'hl' : '');
        row.forEach((cell) => {
          const isObj = typeof cell === 'object';
          tr.appendChild(el('td', isObj ? (cell.cls || '') : '', isObj ? fmt(cell.text) : fmt(cell)));
        });
        tb.appendChild(tr);
      });
      node.append(thead, tb);
      break;
    }
    case 'badge': {
      node = el('div', 'badge' + (b.frag ? ' frag' : ''));
      node.innerHTML = `
        <div class="chip">${esc(b.tag || '新增')}</div>
        <div class="rows">
          <div class="lab">新增</div><div>${fmt(b.what)}</div>
          <div class="lab">缘由</div><div>${fmt(b.why)}</div>
          <div class="lab">现场</div><div>${fmt(b.demo)}</div>
        </div>`;
      break;
    }
    case 'figure': {
      node = el('div', 'figure' + (b.frag ? ' frag' : ''));
      const img = el('img');
      img.src = b.src;
      img.alt = b.caption || '';
      img.onload = () => { img.dataset.ratio = (img.naturalWidth / img.naturalHeight).toFixed(3); };
      node.appendChild(img);
      if (b.caption) node.appendChild(el('div', 'cap', fmt(b.caption)));
      break;
    }
    case 'chart': {
      node = el('div', 'chart');
      node.dataset.chart = b.data;
      node.dataset.type = b.type || 'line';
      if (b.height) node.style.height = b.height + 'px';
      break;
    }
    case 'compare': {
      node = el('div', 'compare');
      ['left', 'right'].forEach((side) => {
        const c = el('div', 'col ' + side);
        c.appendChild(el('h4', '', esc(b[side].title)));
        const ul = el('ul');
        b[side].items.forEach((it) => ul.appendChild(el('li', '', fmt(it))));
        c.appendChild(ul);
        node.appendChild(c);
      });
      break;
    }
    case 'steps': {
      node = el('div', 'steps');
      b.items.forEach((it, i) => {
        const s = el('div', 'step' + (b.frag ? ' frag' : ''));
        s.innerHTML = `<div class="n">${String(i + 1).padStart(2, '0')}</div><div class="t">${fmt(it)}</div>`;
        node.appendChild(s);
        if (i < b.items.length - 1) node.appendChild(el('div', 'arrow', '→'));
      });
      break;
    }
    case 'formula': {
      node = el('div', 'formula' + (b.frag ? ' frag' : ''));
      node.innerHTML = `${b.html}${b.caption ? `<div class="cap">${fmt(b.caption)}</div>` : ''}`;
      break;
    }
    case 'note':
      node = el('div', 'note', fmt(b.text));
      break;
    case 'transition': {
      node = el('div', 'transitionBox');
      node.style.width = '100%';
      node.dataset.transition = JSON.stringify(b);
      break;
    }
    case 'dag': {
      node = el('div', 'dagBox');
      node.style.width = '100%';
      node.dataset.dag = JSON.stringify(b);
      break;
    }
    case 'cycle': {
      node = el('div', 'cy');
      node.style.height = (b.height || 520) + 'px';
      node.dataset.cycle = b.data;
      break;
    }
    case 'ring': {
      node = el('div', 'ringBox');
      node.style.height = (b.height || 560) + 'px';
      node.dataset.ring = b.data;
      break;
    }
    case 'matrix': {
      node = el('table', 'matrix');
      const days = b.days || DAYS;
      const lines = b.lines || [];
      const thead = el('thead');
      const trh = el('tr');
      trh.appendChild(el('th', 'corner', ''));
      days.forEach((d) => trh.appendChild(el('th', '', `Day ${d}`)));
      thead.appendChild(trh);
      node.appendChild(thead);
      const tb = el('tbody');
      lines.forEach((ln) => {
        const tr = el('tr');
        tr.appendChild(el('th', 'rowhead ' + ln.id,
          `<span class="li">${ICONS[ln.id] || ''}</span>${esc(ln.name)}`));
        days.forEach((d) => {
          const n = (b.counts || deckCounts())[`${d}:${ln.id}`] || 0;
          const td = el('td', 'cell ' + ln.id);
          if (n) {
            const sz = 28 + Math.min(n, 9) * 1.6;   // 尺寸只做轻微暗示
            td.innerHTML = `<span class="cnt" style="width:${sz}px;height:${sz}px;font-size:${Math.round(sz * 0.46)}px">${n}</span>`;
          } else {
            td.innerHTML = '<span class="none">·</span>';
          }
          td.dataset.day = d; td.dataset.line = ln.id;
          tr.appendChild(td);
        });
        tb.appendChild(tr);
      });
      node.appendChild(tb);
      break;
    }
    case 'echo': {
      node = el('div', 'echo frag ' + (b.kind === 'ans' ? 'ans' : 'ask'));
      node.textContent = b.text;
      break;
    }
    case 'split': {
      node = el('div', 'split');
      ['left', 'right'].forEach((side) => {
        const box = el('div', 'splitCol');
        (b[side] || []).forEach((sub) => box.appendChild(renderBlock(sub)));
        node.appendChild(box);
      });
      break;
    }
    case 'figures': {
      node = el('div', 'figrow');
      (b.items || []).forEach((it) => {
        const f = el('div', 'figure');
        const img = el('img');
        img.src = it.src; img.alt = it.caption || '';
        img.onload = () => {
          // 记录真实比例，供检查脚本与调试
          img.dataset.ratio = (img.naturalWidth / img.naturalHeight).toFixed(3);
        };
        f.appendChild(img);
        if (it.caption) f.appendChild(el('div', 'cap', fmt(it.caption)));
        node.appendChild(f);
      });
      break;
    }
    case 'html':
      node = el('div', '', b.html);
      break;
    default:
      node = el('div', 'p', '[unknown block: ' + b.t + ']');
  }
  if (b.cls) String(b.cls).split(' ').forEach((c) => node.classList.add(c));
  if (b.mt) node.style.marginTop = b.mt + 'px';
  if (b.frag && node.classList && !['ul','stats','steps'].includes(b.t) && !node.classList.contains('frag')) node.classList.add('frag');
  return node;
}

function deckCounts() {
  const c = {};
  slides.forEach((sl) => {
    if (isSectionPage(sl)) return;
    const cell = cellOf(sl);
    if (!cell) return;
    const k = `${cell.day}:${cell.line}`;
    c[k] = (c[k] || 0) + 1;
  });
  return c;
}

function renderSlide(s) {
  const own = document.querySelector(`link[data-page="${s.slug}"]`);
  if (own) document.head.appendChild(own);
  /* 只启用当前页的 page.css，避免别的页规则串进来
     （link.disabled 在部分 Chrome 下不生效，用 media 开关） */
  document.querySelectorAll('link[data-page]').forEach((l) => {
    l.media = l.dataset.page === s.slug ? '' : 'not all';
  });
  deckEl.innerHTML = '';

  // 页头
  if (!s.bare && (s.day || s.title)) {
    const head = el('div', 'pageHead');
    if (s.day) {
      const co = el('div', 'coord ' + (s.line || ''));
      const names = { hw: '硬件', algo: '算法', exp: '实验', org: '组织', demo: '系统' };
      const dayLabel = typeof s.day === 'number' ? `Day ${s.day}` : esc(s.day);
      const icon = ICONS[s.line] || '';
      co.innerHTML = `<span class="lineIcon">${icon}</span>${dayLabel} · ${esc(names[s.line] || '')}${
        s.no ? ' · 事件 ' + esc(s.no) : ''}`;
      head.appendChild(co);
    }
    if (s.kicker) head.appendChild(el('div', 'kicker', esc(s.kicker)));
    if (s.title) head.appendChild(el('h2', 'pageTitle', fmt(s.title)));
    deckEl.appendChild(head);
  }

  // 页体
  const body = el('div', 'pageBody' + (s.center ? ' center' : ''));
  if (s.bare && s.kicker) body.appendChild(el('div', 'kicker', esc(s.kicker)));
  (s.blocks || []).forEach((b) => body.appendChild(renderBlock(b)));
  deckEl.appendChild(body);

  // 页脚
  if (s.annot) deckEl.appendChild(el('div', 'pageFoot', fmt(s.annot)));

  // 总览按钮：目录表格页不显示
  const ovBtn = $('#ovBtn');
  if (ovBtn) ovBtn.classList.remove('hidden');

  // 图表 / DAG
  requestAnimationFrame(() => {
    body.querySelectorAll('[data-chart]').forEach(initChart);
    body.querySelectorAll('[data-cycle]').forEach(initCycle);
    body.querySelectorAll('[data-ring]').forEach((n) => renderRing(n, window.RINGS?.[n.dataset.ring]));
    body.querySelectorAll('[data-dag]').forEach((n) => renderDag(n, JSON.parse(n.dataset.dag)));
    body.querySelectorAll('[data-transition]').forEach((n) => {
      const td = JSON.parse(n.dataset.transition);
      if (!td.counts) td.counts = deckCounts();
      n.__comp = renderTransition(n, td);
    });
  });

  // 呼应 toast 移出正文流（绝对定位在画面中部），并排在最后一个
  deckEl.querySelectorAll('.pageBody .echo').forEach((n) => deckEl.appendChild(n));

  // fragment 初始化（echo 置后）
  frags = Array.from(deckEl.querySelectorAll('.frag'));
  frags.sort((a, b) => (a.classList.contains('echo') ? 1 : 0) - (b.classList.contains('echo') ? 1 : 0));
  if (location.search.includes('reveal')) revealAll();
  fragIdx = 0;
  if (s.fragAll) revealAll();
}

function initCycle(node) {
  if (!window.cytoscape) return;
  const cfg = window.CYCLES?.[node.dataset.cycle];
  if (!cfg) return;
  node.__cy = cytoscape({
    container: node,
    elements: cfg.elements,
    style: cfg.style,
    layout: cfg.layout,
    userZoomingEnabled: false,
    userPanningEnabled: false,
    boxSelectionEnabled: false,
    autoungrabify: true,
    autounselectify: true,
  });
}

function initChart(node) {
  if (!window.echarts) return;
  const data = window.CHARTS?.[node.dataset.chart];
  if (!data) return;
  const chart = echarts.init(node, null, { renderer: 'canvas' });
  chart.setOption(data);
  new ResizeObserver(() => chart.resize()).observe(node);
}

/* ---------------- 逐条 ---------------- */
function revealAll() {
  frags.forEach((f) => f.classList.add('on'));
  fragIdx = frags.length;
}
function stepFrag(dir) {
  if (!frags.length) return false;
  if (dir > 0) {
    if (fragIdx < frags.length) { frags[fragIdx++].classList.add('on'); return true; }
    return false;
  }
  if (fragIdx > 0) { frags[--fragIdx].classList.remove('on'); return true; }
  return false;
}

/* ---------------- 导航 ---------------- */
function isSectionPage(s) {
  return (s.blocks || []).some((b) => b.t === 'transition');
}

async function go(i, dir = 1) {
  if (busy) return;
  i = Math.max(0, Math.min(slides.length - 1, i));
  if (i === cur) return;
  busy = true;
  const target = slides[i];
  const noAnim = location.search.includes('anim=0');
  const sec = isSectionPage(target) && !noAnim && cur >= 0;

  /* 回目录：上一页向中心收拢淡出 */
  if (sec) {
    deckEl.style.transition = 'scale .22s cubic-bezier(.4,0,.6,1), opacity .22s ease';
    deckEl.style.scale = '0.94';
    deckEl.style.opacity = '0';
    await new Promise((r) => setTimeout(r, 220));
  }

  renderSlide(target);

  /* 表格放大淡入 */
  if (sec) {
    deckEl.classList.remove('enter');
    deckEl.style.transition = 'none';
    deckEl.style.scale = '0.88';
    deckEl.style.opacity = '0';
    void deckEl.offsetWidth;
    deckEl.style.transition = 'scale .40s cubic-bezier(.2,.8,.3,1), opacity .40s ease';
    deckEl.style.scale = '1';
    deckEl.style.opacity = '1';
    setTimeout(() => {
      deckEl.style.transition = '';
      deckEl.style.scale = '';
      deckEl.style.opacity = '';
    }, 460);
  } else {
    deckEl.style.transition = '';
    deckEl.style.scale = '';
    deckEl.style.opacity = '';
    if (!noAnim) {
      deckEl.classList.remove('enter');
      void deckEl.offsetWidth;
      deckEl.classList.add('enter');
    }
  }

  setTimeout(() => { busy = false; }, sec ? 700 : 300);
  cur = i;
  syncOvCur();
  pageNum.textContent = `${i + 1} / ${slides.length}`;
  updateSeg(slides[i], i);
  bar.style.width = `${((i + 1) / slides.length) * 100}%`;
  if (location.hash !== `#${i + 1}`) history.replaceState(null, '', `#${i + 1}`);
  notesBody.textContent = slides[i].notes || '（本页无备注）';
  document.title = `${slides[i].title || '赛博把脉'} · 汇报`;
}

const comp = () => deckEl.querySelector('.transitionBox')?.__comp;
const next = () => {
  const c = comp();
  if (c && c.advance()) return;
  if (!stepFrag(1)) go(cur + 1, 1);
};
const prev = () => { if (!stepFrag(-1)) go(cur - 1, -1); };

/* ---------------- 键盘 ---------------- */
let digits = '';
addEventListener('keydown', (e) => {
  const k = e.key;
  if (/^[0-9]$/.test(k)) { digits += k; return; }
  if (k === 'Enter' && digits) { go(+digits - 1); digits = ''; return; }
  digits = '';
  switch (k) {
    case 'ArrowRight': case ' ': case 'PageDown': next(); e.preventDefault(); break;
    case 'ArrowLeft': case 'PageUp': prev(); e.preventDefault(); break;
    case 'Home': go(0, -1); break;
    case 'End': go(slides.length - 1, 1); break;
    case 'g': case 'G': toggleOverview(); break;
    case 'n': case 'N': notesEl.classList.toggle('hidden'); break;
    case 'f': case 'F': document.fullscreenElement ? document.exitFullscreen() : document.documentElement.requestFullscreen(); break;
    case 'p': case 'P': window.print(); break;
    case '?': $('#help').classList.toggle('hidden'); break;
    case 'Escape': $('#help').classList.add('hidden'); toggleOverview(true); break;
  }
});

/* ---------------- 鼠标：单击 / 滚轮翻页 ---------------- */
function overlayOpen() {
  return ['#overview', '#help', '#locator'].some((sel) => {
    const n = $(sel);
    return n && !n.classList.contains('hidden');
  });
}
let wheelAcc = 0, wheelLock = 0, wheelTimer = 0;
addEventListener('click', (e) => {
  if (e.button !== 0) return;
  if (e.target.closest('a, button, .jump, #hud, #notes, #help, #overview, #locator, #ovBtn')) return;
  if (overlayOpen()) return;
  next();
});
addEventListener('wheel', (e) => {
  if (e.target.closest('#notes, #overview, #help, #locator')) return;
  if (overlayOpen()) return;
  e.preventDefault();
  /* 归一化：行模式 ×40、页模式 ×800，保证一格就是一格 */
  const unit = e.deltaMode === 1 ? 40 : (e.deltaMode === 2 ? 800 : 1);
  const dy = e.deltaY * unit;
  const now = performance.now();
  if (now < wheelLock) return;
  wheelAcc += dy;
  clearTimeout(wheelTimer);
  wheelTimer = setTimeout(() => { wheelAcc = 0; }, 300);
  if (Math.abs(wheelAcc) < 30) return;
  const dir = wheelAcc > 0 ? 1 : -1;
  wheelAcc = 0;
  wheelLock = now + 220;
  dir > 0 ? next() : prev();
}, { passive: false });

/* ---------------- 底部：本段（当天）剩余页数 ---------------- */
function updateSeg(s, i) {
  const box = $('#segProg'), bar = $('#segBar'), left = $('#segLeft');
  if (!box) return;
  if (typeof s.day !== 'number') { box.style.visibility = 'hidden'; left.textContent = ''; return; }
  box.style.visibility = 'visible';
  let a = i, b = i;
  while (a > 0 && slides[a - 1].day === s.day) a--;
  while (b < slides.length - 1 && slides[b + 1].day === s.day) b++;
  const total = b - a + 1;
  bar.style.width = `${((i - a + 1) / total) * 100}%`;
  left.textContent = b - i > 0 ? `还剩 ${b - i} 页` : '本节末页';
}

/* ---------------- 总览（按天×线） ---------------- */
const LINE_NAME = Object.fromEntries(LINES.map((l) => [l.id, l.name]));

function cellOf(s) {
  if (typeof s.day === 'number' && s.line) return { day: s.day, line: s.line };
  const tr = (s.blocks || []).find((b) => b.t === 'transition');
  if (tr && tr.focus) return { day: tr.focus.day, line: tr.focus.line };
  return null;
}

function sectionTitleOf(day, line) {
  const sec = slides.find((s) => {
    if (!isSectionPage(s)) return false;
    const c = cellOf(s);
    return c && c.day === day && c.line === line;
  });
  return sec ? sec.title || '' : '';
}

function buildIndex() {
  const idx = {};
  slides.forEach((s, i) => {
    const c = cellOf(s);
    if (!c || isSectionPage(s)) return;
    const k = `${c.day}:${c.line}`;
    (idx[k] || (idx[k] = [])).push(i);
  });
  return idx;
}

function groupOf(s, i) {
  const c = cellOf(s);
  if (c) return String(c.day);
  const first = slides.findIndex((x) => cellOf(x));
  return i < first ? 'open' : 'end';
}
function groupLabel(g) {
  return g === 'open' ? '开头' : g === 'end' ? '结尾' : `Day ${g}`;
}
function jumpDirect(i) {
  const ov = $('#overview');
  ov.classList.add('hidden');
  setOvBtn(false);
  go(i);
}
function pgButton(j) {
  const s = slides[j];
  const b = el('button', 'ovPage' + (j === cur ? ' cur' : ''));
  const no = s.no ? `<b>${esc(s.no)}</b>` : '';
  b.innerHTML = `${no}<span>${esc(s.title || s.slug)}</span>`;
  b.dataset.i = j;
  return b;
}
function setActiveChip(g) {
  document.querySelectorAll('.ovDayChip').forEach((b) => b.classList.toggle('cur', b.dataset.day === g));
}

function buildMatrixView() {
  const idx = buildIndex();
  const body = $('#ovBody');
  const curG = ovActiveGroup || groupOf(slides[cur] || {}, cur);
  ['open', ...DAYS.map(String), 'end'].forEach((g) => {
    const b = el('button', 'ovDayChip' + (g === curG ? ' cur' : ''), groupLabel(g));
    b.dataset.day = g;
    b.onclick = () => {
      ovActiveGroup = g;
      setActiveChip(g);
      body.querySelector(`[data-group="${g}"]`)?.scrollIntoView({ block: 'center', behavior: 'smooth' });
    };
    $('#ovDays').appendChild(b);
  });

  const openPages = slides.map((s, i) => i).filter((i) => !isSectionPage(slides[i]) && groupOf(slides[i], i) === 'open');
  if (openPages.length) {
    const row = el('div', 'ovStrip');
    row.dataset.group = 'open'; row.dataset.day = 'open';
    row.appendChild(el('div', 'ovStripHead', '开头'));
    const box = el('div', 'ovStripPages');
    openPages.forEach((j) => { const b = pgButton(j); b.onclick = () => jumpDirect(j); box.appendChild(b); });
    row.appendChild(box);
    body.appendChild(row);
  }

  DAYS.forEach((d) => {
    const total = LINES.reduce((n, l) => n + (idx[`${d}:${l.id}`] || []).length, 0);
    const row = el('div', 'ovDay' + (total ? '' : ' empty'));
    row.dataset.day = d;
    row.dataset.group = String(d);
    const head = el('div', 'ovDayHead');
    head.innerHTML = `<b>Day ${d}</b><span>${DAY_DATES[d] || ''}</span>`;
    const cells = el('div', 'ovCells');
    LINES.forEach((ln) => {
      const list = idx[`${d}:${ln.id}`] || [];
      const cell = el('div', 'ovCell ' + ln.id + (list.length ? '' : ' none'));
      const ch = el('div', 'ovCellHead');
      ch.innerHTML = `<i></i>${esc(ln.name)}${list.length ? `<em>${list.length}</em>` : ''}`;
      cell.appendChild(ch);
      if (!list.length) {
        cell.appendChild(el('span', 'ovEmpty', '—'));
      } else {
        list.forEach((j) => {
          const p = pgButton(j);
          p.onclick = () => jumpVia(j, d, ln.id);
          cell.appendChild(p);
        });
      }
      cells.appendChild(cell);
    });
    row.append(head, cells);
    body.appendChild(row);
  });

  const endPages = slides.map((s, i) => i).filter((i) => !isSectionPage(slides[i]) && groupOf(slides[i], i) === 'end');
  const endRow = el('div', 'ovStrip');
  endRow.dataset.group = 'end'; endRow.dataset.day = 'end';
  endRow.appendChild(el('div', 'ovStripHead', '结尾'));
  const endBox = el('div', 'ovStripPages');
  if (endPages.length) {
    endPages.forEach((j) => { const b = pgButton(j); b.onclick = () => jumpDirect(j); endBox.appendChild(b); });
  } else {
    endBox.appendChild(el('span', 'ovEmpty', '（待补：结论 / 三档规格）'));
  }
  endRow.appendChild(endBox);
  body.appendChild(endRow);
}

function buildListView() {
  const body = $('#ovBody');
  const wrap = el('div', 'ovList');
  let last = null;
  slides.forEach((s, i) => {
    if (isSectionPage(s)) return;
    const g = groupOf(s, i);
    if (g !== last) {
      last = g;
      const h = el('div', 'ovListDay');
      h.dataset.group = g;
      h.innerHTML = g === 'open' ? '开头' : g === 'end' ? '结尾' : `Day ${g} <span>${DAY_DATES[g] || ''}</span>`;
      wrap.appendChild(h);
    }
    const c = cellOf(s);
    const row = el('button', 'ovRow' + (i === cur ? ' cur' : ''));
    row.dataset.i = i;
    row.innerHTML = `<span class="abs">${i + 1}</span><span class="no">${esc(s.no || '')}</span><span class="t">${esc(s.title || s.slug)}</span>${c ? `<span class="l ${c.line}">${esc(LINE_NAME[c.line] || '')}</span>` : ''}`;
    row.onclick = () => (c ? jumpVia(i, c.day, c.line) : jumpDirect(i));
    wrap.appendChild(row);
  });
  body.appendChild(wrap);
}

function syncOvCur() {
  const ov = $('#overview');
  if (!ov || ov.classList.contains('hidden')) return;
  const g = groupOf(slides[cur] || {}, cur);
  ovActiveGroup = g;
  setActiveChip(g);
  document.querySelectorAll('#ovBody .cur').forEach((n) => n.classList.remove('cur'));
  document.querySelectorAll(`#ovBody [data-i="${cur}"]`).forEach((n) => n.classList.add('cur'));
}

let ovView = 'matrix';
let ovActiveGroup = null;
const OV_ICON = {
  grid: '<svg viewBox="0 0 16 16" width="14" height="14"><g fill="currentColor"><rect x="2" y="2" width="3.2" height="3.2" rx=".8"/><rect x="6.4" y="2" width="3.2" height="3.2" rx=".8"/><rect x="10.8" y="2" width="3.2" height="3.2" rx=".8"/><rect x="2" y="6.4" width="3.2" height="3.2" rx=".8"/><rect x="6.4" y="6.4" width="3.2" height="3.2" rx=".8"/><rect x="10.8" y="6.4" width="3.2" height="3.2" rx=".8"/><rect x="2" y="10.8" width="3.2" height="3.2" rx=".8"/><rect x="6.4" y="10.8" width="3.2" height="3.2" rx=".8"/><rect x="10.8" y="10.8" width="3.2" height="3.2" rx=".8"/></g></svg>',
  list: '<svg viewBox="0 0 16 16" width="14" height="14"><g fill="currentColor"><rect x="2" y="3" width="12" height="2" rx="1"/><rect x="2" y="7" width="12" height="2" rx="1"/><rect x="2" y="11" width="12" height="2" rx="1"/></g></svg>',
};

function renderOverview() {
  const body = $('#ovBody');
  body.innerHTML = '';
  $('#ovDays').innerHTML = '';
  $('#ovDays').style.display = ovView === 'matrix' ? '' : 'none';
  if (ovView === 'matrix') buildMatrixView(); else buildListView();
  if (ovActiveGroup) {
    const n = body.querySelector(`[data-group="${ovActiveGroup}"]`);
    if (n) n.scrollIntoView({ block: 'start' });
  }
  $('#ovState').innerHTML = `<i></i>当前：${ovView === 'matrix' ? '矩阵视图' : '列表视图'}`;
  const btn = $('#ovToggle');
  if (btn) btn.innerHTML = `<span class="ico">${ovView === 'matrix' ? OV_ICON.list : OV_ICON.grid}</span><span class="tx">切换为${ovView === 'matrix' ? '列表' : '矩阵'}视图</span>`;
}

function switchOverviewView() {
  const body = $('#ovBody');
  body.classList.add('switching');
  setTimeout(() => {
    ovView = ovView === 'matrix' ? 'list' : 'matrix';
    renderOverview();
    body.classList.remove('switching');
    $('#overview').scrollTop = 0;
  }, 170);
}

function setOvBtn(open) {
  const b = $('#ovBtn');
  if (!b) return;
  b.classList.toggle('is-open', open);
  b.innerHTML = open
    ? '<svg viewBox="0 0 16 16" width="15" height="15"><g fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M4 4l8 8M12 4l-8 8"/></g></svg><span>返回</span>'
    : '<svg viewBox="0 0 16 16" width="15" height="15"><g fill="currentColor"><rect x="2" y="2" width="3.2" height="3.2" rx=".8"/><rect x="6.4" y="2" width="3.2" height="3.2" rx=".8"/><rect x="10.8" y="2" width="3.2" height="3.2" rx=".8"/><rect x="2" y="6.4" width="3.2" height="3.2" rx=".8"/><rect x="6.4" y="6.4" width="3.2" height="3.2" rx=".8"/><rect x="10.8" y="6.4" width="3.2" height="3.2" rx=".8"/><rect x="2" y="10.8" width="3.2" height="3.2" rx=".8"/><rect x="6.4" y="10.8" width="3.2" height="3.2" rx=".8"/><rect x="10.8" y="10.8" width="3.2" height="3.2" rx=".8"/></g></svg><span>总览</span>';
  b.title = open ? '关闭总览（G）' : '总览（G）';
}

function toggleOverview(forceClose) {
  const ov = $('#overview');
  if (forceClose || !ov.classList.contains('hidden')) { ov.classList.add('hidden'); setOvBtn(false); return; }
  ovActiveGroup = groupOf(slides[cur] || {}, cur);
  renderOverview();
  ov.classList.remove('hidden');
  setOvBtn(true);
  ov.scrollTop = 0;
}

/* ---------------- 定位转场：点某页先放目录动画再跳 ---------------- */
function jumpVia(i, day, line) {
  const ov = $('#overview');
  ov.classList.add('hidden');
  setOvBtn(false);
  const loc = $('#locator');
  const inner = $('#locInner');
  inner.innerHTML = '';
  const box = el('div', 'transitionBox');
  box.style.width = '100%';
  box.style.height = '100%';
  inner.appendChild(box);
  loc.classList.remove('hidden');
  loc.style.opacity = '1';

  const idx = buildIndex();
  const list = (idx[`${day}:${line}`] || []).map((j) => ({
    n: slides[j].no || '',
    t: slides[j].title || slides[j].slug,
    cur: j === i,
  }));

  let done = false;
  /* 先把目标页渲染到定位层后面，再淡出定位层，避免露出上一页 */
  const safeGo = (j) => {
    if (busy) { setTimeout(() => safeGo(j), 80); return; }
    go(j);
  };
  const finish = () => {
    if (done) return;
    done = true;
    safeGo(i);
    requestAnimationFrame(() => {
      loc.style.transition = 'opacity .28s ease';
      loc.style.opacity = '0';
      setTimeout(() => {
        loc.classList.add('hidden');
        loc.style.transition = '';
        loc.style.opacity = '';
        box.innerHTML = '';
      }, 300);
    });
  };

  renderTransition(box, {
    focus: { day, line },
    section: sectionTitleOf(day, line),
    list, counts: COUNTS,
    autoplay: true, autoDelay: 420, arriveDelay: 1000,
    onArrive: finish,
  });
  setTimeout(finish, 4200);
}

/* ---------------- 计时（备注面板） ---------------- */
setInterval(() => {
  const elx = $('#clock');
  if (!elx) return;
  const s = Math.floor((performance.now() - startedAt) / 1000);
  elx.textContent = `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`;
}, 1000);

/* ---------------- 启动 ---------------- */
slides = await Promise.all(order.map(loadPage));
fit();
go(Math.max(0, (parseInt(location.hash.slice(1), 10) || 1) - 1), 1);

/* 内部跳转：[[页面id|文字]] */
document.addEventListener('click', (e) => {
  const a = e.target.closest('.jump');
  if (!a) return;
  e.preventDefault();
  const i = slides.findIndex((s) => s.id === a.dataset.go || s.slug === a.dataset.go);
  if (i >= 0) go(i);
});

/* 对外：按 id 跳转 */
window.gotoPage = (id) => {
  const i = slides.findIndex((s) => s.id === id || s.slug === id);
  if (i >= 0) go(i);
};
addEventListener('hashchange', () => {
  const i = (parseInt(location.hash.slice(1), 10) || 1) - 1;
  if (i !== cur) go(i, i > cur ? 1 : -1);
});

window.Deck = { go, next, prev, get index() { return cur; }, total: () => slides.length };

if (location.search.includes('ov=list')) { ovView = 'list'; setTimeout(() => toggleOverview(), 400); }
if (location.search.includes('ovtog')) setTimeout(() => document.querySelector('#ovToggle')?.click(), 1400);
if (location.search.includes('ovclose')) setTimeout(() => document.querySelector('#ovBtn')?.click(), 1400);

/* 调试：?click=N 合成 N 次单击；?wheel=N 合成 N 次滚轮 */
for (const kind of ['click', 'wheel']) {
  const pos = location.search.indexOf(kind + '=');
  if (pos < 0) continue;
  const n = parseInt(location.search.slice(pos + kind.length + 1), 10);
  if (!n) continue;
  let i = 0;
  const tick = () => {
    if (i++ >= n) return;
    const deck = document.querySelector('#deck');
    if (kind === 'click') deck.click();
    else deck.dispatchEvent(new WheelEvent('wheel', { deltaY: 120, bubbles: true, cancelable: true }));
    setTimeout(tick, 700);
  };
  setTimeout(tick, 900);
}

/* 调试：?ov=1 打开总览；?loc=<day>,<line> 播放定位转场并跳到该格第一页；?loc2=<day>,<line> 延迟 4.5s 再跳一次 */
if (location.search.includes('ov=1')) setTimeout(() => toggleOverview(), 400);
if (location.search.includes('loc=')) {
  const m = location.search.match(/loc=(\d+),(\w+)/);
  if (m) setTimeout(() => {
    const idx = buildIndex();
    const j = (idx[`${m[1]}:${m[2]}`] || [])[0];
    if (j != null) jumpVia(j, +m[1], m[2]);
  }, 400);
}
if (location.search.includes('loc2=')) {
  const m2 = location.search.match(/loc2=(\d+),(\w+)/);
  if (m2) setTimeout(() => {
    const idx = buildIndex();
    const j = (idx[`${m2[1]}:${m2[2]}`] || [])[0];
    if (j != null) jumpVia(j, +m2[1], m2[2]);
  }, 4500);
}

/* 调试：?auto=N 启动后自动前进 N 页（用于截取转场动画后的状态） */
if (location.search.includes('auto=')) {
  const m = location.search.match(/auto=(\d+)/);
  const n = m ? parseInt(m[1], 10) : 1;
  setTimeout(() => go(Math.min(slides.length - 1, cur + n)), 700);
}
