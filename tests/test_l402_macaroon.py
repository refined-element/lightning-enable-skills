"""Macaroon inspection for resource-binding analysis. Macaroons are built in code, never stored."""
import base64

import l402_check_support  # noqa: F401  (puts the skill's scripts on sys.path)
import l402_macaroon

PAYMENT_HASH = "f41249023341ff317a271287643ae346fc210b620be17520c797f23cb4d35931"


def _varint(n: int) -> bytes:
    out = bytearray()
    while True:
        byte, n = n & 0x7F, n >> 7
        out.append(byte | (0x80 if n else 0))
        if not n:
            return bytes(out)


def _field(kind: int, value: bytes) -> bytes:
    return bytes([kind]) + _varint(len(value)) + value


def build_v2(identifier: bytes, caveats: list[str]) -> str:
    out = bytearray([2]) + _field(1, b"fixture-location") + _field(2, identifier) + b"\x00"
    for caveat in caveats:
        out += _field(2, caveat.encode()) + b"\x00"
    out += b"\x00" + _field(6, b"\x11" * 32)
    return base64.urlsafe_b64encode(bytes(out)).decode().rstrip("=")


def _packet(key: bytes, value: bytes) -> bytes:
    body = key + b" " + value + b"\n"
    return f"{len(body) + 4:04x}".encode() + body


def build_v1(identifier: bytes, caveats: list[str]) -> str:
    out = _packet(b"location", b"fixture-location") + _packet(b"identifier", identifier)
    for caveat in caveats:
        out += _packet(b"cid", caveat.encode())
    out += _packet(b"signature", b"\x22" * 32)
    return base64.urlsafe_b64encode(out).decode()


def lightning_labs_identifier(payment_hash: str) -> bytes:
    return b"\x00\x00" + bytes.fromhex(payment_hash) + b"\x33" * 32


def test_v2_lightning_labs_macaroon_exposes_payment_hash_and_bindings():
    token = build_v2(
        lightning_labs_identifier(PAYMENT_HASH),
        ["services=weather:0", "weather_capabilities=forecast", "expires=1791923855", "method=GET", "path=/forecast"],
    )
    info = l402_macaroon.inspect(token)
    assert info.format == "v2"
    assert info.payment_hash == PAYMENT_HASH
    assert info.bindings() == {
        "scope": ["services", "weather_capabilities"],
        "expiry": ["expires"],
        "method": ["method"],
        "path": ["path"],
    }
    assert info.unrecognized_caveat_keys() == []


def test_v1_macaroon_with_unrecognized_caveats():
    info = l402_macaroon.inspect(build_v1(lightning_labs_identifier(PAYMENT_HASH), ["colour=blue", "flavour=mint"]))
    assert info.format == "v1"
    assert info.payment_hash == PAYMENT_HASH
    assert info.bindings() == {}
    assert info.unrecognized_caveat_keys() == ["colour", "flavour"]


def test_identifier_not_in_lightning_labs_format_has_no_payment_hash():
    assert l402_macaroon.inspect(build_v2(b"fixture-identifier", [])).payment_hash is None


def test_placeholders_and_garbage_are_opaque():
    for token in ("fixture-string-macaroon", "", None, "!!!", base64.b64encode(b"\x02\x05").decode()):
        assert l402_macaroon.inspect(token).format == "opaque"
