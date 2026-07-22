# TalkToMe Server

TalkToMe is a local, privacy-first text-to-speech server. It exposes a POST-only JSON API,
queues speech through Piper worker processes, plays it in global FIFO order, and includes a
responsive web portal for requests, settings, voices, themes, and 30 browser-local languages.

## Install on Windows

Requirements: Windows 10/11, PowerShell 5.1 or newer, internet access for the first install,
and an audio output device. Python and Piper do not need to be preinstalled.

```powershell
.\install.bat
```

The idempotent installer downloads a pinned, SHA-256-verified `uv`, installs Python 3.12 and
the locked dependencies into this project, then downloads the default
`en_US-ljspeech-medium` Piper voice. It does not change the system `PATH`.

Start the server:

```powershell
.\start-server.bat
```

Stop the server with `.\stop-server.bat`.

## Install on Linux or macOS

Requirements: x86_64 or ARM64 Linux/macOS, internet access for the first install, `curl` or
`wget`, `tar`, a SHA-256 utility, and an audio output device. Linux also needs the PortAudio
runtime library supplied by the distribution, typically the `libportaudio2` package on
Debian and Ubuntu. Python and Piper do not need to be preinstalled.

The same scripts support both operating systems:

```sh
sh ./install.sh
sh ./start-server.sh
```

Stop the server with:

```sh
sh ./stop-server.sh
```

The Unix installer downloads a pinned, SHA-256-verified `uv` archive for the detected
operating system and CPU architecture. Like the Windows installer, it keeps Python, the
environment, downloads, and cache inside this project and does not change the system `PATH`.

Open <http://127.0.0.1:44448/>. All API operations use `POST`; see
[`docs/api.md`](docs/api.md). Operational, backup, security, and recovery guidance is in
[`docs/operations.md`](docs/operations.md).

## Global playback stop shortcut

While the server is running, `Ctrl+Shift+X` requests the same playback and queue stop as
`POST /api/v1/stop`. The listener is best effort and never prevents the server from starting,
serving requests, or shutting down. If registration or dispatch fails, the server records a
`hotkey` event in its JSON log and continues without the shortcut.

The shortcut requires an interactive desktop session. macOS may require Accessibility
permission for the Python process or terminal that launches TalkToMe. Linux support depends
on the display server and desktop security policy. X11 sessions are supported by the keyboard
backend, while Wayland sessions may block global input listeners. A headless server continues
normally without the shortcut. The Control key is used on macOS, not the Command key.

## Highlights

- accepts up to 255 values of 16,384 Unicode code points each, including the full combination;
- uses 1–16 spawned Piper processes, avoiding the Python GIL for synthesis;
- keeps playback FIFO even when synthesis completes out of order;
- supports `high` requests and opportunistic `low` requests that are skipped while the
  queue is busy;
- browses the official Piper catalog and imports a user-supplied local `.onnx`/`.onnx.json`
  pair after explicit rights confirmation;
- displays request and response JSON indented with two spaces;
- supports best-effort global `Ctrl+Shift+X` playback stop from the desktop session;
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

Linux and macOS use the same project-local installation and process-control scripts. Audio
uses the existing `sounddevice` adapter, backed by PortAudio on Linux and CoreAudio on macOS.
See the portability table in [`docs/operations.md`](docs/operations.md#platform-roadmap).
