package com.nanshan.classroommonitor.ui

import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.platform.LocalView
import android.view.WindowManager
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.nanshan.classroommonitor.dev.PulseSession
import kotlinx.coroutines.delay

private val GoodGreen = Color(0xFF4ADE80)
private val WarnYellow = Color(0xFFF59E0B)
private val BadRed = Color(0xFFEF4444)
private val IdleGray = Color(0xFF64748B)

@Composable
fun MeasureScreen(nav: Navigator, sessionId: Long) {
    val ctx = LocalContext.current
    val lifecycleOwner = androidx.lifecycle.compose.LocalLifecycleOwner.current
    val view = LocalView.current
    DisposableEffect(Unit) {
        val w = (view.context as? android.app.Activity)?.window
        w?.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        onDispose { w?.clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON) }
    }
    PulseSession.init(ctx)
    // 三阶段：0=等待开始 1=倒计时 2=测量中
    var stage by remember { mutableIntStateOf(0) }
    var countdown by remember { mutableIntStateOf(3) }
    // 倒计时逻辑
    LaunchedEffect(stage) {
        if (stage == 1) {
            countdown = 3
            while (countdown > 0) {
                delay(1000)
                countdown--
            }
            PulseSession.startRecording(sessionId)
            stage = 2
        }
    }
    // 退出页面（含系统返回）→ 结束并落档
    androidx.activity.compose.BackHandler(enabled = stage != 0) {
        if (stage == 2) PulseSession.stopRecording()
        PulseSession.disconnect()
        nav.popToHome()
    }
    DisposableEffect(Unit) {
        onDispose {
            // 页面被销毁时若仍在测量，按"退出即结束"处理
            if (stage == 2) PulseSession.stopRecording()
        }
    }

    var mode by remember { mutableStateOf(0) }   // 0=老方法 1=新方法 2=对照
    val pulse = PulseSession.latest
    val shownBpm = when (mode) {
        1 -> pulse.bpm2
        2 -> pulse.bpm
        else -> pulse.bpm
    }
    val wave = PulseSession.wave
    val connected = PulseSession.connected
    val recording = PulseSession.recording
    val sampleCount = PulseSession.samples
    var elapsed by remember { mutableStateOf(0) }
    LaunchedEffect(PulseSession.recording) {
        while (true) {
            delay(1000)
            if (PulseSession.recording) elapsed++
        }
    }
    val mm = elapsed / 60
    val ss = elapsed % 60

    // ---- 开始前界面（等待开始 / 倒计时）----
    if (stage != 2) {
        Column(
            Modifier.fillMaxSize().padding(24.dp),
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                Text("赛博把脉", fontSize = 18.sp, fontWeight = FontWeight.Bold)
                Text(
                    if (connected) "设备已连接" else "设备未连接",
                    fontSize = 12.sp, color = if (connected) GoodGreen else BadRed
                )
            }
            Spacer(Modifier.weight(1f))
            if (stage == 0) {
                Text("准备就绪", fontSize = 32.sp, fontWeight = FontWeight.Black)
                Spacer(Modifier.height(12.dp))
                Text(
                    "请让拇指压紧传感器\n准备好后点击开始",
                    fontSize = 14.sp, color = IdleGray, textAlign = TextAlign.Center
                )
                Spacer(Modifier.height(40.dp))
                Button(
                    onClick = { if (connected) stage = 1 },
                    enabled = connected,
                    modifier = Modifier.fillMaxWidth().height(64.dp)
                ) { Text(if (connected) "开始测量" else "等待设备连接", fontSize = 20.sp) }
            } else {
                Text("$countdown", fontSize = 96.sp, fontWeight = FontWeight.Black, color = GoodGreen)
                Text("即将开始…", fontSize = 16.sp, color = IdleGray)
            }
            Spacer(Modifier.weight(1f))
        }
        return
    }

    val beatScale by animateFloatAsState(
        targetValue = if (pulse.beat) 1.10f else 1.0f,
        animationSpec = tween(140), label = "beat"
    )
    val stateColor = when (pulse.state) {
        "GOOD" -> GoodGreen
        "WEAK", "SRCH" -> WarnYellow
        "OVER" -> BadRed
        else -> IdleGray
    }

    Column(
        Modifier.fillMaxSize().padding(horizontal = 20.dp, vertical = 16.dp),
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        Row(
            Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically
        ) {
            Text("赛博把脉", fontSize = 18.sp, fontWeight = FontWeight.Bold)
            Text(
                "${mm}:${"%02d".format(ss)}",
                fontSize = 14.sp, color = IdleGray,
                modifier = Modifier.padding(start = 8.dp)
            )
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Surface(color = if (connected) GoodGreen else BadRed, shape = RoundedCornerShape(10.dp)) {
                    Text(if (connected) "已连接" else "断开",
                        Modifier.padding(horizontal = 10.dp, vertical = 4.dp),
                        color = Color.Black, fontSize = 11.sp)
                }
                Surface(color = if (recording) WarnYellow else IdleGray, shape = RoundedCornerShape(10.dp)) {
                    Text(if (recording) "记录中 $sampleCount" else "已暂停",
                        Modifier.padding(horizontal = 10.dp, vertical = 4.dp),
                        color = Color.Black, fontSize = 11.sp)
                }
            }
        }

        Spacer(Modifier.height(6.dp))

        // 测量模式切换（便于现场对照实时性）
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            listOf("老方法", "新方法", "对照").forEachIndexed { idx, label ->
                FilterChip(
                    selected = mode == idx,
                    onClick = { mode = idx },
                    label = { Text(label, fontSize = 12.sp) }
                )
            }
        }

        Spacer(Modifier.height(4.dp))

        Box(Modifier.size(170.dp), contentAlignment = Alignment.Center) {
            Canvas(Modifier.size(170.dp * beatScale)) {
                drawCircle(stateColor.copy(alpha = 0.12f), size.minDimension / 2, style = Stroke(4.dp.toPx()))
                drawCircle(stateColor.copy(alpha = 0.25f), size.minDimension / 2.4f, style = Stroke(2.dp.toPx()))
            }
            Column(horizontalAlignment = Alignment.CenterHorizontally) {
                Text(
                    if (shownBpm > 0) "$shownBpm" else "---",
                    fontSize = 68.sp, fontWeight = FontWeight.Black, color = stateColor
                )
                Text("BPM", fontSize = 13.sp, color = IdleGray)
                if (mode == 2) {
                    Text(
                        "新法 ${if (pulse.bpm2 > 0) "${pulse.bpm2}" else "--"} · 相似度 ${"%.2f".format(pulse.score)}",
                        fontSize = 11.sp, color = IdleGray
                    )
                } else if (mode == 1) {
                    Text("相似度 ${"%.2f".format(pulse.score)}", fontSize = 11.sp, color = IdleGray)
                }
            }
        }

        Spacer(Modifier.height(4.dp))

        Surface(
            color = stateColor.copy(alpha = 0.15f), shape = RoundedCornerShape(12.dp),
            modifier = Modifier.fillMaxWidth()
        ) {
            Text(
                "${pulse.stateLabel}   ·   信号 p95 ${pulse.p95}",
                Modifier.padding(vertical = 8.dp), textAlign = TextAlign.Center,
                color = stateColor, fontSize = 14.sp, fontWeight = FontWeight.Medium
            )
        }

        Spacer(Modifier.height(12.dp))

        Card(Modifier.fillMaxWidth()) {
            Column(Modifier.padding(12.dp)) {
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                    Text("实时波形", fontSize = 13.sp, fontWeight = FontWeight.Medium)
                    Text("100Hz · ${wave.size} 点", fontSize = 11.sp, color = IdleGray)
                }
                Spacer(Modifier.height(6.dp))
                WaveformChart(
                    samples = wave,
                    color = if (pulse.state == "GOOD") GoodGreen else stateColor,
                    modifier = Modifier.fillMaxWidth().height(150.dp)
                )
            }
        }

        Spacer(Modifier.weight(1f))

        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            OutlinedButton(
                onClick = {
                    if (recording) PulseSession.pauseRecording()
                    else PulseSession.startRecording(PulseSession.sessionId)
                },
                modifier = Modifier.weight(1f)
            ) { Text(if (recording) "暂停记录" else "继续记录") }
            Button(
                onClick = {
                    PulseSession.stopRecording()
                    PulseSession.disconnect()
                    nav.popToHome()
                },
                modifier = Modifier.weight(1f)
            ) { Text("结束并保存") }
        }
    }
}

