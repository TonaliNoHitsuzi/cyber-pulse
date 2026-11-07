/* 图表与图形配置：以 JS 对象形式维护，页面用 {t:'chart'|'cycle', data:'键名'} 引用 */

const LOOP_LINES = [
  ['hw', '硬件', '决定 能力', '#1d4ed8'],
  ['algo', '算法', '定义 做法', '#ea580c'],
  ['exp', '实验', '提供 数据', '#0f766e'],
  ['org', '组织', '确保 运转', '#6d28d9'],
  ['sys', '系统', '构成 用途', '#0ea5e9'],
];

export const CHARTS = {};

export const CYCLES = {
  loop: {
    elements: [
      ...LOOP_LINES.map(([id, name, sub, color]) => ({
        data: { id, label: `${name} · ${sub}`, color },
      })),
      ...LOOP_LINES.map(([id, , , color], i) => {
        const next = LOOP_LINES[(i + 1) % LOOP_LINES.length][0];
        return { data: { id: `${id}-${next}`, source: id, target: next, color } };
      }),
    ],
    style: [
      { selector: 'node', style: {
        shape: 'round-rectangle',
        width: 178, height: 62,
        'background-color': '#ffffff',
        'border-width': 1.8,
        'border-color': 'data(color)',
        label: 'data(label)',
        color: 'data(color)',
        'font-size': 15,
        'font-weight': 700,
        'text-valign': 'center',
        'text-halign': 'center',
      } },
      { selector: 'edge', style: {
        width: 2.2,
        'line-color': 'data(color)',
        'target-arrow-color': 'data(color)',
        'target-arrow-shape': 'triangle',
        'arrow-scale': 1.5,
        'curve-style': 'bezier',
        'control-point-step-size': 60,
        opacity: 0.75,
      } },
    ],
    layout: { name: 'circle', radius: 168, padding: 10, avoidOverlap: true },
  },
};


/* 环形流程图（顺序/闭环），{t:'ring', data:'键名'} 引用 */
export const RINGS = {
  loop: {
    w: 650, h: 580, R: 222, thick: 66, blank: 11,
    segs: [
      { name: '硬件', sub: '决定 能力', color: '#1d4ed8' },
      { name: '算法', sub: '定义 做法', color: '#ea580c' },
      { name: '实验', sub: '提供 数据', color: '#0f766e' },
      { name: '组织', sub: '确保 运转', color: '#6d28d9' },
      { name: '系统', sub: '构成 用途', color: '#0ea5e9' },
    ],
  },
};
