"""Decide whether a URL is safe to probe, before any connection opens.

Refused by default: non-HTTP(S) schemes, credentials in the URL, plain HTTP,
and any host that resolves to an address that is not globally routable
(loopback, RFC 1918, link-local, carrier-grade NAT, unique-local, site-local,
multicast, reserved). ``allow_private`` is the explicit local-testing switch:
it admits non-global addresses, and plain HTTP to them. Cloud metadata and
credential endpoints stay refused even then. Every address the host resolves
to is checked, IPv6 forms that embed an IPv4 address (mapped, SIIT, NAT64,
IPv4-compatible, 6to4, Teredo) are checked as that IPv4 address too, and the
caller connects only to an address checked here.
"""
from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass, field
from typing import Callable
from urllib.parse import urlsplit

Resolver = Callable[[str, int], list[str]]

METADATA_ADDRESSES = frozenset(
    ipaddress.ip_address(a)
    for a in (
        "169.254.169.254",  # AWS, GCP, Azure, and most clouds: instance metadata
        "fd00:ec2::254",  # AWS instance metadata over IPv6
        "169.254.170.2",  # AWS ECS task credentials
        "169.254.170.23",  # AWS EKS Pod Identity credentials
        "fd00:ec2::23",  # AWS EKS Pod Identity credentials over IPv6
        "168.63.129.16",  # Azure WireServer
        "100.100.100.200",  # Alibaba Cloud instance metadata
    )
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
    except UnicodeError:
        raise ResolutionError("could not resolve host: the name is not a valid hostname") from None
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
LOCAL_NAT64_PREFIX = ipaddress.ip_network("64:ff9b:1::/48")
SIIT_PREFIX = ipaddress.ip_network("::ffff:0:0:0/96")


def _embedded_ipv4(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> list[ipaddress.IPv4Address]:
    """IPv4 addresses an IPv6 address carries inside it.

    A NAT64 (64:ff9b::/96 and the local-use 64:ff9b:1::/48), SIIT
    (::ffff:0:0:0/96), IPv4-compatible (::/96), 6to4 (2002::/16), or Teredo
    (2001::/32) address can reach the IPv4 address it embeds, so the range
    rules apply to that IPv4 address too. ``::`` and ``::1`` are not embeddings.
    The local-use NAT64 prefix can be split by its operator at /48, /56, /64, or
    /96 (RFC 6052), so every one of those placements is checked.
    """
    if not isinstance(ip, ipaddress.IPv6Address):
        return []
    embedded: list[ipaddress.IPv4Address] = []
    value = int(ip)
    if ip in NAT64_PREFIX or ip in SIIT_PREFIX or (value >> 32 == 0 and value > 1):
        embedded.append(ipaddress.IPv4Address(value & 0xFFFFFFFF))
    if ip in LOCAL_NAT64_PREFIX:
        b = ip.packed
        for octets in (b[6:8] + b[9:11], b[7:8] + b[9:12], b[9:13], b[12:16]):
            embedded.append(ipaddress.IPv4Address(octets))
    if ip.sixtofour is not None:
        embedded.append(ip.sixtofour)
    if ip.teredo is not None:
        embedded.append(ip.teredo[1])
    return embedded


def _views(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> list[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    """The address without any zone id, plus every IPv4 address it embeds.

    A zone id (``fe80::1%eth0``) changes equality, so it is dropped before the
    address is compared with the metadata list or classified.
    """
    if isinstance(ip, ipaddress.IPv6Address) and ip.scope_id:
        ip = ipaddress.IPv6Address(int(ip))
    return [ip, *_embedded_ipv4(ip)]


def _is_global(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return all(
        view.is_global and not view.is_multicast and not getattr(view, "is_site_local", False)
        for view in _views(ip)
    )


def resolve_target(url: str, *, allow_private: bool = False, resolver: Resolver | None = None) -> Target:
    """Return the vetted target, or raise UnsafeTargetError / ResolutionError."""
    parts = urlsplit(url)
    scheme = parts.scheme.lower()
    if scheme not in ("http", "https"):
        raise UnsafeTargetError("scheme", "only http and https URLs can be checked")
    if parts.username is not None or parts.password is not None:
        raise UnsafeTargetError("credentials_in_url", "the URL carries credentials; remove them and pass a header instead")
    host = (parts.hostname or "").lower().rstrip(".")
    if not host:
        raise UnsafeTargetError("no_host", "the URL has no host")
    if host in METADATA_HOSTNAMES:
        raise UnsafeTargetError("cloud_metadata", "cloud metadata endpoints are never probed")
    try:
        port = parts.port
    except ValueError:
        raise UnsafeTargetError("bad_port", "the URL has an invalid port") from None
    if port is None:
        port = 443 if scheme == "https" else 80
    elif port == 0:
        raise UnsafeTargetError("bad_port", "the URL has an invalid port")
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

    try:
        ips = [_normalize(a) for a in addresses]
    except (TypeError, ValueError):
        raise ResolutionError("the resolver returned something that is not an IP address") from None
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
