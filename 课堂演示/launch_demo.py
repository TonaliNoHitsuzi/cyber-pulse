# -*- coding: utf-8 -*-
"""
launch_demo.py · 赛博把脉课堂演示一键启动（讲台环境零硬编码）
================================================================
流程：扫描环境 → (缺依赖自动装) → 拉起串口桥 → 拉起手机相机窗口 → 打开演示页
手机多台时列出让你选；串口/adb/scrcpy/浏览器 全部动态发现。

用法：
    python launch_demo.py            # 全套启动
    python launch_demo.py --no-cam   # 只要串口波形，不要手机摄像头
    python launch_demo.py --no-browser  # 不自动开浏览器（自己开 http://127.0.0.1:8100）
"""
import os
import subprocess
import sys
import time

import scan_env

HERE = os.path.dirname(os.path.abspath(__file__))
CREATE_NEW_CONSOLE = 0x00000010
DETACHED = 0x00000008
URL = 'http://127.0.0.1:8100/?cam=gdm'
CAM_WINDOW_TITLE = 'CYBER-CAM'


def say(tag, msg):
    colors = {'ok': '\033[92m', 'warn': '\033[93m', 'err': '\033[91m', 'info': '\033[96m'}
    try:
        import colorama
        colorama.just_fix_windows_console()
    except Exception:
        pass
    print(f"{colors.get(tag, '')}[{ {'ok':'✓','warn':'!','err':'✗','info':'·'}.get(tag, tag) }]{colors.get(tag, '') if tag in colors else ''} {msg}", flush=True)


def ensure_deps():
    ok, missing = scan_env.check_deps()
    if not missing:
        say('ok', f'依赖就绪: {", ".join(ok)}')
        return True
    say('warn', f'缺少 {missing}，尝试自动安装（清华镜像）…')
    if scan_env.pip_install(missing):
        say('ok', '安装成功')
        return True
    say('err', '自动安装失败，请手动: python -m pip install ' + ' '.join(missing))
    return False


def pick_phone(adb):
    devs = scan_env.adb_devices(adb)
    ready = [d for d in devs if d['state'] == 'device']
    bad = [d for d in devs if d['state'] != 'device']
    for d in bad:
        say('warn', f'手机 {d["serial"]} 状态 {d["state"]}（unauthorized → 看手机弹窗点允许）')
    if not ready:
        return None
    if len(ready) == 1:
        return ready[0]
    say('info', '发现多台手机：')
    for i, d in enumerate(ready, 1):
        print(f'   {i}. {d["model"] or d["serial"]}  ({d["serial"]})')
    while True:
        try:
            n = input('选择序号回车（默认1）: ').strip()
            n = int(n) if n else 1
            if 1 <= n <= len(ready):
                return ready[n - 1]
        except (EOFError, KeyboardInterrupt):
            return ready[0]
        except ValueError:
            pass
        print('输入无效，重来')


def start_bridge():
    if scan_env.port_in_use(8100) and scan_env.port_in_use(8765):
        say('ok', '串口桥已在运行，跳过')
        return True
    port, hits = scan_env.find_target_port()
    if hits == 0:
        ports = scan_env.list_serial() or []
        others = [p['device'] for p in ports
                  if not p['target'] and '蓝牙' not in (p['desc'] or '') and 'Bluetooth' not in (p['desc'] or '')]
        say('warn', '未发现目标串口 303A:1001' + (f'（其他串口: {others}，将自动等待设备插入）' if others else '（将自动等待设备插入）'))
    script = os.path.join(HERE, 'serial_bridge.py')
    subprocess.Popen([sys.executable, '-X', 'utf8', script],
                     creationflags=CREATE_NEW_CONSOLE, cwd=HERE)
    for _ in range(20):
        time.sleep(0.5)
        if scan_env.port_in_use(8100) and scan_env.port_in_use(8765):
            say('ok', f'串口桥已就绪 {URL}')
            return True
    say('err', '串口桥 20 秒内未就绪，看刚弹出的桥窗口报错')
    return False


def start_scrcpy(adb, dev):
    scrcpy = scan_env.find_scrcpy()
    if not scrcpy:
        say('err', 'scrcpy 未找到：把 scrcpy 目录放到 bin/scrcpy/ 或 winget install Genymobile.scrcpy')
        return False
    ver = scan_env.adb_prop(adb, dev['serial'], 'ro.build.version.release')
    if ver.isdigit() and int(ver) < 12:
        say('warn', f'Android {ver} < 12，scrcpy 相机不可用；演示页可改用 MJPEG 或本机摄像头')
        return False
    args = [scrcpy, '--video-source=camera', '--camera-facing=back',
            '-m1280', '--no-audio', '--stay-awake', '--window-borderless',
            '--window-title', CAM_WINDOW_TITLE]
    if dev:
        args += ['-s', dev['serial']]
    env = os.environ.copy()
    env['ADB'] = adb
    subprocess.Popen(args, creationflags=CREATE_NEW_CONSOLE, env=env,
                     cwd=os.path.dirname(scrcpy))
    say('ok', f'相机窗口启动中（{dev["model"] or dev["serial"]} 后置摄像头）→ 弹出的 CYBER-CAM 窗口即手机画面')
    return True


def start_browser():
    browser, name = scan_env.find_browser()
    if not browser:
        say('warn', '未找到 Edge/Chrome，手动打开浏览器访问 ' + URL)
        return False
    profile = os.path.join(os.environ.get('TEMP', HERE),
                           f'pulse_demo_{int(time.time())}')
    args = [browser, f'--user-data-dir={profile}', '--window-size=1500,950',
            '--no-first-run', '--no-default-browser-check',
            f'--auto-select-desktop-capture-source={CAM_WINDOW_TITLE}', URL]
    subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    say('ok', f'浏览器已拉起（{name}，独立演示档案），3 秒后出现完整界面')
    return True


def main():
    no_cam = '--no-cam' in sys.argv
    no_browser = '--no-browser' in sys.argv
    print('=' * 52)
    print(' 赛博把脉 · 课堂演示一键启动')
    print('=' * 52)
    scan_env.print_report()
    print()
    if not ensure_deps():
        sys.exit(1)

    ok_bridge = start_bridge()

    cam_ok = False
    if not no_cam:
        adb = scan_env.find_adb()
        if not adb:
            say('warn', '未找到 adb，跳过手机摄像头（演示页可用 MJPEG/本机摄像头）')
        else:
            dev = pick_phone(adb)
            if dev:
                cam_ok = start_scrcpy(adb, dev)
            else:
                say('warn', '没有已授权手机：检查 USB 线 / 开发者选项 USB 调试 / 手机弹窗')

    if not no_browser:
        time.sleep(2 if cam_ok else 0)
        start_browser()

    print()
    say('info', f'演示页地址: {URL}')
    say('info', '摄像头若未自动进画面：演示页右上角下拉框选「窗口采集(scrcpy)」→ 选 CYBER-CAM 窗口')
    say('info', '退出：直接关各窗口即可')


if __name__ == '__main__':
    main()
