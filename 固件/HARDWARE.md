# 硬件接口备忘（后续程序必须兼容）

## OLED 屏幕（已验证）
- 型号：0.91 寸 SSD1306，**128×32**，I2C
- 地址：**0x3C**（启动时总线扫描自动确认）
- 引脚：**SDA=GPIO8，SCL=GPIO10**（GPIO8 为绑带脚且要求上电为高，I2C 上拉天然兼容；勿用 GPIO2/9/18/19/11-17）
- 供电：板载 3V3/GND（曾用外接 3.3V 方案：需共地、勿并电源，面包板方案已废弃）
- 驱动：工程内手写 `main/ssd1306.c/h` + `font8x8_basic.h`（无外部组件依赖）
  - 初始化：0xAE/D5 80/A8 1F(32行)/D3 00/40/8D 14/20 00/A1 C8/DA 02(32行)/81 CF/D9 F1/DB 40/A4 A6/AF
  - 刷屏：页寻址，每页 0xB0|page + 0x00/0x10 列定位 + 0x40 前缀数据
  - 若换 128×64 屏：main.c 里 `OLED_HEIGHT` 改 64（初始化自动切换 multiplex/compins）
- 挂进任何新固件：`#include "ssd1306.h"`，CMake SRCS 加 `ssd1306.c`，PRIV_REQUIRES 有 `esp_driver_i2c`

## 传感器（压电薄膜）
- 模块 S → GPIO0（ADC1_CH0，12dB 衰减，量程 0~2800mV）
- 模块 VCC → 3V3，GND → GND
- **偏置：内部双拉（45k‖45k≈22.5kΩ）**，必须在 `adc_continuous_start()` **之后**调用
  `gpio_set_pull_mode(GPIO_NUM_0, GPIO_PULLUP_PULLDOWN)` —— 顺序反了会被 ADC 驱动覆盖（v8 踩坑）
- **采样率上限纪律**：1kHz（10kHz 会激发高阻节点泵浦弛豫振荡，v9.3 踩坑）
- 膜片黑面（绝缘面）贴皮肤，金属面朝外

## 板卡
- ESP32-C3 SuperMini，COM6（原生 USB CDC），BOOT 键 = GPIO9
- 禁用引脚：GPIO18/19（USB）、GPIO11-17（flash）、GPIO2/9（绑带，9 已留按键）

## 上位机
- 引擎：`host_pulse.py`（单次 --dur）、`host_rounds.py`（多轮 --dur --pause）、`posthoc.py`（后验补偿）
- 串口 921600，timeout=0.05（长超时会造成断流假象）
- R 帧格式：`R,<seq>,<win_min>,<win_max>` 200行/s，seq 时基 5ms/行

## 传感器物理画像（Day2 实验定版）
- **固体耦合：极敏感**——指腹/±0.5cm偏移/手背/大腿/表带，任何实接触位置均可测得心率（峰幅中位恒定 63~65，BCG 全身传导机制，TE 白皮书/Emfit 商用产品/EMFi+PVDF 文献为产业先例）
- **空气声学：近乎失聪**——受控声源实验（-30~-8dB 全频段）响应≤噪声量级；近距出现的响应实为音箱→桌面→膜片的结构传导
- **流体路径结论**：声阻抗失配（空气 vs 致密膜 ~10³ 倍差），能量全反射
- **测量卫生**：勿与大声源共桌（结构串扰），空气声/说话/音乐无影响

## 面包板注意事项
- 830 孔长面包板的电源轨(+/-)在中点物理隔断，两侧不导通——桥接跳线必须加
- 排查方法：万用表蜂鸣档量同一轨两端

## SuperMini 实测引脚布局（以实物为准，2026-10-31 确认）
左列(USB朝上,从上到下): GPIO5, GPIO6, GPIO7, GPIO8, GPIO9, GPIO10, GPIO20, GPIO21
右列(从上到下): 5V, G, 3V3, GPIO4, GPIO3, GPIO2, GPIO1, GPIO0
注意：不同批次可能排列不同，接线前必须对照丝印确认


## COM6 消失的复现处理（2026-11-02 实战）
- 现象：串口列表里 COM6 消失，拔插 USB / 按 RST 均无效
- 根因：Windows 把板子 USB 复合设备标记为失效实例（含"设备描述符请求失败"幽灵记录），
  软件复位不会清 Windows 侧坏实例
- 修复（需管理员，会弹 UAC）：
  powershell -ExecutionPolicy Bypass -File "课程仓库/usbfix.ps1"
  （内部：pnputil /remove-device 删幽灵设备 + /scan-devices 重新枚举）
- 验证：Get-CimInstance Win32_SerialPort 应列出 COM6
