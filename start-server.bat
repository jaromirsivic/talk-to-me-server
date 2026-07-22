@echo off
setlocal EnableExtensions

powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0server-control.ps1" -Action Start

set "EXIT_CODE=%ERRORLEVEL%"
timeout /t 5 /nobreak >nul
exit /b %EXIT_CODE%
