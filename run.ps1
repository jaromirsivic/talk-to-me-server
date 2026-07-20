[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$projectRoot = $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$runtimeRoot = Join-Path $projectRoot ".runtime"
$environmentRoot = Join-Path $projectRoot ".venv"
$pythonExe = Join-Path $environmentRoot "Scripts\python.exe"
$pidFile = Join-Path $runtimeRoot "server.pid"

$env:UV_CACHE_DIR = Join-Path $runtimeRoot "cache"
$env:UV_PYTHON_INSTALL_DIR = Join-Path $runtimeRoot "python"
$env:UV_PYTHON_BIN_DIR = Join-Path $runtimeRoot "python-bin"
$env:UV_PROJECT_ENVIRONMENT = $environmentRoot

if (-not (Test-Path -LiteralPath $pythonExe)) {
    throw "Local Python environment is missing. Run install.ps1 first."
}

New-Item -ItemType Directory -Force -Path $runtimeRoot | Out-Null
Set-Content -LiteralPath $pidFile -Value $PID -Encoding ASCII
$serverExitCode = 1
try {
    & $pythonExe -m talk_to_me_server
    $serverExitCode = $LASTEXITCODE
}
finally {
    if (Test-Path -LiteralPath $pidFile) {
        try { $recordedPid = [int](Get-Content -LiteralPath $pidFile -Raw) }
        catch { $recordedPid = 0 }
        if ($recordedPid -eq $PID) {
            Remove-Item -LiteralPath $pidFile -Force
        }
    }
}
exit $serverExitCode
