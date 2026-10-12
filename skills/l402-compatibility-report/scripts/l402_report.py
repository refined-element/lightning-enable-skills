"""Render a compatibility report as JSON or Markdown, and scrub it.

The Markdown follows templates/report.md heading for heading. ``scrub``
replaces every known secret (a 64-hex secret in any letter case), and anything that looks like a credential (a
BOLT11 invoice, an L402, LSAT, or Payment credential, a macaroon or token
value, an Authorization header value, a preimage field, or an NWC URI), with
[REDACTED]; payment hashes and amounts survive. ``to_markdown`` scrubs its
finished text; ``to_json`` scrubs every string (keys included) in the report
and then serializes, so no redaction can split a JSON escape.
"""
from __future__ import annotations

import json
import re

SECTIONS = (
    "Summary",
    "Transport",
    "Challenge",
    "Invoice",
    "Authorization and binding",
    "Paid fulfillment",
    "Replay/idempotency",
    "Marketplace readiness",
    "Security findings",
    "Rerun notes",
    "Required fixes",
    "Evidence retained",
)
REDACTED = "[REDACTED]"
# Values left as they are: already redacted (safe_url writes REDACTED), or the
# "..." placeholder in fix text such as macaroon="...".
_KEEP_VALUES = frozenset({"REDACTED", REDACTED, "..."})

# Every pattern stays on one line ([ \t], never \s), so a match can't reach
# into the next line of the Markdown and swallow a heading.

# No word boundaries: an invoice glued to a word character is still an invoice.
BOLT11_PATTERN = re.compile(r"ln(?:bcrt|bc|tbs|tb|sb)[0-9a-z]{20,}", re.IGNORECASE)
# L402 or LSAT <token>:<preimage>, whatever the token's length.
AUTH_VALUE_PATTERN = re.compile(r"\b(L402|LSAT)[ \t]+[A-Za-z0-9+/=_\-]+:[0-9a-fA-F]{64}\b")
# A draft-00 Payment credential: Payment <base64url JSON>.
PAYMENT_CREDENTIAL_PATTERN = re.compile(r"\bPayment[ \t]+[A-Za-z0-9_\-]{16,}={0,2}")
# An NWC URI, plain or percent-encoded.
NWC_PATTERN = re.compile(
    r"nostr(?:\+|%2B)walletconnect(?::|%3A)(?://|%2F%2F)[^\s\"'<>]*", re.IGNORECASE)
# "Authorization: value", "Proxy-Authorization: value", or a JSON member of
# either: everything after the colon to the end of the line goes, so a quoted
# param inside the value can't survive.
AUTHORIZATION_PATTERN = re.compile(r"(authorization[\"']?[ \t]*:[ \t]*)([^\r\n]+)", re.IGNORECASE)
# A value under any key naming a macaroon or token (macaroon, access_token,
# csrfToken, ...): name=value, name: value, "name": "value", quoted or bare.
TOKEN_PARAM_PATTERN = re.compile(
    r"([A-Za-z0-9_\-]*(?:macaroon|token)\w*[\"']?[ \t]*[:=][ \t]*)"
    r"(\"(?:[^\"\\\r\n]|\\.)*\"|'[^'\r\n]*'|[^\s,;&\"'}\]]+)",
    re.IGNORECASE,
)
# 64 hex characters under any key containing preimage (payment_preimage,
# preimageHex, paymentPreimage), as JSON or name=value.
PREIMAGE_PATTERN = re.compile(
    r"(preimage\w*[\"']?[ \t]*[=:][ \t]*[\"']?)[0-9a-fA-F]{64}(?![0-9a-fA-F])", re.IGNORECASE)


def _redact_value(match: re.Match) -> str:
    if match.group(2).strip("\"' ,") in _KEEP_VALUES:
        return match.group(0)
    return match.group(1) + REDACTED


HEX64_SECRET = re.compile(r"[0-9a-fA-F]{64}")  # always used with fullmatch


def scrub(text: str, secrets: set[str] | frozenset[str] = frozenset()) -> str:
    for secret in sorted(secrets, key=len, reverse=True):
        if not secret:
            continue
        if HEX64_SECRET.fullmatch(secret):
            # Hex has no meaningful case: a preimage copy cased differently is the same secret.
            text = re.sub(re.escape(secret), REDACTED, text, flags=re.IGNORECASE)
        else:
            text = text.replace(secret, REDACTED)
    text = NWC_PATTERN.sub(REDACTED, text)
    text = BOLT11_PATTERN.sub(REDACTED, text)
    text = AUTH_VALUE_PATTERN.sub(lambda m: f"{m.group(1)} {REDACTED}", text)
    text = PAYMENT_CREDENTIAL_PATTERN.sub(f"Payment {REDACTED}", text)
    text = PREIMAGE_PATTERN.sub(lambda m: m.group(1) + REDACTED, text)
    text = TOKEN_PARAM_PATTERN.sub(_redact_value, text)
    return AUTHORIZATION_PATTERN.sub(_redact_value, text)


