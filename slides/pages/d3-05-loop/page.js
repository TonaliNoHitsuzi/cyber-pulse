export default {
  id: 'd3-05',
  day: 3, line: 'hw', no: '05',
  kicker: '主循环',
  title: '屏幕为什么慢半拍',
  notes: '三个探针全部正常，唯独主循环滞后 55ms。根因是蓝牙通知在主循环里同步发送。修复：入队 + 独立任务。落点：能不能被打断，取决于数据怎么进来。',
  css: 'page.css',
};
