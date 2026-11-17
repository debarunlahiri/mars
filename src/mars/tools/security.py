"""SSRF guard: only fetch public http(s) addresses."""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from urllib.parse import urlsplit

from ..core.errors import UnsafeURL


async def assert_public_url(url: str) -> None:
    """Raise ``UnsafeURL`` unless ``url`` is http(s) and every resolved IP is globally routable.

    Blocks loopback, private, link-local (cloud metadata 169.254.169.254), CGNAT and reserved
    ranges. Known limitation: DNS is re-resolved when connecting, so a hostile DNS server could
    still rebind between this check and the request; run the service in a network with no
    access to internal hosts for defence in depth.
    """
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise UnsafeURL(f"unsupported URL: {url[:80]}")
    if parts.username or parts.password:
        raise UnsafeURL("URLs with credentials are not allowed")
    port = parts.port or (443 if parts.scheme == "https" else 80)
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(parts.hostname, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise UnsafeURL(f"cannot resolve {parts.hostname}") from exc
    for info in infos:
        ip = ipaddress.ip_address(info[4][0].split("%")[0])
        if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
            ip = ip.ipv4_mapped
        if not ip.is_global:
            raise UnsafeURL(f"{parts.hostname} resolves to a non-public address")
