@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start_app.ps1" %*
if errorlevel 1 pause
