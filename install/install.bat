@echo off
REM Double-click entry point for the Agency Platform installer.
REM
REM Everything real happens in install.ps1. This exists because a Windows user
REM given a repository and told to install it will double-click, and PowerShell
REM will not run an unsigned script from Explorer without -ExecutionPolicy
REM Bypass. Any arguments given here are passed straight through.
REM
REM   install.bat -DryRun
REM   install.bat -BindHost 0.0.0.0 -WithDemoData

setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1" %*
set EXITCODE=%ERRORLEVEL%

REM Keep the window open when double-clicked, so the reason for a failure is
REM readable instead of vanishing with the console.
if "%~1"=="" pause
exit /b %EXITCODE%
