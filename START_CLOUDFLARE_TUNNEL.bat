@echo off
cd /d "%~dp0"
title Cloudflare Quick Tunnel
if not exist cloudflared.exe (
  echo cloudflared.exe was not found in this folder.
  echo Download cloudflared for Windows from the official Cloudflare website and place cloudflared.exe here.
  pause
  exit /b 1
)
echo Keep this window open. The public URL will appear below.
cloudflared.exe tunnel --url http://127.0.0.1:8787
pause
