@echo off
chcp 65001 >nul
title 赛博把脉-课堂演示启动器
cd /d "%~dp0"
echo ============================================
echo   赛博把脉 CYBER-PULSE 课堂演示一键启动
echo ============================================
set "PY=%~dp0runtime\python\python.exe"
if exist "%PY%" goto run
where python >nul 2>nul
if errorlevel 1 (
  echo.
  echo  [!] 未找到内置运行时，本机也没有 Python，走零依赖兜底：
  echo      1. 双击 bin\scrcpy\scrcpy.exe 开相机窗口 ^(命令行参数在演示手册第2步^)
  echo      2. 双击 index.html，页面里点「接入 Web Serial」选串口
  echo      3. 右上下拉选「窗口采集」选 CYBER-CAM
  echo.
  pause
  exit /b 1
)
set "PY=python"
:run
"%PY%" -X utf8 launch_demo.py
echo.
echo 启动脚本结束（各窗口独立运行，关闭窗口即退出对应组件）
pause
