#!/usr/bin/env python3
"""l402_check.py: report how well an endpoint implements L402, without paying.

Read-only check (Mode A, the default). One unpaid request, then a report:

  python scripts/l402_check.py https://api.example.com/resource
  python scripts/l402_check.py https://api.example.com/resource --json --output mode-a.json
  python scripts/l402_check.py https://api.example.com/search --method POST --header "Accept=application/json"
  python scripts/l402_check.py https://api.example.com/resource --max-sats 50
  python scripts/l402_check.py https://api.example.com/resource --profile amazap

Paid check (Mode B). The agent pays once with the Lightning Enable MCP tool
access_l402_resource (max_sats set to the approved cap), records the result in
an evidence file, and passes the credential, if the MCP returned one, on stdin:

  python scripts/l402_check.py --evidence evidence.json --mode-a mode-a.json --credential-stdin

The script never pays: it has no payment code path. It never prints an invoice
string, macaroon, token, preimage, or authorization header, and prints the
payment hash and amount only. --header takes non-secret headers only; a
credential, Host, or framing header is refused before any request.
--profile amazap also fetches /openapi.json and /llms.txt at the host root for
the optional Amazap profile; without it the read-only check makes one request.
--output PATH writes the report to PATH as UTF-8 instead of printing it, which
avoids shell redirection (Windows PowerShell 5.1 redirects as UTF-16). The
JSON and evidence files are read as UTF-8, with or without a byte order mark,
or as UTF-16 when they start with a UTF-16 byte order mark.
Exit status: 0 when a report was printed or written, 2 for a usage,
refused-header, evidence, or output error. Standard library only; Python 3.10
or later.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent))

import l402_analyze  # noqa: E402
import l402_evidence  # noqa: E402
import l402_http  # noqa: E402
import l402_report  # noqa: E402

ROOT_METADATA_PATHS = ("/openapi.json", "/llms.txt")
PROG = "l402_check.py"
MAX_TIMEOUT = 30.0
_TOKEN = re.compile(r"[!#$%&'*+\-.^_`|~0-9A-Za-z]+")  # RFC 7230 tchar
_METHOD = re.compile(r"[!#$%&'*+\-.^_`|~0-9A-Za-z]{1,32}")
_FRAGMENTS = l402_http.CREDENTIAL_HEADER_FRAGMENTS
REFUSED_FRAGMENTS = ", ".join(_FRAGMENTS[:-1]) + ", or " + _FRAGMENTS[-1]
# Fixed text for each refusal; the header's value never reaches a message.
REFUSAL_REASONS = {
    "credential_header": ("credential-bearing headers (Authorization, Cookie, Proxy-Authorization, or a name "
                          f"containing {REFUSED_FRAGMENTS}) are never sent"),
    "reserved_header": "Host, Content-Length, Transfer-Encoding, and Connection are set by the probe itself",
    "invalid_header_name": "the name is not a valid HTTP header name",
    "invalid_header_value": "the value contains a CR, LF, NUL, or non-Latin-1 character",
}

EPILOG = """\
Paid check: the agent pays once with the Lightning Enable MCP tool
access_l402_resource, writes the result to an evidence file (no credential in
it), and pipes the L402 token, <macaroon>:<preimage>, on stdin with
--credential-stdin. The token is read once, never echoed, and never written to
a file. Without --credential-stdin the paid check ends at most INCONCLUSIVE.

This script never pays. It never prints an invoice string, macaroon, token,
preimage, or authorization header.

--output PATH writes the report to PATH as UTF-8 and prints one line naming
the file. Use it instead of shell redirection: Windows PowerShell 5.1 writes a
redirected report as UTF-16.

--profile amazap: the optional Amazap marketplace profile is reported either
way and never changes the classification; this flag also requests
/openapi.json and /llms.txt at the host root, where Amazap's listing prefill
looks. Without it the read-only check makes exactly one request.

Exit status:
  0  a report was printed or written, whatever its classification (a refused
     target gives an INCONCLUSIVE report)
  2  a usage error, a refused --header, an evidence error, or an --output
     file that can't be written; no report is printed on stdout and the
     message never echoes a value
