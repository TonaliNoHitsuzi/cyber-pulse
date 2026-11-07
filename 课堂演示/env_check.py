# -*- coding: utf-8 -*-
"""
env_check.py · 讲台环境体检（只诊断，不启动任何东西）
用法：python env_check.py
"""
import scan_env

def main():
    scan_env.print_report()
    print()
    print('体检说明：')
    print('  [✓] 就绪  [!] 有替补路线  [✗] 需要处理')
    print('  串口目标 = USB 串行设备 (VID:PID 303A:1001，自动枚举，无需关心 COM 号)')
    print('  全绿即可运行 launch_demo.py 一键启动')
    print('  无 Python 环境的机器：双击 index.html 走 Web Serial 直连（浏览器内点「接入 Web Serial」）')

if __name__ == '__main__':
    main()
