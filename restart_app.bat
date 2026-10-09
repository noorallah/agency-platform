@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0restart_app.ps1" %*
if errorlevel 1 pause
