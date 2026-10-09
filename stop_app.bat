@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0stop_app.ps1" %*
if errorlevel 1 pause
