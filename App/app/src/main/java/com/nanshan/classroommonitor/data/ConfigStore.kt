package com.nanshan.classroommonitor.data

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject

/**
 * 表单配置存取：默认来自 assets/form_config.json，
 * 可被开发者页或电脑 HTTP (POST /config) 覆盖，持久化在 SharedPreferences。
 */
class ConfigStore private constructor(private val ctx: Context) {
    companion object {
        @Volatile private var inst: ConfigStore? = null
        fun get(ctx: Context): ConfigStore =
            inst ?: synchronized(this) {
                inst ?: ConfigStore(ctx.applicationContext).also { inst = it }
            }
        private const val PREFS = "pulse_form_config"
        private const val KEY = "json"
    }

    private val prefs = ctx.getSharedPreferences(PREFS, Context.MODE_PRIVATE)

    fun defaultJson(): JSONObject = runCatching {
        JSONObject(ctx.assets.open("form_config.json").bufferedReader().use { it.readText() })
    }.getOrElse {
        JSONObject("""{"version":1,"title":"测量信息","channels":["HEART_RATE"],"fields":[]}""")
    }

    fun load(): JSONObject = runCatching {
        prefs.getString(KEY, null)?.let { JSONObject(it) } ?: defaultJson()
    }.getOrElse { defaultJson() }

    /** 校验并保存；返回 null=成功，否则错误信息 */
    fun save(jsonText: String): String? {
        val obj = runCatching { JSONObject(jsonText) }.getOrNull() ?: return "不是合法 JSON"
        val fields = obj.optJSONArray("fields") ?: return "缺少 fields 数组"
        if (fields.length() == 0) return "fields 不能为空"
        for (i in 0 until fields.length()) {
            val f = fields.optJSONObject(i) ?: return "fields[$i] 不是对象"
            if (f.optString("key").isBlank()) return "fields[$i] 缺少 key"
            if (f.optString("label").isBlank()) return "fields[$i] 缺少 label"
            val t = f.optString("type", "text")
            if (t !in listOf("text", "choice", "number")) return "fields[$i] type 非法：$t"
            if (t == "choice") {
                val opts = f.optJSONArray("options")
                if (opts == null || opts.length() == 0) return "fields[$i] choice 必须带 options"
            }
        }
        prefs.edit().putString(KEY, obj.toString(2)).apply()
        return null
    }

    fun save(json: JSONObject): String? = save(json.toString())

    fun reset() {
        prefs.edit().remove(KEY).apply()
    }

    fun currentText(): String = load().toString(2)
}
