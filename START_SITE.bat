@echo off
cd /d "%~dp0"
title Chorna Rada Web v0.9
py -3 server.py
if errorlevel 1 python server.py
pause
