package com.nanshan.classroommonitor.dev

import android.content.Context
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import com.nanshan.classroommonitor.ble.PulseBleClient
import com.nanshan.classroommonitor.ble.PulseData
import com.nanshan.classroommonitor.data.ChannelType
import com.nanshan.classroommonitor.data.Repository
import com.nanshan.classroommonitor.data.SampleEntity
import com.nanshan.classroommonitor.data.SampleSource
import com.nanshan.classroommonitor.data.SessionEntity
import com.nanshan.classroommonitor.data.SessionStatus
import com.nanshan.classroommonitor.data.DeviceMeta
import com.nanshan.classroommonitor.data.WaveChunkEntity
import com.nanshan.classroommonitor.data.UiFrameEntity
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.runBlocking
import org.json.JSONArray
import org.json.JSONObject

/**
 * 测量会话控制器：UI 与开发者 HTTP 共用的唯一真源。
 * - BLE 连接/订阅、波形缓存
 * - 会话创建/录制/结束（Room 落库）
 * - DevState 同步（供 HTTP /state 读取）
 */
object PulseSession {
    private const val WAVE_WIN = 500

    private lateinit var appCtx: Context
    private val scope = CoroutineScope(Dispatchers.IO + SupervisorJob())

    private val repoLazy: Repository get() = Repository.get(appCtx)

    /* ---- 供 Compose UI 观察 ---- */
    var latest by mutableStateOf(PulseData(0, "IDLE", 0, false))
    val wave = mutableStateListOf<Int>()
    var connected by mutableStateOf(false)
    var recording by mutableStateOf(false)
    var samples by mutableStateOf(0)
    var statusText by mutableStateOf("未连接")
    var sessionId = -1L
        private set

    var connectCallback: (() -> Unit)? = null

