#!/usr/bin/env python3
"""l402_check.py: report how well an endpoint implements L402, without paying.

Read-only check (Mode A, the default). One unpaid request, then a report:

  python scripts/l402_check.py https://api.example.com/resource
  python scripts/l402_check.py https://api.example.com/resource --json > mode-a.json
  python scripts/l402_check.py https://api.example.com/search --method POST --header "Accept=application/json"
  python scripts/l402_check.py https://api.example.com/resource --max-sats 50

Paid check (Mode B). The agent pays once with the Lightning Enable MCP tool
access_l402_resource (max_sats set to the approved cap), records the result in
an evidence file, and passes the credential, if the MCP returned one, on stdin:

  python scripts/l402_check.py --evidence evidence.json --mode-a mode-a.json --credential-stdin

The script never pays: it has no payment code path. It never prints an invoice
string, macaroon, token, preimage, or authorization header, and prints the
payment hash and amount only. --header takes non-secret headers only; a
credential, Host, or framing header is refused before any request.
Exit status: 0 when a report was printed, 2 for a usage, refused-header, or
evidence error. Standard library only; Python 3.10 or later.
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
_METHOD = re.compile(r"[!#$%&'*+\-.^_`|~0-9A-Za-z]{1,32}")

EPILOG = """\
Paid check: the agent pays once with the Lightning Enable MCP tool
access_l402_resource, writes the result to an evidence file (no credential in
it), and pipes the L402 token, <macaroon>:<preimage>, on stdin with
--credential-stdin. The token is read once, never echoed, and never written to
a file. Without --credential-stdin the paid check ends at most INCONCLUSIVE.

This script never pays. It never prints an invoice string, macaroon, token,
preimage, or authorization header.

Exit status:
  0  a report was printed, whatever its classification (a refused target
     prints an INCONCLUSIVE report)
  2  a usage error, a refused --header, or an evidence error; nothing is
     printed on stdout and the message never echoes a value
"""


def parse_header(text: str) -> tuple[str, str]:
    name, sep, value = text.partition("=")
    if not sep or not name.strip():
        raise argparse.ArgumentTypeError("headers take the form Name=value")
    return name.strip(), value.strip()


def parse_method(text: str) -> str:
    if not _METHOD.fullmatch(text):
        raise argparse.ArgumentTypeError("the method must be an HTTP method name such as GET, HEAD, or POST")
    return text.upper()


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
                        help="extra non-secret request header; credential headers (Authorization, Cookie, or a "
                             "name containing key, token, secret, password, session, auth, macaroon, credential, "
                             "or preimage), Host and framing headers, and values with CR, LF, NUL, or non-Latin-1 "
                             "characters are refused")
    parser.add_argument("--body", help="request body to send; never printed")
    parser.add_argument("--timeout", type=float, default=l402_http.DEFAULT_TIMEOUT,
                        help=f"seconds for the whole check (more than 0, at most {MAX_TIMEOUT:g})")
    parser.add_argument("--max-sats", type=int, help="the cap for a paid check; adds a preflight verdict")
    parser.add_argument("--json", action="store_true", help="print JSON instead of Markdown")
    parser.add_argument("--allow-private", action="store_true",
                        help="local testing only: allow loopback, private, and link-local targets, and plain "
                             "http to them; cloud metadata addresses and plain http to a public host stay refused")
    parser.add_argument("--evidence", help="validate a paid-check evidence file (use - for stdin)")
    parser.add_argument("--mode-a", help="with --evidence: the read-only report saved with --json")
    parser.add_argument("--credential-stdin", action="store_true",
                        help="with --evidence: read the L402 token, <macaroon>:<preimage>, from stdin")
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
) -> tuple[dict, set[str]]:
    """Probe once, then the host-root metadata files; return (report, secrets).

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
    root_metadata = {}
    if (result.error_kind is None and result.final_target is not None
            and result.response is not None and result.response.status == 402):
        for path in ROOT_METADATA_PATHS:
            extra = l402_http.probe(result.final_target.origin + path, timeout=timeout,
                                    allow_private=allow_private, resolver=resolver, transport=transport)
            root_metadata[path] = extra.response.status if extra.response is not None and not extra.hops else None
    report = l402_analyze.analyze(request, result, now=now, root_metadata=root_metadata, max_sats=max_sats)
    return report, l402_analyze.collect_secrets(request, result)


