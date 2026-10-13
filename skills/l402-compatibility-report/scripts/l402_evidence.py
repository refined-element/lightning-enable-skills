"""Validate the recorded evidence of one paid check (Mode B).

The agent makes the paid call with the Lightning Enable MCP tool
access_l402_resource, once, with max_sats set to the approved cap. It reads
the wallet's receipt with receipts(source="durable"), then writes an evidence
file (no credential in it) and passes the credential, when the MCP surfaced
one, on stdin. This module checks that SHA-256(preimage) equals every payment
hash it can compare (the one inside a Lightning Labs macaroon identifier and
the receipt's), that the authorized retry returned a 2xx meeting the stated
expectations, and that exactly one payment was recorded at or under the cap.
The macaroon identifier's hash, when the token is readable, ties the preimage
to the server's own challenge; for an opaque token the receipt's hash is the
only comparison, and it ties the token to the wallet's recorded payment, not
to the invoice. The report names the source it used (``hash_source``).
A receipt without the credential is supporting evidence only and never
upgrades the classification. Nothing here pays, and no output suggests
paying again.
"""
from __future__ import annotations

import copy
import hashlib
import re

import l402_macaroon
from l402_levels import (
    CHALLENGE_COMPATIBLE,
    CLASSIFICATIONS,
    FULFILLMENT_VERIFIED,
    INCOMPATIBLE,
    INCONCLUSIVE,
    MARKETPLACE_PROFILES,
    PAYMENT_COMPATIBLE,
    REPORT_VERSION,
    TRANSIENT_STATUSES,
    Finding,
    profile_note,
    profile_status,
)

# Key names refused anywhere in the evidence file, compared case-insensitively
# with underscores and hyphens removed (l402_token, l402-token, and L402TOKEN
# all match l402token).
FORBIDDEN_KEYS = frozenset({"preimage", "l402token", "macaroon", "credential", "authorization", "token"})
TERMINAL_PAYMENT_STATUSES = frozenset({"settled", "succeeded", "paid", "complete", "completed"})
# Answers that say "not now" or "no answer in time" (including a gateway that
# could not reach the server): the retry outcome is ambiguous.
AMBIGUOUS_RETRY_STATUSES = frozenset(TRANSIENT_STATUSES) | {502, 503, 504}
HEX64 = re.compile(r"[0-9a-f]{64}")  # always used with fullmatch
METHOD = re.compile(r"[A-Za-z]{1,16}")  # always used with fullmatch
# Credential forms shorter than this are not added to the scrub list, so a tiny
# bad credential can't turn into a one-character scrub of the whole report.
MIN_SECRET_LENGTH = 8
MODE_A_KEYS = ("checked_at", "target", "transport", "challenge", "invoice", "binding",
               "marketplace_profiles", "findings", "evidence")
NOT_CHECKED_BY_PAID_CHECK = "a synchronous, bounded response"
# The required checks every read-only report's profile carries, by profile. A
# read-only report missing one, or carrying one as advisory, is refused, so an
# emptied or edited checks list can never reach READY.
READ_ONLY_REQUIRED_CHECKS = {
    "amazap": ("public_https", "priced_invoice", "mainnet_invoice", "probe_without_body",
               "within_probe_window", "stable_path"),
}
# Advisory checks a read-only profile may also carry.
READ_ONLY_ADVISORY_CHECKS = {"amazap": ("host_root_metadata",)}
# Where the paid section's facts come from, so no downstream gate reads them as independently observed.
EVIDENCE_SOURCE = "agent-recorded access_l402_resource result"

# Server fixes for paid-check codes that l402_levels.FIXES does not hold.
PAID_FIXES = {
    "paid_retry_failed": (
        "Fix the paid path's error, keep the payment hash, and add claim or status recovery "
        "so a paid request that failed can still be fulfilled; never blindly repay."
    ),
}
# Guidance for the person running the check. Not server fixes: listed under "rerun".
PAID_RERUN_NOTES = {
    "preimage_unchecked": (
        "If the MCP returned payment.l402Token, validate the same evidence again with the whole token, "
        "<macaroon>:<preimage>, piped through --credential-stdin. That reuses the one payment; it does not pay again."
    ),
    "result_unreported": (
        "Copy status_code, content_type, and body_length from the access_l402_resource result into evidence.json "
        "and validate again. That reuses the one payment; it does not pay again."
    ),
    "paid_amount_mismatch": (
        "Check that the receipts in evidence.json are the ones written for this call and that paid_sats matches "
        "the tool result, then validate again. That reuses the one payment; it does not pay again."
    ),
    "no_hash_to_compare": (
        "Add the receipt's paymentHash from receipts(source=\"durable\") to evidence.json and validate "
        "again. That reuses the one payment; it does not pay again."
    ),
    "receipt_mismatch": (
        "Check that the receipt in evidence.json is the one written for this call, correct it from "
        "receipts(source=\"durable\"), and validate again. That reuses the one payment; it does not pay again."
    ),
    "awaiting_confirmation": (
        "Nothing was paid yet. Ask the human for the confirmation code and repeat the same "
        "access_l402_resource call once with confirmation_nonce set to it."
    ),
}


