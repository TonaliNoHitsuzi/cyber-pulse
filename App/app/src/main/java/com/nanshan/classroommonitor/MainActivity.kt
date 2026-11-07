package com.nanshan.classroommonitor

import android.os.Bundle
import android.Manifest
import android.content.pm.PackageManager
import android.os.Build
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.runtime.LaunchedEffect
import androidx.core.content.ContextCompat
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import androidx.activity.ComponentActivity
import androidx.activity.compose.BackHandler
import androidx.activity.compose.setContent
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import com.nanshan.classroommonitor.ui.ConnectScreen
import com.nanshan.classroommonitor.ui.DevScreen
import com.nanshan.classroommonitor.ui.HomeScreen
import com.nanshan.classroommonitor.ui.MeasureScreen
import com.nanshan.classroommonitor.ui.Navigator
import com.nanshan.classroommonitor.ui.NewSessionScreen
import com.nanshan.classroommonitor.ui.Screen
import com.nanshan.classroommonitor.ui.SessionDetailScreen
import com.nanshan.classroommonitor.ui.theme.ClassroomTheme

class MainActivity : ComponentActivity() {
    private val coroutineScope = CoroutineScope(SupervisorJob() + Dispatchers.Main)
    override fun onResume() {
        super.onResume()
        // 回到前台时请求补发（兜底：冻结/丢通知时补回缺口；重复补发由唯一索引去重）
        runCatching {
            val ps = com.nanshan.classroommonitor.dev.PulseSession
            // 回前台先给 1.5s：链路可能一直活着，只是数据回调被冻结暂停
            coroutineScope.launch {
                delay(1500)
                if (ps.verifyConnection()) {
                    ps.requestReplay()
                } else {
                    ps.connect()
                }
            }
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        runCatching { com.nanshan.classroommonitor.ui.DevServerHolder.start(applicationContext) }
        // 单线流程：把上次异常退出残留的"采集中"会话收尾
        runCatching {
            kotlinx.coroutines.CoroutineScope(kotlinx.coroutines.Dispatchers.IO).launch {
                com.nanshan.classroommonitor.data.Repository.get(applicationContext).closeOrphanSessions()
            }
        }  // dev 构建：启动即开调试服务
        setContent {
            ClassroomTheme { AppRoot() }
        }
    }
}

@Composable
fun AppRoot() {
    val ctx = androidx.compose.ui.platform.LocalContext.current
    // 进入 App 一次性申请全部运行时权限（业界常见做法）
    val permLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions()
    ) { }
    LaunchedEffect(Unit) {
        val need = ArrayList<String>()
        if (Build.VERSION.SDK_INT >= 31) {
            listOf(Manifest.permission.BLUETOOTH_SCAN, Manifest.permission.BLUETOOTH_CONNECT)
                .forEach { if (ContextCompat.checkSelfPermission(ctx, it) != PackageManager.PERMISSION_GRANTED) need.add(it) }
        } else {
            if (ContextCompat.checkSelfPermission(ctx, Manifest.permission.ACCESS_FINE_LOCATION) != PackageManager.PERMISSION_GRANTED)
                need.add(Manifest.permission.ACCESS_FINE_LOCATION)
        }
        if (Build.VERSION.SDK_INT >= 29 &&
            ContextCompat.checkSelfPermission(ctx, Manifest.permission.ACTIVITY_RECOGNITION) != PackageManager.PERMISSION_GRANTED)
            need.add(Manifest.permission.ACTIVITY_RECOGNITION)
        if (ContextCompat.checkSelfPermission(ctx, Manifest.permission.ACCESS_FINE_LOCATION) != PackageManager.PERMISSION_GRANTED)
            need.add(Manifest.permission.ACCESS_FINE_LOCATION)
        if (Build.VERSION.SDK_INT >= 33 &&
            ContextCompat.checkSelfPermission(ctx, Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED)
            need.add(Manifest.permission.POST_NOTIFICATIONS)
        if (need.isNotEmpty()) permLauncher.launch(need.toTypedArray())
    }

    val nav = remember { Navigator() }
    BackHandler(enabled = nav.canPop.value) { nav.pop() }
    when (val s = nav.current) {
        is Screen.Home -> HomeScreen(nav)
        is Screen.NewSession -> NewSessionScreen(nav)
        is Screen.Connect -> ConnectScreen(nav, s.sessionId)
        is Screen.Measure -> MeasureScreen(nav, s.sessionId)
        is Screen.SessionDetail -> SessionDetailScreen(nav, s.sessionId)
        is Screen.Dev -> DevScreen(nav)
    }
}
