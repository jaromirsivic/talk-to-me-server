@echo off
setlocal EnableExtensions

powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1"
set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" echo TalkToMe installation failed with exit code %EXIT_CODE%.
exit /b %EXIT_CODE%
