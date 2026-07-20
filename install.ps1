[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$projectRoot = $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$runtimeRoot = Join-Path $projectRoot ".runtime"
$downloadRoot = Join-Path $runtimeRoot "downloads"
$uvRoot = Join-Path $runtimeRoot "uv"
$manifestPath = Join-Path $projectRoot "master-data\install-manifest.json"
$manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json

$env:UV_CACHE_DIR = Join-Path $runtimeRoot "cache"
$env:UV_PYTHON_INSTALL_DIR = Join-Path $runtimeRoot "python"
$env:UV_PYTHON_BIN_DIR = Join-Path $runtimeRoot "python-bin"
$env:UV_PROJECT_ENVIRONMENT = Join-Path $projectRoot ".venv"

New-Item -ItemType Directory -Force -Path $downloadRoot, $uvRoot | Out-Null
$uvArchive = Join-Path $downloadRoot ("uv-" + $manifest.uv.version + ".zip")
$uvExe = Join-Path $uvRoot "uv.exe"

$downloadRequired = -not (Test-Path -LiteralPath $uvArchive)
if (-not $downloadRequired) {
    $actualHash = (Get-FileHash -LiteralPath $uvArchive -Algorithm SHA256).Hash.ToLowerInvariant()
    $downloadRequired = $actualHash -ne $manifest.uv.sha256
}
if ($downloadRequired) {
    Invoke-WebRequest -Uri $manifest.uv.url -OutFile $uvArchive -UseBasicParsing
}
$actualHash = (Get-FileHash -LiteralPath $uvArchive -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actualHash -ne $manifest.uv.sha256) {
    throw "Downloaded uv archive failed SHA-256 verification."
}

Expand-Archive -LiteralPath $uvArchive -DestinationPath $uvRoot -Force
if (-not (Test-Path -LiteralPath $uvExe)) {
    throw "The verified uv archive did not contain uv.exe."
}

& $uvExe python install 3.12
if ($LASTEXITCODE -ne 0) { throw "uv python install failed." }
& $uvExe sync --frozen --no-dev
if ($LASTEXITCODE -ne 0) { throw "uv sync failed." }
& $uvExe run --frozen --no-dev python -m talk_to_me_server.bootstrap --download-default-voice
if ($LASTEXITCODE -ne 0) { throw "TalkToMe bootstrap failed." }

$state = [ordered]@{
    installedAt = [DateTimeOffset]::Now.ToString("o")
    uvVersion = (& $uvExe --version)
    pythonVersion = (& $uvExe run --frozen --no-dev python --version)
    defaultVoice = "en_US-ljspeech-medium"
}
$state | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $runtimeRoot "install-state.json") -Encoding UTF8

Write-Host "TalkToMe is installed locally."
Write-Host ("Run: powershell -NoProfile -ExecutionPolicy Bypass -File `"" + (Join-Path $projectRoot "run.ps1") + "`"")
Write-Host ("Data: " + (Join-Path $projectRoot "data"))
