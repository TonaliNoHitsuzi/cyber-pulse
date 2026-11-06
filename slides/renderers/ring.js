/* 环形流程图：矩形左挖等腰三角补到右边 → 卷绕到圆环上 → 阵列 n 份。
   每个"路标"占 span-blank 度，尖头伸进下一个的缺口，缺口即留白。 */

export function renderRing(node, cfg) {
  if (!cfg) return;
  const W = cfg.w || 650, H = cfg.h || 580;
  const cx = W / 2, cy = H / 2;
  const R = cfg.R || 222;              // 外半径
  const thick = cfg.thick || 70;       // 环带宽度
  const r = R - thick;                 // 内半径
  const rm = (R + r) / 2;              // 中轴半径（缺口/尖头都在中轴上）
  const segs = cfg.segs || [];
  const n = segs.length || 1;
  const span = 360 / n;                // 每份 72°
  const blank = cfg.blank == null ? 8 : cfg.blank;  // 留白角度
  const theta = span - blank;          // 路标实体所占角度
  const a0 = -90 - theta / 2;          // 第一个路标的中点朝上
  const rad = (d) => (d * Math.PI) / 180;
  const P = (rr, ang) => [cx + rr * Math.cos(rad(ang)), cy + rr * Math.sin(rad(ang))];
  const f = (v) => (Math.round(v * 100) / 100).toString();

  const out = [];
  out.push(`<svg viewBox="0 0 ${W} ${H}" width="100%" height="100%" preserveAspectRatio="xMidYMid meet" xmlns="http://www.w3.org/2000/svg">`);
  out.push(`<defs><filter id="ringShadow" x="-20%" y="-20%" width="140%" height="140%"><feDropShadow dx="0" dy="3" stdDeviation="7" flood-color="#0f172a" flood-opacity=".12"/></filter></defs>`);
  out.push('<g filter="url(#ringShadow)">');

  segs.forEach((s, i) => {
    const a = a0 + i * span;           // 尾（缺口嘴）
    const b = a + theta;               // 头（尖头根）
    const pA = P(R, a), pB = P(R, b), qA = P(r, a), qB = P(r, b);
    const notch = P(rm, a + blank);    // 缺口顶点（向圆心方向收）
    const tip = P(rm, b + blank);      // 尖头顶点（伸进下一个缺口）

    const d = `M${f(pA[0])} ${f(pA[1])} A${R} ${R} 0 0 1 ${f(pB[0])} ${f(pB[1])} `
      + `L${f(tip[0])} ${f(tip[1])} L${f(qB[0])} ${f(qB[1])} `
      + `A${r} ${r} 0 0 0 ${f(qA[0])} ${f(qA[1])} L${f(notch[0])} ${f(notch[1])} Z`;
    out.push(`<path d="${d}" fill="${s.color}" opacity=".95"/>`);
  });
  out.push('</g>');

  // 引线与外圈标签
  segs.forEach((s, i) => {
    const mid = a0 + i * span + theta / 2;
    const [tx, ty] = P(R + 8, mid);
    const [ux, uy] = P(R + 20, mid);
    out.push(`<path d="M${f(tx)} ${f(ty)} L${f(ux)} ${f(uy)}" stroke="${s.color}" stroke-width="1.4" opacity=".45"/>`);

    const [lx, ly] = P(R + 36, mid);
    const c = Math.cos(rad(mid));
    const anchor = c > 0.3 ? 'start' : c < -0.3 ? 'end' : 'middle';
    out.push(`<text x="${f(lx)}" y="${f(ly + 4)}" text-anchor="${anchor}" `
      + `font-family="'Noto Sans SC','Microsoft YaHei UI',sans-serif" font-size="24" font-weight="700" fill="${s.color}">${s.name}</text>`);
    out.push(`<text x="${f(lx)}" y="${f(ly + 27)}" text-anchor="${anchor}" `
      + `font-family="'Noto Sans SC','Microsoft YaHei UI',sans-serif" font-size="13.5" fill="#94a3b8" letter-spacing="1">${s.sub}</text>`);
  });

  // 圆心注释
  out.push(`<text x="${cx}" y="${cy + 4}" text-anchor="middle" `
    + `font-family="Consolas,'Cascadia Mono',monospace" font-size="11.5" letter-spacing="4" fill="#c3cddb">闭环</text>`);

  out.push('</svg>');
  node.innerHTML = out.join('');
}
