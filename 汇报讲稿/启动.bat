@echo off
chcp 65001 >nul
title 赛博把脉 · 汇报讲稿
cd /d "%~dp0"
set "NODE=%~dp0..\runtime\node\node.exe"
if not exist "%NODE%" set "NODE=E:\演示环境\node\node-v22.14.0-win-x64\node.exe"
if not exist "%NODE%" set "NODE=node"

netstat -ano | findstr ":8088" | findstr "LISTENING" >nul
if not errorlevel 1 (
  start "" "http://127.0.0.1:8088/"
  exit /b 0
)

echo 正在启动本地服务器...
start "讲稿服务（关此窗口=停止）" "%NODE%" serve.js 8088
timeout /t 2 /nobreak >nul
start "" "http://127.0.0.1:8088/"
exit /b 0
