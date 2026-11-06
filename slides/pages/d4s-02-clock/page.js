export default {
  id: 'd4s-02',
  day: 4, line: 'demo', no: '02',
  kicker: '时钟',
  title: '多端系统，时间基准只能有一个',
  notes: '补发链路三个 bug：连上 1.6 秒被判断链（补发回调没刷新 lastDataTs）、UI 帧溢出（停止时没清会话号）、波形时间偏 82~492 秒（App 用到达时间）。修复：设备每帧带板载毫秒，连接时锚定一次，所有数据统一用这个偏移。',
  css: 'page.css',
};