    fun init(ctx: Context) {
        if (::appCtx.isInitialized) return
        appCtx = ctx.applicationContext
        val c = PulseBleClient.get(appCtx)
        c.onData = { d ->
            lastDataTs = System.currentTimeMillis()
            if (!connected) { connected = true; DevState.connected = true; connectedSince = lastDataTs }
            latest = d
            DevState.bpm = d.bpm
            DevState.bpm2 = d.bpm2
            DevState.score = d.score
            val sid = sessionId
            if (sid > 0) {
                synchronized(replayLock) {
                    uiBuf.add(UiFrameEntity(sessionId = sid, ts = System.currentTimeMillis(),
                        bpm = d.bpm, bpm2 = d.bpm2, sc = d.score, state = d.state,
                        p95 = d.p95, p50 = 0, q = 0))
                }
            }
            DevState.state = d.state
            DevState.p95 = d.p95
            DevState.beat = d.beat
            DevState.sessionId = sessionId
            if (recording && d.bpm > 0) recordSample(d)
            flushReplayIfDue()
        }
        c.onReplay = { startMs, samples ->
            lastDataTs = System.currentTimeMillis()
            DevState.addLog("补发 ${samples.size} 点 起始=${startMs}ms")
            // 显示：只取最后 500 点，避免刷屏
            val tail = if (samples.size > WAVE_WIN) samples.subList(samples.size - WAVE_WIN, samples.size) else samples
            wave.clear(); wave.addAll(tail)
            DevState.wave = tail
            val id = sessionId
            if (recording && id > 0 && samples.isNotEmpty()) {
                synchronized(replayLock) {
                    replayBuf.add(WaveChunkEntity(sessionId = id, startTs = startMs, count = samples.size,
                        data = samplesToBytes(samples)))
                    replayLastEndBoardMs = startMs + samples.size * 10L
                    replayFlushAt = System.currentTimeMillis() + 700
                }
            }
        }
        c.onWave = { s ->
            lastDataTs = System.currentTimeMillis()
            // 实时波形入库：记录会话开启时，按到达时间戳反推样本时段，攒 1 秒成块
            val sid = sessionId
            if (recording && sid > 0 && s.isNotEmpty()) {
                synchronized(replayLock) {
                    val now = System.currentTimeMillis()
                    liveWaveStart = if (liveWaveStart == 0L) now - s.size * 10L else liveWaveStart
                    liveWaveBuf.addAll(s)
                    if (liveWaveBuf.size >= 100) {
                        val chunk = ArrayList(liveWaveBuf.subList(0, 100))
                        liveWaveBuf = ArrayList(liveWaveBuf.subList(100, liveWaveBuf.size))
                        val st = liveWaveStart
                        liveWaveStart += chunk.size * 10L
                        val bytes = samplesToBytes(chunk)
                        scope.launch {
                            repoLazy.insertWaveChunks(listOf(
                                WaveChunkEntity(sessionId = sid, startTs = st, count = chunk.size, data = bytes)
                            ))
                        }
                    }
                }
            }
            wave.addAll(s)
            val over = wave.size - WAVE_WIN
            if (over > 0) wave.subList(0, over).clear()
            DevState.wave = wave.toList()
        }
        c.onConnected = {
            connectInFlight = false
            connectedSince = System.currentTimeMillis()
            lastDataTs = connectedSince      // 新连接宽限：避免旧时间戳误判为断链
            connected = true
            statusText = "已连接"
            DevState.connected = true
            DevState.addLog("BLE 已连接，通知已订阅")
            connectCallback?.invoke()
        }
        c.onDisconnected = {
            // 连接断开：实时波形缓冲收尾入库
            synchronized(replayLock) {
                if (liveWaveBuf.isNotEmpty() && sessionId > 0 && recording) {
                    val st = liveWaveStart
                    val chunk = ArrayList(liveWaveBuf); liveWaveBuf.clear()
                    val bytes = samplesToBytes(chunk)
                    liveWaveStart = 0L
                    scope.launch {
                        repoLazy.insertWaveChunks(listOf(
                            WaveChunkEntity(sessionId = sessionId, startTs = st, count = chunk.size, data = bytes)
                        ))
                    }
                }
                liveWaveStart = 0L
            }
            connected = false
            statusText = "已断开"
            DevState.connected = false
            DevState.addLog("BLE 断开")
        }
        c.onScanEvent = { msg -> DevState.addLog("扫描: $msg") }
        c.onRssi = { rssi -> ContextCollector.onRssi(rssi) }
        /* 链路看门狗：每 500ms 用"数据新鲜度"统一两端口径；断了自动重连 */
        scope.launch {
            var wasAlive = false
            var reconnectAttempts = 0
            while (true) {
                delay(500)
                val alive = refreshLinkState()
                if (alive) runCatching { PulseBleClient.get(appCtx).readRssi() }
                if (!alive && connectedSince > 0L && System.currentTimeMillis() - connectedSince < 6000L) {
                    continue   // 刚连上 6 秒内不判死（补发/订阅需要时间）
                }
                if (alive) {
                    wasAlive = true
                    reconnectAttempts = 0
                } else if (wasAlive && !connectInFlight && reconnectAttempts < 5) {
                    reconnectAttempts++
                    DevState.addLog("链路丢失，自动重连 #$reconnectAttempts")
                    delay(1500)
                    runCatching { PulseBleClient.get(appCtx).forceReset() }
                    connect()
                }
            }
        }
        c.onError = {
            connectInFlight = false
            connected = false
            DevState.connected = false
            statusText = "错误: $it"
            DevState.addLog("BLE 错误: $it")
        }
    }

    /* ---------- 蓝牙 ---------- */
    fun connect(timeoutMs: Long = 12000) {
        if (connectInFlight) { DevState.addLog("连接进行中，忽略重复请求"); return }
        connectInFlight = true
        val c = PulseBleClient.get(appCtx)
        if (c.connectedState) {
            if (verifyConnection()) { connectInFlight = false; return }   // 真连着
            DevState.addLog("僵尸状态已清理，重新扫描")
        }
        statusText = "扫描中…"
        DevState.addLog("开始扫描 CYBER-PULSE")
        var done = false
        c.onDeviceFound = { dev ->
            if (!done) {
                done = true
                statusText = "连接中…"
                DevState.addLog("发现 ${dev.name}，发起连接")
                c.connect(dev)
            }
        }
        c.startScan()
        scope.launch {
            delay(timeoutMs)
            if (!done && !c.connectedState) {
                done = true
                c.stopScan()
                statusText = "未发现设备"
                connectInFlight = false
                DevState.addLog("扫描超时：未发现 CYBER-PULSE")
            } else if (c.connectedState) {
                connectInFlight = false
            }
        }
    }

