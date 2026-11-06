# 赛博把脉 · Cyber Pulse

ESP32-C3 + 压电薄膜的**可穿戴脉搏检测手套**（单片机课程作业）。

心电之外的选择：用压电薄膜把"血管搏动"变成电压波形，ADC 1kHz 采样、实时峰值检测、BLE 推送到安卓 App 记录与导出。

> **使用声明**：本仓库仅供课程小组内部共享与评审使用，**未附带任何开源许可证**（即未授予复制、修改、分发等权利）。任务结束后仓库将转为私有或删除。

---

## 目录结构

```
firmware/     ESP-IDF 固件（ESP32-C3 SuperMini）
  main.c         主逻辑：采样/峰值检测/质量门/BLE/OLED
  ssd1306.c/h    OLED 驱动（128x32，ASCII 字库）
  HARDWARE.md    接线规范、传感器画像、踩坑记录
  CMakeLists.txt / sdkconfig.defaults

app/          安卓 App（Kotlin + Jetpack Compose）
  app/src/       源码：BLE 客户端、会话状态机、采集、Room、导出
  赛博把脉-v2.0.0-debug.apk   可直接安装的调试包

tools/        上位机 / 分析脚本（Python）
  host_rounds.py     多轮对照采集（串口）
  analyze_troika.py  TROIKA 式谱峰跟踪（跑步心率解算）
  sim_*.py           算法仿真与验证

animation/    原理讲解动画（HTML，浏览器直接打开 index.html）
slides/       课程汇报网页讲稿（117 页，静态站，index.html）

hardware/     实物照片与系统拓扑图

docs/         每日总结、迭代记录、交接文档、汇报稿

data/logs/    实验原始数据（串口波形、标定记录、对照实验）
```

---

## 硬件

| 器件 | 型号 / 规格 | 接 ESP32-C3 |
|---|---|---|
| 主控 | ESP32-C3 SuperMini | — |
| 传感器 | 压电薄膜（LDT0-028K 类） | S → GPIO0（ADC1_CH0，12dB）|
| 显示 | OLED 0.91" 128×32 SSD1306 | SDA=GPIO8, SCL=GPIO10, 0x3C |
| 灯环 | WS2812 16 珠 | DIN=GPIO5 |
| 按键 | 轻触开关 | GPIO4（内部上拉，按下=GND）|
| 电源 | 3×AAA 电池盒（4.5V）| → 5V 脚 |

> SuperMini 引脚：左列(USB朝上) GPIO5,6,7,8,9,10,20,21；右列 5V,G,3V3,GPIO4,3,2,1,0。
> 禁用：18/19(USB)、11-17(flash)、GPIO2/9。

## 固件要点

- ADC 连续采样 **1kHz**（10kHz 会激发 ADC 泵浦振荡）
- 每 5 样本取窗口极值，扣除慢速基线 EMA，超阈值记为搏动峰
- **最小峰间距 350ms** 抑制重搏波与噪声
- **质量门**（p50/p95 滞回）+ **间隔 CV 门**（≤0.12）+ 冷启动保护
- 时间戳用**采样序号**换算，免疫主循环卡顿
- BLE 服务 FFE0：FFE1 JSON 实时值 / FFE2 波形流 / FFE3 历史补发 / FFE4 命令

## App 要点

单线流程：首页 → 表单 → 连接 → 进入测量 → 倒计时 → 采集 → 退出即结束落档。
测量期间前台服务常驻；权限进入时一次性申请；支持波形补发补录与 CSV 导出。

## 编译

```powershell
# 固件（ESP-IDF v5.4.1）
& D:\Espressif\frameworks\esp-idf-v5.4.1\export.ps1
idf.py build
idf.py -p COM6 flash

# App（JDK 21 + Gradle 8.9）
JAVA_HOME="C:/Program Files/Java/jdk-21" ./gradlew assembleDebug
```

## 已知限制

- 跑步场景心率存在 ±10% 级别的系统偏差（隔峰配对），趋势可用，绝对精度待改进
- 需要静息段做基线/锁定
- 传感器贴合度直接影响信号质量

## 文档索引

| 文档 | 内容 |
|---|---|
| `docs/Day4-工作总结.md` | 最新进展：时基修正、CV 门、跑步数据分析、App 产品化 |
| `docs/D3-增量记录-交付包之后.md` | 附 1~12 详细迭代 |
| `docs/跑步模式-心率跟踪设计.md` | 运动场景算法设计（PLL / 模板匹配 / 贝叶斯融合）|
| `docs/交接文档.md` | 完整状态交接（硬件/BLE/命令/环境）|
| `docs/交接-天气数据关联任务.md` | 可独立派发的子任务规格 |
| `firmware/HARDWARE.md` | 接线与传感器物理定论 |
