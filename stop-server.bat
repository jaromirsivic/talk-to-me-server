@echo off
setlocal EnableExtensions

powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0server-control.ps1" -Action Stop

set "EXIT_CODE=%ERRORLEVEL%"
exit /b %EXIT_CODE%
