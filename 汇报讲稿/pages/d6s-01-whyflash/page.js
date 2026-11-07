export default {
  id: 'd6s-01',
  day: 6, line: 'demo', no: '01',
  kicker: '闪存',
  title: '蓝牙不适合传全档',

  notes: '1 kHz 原始数据只有 2 KB/s，但蓝牙还要带 100 Hz 波形、状态和补发，实测只有 9~11 KB/s，而且一断就丢。闪存 3 MB 能存 26 分钟，断电不丢、事后取。分工：蓝牙负责实时与状态，闪存负责完整留档。',
  css: 'page.css',
};