    /** 统一的"已连接"判据：1.5 秒内有数据才算连（与板子唯一真值对齐） */
    fun refreshLinkState(): Boolean {
        val alive = connected && (System.currentTimeMillis() - lastDataTs < 1500)
        if (connected != alive) {
            DevState.addLog(if (alive) "链路恢复" else "链路中断（无数据）")
        }
        connected = alive
        DevState.connected = alive
        return alive
    }

    /** 僵尸连接检测：声称已连接但长时间无数据 */
    fun verifyConnection(): Boolean {
        if (!connected && connectedSince == 0L) return false
        if (!connected) return false
        val now = System.currentTimeMillis()
        // 宽限期：刚连上 8 秒内还没数据是正常的（等订阅/首包）
        if (lastDataTs == 0L && now - connectedSince < 8000) return true
        val idle = now - lastDataTs
        if (idle > 4000) {
            DevState.addLog("检测到僵尸连接（${idle / 1000}s 无数据）→ 复位")
            runCatching { PulseBleClient.get(appCtx).forceReset() }
            connected = false
            DevState.connected = false
            statusText = "连接已失效"
            return false
        }
        return true
    }

    fun sendCommand(cmd: String): Boolean {
        val ok = runCatching { PulseBleClient.get(appCtx).sendCommand(cmd) }.getOrDefault(false)
        DevState.addLog("命令 ${if (ok) "已发送" else "失败"}: $cmd")
        return ok
    }

    fun requestReplay() {
        runCatching { PulseBleClient.get(appCtx).requestReplay(0L) }
        DevState.addLog("请求补发（整个缓存）")
    }

    fun disconnect() {
        PulseBleClient.get(appCtx).disconnect()
    }

