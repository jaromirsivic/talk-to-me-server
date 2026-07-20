from __future__ import annotations

from ipaddress import ip_address

from talk_to_me_server.config.models import Settings


class ManagementAccessDenied(PermissionError):
    pass


class ManagementAccessPolicy:
    def authorize(self, client_ip: str, settings: Settings) -> None:
        try:
            is_loopback = ip_address(client_ip.split("%", 1)[0]).is_loopback
        except ValueError:
            is_loopback = False
        if not is_loopback and not settings.network.remote_management_enabled:
            raise ManagementAccessDenied("Remote management is disabled")