def _scrub_tree(node, secrets):
    if isinstance(node, str):
        return scrub(node, secrets)
    if isinstance(node, dict):
        # Insertion order is kept, so the JSON key order is the order the
        # analysis built the report in, which is stable from run to run.
        out: dict = {}
        for key, value in node.items():
            new_key = key
            if isinstance(key, str) and scrub(key, secrets) != key:
                # A redacted key gets a #n suffix, so two never merge and drop a value.
                scrubbed, n = scrub(key, secrets), 1
                while f"{scrubbed}#{n}" in node or f"{scrubbed}#{n}" in out:
                    n += 1
                new_key = f"{scrubbed}#{n}"
            out[new_key] = _scrub_tree(value, secrets)
        return out
    if isinstance(node, (list, tuple)):
        return [_scrub_tree(v, secrets) for v in node]
    return node


def to_json(report: dict, secrets: set[str] | frozenset[str] = frozenset()) -> str:
    # Each string is scrubbed before serializing, and the serialized text is
    # never rewritten, so a redaction can't break a JSON escape.
    return json.dumps(_scrub_tree(report, secrets), indent=2, ensure_ascii=False)


def _yes(value) -> str:
    return {True: "yes", False: "no", None: "unknown"}.get(value, str(value))


def _finding(f: dict) -> str:
    # "[code] message", never "code: message": a code such as missing_token
    # followed by a colon would read to the scrubber as a token value.
    return f"[{f['code']}] {f['message']}"


def _bullets(rows: list[str]) -> list[str]:
    return [f"- {row}" for row in rows] if rows else ["- None."]


def _value(value) -> str:
    if value is None:
        return "none"
    if isinstance(value, (list, tuple)):
        return ", ".join(str(v) for v in value) or "none"
    return str(value)


def to_markdown(report: dict, secrets: set[str] | frozenset[str] = frozenset()) -> str:
    target = report["target"]
    lines = [
        "# L402 Compatibility Report",
        "",
        f"- Target: {target['method']} {target['url']}",
        f"- Checked at: {report['checked_at']}",
        f"- Mode: {report['mode']}",
        f"- Classification: {report['classification']}",
    ]
    body = {
        "Summary": [report["summary"]],
        "Transport": _transport(report),
        "Challenge": _challenge(report),
        "Invoice": _invoice(report),
        "Authorization and binding": _binding(report),
        "Paid fulfillment": _paid(report),
        "Replay/idempotency": [report["replay"]["note"]],
        "Marketplace readiness": _marketplace(report),
        "Security findings": _bullets([_finding(f) for f in report.get("security", [])]),
        "Rerun notes": _bullets(report.get("rerun", [])),
        "Required fixes": _bullets(report.get("required_fixes", [])),
        "Evidence retained": _bullets([f"[{k}] {_value(v)}" for k, v in (report.get("evidence") or {}).items()]),
    }
    for section in SECTIONS:
        lines += ["", f"## {section}", ""] + body[section]
    return scrub("\n".join(lines) + "\n", secrets)


def _transport(report: dict) -> list[str]:
    t = report["transport"]
    rows = [
        f"Status: {t['status'] if t['status'] is not None else 'no response'}",
        f"Latency: {t['latency_ms']} ms" if t["latency_ms"] is not None else "Latency: not measured",
        f"Content type: {t['content_type'] or 'none'}",
        "Redirects: " + (", ".join(f"{h['status']} from {h['url']}" for h in t["redirects"]) or "none"),
    ]
    if t["redirects"] and t.get("final_url") and t["final_url"] not in {h["url"] for h in t["redirects"]}:
        rows.append(f"Final URL: {t['final_url']}")
    if t["error"]:
        rows.append(f"Error: {t['error']}")
    rows += [_finding(f) for f in report["findings"] if f["section"] == "transport"]
    return _bullets(rows)


def _challenge(report: dict) -> list[str]:
    c = report["challenge"]
    if not c["challenges"]:
        rows = ["No challenge parsed."]
    else:
        rows = [f"Schemes: {', '.join(c['schemes'])}", f"Classified by: {c['classified_by'] or 'none'}"]
        for entry in c["challenges"]:
            detail = f"{entry['scheme']} ({entry['kind']}): params {', '.join(entry['params']) or 'none'}"
            if entry.get("token68"):
                detail += "; token68 value present (not shown)"
            if "token_present" in entry:
                detail += (f"; token {_yes(entry['token_present'])}, invoice {_yes(entry['invoice_present'])}"
                           f"; extra params {', '.join(entry['extra_params']) or 'none'}")
            if entry["duplicate_params"]:
                detail += f"; duplicated {', '.join(entry['duplicate_params'])}"
            if entry.get("note"):
                detail += f". {entry['note']}"
            rows.append(detail)
    rows += [f"Parse error: {e}" for e in c["parse_errors"]]
    rows += [_finding(f) for f in report["findings"]
             if f["section"] == "challenge" and f["code"] != "malformed_challenge"]
    return _bullets(rows)


