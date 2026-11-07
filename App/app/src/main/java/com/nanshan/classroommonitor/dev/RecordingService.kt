package com.nanshan.classroommonitor.dev

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.os.Build
import android.os.IBinder
import com.nanshan.classroommonitor.MainActivity
import com.nanshan.classroommonitor.R

/**
 * 测量前台服务：保证 App 在后台/息屏时不被系统冻结，
 * BLE 连接与数据采集可持续（跨厂商通用做法）。
 */
class RecordingService : Service() {

    companion object {
        const val CHANNEL_ID = "pulse_recording"
        const val NOTIF_ID = 1001
        @Volatile var running = false

        fun start(ctx: Context) {
            val i = Intent(ctx, RecordingService::class.java)
            if (Build.VERSION.SDK_INT >= 26) ctx.startForegroundService(i) else ctx.startService(i)
        }

        fun stop(ctx: Context) {
            runCatching { ctx.stopService(Intent(ctx, RecordingService::class.java)) }
        }
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        createChannel()
        val open = PendingIntent.getActivity(
            this, 0, Intent(this, MainActivity::class.java),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
        )
        val n: Notification = Notification.Builder(this, CHANNEL_ID)
            .setContentTitle("赛博把脉 · 测量中")
            .setContentText("正在采集脉搏与运动数据，请勿关闭")
            .setSmallIcon(android.R.drawable.stat_sys_data_bluetooth)
            .setOngoing(true)
            .setContentIntent(open)
            .build()
        startForeground(NOTIF_ID, n)
        running = true
        DevState.addLog("前台服务已启动")
    }

    override fun onDestroy() {
        running = false
        DevState.addLog("前台服务已停止")
        super.onDestroy()
    }

    private fun createChannel() {
        if (Build.VERSION.SDK_INT >= 26) {
            val ch = NotificationChannel(
                CHANNEL_ID, "测量前台服务", NotificationManager.IMPORTANCE_LOW
            ).apply { setShowBadge(false) }
            (getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager)
                .createNotificationChannel(ch)
        }
    }
}
