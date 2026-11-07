export default {
  id: 'd6s-02',
  day: 6, line: 'demo', no: '02',
  kicker: '文件格式',
  title: '每秒一个时间戳',
  notes: '文件头 16 B（CPLS/版本/采样率/起始毫秒/任务号），之后每秒一块：4 B 时间戳 + 2 B 样本数 + 1000 个 int16。块内用采样序号，误差锁在 1 秒内；块间隔异常就能发现丢块。开销 6/2006 ≈ 0.3%。',
  css: 'page.css',
};
