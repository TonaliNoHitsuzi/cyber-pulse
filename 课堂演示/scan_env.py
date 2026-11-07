# -*- coding: utf-8 -*-
"""
scan_env.py · 讲台环境接口扫描（零硬编码）
被 env_check.py（诊断报告）和 launch_demo.py（一键启动）共用。

扫描项：Python 依赖 / 串口 / adb / 手机 / scrcpy / 浏览器 / 端口占用
所有发现均为动态搜索：PATH → 本目录 bin/ → winget 包目录 → 常见安装位置
"""
import glob
import os
import shutil
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
TARGET_VID_PID = (0x303A, 0x1001)

def _gbk_safe(s):
    return s

# ---------------------------------------------------------------- Python 依赖

def check_deps():
    ok, missing = [], []
    for mod, pipname in [('serial', 'pyserial'), ('websockets', 'websockets')]:
        try:
            __import__(mod)
            ok.append(mod)
        except ImportError:
            missing.append(pipname)
    return ok, missing

def pip_install(packages):
    cmd = ['python', '-m', 'pip', 'install', '--quiet'] + packages + [
        '-i', 'https://pypi.tuna.tsinghua.edu.cn/simple']
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=120)
        return r.returncode == 0
    except Exception:
        return False

# ---------------------------------------------------------------- 串口

def list_serial():
    try:
        import serial.tools.list_ports as lp
    except ImportError:
        return None
    ports = []
    for p in lp.comports():
        ports.append({
            'device': p.device,
            'desc': p.description,
            'vid': p.vid, 'pid': p.pid,
            'target': (p.vid, p.pid) == TARGET_VID_PID,
        })
    return ports

def find_target_port():
    ports = list_serial() or []
    hits = [p['device'] for p in ports if p['target']]
    return hits[0] if len(hits) >= 1 else None, len(hits)

# ---------------------------------------------------------------- adb / 手机

def find_adb():
    cands = []
    env = os.environ.get('PULSE_ADB')
    if env:
        cands.append(env)
    w = shutil.which('adb')
    if w:
        cands.append(w)
    cands.append(os.path.join(HERE, 'bin', 'scrcpy', 'adb.exe'))
    cands += glob.glob(os.path.join(os.environ.get('LOCALAPPDATA', ''),
                                    'Microsoft', 'WinGet', 'Packages',
                                    'Genymobile.scrcpy*', '*', 'adb.exe'))
    cands.append(os.path.join(os.environ.get('LOCALAPPDATA', ''),
                              'Android', 'Sdk', 'platform-tools', 'adb.exe'))
    cands += ['D:\\Android\\Sdk\\platform-tools\\adb.exe',
              'C:\\Android\\platform-tools\\adb.exe']
    for c in cands:
        if c and os.path.isfile(c):
            return os.path.abspath(c)
    return None

def adb_devices(adb):
    if not adb:
        return []
    try:
        r = subprocess.run([adb, 'devices', '-l'], capture_output=True,
                           timeout=10, creationflags=0x08000000)
        out = r.stdout.decode('utf-8', 'replace')
    except Exception:
        return []
    devs = []
    for line in out.splitlines()[1:]:
        line = line.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        serial, state = parts[0], parts[1]
        model = ''
        for k in parts[2:]:
            if k.startswith('model:'):
                model = k[6:]
        if serial in ('*', 'List'):
            continue
        devs.append({'serial': serial, 'state': state, 'model': model})
    return devs

def adb_prop(adb, serial, prop):
    try:
        r = subprocess.run([adb, '-s', serial, 'shell', 'getprop', prop],
                           capture_output=True, timeout=8,
                           creationflags=0x08000000)
        return r.stdout.decode('utf-8', 'replace').strip()
    except Exception:
        return ''

# ---------------------------------------------------------------- scrcpy

def find_scrcpy():
    cands = [os.path.join(HERE, 'bin', 'scrcpy', 'scrcpy.exe')]
    w = shutil.which('scrcpy')
    if w:
        cands.append(w)
    cands += glob.glob(os.path.join(os.environ.get('LOCALAPPDATA', ''),
                                    'Microsoft', 'WinGet', 'Packages',
                                    'Genymobile.scrcpy*', '*', 'scrcpy.exe'))
    cands += [r'C:\Program Files\scrcpy\scrcpy.exe',
              r'D:\Program Files\scrcpy\scrcpy.exe']
    for c in cands:
        if c and os.path.isfile(c):
            return os.path.abspath(c)
    return None

# ---------------------------------------------------------------- 浏览器

