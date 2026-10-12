"""Render a compatibility report as JSON or Markdown, and scrub it.

The Markdown follows templates/report.md heading for heading. ``scrub``
replaces every known secret, and anything that looks like a credential (a
BOLT11 invoice, an L402 or LSAT authorization value, a macaroon or token
auth-param value, an Authorization header value, a preimage field, or an NWC
URI), with [REDACTED]; payment hashes and amounts survive. Both renderers
call it last, and ``to_json`` also scrubs every string in the report before
serializing it, so a secret that JSON would escape is still caught.
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
# Values the analysis already redacted in place (safe_url writes REDACTED).
_ALREADY_REDACTED = frozenset({"REDACTED", REDACTED})

# No word boundaries: an invoice glued to a word character is still an invoice.
BOLT11_PATTERN = re.compile(r"ln(?:bcrt|bc|tbs|tb)[0-9a-z]{20,}", re.IGNORECASE)
AUTH_VALUE_PATTERN = re.compile(r"\b(L402|LSAT)\s+[A-Za-z0-9+/=_\-]{16,}:[0-9a-fA-F]{64}\b")
NWC_PATTERN = re.compile(r"nostr\+walletconnect://[^\s\"'<>]*", re.IGNORECASE)
# "Authorization: value", "Proxy-Authorization: value", or a JSON member of either.
AUTHORIZATION_PATTERN = re.compile(r"(\bauthorization[\"']?\s*:\s*[\"']?)([^\"'\r\n]+)", re.IGNORECASE)
# A macaroon or token auth-param or query value: name=value or name="value".
TOKEN_PARAM_PATTERN = re.compile(r"(\b(?:macaroon|token)\s*=\s*)(\"(?:[^\"\\]|\\.)*\"|[^\s,;&\"']+)", re.IGNORECASE)
# 64 hex characters in a field named preimage, as JSON or name=value.
PREIMAGE_PATTERN = re.compile(r"(\bpreimage[\"']?\s*[=:]\s*[\"']?)[0-9a-fA-F]{64}(?![0-9a-fA-F])", re.IGNORECASE)


def _redact_value(match: re.Match) -> str:
    value = match.group(2)
    if value.strip("\"' ") in _ALREADY_REDACTED:
        return match.group(0)
    return match.group(1) + REDACTED


def scrub(text: str, secrets: set[str] | frozenset[str] = frozenset()) -> str:
    for secret in sorted(secrets, key=len, reverse=True):
        if secret:
            text = text.replace(secret, REDACTED)
    text = NWC_PATTERN.sub(REDACTED, text)
    text = BOLT11_PATTERN.sub(REDACTED, text)
    text = AUTH_VALUE_PATTERN.sub(lambda m: f"{m.group(1)} {REDACTED}", text)
    text = AUTHORIZATION_PATTERN.sub(_redact_value, text)
    text = TOKEN_PARAM_PATTERN.sub(_redact_value, text)
    return PREIMAGE_PATTERN.sub(lambda m: m.group(1) + REDACTED, text)


def _scrub_tree(node, secrets):
    if isinstance(node, str):
        return scrub(node, secrets)
    if isinstance(node, dict):
        return {(scrub(k, secrets) if isinstance(k, str) else k): _scrub_tree(v, secrets) for k, v in node.items()}
    if isinstance(node, (list, tuple)):
        return [_scrub_tree(v, secrets) for v in node]
    return node


def to_json(report: dict, secrets: set[str] | frozenset[str] = frozenset()) -> str:
    # Escaped forms catch a secret holding a quote, backslash, or control character.
    escaped = {json.dumps(s, ensure_ascii=False)[1:-1] for s in secrets if s}
    text = json.dumps(_scrub_tree(report, secrets), indent=2, ensure_ascii=False)
    return scrub(text, set(secrets) | escaped)


def _yes(value) -> str:
    return {True: "yes", False: "no", None: "unknown"}.get(value, str(value))


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
        "Security findings": _bullets([f"{f['code']}: {f['message']}" for f in report.get("security", [])]),
        "Rerun notes": _bullets(report.get("rerun", [])),
        "Required fixes": _bullets(report.get("required_fixes", [])),
        "Evidence retained": _bullets([f"{k}: {_value(v)}" for k, v in (report.get("evidence") or {}).items()]),
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
    rows += [f"{f['code']}: {f['message']}" for f in report["findings"] if f["section"] == "transport"]
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
    rows += [f"{f['code']}: {f['message']}" for f in report["findings"]
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
    rows += [f"{f['code']}: {f['message']}" for f in report["findings"] if f["section"] == "invoice"]
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
        f"Payment hash in the token: {hash_row}",
        f"Bound to: {bound_row}",
        b["note"],
    ]
    if b["unrecognized_caveats"]:
        rows.append("Unrecognized caveats: " + ", ".join(b["unrecognized_caveats"]))
    rows += [f"{f['code']}: {f['message']}" for f in report["findings"] if f["section"] == "binding"]
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
        f"Preimage check: {p['preimage_check']}"
        + ("" if not p["hash_sources"]
           else " (" + "; ".join(f"{s['source']}: {_yes(s['match'])}" for s in p["hash_sources"]) + ")"),
        f"Authorized retry status: {p['status']}" + (" (inferred from success)" if p["status_inferred"] else ""),
        f"Content type: {p['content_type'] or 'unknown'}; body length: {p['body_length']}",
    ]
    rows += [f"{c['name']}: {'pass' if c['pass'] else 'fail'} ({c['detail']})" for c in p["expectations"]]
    rows += [f"{f['code']}: {f['message']}" for f in report["findings"] if f["section"] == "paid"]
    return _bullets(rows)


def _marketplace(report: dict) -> list[str]:
    m = report["marketplace"]
    rows = [f"{c['name']}: {'pass' if c['pass'] else 'fail'}. {c['detail']}" for c in m["checks"]]
    rows += [f"Not checked by the script: {item}" for item in m["not_checked_by_script"]]
    rows += [f"{f['code']}: {f['message']}" for f in report["findings"] if f["section"] == "marketplace"]
    rows.append(m["note"])
    return _bullets(rows)
