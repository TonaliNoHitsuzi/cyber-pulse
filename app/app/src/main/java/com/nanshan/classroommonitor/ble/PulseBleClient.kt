package com.nanshan.classroommonitor.ble

import android.annotation.SuppressLint
import android.bluetooth.*
import android.bluetooth.le.ScanCallback
import android.bluetooth.le.ScanFilter
import android.bluetooth.le.ScanResult
import android.bluetooth.le.ScanSettings
import android.content.Context
import android.os.Build
import android.os.ParcelUuid
import android.util.Log
import org.json.JSONObject
import java.util.UUID

data class PulseData(
    val bpm: Int,
    val state: String,
    val p95: Int,
    val beat: Boolean,
    val bpm2: Int = 0,
    val score: Float = 0f
) {
    val stateLabel: String get() = when(state) {
        "GOOD" -> "正常佩戴"
        "WEAK" -> "弱耦合"
        "IDLE" -> "悬空"
        "VIB"  -> "振荡"
        "OVER" -> "过压"
        "SRCH" -> "搜索中"
        else -> state
    }
    val stateColor: String get() = when(state) {
        "GOOD" -> "#4ADE80"
        "WEAK", "SRCH" -> "#F59E0B"
        "OVER" -> "#EF4444"
        else -> "#64748B"
    }
}

@SuppressLint("MissingPermission")
class PulseBleClient private constructor(private val context: Context) {

    companion object {
        @Volatile private var instance: PulseBleClient? = null
        fun get(ctx: Context): PulseBleClient =
            instance ?: synchronized(this) {
                instance ?: PulseBleClient(ctx.applicationContext).also { instance = it }
            }
        private const val TAG = "PulseBle"
        val SERVICE_UUID: UUID = UUID.fromString("0000ffe0-0000-1000-8000-00805f9b34fb")
        val CHAR_UUID: UUID = UUID.fromString("0000ffe1-0000-1000-8000-00805f9b34fb")
        /** 波形流: int16 LE × N，100Hz（每包 10 点 / 100ms） */
        val WAVE_UUID: UUID = UUID.fromString("0000ffe2-0000-1000-8000-00805f9b34fb")
        /** 断线补发: [start_ms int32][n uint16][int16 × n] */
        val REPLAY_UUID: UUID = UUID.fromString("0000ffe3-0000-1000-8000-00805f9b34fb")
        /** 补发请求（可写 4 字节 LE，0=整个缓存） */
        val REPLAY_CMD_UUID: UUID = UUID.fromString("0000ffe4-0000-1000-8000-00805f9b34fb")
        const val TARGET_MTU = 517
        const val DEVICE_NAME = "CYBER-PULSE"
    }

    private val btManager = context.getSystemService(Context.BLUETOOTH_SERVICE) as BluetoothManager
    private val btAdapter = btManager.adapter
    private var btGatt: BluetoothGatt? = null
    private var discoverRetry = 0
    private var scanRetries = 0
    @Volatile private var connecting = false
    private var replayCmdChr: BluetoothGattCharacteristic? = null
    private var scanning = false

    var onConnected: (() -> Unit)? = null
    var onDisconnected: (() -> Unit)? = null
    var onData: ((PulseData) -> Unit)? = null
    var onWave: ((List<Int>) -> Unit)? = null
    var onReplay: ((Long, List<Int>) -> Unit)? = null
    var onError: ((String) -> Unit)? = null
    var onRssi: ((Int) -> Unit)? = null
    /** 最近一次波形（开发者 HTTP 调试取用） */
    @Volatile var lastWave: List<Int> = emptyList()
    @Volatile var connectedState = false
    @Volatile var lastError: String? = null

    var onScanEvent: ((String) -> Unit)? = null

