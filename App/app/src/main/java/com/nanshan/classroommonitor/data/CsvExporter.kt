package com.nanshan.classroommonitor.data

import android.content.ContentValues
import android.content.Context
import android.os.Build
import android.os.Environment
import android.provider.MediaStore
import java.io.File

/**
 * 导出会话数据：samples.csv + manifest.json
 * - API 29+：写入公共 Downloads/classroom-monitor/<会话>/（文件管理器可见、USB MTP 直拷）
 * - API <29：退回应用外部私有目录（adb pull）
 * 返回人类可读的导出位置描述。
 */
object CsvExporter {

    fun export(context: Context, session: SessionEntity): String {
        val repo = Repository.get(context)
        val samples = kotlinx.coroutines.runBlocking { repo.samplesOf(session.id) }

        val dirName = buildString {
            append(SimpleDateFormatSafe.date(session.createdAt))
            append("_").append(session.classId)
            append("_").append(session.studentName.ifBlank { session.studentId })
            append("_").append(session.id)
        }

        val csv = buildCsv(session, samples)
        val manifest = buildManifest(session, samples)

        return if (Build.VERSION.SDK_INT >= 29) {
            writeViaMediaStore(context, dirName, "samples.csv", csv, "text/csv")
            writeViaMediaStore(context, dirName, "manifest.json", manifest, "application/json")
            "Download/classroom-monitor/$dirName/（文件管理→Download 可见，USB 直拷）"
        } else {
            val dir = File(context.getExternalFilesDir("exports"), dirName)
            dir.mkdirs()
            File(dir, "samples.csv").writeText(csv, Charsets.UTF_8)
            File(dir, "manifest.json").writeText(manifest, Charsets.UTF_8)
            dir.absolutePath
        }
    }

    private fun buildCsv(session: SessionEntity, samples: List<SampleEntity>): String = buildString {
        appendLine("session_id,student_id,gender,hand,finger,temperature,humidity,class_id,channel,channel_label,unit,ts_ms,ts_iso8601_utc,value,source,quality,extra")
        for (s in samples) {
            val ch = ChannelType.from(s.channel)
            appendLine(
                listOf(
                    session.id.toString(),
                    csv(session.studentId),
                    csv(session.gender),
                    csv(session.hand),
                    csv(session.finger),
                    session.temperature?.toString() ?: "",
                    session.humidity?.toString() ?: "",
                    csv(session.classId),
                    s.channel,
                    csv(ch?.label ?: s.channel),
                    csv(ch?.unit ?: ""),
                    s.tsMillis.toString(),
                    Repository.iso(s.tsMillis),
                    s.value.toString(),
                    s.sourceTag,
                    s.quality,
                    csv(s.extraJson ?: "")
                ).joinToString(",")
            )
        }
    }

    private fun buildManifest(session: SessionEntity, samples: List<SampleEntity>): String = buildString {
        appendLine("{")
        appendLine("  \"session_id\": ${session.id},")
        appendLine("  \"student_id\": \"${escape(session.studentId)}\",")
        appendLine("  \"student_name\": \"${escape(session.studentName)}\",")
        appendLine("  \"gender\": \"${escape(session.gender)}\",")
        appendLine("  \"exercise\": \"${escape(session.exercise)}\",")
        appendLine("  \"height_cm\": ${session.height ?: "null"},")
        appendLine("  \"weight_kg\": ${session.weight ?: "null"},")
        appendLine("  \"weather\": \"${escape(session.weather)}\",")
        appendLine("  \"hand\": \"${escape(session.hand)}\",")
        appendLine("  \"finger\": \"${escape(session.finger)}\",")
        appendLine("  \"temperature\": ${session.temperature ?: "null"},")
        appendLine("  \"humidity\": ${session.humidity ?: "null"},")
        appendLine("  \"class_id\": \"${escape(session.classId)}\",")
        appendLine("  \"note\": \"${escape(session.note)}\",")
        appendLine("  \"project_code\": \"cyber-pulse\",")
        appendLine("  \"channels\": [${session.channels.split(",").filter { it.isNotBlank() }.joinToString(",") { "\"${it.trim()}\"" }}],")
        appendLine("  \"status\": \"${session.status}\",")
        appendLine("  \"created_at_ms\": ${session.createdAt},")
        appendLine("  \"started_at_ms\": ${session.startedAt ?: "null"},")
        appendLine("  \"ended_at_ms\": ${session.endedAt ?: "null"},")
        appendLine("  \"ntp_offset_ms\": 0,")
        appendLine("  \"device\": \"${escape(session.deviceLabel)}\",")
        appendLine("  \"app_version\": \"${escape(session.appVersion)}\",")
        appendLine("  \"sample_count\": ${samples.size},")
        appendLine("  \"exported_at_ms\": ${System.currentTimeMillis()}")
        appendLine("}")
    }

    /** API 29+：经 MediaStore 写入公共 Downloads 子目录 */
    private fun writeViaMediaStore(context: Context, dirName: String, fileName: String, content: String, mime: String) {
        val resolver = context.contentResolver
        val relPath = "${Environment.DIRECTORY_DOWNLOADS}/classroom-monitor/$dirName"

        // 同名先删（重复导出幂等）
        resolver.delete(
            MediaStore.Downloads.EXTERNAL_CONTENT_URI,
            "${MediaStore.MediaColumns.RELATIVE_PATH}=? AND ${MediaStore.MediaColumns.DISPLAY_NAME}=?",
            arrayOf(relPath, fileName)
        )

        val values = ContentValues().apply {
            put(MediaStore.MediaColumns.DISPLAY_NAME, fileName)
            put(MediaStore.MediaColumns.MIME_TYPE, mime)
            put(MediaStore.MediaColumns.RELATIVE_PATH, relPath)
            put(MediaStore.MediaColumns.IS_PENDING, 1)
        }
        val uri = resolver.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, values) ?: return
        resolver.openOutputStream(uri)?.use { it.write(content.toByteArray(Charsets.UTF_8)) }
        values.clear()
        values.put(MediaStore.MediaColumns.IS_PENDING, 0)
        resolver.update(uri, values, null, null)
    }

    private fun csv(v: String) = "\"" + escape(v) + "\""
    private fun escape(v: String) = v.replace("\\", "\\\\").replace("\"", "\\\"")

    private object SimpleDateFormatSafe {
        private val f = java.text.SimpleDateFormat("yyyyMMdd", java.util.Locale.US)
        fun date(ms: Long): String = synchronized(f) { f.format(java.util.Date(ms)) }
    }
}
