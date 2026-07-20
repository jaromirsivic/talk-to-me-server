#!/bin/sh

set -eu

project_root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
runtime_root="$project_root/.runtime"
python_bin="$project_root/.venv/bin/python"
pid_file="$runtime_root/server.pid"
stdout_path="$runtime_root/server.out.log"
stderr_path="$runtime_root/server.err.log"
setup_file="$project_root/data/setup.json"

if [ ! -f "$setup_file" ]; then
    setup_file="$project_root/master-data/setup.json"
fi
if [ ! -x "$python_bin" ]; then
    echo "Local Python environment is missing. Run sh ./install.sh first." >&2
    exit 1
fi

network_info=$(
    "$python_bin" - "$setup_file" <<'PY'
import json
import pathlib
import sys

network = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))["network"]
addresses = []
if network["ipv4Enabled"]:
    addresses.append(network["ipv4Address"])
if network["ipv6Enabled"]:
    addresses.append(network["ipv6Address"])
host = network["ipv4Address"] if network["ipv4Enabled"] else f'[{network["ipv6Address"]}]'
print(network["port"])
print(", ".join(addresses))
print(f'http://{host}:{network["port"]}')
PY
)
port=$(printf '%s\n' "$network_info" | sed -n '1p')
listen_addresses=$(printf '%s\n' "$network_info" | sed -n '2p')
portal_url=$(printf '%s\n' "$network_info" | sed -n '3p')

port_is_open() {
    "$python_bin" - "$setup_file" <<'PY' >/dev/null 2>&1
import json
import pathlib
import socket
import sys

network = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))["network"]
hosts = []
if network["ipv4Enabled"]:
    hosts.append("127.0.0.1" if network["ipv4Address"] == "0.0.0.0" else network["ipv4Address"])
if network["ipv6Enabled"]:
    hosts.append("::1" if network["ipv6Address"] == "::" else network["ipv6Address"])
for host in hosts:
    try:
        with socket.create_connection((host, network["port"]), timeout=0.25):
            raise SystemExit(0)
    except OSError:
        pass
raise SystemExit(1)
PY
}

is_project_server() {
    server_command=$(ps -p "$server_pid" -o command= 2>/dev/null || true)
    case "$server_command" in
        *"$python_bin"*"-m talk_to_me_server"*) return 0 ;;
        *) return 1 ;;
    esac
}

write_location() {
    echo "Port: $port"
    echo "Listening addresses: $listen_addresses"
    echo "Portal URL: $portal_url"
}

mkdir -p "$runtime_root"
if [ -f "$pid_file" ]; then
    server_pid=$(tr -d '[:space:]' < "$pid_file")
    case "$server_pid" in
        ''|*[!0-9]*) server_pid=0 ;;
    esac
    if [ "$server_pid" -gt 0 ] && kill -0 "$server_pid" 2>/dev/null; then
        if ! is_project_server; then
            echo "PID $server_pid does not belong to this TalkToMe server." >&2
            exit 1
        fi
        if port_is_open; then
            echo "TalkToMe server is already running. PID: $server_pid"
            write_location
            exit 0
        fi
        echo "TalkToMe process $server_pid exists, but the configured port is not ready." >&2
        echo "Inspect $stderr_path and $stdout_path before retrying." >&2
        exit 1
    fi
    rm -f "$pid_file"
fi

cd "$project_root"
nohup "$python_bin" -m talk_to_me_server >"$stdout_path" 2>"$stderr_path" </dev/null &
server_pid=$!
printf '%s\n' "$server_pid" > "$pid_file"

attempt=0
while [ "$attempt" -lt 150 ]; do
    if ! kill -0 "$server_pid" 2>/dev/null; then
        break
    fi
    if port_is_open; then
        echo "TalkToMe server started. PID: $server_pid"
        write_location
        exit 0
    fi
    attempt=$((attempt + 1))
    sleep 0.1
done

echo "TalkToMe server failed to start." >&2
if [ -s "$stderr_path" ]; then
    cat "$stderr_path" >&2
fi
if [ -s "$stdout_path" ]; then
    cat "$stdout_path" >&2
fi
if ! kill -0 "$server_pid" 2>/dev/null; then
    rm -f "$pid_file"
fi
exit 1
