package com.nanshan.classroommonitor.ui

import android.widget.Toast
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.produceState
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.nanshan.classroommonitor.data.CsvExporter
import com.nanshan.classroommonitor.data.ChannelType
import com.nanshan.classroommonitor.data.ChannelStat
import com.nanshan.classroommonitor.data.Repository
import com.nanshan.classroommonitor.data.SessionEntity
import kotlinx.coroutines.launch

@Composable
fun SessionDetailScreen(nav: Navigator, sessionId: Long) {
    val ctx = LocalContext.current
    val repo = remember { Repository.get(ctx) }
    val scope = rememberCoroutineScope()

    var session by remember { mutableStateOf<SessionEntity?>(null) }
    val stats by produceState(initialValue = listOf<ChannelStat>(), sessionId) {
        value = repo.statsOf(sessionId)
    }
    var exportPath by remember { mutableStateOf<String?>(null) }

    LaunchedEffect(sessionId) { session = repo.session(sessionId) }

    val s = session ?: return

    Column(Modifier.fillMaxSize().padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Text("任务详情", fontSize = 20.sp, fontWeight = FontWeight.Bold)
        StatusBadge(s.status)

        Card(Modifier.fillMaxWidth()) {
            Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                DetailRow("姓名", s.studentName)
                DetailRow("学号", s.studentId)
                DetailRow("性别", s.gender)
                DetailRow("运动类型", s.exercise)
                DetailRow("身高", s.height?.let { "${it}cm" } ?: "")
                DetailRow("体重", s.weight?.let { "${it}kg" } ?: "")
                DetailRow("测量手", s.hand)
                DetailRow("测量手指", s.finger)
                DetailRow("温度", s.temperature?.let { "${it}℃" } ?: "")
                DetailRow("湿度", s.humidity?.let { "${it}%" } ?: "")
                DetailRow("天气", s.weather)
                DetailRow("备注", s.note)
                DetailRow("任务号", "#${s.id}")
                DetailRow("创建", Repository.local(s.createdAt))
                s.startedAt?.let { DetailRow("开始", Repository.local(it)) }
                s.endedAt?.let { DetailRow("结束", Repository.local(it)) }
                DetailRow("通道", s.channels.split(",").mapNotNull { ChannelType.from(it.trim())?.label }.joinToString("、"))
            }
        }

        Text("通道统计", fontWeight = FontWeight.Medium)
        if (stats.isEmpty()) {
            Text("暂无样本", fontSize = 13.sp, color = Color.Gray)
        } else {
            Card(Modifier.fillMaxWidth()) {
                Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    stats.forEach { st ->
                        val ch = ChannelType.from(st.channel)
                        Row(Modifier.fillMaxWidth()) {
                            Text(ch?.label ?: st.channel, fontSize = 13.sp)
                            Spacer(Modifier.weight(1f))
                            Text(
                                "${st.n} 条 · ${"%.1f".format(st.vmin)}~${"%.1f".format(st.vmax)} ${ch?.unit ?: ""}",
                                fontSize = 13.sp, color = Color.Gray
                            )
                        }
                    }
                }
            }
        }

        Spacer(Modifier.weight(1f))

        Button(
            onClick = {
                scope.launch {
                    runCatching { CsvExporter.export(ctx, s) }
                        .onSuccess { exportPath = it }
                        .onFailure { Toast.makeText(ctx, "导出失败：${it.message}", Toast.LENGTH_LONG).show() }
                }
            },
            modifier = Modifier.fillMaxWidth()
        ) { Text("导出 CSV + manifest") }

        exportPath?.let { p ->
            Card(Modifier.fillMaxWidth()) {
                Column(Modifier.padding(12.dp)) {
                    Text("已导出 ✓", color = Color(0xFF2E7D32), fontSize = 14.sp)
                    Text(p, fontSize = 11.sp)
                }
            }
        }

        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {

            Button(
                onClick = {
                    scope.launch {
                        repo.deleteSession(sessionId)
                        nav.pop()
                    }
                },
                modifier = Modifier.weight(1f),
                colors = ButtonDefaults.buttonColors(containerColor = Color(0xFFB71C1C))
            ) { Text("删除任务") }
        }
    }
}

@Composable
private fun DetailRow(k: String, v: String) {
    Row(Modifier.fillMaxWidth()) {
        Text(k, fontSize = 13.sp, color = Color.Gray)
        Spacer(Modifier.weight(1f))
        Text(v.ifBlank { "—" }, fontSize = 13.sp)
    }
}