"""


def parse_header(text: str) -> tuple[str, str]:
    """(name, value) from NAME=VALUE. The name must be an HTTP token; the error never includes the input."""
    name, sep, value = text.partition("=")
    name = name.strip()
    if not sep or not _TOKEN.fullmatch(name):
        # A curl-style "Authorization: Bearer x=" would otherwise turn the token into a header name.
        raise argparse.ArgumentTypeError("header must be NAME=VALUE with a token name")
    return name, value.strip()


def refusal_message(exc: l402_http.RefusedHeaderError) -> str:
    """Fixed text for a refused header, naming it only when the name is a plain HTTP token."""
    reason = REFUSAL_REASONS.get(exc.reason, "the header cannot be sent")
    name = str(exc.header_name).strip()
    which = f"the header {name}" if _TOKEN.fullmatch(name) else "a header"
    return f"refusing to send {which}: {reason}. --header takes non-secret headers only."


def parse_method(text: str) -> str:
    if not _METHOD.fullmatch(text):
        raise argparse.ArgumentTypeError("the method must be an HTTP method name such as GET, HEAD, or POST")
    return text.upper()


def parse_profile(text: str) -> str:
    """A marketplace profile name. The error is fixed text: it never echoes the input."""
    if text not in l402_analyze.MARKETPLACE_PROFILES:
        raise argparse.ArgumentTypeError(
            "the profile must be one of: " + ", ".join(l402_analyze.MARKETPLACE_PROFILES))
    return text


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=PROG,
        description="Report L402 compatibility without paying.",
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("url", nargs="?", help="endpoint to check (public https unless --allow-private)")
    parser.add_argument("--method", default="GET", type=parse_method,
                        help="HTTP method for the unpaid request (default GET)")
    parser.add_argument("--header", action="append", default=[], type=parse_header, metavar="NAME=VALUE",
                        help="extra non-secret request header; NAME must be an HTTP token. Credential headers "
                             "(Authorization, Cookie, Proxy-Authorization, or a name containing "
                             f"{REFUSED_FRAGMENTS}), Host and framing headers, and values with CR, LF, NUL, or "
                             "non-Latin-1 characters are refused")
    parser.add_argument("--body", help="request body to send; never printed")
    parser.add_argument("--timeout", type=float, default=l402_http.DEFAULT_TIMEOUT,
                        help=f"seconds for the whole check (more than 0, at most {MAX_TIMEOUT:g})")
    parser.add_argument("--max-sats", type=int, help="the cap for a paid check; adds a preflight verdict")
    parser.add_argument("--profile", action="append", default=[], type=parse_profile, metavar="NAME",
                        help="run an optional marketplace profile's extra read-only requests: amazap probes "
                             "/openapi.json and /llms.txt at the host root (never changes the classification)")
    parser.add_argument("--json", action="store_true", help="print JSON instead of Markdown")
    parser.add_argument("--output", metavar="PATH",
                        help="write the report to PATH as UTF-8 instead of printing it (use this, not shell "
                             "redirection, to save mode-a.json); never --evidence or --mode-a")
    parser.add_argument("--allow-private", action="store_true",
                        help="local testing only: allow loopback, private, and link-local targets, and plain "
                             "http to them; cloud metadata addresses and plain http to a public host stay refused")
    parser.add_argument("--evidence", help="validate a paid-check evidence file (a file path, never -)")
    parser.add_argument("--mode-a", help="with --evidence: the read-only report saved with --json (a file path, "
                                         "never -)")
    parser.add_argument("--credential-stdin", action="store_true",
                        help="with --evidence: read the L402 token, <macaroon>:<preimage>, from piped stdin "
                             "(never from a terminal)")
    return parser


def _unparseable_url(url: str) -> l402_http.ProbeResult | None:
    """A no_host refusal when ``url`` can't be split (a malformed bracketed host); otherwise None."""
    try:
        urlsplit(url)
    except ValueError:
        return l402_http.ProbeResult(requested_url=url, error_kind="refused", error_reason="no_host",
                                     error_message="the URL has no valid host")
    return None


