[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("Start", "Stop")]
    [string]$Action
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$projectRoot = $PSScriptRoot
$runtimeRoot = Join-Path $projectRoot ".runtime"
$pidFile = Join-Path $runtimeRoot "server.pid"
$runScript = Join-Path $projectRoot "run.ps1"
$environmentRoot = [IO.Path]::GetFullPath((Join-Path $projectRoot ".venv"))
$environmentPrefix = $environmentRoot.TrimEnd([IO.Path]::DirectorySeparatorChar) + [IO.Path]::DirectorySeparatorChar
$pythonExe = Join-Path $environmentRoot "Scripts\python.exe"
$setupFile = Join-Path $projectRoot "data\setup.json"
if (-not (Test-Path -LiteralPath $setupFile)) {
    $setupFile = Join-Path $projectRoot "master-data\setup.json"
}
$network = (Get-Content -LiteralPath $setupFile -Raw | ConvertFrom-Json).network
$configuredPort = [int]$network.port

function Get-ProcessInfo([int]$ProcessId) {
    Get-CimInstance Win32_Process -Filter ("ProcessId = " + $ProcessId) -ErrorAction SilentlyContinue
}

function Get-ListenerProcessIds {
    @(
        Get-NetTCPConnection -LocalPort $configuredPort -State Listen -ErrorAction SilentlyContinue |
            Select-Object -ExpandProperty OwningProcess -Unique
    )
}

function Test-IsDescendant([int]$ProcessId, [int]$RootProcessId) {
    $currentId = $ProcessId
    $visited = @{}
    while ($currentId -gt 0 -and -not $visited.ContainsKey($currentId)) {
        if ($currentId -eq $RootProcessId) { return $true }
        $visited[$currentId] = $true
        $current = Get-ProcessInfo $currentId
        if (-not $current) { break }
        $currentId = [int]$current.ParentProcessId
    }
    return $false
}

function Test-ListenerBelongsToRoot([int]$RootProcessId) {
    foreach ($listenerPid in @(Get-ListenerProcessIds)) {
        if (Test-IsDescendant ([int]$listenerPid) $RootProcessId) { return $true }
    }
    return $false
}

function Test-IsControlProcess($Process) {
    return [bool](
        $Process -and
        $Process.CommandLine -and
        $Process.CommandLine.IndexOf($runScript, [StringComparison]::OrdinalIgnoreCase) -ge 0
    )
}

function Get-ProjectControlRoot($Process) {
    if (-not $Process -or -not $Process.CommandLine -or
        $Process.CommandLine.IndexOf("-m talk_to_me_server", [StringComparison]::OrdinalIgnoreCase) -lt 0) {
        return 0
    }

    $current = $Process
    $projectMarkerSeen = $false
    $controlRoot = 0
    $fallbackRoot = 0
    $visited = @{}
    while ($current -and -not $visited.ContainsKey([int]$current.ProcessId)) {
        $visited[[int]$current.ProcessId] = $true
        $commandLine = [string]$current.CommandLine
        $executablePath = [string]$current.ExecutablePath
        if (($executablePath -and [IO.Path]::GetFullPath($executablePath).StartsWith($environmentPrefix, [StringComparison]::OrdinalIgnoreCase)) -or
            ($commandLine -and $commandLine.IndexOf($pythonExe, [StringComparison]::OrdinalIgnoreCase) -ge 0)) {
            $projectMarkerSeen = $true
            $fallbackRoot = [int]$current.ProcessId
        }
        if (Test-IsControlProcess $current) {
            $controlRoot = [int]$current.ProcessId
            $projectMarkerSeen = $true
            break
        }
        if ([int]$current.ParentProcessId -le 0) { break }
        $current = Get-ProcessInfo ([int]$current.ParentProcessId)
    }
    if ($controlRoot -gt 0) { return $controlRoot }
    if ($projectMarkerSeen) { return $fallbackRoot }
    return 0
}

function Write-PortStatus {
    $listenerIds = @(Get-ListenerProcessIds)
    if ($listenerIds.Count -eq 0) {
        Write-Host ("Port " + $configuredPort + " is free. No application is listening.")
        return
    }
    Write-Host ("Port " + $configuredPort + " is in use.")
    foreach ($listenerPid in $listenerIds) {
        $owner = Get-ProcessInfo ([int]$listenerPid)
        Write-Host ("PID: " + $listenerPid)
        Write-Host ("Process: " + $(if ($owner) { $owner.Name } else { "<unknown>" }))
        Write-Host ("Command line: " + $(if ($owner -and $owner.CommandLine) { $owner.CommandLine } else { "<unavailable>" }))
    }
}

function Write-Location {
    $listenAddresses = @()
    if ($network.ipv4Enabled) { $listenAddresses += [string]$network.ipv4Address }
    if ($network.ipv6Enabled) { $listenAddresses += [string]$network.ipv6Address }
    $browserHost = if ($network.ipv4Enabled) { [string]$network.ipv4Address } else { "[" + [string]$network.ipv6Address + "]" }
    Write-Host ("Port: " + $configuredPort)
    Write-Host ("Listening addresses: " + ($listenAddresses -join ", "))
    Write-Host ("Portal URL: http://" + $browserHost + ":" + $configuredPort)
}

