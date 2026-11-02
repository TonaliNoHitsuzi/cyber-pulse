package com.nanshan.classroommonitor.ui

import android.Manifest
import android.app.Activity
import android.bluetooth.BluetoothDevice
import android.content.pm.PackageManager
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.content.ContextCompat
import com.nanshan.classroommonitor.dev.PulseSession

private val GoodGreen = Color(0xFF4ADE80)
private val WarnYellow = Color(0xFFF59E0B)
private val BadRed = Color(0xFFEF4444)
private val IdleGray = Color(0xFF64748B)

@Composable
fun ConnectScreen(nav: Navigator, sessionId: Long) {
    val ctx = LocalContext.current
    val session = remember { PulseSession }
    session.init(ctx)
    var status by remember { mutableStateOf("准备就绪") }
    var scanning by remember { mutableStateOf(false) }
    var foundDevice by remember { mutableStateOf<BluetoothDevice?>(null) }

    // 权限请求
    val permLauncher = rememberLauncherForActivityResult(ActivityResultContracts.RequestMultiplePermissions()) { grants ->
        if (grants.values.all { it }) {
            status = "权限已授权，可以扫描"
        } else {
            status = "缺少蓝牙权限"
        }
    }

    fun checkPerms(): Boolean {
        val perms = if (android.os.Build.VERSION.SDK_INT >= 31) {
            arrayOf(Manifest.permission.BLUETOOTH_SCAN, Manifest.permission.BLUETOOTH_CONNECT)
        } else {
            arrayOf(Manifest.permission.ACCESS_FINE_LOCATION)
        }
        val need = perms.filter { ContextCompat.checkSelfPermission(ctx, it) != PackageManager.PERMISSION_GRANTED }
        if (need.isNotEmpty()) {
            permLauncher.launch(need.toTypedArray()); return false
        }
        return true
    }

    LaunchedEffect(session.statusText) { status = session.statusText }
    // 连接成功后不自动跳转，等待用户点"进入测量"（明确的下一层入口）

    fun startScan() {
        if (!checkPerms()) return
        scanning = true
        status = "正在扫描 CYBER-PULSE..."
        session.connect()
        // 扫描结束（成功或超时）后由状态文本反馈
    }

    Column(
        modifier = Modifier.fillMaxSize().padding(32.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center
    ) {
        Text("赛博把脉", fontSize = 36.sp, fontWeight = FontWeight.Black)
        Spacer(Modifier.height(8.dp))
        Text("ESP32-C3 压电脉搏检测", fontSize = 14.sp, color = IdleGray)
        Spacer(Modifier.height(48.dp))

        // 状态卡
        Card(
            modifier = Modifier.fillMaxWidth(),
            shape = RoundedCornerShape(16.dp)
        ) {
            Column(Modifier.padding(24.dp), horizontalAlignment = Alignment.CenterHorizontally) {
                Text(status, fontSize = 16.sp, textAlign = TextAlign.Center)
                if (scanning) {
                    Spacer(Modifier.height(12.dp))
                    LinearProgressIndicator(Modifier.fillMaxWidth())
                }
            }
        }
        Spacer(Modifier.height(24.dp))

        // 扫描按钮
        Button(
            onClick = { startScan() },
            modifier = Modifier.fillMaxWidth().height(56.dp),
            enabled = !scanning
        ) {
            Text(if (scanning) "扫描中..." else "扫描设备", fontSize = 18.sp)
        }
        Spacer(Modifier.height(16.dp))

        LaunchedEffect(status) {
            if (!status.contains("扫描")) scanning = false
        }

        // 已连接 → 显示明确的"进入测量"按钮
        if (session.connected) {
            Spacer(Modifier.height(20.dp))
            Button(
                onClick = { nav.push(Screen.Measure(sessionId)) },
                modifier = Modifier.fillMaxWidth().height(56.dp),
                colors = ButtonDefaults.buttonColors(containerColor = GoodGreen)
            ) {
                Text("进入测量", fontSize = 18.sp, color = Color.Black)
            }
        }
    }
}
