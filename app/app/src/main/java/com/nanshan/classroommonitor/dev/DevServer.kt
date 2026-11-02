package com.nanshan.classroommonitor.dev

import android.content.Context
import android.net.nsd.NsdManager
import android.net.nsd.NsdServiceInfo
import android.util.Log
import com.nanshan.classroommonitor.data.ConfigStore
import fi.iki.elonen.NanoHTTPD
import org.json.JSONObject
import java.net.Inet4Address
import java.net.NetworkInterface
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.concurrent.CopyOnWriteArrayList

/** 运行时状态（测量页写入，HTTP 读出） */
object DevState {
    @Volatile var connected = false
    @Volatile var bpm = 0
    @Volatile var bpm2 = 0
    @Volatile var score = 0f
    @Volatile var state = "IDLE"
    @Volatile var p95 = 0
    @Volatile var beat = false
    @Volatile var samples = 0
    @Volatile var sessionId = -1L
    @Volatile var wave: List<Int> = emptyList()
    val log = CopyOnWriteArrayList<String>()

    fun addLog(msg: String) {
        val t = SimpleDateFormat("HH:mm:ss", Locale.getDefault()).format(Date())
        log.add("$t $msg")
        while (log.size > 200) log.removeAt(0)
        Log.i("DevState", msg)
    }
}

/**
 * 开发者 HTTP 服务：电脑浏览器连手机（同 WiFi），
 * GET  /         调试面板（实时波形 + 配置编辑）
 * GET  /state    实时状态 JSON
 * GET  /wave     最近波形 CSV
 * GET  /config   表单配置 JSON
 * POST /config   提交新配置 JSON（原子校验后保存）
 */
