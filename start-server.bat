@echo off
setlocal EnableExtensions

set "SKIP_WAIT="
if "%~1"=="" goto start
if /I "%~1"=="skip-wait" (
    set "SKIP_WAIT=-SkipWait"
    goto start
)

echo Unknown argument: %~1>&2
exit /b 2

:start
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0server-control.ps1" -Action Start %SKIP_WAIT%
exit /b %ERRORLEVEL%
