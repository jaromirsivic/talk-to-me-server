import json
from pathlib import Path


def test_install_script_is_project_local_and_pinned() -> None:
    text = Path("install.ps1").read_text(encoding="utf-8")

    assert "$PSScriptRoot" in text
    assert "Set-Location -LiteralPath $projectRoot" in text
    assert "$env:PATH" not in text
    assert "python install 3.12" in text
    assert "en_US-ljspeech-medium" in text
    assert "D:/git/voice" not in text.replace("\\", "/")
    assert "$uvExe sync --frozen --no-dev" in text
    assert "Get-FileHash" in text


def test_run_script_never_installs_or_downloads() -> None:
    text = Path("run.ps1").read_text(encoding="utf-8")

    assert "$PSScriptRoot" in text
    assert "Set-Location -LiteralPath $projectRoot" in text
    assert "$env:PATH" not in text
    assert 'Join-Path $environmentRoot "Scripts\\python.exe"' in text
    assert "& $pythonExe -m talk_to_me_server" in text
    assert "Local uv is missing" not in text
    assert "uv run" not in text
    assert "Invoke-WebRequest" not in text
    assert "python install" not in text
    assert "uv sync" not in text


def test_run_script_tracks_its_own_pid_and_removes_only_its_pid_file() -> None:
    text = Path("run.ps1").read_text(encoding="utf-8")

    assert 'Join-Path $runtimeRoot "server.pid"' in text
    assert "Set-Content -LiteralPath $pidFile -Value $PID" in text
    assert "finally" in text
    assert "$recordedPid -eq $PID" in text


def test_install_batch_delegates_to_install_script_and_preserves_exit_code() -> None:
    text = Path("install.bat").read_text(encoding="utf-8").lower()

    assert "%~dp0install.ps1" in text
    assert "-executionpolicy bypass" in text
    assert "exit /b %exit_code%" in text


def test_start_batch_launches_one_tracked_server_process() -> None:
    text = Path("start-server.bat").read_text(encoding="utf-8").lower()
    control = Path("server-control.ps1").read_text(encoding="utf-8").lower()

    assert "server-control.ps1" in text
    assert "-action start" in text
    assert "run.ps1" in control
    assert "server.pid" in control
    assert "start-process" in control
    assert "-passthru" in control
    assert "get-ciminstance" in control


def test_start_batch_waits_for_listener_and_prints_browser_url_last() -> None:
    text = Path("server-control.ps1").read_text(encoding="utf-8")

    assert "Get-NetTCPConnection" in text
    assert "Test-ListenerBelongsToRoot" in text
    assert "configured port is owned by another process" in text
    assert "RedirectStandardError" in text
    assert "Set-Content -LiteralPath $pidFile" not in text
    assert "$network.ipv4Address" in text
    assert "$network.port" in text
    message = "Portal URL: "
    assert message in text
    assert text.rindex("Write-Location") > text.index("TalkToMe server started.")
    assert "PID: " in text
    assert "Port: " in text
    assert "Listening addresses: " in text
    wrapper = Path("start-server.bat").read_text(encoding="utf-8").lower()
    assert "timeout /t 5 /nobreak" in wrapper


def test_stop_batch_validates_and_stops_only_the_tracked_process_tree() -> None:
    text = Path("stop-server.bat").read_text(encoding="utf-8").lower()
    control = Path("server-control.ps1").read_text(encoding="utf-8").lower()

    assert "server-control.ps1" in text
    assert "-action stop" in text
    assert "server.pid" in control
    assert "get-ciminstance" in control
    assert "commandline" in control
    assert "taskkill.exe" in control
    assert any(quoted in control for quoted in ('"/t"', "'/t'"))
    assert any(quoted in control for quoted in ('"/f"', "'/f'"))


def test_stop_batch_finds_a_legacy_project_server_when_pid_file_is_missing() -> None:
    text = Path("server-control.ps1").read_text(encoding="utf-8").lower()

    assert "if (-not (test-path -literalpath $pidfile)) { write-host 'talktome server is not running.'; exit 0 }" not in text
    assert ".venv" in text
    assert "-m talk_to_me_server" in text
    assert "executablepath" in text
    assert "parentprocessid" in text
    assert "get-projectcontrolroot" in text


def test_stop_batch_always_reports_configured_port_owner() -> None:
    text = Path("server-control.ps1").read_text(encoding="utf-8").lower()

    assert "data\\setup.json" in text
    assert "master-data\\setup.json" in text
    assert "get-nettcpconnection" in text
    assert "localport" in text
    assert "owningprocess" in text
    assert "port " in text and " is free" in text
    assert "pid: " in text
    assert "process: " in text
    assert "command line: " in text


def test_install_manifest_pins_official_uv_artifact() -> None:
    manifest = json.loads(
        Path("master-data/install-manifest.json").read_text(encoding="utf-8")
    )

    assert manifest["uv"]["version"] == "0.11.29"
    assert manifest["uv"]["sha256"] == (
        "a047d55651bc3e0ca24595b25ec4cfcb10f9dca9fb56514e661269b37d4fae68"
    )
    assert manifest["defaultVoice"]["id"] == "en_US-ljspeech-medium"


def test_unix_installer_supports_linux_and_macos_without_system_install() -> None:
    text = Path("install.sh").read_text(encoding="utf-8")

    assert 'Darwin)' in text
    assert 'Linux)' in text
    assert 'x86_64|amd64)' in text
    assert 'arm64|aarch64)' in text
    assert 'UV_PROJECT_ENVIRONMENT="$project_root/.venv"' in text
    assert 'python install 3.12' in text
    assert 'sync --frozen --no-dev' in text
    assert 'bootstrap --download-default-voice' in text
    assert 'sha256sum' in text and 'shasum -a 256' in text
    assert '/usr/local' not in text
    assert 'sudo ' not in text


def test_unix_start_script_tracks_and_validates_the_server() -> None:
    text = Path("start-server.sh").read_text(encoding="utf-8")

    assert '.venv/bin/python' in text
    assert 'server.pid' in text
    assert 'nohup "$python_bin" -m talk_to_me_server' in text
    assert 'ps -p "$server_pid" -o command=' in text
    assert 'Portal URL: ' in text
    assert 'socket.create_connection' in text
    assert 'listener_belongs_to_server' in text
    assert 'listener_pids' in text
    assert 'configured port is owned by another process' in text


def test_unix_stop_script_only_stops_the_validated_server() -> None:
    text = Path("stop-server.sh").read_text(encoding="utf-8")

    assert 'server.pid' in text
    assert 'ps -p "$server_pid" -o command=' in text
    assert 'Refusing to stop it' in text
    assert 'kill -TERM "$server_pid"' in text
    assert 'kill -KILL "$server_pid"' in text
    assert 'listener_belongs_to_server' in text