function Read-TrackedPid {
    if (-not (Test-Path -LiteralPath $pidFile)) { return 0 }
    try { return [int](Get-Content -LiteralPath $pidFile -Raw) }
    catch { throw "The server PID file is invalid." }
}

function Start-TalkToMeServer {
    New-Item -ItemType Directory -Force -Path $runtimeRoot | Out-Null
    $existingPid = Read-TrackedPid
    if ($existingPid -gt 0) {
        $existing = Get-ProcessInfo $existingPid
        if ($existing) {
            if (-not (Test-IsControlProcess $existing)) {
                throw "PID $existingPid does not belong to this TalkToMe server."
            }
            if (Test-ListenerBelongsToRoot $existingPid) {
                Write-Host ("TalkToMe server is already running. PID: " + $existingPid)
                Write-Location
                return
            }
            if (@(Get-ListenerProcessIds).Count -gt 0) {
                Write-PortStatus
                throw "The configured port is owned by another process, not by PID $existingPid."
            }
            throw "TalkToMe process $existingPid exists, but its process tree does not own the configured port."
        }
        Remove-Item -LiteralPath $pidFile -Force
    }

    if (@(Get-ListenerProcessIds).Count -gt 0) {
        Write-PortStatus
        throw "The configured port is owned by another process. Refusing to report a false successful start."
    }

    $stdoutPath = Join-Path $runtimeRoot "server.out.log"
    $stderrPath = Join-Path $runtimeRoot "server.err.log"
    $arguments = "-NoLogo -NoProfile -ExecutionPolicy Bypass -File `"$runScript`""
    $launcher = Start-Process -FilePath "powershell.exe" -ArgumentList $arguments -WorkingDirectory $projectRoot -WindowStyle Hidden -RedirectStandardOutput $stdoutPath -RedirectStandardError $stderrPath -PassThru
    $deadline = [DateTime]::UtcNow.AddSeconds(15)
    $trackedPid = 0
    do {
        $trackedPid = Read-TrackedPid
        if ($trackedPid -gt 0) {
            $tracked = Get-ProcessInfo $trackedPid
            if ($tracked -and (Test-IsControlProcess $tracked) -and (Test-ListenerBelongsToRoot $trackedPid)) {
                Write-Host ("TalkToMe server started. PID: " + $trackedPid)
                Write-Location
                return
            }
        }
        if ($launcher.HasExited) { break }
        Start-Sleep -Milliseconds 100
    } while ([DateTime]::UtcNow -lt $deadline)

    Write-Host "TalkToMe server failed to start."
    if (Test-Path -LiteralPath $stderrPath) { Get-Content -LiteralPath $stderrPath | Write-Host }
    if (Test-Path -LiteralPath $stdoutPath) { Get-Content -LiteralPath $stdoutPath | Write-Host }
    if (-not $launcher.HasExited) { & taskkill.exe "/PID" $launcher.Id "/T" "/F" | Out-Host }
    if (Test-Path -LiteralPath $pidFile) { Remove-Item -LiteralPath $pidFile -Force }
    throw "The launched process tree did not acquire port $configuredPort."
}

function Stop-TalkToMeServer {
    $serverPid = Read-TrackedPid
    $server = if ($serverPid -gt 0) { Get-ProcessInfo $serverPid } else { $null }
    if ($serverPid -gt 0 -and -not $server) {
        Remove-Item -LiteralPath $pidFile -Force
        $serverPid = 0
    }
    if ($server) {
        if (Test-IsControlProcess $server) {
            $serverPid = [int]$server.ProcessId
        } else {
            $serverPid = Get-ProjectControlRoot $server
            if ($serverPid -le 0) {
                Write-PortStatus
                throw "The tracked PID does not belong to this TalkToMe server. Refusing to stop it."
            }
        }
    } else {
        $roots = @(
            Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
                Where-Object { $_.CommandLine -and $_.CommandLine.IndexOf("-m talk_to_me_server", [StringComparison]::OrdinalIgnoreCase) -ge 0 } |
                ForEach-Object { Get-ProjectControlRoot $_ } |
                Where-Object { $_ -gt 0 } |
                Sort-Object -Unique
        )
        if ($roots.Count -eq 0) {
            Write-Host "TalkToMe server is not running."
            Write-PortStatus
            return
        }
        if ($roots.Count -ne 1) {
            Write-PortStatus
            throw "Multiple project TalkToMe process trees were found. Refusing to guess."
        }
        $serverPid = [int]$roots[0]
        Write-Host ("Found an untracked TalkToMe server process tree. PID: " + $serverPid)
    }

    & taskkill.exe "/PID" $serverPid "/T" "/F" | Out-Host
    if ($LASTEXITCODE -ne 0) { throw "Unable to stop TalkToMe process tree $serverPid." }
    if (Test-Path -LiteralPath $pidFile) { Remove-Item -LiteralPath $pidFile -Force }
    Write-Host "TalkToMe server stopped."
    Write-PortStatus
}

if ($Action -eq "Start") {
    Start-TalkToMeServer
} else {
    Stop-TalkToMeServer
}