# check_preimage results that leave the preimage unchecked, with the reason the report gives.
UNCHECKED_REASONS = {
    "not_available": "no credential was piped",
    "no_macaroon": ("the piped credential is a bare preimage with no macaroon; pipe the whole L402 token, "
                    "<macaroon>:<preimage>"),
    "missing_preimage": "the piped credential has a macaroon but its preimage is missing",
    "malformed": "the piped preimage is not 64 hex characters",
}


class EvidenceError(ValueError):
    """The evidence file is unusable. The message never echoes a value."""


def _reject_embedded_credentials(node, path: str = "evidence") -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            if isinstance(key, str) and key.replace("_", "").replace("-", "").lower() in FORBIDDEN_KEYS:
                raise EvidenceError(
                    f"{path}.{key} looks like a credential. Keep credentials out of the evidence file; "
                    "pass the L402 token on stdin with --credential-stdin."
                )
            _reject_embedded_credentials(value, f"{path}.{key}")
    elif isinstance(node, list):
        for i, value in enumerate(node):
            _reject_embedded_credentials(value, f"{path}[{i}]")


def split_credential(credential: str | None) -> tuple[str | None, str | None]:
    """(macaroon, preimage) from 'L402 <macaroon>:<preimage>' or '<macaroon>:<preimage>'.

    Values keep their original case. Text with no colon has no macaroon and is
    returned as (None, text): check_preimage refuses that as a bare preimage.
    """
    if not credential:
        return None, None
    text = credential.strip()
    text = re.sub(r"^(?:authorization:\s*)?(?:l402|lsat)\s+", "", text, flags=re.IGNORECASE)
    if ":" in text:
        macaroon, _, preimage = text.rpartition(":")
        return macaroon.strip() or None, preimage.strip() or None
    return None, text or None


def credential_secrets(credential: str | None) -> set[str]:
    """Every form of the credential that must stay out of output: pass it to l402_report.

    Split before any case change, so the original-case macaroon and preimage
    are included, plus both case forms of the preimage and the joined
    macaroon:preimage. A credential with no colon adds its bare text after
    any L402 or LSAT prefix, most likely a macaroon. Preimage forms are added
    only for exactly 64 hex characters, and no form shorter than
    MIN_SECRET_LENGTH is added.
    """
    if not credential:
        return set()
    macaroon, preimage = split_credential(credential)
    found = {credential, credential.strip(), macaroon}
    if macaroon and preimage:
        found.add(f"{macaroon}:{preimage}")
    elif macaroon is None and preimage:
        found.add(preimage)  # no colon: the bare text, whatever it is
    if preimage and HEX64.fullmatch(preimage.lower()):
        found.update({preimage, preimage.lower(), preimage.upper()})
    return {s for s in found if s and len(s) >= MIN_SECRET_LENGTH}


