"""Turn one unpaid probe into a Mode A (read-only) compatibility report.

The report is a plain dict, ready for ``l402_report`` to render as JSON or
Markdown. It holds parameter names, decoded invoice metadata, the payment
hash, and the amount; it never holds an invoice string, a macaroon or token,
or a header value the caller marked as a credential. URLs keep their path and
query string as given but lose any userinfo and fragment. ``collect_secrets``
returns every string that must stay out of output, so the renderer can prove
none slipped through.

Mode A never pays, so its best classification is CHALLENGE_COMPATIBLE. The
optional Amazap marketplace profile is computed beside the core sections and
never changes the classification, the findings, or the required fixes.
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from urllib.parse import unquote, unquote_plus, urlsplit

import l402_bolt11
import l402_challenge
import l402_http
import l402_macaroon
from l402_http import ProbeResult
# The shared vocabulary lives in l402_levels; it is re-exported here for callers of this module.
from l402_levels import (  # noqa: F401
    CHALLENGE_COMPATIBLE,
    CLASSIFICATIONS,
    FIXES,
    FULFILLMENT_VERIFIED,
    INCOMPATIBLE,
    INCONCLUSIVE,
    MARKETPLACE_PROFILES,
    PAYMENT_COMPATIBLE,
    PROFILE_STATUSES,
    REPORT_VERSION,
    TRANSIENT_STATUSES,
    Finding,
    profile_note,
    profile_status,
)

AMAZAP_PROBE_WINDOW_MS = 8000
# The host every Lightning Enable proxy shares; its host-root files describe the platform.
LIGHTNING_ENABLE_HOST = "api.lightningenable.com"
SHORT_LIVED_SECONDS = 60
PAID_CHECK_METHODS = ("GET", "HEAD")
# Reasons l402_netsafety gives for refusing a redirect target in a blocked range.
BLOCKED_RANGE_REASONS = frozenset({"private_address", "cloud_metadata"})
SECRET_PARAM_NAMES = frozenset({"macaroon", "token", "invoice", "request", "opaque", "credential", "preimage"})
CREDENTIAL_HEADER = re.compile(r"authorization|cookie|token|secret|key|session|signature|password", re.IGNORECASE)
# Query keys whose values are redacted. Matched as substrings, so api_key,
# apikey, access_token, and signature are covered by key, token, and sig.
SENSITIVE_QUERY = re.compile(
    r"key|api_key|apikey|token|access_token|secret|password|passwd|auth|signature|sig|session|"
    r"macaroon|preimage|credential",
    re.IGNORECASE,
)
URL_USERINFO = re.compile(r"^([A-Za-z][A-Za-z0-9+.\-]*://)[^/?#]*@")
BOLT11_TEXT = re.compile(r"\bln(?:bcrt|bc|tbs|tb)[0-9a-z]{50,}\b", re.IGNORECASE)
DECLARED_PRICE_KEYS = ("amountsats", "pricesats", "sats")
X402_OUTSIDE_HEADER = re.compile(r"x402", re.IGNORECASE)
X402_HEADERS = ("X-PAYMENT", "X-PAYMENT-REQUIRED", "PAYMENT-REQUIRED")
BODY_SECRET_PATTERNS = (
    ("nwc_connection_string", re.compile(r"nostr\+walletconnect://", re.IGNORECASE)),
    ("private_key_block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("extended_private_key", re.compile(r"\b[xtyz]prv[1-9A-HJ-NP-Za-km-z]{100,}")),
    ("stripe_live_key", re.compile(r"\b[rs]k_live_[0-9A-Za-z]{16,}")),
    ("aws_access_key_id", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("preimage", re.compile(r'"preimage"\s*:\s*"[0-9a-fA-F]{64}"')),
)


# Guidance for the person running the check, by finding code. These are not
# server fixes, so they never enter required_fixes; the report lists them
# under "rerun".
RERUN_NOTES = {
    "method_not_allowed": "Rerun the check with the method the endpoint accepts.",
}


@dataclass
class ProbeRequest:
    url: str
    method: str = "GET"
    headers: dict = field(default_factory=dict)
    body: bytes | None = None


_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def iso(moment: datetime | int) -> str:
    """UTC ISO 8601 with a Z. An int is Unix seconds; one past year 9999 is reported as out of range."""
    if isinstance(moment, int):
        try:
            moment = _EPOCH + timedelta(seconds=moment)
        except OverflowError:
            return f"out of range ({moment} s after the Unix epoch)"
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sensitive_query_key(raw_key: str) -> bool:
    """True when the key, as sent or percent-decoded, names a credential."""
    return bool(SENSITIVE_QUERY.search(raw_key) or SENSITIVE_QUERY.search(unquote_plus(raw_key)))


def _query_pairs(url: str) -> list[tuple[str, str]]:
    """(raw key, raw value) for every ``key=value`` piece of the query, never decoded."""
    query = url.split("#", 1)[0].partition("?")[2]
    pairs = []
    for piece in query.split("&"):
        key, sep, value = piece.partition("=")
        if sep:
            pairs.append((key, value))
    return pairs


def safe_url(url: str) -> str:
    """``url`` without userinfo or fragment, and with every credential query value replaced by REDACTED.

    Works on the raw text: nothing is decoded or re-encoded, so the path and the
    rest of the query stay exactly as given, and a percent-encoded value is
    replaced whole.
    """
    text = URL_USERINFO.sub(r"\1", url.split("#", 1)[0])
    base, sep, query = text.partition("?")
    if not sep:
        return base
    pieces = []
    for piece in query.split("&"):
        key, eq, value = piece.partition("=")
        if eq and value and _sensitive_query_key(key):
            piece = f"{key}=REDACTED"
        pieces.append(piece)
    return f"{base}?{'&'.join(pieces)}"


def _is_credential_header(name: str) -> bool:
    return l402_http.is_credential_header(name) or bool(CREDENTIAL_HEADER.search(name))


def safe_headers(headers: dict) -> dict:
    return {k: ("[REDACTED]" if _is_credential_header(k) else v) for k, v in headers.items()}


def _userinfo(url: str) -> list[str]:
    try:
        parts = urlsplit(url)
        return [v for v in (parts.username, parts.password) if v]
    except ValueError:
        return []


def collect_secrets(request: ProbeRequest, probe_result: ProbeResult) -> set[str]:
    """Every string that must never appear in output.

    Credential query values are collected raw and percent-decoded from the
    requested URL, every hop, and the final target, so a scrub of the rendered
    output catches every form a value could take. Like every other secret, a
    value joins the set only at 8 or more characters; shorter ones are still
    redacted in place by ``safe_url``.
    """
    secrets = {str(v) for k, v in request.headers.items() if _is_credential_header(k) and v}
    query_values: set[str] = set()
    urls = [request.url] + [hop.url for hop in probe_result.hops]
    if probe_result.final_target is not None:
        urls.append(probe_result.final_target.url)
    for url in urls:
        secrets.update(_userinfo(url))
        for key, value in _query_pairs(url):
            if value and _sensitive_query_key(key):
                query_values.update({value, unquote(value), unquote_plus(value)})
    response = probe_result.response
    if response is not None:
        values = response.header_values("WWW-Authenticate")
        parsed = l402_challenge.parse(values)
        for challenge in parsed.challenges:
            if challenge.token68:
                secrets.add(challenge.token68)
            for name, value in challenge.params.items():
                if name in SECRET_PARAM_NAMES and value:
                    secrets.add(value)
        for text in values:
            secrets.update(BOLT11_TEXT.findall(text))
        secrets.update(BOLT11_TEXT.findall(response.body.decode("utf-8", errors="replace")))
    # safe_url redacts query credentials of any length in place; only values of
    # 8 or more characters join the scrub set, so a short value such as
    # sig=ab can't redact unrelated text elsewhere in the output.
    return {s for s in secrets | query_values if len(s) >= 8}


def _declared_price(body: bytes) -> int | None:
    try:
        data = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, ValueError, RecursionError):
        return None
    stack = [data]
    while stack:
        node = stack.pop(0)
        if isinstance(node, dict):
            for key, value in node.items():
                normalized = key.replace("_", "").lower()
                if normalized in DECLARED_PRICE_KEYS and isinstance(value, int) and not isinstance(value, bool):
                    return value
                stack.append(value)
        elif isinstance(node, list):
            stack.extend(node)
    return None


def _challenge_entry(challenge: l402_challenge.Challenge) -> dict:
    entry = {
        "scheme": challenge.scheme,
        "kind": challenge.kind,
        "params": sorted(challenge.params),
        "duplicate_params": sorted(set(challenge.duplicate_params)),
        "token68": challenge.token68 is not None,
    }
    if challenge.kind in ("L402", "LSAT"):
        entry["token_present"] = bool(challenge.param("macaroon") or challenge.param("token"))
        entry["invoice_present"] = bool(challenge.param("invoice"))
        entry["extra_params"] = sorted(set(challenge.params) - {"macaroon", "invoice"})
    elif challenge.kind == "Payment":
        entry["note"] = "Payment is its own scheme, reported separately; it is not classic L402."
    return entry


def _status_finding(status: int, method: str, sent_body: bool, allow: str | None = None) -> Finding:
    if status == 405:
        # Only method tokens are echoed from Allow, never free text.
        methods = [m.strip() for m in (allow or "").split(",") if re.fullmatch(r"[A-Za-z]{1,16}", m.strip())]
        allowed = f" The endpoint allows: {', '.join(methods)}." if methods else ""
        return Finding("method_not_allowed", "warning", "transport", f"An unpaid {method} got 405 Method Not Allowed.{allowed}")
    if 200 <= status < 300:
        return Finding("unpaid_2xx", "error", "transport", f"An unpaid request got {status}: the resource is served without payment.")
    if status == 401:
        return Finding("unpaid_401", "error", "transport", "An unpaid request got 401: ordinary authentication runs before the L402 check.")
    if status in (400, 422):
        return Finding("validation_before_challenge", "error", "transport", f"An unpaid request got {status}: input validation runs before the 402 challenge.")
    if status == 415:
        what = f"empty-body {method}" if not sent_body else f"{method} request"
        return Finding("unsupported_media_before_challenge", "error", "transport", f"An unpaid {what} got 415: content-type validation runs before the 402 challenge.")
    return Finding("unexpected_status", "error", "transport", f"An unpaid request got {status}, not 402 Payment Required.")


def analyze(
    request: ProbeRequest,
    probe_result: ProbeResult,
    *,
    now: datetime,
    root_metadata: dict | None = None,
    max_sats: int | None = None,
    profiles: tuple[str, ...] = (),
) -> dict:
    """Build the Mode A report for one probe.

    ``profiles`` names the marketplace profiles the caller requested (``--profile``).
    ``root_metadata`` is None when the host root was not probed: either the amazap
    profile was not requested, or it was and the probe got no 402.
    """
    findings: list[Finding] = []
    response = probe_result.response
    target = probe_result.final_target
    # When the probe stopped with an error after a response, that response is
    # the last recorded hop (a redirect it did not follow), not a further answer.
    response_is_last_hop = response is not None and probe_result.error_kind is not None and bool(probe_result.hops)
    report: dict = {
        "report_version": REPORT_VERSION,
        "mode": "read-only",
        "checked_at": iso(now),
        "target": {
            "url": safe_url(request.url),
            "method": request.method.upper(),
            "headers": safe_headers(request.headers),
            "body": "none" if not request.body else f"provided ({len(request.body)} bytes, not shown)",
        },
        "transport": {
            "status": response.status if response else None,
            "latency_ms": response.elapsed_ms if response else None,
            "redirects": [{"url": safe_url(h.url), "status": h.status} for h in probe_result.hops],
            "final_url": safe_url(target.url) if target else None,
            "content_type": response.header("Content-Type") if response else None,
            "error": probe_result.error_kind,
        },
        "challenge": {"schemes": [], "classified_by": None, "multi_scheme": False, "challenges": [], "parse_errors": []},
        "invoice": None,
        "binding": None,
        "paid_fulfillment": {"tested": False, "note": "Not tested: the read-only check never pays."},
        "replay": {"tested": False, "note": "Not tested: replay needs a paid credential."},
    }
    classification = _transport(probe_result, request, findings)
    invoice = None
    if classification is None:
        classification, invoice = _challenge_and_invoice(report, response, now, findings)
    _security(response, target, findings)
    _manifest_link(response, findings)
    amazap = _amazap_profile(request, probe_result, invoice, root_metadata, "amazap" in profiles)
    report["classification"] = classification
    report["findings"] = [asdict(f) | {"fix": f.fix} for f in findings]
    report["required_fixes"] = list(dict.fromkeys(f.fix for f in findings if f.fix and f.severity == "error"))
    report["rerun"] = list(dict.fromkeys(RERUN_NOTES[f.code] for f in findings if f.code in RERUN_NOTES))
    report["security"] = [asdict(f) for f in findings if f.section == "security"]
    report["preflight"] = _preflight(classification, request, invoice, max_sats) if max_sats is not None else None
    report["summary"] = _summary(classification, report)
    statuses = [h["status"] for h in report["transport"]["redirects"]]
    if response is not None and not response_is_last_hop:
        statuses.append(response.status)
    report["evidence"] = {
        "timestamp": report["checked_at"],
        "url": report["target"]["url"],
        "method": report["target"]["method"],
        "statuses": statuses,
        "amount_sats": report["invoice"]["amount_sats"] if report["invoice"] else None,
        "payment_hash": report["invoice"]["payment_hash"] if report["invoice"] else None,
        "latency_ms": report["transport"]["latency_ms"],
        "classification": classification,
    }
    amazap["status"] = profile_status(classification, amazap["checks"])
    amazap["note"] = profile_note(amazap["status"])
    report["marketplace_profiles"] = {"amazap": amazap}
    return report


def _redirect_refused(probe_result: ProbeResult) -> tuple[Finding, str]:
    reason = probe_result.error_reason
    message = probe_result.error_message or "the redirect was not followed"
    if reason in BLOCKED_RANGE_REASONS:
        return Finding("redirect_into_blocked_range", "error", "security",
                       "A redirect leads to a blocked address range; it was not followed."), INCOMPATIBLE
    if reason == "downgrade":
        return Finding("redirect_downgrade", "error", "security",
                       "A redirect leads from https to plain http; it was not followed."), INCOMPATIBLE
    if reason == "not_https":
        # The probe refuses https-to-http first, so here the origin was already http (a local test).
        return Finding("redirect_not_https", "error", "security",
                       "A redirect from a local plain http address leads to a public plain http URL; "
                       "public endpoints must use https, so it was not followed."), INCOMPATIBLE
    if reason == "redirect_cross_origin_with_body":
        # The check's own safety rule, not a protocol defect: HTTP allows the redirect.
        return Finding("redirect_body_not_resent", "warning", "transport",
                       f"{message[:1].upper()}{message[1:]}, so the check could not reach a 402."), INCONCLUSIVE
    return Finding("redirect_refused", "error", "security",
                   f"A redirect target was refused: {message}."), INCOMPATIBLE


def _transport(probe_result: ProbeResult, request: ProbeRequest, findings: list[Finding]) -> str | None:
    kind = probe_result.error_kind
    if kind == "refused":
        findings.append(Finding("refused_target", "info", "security", probe_result.error_message or "target refused"))
        return INCONCLUSIVE
    if kind == "redirect_refused":
        finding, classification = _redirect_refused(probe_result)
        findings.append(finding)
        return classification
    if kind == "redirect_limit":
        findings.append(Finding("redirect_limit", "error", "transport", probe_result.error_message or "too many redirects"))
        return INCOMPATIBLE
    if kind in ("timeout", "network", "dns"):
        findings.append(Finding(f"transport_{kind}", "warning", "transport", probe_result.error_message or kind))
        return INCONCLUSIVE
    if kind is not None or probe_result.response is None:
        findings.append(Finding("transport_unknown", "warning", "transport", probe_result.error_message or "no response"))
        return INCONCLUSIVE
    status = probe_result.response.status
    if status == 402:
        return None
    if status >= 500:
        findings.append(Finding("server_error", "warning", "transport", f"An unpaid request got {status}; retry later."))
        return INCONCLUSIVE
    if status in TRANSIENT_STATUSES:
        findings.append(Finding("transient_status", "warning", "transport", f"An unpaid request got {status}; retry later."))
        return INCONCLUSIVE
    finding = _status_finding(status, request.method.upper(), bool(request.body), probe_result.response.header("Allow"))
    findings.append(finding)
    # A 405 most likely means the check used a method the endpoint never serves:
    # the caller can rerun, so it says nothing certain about the server.
    return INCONCLUSIVE if finding.code == "method_not_allowed" else INCOMPATIBLE


def _challenge_and_invoice(report: dict, response, now: datetime, findings: list[Finding]):
    headers = response.header_values("WWW-Authenticate")
    _x402_outside_header(response, headers, findings)
    if not headers:
        findings.append(Finding("missing_www_authenticate", "error", "challenge", "The 402 carries no WWW-Authenticate header."))
        return INCOMPATIBLE, None
    parsed = l402_challenge.parse(headers)
    section = report["challenge"]
    section["challenges"] = [_challenge_entry(c) for c in parsed.challenges]
    section["schemes"] = [c.kind if c.kind != "other" else c.scheme for c in parsed.challenges]
    section["multi_scheme"] = len({c.kind for c in parsed.challenges}) > 1
    section["parse_errors"] = list(parsed.errors)
    primary = next((c for c in parsed.challenges if c.kind == "L402"), None) or next(
        (c for c in parsed.challenges if c.kind == "LSAT"), None
    )
    section["classified_by"] = primary.kind if primary else None
    # A challenge that does not parse, or that offers no L402, is rejected
    # before any invoice is decoded: a value cut short by bad quoting is not
    # the server's invoice, and a Payment invoice is not an L402 quote.
    if parsed.errors:
        findings.append(Finding("malformed_challenge", "error", "challenge", "WWW-Authenticate does not parse: " + "; ".join(parsed.errors) + "."))
    if primary is None:
        findings.append(Finding("no_l402_challenge", "error", "challenge", "No L402 or LSAT challenge; schemes present: " + (", ".join(section["schemes"]) or "none") + "."))
    if parsed.errors or primary is None:
        return INCOMPATIBLE, None
    same_kind = [c for c in parsed.challenges if c.kind == primary.kind]
    if len(same_kind) > 1:
        findings.append(Finding("multiple_l402_challenges", "warning", "challenge",
                                f"The 402 carries {len(same_kind)} {primary.kind} challenges; the first one was checked."))
    if primary.duplicate_params:
        findings.append(Finding("duplicate_params", "error", "challenge",
                                f"Repeated auth-params in the {primary.kind} challenge: "
                                + ", ".join(sorted(set(primary.duplicate_params))) + "."))
    for challenge in parsed.challenges:
        if challenge is not primary and challenge.duplicate_params:
            name = challenge.kind if challenge.kind != "other" else challenge.scheme
            findings.append(Finding("duplicate_params_other_scheme", "info", "challenge",
                                    f"Repeated auth-params in a {name} challenge: "
                                    + ", ".join(sorted(set(challenge.duplicate_params))) + "."))
    others = [s for c, s in zip(parsed.challenges, section["schemes"]) if c.kind not in ("L402", "LSAT")]
    if others:
        findings.append(Finding("other_schemes", "info", "challenge", "Also offered, reported separately: " + ", ".join(dict.fromkeys(others)) + "."))
    token = primary.param("macaroon") or primary.param("token")
    if not token:
        findings.append(Finding("missing_token", "error", "challenge", f"The {primary.kind} challenge has no macaroon or token parameter."))
    raw_invoice = primary.param("invoice")
    if not raw_invoice:
        findings.append(Finding("missing_invoice", "error", "challenge", f"The {primary.kind} challenge has no invoice parameter."))
    invoice = None
    if raw_invoice:
        try:
            invoice = l402_bolt11.decode(raw_invoice)
        except l402_bolt11.Bolt11Error as exc:
            findings.append(Finding("invalid_invoice", "error", "invoice", f"The invoice does not decode as BOLT11: {exc}."))
    if invoice is not None:
        report["invoice"] = _invoice_section(invoice, response, now, findings)
    report["binding"] = _binding(token, invoice, findings)
    if any(f.severity == "error" for f in findings):
        return INCOMPATIBLE, invoice
    return CHALLENGE_COMPATIBLE, invoice


def _x402_outside_header(response, www_authenticate: list[str], findings: list[Finding]) -> None:
    """x402 can live in the body or X-PAYMENT headers, not only in WWW-Authenticate."""
    if any(c.kind == "x402" for c in l402_challenge.parse(www_authenticate).challenges):
        return
    in_headers = [name for name in X402_HEADERS if response.header_values(name)]
    in_body = bool(X402_OUTSIDE_HEADER.search(response.body.decode("utf-8", errors="replace")))
    if in_headers or in_body:
        where = ", ".join((["the response body"] if in_body else []) + [f"the {h} header" for h in in_headers])
        findings.append(Finding("x402_outside_header", "info", "challenge",
                                f"x402 appears in {where}; it is a separate scheme, reported by name only."))


def _invoice_section(invoice: l402_bolt11.Invoice, response, now: datetime, findings: list[Finding]) -> dict:
    remaining = invoice.expires_at - int(now.timestamp())
    declared = _declared_price(response.body)
    section = {
        "network": invoice.network,
        "amount_sats": invoice.amount_sats,
        "amount_msat": invoice.amount_msat,
        "priced": invoice.amount_msat is not None,
        "payment_hash": invoice.payment_hash,
        "created_at": iso(invoice.timestamp),
        "expiry_seconds": invoice.expiry_seconds,
        "expires_at": iso(invoice.expires_at),
        "remaining_seconds": max(remaining, 0),
        "expired": remaining <= 0,
        "description": "present" if invoice.has_description else ("hash" if invoice.has_description_hash else "none"),
        "payee": invoice.payee or "not stated (needs signature recovery)",
        "route_hints": invoice.route_hint_count,
        "feature_bits": invoice.has_features,
        "declared_price_sats": declared,
        "declared_price_matches": None if declared is None or invoice.amount_sats is None else declared == invoice.amount_sats,
    }
    if invoice.amount_msat is None:
        findings.append(Finding("amountless_invoice", "error", "invoice", "The invoice has no amount."))
    if remaining <= 0:
        findings.append(Finding("expired_invoice", "error", "invoice", "The invoice had already expired when it was checked."))
    elif remaining < SHORT_LIVED_SECONDS:
        findings.append(Finding("short_lived_invoice", "warning", "invoice", f"The invoice expires {remaining} s after the check."))
    if invoice.network != "mainnet":
        findings.append(Finding("non_mainnet_invoice", "warning", "invoice", f"The invoice is for {invoice.network}."))
    if section["declared_price_matches"] is False:
        findings.append(Finding("body_price_mismatch", "error", "invoice", f"The body declares {declared} sats; the invoice asks {invoice.amount_sats}."))
    return section


def _caveat_payment_hashes(info: l402_macaroon.MacaroonInfo, keys: list[str]) -> list[str]:
    """Values of payment-hash caveats (``key=value`` or ``key value``), lowercased."""
    values = []
    for caveat in info.caveats:
        key, _, value = caveat.partition("=")
        if not value:
            key, _, value = caveat.partition(" ")
        if key.strip().lower() in keys and value.strip():
            values.append(value.strip().lower())
    return values


def _binding(token: str | None, invoice, findings: list[Finding]) -> dict:
    if not token:
        return {
            "token_format": "absent",
            "externally_verifiable": False,
            "payment_hash_bound": None,
            "bound_to": None,
            "unrecognized_caveats": [],
            "note": "The challenge carries no macaroon or token, so there is nothing to bind.",
        }
    info = l402_macaroon.inspect(token)
    bindings = info.bindings()
    if bindings is None:
        return {
            "token_format": "opaque",
            "externally_verifiable": False,
            "payment_hash_bound": None,
            "bound_to": None,
            "unrecognized_caveats": [],
            "note": "The token is opaque: binding is not externally verifiable, which is not the same as absent.",
        }
    claimed = ([info.payment_hash] if info.payment_hash else []) + _caveat_payment_hashes(info, bindings.get("payment_hash", []))
    bound = None
    if claimed and invoice is not None and invoice.payment_hash:
        bound = all(value == invoice.payment_hash for value in claimed)
        if not bound:
            findings.append(Finding("payment_hash_unbound", "error", "binding",
                                    "The macaroon carries a different payment hash than the invoice."))
    unrecognized = info.unrecognized_caveat_keys()
    verifiable = True
    if not info.caveats:
        note = "The macaroon decoded and has no first-party caveats: it binds no method, path, or body."
    elif unrecognized and not bindings and bound is None:
        verifiable = False
        note = "Caveats are present but not recognized: binding is not externally verifiable."
    else:
        note = "Bindings inferred from caveat names."
    if info.third_party_caveats:
        note += f" {info.third_party_caveats} third-party caveat(s) can't be inspected."
    return {
        "token_format": info.format,
        "externally_verifiable": verifiable,
        "payment_hash_bound": bound,
        "bound_to": bindings,
        "unrecognized_caveats": unrecognized,
        "note": note,
    }


def _security(response, target, findings: list[Finding]) -> None:
    if response is None:
        return
    text = response.body.decode("utf-8", errors="replace")
    kinds = [name for name, pattern in BODY_SECRET_PATTERNS if pattern.search(text)]
    if kinds:
        findings.append(Finding("unpaid_body_secret", "error", "security", "The unpaid response body contains: " + ", ".join(kinds) + "."))
    if target is not None and target.scheme == "http":
        findings.append(Finding("plain_http", "warning", "security", "The check ran over plain http (local testing only)."))


def _manifest_link(response, findings: list[Finding]) -> None:
    """A 402 that links an L402 manifest tells agents where its paid routes and prices are."""
    if response is None or response.status != 402:
        return
    if any('rel="l402-manifest"' in link for link in response.header_values("Link")):
        findings.append(Finding("l402_manifest_link", "info", "challenge",
                                'The 402 links an L402 manifest (rel="l402-manifest"); agents read it to discover '
                                "the endpoint's paid routes and prices."))


def _check(name: str, ok, detail: str, required: bool = True) -> dict:
    return {"name": name, "pass": ok, "required": required, "detail": detail}


def _host_root_check(target, root_metadata: dict | None, requested: bool) -> dict:
    """Advisory: Amazap's listing prefill reads openapi.json or llms.txt at the host root.

    ``requested`` is True when --profile amazap asked for the host-root probe;
    with ``root_metadata`` None it means the probe was skipped because no 402 came.
    """
    if target is not None and target.host == LIGHTNING_ENABLE_HOST:
        return _check("host_root_metadata", False,
                      "On api.lightningenable.com the host-root openapi.json and llms.txt describe the Lightning "
                      "Enable platform, not this endpoint, so Amazap's prefill can't use them; supply the title, "
                      "description, category, and example parameters by hand.", required=False)
    if root_metadata is None and requested:
        return _check("host_root_metadata", None,
                      "Skipped: --profile amazap was given, but the host root is probed only after the listed URL "
                      "answers 402, and it did not. Fix the 402 first, then run the check again.",
                      required=False)
    if root_metadata is None:
        return _check("host_root_metadata", None,
                      "Not probed: add --profile amazap to look for openapi.json or llms.txt at the host root, "
                      "where Amazap's listing prefill looks. Without them, supply the listing fields by hand.",
                      required=False)
    found = sorted(path for path, status in root_metadata.items() if status == 200)
    return _check("host_root_metadata", bool(found),
                  "openapi.json or llms.txt at the host root, where Amazap's listing prefill looks: "
                  + (", ".join(found) or "none found; supply the listing fields by hand") + ".",
                  required=False)


def _amazap_profile(request: ProbeRequest, probe_result: ProbeResult, invoice, root_metadata: dict | None,
                    requested: bool = False) -> dict:
    """The optional Amazap listing profile. It adds no finding and no required fix.

    ``root_metadata`` is None when the host root was not probed; ``requested``
    tells "not asked for" (no --profile amazap) from "asked for, but skipped
    because no 402 came". The caller sets ``status`` and ``note`` once the
    classification is known.
    """
    response = probe_result.response
    target = probe_result.final_target
    latency = f" (took {response.elapsed_ms} ms)" if response is not None else ""
    checks = [
        _check("public_https", bool(target and target.scheme == "https" and target.is_public), "Public https endpoint."),
        _check("priced_invoice", bool(invoice and invoice.amount_msat is not None), "The invoice carries an amount."),
        _check("mainnet_invoice", bool(invoice and invoice.network == "mainnet"), "The invoice is for mainnet."),
        _check("probe_without_body", bool(response and response.status == 402 and not request.body),
               "An unpaid request with no body gets the 402 (Amazap's listing probe sends the listed method "
               "with no body)."),
        _check("within_probe_window", bool(response and response.elapsed_ms <= AMAZAP_PROBE_WINDOW_MS),
               f"The 402 arrives within 8 seconds, the time Amazap's listing probe waits{latency}."),
        _check("stable_path", not probe_result.hops, "No redirect between the listed URL and the 402."),
        _host_root_check(target, root_metadata, requested),
    ]
    return {
        "status": None,
        "checks": checks,
        "not_checked_by_script": [
            "example parameters for the listing",
            "a synchronous, bounded response",
            "stable price over time (the paid check compares the paid amount with this quote)",
        ],
        "note": None,
    }


def _preflight(classification: str, request: ProbeRequest, invoice, max_sats: int) -> dict:
    reasons = []
    if classification != CHALLENGE_COMPATIBLE:
        reasons.append(f"the read-only check is {classification}, not {CHALLENGE_COMPATIBLE}")
    if request.method.upper() not in PAID_CHECK_METHODS:
        reasons.append("access_l402_resource pays GET and HEAD requests only")
    amount = invoice.amount_sats if invoice is not None else None
    if amount is None:
        reasons.append("no priced invoice")
    elif amount > max_sats:
        reasons.append(f"the invoice asks {amount} sats, over the {max_sats}-sat cap")
    return {"max_sats": max_sats, "invoice_sats": amount, "allowed": not reasons, "reasons": reasons}


def _summary(classification: str, report: dict) -> str:
    invoice = report["invoice"] or {}
    if classification == CHALLENGE_COMPATIBLE:
        others = [s for s in report["challenge"]["schemes"] if s not in ("L402", "LSAT")]
        extra = f" Other schemes offered: {', '.join(dict.fromkeys(others))}." if others else ""
        return (
            f"A valid unpaid {report['challenge']['classified_by']} challenge with a priced invoice "
            f"({invoice.get('amount_sats')} sats) was observed. Paid fulfillment was not tested.{extra}"
        )
    if classification == INCOMPATIBLE:
        return "A protocol or transport defect prevents the L402 flow. See Required fixes."
    return "The check could not determine compatibility. See Transport and Security findings."