def find_browser():
    env = os.environ.get('PULSE_BROWSER')
    if env and os.path.isfile(env):
        return env, 'custom'
    la = os.environ.get('LOCALAPPDATA', '')
    pf = [os.environ.get('ProgramFiles(x86)', ''), os.environ.get('ProgramFiles', '')]
    edge = [os.path.join(pf[0], 'Microsoft', 'Edge', 'Application', 'msedge.exe'),
            os.path.join(pf[1], 'Microsoft', 'Edge', 'Application', 'msedge.exe'),
            os.path.join(la, 'Microsoft', 'Edge', 'Application', 'msedge.exe')]
    for p in edge:
        if p and os.path.isfile(p):
            return p, 'edge'
    chrome = [os.path.join(pf[0], 'Google', 'Chrome', 'Application', 'chrome.exe'),
              os.path.join(pf[1], 'Google', 'Chrome', 'Application', 'chrome.exe'),
              os.path.join(la, 'Google', 'Chrome', 'Application', 'chrome.exe')]
    for p in chrome:
        if p and os.path.isfile(p):
            return p, 'chrome'
    return None, None

# ---------------------------------------------------------------- 端口

def port_in_use(port):
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.3)
        return s.connect_ex(('127.0.0.1', port)) == 0

# ---------------------------------------------------------------- 汇总报告

GREEN, YELLOW, RED, CYAN, DIM, RESET = '\033[92m', '\033[93m', '\033[91m', '\033[96m', '\033[90m', '\033[0m'

def _mark(ok, warn=False):
    return f'{GREEN}[✓]{RESET}' if ok else (f'{YELLOW}[!]{RESET}' if warn else f'{RED}[✗]{RESET}')

def full_report():
    lines = []
    ap = lines.append
    ap(f'{CYAN}══════════ 赛博把脉 · 讲台环境扫描 ══════════{RESET}')

    ok, missing = check_deps()
    ap(f'{_mark(not missing)} Python 依赖：' + (', '.join(ok) if not missing else f'缺 {missing} → 将自动 pip 安装'))

    ports = list_serial()
    if ports is None:
        ap(f'{_mark(False)} 串口：pyserial 未安装，无法枚举')
    else:
        tgt = [p for p in ports if p['target']]
        ap(f'{_mark(len(tgt) == 1, len(tgt) > 1)} 串口设备（目标 CYBER-PULSE 303A:1001）：'
           + (f'{tgt[0]["device"]}' if len(tgt) == 1 else f'命中 {len(tgt)} 个（用第一个）' if tgt else '未命中'))
        for p in ports:
            tag = f'{GREEN}← 目标设备{RESET}' if p['target'] else ''
            desc = p['desc'] or ''
            if '蓝牙' in desc or 'Bluetooth' in desc:
                continue
            ap(f'    {DIM}- {p["device"]:6s} {desc[:40]} {tag}{RESET}')

    adb = find_adb()
    ap(f'{_mark(bool(adb))} adb：{adb or "未找到（装 scrcpy 即自带，或装 Android platform-tools）"}')
    if adb:
        devs = adb_devices(adb)
        ready = [d for d in devs if d['state'] == 'device']
        bad = [d for d in devs if d['state'] != 'device']
        if not devs:
            ap(f'{_mark(False, True)} 手机：未发现 USB 设备（检查：USB线/手机端USB调试开关/弹窗授权/换线换口）')
        for d in ready:
            ver = adb_prop(adb, d['serial'], 'ro.build.version.release')
            model = d['model'] or adb_prop(adb, d['serial'], 'ro.product.model')
            cam_ok = ver.isdigit() and int(ver) >= 12
            ap(f'{_mark(cam_ok, not cam_ok)} 手机：{model} (Android {ver}, {d["serial"]})'
               + ('' if cam_ok else ' ⚠ Android<12 不支持 scrcpy 相机，改用 MJPEG 路线'))
        for d in bad:
            ap(f'{_mark(False, True)} 手机 {d["serial"]} 状态={d["state"]}（unauthorized→手机上点允许USB调试）')

    scrcpy = find_scrcpy()
    ap(f'{_mark(bool(scrcpy))} scrcpy：{scrcpy or "未找到（把 scrcpy 目录放到 bin/scrcpy/ 或 winget install Genymobile.scrcpy）"}')

    browser, bname = find_browser()
    ap(f'{_mark(bool(browser))} 浏览器：{browser or "未找到 Edge/Chrome（Web Serial 需要 Chromium 内核）"}')

    bridge_http = port_in_use(8100)
    bridge_ws = port_in_use(8765)
    ap(f'{_mark(bridge_http and bridge_ws, not (bridge_http or bridge_ws))} 串口桥服务：'
       + ('已在运行 ✓' if bridge_http and bridge_ws else '未运行（launch_demo 会自动拉起）' if bridge_http or bridge_ws else '未运行'))

    ap(f'{CYAN}════════════════════════════════════════════{RESET}')
    return lines

def print_report():
    try:
        import colorama
        colorama.just_fix_windows_console()
    except Exception:
        pass
    for l in full_report():
        print(l, flush=True)

if __name__ == '__main__':
    print_report()
