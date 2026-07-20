from __future__ import annotations

from pathlib import Path

import uvicorn

from talk_to_me_server.app import create_app
from talk_to_me_server.lifespan import build_runtime
from talk_to_me_server.network import build_listeners


def main() -> None:
    project_root = Path(__file__).resolve().parents[2]
    runtime = build_runtime(project_root)
    app = create_app(runtime)
    listeners = build_listeners(runtime.effective_settings().network)
    config = uvicorn.Config(app, lifespan="on", log_level="info")
    uvicorn.Server(config).run(sockets=listeners)


if __name__ == "__main__":
    main()