def check_preimage(credential: str | None, payments: list[dict]) -> tuple[str, list[dict]]:
    """Return (result, sources).

    result: matched, mismatch, malformed, not_available (nothing piped),
    no_macaroon (a bare preimage, refused: the credential must be
    <macaroon>:<preimage>), missing_preimage (a macaroon with nothing after
    the colon), or no_hash_source.

    A source is a payment hash the preimage can be compared with: the one in a
    Lightning Labs macaroon identifier, and the receipt's when exactly one
    receipt was recorded. The macaroon hash, when there is one, governs the
    result (it is the server's own challenge); the receipt decides only when
    there is no macaroon hash. ``sources`` holds hashes only, never the
    credential, and records every comparison so a receipt that disagrees with
    a matching macaroon still shows.
    """
    if not credential or not credential.strip():
        return "not_available", []
    macaroon, preimage = split_credential(credential)
    if macaroon is None:
        return "no_macaroon", []
    if preimage is None:
        return "missing_preimage", []
    preimage = preimage.lower()
    if not HEX64.fullmatch(preimage):
        return "malformed", []
    digest = hashlib.sha256(bytes.fromhex(preimage)).hexdigest()
    sources = []
    from_macaroon = l402_macaroon.inspect(macaroon).payment_hash if macaroon else None
    if from_macaroon:
        sources.append({"source": "macaroon identifier", "payment_hash": from_macaroon, "match": from_macaroon == digest})
    if len(payments) == 1 and payments[0].get("payment_hash"):
        recorded = str(payments[0]["payment_hash"]).lower()
        sources.append({"source": "wallet receipt", "payment_hash": recorded, "match": recorded == digest})
    if not sources:
        return "no_hash_source", []
    return ("matched" if sources[0]["match"] else "mismatch"), sources


def _is_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _optional(container: dict, key: str, path: str, check, wanted: str) -> None:
    if key in container and container[key] is not None and not check(container[key]):
        raise EvidenceError(f"{path}.{key} must be {wanted}")


def _is_check(check) -> bool:
    """A check object as the read-only check writes it. ``pass`` is True, False, or None (not judged)."""
    return (isinstance(check, dict)
            and isinstance(check.get("name"), str)
            and "pass" in check and (check["pass"] is None or isinstance(check["pass"], bool))
            and isinstance(check.get("required"), bool)
            and isinstance(check.get("detail"), str))


def _require_read_only_checks(checks, profile: str, where: str) -> None:
    """Refuse a profile's read-only checks unless they are exactly what the read-only check writes.

    Every check has a string name, a pass of true, false, or null, a boolean
    required, and a string detail. Every required read-only check is present,
    once, and still required; no other name appears (a paid-check name in a
    read-only report is refused too). Fixed text: no value is echoed.
    """
    again = "; produce the read-only report again with --json"
    if not isinstance(checks, list) or not all(_is_check(c) for c in checks):
        raise EvidenceError(f"{where} must be a list of check objects, each with a string name, a pass of "
                            f"true, false, or null, a boolean required, and a string detail{again}")
    required = READ_ONLY_REQUIRED_CHECKS[profile]
    known = set(required) | set(READ_ONLY_ADVISORY_CHECKS.get(profile, ()))
    names = [c["name"] for c in checks]
    if len(names) != len(set(names)) or not set(names) <= known:
        raise EvidenceError(f"{where} holds a repeated check or one the read-only check does not write{again}")
    by_name = {c["name"]: c for c in checks}
    if any(name not in by_name or by_name[name]["required"] is not True for name in required):
        raise EvidenceError(f"{where} must hold every required read-only check as required ("
                            + ", ".join(required) + f"){again}")


def _require_mode_a_shapes(mode_a: dict) -> None:
    """Refuse a read-only report whose fields this module or the renderer read with the wrong type."""
    path = "evidence.mode_a_report"
    for key in ("target", "transport", "challenge", "marketplace_profiles", "evidence"):
        if not isinstance(mode_a[key], dict):
            raise EvidenceError(f"{path}.{key} must be an object")
    for key in ("invoice", "binding"):
        if mode_a[key] is not None and not isinstance(mode_a[key], dict):
            raise EvidenceError(f"{path}.{key} must be an object or null")
    for key in ("findings", "security", "required_fixes", "rerun"):
        if key in mode_a and not isinstance(mode_a[key], list):
            raise EvidenceError(f"{path}.{key} must be a list")
    if not all(isinstance(f, dict) for f in mode_a["findings"]) or not all(
            isinstance(f, dict) for f in mode_a.get("security", [])):
        raise EvidenceError(f"{path}.findings and security must hold finding objects")
    if not all(isinstance(mode_a["target"].get(k), str) for k in ("url", "method")):
        raise EvidenceError(f"{path}.target.url and target.method must be strings")
    profiles = mode_a["marketplace_profiles"]
    where = f"{path}.marketplace_profiles"
    if set(profiles) != set(MARKETPLACE_PROFILES):
        raise EvidenceError(f"{where} must hold exactly the profiles this script writes ("
                            + ", ".join(MARKETPLACE_PROFILES) + "); produce the read-only report again with --json")
    for name, profile in profiles.items():
        if not isinstance(profile, dict):
            raise EvidenceError(f"{where}.{name} must be an object")
        # Absent (an earlier version 2 report), true (--profile given), or false.
        if not isinstance(profile.get("requested", True), bool):
            raise EvidenceError(f"{where}.{name}.requested must be true or false")
        _require_read_only_checks(profile.get("checks"), name, f"{where}.{name}.checks")
        if not isinstance(profile.get("not_checked_by_script", []), list):
            raise EvidenceError(f"{where}.{name}.not_checked_by_script must be a list")
    if not isinstance(mode_a["evidence"].get("statuses", []), list):
        raise EvidenceError(f"{path}.evidence.statuses must be a list")


