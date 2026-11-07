@echo off
chcp 65001 >nul
title 打包到 E:\汇报文件
cd /d "%~dp0"
set "DST=E:\汇报文件"

if not exist "E:\演示环境\node\node-v22.14.0-win-x64\node.exe" (
  echo [x] 找不到 E:\演示环境\node 的可移植 Node。
  pause
  exit /b 1
)

echo 同步 汇报讲稿 ...
robocopy "汇报讲稿" "%DST%\汇报讲稿" /MIR /XD __pycache__ /NFL /NDL /NJH /NJS /NP >nul
echo 同步 课堂演示 ...
robocopy "课堂演示" "%DST%\课堂演示" /MIR /XD __pycache__ /XF bridge.log bridge.err /NFL /NDL /NJH /NJS /NP >nul
echo 同步 Node 运行时 ...
robocopy "E:\演示环境\node\node-v22.14.0-win-x64" "%DST%\runtime\node" /E /NFL /NDL /NJH /NJS /NP >nul
copy /y "一键启动.bat" "%DST%\一键启动.bat" >nul

echo.
echo 已完成：%DST%
echo 入口：双击 %DST%\一键启动.bat
pause