def _invoice(report: dict) -> list[str]:
    i = report["invoice"]
    if not i:
        return ["- No invoice decoded."]
    rows = [
        f"Network: {i['network']}",
        f"Amount: {i['amount_sats']} sats" if i["priced"] else "Amount: none (amountless invoice)",
        f"Payment hash: {i['payment_hash']}",
        f"Created: {i['created_at']}; expiry {i['expiry_seconds']} s; expires {i['expires_at']}; "
        f"{'expired' if i['expired'] else str(i['remaining_seconds']) + ' s remaining'}",
        f"Description: {i['description']}",
        f"Payee: {i['payee']}",
        f"Route hints: {i['route_hints']}; feature bits: {_yes(i['feature_bits'])}",
        "Declared price in body: "
        + ("none" if i["declared_price_sats"] is None
           else f"{i['declared_price_sats']} sats (matches: {_yes(i['declared_price_matches'])})"),
    ]
    rows += [_finding(f) for f in report["findings"] if f["section"] == "invoice"]
    return _bullets(rows)


def _binding(report: dict) -> list[str]:
    b = report["binding"]
    if not b:
        return ["- No token to inspect."]
    token_format = b["token_format"]
    bound_to = b["bound_to"]
    if token_format == "absent":
        hash_row = "not applicable (no token)"
        bound_row = "not applicable (no token)"
    elif bound_to is None:
        hash_row = "not externally verifiable"
        bound_row = "not externally verifiable"
    else:
        hash_row = {None: "none found", True: "matches the invoice", False: "differs from the invoice"}.get(
            b["payment_hash_bound"], str(b["payment_hash_bound"]))
        bound_row = "; ".join(f"{k} ({', '.join(v)})" for k, v in bound_to.items()) or "none found in caveats"
    rows = [
        f"Token format: {token_format}",
        # Worded so no row reads "token: value", which the scrubber would redact.
        f"Token payment hash: {hash_row}",
        f"Bound to: {bound_row}",
        b["note"],
    ]
    if b["unrecognized_caveats"]:
        rows.append("Unrecognized caveats: " + ", ".join(b["unrecognized_caveats"]))
    rows += [_finding(f) for f in report["findings"] if f["section"] == "binding"]
    return _bullets(rows)


def _paid(report: dict) -> list[str]:
    p = report["paid_fulfillment"]
    if not p["tested"]:
        rows = [p["note"]]
        preflight = report.get("preflight")
        if preflight:
            verdict = "allowed" if preflight["allowed"] else "not allowed: " + "; ".join(preflight["reasons"])
            rows.append(f"Preflight for a paid check capped at {preflight['max_sats']} sats: {verdict}")
        return _bullets(rows)
    rows = [
        f"Tool: {p['tool']}, cap {p['cap_sats']} sats",
        f"Paid: {p['paid_sats']} sats in {p['payments_recorded']} recorded payment(s)",
        "Payment hashes: " + (", ".join(p["payment_hashes"]) or "none recorded"),
    ]
    rows += [f"Receipt (supporting evidence): {r['amount_sats']} sats, status {r['status']}, "
             f"payment hash {r['payment_hash'] or 'none'}, context {r['context'] or 'none'}"
             for r in p.get("receipts", [])]
    if p.get("quote_payment_hash"):
        rows.append(f"Read-only quote payment hash: {p['quote_payment_hash']}; same as the paid one: "
                    f"{_yes(p.get('quote_hash_matches'))} (information only: a server may mint a fresh invoice "
                    "for each 402)")
    rows += [
        f"Preimage check: {p['preimage_check']}"
        + ("" if not p["hash_sources"]
           else " (" + "; ".join(f"[{s['source']}] {_yes(s['match'])}" for s in p["hash_sources"]) + ")"),
        "Authorized retry status: " + (str(p["status"]) if p["status"] is not None else "not reported"),
        f"Content type: {p['content_type'] or 'not reported'}; body length: "
        + (str(p["body_length"]) if p["body_length"] is not None else "not reported"),
    ]
    if p.get("tool_paid_sats") is not None and p.get("receipt_sats") is not None:
        rows.append(f"Amounts: the tool reported {p['tool_paid_sats']} sats; the receipts add up to {p['receipt_sats']} sats")
    verdict = {True: "pass", False: "fail", None: "not reported"}
    rows += [f"[{c['name']}] {verdict.get(c['pass'], 'fail')} ({c['detail']})" for c in p["expectations"]]
    rows += [_finding(f) for f in report["findings"] if f["section"] == "paid"]
    return _bullets(rows)


def _marketplace(report: dict) -> list[str]:
    m = report["marketplace"]
    rows = [f"[{c['name']}] {'pass' if c['pass'] else 'fail'}. {c['detail']}" for c in m["checks"]]
    rows += [f"Not checked by the script: {item}" for item in m["not_checked_by_script"]]
    rows += [_finding(f) for f in report["findings"] if f["section"] == "marketplace"]
    rows.append(m["note"])
    return _bullets(rows)
