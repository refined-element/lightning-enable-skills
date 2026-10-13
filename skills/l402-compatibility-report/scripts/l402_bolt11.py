"""Decode a BOLT11 Lightning invoice without paying it.

Reads the human-readable part (network and amount) and the tagged fields that
need no signature recovery: payment hash (p), expiry (x, default 3600 s),
description (d) or description hash (h), payee (n, when stated), route hints
(r) and feature bits (9). The checksum is verified; the signature is not.
Error messages never echo the invoice.
"""
from __future__ import annotations

from dataclasses import dataclass

CHARSET = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"
# Longest prefix first: "bcrt" before "bc", "tbs" before "tb".
NETWORKS = (("bcrt", "regtest"), ("bc", "mainnet"), ("tbs", "signet"), ("tb", "testnet"))
MSAT_PER_UNIT = {"m": 100_000_000, "u": 100_000, "n": 100}
SIGNATURE_WORDS = 104
TIMESTAMP_WORDS = 7
DEFAULT_EXPIRY_SECONDS = 3600


class Bolt11Error(ValueError):
    """The string is not a decodable BOLT11 invoice. The message never echoes it."""


@dataclass
class Invoice:
    network: str
    amount_msat: int | None
    timestamp: int
    payment_hash: str | None = None
    expiry_seconds: int = DEFAULT_EXPIRY_SECONDS
    has_description: bool = False
    has_description_hash: bool = False
    payee: str | None = None
    route_hint_count: int = 0
    has_features: bool = False

    @property
    def amount_sats(self) -> int | None:
        """Whole sats, rounded up; None for an amountless invoice."""
        if self.amount_msat is None:
            return None
        return -(-self.amount_msat // 1000)

    @property
    def expires_at(self) -> int:
        return self.timestamp + self.expiry_seconds


def _polymod(values: list[int]) -> int:
    generator = (0x3B6A57B2, 0x26508E6D, 0x1EA119FA, 0x3D4233DD, 0x2A1462B3)
    chk = 1
    for value in values:
        top = chk >> 25
        chk = (chk & 0x1FFFFFF) << 5 ^ value
        for i in range(5):
            if (top >> i) & 1:
                chk ^= generator[i]
    return chk


def _hrp_expand(hrp: str) -> list[int]:
    return [ord(c) >> 5 for c in hrp] + [0] + [ord(c) & 31 for c in hrp]


def _bech32_decode(text: str) -> tuple[str, list[int]]:
    # str.isdigit() accepts non-ASCII digits that int() can reject with a
    # ValueError echoing the input, so refuse non-ASCII before anything else.
    if not text.isascii():
        raise Bolt11Error("non-ASCII character")
    if text.lower() != text and text.upper() != text:
        raise Bolt11Error("mixed case")
    text = text.lower()
    pos = text.rfind("1")
    if pos < 1 or pos + 7 > len(text):
        raise Bolt11Error("no bech32 separator")
    hrp, data_part = text[:pos], text[pos + 1:]
    if any(c not in CHARSET for c in data_part):
        raise Bolt11Error("character outside the bech32 alphabet")
    data = [CHARSET.find(c) for c in data_part]
    if _polymod(_hrp_expand(hrp) + data) != 1:
        raise Bolt11Error("bad bech32 checksum")
    return hrp, data[:-6]


def _words_to_int(words: list[int]) -> int:
    value = 0
    for word in words:
        value = value * 32 + word
    return value


def _words_to_bytes(words: list[int]) -> bytes:
    acc = bits = 0
    out = bytearray()
    for word in words:
        acc = (acc << 5) | word
        bits += 5
        while bits >= 8:
            bits -= 8
            out.append((acc >> bits) & 0xFF)
    return bytes(out)


def _parse_hrp(hrp: str) -> tuple[str, int | None]:
    if not hrp.startswith("ln"):
        raise Bolt11Error("prefix is not 'ln'")
    rest = hrp[2:]
    for prefix, network in NETWORKS:
        if rest.startswith(prefix):
            amount = rest[len(prefix):]
            break
    else:
        raise Bolt11Error("unknown network prefix")
    if not amount:
        return network, None
    digits, unit = (amount[:-1], amount[-1]) if amount[-1].isalpha() else (amount, "")
    if not digits.isdigit() or digits.startswith("0"):
        raise Bolt11Error("malformed amount")
    value = int(digits)
    if unit == "":
        return network, value * 100_000_000_000
    if unit == "p":
        if value % 10:
            raise Bolt11Error("pico amount is not a whole millisatoshi")
        return network, value // 10
    if unit not in MSAT_PER_UNIT:
        raise Bolt11Error("unknown amount multiplier")
    return network, value * MSAT_PER_UNIT[unit]


def decode(invoice: str) -> Invoice:
    """Decode the parts of ``invoice`` that need no signature recovery."""
    text = invoice.strip()
    if text.lower().startswith("lightning:"):
        text = text[len("lightning:"):]
    hrp, data = _bech32_decode(text)
    network, amount_msat = _parse_hrp(hrp)
    if len(data) < TIMESTAMP_WORDS + SIGNATURE_WORDS:
        raise Bolt11Error("too short to be an invoice")
    result = Invoice(
        network=network,
        amount_msat=amount_msat,
        timestamp=_words_to_int(data[:TIMESTAMP_WORDS]),
    )
    tagged = data[TIMESTAMP_WORDS:-SIGNATURE_WORDS]
    i = 0
    expiry_seen = False
    while i < len(tagged):
        if i + 3 > len(tagged):
            raise Bolt11Error("truncated tagged field")
        tag = CHARSET[tagged[i]]
        length = tagged[i + 1] * 32 + tagged[i + 2]
        words = tagged[i + 3:i + 3 + length]
        if len(words) != length:
            raise Bolt11Error("truncated tagged field")
        i += 3 + length
        if tag == "p" and length == 52 and result.payment_hash is None:
            result.payment_hash = _words_to_bytes(words)[:32].hex()
        elif tag == "x" and not expiry_seen:
            # First wins, the same as p: a later repeated x field is ignored.
            # No captured fixture repeats x, so this rule has no fixture test.
            expiry_seen = True
            result.expiry_seconds = _words_to_int(words)
        elif tag == "d":
            result.has_description = True
        elif tag == "h" and length == 52:
            result.has_description_hash = True
        elif tag == "n" and length == 53:
            result.payee = _words_to_bytes(words)[:33].hex()
        elif tag == "r":
            result.route_hint_count += 1
        elif tag == "9":
            result.has_features = True
    if result.payment_hash is None:
        raise Bolt11Error("no payment hash")
    return result