    /* ---------- 会话 ---------- */
    fun createSession(values: Map<String, String>): Long = runBlocking {
        val extras = JSONObject()
        runCatching { DeviceMeta.collect(appCtx).let { meta -> meta.keys().forEach { k -> extras.put(k, meta.get(k)) } } }
        val known = setOf("studentName", "studentId", "gender", "exercise", "height", "weight", "weather", "hand", "finger",
            "temperature", "humidity", "note")
        for ((k, v) in values) if (k !in known && v.isNotBlank()) extras.put(k, v)
        val id = repoLazy.createSession(
            SessionEntity(
                classId = "",
                studentId = values["studentId"].orEmpty(),
                studentName = values["studentName"].orEmpty(),
                note = values["note"].orEmpty(),
                channels = "HEART_RATE",
                createdAt = System.currentTimeMillis(),
                appVersion = "1.2.0-pulse",
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
        DevState.addLog("创建会话 #$id ${values["studentName"].orEmpty()}")
        id
    }

    fun startRecording(id: Long? = null) {
        val target = id ?: sessionId
        if (target <= 0) return
        sessionId = target
        samples = 0
        finished = false
        recording = true
        runCatching { ImuCollector.start(appCtx, target) }
        runCatching { ContextCollector.start(appCtx, target) }
        runCatching { RecordingService.start(appCtx) }
        DevState.samples = 0
        DevState.sessionId = target
        scope.launch {
            repoLazy.markStarted(target)
            repoLazy.setStatus(target, SessionStatus.RECORDING)
        }
        DevState.addLog("开始录制 #$target")
    }

    fun pauseRecording() {
        recording = false
        runCatching { ImuCollector.stop() }
        runCatching { ContextCollector.stop() }
        runCatching { RecordingService.stop(appCtx) }
        sessionId.takeIf { it > 0 }?.let { id ->
            scope.launch { repoLazy.setStatus(id, SessionStatus.PAUSED) }
        }
        DevState.addLog("暂停录制")
    }

    private var finished = false
    fun stopRecording() {
        if (finished) return          // 防重复（BackHandler 与 onDispose 都会调）
        finished = true
        recording = false
        runCatching { ImuCollector.stop() }
        runCatching { ContextCollector.stop() }
        runCatching { RecordingService.stop(appCtx) }
        runCatching { ContextCollector.stop() }
        runCatching { RecordingService.stop(appCtx) }
        val id = sessionId
        if (id > 0) {
            scope.launch {
                repoLazy.markEnded(id)
                repoLazy.setStatus(id, SessionStatus.DONE)
                DevState.addLog("结束会话 #$id，共 $samples 条")
            }
        }
    }

    private fun recordSample(d: PulseData) {
        val id = sessionId
        if (id <= 0) return
        scope.launch {
            repoLazy.insertSamples(
                listOf(
                    SampleEntity(
                        sessionId = id,
                        channel = ChannelType.HEART_RATE.name,
                        tsMillis = System.currentTimeMillis(),
                        value = d.bpm.toDouble(),
                        quality = d.state,
                        extraJson = "{\"p95\":${d.p95}}",
                        sourceTag = SampleSource.PIEZO
                    )
                )
            )
            samples++
            DevState.samples = samples
        }
    }

    /* ---------- 断线补发的定标与落库 ---------- */
    private val replayLock = Any()
    private val replayBuf = ArrayList<WaveChunkEntity>()
    private val uiBuf = ArrayList<UiFrameEntity>()
    private var liveWaveBuf = ArrayList<Int>()
    private var liveWaveStart = 0L
    @Volatile private var lastDataTs = 0L
    @Volatile private var connectedSince = 0L
    @Volatile private var connectInFlight = false
    private var replayLastEndBoardMs = 0L
    private var replayFlushAt = 0L
    private var uiFlushAt = 0L

    private fun samplesToBytes(samples: List<Int>): ByteArray {
        val b = ByteArray(samples.size * 2)
        for (i in samples.indices) {
            b[2 * i] = (samples[i] and 0xFF).toByte()
            b[2 * i + 1] = ((samples[i] shr 8) and 0xFF).toByte()
        }
        return b
    }

    /** 补发静默后统一换算为墙上时间并入库；ui 帧独立按 2s 落库 */
    private fun flushReplayIfDue() {
        synchronized(replayLock) {
            val now = System.currentTimeMillis()
            // ui 帧独立落库（每 2 秒），不依赖补发
            if (uiBuf.isNotEmpty() && now >= uiFlushAt) {
                val frames = ArrayList(uiBuf); uiBuf.clear()
                uiFlushAt = now + 2000
                scope.launch { repoLazy.insertUiFrames(frames) }
            }
            if (replayBuf.isEmpty() || now < replayFlushAt) return
            val offset = System.currentTimeMillis() - replayLastEndBoardMs
            val fixed = replayBuf.map { it.copy(startTs = it.startTs + offset) }
            replayBuf.clear()
            scope.launch { repoLazy.insertWaveChunks(fixed) }
            if (fixed.isNotEmpty()) DevState.addLog("补发入库 ${fixed.size} 块（已换算墙上时间）")
        }
    }

    /* ---------- 查询（HTTP 用） ---------- */
    fun sessionsJson(): String = runBlocking {
        val arr = JSONArray()
        repoLazy.allSessions().forEach { s ->
            val o = JSONObject()
            o.put("id", s.id)
            o.put("name", s.studentName)
            o.put("studentId", s.studentId)
            o.put("gender", s.gender)
            o.put("hand", s.hand)
            o.put("finger", s.finger)
            o.put("temperature", s.temperature ?: JSONObject.NULL)
            o.put("humidity", s.humidity ?: JSONObject.NULL)
            o.put("status", s.status)
            o.put("createdAt", s.createdAt)
            o.put("samples", repoLazy.countOf(s.id))
            arr.put(o)
        }
        arr.toString()
    }

    fun samplesCsv(id: Long): String = runBlocking {
        val sb = StringBuilder("idx,ts_ms,ts_iso,bpm,quality,p95\n")
        repoLazy.samplesOf(id).forEachIndexed { i, s ->
            sb.append(i).append(',')
                .append(s.tsMillis).append(',')
                .append(Repository.iso(s.tsMillis)).append(',')
                .append(s.value).append(',')
                .append(s.quality).append(',')
                .append(s.extraJson ?: "").append('\n')
        }
        sb.toString()
    }

    fun stateJson(): String = JSONObject()
        .put("connected", connected)
        .put("recording", recording)
        .put("sessionId", sessionId)
        .put("samples", samples)
        .put("bpm", latest.bpm)
        .put("state", latest.state)
        .put("p95", latest.p95)
        .put("beat", latest.beat)
        .put("wavePoints", wave.size)
        .put("status", statusText)
        .toString()
}
