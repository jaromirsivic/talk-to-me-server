import socket

import pytest

from talk_to_me_server.config.models import NetworkSettings
from talk_to_me_server.network import build_listeners


class FakeSocket:
    def __init__(self, family, _kind) -> None:
        self.family = family
        self.options = []
        self.bound = None
        self.closed = False

    def setsockopt(self, *args) -> None:
        self.options.append(args)

    def bind(self, address) -> None:
        self.bound = address

    def listen(self) -> None:
        pass

    def setblocking(self, _value) -> None:
        pass

    def close(self) -> None:
        self.closed = True


def test_build_listeners_binds_enabled_ipv4_and_ipv6(monkeypatch) -> None:
    created = []

    def factory(family, kind):
        result = FakeSocket(family, kind)
        created.append(result)
        return result

    monkeypatch.setattr(socket, "socket", factory)

    listeners = build_listeners(NetworkSettings())

    assert listeners == created
    assert created[0].bound == ("127.0.0.1", 44448)
    assert created[1].bound == ("::1", 44448)
    assert any(option[:2] == (socket.IPPROTO_IPV6, socket.IPV6_V6ONLY) for option in created[1].options)


def test_bind_failure_closes_previously_created_listener(monkeypatch) -> None:
    first = FakeSocket(socket.AF_INET, socket.SOCK_STREAM)
    second = FakeSocket(socket.AF_INET6, socket.SOCK_STREAM)

    def fail_bind(_address) -> None:
        raise OSError("port busy")

    second.bind = fail_bind
    created = iter([first, second])
    monkeypatch.setattr(socket, "socket", lambda *_args: next(created))

    with pytest.raises(OSError, match="port busy"):
        build_listeners(NetworkSettings())

    assert first.closed is True
    assert second.closed is True
