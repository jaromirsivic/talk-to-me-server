# TalkToMe Server

TalkToMe is a local, privacy-first text-to-speech server. It exposes a POST-only JSON API,
queues speech through Piper worker processes, plays it in global FIFO order, and includes a
responsive web portal for requests, settings, voices, themes, and 30 browser-local languages.

## Install on Windows

Requirements: Windows 10/11, PowerShell 5.1 or newer, internet access for the first install,
and an audio output device. Python and Piper do not need to be preinstalled.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\install.ps1
```

The idempotent installer downloads a pinned, SHA-256-verified `uv`, installs Python 3.12 and
the locked dependencies into this project, then downloads the default
`en_US-ljspeech-medium` Piper voice. It does not change the system `PATH`.

Start the server:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\run.ps1
```

Open <http://127.0.0.1:44448/>. All API operations use `POST`; see
[`docs/api.md`](docs/api.md). Operational, backup, security, and recovery guidance is in
[`docs/operations.md`](docs/operations.md).

## Highlights

- accepts up to 255 values of 16,384 Unicode code points each, including the full combination;
- uses 1–16 spawned Piper processes, avoiding the Python GIL for synthesis;
- keeps playback FIFO even when synthesis completes out of order;
- supports `high` requests and opportunistic `low` requests that are skipped while the
  queue is busy;
- browses the official Piper catalog and imports a user-supplied local `.onnx`/`.onnx.json`
  pair after explicit rights confirmation;
- displays request and response JSON indented with two spaces;
- supports 30 locales, including Ukrainian and Norwegian, with RTL Arabic and LTR technical
  fields;
- keeps Voice, Network, and General Setup edits as drafts until an explicit Save; Cancel,
  close, and Escape discard the draft. Restart-required changes are reported but never restart
  the process automatically.

## Development

```powershell
uv sync
uv run ruff check .
uv run pytest -q
```

Browser tests require Chromium installed by Playwright. Real Piper and Windows audio smoke
tests are opt-in; the default test suite does not play sound.

Linux and macOS are planned targets. The domain, API, queue, catalog, storage, and portal are
portable; only packaging, launch scripts, and platform audio adapters need platform work.
See the portability table in [`docs/operations.md`](docs/operations.md#platform-roadmap).