def _require(evidence: dict) -> tuple[dict, int, dict, list, dict]:
    if not isinstance(evidence, dict):
        raise EvidenceError("the evidence must be a JSON object")
    # First, before any other field is read.
    _reject_embedded_credentials(evidence)
    mode_a = evidence.get("mode_a_report")
    if isinstance(mode_a, dict) and mode_a.get("mode") == "read-only" and mode_a.get("report_version") != REPORT_VERSION:
        raise EvidenceError(f"evidence.mode_a_report is not a report_version {REPORT_VERSION} read-only report; "
                            "produce it again with this l402_check.py and --json")
    if (not isinstance(mode_a, dict) or mode_a.get("mode") != "read-only"
            or mode_a.get("classification") not in CLASSIFICATIONS
            or any(key not in mode_a for key in MODE_A_KEYS)):
        raise EvidenceError("evidence.mode_a_report must be the read-only report produced with --json")
    _require_mode_a_shapes(mode_a)
    cap = evidence.get("cap_sats")
    if not _is_int(cap) or cap <= 0:
        raise EvidenceError("evidence.cap_sats must be the approved max_sats, a positive integer")
    _optional(evidence, "recorded_at", "evidence", lambda v: isinstance(v, str),
              "a string: when the evidence was recorded, in UTC ISO 8601")
    _optional(evidence, "method", "evidence", lambda v: isinstance(v, str) and bool(METHOD.fullmatch(v)),
              "the HTTP method the paid call used, such as GET or HEAD")
    checked = str(mode_a["target"]["method"]).upper()
    if evidence.get("method") is not None and evidence["method"].upper() != checked:
        # The HEAD rule and every expectation are judged by the read-only check's method.
        raise EvidenceError(
            "evidence.method differs from the read-only check's method; the paid call must repeat the "
            "checked request with the same method and non-secret headers")
    tool = evidence.get("tool_result")
    if not isinstance(tool, dict):
        raise EvidenceError("evidence.tool_result must record the access_l402_resource result fields")
    if not isinstance(tool.get("success"), bool):
        raise EvidenceError("evidence.tool_result.success must be true or false")
    path = "evidence.tool_result"
    _optional(tool, "status_code", path, lambda v: _is_int(v) and 100 <= v <= 599, "an HTTP status code")
    _optional(tool, "content_type", path, lambda v: isinstance(v, str), "a string")
    _optional(tool, "body_length", path, lambda v: _is_int(v) and v >= 0, "a non-negative integer")
    _optional(tool, "paid_sats", path, lambda v: _is_int(v) and v >= 0, "a non-negative integer")
    for flag in ("already_paid", "requires_confirmation"):
        _optional(tool, flag, path, lambda v: isinstance(v, bool), "true or false")
    payments = evidence.get("payments", [])
    if not isinstance(payments, list) or not all(isinstance(p, dict) for p in payments):
        raise EvidenceError("evidence.payments must be a list of receipt objects")
    for i, payment in enumerate(payments):
        path = f"evidence.payments[{i}]"
        if not _is_int(payment.get("amount_sats")) or payment["amount_sats"] < 0:
            raise EvidenceError(f"{path}.amount_sats must be a non-negative integer")
        if not isinstance(payment.get("status"), str):
            raise EvidenceError(f"{path}.status must be the receipt's status string")
        _optional(payment, "payment_hash", path, lambda v: isinstance(v, str) and bool(HEX64.fullmatch(v.lower())),
                  "the receipt's paymentHash, 64 hex characters")
        for text_field in ("context", "timestamp"):
            _optional(payment, text_field, path, lambda v: isinstance(v, str), "a string")
    expected = evidence.get("expected")
    if expected is None:
        expected = {}
    if not isinstance(expected, dict):
        raise EvidenceError("evidence.expected must be an object")
    _optional(expected, "status", "evidence.expected", lambda v: _is_int(v) and 100 <= v <= 599, "an HTTP status code")
    _optional(expected, "content_type", "evidence.expected", lambda v: isinstance(v, str), "a string")
    return mode_a, cap, tool, payments, expected