class DevServer(
    private val ctx: Context,
    private val port: Int = 8080
) : NanoHTTPD(port) {

    private val configStore = ConfigStore.get(ctx)
    private var nsd: NsdManager? = null
    private var nsdListener: NsdManager.RegistrationListener? = null

    fun startWithMdns() {
        PulseSession.init(ctx)
        start(SOCKET_READ_TIMEOUT, false)
        advertise()
    }

    private fun advertise() {
        runCatching {
            val mgr = ctx.getSystemService(Context.NSD_SERVICE) as NsdManager
            val info = NsdServiceInfo().apply {
                serviceName = "cyberpulse"
                serviceType = "_http._tcp."
                setPort(port)
            }
            val listener = object : NsdManager.RegistrationListener {
                override fun onServiceRegistered(info: NsdServiceInfo) {
                    DevState.addLog("mDNS: ${info.serviceName}.local")
                }
                override fun onRegistrationFailed(info: NsdServiceInfo, e: Int) {
                    DevState.addLog("mDNS 注册失败 $e")
                }
                override fun onServiceUnregistered(info: NsdServiceInfo) {}
                override fun onUnregistrationFailed(info: NsdServiceInfo, e: Int) {}
            }
            mgr.registerService(info, NsdManager.PROTOCOL_DNS_SD, listener)
            nsd = mgr
            nsdListener = listener
        }.onFailure { DevState.addLog("mDNS 不可用: ${it.message}") }
    }

    override fun stop() {
        runCatching { nsdListener?.let { nsd?.unregisterService(it) } }
        nsdListener = null
        super.stop()
    }

    override fun serve(session: IHTTPSession): Response {
        return try {
            when (session.uri) {
                "/", "/index.html" -> html(indexHtml())
                "/state" -> json(PulseSession.stateJson())
                "/wave" -> plain(waveCsv(), "text/csv")
                "/sessions" -> json(PulseSession.sessionsJson())
                "/samples" -> {
                    val id = session.parameters["session"]?.firstOrNull()?.toLongOrNull()
                        ?: PulseSession.sessionId
                    if (id <= 0) json("""{"ok":false,"error":"没有会话"}""")
                    else plain(PulseSession.samplesCsv(id), "text/csv")
                }
                "/cmd" -> {
                    if (session.method != Method.POST) json("""{"ok":false,"error":"用 POST"}""")
                    else {
                        val body = readBody(session).trim()
                        if (body.isEmpty()) json("""{"ok":false,"error":"空命令"}""")
                        else {
                            PulseSession.init(ctx)
                            val ok = PulseSession.sendCommand(body)
                            json(if (ok) """{"ok":true}""" else """{"ok":false,"error":"未连接或写入失败"}""")
                        }
                    }
                }
                "/ble/connect" -> {
                    PulseSession.init(ctx)
                    PulseSession.connect()
                    json("""{"ok":true,"note":"开始扫描并连接 CYBER-PULSE"}""")
                }
                "/ble/disconnect" -> {
                    PulseSession.disconnect()
                    json("""{"ok":true}""")
                }
                "/record/start" -> {
                    val body = readBody(session)
                    val id = runCatching {
                        if (body.isBlank()) null else JSONObject(body).optLong("sessionId", 0)
                    }.getOrNull()?.takeIf { it > 0 } ?: PulseSession.sessionId
                    if (id <= 0) json("""{"ok":false,"error":"请先 POST /session 创建会话"}""")
                    else { PulseSession.startRecording(id); json("""{"ok":true,"sessionId":$id}""") }
                }
                "/record/pause" -> { PulseSession.pauseRecording(); json("""{"ok":true}""") }
                "/record/stop" -> { PulseSession.stopRecording(); json("""{"ok":true}""") }
                "/session" -> {
                    if (session.method != Method.POST) json("""{"ok":false,"error":"用 POST"}""")
                    else {
                        val body = readBody(session)
                        val obj = runCatching { JSONObject(body) }.getOrNull()
                        if (obj == null) json("""{"ok":false,"error":"body 不是合法 JSON"}""")
                        else {
                            PulseSession.init(ctx)
                            val map = HashMap<String, String>()
                            obj.keys().forEach { k -> map[k] = obj.optString(k) }
                            val id = PulseSession.createSession(map)
                            if (obj.has("autoStart") && obj.optBoolean("autoStart", true))
                                PulseSession.startRecording(id)
                            json("""{"ok":true,"id":$id}""")
                        }
                    }
                }
                "/config" -> {
                    if (session.method == Method.POST) handleConfigPost(session) else json(configStore.currentText())
                }
                "/health" -> plain("ok", "text/plain")
                else -> newFixedLengthResponse(
                    Response.Status.NOT_FOUND, MIME_PLAINTEXT, "not found: ${session.uri}"
                )
            }
        } catch (e: Exception) {
            DevState.addLog("HTTP 错误: ${e.message}")
            newFixedLengthResponse(Response.Status.INTERNAL_ERROR, MIME_PLAINTEXT, "error: ${e.message}")
        }
    }

    /** NanoHTTPD 只自动解析表单型 body，application/json 需自己按 content-length 读 */
    private fun readBody(session: IHTTPSession): String {
        val len = session.headers["content-length"]?.trim()?.toIntOrNull() ?: 0
        if (len <= 0) {
            val form = HashMap<String, String>()
            runCatching { session.parseBody(form) }
            return form["postData"] ?: ""
        }
        return runCatching {
            val buf = ByteArray(len)
            var off = 0
            val ins = session.inputStream
            while (off < len) {
                val n = ins.read(buf, off, len - off)
                if (n < 0) break
                off += n
            }
            String(buf, 0, off, Charsets.UTF_8)
        }.getOrDefault("")
    }

    private fun handleConfigPost(session: IHTTPSession): Response {
        val text = readBody(session).ifBlank { session.parameters["json"]?.firstOrNull() ?: "" }
        if (text.isNullOrBlank()) return json("""{"ok":false,"error":"空请求体"}""")
        val err = configStore.save(text)
        return if (err == null) {
            DevState.addLog("配置已更新 (HTTP)")
            json("""{"ok":true}""")
        } else {
            json("""{"ok":false,"error":"${err.replace("\"", "'")}"}""")
        }
    }

    private fun waveCsv(): String {
        val sb = StringBuilder("idx,value\n")
        DevState.wave.forEachIndexed { i, v -> sb.append(i).append(',').append(v).append('\n') }
        return sb.toString()
    }

    private fun json(text: String): Response =
        newFixedLengthResponse(Response.Status.OK, "application/json; charset=utf-8", text)

    private fun plain(text: String, mime: String): Response =
        newFixedLengthResponse(Response.Status.OK, "$mime; charset=utf-8", text)

    private fun html(text: String): Response =
        newFixedLengthResponse(Response.Status.OK, "text/html; charset=utf-8", text)

    private fun indexHtml(): String = """
<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>赛博把脉 · 调试台</title>
<style>
 body{font-family:system-ui,-apple-system,"Segoe UI",sans-serif;margin:0;background:#0f172a;color:#e2e8f0}
 .wrap{max-width:880px;margin:0 auto;padding:20px}
 h1{font-size:20px;margin:0 0 4px} .sub{color:#64748b;font-size:12px;margin-bottom:16px}
 .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:10px;margin-bottom:16px}
 .card{background:#1e293b;border-radius:12px;padding:14px}
 .k{font-size:11px;color:#94a3b8} .v{font-size:22px;font-weight:700;margin-top:2px}
 #wave{width:100%;height:260px;background:#1e293b;border-radius:12px;display:block}
 textarea{width:100%;height:280px;background:#1e293b;color:#e2e8f0;border:1px solid #334155;
   border-radius:12px;padding:12px;font-family:ui-monospace,Consolas,monospace;font-size:12px;box-sizing:border-box}
 button{background:#22c55e;color:#06210f;border:0;border-radius:10px;padding:10px 18px;font-weight:700;cursor:pointer;margin:8px 8px 0 0}
 button.sec{background:#334155;color:#e2e8f0}
 .row{display:flex;gap:12px;align-items:flex-start;flex-wrap:wrap}
 .row>*{flex:1;min-width:260px}
 #msg{font-size:12px;color:#4ade80;margin-top:8px}
</style></head><body><div class="wrap">
<h1>赛博把脉 · 调试台</h1>
<div class="sub">手机同屏输出 · 每 1 秒自动刷新 · POST /config 可远程改表单</div>

<div class="grid">
  <div class="card"><div class="k">BPM</div><div class="v" id="bpm">--</div></div>
  <div class="card"><div class="k">状态</div><div class="v" id="state">--</div></div>
  <div class="card"><div class="k">p95</div><div class="v" id="p95">--</div></div>
  <div class="card"><div class="k">已记录</div><div class="v" id="samples">0</div></div>
  <div class="card"><div class="k">连接</div><div class="v" id="conn">--</div></div>
</div>

<canvas id="wave"></canvas>

<div class="card" style="margin-top:16px">
  <div class="k">远程控制（手机端立即执行）</div>
  <div style="margin-top:10px">
    <button onclick="post('/ble/connect')">连接蓝牙</button>
    <button class="sec" onclick="post('/ble/disconnect')">断开蓝牙</button>
    <button onclick="post('/record/start')">开始记录</button>
    <button class="sec" onclick="post('/record/pause')">暂停</button>
    <button class="sec" onclick="post('/record/stop')">停止并结束</button>
  </div>
  <div style="margin-top:10px;display:flex;gap:8px;flex-wrap:wrap">
    <input id="nm" placeholder="姓名" style="padding:8px;border-radius:8px;border:1px solid #334155;background:#0f172a;color:#e2e8f0">
    <input id="sid" placeholder="学号" style="padding:8px;border-radius:8px;border:1px solid #334155;background:#0f172a;color:#e2e8f0">
    <button onclick="newSession()">建会话并开始记录</button>
    <button class="sec" onclick="listSessions()">查看会话</button>
  </div>
  <div id="ctl" style="font-size:12px;margin-top:8px;color:#94a3b8"></div>
</div>

<div class="row" style="margin-top:16px">
  <div>
    <div class="k" style="margin-bottom:6px">表单配置 config.json（改完点保存，手机立即生效）</div>
    <textarea id="cfg"></textarea>
    <div>
      <button onclick="saveCfg()">保存配置</button>
      <button class="sec" onclick="loadCfg()">重新读取</button>
    </div>
    <div id="msg"></div>
  </div>
  <div>
    <div class="k" style="margin-bottom:6px">事件日志</div>
    <pre id="log" style="background:#1e293b;border-radius:12px;padding:12px;font-size:11px;
      height:280px;overflow:auto;margin:0;white-space:pre-wrap"></pre>
  </div>
</div>
</div>
<script>
async function tick(){
  try{
    const s = await (await fetch('/state',{cache:'no-store'})).json();
    bpm.textContent = s.bpm>0 ? s.bpm : '--';
    state.textContent = s.state;
    p95.textContent = s.p95;
    samples.textContent = s.samples;
    conn.textContent = s.connected ? '已连接' : '断开';
    log.textContent = (s.log||[]).slice(-60).join('\n');
  }catch(e){}
}
async function drawWave(){
  try{
    const txt = await (await fetch('/wave',{cache:'no-store'})).text();
    const rows = txt.trim().split('\n').slice(1).map(r=>+r.split(',')[1]).filter(v=>!isNaN(v));
    const c = document.getElementById('wave');
    const dpr = window.devicePixelRatio||1;
    c.width = c.clientWidth*dpr; c.height = c.clientHeight*dpr;
    const g = c.getContext('2d'); g.scale(dpr,dpr);
    const W=c.clientWidth,H=c.clientHeight; g.clearRect(0,0,W,H);
    if(rows.length<4){ g.fillStyle='#334155'; g.font='13px sans-serif';
      g.fillText('等待波形数据…', 16, 24); return; }
    const lo=Math.min(...rows), hi=Math.max(...rows), rng=Math.max(hi-lo,20), pad=10;
    g.beginPath();
    rows.forEach((v,i)=>{
      const x=i/(rows.length-1)*W;
      const y=pad+(H-2*pad)*(1-(v-lo)/rng);
      i?g.lineTo(x,y):g.moveTo(x,y);
    });
    g.strokeStyle='#4ade80'; g.lineWidth=2; g.stroke();
  }catch(e){}
}
async function loadCfg(){
  const r = await fetch('/config',{cache:'no-store'});
  cfg.value = await r.text();
}
async function saveCfg(){
  const r = await fetch('/config',{method:'POST',headers:{'Content-Type':'application/json'},body:cfg.value});
  const j = await r.json();
  msg.textContent = j.ok ? '✓ 已保存，手机端新表单立即生效' : '✗ ' + j.error;
  msg.style.color = j.ok ? '#4ade80' : '#f87171';
}
async function post(path, body){
  const r = await fetch(path, {method:'POST', headers:{'Content-Type':'application/json'}, body: body?JSON.stringify(body):''});
  const j = await r.json().catch(()=>({}));
  ctl.textContent = j.ok ? ('✓ '+path+(j.note?(' · '+j.note):'')+(j.id?(' · #'+j.id):'')) : ('✗ '+path+' '+(j.error||''));
}
function newSession(){
  post('/session', {studentName:nm.value, studentId:sid.value, width:0, autoStart:true});
}
async function listSessions(){
  const r = await fetch('/sessions',{cache:'no-store'});
  const t = await r.text();
  ctl.textContent = t.slice(0, 600);
}
setInterval(tick,1000); setInterval(drawWave,500); tick(); drawWave(); loadCfg();
</script></body></html>
""".trimIndent()

    companion object {
        /** 取本机 WiFi IPv4，失败返回 null */
        fun localIp(): String? = runCatching {
            for (nif in NetworkInterface.getNetworkInterfaces()) {
                if (!nif.isUp || nif.isLoopback) continue
                for (addr in nif.inetAddresses) {
                    if (addr is Inet4Address && !addr.isLoopbackAddress) return addr.hostAddress
                }
            }
            null
        }.getOrNull()
    }
}
