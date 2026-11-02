package com.nanshan.classroommonitor.data

import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.hardware.Sensor
import android.hardware.SensorManager
import android.os.Build
import org.json.JSONObject

/**
 * 会话元数据：设备信息 + 电量 + 环境光（可获取则采集）
 * 用于后期分析时排除设备/环境因素，也便于和外部数据（天气等）关联。
 */
object DeviceMeta {
    fun collect(ctx: Context): JSONObject {
        val o = JSONObject()
        runCatching {
            o.put("device_model", Build.MODEL)
            o.put("device_brand", Build.BRAND)
            o.put("android", Build.VERSION.RELEASE)
            o.put("sdk", Build.VERSION.SDK_INT)
            o.put("timezone", java.util.TimeZone.getDefault().id)
            o.put("locale", java.util.Locale.getDefault().toString())
            o.put("ts_start", System.currentTimeMillis())
        }
        // 电量
        runCatching {
            val bm = ctx.getSystemService(Context.BATTERY_SERVICE) as android.os.BatteryManager
            o.put("battery_pct", bm.getIntProperty(android.os.BatteryManager.BATTERY_PROPERTY_CAPACITY))
        }
        // 环境光（有则采）
        runCatching {
            val sm = ctx.getSystemService(Context.SENSOR_SERVICE) as SensorManager
            val lux = sm.getDefaultSensor(Sensor.TYPE_LIGHT)
            o.put("has_light_sensor", lux != null)
        }
        return o
    }

    /** 读一次环境光（阻塞最多 300ms，失败返回 null） */
    fun readLux(ctx: Context): Float? {
        val sm = ctx.getSystemService(Context.SENSOR_SERVICE) as SensorManager
        val sensor = sm.getDefaultSensor(Sensor.TYPE_LIGHT) ?: return null
        val latch = java.util.concurrent.CountDownLatch(1)
        var v: Float? = null
        val l = object : android.hardware.SensorEventListener {
            override fun onSensorChanged(e: android.hardware.SensorEvent) {
                v = e.values[0]; latch.countDown()
            }
            override fun onAccuracyChanged(s: Sensor?, a: Int) {}
        }
        sm.registerListener(l, sensor, SensorManager.SENSOR_DELAY_FASTEST)
        try { latch.await(300, java.util.concurrent.TimeUnit.MILLISECONDS) } catch (_: Exception) {}
        sm.unregisterListener(l)
        return v
    }
}
