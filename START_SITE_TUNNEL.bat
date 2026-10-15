@echo off
cd /d "%~dp0"
title Chorna Rada - private tunnel site
set "DOSSIER_PASSWORD="
set /p "DOSSIER_PASSWORD=Enter shared password for officers (letters and digits only): "
if not defined DOSSIER_PASSWORD (
  echo Password is empty. Stopping for safety.
  pause
  exit /b 1
)
set "DOSSIER_HOST=127.0.0.1"
py -3 server.py
if errorlevel 1 python server.py
pause
