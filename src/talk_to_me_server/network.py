from __future__ import annotations

import socket

from talk_to_me_server.config.models import NetworkSettings


def build_listeners(settings: NetworkSettings) -> list[socket.socket]:
    listeners: list[socket.socket] = []
    try:
        if settings.ipv4_enabled:
            listeners.append(_listener(socket.AF_INET, (settings.ipv4_address, settings.port)))
        if settings.ipv6_enabled:
            listener = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
            listeners.append(listener)
            if hasattr(socket, "IPV6_V6ONLY"):
                listener.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
            _prepare(listener, (settings.ipv6_address, settings.port))
        return listeners
    except BaseException:
        for listener in listeners:
            listener.close()
        raise


def _listener(family: int, address: tuple[str, int]) -> socket.socket:
    listener = socket.socket(family, socket.SOCK_STREAM)
    try:
        _prepare(listener, address)
    except BaseException:
        listener.close()
        raise
    return listener


def _prepare(listener: socket.socket, address: tuple[str, int]) -> None:
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(address)
    listener.listen()
    listener.setblocking(False)