def evaluate(evidence: dict, credential: str | None = None) -> dict:
    """Build the paid-mode report from the read-only report plus the recorded evidence.

    ``credential`` is what the agent piped on stdin (``L402 <macaroon>:<preimage>``
    or ``<macaroon>:<preimage>``), or None. A bare preimage is refused: the run
    is then INCONCLUSIVE with preimage_unchecked. The returned report holds payment hashes and
    amounts, never the credential, its macaroon, or its preimage.
    """
    mode_a, cap, tool, payments, expected = _require(evidence)
    report = copy.deepcopy(mode_a)
    report["mode"] = "paid"
    findings: list[Finding] = []
    paid_sats = int(tool.get("paid_sats") or 0)
    receipt_sats = sum(p["amount_sats"] for p in payments) if payments else None
    # The larger of the tool's figure and the receipts' sum is what gets held to the cap.
    total_paid = max(paid_sats, receipt_sats or 0)
    # Never inferred: with no reported status the retry outcome is ambiguous.
    status = tool.get("status_code")
    preimage_result, sources = check_preimage(credential, payments)
    # The paid call repeats the checked request (same method and non-secret headers), and
    # _require refuses evidence that names another method, so the HEAD rule follows this one.
    method = str((mode_a.get("target") or {}).get("method") or "GET").upper()
    expectations = _expectations(tool, expected, status, method)
    quoted = (mode_a.get("invoice") or {}).get("amount_sats")
    quote_hash = (mode_a.get("invoice") or {}).get("payment_hash")
    payment_hashes = [str(p["payment_hash"]).lower() for p in payments if p.get("payment_hash")]
    paid_hash = sources[0]["payment_hash"] if sources else (payment_hashes[0] if len(payment_hashes) == 1 else None)

    profiles = copy.deepcopy(report.get("marketplace_profiles") or {})
    amazap = profiles.get("amazap")
    if amazap is not None:
        amazap["checks"] = list(amazap.get("checks", [])) + _paid_profile_checks(quoted, total_paid, status)
        amazap["not_checked_by_script"] = [
            item for item in amazap.get("not_checked_by_script", []) if item != NOT_CHECKED_BY_PAID_CHECK]

    classification = _classify(mode_a, cap, tool, payments, paid_sats, receipt_sats, total_paid, status,
                               preimage_result, sources, expectations, findings)
    receipt_times = sorted(p["timestamp"] for p in payments if p.get("timestamp"))
    report["paid_fulfillment"] = {
        "tested": True,
        # Mode B validates what the agent recorded; the script never observed the paid call itself.
        "evidence_source": EVIDENCE_SOURCE,
        # The latest receipt timestamp, else the evidence file's recorded_at, else unknown.
        "paid_checked_at": receipt_times[-1] if receipt_times else evidence.get("recorded_at"),
        "tool": "access_l402_resource",
        "cap_sats": cap,
        "paid_sats": total_paid,
        "payments_recorded": len(payments),
        "payment_hashes": payment_hashes,
        "receipts": [
            {
                "payment_hash": str(p["payment_hash"]).lower() if p.get("payment_hash") else None,
                "amount_sats": p["amount_sats"],
                "status": p["status"],
                "context": p.get("context"),
                "timestamp": p.get("timestamp"),
            }
            for p in payments
        ],
        "preimage_check": preimage_result,
        # The hash that decided the preimage check: "macaroon identifier" (the server's own
        # challenge) or "wallet receipt" (opaque token: ties the token to the wallet's
        # recorded payment, not to the invoice). None when nothing was compared.
        "hash_source": sources[0]["source"] if sources else None,
        "hash_sources": sources,
        "tool_paid_sats": tool.get("paid_sats"),
        "receipt_sats": receipt_sats,
        "status": status,
        "content_type": tool.get("content_type"),
        "body_length": tool.get("body_length"),
        "expectations": expectations,
        # Information only: a server may mint a fresh invoice for each 402.
        "quote_payment_hash": quote_hash,
        "quote_hash_matches": (paid_hash == quote_hash) if paid_hash and quote_hash else None,
    }
    report["replay"] = {
        "tested": False,
        "note": "Not tested: access_l402_resource makes one paid call and does not replay the credential. "
                "Token binding from the read-only check is under Authorization and binding.",
    }
    report["findings"] = list(report.get("findings", [])) + [_finding_dict(f) for f in findings]
    report["security"] = list(report.get("security", [])) + [
        {"code": f.code, "severity": f.severity, "section": f.section, "message": f.message}
        for f in findings if f.section == "security"
    ]
    report["required_fixes"] = list(dict.fromkeys(
        list(report.get("required_fixes", [])) + [_fix(f) for f in findings if _fix(f) and f.severity == "error"]
    ))
    report["rerun"] = list(dict.fromkeys(
        list(report.get("rerun", [])) + [PAID_RERUN_NOTES[f.code] for f in findings if f.code in PAID_RERUN_NOTES]
    ))
    report["classification"] = classification
    report["summary"] = _summary(classification, total_paid, status, bool(payments) or paid_sats > 0,
                                 sources[0]["source"] if sources else None)
    for profile in profiles.values():
        profile["status"] = profile_status(classification, profile.get("checks", []))
        profile["note"] = profile_note(profile["status"])
    report["marketplace_profiles"] = profiles
    evidence_section = dict(report.get("evidence") or {})
    evidence_section.update({
        "statuses": list(evidence_section.get("statuses", [])) + ([status] if status is not None else []),
        "amount_sats": total_paid or evidence_section.get("amount_sats"),
        "payment_hash": paid_hash,
        "quote_payment_hash": quote_hash,
        "classification": classification,
    })
    if len(payment_hashes) > 1:
        evidence_section["payment_hashes"] = payment_hashes
    paid_at = [p["timestamp"] for p in payments if p.get("timestamp")]
    if paid_at:
        evidence_section["paid_at"] = paid_at
    report["evidence"] = evidence_section
    return report


