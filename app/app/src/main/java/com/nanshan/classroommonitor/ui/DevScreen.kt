package com.nanshan.classroommonitor.ui

import android.content.Context
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.nanshan.classroommonitor.data.ConfigStore
import com.nanshan.classroommonitor.dev.DevServer
import com.nanshan.classroommonitor.dev.DevState
import kotlinx.coroutines.delay

/** 服务单例持有（跨页面存活） */
object DevServerHolder {
    var server: DevServer? = null
    val running: Boolean get() = server?.wasStarted() == true

    private fun prefs(ctx: Context) = ctx.getSharedPreferences("pulse_dev", Context.MODE_PRIVATE)
    fun autoStartEnabled(ctx: Context) = prefs(ctx).getBoolean("auto_start", false)

    /** App 启动时恢复上次的开关状态 */
    fun restoreIfEnabled(ctx: Context) {
        if (autoStartEnabled(ctx) && !running) start(ctx)
    }

    fun start(ctx: Context): String? = runCatching {
        if (server?.wasStarted() == true) return null
        val s = DevServer(ctx.applicationContext)
        s.startWithMdns()
        server = s
        DevState.addLog("HTTP 服务已启动 :8080")
        prefs(ctx).edit().putBoolean("auto_start", true).apply()
        null
    }.getOrElse { "启动失败：${it.message}" }

    fun stop(ctx: Context) {
        runCatching { server?.stop() }
        server = null
        prefs(ctx).edit().putBoolean("auto_start", false).apply()
        DevState.addLog("HTTP 服务已停止")
    }
}

@Composable
fun DevScreen(nav: Navigator) {
    val ctx = LocalContext.current
    val configStore = remember { ConfigStore.get(ctx) }
    var running by remember { mutableStateOf(DevServerHolder.running) }
    var ip by remember { mutableStateOf<String?>(DevServer.localIp()) }
    var cfgText by remember { mutableStateOf(configStore.currentText()) }
    var msg by remember { mutableStateOf<String?>(null) }
    var live by remember { mutableStateOf("") }

    LaunchedEffect(Unit) {
        while (true) {
            live = "BPM ${DevState.bpm} · ${DevState.state} · p95 ${DevState.p95} · 样本 ${DevState.samples}"
            delay(1000)
        }
    }

    Column(
        Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp)
    ) {
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            Text("开发者", fontSize = 20.sp, fontWeight = FontWeight.Bold)
            OutlinedButton(onClick = { nav.pop() }) { Text("返回") }
        }

        Card(Modifier.fillMaxWidth()) {
            Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Text("HTTP 调试服务", fontWeight = FontWeight.Medium, fontSize = 15.sp)
                Text(
                    when {
                        running && ip != null -> "电脑浏览器打开：\nhttp://$ip:8080\n或 http://cyberpulse.local:8080（mDNS）"
                        running -> "服务已启动，但未获取到 WiFi IP（检查是否连上 WiFi）"
                        else -> "未启动。启动后电脑与手机连同一 WiFi，浏览器输入手机 IP:8080"
                    },
                    fontSize = 12.sp, color = MaterialTheme.colorScheme.onSurfaceVariant
                )
                OutlinedButton(onClick = {
                    val pm = ctx.getSystemService(android.content.Context.POWER_SERVICE) as android.os.PowerManager
                    val pkg = ctx.packageName
                    if (!pm.isIgnoringBatteryOptimizations(pkg)) {
                        runCatching {
                            ctx.startActivity(
                                android.content.Intent(
                                    android.provider.Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS,
                                    android.net.Uri.parse("package:$pkg")
                                ).addFlags(android.content.Intent.FLAG_ACTIVITY_NEW_TASK)
                            )
                        }.onFailure { msg = "请手动到设置里设省电策略为无限制" }
                    } else msg = "✓ 已在电池优化白名单"
                }) { Text("关闭电池优化") }
                Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    Button(onClick = {
                        if (running) {
                            DevServerHolder.stop(ctx)
                            running = false
                            msg = "已停止"
                        } else {
                            ip = DevServer.localIp()
                            val err = DevServerHolder.start(ctx)
                            running = DevServerHolder.running
                            msg = err ?: "已启动"
                        }
                    }) { Text(if (running) "停止服务" else "启动服务") }
                    OutlinedButton(onClick = { ip = DevServer.localIp() }) { Text("刷新 IP") }
                }
                Text(live, fontSize = 12.sp)
            }
        }

        Text("表单配置（正文字段 JSON，可被电脑 POST /config 覆盖）", fontSize = 13.sp, fontWeight = FontWeight.Medium)
        OutlinedTextField(
            value = cfgText,
            onValueChange = { cfgText = it },
            modifier = Modifier.fillMaxWidth().height(280.dp),
            textStyle = MaterialTheme.typography.bodySmall.copy(fontFamily = FontFamily.Monospace)
        )
        Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            Button(onClick = {
                val err = configStore.save(cfgText)
                msg = if (err == null) "✓ 配置已保存，新建测量页立即生效" else "✗ $err"
                if (err == null) cfgText = configStore.currentText()
            }) { Text("保存配置") }
            OutlinedButton(onClick = { cfgText = configStore.currentText(); msg = "已重新读取" }) {
                Text("重新读取")
            }
            OutlinedButton(onClick = {
                configStore.reset()
                cfgText = configStore.currentText()
                msg = "已恢复默认配置"
            }) { Text("恢复默认") }
        }
        msg?.let { Text(it, fontSize = 12.sp, color = MaterialTheme.colorScheme.primary) }

        Spacer(Modifier.height(8.dp))
        Text("事件日志", fontSize = 13.sp, fontWeight = FontWeight.Medium)
        Card(Modifier.fillMaxWidth()) {
            Text(
                DevState.log.takeLast(15).joinToString("\n").ifBlank { "（暂无）" },
                Modifier.padding(12.dp),
                fontSize = 10.sp, fontFamily = FontFamily.Monospace,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )
        }
        Spacer(Modifier.height(16.dp))
    }
}