def run_mode_a(
    request: l402_analyze.ProbeRequest,
    *,
    timeout: float,
    allow_private: bool,
    max_sats: int | None,
    now: datetime,
    resolver=None,
    transport=None,
    profiles: tuple[str, ...] = (),
) -> tuple[dict, set[str]]:
    """Probe once, then, with the amazap profile, the host-root metadata files; return (report, secrets).

    The metadata files are fetched only after the main request got a 402, as
    unpaid GETs with no caller headers and no body, over the same pinned
    transport; only their presence is recorded. Raises
    ``l402_http.RefusedHeaderError`` before any request when a caller header
    is a credential, a Host or framing header, or cannot be sent intact. A URL
    that can't be split at all is reported as a no_host refusal.
    """
    l402_http.check_headers(request.headers)
    result = _unparseable_url(request.url) or l402_http.probe(
        request.url, method=request.method, headers=request.headers, body=request.body,
        timeout=timeout, allow_private=allow_private, resolver=resolver, transport=transport,
    )
    root_metadata = None
    if ("amazap" in profiles and result.error_kind is None and result.final_target is not None
            and result.response is not None and result.response.status == 402):
        root_metadata = {}
        for path in ROOT_METADATA_PATHS:
            extra = l402_http.probe(result.final_target.origin + path, timeout=timeout,
                                    allow_private=allow_private, resolver=resolver, transport=transport)
            root_metadata[path] = extra.response.status if extra.response is not None and not extra.hops else None
    report = l402_analyze.analyze(request, result, now=now, root_metadata=root_metadata, max_sats=max_sats,
                                  profiles=profiles)
    return report, l402_analyze.collect_secrets(request, result)


def read_credential(stdin) -> str | None:
    """Read stdin exactly once and strip one trailing newline. Never echoed, never written anywhere."""
    text = stdin.read()
    if text.endswith("\r\n"):
        text = text[:-2]
    elif text.endswith("\n"):
        text = text[:-1]
    return text or None


def _is_terminal(stream) -> bool:
    try:
        return bool(stream.isatty())
    except (AttributeError, ValueError, OSError):
        return False


UTF16_BOMS = (b"\xff\xfe", b"\xfe\xff")


def decode_text(raw: bytes) -> str:
    """UTF-16 when the bytes start with a UTF-16 byte order mark, else UTF-8 with an optional BOM.

    Windows PowerShell 5.1 redirects output (``> file``) as UTF-16LE with a
    BOM, and some editors save UTF-8 with one; both must load. Raises
    UnicodeDecodeError for anything else.
    """
    return raw.decode("utf-16" if raw.startswith(UTF16_BOMS) else "utf-8-sig")


def _read_text(path: str, label: str) -> str:
    try:
        return decode_text(Path(path).read_bytes())
    except UnicodeDecodeError:
        raise l402_evidence.EvidenceError(f"{label} is not UTF-8 or UTF-16 text") from None
    except OSError as exc:
        raise l402_evidence.EvidenceError(f"cannot read {label}: {exc.strerror or type(exc).__name__}") from None


class OutputError(Exception):
    """The --output file can't be used. The message never echoes report content."""


def _same_file(a: str, b: str | None) -> bool:
    if b is None or b == "-":
        return False
    try:
        return Path(a).resolve() == Path(b).resolve()
    except (OSError, RuntimeError):
        return False