def _fix(f: Finding) -> str | None:
    return f.fix or PAID_FIXES.get(f.code)


def _finding_dict(f: Finding) -> dict:
    return {"code": f.code, "severity": f.severity, "section": f.section, "message": f.message, "fix": _fix(f)}


def _expectations(tool: dict, expected: dict, status, method: str) -> list[dict]:
    """Each check passes (True), fails (False), or can't be judged because the evidence omits the field (None)."""
    checks = []
    if method != "HEAD":
        length = tool.get("body_length")
        checks.append({"name": "non_empty_body", "pass": None if length is None else length > 0,
                       "detail": "body_length not reported" if length is None else f"body_length={length}"})
    if expected.get("status") is not None:
        checks.append({"name": "expected_status",
                       "pass": None if status is None else status == expected["status"],
                       "detail": f"expected {expected['status']}, "
                                 + ("status not reported" if status is None else f"got {status}")})
    if expected.get("content_type") is not None:
        want = str(expected["content_type"]).split(";", 1)[0].strip().lower()
        reported = tool.get("content_type")
        if reported is None:
            checks.append({"name": "expected_content_type", "pass": None,
                           "detail": f"expected {want}, content_type not reported"})
        else:
            got = reported.split(";", 1)[0].strip().lower()
            checks.append({"name": "expected_content_type", "pass": got == want,
                           "detail": f"expected {want}, got {got or 'none'}"})
    return checks


def _paid_profile_checks(quoted, total_paid: int, status) -> list[dict]:
    """The checks the paid check adds to the Amazap profile. A status is never inferred.

    Both are required: Amazap pays a live invoice only when it fits the price it
    stored at listing time, so a price that moves between quote and payment
    breaks buys. With nothing paid, or no quote, the price can't be compared.
    """
    if status is None:
        synchronous, detail = None, "The paid call's status was not reported."
    elif status in AMBIGUOUS_RETRY_STATUSES:
        synchronous, detail = None, f"The paid call returned {status}: no definitive answer."
    elif status == 202:
        synchronous, detail = False, "The paid call returned 202 Accepted: the resource was deferred, not delivered."
    elif 200 <= status < 300:
        synchronous, detail = True, f"The paid call returned {status} within access_l402_resource's bounded call."
    else:
        synchronous, detail = False, f"The paid call returned {status}, not a 2xx."
    stable = None if quoted is None or total_paid == 0 else quoted == total_paid
    return [
        {"name": "stable_price", "pass": stable, "required": True,
         "detail": f"Quoted {quoted} sats in the read-only check; paid {total_paid} sats. Amazap pays a live "
                   "invoice only when it fits the price it stored at listing time."},
        {"name": "synchronous_response", "pass": synchronous, "required": True, "detail": detail},
    ]


