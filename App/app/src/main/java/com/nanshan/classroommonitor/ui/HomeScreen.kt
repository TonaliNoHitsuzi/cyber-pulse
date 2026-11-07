package com.nanshan.classroommonitor.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.nanshan.classroommonitor.data.ChannelType
import com.nanshan.classroommonitor.data.Repository
import com.nanshan.classroommonitor.data.SessionEntity
import com.nanshan.classroommonitor.data.SessionStatus

@Composable
fun HomeScreen(nav: Navigator) {
    val ctx = LocalContext.current
    val repo = remember { Repository.get(ctx) }
    val sessions by repo.observeSessions().collectAsState(initial = emptyList())

    Column(Modifier.fillMaxSize().padding(16.dp)) {
        Row(
            Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically
        ) {
            Text("赛博把脉", fontSize = 22.sp, fontWeight = FontWeight.Bold)
            Text(
                "开发者",
                fontSize = 14.sp,
                color = MaterialTheme.colorScheme.primary,
                modifier = Modifier
                    .padding(8.dp)
                    .clickable { nav.push(Screen.Dev) }
            )
        }
        Spacer(Modifier.height(8.dp))
        Text(
            "ESP32-C3 压电薄膜脉搏检测 · 手套原型",
            fontSize = 12.sp, color = Color.Gray
        )
        Spacer(Modifier.height(12.dp))

        Button(
            onClick = { nav.push(Screen.NewSession) },
            modifier = Modifier.fillMaxWidth()
        ) { Text("＋ 开始新测量") }

        Spacer(Modifier.height(12.dp))
        Text("历史记录（${sessions.size}）", fontSize = 14.sp, fontWeight = FontWeight.Medium)
        Spacer(Modifier.height(6.dp))

        LazyColumn(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            items(sessions, key = { it.id }) { s ->
                SessionCard(s) { nav.push(Screen.SessionDetail(s.id)) }
            }
        }
    }
}

@Composable
private fun SessionCard(s: SessionEntity, onClick: () -> Unit) {
    Card(Modifier.fillMaxWidth().clickable { onClick() }) {
        Column(Modifier.padding(12.dp)) {
            Row(
                Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text(
                    s.studentName.ifBlank { "学生${s.studentId}" },
                    fontWeight = FontWeight.Medium, fontSize = 16.sp
                )
                StatusBadge(s.status)
            }
            Spacer(Modifier.height(4.dp))
            Text(
                "${s.classId} · #${s.id} · ${Repository.local(s.createdAt)}",
                fontSize = 12.sp, color = Color.Gray
            )
            Text(
                s.channels.split(",").mapNotNull { ChannelType.from(it.trim())?.label }.joinToString(" / "),
                fontSize = 12.sp, color = Color.Gray,
                maxLines = 1
            )
        }
    }
}

@Composable
fun StatusBadge(statusName: String) {
    val st = runCatching { SessionStatus.valueOf(statusName) }.getOrDefault(SessionStatus.CREATED)
    val color = when (st) {
        SessionStatus.CREATED -> Color(0xFF9E9E9E)
        SessionStatus.RECORDING -> Color(0xFF2E7D32)
        SessionStatus.PAUSED -> Color(0xFFF9A825)
        SessionStatus.DONE -> Color(0xFF1565C0)
    }
    Row(verticalAlignment = Alignment.CenterVertically) {
        Spacer(
            Modifier.width(8.dp).height(8.dp).background(color, CircleShape)
        )
        Spacer(Modifier.width(4.dp))
        Text(st.label, fontSize = 12.sp, color = color)
    }
}
