/* 全局时间×线 网格：目录页、转场、总览共用同一份数据 */
export const DAYS = [1, 2, 3, 4, 5, 6, 7];

export const DAY_DATES = {
  1: '10/29', 2: '10/31', 3: '11/01', 4: '11/02', 5: '11/03',
  6: '11/04', 7: '11/05',
};

export const LINES = [
  { id: 'hw', name: '硬件' },
  { id: 'algo', name: '算法' },
  { id: 'exp', name: '实验' },
  { id: 'org', name: '组织' },
  { id: 'demo', name: '系统' },
];

/* 每个交点的事件数（用于大小暗示，差异刻意收敛） */
export const COUNTS = {
  '1:hw': 4, '1:algo': 3,
  '2:hw': 5, '2:algo': 4, '2:exp': 1, '2:org': 2,
  '3:hw': 3, '3:algo': 3, '3:exp': 1, '3:org': 1, '3:demo': 3,
  '4:algo': 7, '4:org': 2, '4:demo': 2,
  '5:hw': 6, '5:algo': 8, '5:exp': 2, '5:org': 1, '5:demo': 1,
  '6:hw': 2, '6:algo': 2, '6:exp': 3, '6:org': 2, '6:demo': 2,
  '7:hw': 3, '7:exp': 7, '7:org': 1, '7:demo': 2,
};

export const LINE_COLOR = {
  hw: '#1d4ed8', algo: '#ea580c', exp: '#0f766e', org: '#6d28d9', demo: '#0ea5e9',
};
