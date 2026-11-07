@echo off
chcp 65001 >nul
title 赛博把脉 · 汇报入口
set "ROOT=%~dp0"

set "NODE=%ROOT%runtime\node\node.exe"
if not exist "%NODE%" (
  where node >nul 2>nul
  if errorlevel 1 (
    echo [x] 找不到内置 Node 运行时，也没有 node 命令。
    pause
    exit /b 1
  )
  set "NODE=node"
)

netstat -ano | findstr ":8088" | findstr "LISTENING" >nul
if not errorlevel 1 (
  start "" "http://127.0.0.1:8088/"
  exit /b 0
)

start "讲稿服务（关此窗口=停止）" "%NODE%" "%ROOT%汇报讲稿\serve.js" 8088
timeout /t 2 /nobreak >nul
start "" "http://127.0.0.1:8088/"
exit /b 0
