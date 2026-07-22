#!/bin/sh

set -eu

project_root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
runtime_root="$project_root/.runtime"
python_bin="$project_root/.venv/bin/python"
pid_file="$runtime_root/server.pid"
setup_file="$project_root/data/setup.json"

if [ ! -f "$setup_file" ]; then
    setup_file="$project_root/master-data/setup.json"
fi
if [ ! -x "$python_bin" ]; then
    echo "Local Python environment is missing. Run sh ./install.sh first." >&2
    exit 1
fi

port=$(
    "$python_bin" - "$setup_file" <<'PY'
import json
import pathlib
import sys

network = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))["network"]
print(network["port"])
PY
)

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

listener_pids() {
    if command -v lsof >/dev/null 2>&1; then
        lsof -nP -t -iTCP:"$port" -sTCP:LISTEN 2>/dev/null || true
        return 0
    fi
    if command -v ss >/dev/null 2>&1; then
        ss -ltnp 2>/dev/null | awk -v port="$port" '
            $4 ~ (":" port "$") {
                line = $0
                while (match(line, /pid=[0-9]+/)) {
                    print substr(line, RSTART + 4, RLENGTH - 4)
                    line = substr(line, RSTART + RLENGTH)
                }
            }
        ' | sort -u
        return 0
    fi
    echo "Cannot identify the listener process. Install lsof or ss." >&2
    return 2
}

is_descendant() {
    child_pid=$1
    root_pid=$2
    while [ "$child_pid" -gt 0 ] 2>/dev/null; do
        [ "$child_pid" -eq "$root_pid" ] && return 0
        child_pid=$(ps -p "$child_pid" -o ppid= 2>/dev/null | tr -d '[:space:]')
        case "$child_pid" in
            ''|*[!0-9]*) return 1 ;;
        esac
    done
    return 1
}

listener_belongs_to_server() {
    pids=$(listener_pids) || return $?
    for listener_pid in $pids; do
        if is_descendant "$listener_pid" "$server_pid"; then
            return 0
        fi
    done
    return 1
}

write_port_status() {
    if port_is_open; then
        echo "Port $port is in use."
    else
        echo "Port $port is free. No application is listening."
    fi
}

is_project_server() {
    server_command=$(ps -p "$server_pid" -o command= 2>/dev/null || true)
    case "$server_command" in
        *"$python_bin"*"-m talk_to_me_server"*) return 0 ;;
        *) return 1 ;;
    esac
}

if [ ! -f "$pid_file" ]; then
    echo "TalkToMe server is not running."
    write_port_status
    exit 0
fi

server_pid=$(tr -d '[:space:]' < "$pid_file")
case "$server_pid" in
    ''|*[!0-9]*)
        write_port_status
        echo "The server PID file is invalid." >&2
        exit 1
        ;;
esac

if ! kill -0 "$server_pid" 2>/dev/null; then
    rm -f "$pid_file"
    echo "TalkToMe server is not running. Removed a stale PID file."
    write_port_status
    exit 0
fi

if ! is_project_server; then
    write_port_status
    echo "PID $server_pid does not belong to this TalkToMe server. Refusing to stop it." >&2
    exit 1
fi

if port_is_open && ! listener_belongs_to_server; then
    echo "The configured port is owned by another process. Only the validated project process will be stopped." >&2
fi

kill -TERM "$server_pid"
attempt=0
while [ "$attempt" -lt 150 ] && kill -0 "$server_pid" 2>/dev/null; do
    attempt=$((attempt + 1))
    sleep 0.1
done

if kill -0 "$server_pid" 2>/dev/null; then
    if ! is_project_server; then
        echo "PID $server_pid changed ownership while stopping. Refusing to force it." >&2
        exit 1
    fi
    kill -KILL "$server_pid"
    echo "TalkToMe server required a forced stop."
fi

rm -f "$pid_file"
echo "TalkToMe server stopped."
write_port_status
