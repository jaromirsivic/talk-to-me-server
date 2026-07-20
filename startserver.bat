@echo off
setlocal EnableExtensions
set "TALK_TO_ME_ROOT=%~dp0"

powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference = 'Stop';" ^
  "$root = [IO.Path]::GetFullPath($env:TALK_TO_ME_ROOT);" ^
  "$runtime = Join-Path $root '.runtime';" ^
  "$pidFile = Join-Path $runtime 'server.pid';" ^
  "$runScript = Join-Path $root 'run.ps1';" ^
  "$setupFile = Join-Path $root 'data\setup.json';" ^
  "if (-not (Test-Path -LiteralPath $setupFile)) { $setupFile = Join-Path $root 'master-data\setup.json' };" ^
  "$network = (Get-Content -LiteralPath $setupFile -Raw | ConvertFrom-Json).network;" ^
  "$listenAddresses = @();" ^
  "if ($network.ipv4Enabled) { $listenAddresses += [string]$network.ipv4Address };" ^
  "if ($network.ipv6Enabled) { $listenAddresses += [string]$network.ipv6Address };" ^
  "$browserHost = if ($network.ipv4Enabled) { [string]$network.ipv4Address } else { '[' + [string]$network.ipv6Address + ']' };" ^
  "$browserUrl = 'http://' + $browserHost + ':' + $network.port;" ^
  "$writeLocation = {" ^
  "  Write-Host ('Port: ' + $network.port);" ^
  "  Write-Host ('Listening addresses: ' + ($listenAddresses -join ', '));" ^
  "  Write-Host ('Portal URL: ' + $browserUrl)" ^
  "};" ^
  "New-Item -ItemType Directory -Force -Path $runtime | Out-Null;" ^
  "if (Test-Path -LiteralPath $pidFile) {" ^
  "  try { $existingPid = [int](Get-Content -LiteralPath $pidFile -Raw) } catch { $existingPid = 0 };" ^
  "  if ($existingPid -gt 0) {" ^
  "    $existing = Get-CimInstance Win32_Process -Filter ('ProcessId = ' + $existingPid) -ErrorAction SilentlyContinue;" ^
  "    $listener = Get-NetTCPConnection -LocalPort ([int]$network.port) -State Listen -ErrorAction SilentlyContinue;" ^
  "    if ($existing -and $existing.CommandLine -and $existing.CommandLine.IndexOf($runScript, [StringComparison]::OrdinalIgnoreCase) -ge 0 -and $listener) {" ^
  "      Write-Host ('TalkToMe server is already running. PID: ' + $existingPid); & $writeLocation; exit 0" ^
  "    }" ^
  "  };" ^
  "  Remove-Item -LiteralPath $pidFile -Force" ^
  "};" ^
  "$stdoutPath = Join-Path $runtime 'server.out.log';" ^
  "$stderrPath = Join-Path $runtime 'server.err.log';" ^
  "$arguments = '-NoLogo -NoProfile -ExecutionPolicy Bypass -File ""' + $runScript + '""';" ^
  "$launcher = Start-Process -FilePath 'powershell.exe' -ArgumentList $arguments -WorkingDirectory $root -WindowStyle Hidden -RedirectStandardOutput $stdoutPath -RedirectStandardError $stderrPath -PassThru;" ^
  "$deadline = [DateTime]::UtcNow.AddSeconds(15);" ^
  "$trackedPid = 0; $tracked = $null; $listener = $null;" ^
  "do {" ^
  "  if (Test-Path -LiteralPath $pidFile) {" ^
  "    try { $trackedPid = [int](Get-Content -LiteralPath $pidFile -Raw) } catch { $trackedPid = 0 };" ^
  "    if ($trackedPid -gt 0) { $tracked = Get-CimInstance Win32_Process -Filter ('ProcessId = ' + $trackedPid) -ErrorAction SilentlyContinue }" ^
  "  };" ^
  "  $listener = Get-NetTCPConnection -LocalPort ([int]$network.port) -State Listen -ErrorAction SilentlyContinue;" ^
  "  if ($tracked -and $listener) { break };" ^
  "  if ($launcher.HasExited) { break };" ^
  "  Start-Sleep -Milliseconds 100" ^
  "} while ([DateTime]::UtcNow -lt $deadline);" ^
  "if (-not $tracked -or -not $listener) {" ^
  "  Write-Host 'TalkToMe server failed to start.';" ^
  "  if (Test-Path -LiteralPath $stderrPath) { Get-Content -LiteralPath $stderrPath | Write-Host };" ^
  "  if (Test-Path -LiteralPath $stdoutPath) { Get-Content -LiteralPath $stdoutPath | Write-Host };" ^
  "  if (Test-Path -LiteralPath $pidFile) {" ^
  "    try { $failedPid = [int](Get-Content -LiteralPath $pidFile -Raw) } catch { $failedPid = 0 };" ^
  "    if ($failedPid -eq $launcher.Id -or -not (Get-CimInstance Win32_Process -Filter ('ProcessId = ' + $failedPid) -ErrorAction SilentlyContinue)) { Remove-Item -LiteralPath $pidFile -Force }" ^
  "  };" ^
  "  exit 1" ^
  "};" ^
  "Write-Host ('TalkToMe server started. PID: ' + $trackedPid);" ^
  "& $writeLocation"

set "EXIT_CODE=%ERRORLEVEL%"
timeout /t 5 /nobreak >nul
exit /b %EXIT_CODE%
