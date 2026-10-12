"""Parse WWW-Authenticate values into challenges (RFC 7235 section 4.1).

A header may hold several challenges joined by commas, and a response may carry
several headers; both forms produce the same list. Each challenge is a scheme
plus either a token68 or comma-separated auth-params, whose values are a token
or a quoted-string with backslash escapes. Errors name the header index and the
character offset, never the header text, because values carry macaroons and
invoices.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

TOKEN_CHARS = "!#$%&'*+-.^_`|~0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
TOKEN68 = re.compile(r"[A-Za-z0-9\-._~+/]+=*")
KNOWN_SCHEMES = {"l402": "L402", "lsat": "LSAT", "payment": "Payment", "x402": "x402"}


@dataclass
class Challenge:
    scheme: str
    params: dict[str, str] = field(default_factory=dict)
    token68: str | None = None
    duplicate_params: list[str] = field(default_factory=list)
    header_index: int = 0

    @property
    def kind(self) -> str:
        """Canonical scheme name: L402, LSAT, Payment, x402, or other."""
        return KNOWN_SCHEMES.get(self.scheme.lower(), "other")

    def param(self, name: str) -> str | None:
        return self.params.get(name.lower())


@dataclass
class ParseResult:
    challenges: list[Challenge] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class _Cursor:
    def __init__(self, text: str):
        self.text = text
        self.pos = 0

    def peek(self) -> str:
        return self.text[self.pos] if self.pos < len(self.text) else ""

    def skip_ws(self) -> None:
        while self.peek() in (" ", "\t"):
            self.pos += 1

    def skip_ows_commas(self) -> None:
        while self.peek() in (" ", "\t", ","):
            self.pos += 1

    def token(self) -> str:
        start = self.pos
        while self.peek() and self.peek() in TOKEN_CHARS:
            self.pos += 1
        return self.text[start:self.pos]

    def quoted(self) -> str:
        """Read a quoted-string starting at the opening quote."""
        assert self.peek() == '"'
        self.pos += 1
        out = []
        while self.pos < len(self.text):
            ch = self.text[self.pos]
            if ch == "\\":
                if self.pos + 1 >= len(self.text):
                    break
                out.append(self.text[self.pos + 1])
                self.pos += 2
                continue
            if ch == '"':
                self.pos += 1
                return "".join(out)
            out.append(ch)
            self.pos += 1
        raise ValueError(f"unterminated quoted-string starting near offset {self.pos}")


def _is_param_start(cur: _Cursor) -> bool:
    """True when the cursor sits on `name =` (an auth-param, not a new scheme)."""
    save = cur.pos
    name = cur.token()
    cur.skip_ws()
    is_param = bool(name) and cur.peek() == "="
    if is_param:
        cur.pos += 1
        cur.skip_ws()
        # `name==` or `name=` at the end is a token68, not a param.
        is_param = cur.peek() == '"' or (cur.peek() != "" and cur.peek() in TOKEN_CHARS and cur.peek() != "=")
    cur.pos = save
    return is_param


def _parse_header(text: str, index: int, result: ParseResult) -> None:
    cur = _Cursor(text)
    current: Challenge | None = None
    while True:
        cur.skip_ows_commas()
        if not cur.peek():
            return
        start = cur.pos
        if current is not None and _is_param_start(cur):
            name = cur.token().lower()
            cur.skip_ws()
            cur.pos += 1  # '='
            cur.skip_ws()
            try:
                value = cur.quoted() if cur.peek() == '"' else cur.token()
            except ValueError:
                result.errors.append(f"header {index}: unterminated quoted-string at offset {start}")
                return
            if name in current.params:
                current.duplicate_params.append(name)
            else:
                current.params[name] = value
        else:
            scheme = cur.token()
            if not scheme:
                result.errors.append(f"header {index}: unexpected character at offset {cur.pos}")
                return
            current = Challenge(scheme=scheme, header_index=index)
            result.challenges.append(current)
            if cur.peek() not in (" ", "\t", ",", ""):
                result.errors.append(f"header {index}: unexpected character at offset {cur.pos}")
                return
            cur.skip_ws()
            if cur.peek() in (",", "") or _is_param_start(cur):
                continue
            match = TOKEN68.match(cur.text, cur.pos)
            if not match:
                result.errors.append(f"header {index}: unexpected character at offset {cur.pos}")
                return
            current.token68 = match.group(0)
            cur.pos = match.end()
        cur.skip_ws()
        if cur.peek() not in (",", ""):
            result.errors.append(f"header {index}: expected ',' at offset {cur.pos}")
            return


def parse(headers: list[str]) -> ParseResult:
    """Parse every WWW-Authenticate value, in order."""
    result = ParseResult()
    for index, text in enumerate(headers):
        _parse_header(text, index, result)
    return result
