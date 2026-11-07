/**
 * DAG 渲染器（卡片式节点）
 * 数据：
 * { nodes:[{id,label,day,state:'done'|'cur'|'next'|'idle', pos?}],
 *   edges:[{from,to,label,type:'deps'|'leads'|'link'}],
 *   compact:false }
 */
export function renderDag(container, data) {
  const compact = !!data.compact;
  const W = Math.max(container.clientWidth || 0, 600);
  const H = compact ? 150 : Math.max(container.clientHeight || 0, 480);

  const nodes = (data.nodes || []).map((n) => ({ ...n }));
  const edges = data.edges || [];
  const NW = compact ? 0 : 210;      // 节点宽
  const NH = compact ? 0 : 62;       // 节点高

  // 布局：横向均分
  const n = nodes.length;
  nodes.forEach((node, i) => {
    if (!node.pos) {
      node.pos = {
        x: (W / (n + 1)) * (i + 1),
        y: H / 2 + (node.dy || 0),
      };
    }
  });

  const byId = Object.fromEntries(nodes.map((x) => [x.id, x]));
  const NS = 'http://www.w3.org/2000/svg';
  const svg = document.createElementNS(NS, 'svg');
  svg.setAttribute('width', W);
  svg.setAttribute('height', H);
  svg.style.display = 'block';
  svg.style.overflow = 'visible';

  const COLOR = {
    done: '#94a3b8', cur: '#1d4ed8', next: '#ea580c', idle: '#cbd5e1',
  };
  const EDGE = { deps: '#94a3b8', leads: '#ea580c', link: '#cbd5e1' };
  const EDGE_LABEL = { deps: '依赖', leads: '通向', link: '关联' };

  // ---------- 边 ----------
  edges.forEach((e) => {
    const a = byId[e.from], b = byId[e.to];
    if (!a || !b) return;

    const x1 = a.pos.x + (compact ? 0 : NW / 2);
    const y1 = a.pos.y;
    const x2 = b.pos.x - (compact ? 0 : NW / 2);
    const y2 = b.pos.y;

    const midX = (x1 + x2) / 2;
    const path = document.createElementNS(NS, 'path');
    path.setAttribute('d', `M${x1},${y1} C${midX},${y1} ${midX},${y2} ${x2},${y2}`);
    path.setAttribute('fill', 'none');
    path.setAttribute('stroke', EDGE[e.type] || EDGE.deps);
    path.setAttribute('stroke-width', compact ? 1.2 : 2.5);
    path.setAttribute('stroke-dasharray', e.type === 'link' ? '6 6' : 'none');
    path.setAttribute('opacity', a.state === 'idle' && b.state === 'idle' ? '.5' : '1');
    svg.appendChild(path);

    // 箭头
    const ang = Math.atan2(y2 - y1, x2 - x1);
    const s = compact ? 4 : 8;
    const ax = x2 - Math.cos(ang) * 2;
    const ay = y2 - Math.sin(ang) * 2;
    const arrow = document.createElementNS(NS, 'polygon');
    arrow.setAttribute('points',
      `${ax},${ay} ` +
      `${ax - s * Math.cos(ang - 0.45)},${ay - s * Math.sin(ang - 0.45)} ` +
      `${ax - s * Math.cos(ang + 0.45)},${ay - s * Math.sin(ang + 0.45)}`);
    arrow.setAttribute('fill', EDGE[e.type] || EDGE.deps);
    svg.appendChild(arrow);

    if (!compact) {
      const t = document.createElementNS(NS, 'text');
      t.setAttribute('x', midX);
      t.setAttribute('y', (y1 + y2) / 2 - 10);
      t.setAttribute('text-anchor', 'middle');
      t.setAttribute('font-size', '15');
      t.setAttribute('fill', EDGE[e.type] || '#94a3b8');
      t.textContent = e.label || EDGE_LABEL[e.type] || '';
      svg.appendChild(t);
    }
  });

  // ---------- 节点 ----------
  nodes.forEach((nd) => {
    const c = COLOR[nd.state] || COLOR.idle;
    const g = document.createElementNS(NS, 'g');

    if (compact) {
      const circle = document.createElementNS(NS, 'circle');
      circle.setAttribute('cx', nd.pos.x);
      circle.setAttribute('cy', nd.pos.y);
      circle.setAttribute('r', 7);
      circle.setAttribute('fill', nd.state === 'cur' ? c : '#fff');
      circle.setAttribute('stroke', c);
      circle.setAttribute('stroke-width', 2);
      g.appendChild(circle);
    } else {
      const rect = document.createElementNS(NS, 'rect');
      rect.setAttribute('x', nd.pos.x - NW / 2);
      rect.setAttribute('y', nd.pos.y - NH / 2);
      rect.setAttribute('width', NW);
      rect.setAttribute('height', NH);
      rect.setAttribute('rx', 14);
      rect.setAttribute('fill', nd.state === 'cur' ? '#eef4ff' : '#ffffff');
      rect.setAttribute('stroke', c);
      rect.setAttribute('stroke-width', nd.state === 'cur' ? 2.5 : 1.5);
      g.appendChild(rect);

      if (nd.day) {
        const d = document.createElementNS(NS, 'text');
        d.setAttribute('x', nd.pos.x);
        d.setAttribute('y', nd.pos.y - 10);
        d.setAttribute('text-anchor', 'middle');
        d.setAttribute('font-size', '13');
        d.setAttribute('fill', '#94a3b8');
        d.textContent = nd.day;
        g.appendChild(d);
      }

      const t = document.createElementNS(NS, 'text');
      t.setAttribute('x', nd.pos.x);
      t.setAttribute('y', nd.pos.y + 16);
      t.setAttribute('text-anchor', 'middle');
      t.setAttribute('font-size', '19');
      t.setAttribute('font-weight', nd.state === 'cur' ? '700' : '500');
      t.setAttribute('fill', nd.state === 'cur' ? '#0f172a' : '#475569');
      t.textContent = nd.label;
      g.appendChild(t);
    }
    svg.appendChild(g);
  });

  container.innerHTML = '';
  container.appendChild(svg);
  container.style.height = H + 'px';
}