def write_output(path: str, text: str) -> None:
    """Write the (already scrubbed) report to ``path`` as UTF-8 with LF line endings."""
    try:
        with open(path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
    except OSError as exc:
        raise OutputError(f"cannot write the report to --output: {exc.strerror or type(exc).__name__}") from None


def _load_json(text: str, label: str):
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise l402_evidence.EvidenceError(
            f"{label} is not valid JSON (line {exc.lineno}, column {exc.colno})") from None
    except (ValueError, RecursionError):
        raise l402_evidence.EvidenceError(f"{label} is not valid JSON") from None


def run_mode_b(args, stdin) -> str:
    """Validate the evidence of one paid check and render it; return the text. Raises EvidenceError.

    stdin carries the credential only, so it is read at most once: never for
    the evidence or the Mode A file, and never from a terminal.
    """
    if "-" in (args.evidence, args.mode_a):
        raise l402_evidence.EvidenceError(
            "--evidence and --mode-a take file paths, not -: stdin carries the credential only")
    if args.credential_stdin and _is_terminal(stdin):
        raise l402_evidence.EvidenceError(
            "--credential-stdin reads a piped credential and never reads one from a terminal; "
            "pipe the token, for example with printf")
    evidence = _load_json(_read_text(args.evidence, "the evidence file"), "the evidence file")
    if args.mode_a is not None and isinstance(evidence, dict):
        if "mode_a_report" in evidence:
            raise l402_evidence.EvidenceError(
                "evidence.mode_a_report is set and --mode-a was given; give the read-only report one way only")
        # Merged first; evaluate then refuses credential keys before reading any field.
        evidence["mode_a_report"] = _load_json(_read_text(args.mode_a, "the --mode-a file"), "the --mode-a file")
    credential = read_credential(stdin) if args.credential_stdin else None
    secrets = l402_evidence.credential_secrets(credential)
    render = l402_report.to_json if args.json else l402_report.to_markdown
    try:
        return render(l402_evidence.evaluate(evidence, credential), secrets)
    except l402_evidence.EvidenceError as exc:
        raise l402_evidence.EvidenceError(l402_report.scrub(str(exc), secrets)) from None
    except (ValueError, TypeError, KeyError, AttributeError, IndexError) as exc:
        # A Mode A report or evidence file of the wrong shape. Fixed text: no value is echoed.
        raise l402_evidence.EvidenceError(
            f"the evidence or the read-only report has a field of the wrong shape ({type(exc).__name__}); "
            "produce the read-only report again with --json and check evidence.json") from None


def main(argv: list[str] | None = None, *, stdin=None, stdout=None, resolver=None, transport=None, now=None) -> int:
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    parser = build_parser()
    args = parser.parse_args(argv)
    render = l402_report.to_json if args.json else l402_report.to_markdown
    if args.output is not None:
        if args.output in ("", "-"):
            parser.error("--output takes a file path; leave it out to print the report")
        if _same_file(args.output, args.evidence) or _same_file(args.output, args.mode_a):
            parser.error("--output must not be the --evidence or --mode-a file")

    def emit(text: str) -> int:
        if args.output is None:
            stdout.write(text)
            return 0
        try:
            write_output(args.output, text)
        except OutputError as exc:
            print(f"{PROG}: error: {exc}", file=sys.stderr)
            return 2
        stdout.write(f"Wrote the report to {args.output}.\n")
        return 0

    if args.evidence is not None:
        if args.url:
            parser.error("give a URL for the read-only check or --evidence for the paid check, not both")
        if args.profile:
            parser.error("--profile goes with a URL: the paid check reuses the read-only report's profile")
        try:
            text = run_mode_b(args, stdin)
        except l402_evidence.EvidenceError as exc:
            print(f"evidence error: {exc}", file=sys.stderr)
            return 2
        return emit(text)

    if args.mode_a is not None or args.credential_stdin:
        parser.error("--mode-a and --credential-stdin go with --evidence")
    if not args.url:
        parser.error("a URL is required unless --evidence is given")
    if not 0 < args.timeout <= MAX_TIMEOUT:
        parser.error(f"--timeout must be more than 0 and at most {MAX_TIMEOUT:g} seconds")
    if args.max_sats is not None and args.max_sats <= 0:
        parser.error("--max-sats must be a positive integer")
    request = l402_analyze.ProbeRequest(
        url=args.url,
        method=args.method,
        headers=dict(args.header),
        body=args.body.encode("utf-8", "surrogateescape") if args.body is not None else None,
    )
    try:
        report, secrets = run_mode_a(
            request, timeout=args.timeout, allow_private=args.allow_private, max_sats=args.max_sats,
            now=now or datetime.now(timezone.utc), resolver=resolver, transport=transport,
            profiles=tuple(args.profile),
        )
    except l402_http.RefusedHeaderError as exc:
        # Fixed text: names the header only when the name is a plain token, never its value.
        print(f"{PROG}: error: {refusal_message(exc)}", file=sys.stderr)
        return 2
    return emit(render(report, secrets))


if __name__ == "__main__":
    sys.exit(main())