@Composable
private fun WaveformChart(
    samples: List<Int>,
    color: Color,
    modifier: Modifier = Modifier
) {
    Canvas(modifier) {
        val w = size.width
        val h = size.height
        if (samples.size < 4) {
            drawLine(
                IdleGray.copy(alpha = 0.3f),
                Offset(0f, h / 2), Offset(w, h / 2), strokeWidth = 1.dp.toPx()
            )
            return@Canvas
        }

        val stride = (samples.size / 250).coerceAtLeast(1)
        val pts = ArrayList<Float>(samples.size / stride + 2)
        var i = 0
        while (i < samples.size) {
            pts.add(samples[i].toFloat()); i += stride
        }
        if ((samples.size - 1) % stride != 0) pts.add(samples.last().toFloat())

        var lo = Float.MAX_VALUE
        var hi = -Float.MAX_VALUE
        for (v in pts) { if (v < lo) lo = v; if (v > hi) hi = v }
        var range = hi - lo
        if (range < 20f) range = 20f
        val mid = (hi + lo) / 2f
        lo = mid - range / 2f

        val pad = 6.dp.toPx()
        val drawH = h - 2 * pad
        val dx = w / (pts.size - 1).coerceAtLeast(1)
        fun y(v: Float) = pad + drawH * (1f - (v - lo) / range)

        for (g in 1..3) {
            val gy = pad + drawH * g / 4f
            drawLine(IdleGray.copy(alpha = 0.12f), Offset(0f, gy), Offset(w, gy), strokeWidth = 1f)
        }

        val path = Path()
        path.moveTo(0f, y(pts[0]))
        for (k in 1 until pts.size) {
            val x1 = (k - 1) * dx
            val y1 = y(pts[k - 1])
            val x2 = k * dx
            val y2 = y(pts[k])
            val mx = (x1 + x2) / 2f
            val my = (y1 + y2) / 2f
            path.quadraticTo(x1, y1, mx, my)
        }
        path.lineTo(w, y(pts.last()))

        val fill = Path().apply {
            addPath(path)
            lineTo(w, h)
            lineTo(0f, h)
            close()
        }
        drawPath(fill, Brush.verticalGradient(
            listOf(color.copy(alpha = 0.22f), color.copy(alpha = 0.02f)),
            startY = pad, endY = h
        ))
        drawPath(path, color, style = Stroke(width = 2.dp.toPx()))
    }
}
