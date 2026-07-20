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
    text = Path("Install.bat").read_text(encoding="utf-8").lower()

    assert "%~dp0install.ps1" in text
    assert "-executionpolicy bypass" in text
    assert "exit /b %exit_code%" in text


def test_start_batch_launches_one_tracked_server_process() -> None:
    text = Path("startserver.bat").read_text(encoding="utf-8").lower()

    assert "run.ps1" in text
    assert "server.pid" in text
    assert "start-process" in text
    assert "-passthru" in text
    assert "get-ciminstance" in text


def test_start_batch_waits_for_listener_and_prints_browser_url_last() -> None:
    text = Path("startserver.bat").read_text(encoding="utf-8")

    assert "Get-NetTCPConnection" in text
    assert "RedirectStandardError" in text
    assert "Set-Content -LiteralPath $pidFile" not in text
    assert "$network.ipv4Address" in text
    assert "$network.port" in text
    message = "Portal URL: "
    assert message in text
    assert text.rindex("& $writeLocation") > text.index("TalkToMe server started.")
    assert "PID: " in text
    assert "Port: " in text
    assert "Listening addresses: " in text
    assert "timeout /t 5 /nobreak" in text.lower()


def test_stop_batch_validates_and_stops_only_the_tracked_process_tree() -> None:
    text = Path("stopserver.bat").read_text(encoding="utf-8").lower()

    assert "server.pid" in text
    assert "get-ciminstance" in text
    assert "commandline" in text
    assert "taskkill.exe" in text
    assert any(quoted in text for quoted in ('"/t"', "'/t'"))
    assert any(quoted in text for quoted in ('"/f"', "'/f'"))


def test_stop_batch_finds_a_legacy_project_server_when_pid_file_is_missing() -> None:
    text = Path("stopserver.bat").read_text(encoding="utf-8").lower()

    assert "if (-not (test-path -literalpath $pidfile)) { write-host 'talktome server is not running.'; exit 0 }" not in text
    assert ".venv" in text
    assert "-m talk_to_me_server" in text
    assert "executablepath" in text
    assert "parentprocessid" in text


def test_stop_batch_always_reports_configured_port_owner() -> None:
    text = Path("stopserver.bat").read_text(encoding="utf-8").lower()

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
