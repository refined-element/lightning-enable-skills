"""One unpaid HTTP request, with vetted addresses and bounded redirects.

``probe`` checks every hop with ``l402_netsafety.resolve_target`` and connects
only to an address that check returned (the first one, recorded on the hop),
so a DNS answer cannot change between the check and the connection. Redirects
are followed up to ``max_redirects``; a redirect into a blocked range stops the
probe and is reported, an https-to-http downgrade is refused, caller headers
are dropped when a redirect leaves the origin, and a 307/308 that would resend
a body to a different origin is not followed. ``timeout`` is one deadline for
the whole probe, every hop and every read included. Credential-bearing header
names, the Host and framing headers the probe sets itself, and header values
that could not be sent intact are refused before any request is sent. Nothing
here sends an Authorization header, and nothing here pays.
"""
from __future__ import annotations

import http.client
import re
import socket
import ssl
import threading
import time
from dataclasses import dataclass, field
from typing import Callable
from urllib.parse import urljoin, urlsplit

from l402_netsafety import Resolver, ResolutionError, Target, UnsafeTargetError, resolve_target

__all__ = [
    "CredentialHeaderError", "DEFAULT_TIMEOUT", "Hop", "HttpResponse", "MAX_BODY_BYTES", "MAX_REDIRECTS",
    "ProbeResult", "RefusedHeaderError", "ReservedHeaderError", "ResolutionError", "Target", "Transport",
    "USER_AGENT", "check_headers", "is_credential_header", "is_reserved_header", "pinned_transport", "probe",
]

MAX_BODY_BYTES = 256 * 1024
READ_CHUNK_BYTES = 16 * 1024
DEFAULT_TIMEOUT = 10.0
MAX_REDIRECTS = 5
USER_AGENT = (
    "l402-compatibility-report/1 "
    "(+https://github.com/refined-element/lightning-enable-skills; unpaid probe, never pays)"
)
REDIRECT_STATUSES = (301, 302, 303, 307, 308)

CREDENTIAL_HEADER_NAMES = frozenset({"authorization", "cookie", "proxy-authorization"})
CREDENTIAL_HEADER_FRAGMENTS = (
    "key", "token", "secret", "password", "session", "auth", "macaroon", "credential", "preimage",
)
RESERVED_HEADER_NAMES = frozenset({"host", "content-length", "transfer-encoding", "connection"})
_HEADER_NAME = re.compile(r"[!#$%&'*+\-.^_`|~0-9A-Za-z]+")
_FORBIDDEN_VALUE_CHARS = ("\r", "\n", "\0")

# The clock every deadline reads. Tests replace it; nothing else should.
_clock = time.monotonic


class RefusedHeaderError(ValueError):
    """A caller header the probe will not send. The value is never echoed."""

    def __init__(self, header_name: str, reason: str, message: str):
        super().__init__(message)
        self.header_name = header_name
        self.reason = reason


class CredentialHeaderError(RefusedHeaderError):
    """A caller header name looks like it carries a credential."""

    def __init__(self, header_name: str):
        super().__init__(
            header_name, "credential_header",
            f"refusing to send the header {header_name.strip()!r}: credential-bearing headers "
            "(Authorization, Cookie, Proxy-Authorization, or a name containing key, token, secret, "
            "password, session, auth, macaroon, credential, or preimage) are never passed to the "
            "read-only check",
        )


class ReservedHeaderError(RefusedHeaderError):
    """A caller header name the probe sets itself (Host and message framing)."""

    def __init__(self, header_name: str):
        super().__init__(
            header_name, "reserved_header",
            f"refusing to send the header {header_name.strip()!r}: Host, Content-Length, "
            "Transfer-Encoding, and Connection are set by the probe itself",
        )


def is_credential_header(name: str) -> bool:
    """True when ``name`` is a credential-bearing header this check refuses to send."""
    lowered = name.strip().lower()
    return lowered in CREDENTIAL_HEADER_NAMES or any(f in lowered for f in CREDENTIAL_HEADER_FRAGMENTS)


def is_reserved_header(name: str) -> bool:
    """True when ``name`` is a header the probe sets itself and refuses from the caller."""
    return name.strip().lower() in RESERVED_HEADER_NAMES


def _value_problem(value: object) -> str | None:
    """Why ``value`` can't be sent as a header value, or None. Never includes the value."""
    if isinstance(value, (bytes, bytearray)):
        text = bytes(value).decode("latin-1")
    else:
        text = str(value)
        try:
            text.encode("latin-1")
        except UnicodeEncodeError:
            return "contains characters outside Latin-1"
    if any(ch in text for ch in _FORBIDDEN_VALUE_CHARS):
        return "contains a CR, LF, or NUL character"
    return None


