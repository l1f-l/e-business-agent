@echo off
REM ShopPilot demo launcher: backend + frontend + public tunnel
chcp 65001 >nul
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -Command "[Console]::OutputEncoding=[Text.Encoding]::UTF8; & '%~dp0demo-remote.ps1'"
pause