    private val scanCallback: ScanCallback = object : ScanCallback() {
        override fun onScanResult(callbackType: Int, result: ScanResult) {
            val rec = result.scanRecord
            val advName = rec?.deviceName
            val devName = runCatching { result.device.name }.getOrNull()
            val hasSvc = rec?.serviceUuids?.any { it.uuid == SERVICE_UUID } == true
            onScanEvent?.invoke("${result.device.address} name=${advName ?: devName} svc=$hasSvc rssi=${result.rssi}")
            if (advName == DEVICE_NAME || devName == DEVICE_NAME || hasSvc) {
                scanRetries = 0
                stopScan()
                onDeviceFound?.invoke(result.device)
            }
        }
        override fun onScanFailed(errorCode: Int) {
            scanning = false
            Log.w(TAG, "扫描失败 code=$errorCode")
            if (errorCode == 1 && scanRetries < 2) {   // ALREADY_STARTED → 稍等重试
                scanRetries++
                android.os.Handler(android.os.Looper.getMainLooper()).postDelayed({
                    runCatching {
                        btAdapter?.bluetoothLeScanner?.stopScan(scanCallback)
                        Thread.sleep(300)
                        startScanInner()
                    }
                }, 400)
            } else {
                onError?.invoke("扫描失败 code=$errorCode")
            }
        }
        override fun onBatchScanResults(results: MutableList<ScanResult>?) {
            results?.forEach { onScanResult(ScanSettings.CALLBACK_TYPE_ALL_MATCHES, it) }
        }
    }

    var onDeviceFound: ((BluetoothDevice) -> Unit)? = null

    fun startScan() {
        if (scanning) return
        try {
            // 先无条件停掉可能残留的扫描（否则 Android 返回 code=1 ALREADY_STARTED）
            runCatching { btAdapter?.bluetoothLeScanner?.stopScan(scanCallback) }
            Thread.sleep(200)
            startScanInner()
        } catch (e: SecurityException) {
            scanning = false
            lastError = "缺少蓝牙权限，请在手机上先手动扫描一次授权"
            onError?.invoke(lastError!!)
        } catch (e: Exception) {
            scanning = false
            lastError = "扫描异常: ${e.message}"
            onError?.invoke(lastError!!)
        }
    }

    private fun startScanInner() {
        scanning = true
        val scanner = btAdapter?.bluetoothLeScanner ?: run {
            onError?.invoke("蓝牙不可用"); return
        }
        val settings = ScanSettings.Builder()
            .setScanMode(ScanSettings.SCAN_MODE_LOW_LATENCY)
            .setReportDelay(0)
            .build()
        scanner.startScan(null, settings, scanCallback)
        Log.i(TAG, "开始扫描 $DEVICE_NAME")
    }

    fun stopScan() {
        if (!scanning) return
        scanning = false
        btAdapter?.bluetoothLeScanner?.stopScan(scanCallback)
    }