def check_headers(headers: dict | None) -> None:
    """Raise RefusedHeaderError for the first caller header the probe will not send.

    Refused: credential-bearing names, names the probe sets itself, names that
    are not HTTP tokens, and values containing CR, LF, NUL, or characters
    outside Latin-1. The error names the header and never carries its value.
    """
    for raw_name, value in (headers or {}).items():
        name = str(raw_name)
        if is_credential_header(name):
            raise CredentialHeaderError(name)
        if is_reserved_header(name):
            raise ReservedHeaderError(name)
        if not _HEADER_NAME.fullmatch(name):
            raise RefusedHeaderError(name, "invalid_header_name",
                                     f"refusing to send the header {name!r}: the name is not a valid HTTP header name")
        problem = _value_problem(value)
        if problem:
            raise RefusedHeaderError(name, "invalid_header_value",
                                     f"refusing to send the header {name!r}: its value {problem}")


def _origin_key(url: str) -> tuple[str, str, int] | None:
    """(scheme, host, port) for ``url``, the same normalization as ``Target``; None if unparseable."""
    parts = urlsplit(url)
    scheme = parts.scheme.lower()
    host = (parts.hostname or "").lower().rstrip(".")
    try:
        port = parts.port
    except ValueError:
        return None
    if port is None:
        port = 443 if scheme == "https" else 80
    return scheme, host, port


class _Deadline:
    """A fixed point in monotonic time that every wait is measured against."""

    def __init__(self, seconds: float):
        self.seconds = seconds
        self.at = _clock() + seconds

    def remaining(self) -> float:
        """Seconds left; raises TimeoutError once none are."""
        left = self.at - _clock()
        if left <= 0:
            raise TimeoutError(f"no response within {self.seconds:g} s")
        return left

    def expired(self) -> bool:
        return _clock() >= self.at


@dataclass
class HttpResponse:
    status: int
    headers: list[tuple[str, str]]
    body: bytes = b""
    elapsed_ms: int = 0
    truncated: bool = False

    def header_values(self, name: str) -> list[str]:
        wanted = name.lower()
        return [value for key, value in self.headers if key.lower() == wanted]

    def header(self, name: str) -> str | None:
        values = self.header_values(name)
        return values[0] if values else None


# The float is the time the transport may spend, the probe's remaining budget.
Transport = Callable[[Target, str, dict, "bytes | None", float], HttpResponse]


@dataclass
class Hop:
    url: str
    status: int
    address: str | None = None


@dataclass
class ProbeResult:
    requested_url: str
    final_target: Target | None = None
    response: HttpResponse | None = None
    hops: list[Hop] = field(default_factory=list)
    error_kind: str | None = None  # refused, redirect_refused, timeout, network, dns, redirect_limit
    error_reason: str | None = None
    error_message: str | None = None
    connected_address: str | None = None


class _PinnedHTTPConnection(http.client.HTTPConnection):
    def __init__(self, host: str, port: int, address: str, timeout: float):
        super().__init__(host, port, timeout=timeout)
        self._address = address

    def connect(self) -> None:
        self.sock = socket.create_connection((self._address, self.port), self.timeout)


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, host: str, port: int, address: str, timeout: float):
        super().__init__(host, port, timeout=timeout)
        self._address = address
        self._pinned_context = ssl.create_default_context()

    def connect(self) -> None:
        raw = socket.create_connection((self._address, self.port), self.timeout)
        try:
            self.sock = self._pinned_context.wrap_socket(raw, server_hostname=self.host)
        except BaseException:
            raw.close()
            raise


def _open_connection(target: Target, timeout: float) -> http.client.HTTPConnection:
    """An unconnected connection that will dial only the first vetted address."""
    cls = _PinnedHTTPSConnection if target.scheme == "https" else _PinnedHTTPConnection
    return cls(target.host, target.port, target.addresses[0], timeout)


def _abort(holder: list) -> None:
    """Watchdog: shut the socket down so a blocked read returns at the deadline."""
    sock = holder[0] if holder else None
    if sock is None:
        return
    try:
        socket.socket.shutdown(sock, socket.SHUT_RDWR)
    except (OSError, ValueError):
        pass


def _read_capped(resp, sock, deadline: _Deadline) -> tuple[bytes, bool]:
    """Read at most MAX_BODY_BYTES (+1 to detect truncation), each chunk bounded by the deadline."""
    chunks: list[bytes] = []
    total = 0
    # http.client closes the socket itself once it has read the whole body.
    while total <= MAX_BODY_BYTES and not resp.isclosed():
        sock.settimeout(deadline.remaining())
        chunk = resp.read1(min(READ_CHUNK_BYTES, MAX_BODY_BYTES + 1 - total))
        if not chunk:
            break
        chunks.append(chunk)
        total += len(chunk)
    data = b"".join(chunks)
    return data[:MAX_BODY_BYTES], len(data) > MAX_BODY_BYTES