def _payment_blockers(cap, tool, payments, paid_sats, receipt_sats, total_paid, findings) -> bool:
    """Findings that cap the result at INCONCLUSIVE. True when any was added."""
    blocked = False
    if total_paid > cap:
        findings.append(Finding("paid_over_cap", "error", "security", f"{total_paid} sats paid against a {cap}-sat cap."))
        blocked = True
    if receipt_sats is not None and tool.get("paid_sats") is not None and tool["paid_sats"] != receipt_sats:
        findings.append(Finding("paid_amount_mismatch", "warning", "paid",
                                f"The tool reported {tool['paid_sats']} sats paid, but the receipts add up to "
                                f"{receipt_sats} sats. Reconcile them from the wallet receipts; do not pay again."))
        blocked = True
    if len(payments) > 1:
        findings.append(Finding("multiple_payments", "error", "security",
                                f"{len(payments)} payments were recorded for one check. Do not pay again; "
                                "reconcile them from the wallet receipts."))
        blocked = True
    if payments:
        unsettled = sorted({p["status"] for p in payments if p["status"].lower() not in TERMINAL_PAYMENT_STATUSES})
    else:
        reported = paid_sats > 0 and (tool.get("success") is True or tool.get("already_paid") is True)
        unsettled = [] if reported else ["unknown"]
    if unsettled:
        findings.append(Finding("payment_pending", "warning", "paid",
                                f"The wallet does not report terminal success for the payment (status {', '.join(unsettled)}). "
                                "Keep the payment hash and amount; never start a replacement payment while one is "
                                "pending or ambiguous."))
        blocked = True
    return blocked