    fun connect(device: BluetoothDevice) {
        if (connecting) { Log.w(TAG, "连接进行中，忽略重复请求"); return }
        connecting = true
        stopScan()
        runCatching { btGatt?.disconnect(); btGatt?.close() }
        btGatt = null
        discoverRetry = 0
        android.os.Handler(android.os.Looper.getMainLooper()).postDelayed({
            if (connecting && !connectedState) {
                Log.w(TAG, "连接超时，复位")
                connecting = false
                forceReset()
            }
        }, 15000)
        try {
            btGatt = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
                device.connectGatt(context, false, gattCallback, BluetoothDevice.TRANSPORT_LE)
            } else {
                device.connectGatt(context, false, gattCallback)
            }
        } catch (e: SecurityException) {
            onError?.invoke("缺少蓝牙连接权限")
        }
    }

    /** 强制复位：清掉可能僵尸的 GATT 与状态 */
    fun forceReset() {
        runCatching { btGatt?.disconnect() }
        runCatching { btGatt?.close() }
        btGatt = null
        connectedState = false
        connecting = false
        discoverRetry = 0
        runCatching { stopScan() }
    }

    /** 请求读一次 RSSI（异步回调 onReadRemoteRssi） */
    fun readRssi() { runCatching { btGatt?.readRemoteRssi() } }

    fun disconnect() {
        btGatt?.disconnect()
        btGatt?.close()
        btGatt = null
    }

    val isConnected: Boolean get() = btGatt != null

    private val gattCallback = object : BluetoothGattCallback() {
        private fun stale(gatt: BluetoothGatt) = (btGatt !== gatt)

        override fun onConnectionStateChange(gatt: BluetoothGatt, status: Int, newState: Int) {
            if (stale(gatt) && newState != BluetoothProfile.STATE_DISCONNECTED) {
                Log.w(TAG, "忽略过期 GATT 回调 newState=$newState"); return
            }
            when (newState) {
                BluetoothProfile.STATE_CONNECTED -> {
                    connecting = false
                    Log.i(TAG, "已连接，开始服务发现（MTU 在发现完成后再协商）")
                    gatt.discoverServices()
                }
                BluetoothProfile.STATE_DISCONNECTED -> {
                    Log.i(TAG, "已断开")
                    connecting = false
                    if (!stale(gatt)) { btGatt = null }
                    runCatching { gatt.close() }
                    connectedState = false
                    onDisconnected?.invoke()
                }
            }
        }

        override fun onServicesDiscovered(gatt: BluetoothGatt, status: Int) {
            if (stale(gatt)) return
            val svc = if (status == BluetoothGatt.GATT_SUCCESS) gatt.getService(SERVICE_UUID) else null
            if (svc == null) {
                if (discoverRetry < 2) {
                    discoverRetry++
                    Log.w(TAG, "服务发现不完整(status=$status, services=${gatt.services.size})，第 $discoverRetry 次重试")
                    android.os.Handler(android.os.Looper.getMainLooper()).postDelayed({
                        runCatching { gatt.discoverServices() }
                    }, 400)
                    return
                }
                onError?.invoke("找不到脉搏服务（已重试，主动断开）")
                runCatching { gatt.disconnect(); gatt.close() }
                btGatt = null
                connectedState = false
                discoverRetry = 0
                return
            }
            discoverRetry = 0
            val chr = svc.getCharacteristic(CHAR_UUID) ?: run {
                onError?.invoke("找不到通知特征"); return
            }
            // 订阅通知（FFE1 JSON + FFE2 波形）
            subscribe(gatt, chr)
            svc.getCharacteristic(WAVE_UUID)?.let { subscribe(gatt, it) }
            svc.getCharacteristic(REPLAY_UUID)?.let { subscribe(gatt, it) }
            replayCmdChr = svc.getCharacteristic(REPLAY_CMD_UUID)
            runCatching { gatt.requestMtu(TARGET_MTU) }
            Log.i(TAG, "已订阅脉搏通知 + 波形流（services=${gatt.services.size}）")
            connectedState = true
            onConnected?.invoke()
        }

        override fun onCharacteristicChanged(gatt: BluetoothGatt, characteristic: BluetoothGattCharacteristic) {
            handleChr(characteristic.uuid, characteristic.value ?: return)
        }

        // Android 13+ 新API
        override fun onCharacteristicChanged(gatt: BluetoothGatt, characteristic: android.bluetooth.BluetoothGattCharacteristic, value: ByteArray) {
            handleChr(characteristic.uuid, value)
        }

        override fun onMtuChanged(gatt: BluetoothGatt, mtu: Int, status: Int) {
            Log.i(TAG, "MTU=$mtu")
        }

        override fun onReadRemoteRssi(gatt: BluetoothGatt, rssi: Int, status: Int) {
            if (status == BluetoothGatt.GATT_SUCCESS) onRssi?.invoke(rssi)
        }
    }

    private fun subscribe(gatt: BluetoothGatt, chr: BluetoothGattCharacteristic) {
        gatt.setCharacteristicNotification(chr, true)
        chr.getDescriptor(UUID.fromString("00002902-0000-1000-8000-00805f9b34fb"))?.let {
            it.value = BluetoothGattDescriptor.ENABLE_NOTIFICATION_VALUE
            gatt.writeDescriptor(it)
        }
    }

    private fun handleChr(uuid: UUID, value: ByteArray) {
        when (uuid) {
            CHAR_UUID -> parseData(value.toString(Charsets.UTF_8))
            WAVE_UUID -> parseWave(value)
            REPLAY_UUID -> parseReplay(value)
        }
    }

    /** 发送文本命令到板子（"C:" 前缀） */
    fun sendCommand(cmd: String): Boolean {
        val gatt = btGatt ?: return false
        val chr = replayCmdChr ?: return false
        val bytes = ("C:" + cmd).toByteArray(Charsets.UTF_8)
        return runCatching {
            if (Build.VERSION.SDK_INT >= 33) {
                gatt.writeCharacteristic(chr, bytes, BluetoothGattCharacteristic.WRITE_TYPE_DEFAULT) ==
                    BluetoothStatusCodes.SUCCESS
            } else {
                @Suppress("DEPRECATION")
                chr.value = bytes
                @Suppress("DEPRECATION")
                gatt.writeCharacteristic(chr)
            }
        }.getOrDefault(false)
    }

    /** 请求补发：sinceBoardMs=0 表示整个缓存 */
    fun requestReplay(sinceBoardMs: Long = 0L) {
        val gatt = btGatt ?: return
        val chr = replayCmdChr ?: return
        val b = java.nio.ByteBuffer.allocate(4).order(java.nio.ByteOrder.LITTLE_ENDIAN)
            .putInt(sinceBoardMs.toInt()).array()
        runCatching {
            if (Build.VERSION.SDK_INT >= 33) {
                gatt.writeCharacteristic(chr, b, BluetoothGattCharacteristic.WRITE_TYPE_DEFAULT)
            } else {
                @Suppress("DEPRECATION")
                chr.value = b
                @Suppress("DEPRECATION")
                gatt.writeCharacteristic(chr)
            }
        }
    }

    private fun parseReplay(bytes: ByteArray) {
        if (bytes.size < 8) return
        val start = java.nio.ByteBuffer.wrap(bytes, 0, 4).order(java.nio.ByteOrder.LITTLE_ENDIAN).int.toLong()
        val n = java.nio.ByteBuffer.wrap(bytes, 4, 2).order(java.nio.ByteOrder.LITTLE_ENDIAN).short.toInt()
        if (n <= 0 || bytes.size < 6 + n * 2) return
        val list = ArrayList<Int>(n)
        for (i in 0 until n) {
            val lo = bytes[6 + 2 * i].toInt() and 0xFF
            val hi = bytes[7 + 2 * i].toInt()
            list.add((hi shl 8) or lo)
        }
        onReplay?.invoke(start, list)
    }

    private fun parseWave(bytes: ByteArray) {
        val n = bytes.size / 2
        if (n == 0) return
        val list = ArrayList<Int>(n)
        for (i in 0 until n) {
            val lo = bytes[2 * i].toInt() and 0xFF
            val hi = bytes[2 * i + 1].toInt()
            list.add((hi shl 8) or lo)
        }
        lastWave = list
        onWave?.invoke(list)
    }

    private fun parseData(json: String) {
        try {
            val obj = JSONObject(json)
            val data = PulseData(
                bpm = obj.optInt("bpm", 0),
                state = obj.optString("state", "IDLE"),
                p95 = obj.optInt("p95", 0),
                beat = obj.optInt("beat", 0) == 1,
                bpm2 = obj.optInt("bpm2", 0),
                score = obj.optDouble("sc", 0.0).toFloat()
            )
            onData?.invoke(data)
        } catch (e: Exception) {
            Log.w(TAG, "JSON解析失败: $json")
        }
    }
}