def pinned_transport(target: Target, method: str, headers: dict, body: bytes | None, timeout: float) -> HttpResponse:
    """Send one request to the first vetted address of ``target``; the host name is never resolved here.

    ``timeout`` is the whole budget for this request: connect, send, the header
    read, and every body chunk each get only the time remaining, and a watchdog
    shuts the socket down when it runs out. Running out raises TimeoutError.
    """
    deadline = _Deadline(timeout)
    conn = _open_connection(target, deadline.remaining())
    holder: list = []
    watchdog = threading.Timer(deadline.remaining(), _abort, args=(holder,))
    watchdog.daemon = True
    resp = None
    started = _clock()
    watchdog.start()
    try:
        conn.timeout = deadline.remaining()
        conn.connect()
        sock = conn.sock
        holder.append(sock)
        sock.settimeout(deadline.remaining())
        conn.request(method, target.path_query, body=body, headers=headers)
        sock.settimeout(deadline.remaining())
        resp = conn.getresponse()
        if method == "HEAD":
            data, truncated = b"", False
        else:
            data, truncated = _read_capped(resp, sock, deadline)
        return HttpResponse(
            status=resp.status,
            headers=list(resp.getheaders()),
            body=data,
            elapsed_ms=int((_clock() - started) * 1000),
            truncated=truncated,
        )
    except (OSError, http.client.HTTPException):
        if deadline.expired():
            raise TimeoutError(f"no response within {deadline.seconds:g} s") from None
        raise
    finally:
        watchdog.cancel()
        if resp is not None:
            resp.close()
        conn.close()


def probe(
    url: str,
    *,
    method: str = "GET",
    headers: dict | None = None,
    body: bytes | None = None,
    timeout: float = DEFAULT_TIMEOUT,
    allow_private: bool = False,
    max_redirects: int = MAX_REDIRECTS,
    resolver: Resolver | None = None,
    transport: Transport | None = None,
) -> ProbeResult:
    """Request ``url`` without paying, following at most ``max_redirects`` redirects.

    ``timeout`` is a deadline for the whole probe, every redirect included.
    Raises RefusedHeaderError (CredentialHeaderError, ReservedHeaderError, or
    an invalid name or value) before any request. A 307/308 redirect that
    would resend a body to a different origin is not followed. Every other
    failure is reported on the result.
    """
    check_headers(headers)
    deadline = _Deadline(timeout)
    send = transport or pinned_transport
    result = ProbeResult(requested_url=url)
    current_url, current_method, current_body = url, method.upper(), body
    caller_headers = dict(headers or {})
    first_origin: str | None = None
    max_redirects = max(0, max_redirects)
    timeout_message = f"no response within {timeout:g} s"
    for hop_index in range(max_redirects + 1):
        try:
            target = resolve_target(current_url, allow_private=allow_private, resolver=resolver)
        except UnsafeTargetError as exc:
            result.error_kind = "refused" if hop_index == 0 else "redirect_refused"
            result.error_reason, result.error_message = exc.reason, str(exc)
            return result
        except ResolutionError as exc:
            result.error_kind, result.error_message = "dns", str(exc)
            return result
        if first_origin is None:
            first_origin = target.origin
        address = target.addresses[0]
        send_headers = {"User-Agent": USER_AGENT, "Accept": "*/*"}
        if target.origin == first_origin:
            send_headers.update(caller_headers)
        try:
            response = send(target, current_method, send_headers, current_body, deadline.remaining())
        except (socket.timeout, TimeoutError):
            result.error_kind, result.error_message = "timeout", timeout_message
            return result
        except (OSError, http.client.HTTPException) as exc:
            if deadline.expired():
                result.error_kind, result.error_message = "timeout", timeout_message
            else:
                result.error_kind, result.error_message = "network", type(exc).__name__
            return result
        result.final_target, result.response, result.connected_address = target, response, address
        location = response.header("Location")
        if response.status not in REDIRECT_STATUSES or not location:
            return result
        result.hops.append(Hop(url=current_url, status=response.status, address=address))
        if deadline.expired():
            result.error_kind, result.error_message = "timeout", timeout_message
            return result
        next_url = urljoin(current_url, location.strip())
        if target.scheme == "https" and urlsplit(next_url).scheme.lower() == "http":
            result.error_kind, result.error_reason = "redirect_refused", "downgrade"
            result.error_message = "the redirect downgrades https to http"
            return result
        if (response.status in (307, 308) and current_body
                and _origin_key(next_url) != (target.scheme, target.host, target.port)):
            result.error_kind, result.error_reason = "redirect_refused", "redirect_cross_origin_with_body"
            result.error_message = (
                f"the {response.status} redirect would resend the request body to a different origin; not followed"
            )
            return result
        if response.status in (301, 302, 303):
            current_body = None
            if current_method != "HEAD":
                current_method = "GET"
        current_url = next_url
    result.error_kind, result.error_message = "redirect_limit", f"more than {max_redirects} redirects"
    return result
