"""Decide whether a URL is safe to probe, before any connection opens.

Refused by default: non-HTTP(S) schemes, credentials in the URL, plain HTTP,
and any host that resolves to an address that is not globally routable
(loopback, RFC 1918, link-local, carrier-grade NAT, unique-local, multicast,
reserved). ``allow_private`` is the explicit local-testing switch: it admits
non-global addresses, and plain HTTP to them. Cloud metadata endpoints stay
refused even then. Every address the host resolves to is checked, IPv6 forms
that embed an IPv4 address (mapped, NAT64, IPv4-compatible, 6to4, Teredo) are
checked as that IPv4 address too, and the caller connects only to an address
checked here.
"""
from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass, field
from typing import Callable
from urllib.parse import urlsplit

Resolver = Callable[[str, int], list[str]]

METADATA_ADDRESSES = frozenset(
    ipaddress.ip_address(a) for a in ("169.254.169.254", "fd00:ec2::254", "100.100.100.200")
)
METADATA_HOSTNAMES = frozenset({"metadata.google.internal", "metadata.goog", "metadata"})


class UnsafeTargetError(ValueError):
    """The URL must not be probed. ``reason`` is a stable code for the report."""

    def __init__(self, reason: str, message: str):
        super().__init__(message)
        self.reason = reason


class ResolutionError(OSError):
    """The host did not resolve. The check is inconclusive, not refused."""


@dataclass
class Target:
    url: str
    scheme: str
    host: str
    port: int
    path_query: str
    addresses: list[str] = field(default_factory=list)

    @property
    def origin(self) -> str:
        default = 443 if self.scheme == "https" else 80
        host = f"[{self.host}]" if ":" in self.host else self.host
        return f"{self.scheme}://{host}" + ("" if self.port == default else f":{self.port}")

    @property
    def is_public(self) -> bool:
        return bool(self.addresses) and all(_is_global(_normalize(a)) for a in self.addresses)


def system_resolver(host: str, port: int) -> list[str]:
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ResolutionError(f"could not resolve host: {exc.strerror}") from None
    seen: list[str] = []
    for info in infos:
        address = info[4][0].split("%", 1)[0]
        if address not in seen:
            seen.append(address)
    return seen


def _normalize(address: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address:
    ip = ipaddress.ip_address(address)
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        return ip.ipv4_mapped
    return ip


NAT64_PREFIX = ipaddress.ip_network("64:ff9b::/96")


def _embedded_ipv4(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> list[ipaddress.IPv4Address]:
    """IPv4 addresses an IPv6 address carries inside it.

    A NAT64 (64:ff9b::/96), IPv4-compatible (::/96), 6to4 (2002::/16), or Teredo
    (2001::/32) address can reach the IPv4 address it embeds, so the range
    rules apply to that IPv4 address too. ``::`` and ``::1`` are not embeddings.
    """
    if not isinstance(ip, ipaddress.IPv6Address):
        return []
    embedded: list[ipaddress.IPv4Address] = []
    value = int(ip)
    if ip in NAT64_PREFIX or (value >> 32 == 0 and value > 1):
        embedded.append(ipaddress.IPv4Address(value & 0xFFFFFFFF))
    if ip.sixtofour is not None:
        embedded.append(ip.sixtofour)
    if ip.teredo is not None:
        embedded.append(ip.teredo[1])
    return embedded


def _views(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> list[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    return [ip, *_embedded_ipv4(ip)]


def _is_global(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return all(view.is_global and not view.is_multicast for view in _views(ip))


def resolve_target(url: str, *, allow_private: bool = False, resolver: Resolver | None = None) -> Target:
    """Return the vetted target, or raise UnsafeTargetError / ResolutionError."""
    parts = urlsplit(url)
    scheme = parts.scheme.lower()
    if scheme not in ("http", "https"):
        raise UnsafeTargetError("scheme", "only http and https URLs can be checked")
    if parts.username is not None or parts.password is not None:
        raise UnsafeTargetError("credentials_in_url", "the URL carries credentials; remove them and pass a header instead")
    host = (parts.hostname or "").lower()
    if not host:
        raise UnsafeTargetError("no_host", "the URL has no host")
    if host in METADATA_HOSTNAMES:
        raise UnsafeTargetError("cloud_metadata", "cloud metadata endpoints are never probed")
    try:
        port = parts.port or (443 if scheme == "https" else 80)
    except ValueError:
        raise UnsafeTargetError("bad_port", "the URL has an invalid port") from None
    path_query = (parts.path or "/") + (f"?{parts.query}" if parts.query else "")

    if host == "localhost" or host.endswith(".localhost"):
        addresses = ["127.0.0.1"]
    else:
        try:
            addresses = [str(_normalize(host))]
        except ValueError:
            addresses = (resolver or system_resolver)(host, port)
    if not addresses:
        raise ResolutionError("the host resolved to no addresses")

    ips = [_normalize(a) for a in addresses]
    if any(view in METADATA_ADDRESSES for ip in ips for view in _views(ip)):
        raise UnsafeTargetError("cloud_metadata", "the host resolves to a cloud metadata address; never probed")
    non_global = [ip for ip in ips if not _is_global(ip)]
    if non_global and not allow_private:
        raise UnsafeTargetError(
            "private_address",
            "the host resolves to a loopback, private, link-local, or reserved address; "
            "pass --allow-private only when deliberately testing a local environment",
        )
    if scheme == "http" and not (allow_private and len(non_global) == len(ips)):
        raise UnsafeTargetError("not_https", "public endpoints must use https")
    return Target(url=url, scheme=scheme, host=host, port=port, path_query=path_query,
                  addresses=[str(ip) for ip in ips])