def _classify(mode_a, cap, tool, payments, paid_sats, receipt_sats, total_paid, status, preimage_result, sources,
              expectations, findings) -> str:
    if mode_a.get("classification") != CHALLENGE_COMPATIBLE:
        findings.append(Finding("paid_check_without_challenge", "error", "paid",
                                f"The read-only check was {mode_a.get('classification')}; the paid check should not "
                                "have run. Do not pay again."))
        return INCONCLUSIVE
    if not payments and not paid_sats:
        if tool.get("requires_confirmation"):
            findings.append(Finding("awaiting_confirmation", "info", "paid",
                                    "No payment was made: the call waits for the human's confirmation code."))
        else:
            findings.append(Finding("no_payment", "warning", "paid",
                                    "No payment was recorded, so there is nothing to evaluate. If the call's outcome "
                                    "is unknown, check the wallet receipts; do not pay again."))
        return INCONCLUSIVE
    if _payment_blockers(cap, tool, payments, paid_sats, receipt_sats, total_paid, findings):
        return INCONCLUSIVE
    retry = f"status {status}" if status is not None else "no status"
    # The payment is confirmed only when SHA-256 of the piped preimage equals a comparable hash.
    # The macaroon hash governs when there is one; the receipt decides only without it.
    from_macaroon = bool(sources) and sources[0]["source"] == "macaroon identifier"
    receipt_disagrees = any(s["source"] == "wallet receipt" and not s["match"] for s in sources)
    if preimage_result == "mismatch" and from_macaroon:
        findings.append(Finding("preimage_mismatch", "error", "paid",
                                "SHA-256 of the preimage does not equal the payment hash in the macaroon identifier. "
                                "The server's own challenge disagrees with the paid preimage. Do not pay again."))
        return INCOMPATIBLE
    if preimage_result == "mismatch":
        findings.append(Finding("receipt_mismatch", "warning", "paid",
                                "SHA-256 of the preimage does not equal the receipt's paymentHash, and the macaroon "
                                "carries no payment hash to compare. The receipt is likely paired with a different "
                                f"payment, so the payment is not confirmed. The authorized retry got {retry}. "
                                "Do not pay again."))
        return INCONCLUSIVE
    if from_macaroon and receipt_disagrees:
        findings.append(Finding("receipt_mismatch", "info", "paid",
                                "The macaroon's payment hash matches the preimage, but the receipt's paymentHash does "
                                "not, so the receipt is likely from a different payment. The macaroon match governs."))
    if preimage_result == "no_hash_source":
        findings.append(Finding("no_hash_to_compare", "warning", "paid",
                                f"The credential was piped, but there is no payment hash to compare it with: the macaroon "
                                f"is not in Lightning Labs format and the receipt gave no paymentHash. The authorized "
                                f"retry got {retry}. Do not pay again."))
        return INCONCLUSIVE
    if preimage_result in UNCHECKED_REASONS:
        why = UNCHECKED_REASONS[preimage_result]
        findings.append(Finding("preimage_unchecked", "warning", "paid",
                                f"The preimage went unchecked: {why}. The payment is not confirmed. The authorized "
                                f"retry got {retry}. A receipt is supporting evidence only. Do not pay again."))
        return INCONCLUSIVE
    # Payment confirmed. Classify the authorized retry; a status is never inferred.
    if status is None:
        findings.append(Finding("ambiguous_fulfillment", "warning", "paid",
                                "Paid, but the evidence reports no status for the authorized retry, so its outcome "
                                "is ambiguous. The payment hash is retained; do not pay again."))
        return INCONCLUSIVE
    if status in AMBIGUOUS_RETRY_STATUSES:
        findings.append(Finding("ambiguous_fulfillment", "warning", "paid",
                                f"Paid, then the authorized retry gave no definitive answer ({retry}). "
                                "The payment hash is retained; do not pay again."))
        return INCONCLUSIVE
    if 200 <= status < 300 and (tool.get("success") is False or tool.get("already_paid")):
        findings.append(Finding("ambiguous_fulfillment", "warning", "paid",
                                f"The authorized retry reported {status}, but the tool reported the call as failed. "
                                "The payment hash is retained; do not pay again."))
        return INCONCLUSIVE
    if status == 402:
        findings.append(Finding("paid_retry_402", "error", "paid",
                                "The payment is confirmed, and the authorized retry got another 402. Do not pay again."))
        return PAYMENT_COMPATIBLE
    if 400 <= status < 500:
        findings.append(Finding("paid_retry_rejected", "error", "paid",
                                f"The payment is confirmed, and the authorized retry got {status}. Do not pay again."))
        return PAYMENT_COMPATIBLE
    if not 200 <= status < 300:
        findings.append(Finding("paid_retry_failed", "error", "paid",
                                f"The payment is confirmed, and the authorized retry got {status}. Do not pay again."))
        return PAYMENT_COMPATIBLE
    failed = [c["name"] for c in expectations if c["pass"] is False]
    if failed:
        findings.append(Finding("unexpected_result", "warning", "paid",
                                "The paid result did not meet: " + ", ".join(failed) + "."))
        return PAYMENT_COMPATIBLE
    unreported = [c["name"] for c in expectations if c["pass"] is None]
    if unreported:
        findings.append(Finding("result_unreported", "warning", "paid",
                                f"The authorized retry returned {status}, but the evidence omits what these checks "
                                "need: " + ", ".join(unreported) + ". The payment hash is retained; do not pay again."))
        return INCONCLUSIVE
    return FULFILLMENT_VERIFIED


MATCHED_BY = {
    "macaroon identifier": "SHA-256 of the preimage matched the payment hash in the macaroon identifier",
    "wallet receipt": (
        "SHA-256 of the preimage matched the wallet receipt's payment hash (the token is opaque, so this ties "
        "the token to the wallet's recorded payment, not to the invoice)"
    ),
}


def _summary(classification: str, paid: int, status, payment_recorded: bool, hash_source: str | None = None) -> str:
    matched = MATCHED_BY.get(hash_source, "SHA-256 of the preimage matched the payment hash")
    if classification == FULFILLMENT_VERIFIED:
        return (f"Paid {paid} sats; {matched}; the authorized retry returned {status}, meeting the stated "
                "expectations.")
    if classification == PAYMENT_COMPATIBLE:
        return (f"Paid {paid} sats and {matched}, but the authorized retry ({status}) was not a 2xx "
                "meeting the stated expectations. Keep the payment hash; do not pay again.")
    if classification == INCOMPATIBLE:
        return "A protocol defect showed up in the paid flow. See Required fixes. Do not pay again."
    if not payment_recorded:
        return "No payment was recorded, so the paid check has nothing to evaluate. See Paid fulfillment."
    return "The paid check could not reach a conclusion. Keep the payment hash and amount; do not pay again."