def read_credential(stdin) -> str | None:
    """Read stdin exactly once and strip one trailing newline. Never echoed, never written anywhere."""
    text = stdin.read()
    if text.endswith("\r\n"):
        text = text[:-2]
    elif text.endswith("\n"):
        text = text[:-1]
    return text or None


def _read_text(path: str, label: str, stdin) -> str:
    try:
        return stdin.read() if path == "-" else Path(path).read_text(encoding="utf-8")
    except UnicodeDecodeError:
        raise l402_evidence.EvidenceError(f"{label} is not UTF-8 text") from None
    except OSError as exc:
        raise l402_evidence.EvidenceError(f"cannot read {label}: {exc.strerror or type(exc).__name__}") from None


def _load_json(text: str, label: str):
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise l402_evidence.EvidenceError(
            f"{label} is not valid JSON (line {exc.lineno}, column {exc.colno})") from None
    except (ValueError, RecursionError):
        raise l402_evidence.EvidenceError(f"{label} is not valid JSON") from None


def run_mode_b(args, stdin) -> tuple[dict, set[str]]:
    """Validate the evidence of one paid check; return (report, secrets). Raises EvidenceError."""
    if args.credential_stdin and args.evidence == "-":
        raise l402_evidence.EvidenceError("--credential-stdin needs the evidence in a file, not on stdin")
    evidence = _load_json(_read_text(args.evidence, "the evidence file", stdin), "the evidence file")
    if args.mode_a and isinstance(evidence, dict):
        if "mode_a_report" in evidence:
            raise l402_evidence.EvidenceError(
                "evidence.mode_a_report is set and --mode-a was given; give the read-only report one way only")
        # Merged first; evaluate then refuses credential keys before reading any field.
        evidence["mode_a_report"] = _load_json(_read_text(args.mode_a, "the --mode-a file", stdin),
                                               "the --mode-a file")
    credential = read_credential(stdin) if args.credential_stdin else None
    secrets = l402_evidence.credential_secrets(credential)
    try:
        return l402_evidence.evaluate(evidence, credential), secrets
    except l402_evidence.EvidenceError as exc:
        raise l402_evidence.EvidenceError(l402_report.scrub(str(exc), secrets)) from None
    except (ValueError, TypeError, KeyError) as exc:
        raise l402_evidence.EvidenceError(f"the evidence could not be evaluated ({type(exc).__name__})") from None


def main(argv: list[str] | None = None, *, stdin=None, stdout=None, resolver=None, transport=None, now=None) -> int:
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    parser = build_parser()
    args = parser.parse_args(argv)
    render = l402_report.to_json if args.json else l402_report.to_markdown

    if args.evidence is not None:
        if args.url:
            parser.error("give a URL for the read-only check or --evidence for the paid check, not both")
        try:
            report, secrets = run_mode_b(args, stdin)
        except l402_evidence.EvidenceError as exc:
            print(f"evidence error: {exc}", file=sys.stderr)
            return 2
        stdout.write(render(report, secrets))
        return 0

    if args.mode_a or args.credential_stdin:
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
        )
    except l402_http.RefusedHeaderError as exc:
        # The message names the header, never its value.
        print(f"{PROG}: error: {exc}. --header takes non-secret headers only.", file=sys.stderr)
        return 2
    stdout.write(render(report, secrets))
    return 0


if __name__ == "__main__":
    sys.exit(main())
