# 赛博把脉 · 安卓 App 改造需求单

> 基于"课堂监测（南山）"项目骨架，替换连接层为标准 BLE，适配压电脉搏传感器

## 一、保留不动的组件

| 组件 | 路径 | 说明 |
|---|---|---|
| Room 数据库 | `data/AppDatabase.kt` `Models.kt` `Repository.kt` | Session→Sample 存储链 |
| CSV 导出 | `data/CsvExporter.kt` | 直接复用 |
| 导航 | `ui/Nav.kt` | 页面路由 |
| 主题 | `ui/theme/Theme.kt` | 深色主题 |
| 后台采集 | `capture/CaptureService.kt` | 前台服务保活 |

## 二、需要替换的组件

### 1. 删除 `hi/` 包（华为 SDK 适配层）
全部删除，用标准 Android BLE API 替代。

### 2. 新建 `ble/PulseBleClient.kt`（核心新文件）

```kotlin
// 职责：扫描→连接→订阅通知→解析数据→回调
class PulseBleClient(private val context: Context) {
    // 扫描过滤：设备名 "CYBER-PULSE"
    // 服务 UUID: 0000FFE0-0000-1000-8000-00805F9B34FB
    // 通知特征 UUID: 0000FFE1-0000-1000-8000-00805F9B34FB
    // 数据格式: JSON一行，如 {"bpm":82,"state":"GOOD","p95":112,"beat":1}
    
    fun startScan(onFound: (BluetoothDevice) -> Unit)
    fun stopScan()
    fun connect(device: BluetoothDevice, onConnected: () -> Unit, onData: (PulseData) -> Unit, onDisconnected: () -> Unit)
    fun disconnect()
}

data class PulseData(
    val bpm: Int,       // 0=无信号
    val state: String,  // IDLE/VIB/WEAK/OVER/SRCH/GOOD
    val p95: Int,       // 信号幅度
    val beat: Boolean   // 本帧是否有搏动（用于心跳动画）
)
```

### 3. 修改 `ConnectScreen.kt`
- 删除华为五步链（权限/知情/登录/加入研究/设备连接）
- 改为：请求 BLE 权限 → 扫描 CYBER-PULSE → 显示信号强度 → 点击连接
- 连接成功后导航到测量页

### 4. 修改 `MeasureScreen.kt`
- 大号 BPM 数字显示（类似 OLED 布局：右侧大字 BPM，左侧状态+信号条）
- 心跳动画（beat=true 时闪一下/放大一下）
- 状态码映射：GOOD=绿色, WEAK=黄色, IDLE/VIB=灰色, OVER=红色
- 实时曲线（最近30秒BPM趋势，用 Compose Canvas 画）

### 5. 修改 `Models.kt`
```kotlin
// 新增通道
PIEZO("压电脉搏", "bpm", ChannelSource.PHONE)  // source改为PHONE因为走手机BLE
```

### 6. 修改 `capture/CaptureService.kt`
- 数据源从华为 SDK 改为 PulseBleClient 的回调
- 每秒存一条 Sample(timestamp, bpm, state, p95)

## 三、固件 BLE 协议（已实现）

```
服务 UUID:   0000FFE0-0000-1000-8000-00805F9B34FB
通知特征:    0000FFE1-0000-1000-8000-00805F9B34FB
发送频率:    每500ms一条
数据格式:    JSON单行
示例:        {"bpm":82,"state":"GOOD","p95":112,"beat":1}
             {"bpm":0,"state":"IDLE","p95":8,"beat":0}

状态码表:
  IDLE  = 悬空/无信号 (p95<40)
  VIB   = 悬空振荡   (p50<15 + 有峰)
  WEAK  = 弱耦合     (p95 40-55)
  OVER  = 过压       (中线≥2600 + p95<55)
  SRCH  = 搜索中     (有信号但BPM未锁定)
  GOOD  = 正常佩戴   (BPM稳定输出)
```

## 四、所需权限（AndroidManifest.xml）

```xml
<uses-permission android:name="android.permission.BLUETOOTH_SCAN" />
<uses-permission android:name="android.permission.BLUETOOTH_CONNECT" />
<uses-permission android:name="android.permission.ACCESS_FINE_LOCATION" />
<uses-permission android:name="android.permission.FOREGROUND_SERVICE" />
<uses-permission android:name="android.permission.FOREGROUND_SERVICE_CONNECTED_DEVICE" />
```

## 五、项目结构

```
code/pulse-app/          ← 新项目目录（从课堂监测复制改造）
├── app/src/main/java/com/pulse/
│   ├── MainActivity.kt
│   ├── ble/PulseBleClient.kt      ← 新建
│   ├── capture/CaptureService.kt   ← 修改数据源
│   ├── data/                       ← 基本不动
│   └── ui/
│       ├── ConnectScreen.kt        ← 重写
│       ├── MeasureScreen.kt        ← 重写
│       ├── SessionDetailScreen.kt  ← 微调
│       └── Nav.kt                  ← 微调
└── ...
```
