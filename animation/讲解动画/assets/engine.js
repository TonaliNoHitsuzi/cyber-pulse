/* 赛博把脉 · 讲解动画通用引擎（无外部依赖） */
(function (global) {
  'use strict';
  const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
  const map = (v, a, b, c, d) => c + (d - c) * clamp((v - a) / (b - a), 0, 1);
  const ease = t => 1 - Math.pow(1 - clamp(t, 0, 1), 3);
  const easeIO = t => { t = clamp(t, 0, 1); return t < .5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2; };
  const lerp = (a, b, t) => a + (b - a) * t;

  const A = {
    clamp, map, ease, easeIO, lerp,
    rr(ctx, x, y, w, h, r) {
      r = Math.min(r, Math.abs(w) / 2, Math.abs(h) / 2);
      ctx.beginPath();
      ctx.moveTo(x + r, y); ctx.arcTo(x + w, y, x + w, y + h, r);
      ctx.arcTo(x + w, y + h, x, y + h, r); ctx.arcTo(x, y + h, x, y, r);
      ctx.arcTo(x, y, x + w, y, r); ctx.closePath();
    },
    text(ctx, s, x, y, o = {}) {
      ctx.save();
      ctx.font = (o.weight || 400) + ' ' + (o.size || 13) + 'px ' + (o.mono ? '"JetBrains Mono",Consolas,monospace' : (o.serif ? '"Iowan Old Style","Songti SC",serif' : '"Segoe UI","Microsoft YaHei",sans-serif'));
      ctx.fillStyle = o.color || '#e8f2ef';
      ctx.textAlign = o.align || 'left';
      ctx.textBaseline = o.baseline || 'alphabetic';
      if (o.glow) { ctx.shadowColor = o.glow; ctx.shadowBlur = o.blur || 10; }
      if (o.alpha != null) ctx.globalAlpha = o.alpha;
      ctx.fillText(s, x, y);
      const w = ctx.measureText(s).width;
      ctx.restore();
      return w;
    },
    line(ctx, x1, y1, x2, y2, o = {}) {
      ctx.save();
      ctx.strokeStyle = o.color || '#2a4046';
      ctx.lineWidth = o.width || 1;
      if (o.alpha != null) ctx.globalAlpha = o.alpha;
      if (o.dash) ctx.setLineDash(o.dash);
      if (o.glow) { ctx.shadowColor = o.glow; ctx.shadowBlur = o.blur || 8; }
      ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(x2, y2); ctx.stroke();
      ctx.restore();
    },
    path(ctx, pts, o = {}) {
      if (!pts || pts.length < 2) return;
      ctx.save();
      ctx.strokeStyle = o.color || '#62f0b6';
      ctx.lineWidth = o.width || 2;
      ctx.lineJoin = 'round'; ctx.lineCap = 'round';
      if (o.alpha != null) ctx.globalAlpha = o.alpha;
      if (o.dash) ctx.setLineDash(o.dash);
      if (o.glow) { ctx.shadowColor = o.glow; ctx.shadowBlur = o.blur || 12; }
      ctx.beginPath(); ctx.moveTo(pts[0][0], pts[0][1]);
      for (let i = 1; i < pts.length; i++) ctx.lineTo(pts[i][0], pts[i][1]);
      if (o.fill) {
        ctx.lineTo(pts[pts.length - 1][0], o.baseY);
        ctx.lineTo(pts[0][0], o.baseY);
        ctx.closePath();
        const g = ctx.createLinearGradient(0, o.topY || 0, 0, o.baseY);
        g.addColorStop(0, o.fill); g.addColorStop(1, 'transparent');
        ctx.fillStyle = g; ctx.fill();
      }
      ctx.stroke(); ctx.restore();
    },
    dot(ctx, x, y, r, color, glow) {
      ctx.save();
      ctx.fillStyle = color; ctx.shadowColor = glow || color; ctx.shadowBlur = glow ? 14 : 0;
      ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI * 2); ctx.fill(); ctx.restore();
    },
    grid(ctx, b, o = {}) {
      const step = o.step || 40;
      ctx.save();
      ctx.strokeStyle = o.color || 'rgba(45,70,75,.25)'; ctx.lineWidth = 1;
      ctx.beginPath();
      for (let x = b.x; x <= b.x + b.w + 1; x += step) { ctx.moveTo(x, b.y); ctx.lineTo(x, b.y + b.h); }
      for (let y = b.y; y <= b.y + b.h + 1; y += step) { ctx.moveTo(b.x, y); ctx.lineTo(b.x + b.w, y); }
      ctx.stroke(); ctx.restore();
    },
    axis(ctx, b, o = {}) {
      A.line(ctx, b.x, b.y + b.h, b.x + b.w, b.y + b.h, { color: o.color || '#2a4046' });
      A.line(ctx, b.x, b.y, b.x, b.y + b.h, { color: o.color || '#2a4046' });
      if (o.xlabel) A.text(ctx, o.xlabel, b.x + b.w, b.y + b.h + 18, { size: 10, mono: true, color: '#637875', align: 'right' });
      if (o.ylabel) A.text(ctx, o.ylabel, b.x - 8, b.y + 4, { size: 10, mono: true, color: '#637875', align: 'right' });
    },
    chip(ctx, x, y, label, color, bg) {
      ctx.save();
      ctx.font = '500 11px "JetBrains Mono",Consolas,monospace';
      const w = ctx.measureText(label).width + 16, h = 22;
      A.rr(ctx, x, y, w, h, 2);
      ctx.fillStyle = bg || 'rgba(98,240,182,.08)'; ctx.fill();
      ctx.strokeStyle = color || '#62f0b6'; ctx.globalAlpha = .55; ctx.stroke();
      ctx.globalAlpha = 1; ctx.fillStyle = color || '#62f0b6';
      ctx.textBaseline = 'middle'; ctx.fillText(label, x + 8, y + h / 2 + .5);
      ctx.restore();
      return w;
    },
    arrow(ctx, x1, y1, x2, y2, color, width) {
      const a = Math.atan2(y2 - y1, x2 - x1), L = 8;
      A.line(ctx, x1, y1, x2, y2, { color: color || '#57c8ff', width: width || 1.5 });
      ctx.save(); ctx.fillStyle = color || '#57c8ff';
      ctx.beginPath();
      ctx.moveTo(x2, y2);
      ctx.lineTo(x2 - L * Math.cos(a - .38), y2 - L * Math.sin(a - .38));
      ctx.lineTo(x2 - L * Math.cos(a + .38), y2 - L * Math.sin(a + .38));
      ctx.closePath(); ctx.fill(); ctx.restore();
    },
    tag(ctx, x, y, label, color) {
      A.text(ctx, label, x, y, { size: 10, mono: true, color: color || '#637875' });
    },
    fmt(v, n) { return (Math.round(v * Math.pow(10, n || 0)) / Math.pow(10, n || 0)).toFixed(n || 0); },
    envMax(y, half, smooth) {
      half = half || 7; smooth = smooth || 5;
      const n = y.length, m = new Array(n);
      for (let i = 0; i < n; i++) {
        let mx = 0;
        for (let j = Math.max(0, i - half); j <= Math.min(n - 1, i + half); j++) if (y[j] > mx) mx = y[j];
        m[i] = mx;
      }
      const out = new Array(n);
      for (let i = 0; i < n; i++) {
        let s = 0, c = 0;
        for (let j = Math.max(0, i - smooth); j <= Math.min(n - 1, i + smooth); j++) { s += m[j]; c++; }
        out[i] = s / c;
      }
      return out;
    }
  };
  global.A = A;

  class Deck {
    constructor(opt) {
      this.cv = document.getElementById('cv');
      this.ctx = this.cv.getContext('2d');
      this.steps = opt.steps || [];
      this.draw = opt.draw;
      this.state = opt.state || {};
      this.step = 0; this.t = 0; this.playing = false; this.speed = 1;
      this.last = performance.now();
      this.autoplay = opt.autoplay !== false;
      this.W = 0; this.H = 0; this.dpr = 1;
      this.els = {
        title: document.getElementById('step-title'),
        body: document.getElementById('step-body'),
        human: document.getElementById('step-human'),
        tag: document.getElementById('step-tag'),
        count: document.getElementById('step-count'),
        dots: document.getElementById('dots'),
        bar: document.querySelector('#timebar > i'),
        play: document.getElementById('btn-play'),
        prev: document.getElementById('btn-prev'),
        next: document.getElementById('btn-next'),
        reset: document.getElementById('btn-reset'),
        speed: document.getElementById('btn-speed')
      };
      this.buildDots(); this.bind(); this.resize();
      window.addEventListener('resize', () => this.resize());
      const q = new URLSearchParams(location.search);
      const start = q.has('step') ? Math.max(0, parseInt(q.get('step')) - 1) : 0;
      this.goto(start, true);
      if (q.has('t')) { this.t = Math.min(parseFloat(q.get('t')) || 0, this.duration()); this.playing = false; if (this.els.bar) this.els.bar.style.width = (this.t / this.duration() * 100) + '%'; this.updateControls(); }
      requestAnimationFrame(ts => this.loop(ts));
    }
    duration() { return (this.steps[this.step] && this.steps[this.step].dur) || 6; }
    buildDots() {
      if (!this.els.dots) return;
      this.els.dots.innerHTML = '';
      this.steps.forEach((s, i) => {
        const d = document.createElement('i');
        d.title = s.title || ('第 ' + (i + 1) + ' 步');
        d.onclick = () => this.goto(i, true);
        this.els.dots.appendChild(d);
      });
    }
    bind() {
      const e = this.els;
      if (e.play) e.play.onclick = () => this.toggle();
      if (e.prev) e.prev.onclick = () => this.goto(this.step - 1, true);
      if (e.next) e.next.onclick = () => this.goto(this.step + 1, true);
      if (e.reset) e.reset.onclick = () => this.goto(0, true);
      if (e.speed) e.speed.onclick = () => {
        this.speed = this.speed === 1 ? 0.5 : this.speed === 0.5 ? 2 : 1;
        e.speed.textContent = this.speed + '×';
      };
      this.cv.addEventListener('click', () => this.toggle());
      window.addEventListener('keydown', ev => {
        if (ev.code === 'Space') { ev.preventDefault(); this.toggle(); }
        else if (ev.code === 'ArrowRight') { ev.preventDefault(); this.goto(this.step + 1, true); }
        else if (ev.code === 'ArrowLeft') { ev.preventDefault(); this.goto(this.step - 1, true); }
        else if (ev.key === 'r' || ev.key === 'R') this.goto(0, true);
        else if (/^[1-9]$/.test(ev.key)) this.goto(parseInt(ev.key) - 1, true);
      });
    }
    resize() {
      const r = this.cv.getBoundingClientRect();
      this.dpr = Math.min(window.devicePixelRatio || 1, 2);
      this.W = Math.max(320, r.width); this.H = Math.max(200, r.height);
      this.cv.width = Math.round(this.W * this.dpr);
      this.cv.height = Math.round(this.H * this.dpr);
      this.ctx.setTransform(this.dpr, 0, 0, this.dpr, 0, 0);
    }
    goto(i, play) {
      i = clamp(i, 0, this.steps.length - 1);
      this.step = i; this.t = 0;
      const s = this.steps[i];
      if (s.onEnter) s.onEnter(this.state, this);
      this.paintText();
      this.playing = play !== false && this.autoplay;
      this.updateControls();
    }
    paintText() {
      const s = this.steps[this.step], e = this.els;
      if (e.title) e.title.innerHTML = s.title || '';
      if (e.body) e.body.innerHTML = s.body || '';
      if (e.human) { e.human.innerHTML = s.extra || ''; e.human.style.display = s.extra ? '' : 'none'; }
      if (e.tag) { e.tag.textContent = s.tag || '原理'; e.tag.style.display = s.tag === '' ? 'none' : ''; }
      if (e.count) e.count.textContent = 'STEP ' + String(this.step + 1).padStart(2, '0') + ' / ' + String(this.steps.length).padStart(2, '0');
      if (e.dots) [...e.dots.children].forEach((d, k) => { d.className = k === this.step ? 'on' : (k < this.step ? 'done' : ''); });
    }
    updateControls() {
      const e = this.els;
      if (e.play) { e.play.textContent = this.playing ? '暂停' : '播放'; e.play.classList.toggle('primary', !this.playing); }
      if (e.prev) e.prev.disabled = this.step === 0;
      if (e.next) e.next.disabled = this.step === this.steps.length - 1;
      if (this.els.dots) [...this.els.dots.children].forEach((d, k) => { d.className = k === this.step ? 'on' : (k < this.step ? 'done' : ''); });
    }
    toggle() { this.playing = !this.playing; if (this.playing && this.t >= this.duration()) this.t = 0; this.updateControls(); }
    loop(ts) {
      const dt = Math.min(.05, (ts - this.last) / 1000); this.last = ts;
      if (this.playing) {
        this.t += dt * this.speed;
        if (this.t >= this.duration()) { this.t = this.duration(); this.playing = false; this.updateControls(); }
        if (this.els.bar) this.els.bar.style.width = (this.t / this.duration() * 100) + '%';
      }
      const ctx = this.ctx;
      ctx.clearRect(0, 0, this.W, this.H);
      try { this.draw(ctx, this.W, this.H, this); }
      catch (err) { console.error(err); }
      requestAnimationFrame(t => this.loop(t));
    }
  }
  global.Deck = Deck;
})(window);
