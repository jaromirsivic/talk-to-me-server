@echo off
setlocal EnableExtensions
set "TALK_TO_ME_ROOT=%~dp0"

powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference = 'Stop';" ^
  "$root = [IO.Path]::GetFullPath($env:TALK_TO_ME_ROOT);" ^
  "$runtime = Join-Path $root '.runtime';" ^
  "$pidFile = Join-Path $runtime 'server.pid';" ^
  "$runScript = Join-Path $root 'run.ps1';" ^
  "$environmentRoot = [IO.Path]::GetFullPath((Join-Path $root '.venv'));" ^
  "$environmentPrefix = $environmentRoot.TrimEnd([IO.Path]::DirectorySeparatorChar) + [IO.Path]::DirectorySeparatorChar;" ^
  "$setupFile = Join-Path $root 'data\setup.json';" ^
  "if (-not (Test-Path -LiteralPath $setupFile)) { $setupFile = Join-Path $root 'master-data\setup.json' };" ^
  "$configuredPort = [int]((Get-Content -LiteralPath $setupFile -Raw | ConvertFrom-Json).network.port);" ^
  "$writePortStatus = {" ^
  "  $listeners = @(Get-NetTCPConnection -LocalPort $configuredPort -State Listen -ErrorAction SilentlyContinue);" ^
  "  if ($listeners.Count -eq 0) { Write-Host ('Port ' + $configuredPort + ' is free. No application is listening.'); return };" ^
  "  Write-Host ('Port ' + $configuredPort + ' is in use.');" ^
  "  foreach ($processPid in @($listeners | Select-Object -ExpandProperty OwningProcess -Unique)) {" ^
  "    $owner = Get-CimInstance Win32_Process -Filter ('ProcessId = ' + $processPid) -ErrorAction SilentlyContinue;" ^
  "    Write-Host ('PID: ' + $processPid);" ^
  "    Write-Host ('Process: ' + $(if ($owner) { $owner.Name } else { '<unknown>' }));" ^
  "    Write-Host ('Command line: ' + $(if ($owner -and $owner.CommandLine) { $owner.CommandLine } else { '<unavailable>' }))" ^
  "  }" ^
  "};" ^
  "$isProjectServer = { param($process)" ^
  "  if (-not $process -or -not $process.CommandLine -or -not $process.ExecutablePath) { return $false };" ^
  "  $executable = [IO.Path]::GetFullPath($process.ExecutablePath);" ^
  "  return $executable.StartsWith($environmentPrefix, [StringComparison]::OrdinalIgnoreCase) -and $process.CommandLine.IndexOf('-m talk_to_me_server', [StringComparison]::OrdinalIgnoreCase) -ge 0" ^
  "};" ^
  "$server = $null; $serverPid = 0;" ^
  "if (Test-Path -LiteralPath $pidFile) {" ^
  "  try { $serverPid = [int](Get-Content -LiteralPath $pidFile -Raw) } catch { & $writePortStatus; Write-Error 'The server PID file is invalid.'; exit 1 };" ^
  "  $server = Get-CimInstance Win32_Process -Filter ('ProcessId = ' + $serverPid) -ErrorAction SilentlyContinue;" ^
  "  if (-not $server) { Remove-Item -LiteralPath $pidFile -Force; $serverPid = 0 };" ^
  "  if ($server -and (-not $server.CommandLine -or ($server.CommandLine.IndexOf($runScript, [StringComparison]::OrdinalIgnoreCase) -lt 0 -and -not (& $isProjectServer $server)))) {" ^
  "    & $writePortStatus; Write-Error ('PID ' + $serverPid + ' does not belong to this TalkToMe server. Refusing to stop it.'); exit 1" ^
  "  }" ^
  "};" ^
  "if (-not $server) {" ^
  "  $candidates = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object { & $isProjectServer $_ });" ^
  "  $candidateIds = @($candidates | ForEach-Object { $_.ProcessId });" ^
  "  $roots = @($candidates | Where-Object { $_.ParentProcessId -notin $candidateIds });" ^
  "  if ($roots.Count -eq 0) { Write-Host 'TalkToMe server is not running.'; & $writePortStatus; exit 0 };" ^
  "  if ($roots.Count -ne 1) { & $writePortStatus; Write-Error 'Multiple untracked TalkToMe server processes were found. Refusing to guess.'; exit 1 };" ^
  "  $server = $roots[0]; $serverPid = [int]$server.ProcessId;" ^
  "  Write-Host ('Found an untracked TalkToMe server. PID: ' + $serverPid)" ^
  "};" ^
  "& taskkill.exe '/PID' $serverPid '/T' '/F' | Out-Host;" ^
  "if ($LASTEXITCODE -ne 0) { & $writePortStatus; exit $LASTEXITCODE };" ^
  "if (Test-Path -LiteralPath $pidFile) { Remove-Item -LiteralPath $pidFile -Force };" ^
  "Write-Host 'TalkToMe server stopped.';" ^
  "& $writePortStatus"

set "EXIT_CODE=%ERRORLEVEL%"
exit /b %EXIT_CODE%
