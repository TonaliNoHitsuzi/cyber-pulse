package com.nanshan.classroommonitor.dev

import android.content.Context
import android.hardware.Sensor
import android.hardware.SensorEvent
import android.hardware.SensorEventListener
import android.hardware.SensorManager
import com.nanshan.classroommonitor.data.ImuChunkEntity
import com.nanshan.classroommonitor.data.Repository
import com.nanshan.classroommonitor.data.SampleEntity
import com.nanshan.classroommonitor.data.SampleSource
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch
import java.nio.ByteBuffer
import java.nio.ByteOrder

/**
 * 手机 IMU 采集（原始数据 + 系统计步器）：
 * - 六轴原始值 50Hz，按秒成块：[dt_ms(2B) ax ay az gx gy gz] × n（各 ×100，m/s² 与 rad/s）
 * - 步态：直接用 Android 硬件计步器 TYPE_STEP_DETECTOR（系统级算法，不自己造轮子）
 *   每个步事件记一条 STEP 样本（墙钟时间戳）；TYPE_STEP_COUNTER 作为累计校验
 */
object ImuCollector {
    private const val TARGET_HZ = 50

    private var sm: SensorManager? = null
    private var running = false
    private var sessionId = -1L
    private var ctx: Context? = null
    private val scope = CoroutineScope(Dispatchers.IO + SupervisorJob())

    // 当前秒缓冲：[ax,ay,az,gx,gy,gz,dt_ms]
    private val samples = ArrayList<FloatArray>()
    private var chunkStart = 0L

    private var lastAcc = FloatArray(3)
    private var lastGyr = FloatArray(3)
    private var lastAccTs = 0L
    private var lastGyrTs = 0L

    private val listener = object : SensorEventListener {
        override fun onSensorChanged(e: SensorEvent) {
            if (!running) return
            val now = System.currentTimeMillis()
            when (e.sensor.type) {
                Sensor.TYPE_ACCELEROMETER -> {
                    System.arraycopy(e.values, 0, lastAcc, 0, 3)
                    lastAccTs = now
                }
                Sensor.TYPE_GYROSCOPE -> {
                    System.arraycopy(e.values, 0, lastGyr, 0, 3)
                    lastGyrTs = now
                }
                Sensor.TYPE_STEP_DETECTOR -> {
                    // 系统计步器：一次事件 = 一步
                    val id = sessionId
                    if (id > 0) {
                        scope.launch {
                            runCatching {
                                Repository.get(ctx!!).insertSamples(listOf(
                                    SampleEntity(sessionId = id, channel = "STEP",
                                        tsMillis = now, value = 1.0, quality = "SYS_STEP",
                                        sourceTag = SampleSource.PHONE_SENSOR)
                                ))
                            }
                        }
                    }
                    return
                }
                Sensor.TYPE_STEP_COUNTER -> {
                    val id = sessionId
                    val total = e.values[0]
                    if (id > 0) {
                        scope.launch {
                            runCatching {
                                Repository.get(ctx!!).insertSamples(listOf(
                                    SampleEntity(sessionId = id, channel = "STEP_TOTAL",
                                        tsMillis = now, value = total.toDouble(), quality = "SYS_STEP",
                                        sourceTag = SampleSource.PHONE_SENSOR)
                                ))
                            }
                        }
                    }
                    return
                }
            }
            // 六轴合成（两路都有新鲜数据，间隔 <50ms）
            if (lastAccTs > 0 && lastGyrTs > 0 && Math.abs(lastAccTs - lastGyrTs) < 50) {
                if (chunkStart == 0L) chunkStart = now
                samples.add(floatArrayOf(
                    lastAcc[0], lastAcc[1], lastAcc[2],
                    lastGyr[0], lastGyr[1], lastGyr[2],
                    (now - chunkStart).toFloat()))
                lastAccTs = 0; lastGyrTs = 0
                if (now - chunkStart >= 1000) flushChunk(now)
            }
        }
        override fun onAccuracyChanged(s: Sensor?, a: Int) {}
    }

    private fun flushChunk(now: Long) {
        val id = sessionId
        val n = samples.size
        if (id > 0 && n > 0) {
            val bb = ByteBuffer.allocate(n * 14).order(ByteOrder.LITTLE_ENDIAN)
            for (i in 0 until n) {
                val s = samples[i]
                bb.putShort(s[6].toInt().toShort())          // 每样本独立 dt
                bb.putShort((s[0] * 100).toInt().toShort())
                bb.putShort((s[1] * 100).toInt().toShort())
                bb.putShort((s[2] * 100).toInt().toShort())
                bb.putShort((s[3] * 100).toInt().toShort())
                bb.putShort((s[4] * 100).toInt().toShort())
                bb.putShort((s[5] * 100).toInt().toShort())
            }
            val ent = ImuChunkEntity(sessionId = id, startTs = chunkStart, n = n, data = bb.array())
            scope.launch { runCatching { Repository.get(ctx!!).insertImuChunks(listOf(ent)) } }
        }
        samples.clear(); chunkStart = 0L
    }

    fun start(context: Context, sid: Long) {
        if (running) { sessionId = sid; return }
        ctx = context.applicationContext
        sessionId = sid
        running = true
        samples.clear(); chunkStart = 0; lastAccTs = 0; lastGyrTs = 0
        sm = context.getSystemService(Context.SENSOR_SERVICE) as SensorManager
        val rate = 1_000_000 / TARGET_HZ
        sm?.getDefaultSensor(Sensor.TYPE_ACCELEROMETER)?.let { sm?.registerListener(listener, it, rate) }
        sm?.getDefaultSensor(Sensor.TYPE_GYROSCOPE)?.let { sm?.registerListener(listener, it, rate) }
        // 系统计步器（硬件算法，需 ACTIVITY_RECOGNITION 权限）
        val step = sm?.getDefaultSensor(Sensor.TYPE_STEP_DETECTOR)
        val total = sm?.getDefaultSensor(Sensor.TYPE_STEP_COUNTER)
        step?.let { sm?.registerListener(listener, it, SensorManager.SENSOR_DELAY_NORMAL) }
        total?.let { sm?.registerListener(listener, it, SensorManager.SENSOR_DELAY_NORMAL) }
        DevState.addLog("IMU 采集开始 (会话 #$sid) 计步器:${if (step != null) "有" else "无"}")
    }

    fun stop() {
        if (!running) return
        running = false
        runCatching { sm?.unregisterListener(listener) }
        if (samples.isNotEmpty() && sessionId > 0) flushChunk(System.currentTimeMillis())
        DevState.addLog("IMU 采集停止")
    }
}
