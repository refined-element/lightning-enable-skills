"""Read the public parts of a macaroon: identifier and first-party caveats.

Supports the binary V2 format (what Lightning Labs' aperture emits) and the
text-packet V1 format, each base64 or base64url, padded or not. Nothing here
verifies the signature; only the issuer holds the root key. Anything that does
not decode is "opaque", which the report calls not externally verifiable.
"""
from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass, field

FIELD_EOS, FIELD_LOCATION, FIELD_IDENTIFIER, FIELD_VID, FIELD_SIGNATURE = 0, 1, 2, 4, 6
LIGHTNING_LABS_ID_LENGTH = 66  # uint16 version + 32-byte payment hash + 32-byte token id

# Caveat-name fragments mapped to the binding they evidence. Heuristic: the
# report labels these as inferred from caveat names.
BINDING_HINTS = (
    ("method", ("method",)),
    ("path", ("path", "resource", "route", "endpoint", "uri", "url")),
    ("query", ("query",)),
    ("body_digest", ("body", "digest", "content_hash", "request_hash")),
    ("expiry", ("expires", "expiry", "valid_until", "valid_before", "exp", "time")),
    ("scope", ("services", "capabilities", "scope", "tier")),
)


@dataclass
class MacaroonInfo:
    format: str  # "v2", "v1", or "opaque"
    identifier: bytes = b""
    caveats: list[str] = field(default_factory=list)

    @property
    def payment_hash(self) -> str | None:
        """Payment hash from a Lightning Labs identifier (version 0), else None."""
        ident = self.identifier
        if len(ident) == LIGHTNING_LABS_ID_LENGTH and ident[:2] == b"\x00\x00":
            return ident[2:34].hex()
        return None

    @property
    def caveat_keys(self) -> list[str]:
        keys = []
        for caveat in self.caveats:
            key = caveat.split("=", 1)[0].split(" ", 1)[0].strip().lower()
            if key and key not in keys:
                keys.append(key)
        return keys

    def bindings(self) -> dict[str, list[str]]:
        """Binding category -> caveat keys that suggest it."""
        found: dict[str, list[str]] = {}
        for key in self.caveat_keys:
            for category, fragments in BINDING_HINTS:
                if any(fragment in key for fragment in fragments):
                    found.setdefault(category, []).append(key)
                    break
        return found

    def unrecognized_caveat_keys(self) -> list[str]:
        matched = {key for keys in self.bindings().values() for key in keys}
        return [key for key in self.caveat_keys if key not in matched]


def _b64decode(text: str) -> bytes | None:
    cleaned = text.strip()
    padded = cleaned + "=" * (-len(cleaned) % 4)
    for decoder in (base64.urlsafe_b64decode, base64.b64decode):
        try:
            return decoder(padded)
        except (binascii.Error, ValueError):
            continue
    return None


def _varint(data: bytes, pos: int) -> tuple[int, int]:
    value = shift = 0
    while True:
        if pos >= len(data) or shift > 63:
            raise ValueError("bad varint")
        byte = data[pos]
        pos += 1
        value |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return value, pos
        shift += 7


def _v2_fields(data: bytes, pos: int) -> tuple[list[tuple[int, bytes]], int]:
    """Read fields up to and including the next EOS."""
    fields = []
    while True:
        if pos >= len(data):
            raise ValueError("truncated")
        kind = data[pos]
        pos += 1
        if kind == FIELD_EOS:
            return fields, pos
        length, pos = _varint(data, pos)
        if pos + length > len(data):
            raise ValueError("truncated")
        fields.append((kind, data[pos:pos + length]))
        pos += length


def _parse_v2(data: bytes) -> MacaroonInfo:
    header, pos = _v2_fields(data, 1)
    identifier = next((value for kind, value in header if kind == FIELD_IDENTIFIER), None)
    if identifier is None:
        raise ValueError("no identifier")
    info = MacaroonInfo(format="v2", identifier=identifier)
    while True:
        if pos >= len(data):
            raise ValueError("truncated")
        if data[pos] == FIELD_EOS:
            pos += 1
            break
        fields, pos = _v2_fields(data, pos)
        kinds = {kind for kind, _ in fields}
        caveat_id = next((value for kind, value in fields if kind == FIELD_IDENTIFIER), b"")
        if FIELD_VID not in kinds:  # first-party caveat
            info.caveats.append(caveat_id.decode("utf-8", errors="replace"))
    if pos >= len(data) or data[pos] != FIELD_SIGNATURE:
        raise ValueError("no signature")
    return info


def _parse_v1(data: bytes) -> MacaroonInfo:
    info = MacaroonInfo(format="v1")
    pos = 0
    pending_cid: str | None = None
    seen_identifier = False
    while pos < len(data):
        size = int(data[pos:pos + 4].decode("ascii"), 16)
        if size < 5 or pos + size > len(data):
            raise ValueError("bad packet")
        packet = data[pos + 4:pos + size]
        pos += size
        key, _, value = packet.rstrip(b"\n").partition(b" ")
        if key == b"identifier":
            info.identifier = value
            seen_identifier = True
        elif key == b"cid":
            if pending_cid is not None:
                info.caveats.append(pending_cid)
            pending_cid = value.decode("utf-8", errors="replace")
        elif key == b"vid":
            pending_cid = None  # third-party caveat: not inspectable
        elif key == b"signature":
            break
    if pending_cid is not None:
        info.caveats.append(pending_cid)
    if not seen_identifier:
        raise ValueError("no identifier")
    return info


def inspect(token: str | None) -> MacaroonInfo:
    """Decode ``token`` if it is a macaroon; otherwise return an opaque result."""
    if not token:
        return MacaroonInfo(format="opaque")
    data = _b64decode(token)
    if not data:
        return MacaroonInfo(format="opaque")
    try:
        if data[0] == 2:
            return _parse_v2(data)
        return _parse_v1(data)
    except (ValueError, UnicodeDecodeError, IndexError):
        return MacaroonInfo(format="opaque")
