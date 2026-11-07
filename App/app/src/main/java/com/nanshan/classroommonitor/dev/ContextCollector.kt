package com.nanshan.classroommonitor.dev

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.hardware.Sensor
import android.hardware.SensorEvent
import android.hardware.SensorEventListener
import android.hardware.SensorManager
import android.location.Location
import android.location.LocationListener
import android.location.LocationManager
import android.os.Looper
import com.nanshan.classroommonitor.data.Repository
import com.nanshan.classroommonitor.data.SampleEntity
import com.nanshan.classroommonitor.data.SampleSource
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch
import org.json.JSONObject

/**
 * 环境与上下文采集（与心率分析相关的部分）：
 * - GPS 速度/位置/海拔（强度真值 + 天气关联）
 * - 气压（海拔变化，5s 一次）
 * - 旋转矢量（手机姿态：口袋/手持）
 * - BLE RSSI（链路质量，由 PulseBleClient 回调）
 * 全部以 samples 表通道形式落库，与心率共用墙钟。
 */
object ContextCollector {
    private var running = false
    private var sessionId = -1L
    private var ctx: Context? = null
    private val scope = CoroutineScope(Dispatchers.IO + SupervisorJob())

    private var sm: SensorManager? = null
    private var lm: LocationManager? = null
    private var lastLocTs = 0L
    private var lastPressTs = 0L
    private var lastOrientTs = 0L

    private fun save(channel: String, value: Double, quality: String = "CTX", extra: String? = null) {
        val id = sessionId
        if (id <= 0) return
        scope.launch {
            runCatching {
                Repository.get(ctx!!).insertSamples(listOf(
                    SampleEntity(sessionId = id, channel = channel, tsMillis = System.currentTimeMillis(),
                        value = value, quality = quality, extraJson = extra,
                        sourceTag = SampleSource.PHONE_SENSOR)
                ))
            }
        }
    }

    private val sensorListener = object : SensorEventListener {
        override fun onSensorChanged(e: SensorEvent) {
            if (!running) return
            val now = System.currentTimeMillis()
            when (e.sensor.type) {
                Sensor.TYPE_ROTATION_VECTOR -> {
                    if (now - lastOrientTs >= 2000) {
                        lastOrientTs = now
                        val r = FloatArray(9)
                        SensorManager.getRotationMatrixFromVector(r, e.values)
                        val orient = FloatArray(3)
                        SensorManager.getOrientation(r, orient)
                        val deg = orient.map { Math.toDegrees(it.toDouble()) }
                        save("ORIENT", deg[0], extra = JSONObject()
                            .put("yaw", deg[0]).put("pitch", deg[1]).put("roll", deg[2]).toString())
                    }
                }
            }
        }
        override fun onAccuracyChanged(s: Sensor?, a: Int) {}
    }

    private val locListener = object : LocationListener {
        override fun onLocationChanged(loc: Location) {
            if (!running) return
            val now = System.currentTimeMillis()
            if (now - lastLocTs < 3000) return
            lastLocTs = now
            save("GPS_SPEED", loc.speed.toDouble(), extra = JSONObject()
                .put("lat", loc.latitude).put("lon", loc.longitude)
                .put("acc", loc.accuracy).toString())
        }
        override fun onProviderEnabled(p: String) {}
        override fun onProviderDisabled(p: String) {}
        @Deprecated("Deprecated in Java")
        override fun onStatusChanged(p: String?, s: Int, e: android.os.Bundle?) {}
    }

    fun start(context: Context, sid: Long) {
        if (running) { sessionId = sid; return }
        ctx = context.applicationContext
        sessionId = sid
        running = true
        sm = context.getSystemService(Context.SENSOR_SERVICE) as SensorManager
        sm?.getDefaultSensor(Sensor.TYPE_ROTATION_VECTOR)?.let {
            sm?.registerListener(sensorListener, it, SensorManager.SENSOR_DELAY_UI)
        }
        // 定位：同时用 GPS（室外精确）和 NETWORK（室内 Wi-Fi/基站）
        runCatching {
            val fine = context.checkSelfPermission(Manifest.permission.ACCESS_FINE_LOCATION) ==
                PackageManager.PERMISSION_GRANTED
            val coarse = context.checkSelfPermission(Manifest.permission.ACCESS_COARSE_LOCATION) ==
                PackageManager.PERMISSION_GRANTED
            if (!fine && !coarse) {
                DevState.addLog("无定位权限，跳过")
            } else {
                lm = context.getSystemService(Context.LOCATION_SERVICE) as LocationManager
                var started = 0
                for (prov in listOf(LocationManager.GPS_PROVIDER,
                                    LocationManager.NETWORK_PROVIDER,
                                    LocationManager.PASSIVE_PROVIDER)) {
                    if (lm?.isProviderEnabled(prov) != true) continue
                    runCatching {
                        lm?.requestLocationUpdates(prov, 3000L, 0f, locListener, Looper.getMainLooper())
                        started++
                    }.onFailure { DevState.addLog("定位源 $prov 不可用: ${it.message}") }
                    // 先用最近一次已知位置兜底
                    runCatching {
                        lm?.getLastKnownLocation(prov)?.let { onLocation(it) }
                    }
                }
                DevState.addLog("定位已启动: $started 个源")
            }
        }.onFailure { DevState.addLog("定位初始化失败: ${it.message}") }
        DevState.addLog("上下文采集开始（姿态${if (lm != null) "/GPS" else ""}）")
    }

    private fun onLocation(loc: Location) {
        if (!running) return
        lastLocTs = System.currentTimeMillis()
        save("GPS_SPEED", loc.speed.toDouble(), extra = JSONObject()
            .put("lat", loc.latitude).put("lon", loc.longitude)
            .put("acc", loc.accuracy).toString())
    }

    /** BLE RSSI（由 PulseBleClient 每 5s 回调） */
    fun onRssi(rssi: Int) {
        if (!running) return
        save("RSSI", rssi.toDouble())
    }

    fun stop() {
        if (!running) return
        running = false
        runCatching { sm?.unregisterListener(sensorListener) }
        runCatching { lm?.removeUpdates(locListener) }
        DevState.addLog("上下文采集停止")
    }
}
