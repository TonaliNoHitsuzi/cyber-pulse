// 零依赖静态服务器 + 现场演示一键启动
// node serve.js [端口]
const http = require('http');
const fs = require('fs');
const path = require('path');
const net = require('net');
const { spawn } = require('child_process');

const ROOT = __dirname;
const PORT = parseInt(process.argv[2], 10) || 8088;

const DEMO_PORT = 8100;
const DEMO_URL = 'http://127.0.0.1:8100/?cam=gdm';
const DEMO_DIR = path.join(ROOT, '..', '课堂演示');

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.mjs': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.svg': 'image/svg+xml',
  '.ico': 'image/x-icon',
  '.woff2': 'font/woff2',
  '.mp4': 'video/mp4',
  '.webm': 'video/webm',
  '.md': 'text/markdown; charset=utf-8',
};

/* ---------------- 现场演示：探测 / 启动 ---------------- */
let demoChild = null;
let demoErr = '';

function probe(port, timeout = 350) {
  return new Promise((resolve) => {
    const sock = net.connect({ port, host: '127.0.0.1' });
    let done = false;
    const fin = (v) => { if (done) return; done = true; sock.destroy(); resolve(v); };
    sock.setTimeout(timeout);
    sock.once('connect', () => fin(true));
    sock.once('timeout', () => fin(false));
    sock.once('error', () => fin(false));
  });
}

function pyExe() {
  const p = path.join(DEMO_DIR, 'runtime', 'python', 'python.exe');
  return fs.existsSync(p) ? p : 'python';
}

function startDemo() {
  if (demoChild) return;
  demoErr = '';
  const script = path.join(DEMO_DIR, 'launch_demo.py');
  if (!fs.existsSync(script)) { demoErr = '找不到 课堂演示/launch_demo.py'; return; }
  try {
    demoChild = spawn(pyExe(), ['-X', 'utf8', script, '--no-browser'], {
      cwd: DEMO_DIR,
      detached: true,
      stdio: 'ignore',
      windowsHide: true,
    });
    demoChild.once('error', (e) => { demoErr = '无法启动后端：' + e.message; demoChild = null; });
    demoChild.once('exit', (code) => {
      demoChild = null;
      if (code) demoErr = `启动脚本退出（代码 ${code}）`;
    });
    demoChild.unref();
  } catch (e) {
    demoErr = '无法启动后端：' + (e.message || e);
    demoChild = null;
  }
}

const LAUNCH_HTML = `<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>正在启动现场演示…</title>
<style>
 html,body{height:100%;margin:0;background:#fbfcfe;color:#0f172a;
   font-family:"Noto Sans SC","Microsoft YaHei UI",system-ui,sans-serif}
 .wrap{height:100%;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:16px}
 .ring{width:34px;height:34px;border-radius:50%;border:3px solid #dbe7ff;border-top-color:#1d4ed8;animation:spin .9s linear infinite}
 @keyframes spin{to{transform:rotate(360deg)}}
 .msg{font-size:18px;font-weight:600}
 .hint{font-size:13px;color:#94a3b8;max-width:520px;text-align:center;line-height:1.7}
 .err{color:#b91c1c}
</style></head>
<body><div class="wrap">
 <div class="ring" id="ring"></div>
 <div class="msg" id="msg">检查后端…</div>
 <div class="hint" id="hint">首次启动约 3–5 秒。若一直失败，双击 课堂演示/启动演示.bat 后刷新演示页。</div>
</div>
<script>
const msg=document.getElementById('msg'), hint=document.getElementById('hint'), ring=document.getElementById('ring');
const DEMO='http://127.0.0.1:8100/?cam=gdm';
const t0=Date.now();
(async function tick(){
  try{
    const r=await fetch('/demo/ping?t='+Date.now(),{cache:'no-store'});
    const j=await r.json();
    if(j.ok){ msg.textContent='已就绪，正在打开演示页…'; hint.textContent=''; location.replace(DEMO); return; }
    if(j.err){ ring.style.display='none'; msg.classList.add('err'); msg.textContent=j.err; hint.textContent='可双击 课堂演示/启动演示.bat，看窗口里的报错。'; return; }
    msg.textContent='正在启动后端…（串口桥 + 手机相机）';
  }catch(e){}
  if(Date.now()-t0>25000){ ring.style.display='none'; msg.classList.add('err'); msg.textContent='后端未在 25 秒内就绪'; hint.textContent='检查板子 USB 是否插好，或双击 课堂演示/启动演示.bat。'; return; }
  setTimeout(tick,500);
})();
</script></body></html>`;

const server = http.createServer((req, res) => {
  let p = decodeURIComponent(req.url.split('?')[0]);
  if (p === '/') p = '/index.html';

  if (p === '/demo/ping') {
    probe(DEMO_PORT).then((ok) => {
      if (ok) demoErr = '';
      res.writeHead(200, { 'content-type': 'application/json; charset=utf-8', 'cache-control': 'no-store' });
      res.end(JSON.stringify(ok
        ? { ok, starting: !!demoChild }
        : { ok, starting: !!demoChild, err: demoErr || undefined }));
    });
    return;
  }
  if (p === '/demo/launch' || p === '/demo/start') {
    probe(DEMO_PORT).then((ok) => {
      if (ok) { res.writeHead(302, { location: DEMO_URL }); res.end(); return; }
      startDemo();
      res.writeHead(200, { 'content-type': 'text/html; charset=utf-8', 'cache-control': 'no-store' });
      res.end(LAUNCH_HTML);
    });
    return;
  }

  // 支持 /讲稿/xx 与 /演示/xx 两个子站
  let file = path.join(ROOT, p);
  if (!file.startsWith(ROOT)) { res.writeHead(403); return res.end('forbidden'); }

  fs.stat(file, (err, st) => {
    if (!err && st.isDirectory()) file = path.join(file, 'index.html');
    fs.readFile(file, (e, buf) => {
      if (e) {
        res.writeHead(404, { 'content-type': 'text/plain; charset=utf-8' });
        return res.end('404 ' + p);
      }
      res.writeHead(200, {
        'content-type': MIME[path.extname(file).toLowerCase()] || 'application/octet-stream',
        'cache-control': 'no-cache',
      });
      res.end(buf);
    });
  });
});

server.listen(PORT, '127.0.0.1', () => {
  console.log(`[serve] http://127.0.0.1:${PORT}/  root=${ROOT}`);
});
