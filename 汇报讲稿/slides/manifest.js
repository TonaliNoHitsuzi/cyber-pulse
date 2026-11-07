/**
 * 幻灯片清单
 * 每项：{ id, title, notes, render(el) }
 * render 在首次进入时调用，可以放图表、动画、绑定数据。
 */
export const slides = [
  {
    id: 'cover',
    title: '封面',
    notes: '开场：一句话说清我们在做什么——用一块 5 块钱的压电薄膜，做可穿戴脉搏检测。',
    render(el) {
      el.innerHTML = `
        <div class="kicker">单片机课程设计 · 第六组</div>
        <h1>赛博把脉</h1>
        <p style="font-size:clamp(17px,1.6vw,26px);max-width:62ch">
          ESP32-C3 + 压电薄膜的可穿戴脉搏检测系统
        </p>
        <div style="margin-top:auto;display:flex;gap:44px;align-items:flex-end">
          <div><div class="k" style="color:#4a6080;font-family:var(--mono);font-size:12px">心率精度</div>
               <div class="big green">±1<span style="font-size:.4em;color:#8ea3bd"> BPM</span></div></div>
          <div><div class="k" style="color:#4a6080;font-family:var(--mono);font-size:12px">采样率</div>
               <div class="big cyan">1k<span style="font-size:.4em;color:#8ea3bd"> Hz</span></div></div>
          <div><div class="k" style="color:#4a6080;font-family:var(--mono);font-size:12px">元件成本</div>
               <div class="big amber">¥58</div></div>
        </div>`;
    },
  },
  {
    id: 'agenda',
    title: '目录',
    notes: '四个部分：为什么做、怎么做、做到了什么、边界在哪。最后一部分是重点。',
    render(el) {
      el.innerHTML = `
        <div class="kicker">Outline</div>
        <h2>今天讲四件事</h2>
        <div class="grid2" style="margin-top:8px">
          <div class="card"><div class="k">01</div><h3>为什么做压电</h3>
            <p>光电容积脉搏波之外的另一条路</p></div>
          <div class="card"><div class="k">02</div><h3>怎么把信号变成心率</h3>
            <p>采样、检峰、质量门、跨设备链路</p></div>
          <div class="card"><div class="k">03</div><h3>做到了什么</h3>
            <p>静息 ±1 BPM，N 人 M 次对照验证</p></div>
          <div class="card hl"><div class="k">04</div><h3>边界在哪</h3>
            <p>运动场景为什么失效——机理与量化</p></div>
        </div>`;
    },
  },
  {
    id: 'placeholder',
    title: '（待填充）',
    notes: '内容下一轮讨论后填入。',
    render(el) {
      el.innerHTML = `
        <div class="kicker">Next</div>
        <h2>内容待填充</h2>
        <p>这个骨架已经能翻页、跳转、出总览、开备注、导出 PDF。</p>
        <ul>
          <li>按 <code>G</code> 看总览</li>
          <li>按 <code>N</code> 看备注</li>
          <li>按 <code>P</code> 导出 PDF</li>
        </ul>`;
    },
  },
];
