package com.nanshan.classroommonitor.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AssistChip
import androidx.compose.material3.AssistChipDefaults
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.nanshan.classroommonitor.data.ConfigStore
import com.nanshan.classroommonitor.data.DeviceMeta
import com.nanshan.classroommonitor.data.Repository
import com.nanshan.classroommonitor.data.ProfileRow
import com.nanshan.classroommonitor.data.SessionEntity
import kotlinx.coroutines.launch
import org.json.JSONObject

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun NewSessionScreen(nav: Navigator) {
    val ctx = LocalContext.current
    val repo = remember { Repository.get(ctx) }
    val scope = rememberCoroutineScope()

    // 表单配置（assets 默认值 + 电脑 HTTP 覆盖，进入页面时读最新）
    val config = remember { ConfigStore.get(ctx).load() }
    val fields = remember { config.optJSONArray("fields") ?: org.json.JSONArray() }
    val title = config.optString("title", "测量信息")

    val values = remember {
        mutableStateMapOf<String, String>().apply {
            for (i in 0 until fields.length()) {
                val f = fields.getJSONObject(i)
                put(f.getString("key"), f.optString("default", ""))
            }
        }
    }

    var missingHint by remember { mutableStateOf<String?>(null) }

    fun requiredMissing(): String? {
        for (i in 0 until fields.length()) {
            val f = fields.getJSONObject(i)
            if (f.optBoolean("required", false) && values[f.getString("key")].isNullOrBlank())
                return f.optString("label", f.getString("key"))
        }
        return null
    }

    Column(
        Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp)
    ) {
        Text("新建测量", fontSize = 20.sp, fontWeight = FontWeight.Bold)

        // 采集通道：仅脉搏（固定）
        Card(Modifier.fillMaxWidth()) {
            Row(Modifier.padding(12.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Text("采集通道", fontSize = 13.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
                AssistChip(
                    onClick = {},
                    label = { Text("脉搏 BPM", fontSize = 13.sp) },
                    colors = AssistChipDefaults.assistChipColors(
                        containerColor = MaterialTheme.colorScheme.primaryContainer
                    )
                )
            }
        }

        // 常用被试：一键填入（同组只有几个人，反复采集）
        var profiles by remember { mutableStateOf<List<ProfileRow>>(emptyList()) }
        LaunchedEffect(Unit) {
            profiles = runCatching { repo.recentProfiles() }.getOrDefault(emptyList())
        }
        if (profiles.isNotEmpty()) {
            Text("常用被试（点一下自动填入）", fontSize = 13.sp,
                 color = MaterialTheme.colorScheme.onSurfaceVariant)
            FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                profiles.forEach { pr ->
                    AssistChip(
                        onClick = {
                            values["studentName"] = pr.name
                            pr.sid?.takeIf { it.isNotBlank() }?.let { values["studentId"] = it }
                            pr.gender?.takeIf { it.isNotBlank() }?.let { values["gender"] = it }
                            pr.height?.let { values["height"] = if (it % 1.0 == 0.0) it.toInt().toString() else it.toString() }
                            pr.weight?.let { values["weight"] = if (it % 1.0 == 0.0) it.toInt().toString() else it.toString() }
                        },
                        label = { Text(pr.name, fontSize = 13.sp) }
                    )
                }
            }
        }

        Text(title, fontWeight = FontWeight.Medium)

        // 动态字段
        for (i in 0 until fields.length()) {
            val f = fields.getJSONObject(i)
            val key = f.getString("key")
            val label = f.optString("label", key)
            val required = f.optBoolean("required", false)
            val star = when {
                required -> " *"
                label.contains("选填") -> ""
                else -> "（选填）"
            }
            when (f.optString("type", "text")) {
                "choice" -> {
                    val opts = f.optJSONArray("options") ?: org.json.JSONArray()
                    Column {
                        Text("$label$star", fontSize = 13.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
                        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            for (j in 0 until opts.length()) {
                                val opt = opts.optString(j)
                                FilterChip(
                                    selected = values[key] == opt,
                                    onClick = { values[key] = opt },
                                    label = { Text(opt, fontSize = 13.sp) }
                                )
                            }
                        }
                    }
                }
                "number" -> OutlinedTextField(
                    value = values[key] ?: "",
                    onValueChange = { v -> values[key] = v.filter { it.isDigit() || it == '.' } },
                    label = { Text("$label$star") },
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth()
                )
                else -> OutlinedTextField(
                    value = values[key] ?: "",
                    onValueChange = { v -> values[key] = v },
                    label = { Text("$label$star") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth()
                )
            }
        }

        Text(
            "提示：字段与默认值可由电脑通过开发者 HTTP 接口更新（同 WiFi 访问手机 IP:8080）",
            fontSize = 11.sp, color = MaterialTheme.colorScheme.onSurfaceVariant
        )

        Button(
            enabled = true,
            onClick = {
                val miss = requiredMissing()
                if (miss != null) { missingHint = "请填写：$miss"; return@Button }
                missingHint = null
                scope.launch {
                    val extras = JSONObject()
                    runCatching { DeviceMeta.collect(ctx).let { meta -> meta.keys().forEach { k -> extras.put(k, meta.get(k)) } } }
                    val known = setOf("studentName", "studentId", "gender", "exercise", "height", "weight", "weather", "hand", "finger",
                        "temperature", "humidity", "note")
                    for ((k, v) in values) if (k !in known && v.isNotBlank()) extras.put(k, v)
                    val id = repo.createSession(
                        SessionEntity(
                            classId = "",
                            studentId = values["studentId"].orEmpty().trim(),
                            studentName = values["studentName"].orEmpty().trim(),
                            note = values["note"].orEmpty().trim(),
                            channels = "HEART_RATE",
                            createdAt = System.currentTimeMillis(),
                            appVersion = "1.0.0-pulse",
                            gender = values["gender"].orEmpty(),
                            exercise = values["exercise"].orEmpty().ifBlank { "静坐" },
                            height = values["height"]?.toDoubleOrNull(),
                            weight = values["weight"]?.toDoubleOrNull(),
                            weather = values["weather"].orEmpty(),
                            hand = values["hand"].orEmpty().ifBlank { "左手" },
                            finger = values["finger"].orEmpty().ifBlank { "拇指" },
                            temperature = values["temperature"]?.toDoubleOrNull(),
                            humidity = values["humidity"]?.toDoubleOrNull(),
                            extraJson = if (extras.length() > 0) extras.toString() else null
                        )
                    )
                    nav.push(Screen.Connect(id))
                }
            },
            modifier = Modifier.fillMaxWidth()
        ) { Text("下一步：连接设备") }

        missingHint?.let {
            Text(it, fontSize = 12.sp, color = MaterialTheme.colorScheme.error)
        }
        Spacer(Modifier.height(16.dp))
    }
}
