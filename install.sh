#!/bin/sh

set -eu

project_root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
runtime_root="$project_root/.runtime"
download_root="$runtime_root/downloads"
uv_root="$runtime_root/uv"
uv_version="0.11.29"

case "$(uname -s)" in
    Darwin)
        platform="apple-darwin"
        ;;
    Linux)
        platform="unknown-linux-gnu"
        ;;
    *)
        echo "Unsupported operating system. Use Windows scripts on Windows." >&2
        exit 1
        ;;
esac

case "$(uname -m)" in
    x86_64|amd64)
        architecture="x86_64"
        ;;
    arm64|aarch64)
        architecture="aarch64"
        ;;
    *)
        echo "Unsupported CPU architecture. Only x86_64 and ARM64 are supported." >&2
        exit 1
        ;;
esac

target="$architecture-$platform"
archive_name="uv-$target.tar.gz"
archive_path="$download_root/$archive_name"
archive_url="https://releases.astral.sh/github/uv/releases/download/$uv_version/$archive_name"

case "$target" in
    aarch64-apple-darwin)
        expected_sha256="61c04acc52a33ef0f331e494bdfbedcdb6c26c6970c022ed3699e5860f8930e3"
        ;;
    x86_64-apple-darwin)
        expected_sha256="c4c4de482da9ccdd076dc4fb5cfe7b740609029385c72f58606be3153602387d"
        ;;
    aarch64-unknown-linux-gnu)
        expected_sha256="94500fb064ae3c971a873cba64d94694c50677e0a4dbf78735c80509e7429919"
        ;;
    x86_64-unknown-linux-gnu)
        expected_sha256="04f8b82f5d47f0512dcd32c67a4a6f16a0ea27c81537c338fd0ad6b23cebe829"
        ;;
esac

temporary_path=""
extract_root=""
cleanup() {
    if [ -n "$extract_root" ]; then
        rm -rf "$extract_root"
    fi
    if [ -n "$temporary_path" ]; then
        rm -f "$temporary_path"
    fi
}
trap cleanup 0
trap 'exit 1' 1 2 15

calculate_sha256() {
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum "$1" | awk '{print $1}'
    elif command -v shasum >/dev/null 2>&1; then
        shasum -a 256 "$1" | awk '{print $1}'
    else
        echo "A SHA-256 utility is required: sha256sum or shasum." >&2
        return 1
    fi
}

download_archive() {
    temporary_path="$archive_path.part.$$"
    if command -v curl >/dev/null 2>&1; then
        curl --proto '=https' --tlsv1.2 -fL "$archive_url" -o "$temporary_path"
    elif command -v wget >/dev/null 2>&1; then
        wget -q "$archive_url" -O "$temporary_path"
    else
        echo "curl or wget is required to install TalkToMe." >&2
        return 1
    fi
    mv -f "$temporary_path" "$archive_path"
}

mkdir -p "$download_root" "$uv_root"

if [ ! -f "$archive_path" ] || [ "$(calculate_sha256 "$archive_path")" != "$expected_sha256" ]; then
    download_archive
fi

actual_sha256=$(calculate_sha256 "$archive_path")
if [ "$actual_sha256" != "$expected_sha256" ]; then
    echo "Downloaded uv archive failed SHA-256 verification." >&2
    exit 1
fi

extract_root="$runtime_root/uv-extract.$$"
mkdir -p "$extract_root"
tar -xzf "$archive_path" -C "$extract_root"
extracted_uv="$extract_root/uv-$target/uv"
extracted_uvx="$extract_root/uv-$target/uvx"
if [ ! -x "$extracted_uv" ]; then
    echo "The verified uv archive did not contain the expected executable." >&2
    exit 1
fi
cp "$extracted_uv" "$uv_root/uv"
chmod 755 "$uv_root/uv"
if [ -x "$extracted_uvx" ]; then
    cp "$extracted_uvx" "$uv_root/uvx"
    chmod 755 "$uv_root/uvx"
fi

uv_bin="$uv_root/uv"
export UV_CACHE_DIR="$runtime_root/cache"
export UV_PYTHON_INSTALL_DIR="$runtime_root/python"
export UV_PYTHON_BIN_DIR="$runtime_root/python-bin"
export UV_PROJECT_ENVIRONMENT="$project_root/.venv"

cd "$project_root"
"$uv_bin" python install 3.12
"$uv_bin" sync --frozen --no-dev
"$uv_bin" run --frozen --no-dev python -c "import sounddevice"
"$uv_bin" run --frozen --no-dev python -m talk_to_me_server.bootstrap --download-default-voice

uv_description=$("$uv_bin" --version)
python_description=$("$uv_bin" run --frozen --no-dev python --version)
"$uv_bin" run --frozen --no-dev python - "$runtime_root/install-state.json" "$uv_description" "$python_description" <<'PY'
import datetime
import json
import pathlib
import sys

state = {
    "installedAt": datetime.datetime.now().astimezone().isoformat(),
    "uvVersion": sys.argv[2],
    "pythonVersion": sys.argv[3],
    "defaultVoice": "en_US-ljspeech-medium",
}
pathlib.Path(sys.argv[1]).write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
PY

echo "TalkToMe is installed locally."
echo "Run: sh $project_root/start-server.sh"
echo "Data: $project_root/data"
