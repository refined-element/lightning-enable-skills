"""Behavioral tests for the read-only check (Mode A) of l402-compatibility-report.

Every test runs offline against tests/fixtures/l402-challenges: captured 402
responses with placeholder macaroons, plus synthetic cases. Nothing pays and
nothing opens a network connection. Numbered comments map tests to the spec's
acceptance tests (section 42); paid-mode acceptance tests live in
test_l402_evidence.py, output redaction in test_l402_report_render.py, and the
command line in test_l402_cli.py.
"""
import json

import pytest

import l402_check_support as support
import test_shared_references
from l402_analyze import CLASSIFICATIONS


def report_for(name, **kwargs):
    return support.run_fixture(support.load_fixture(name), **kwargs)


def test_script_classifications_match_the_shared_reference():
    assert CLASSIFICATIONS == test_shared_references.CLASSIFICATIONS


@pytest.mark.parametrize("name", support.fixture_names())
def test_fixture_classification_and_metadata(name):
    fixture = support.load_fixture(name)
    expected = fixture["expected"]
    report, _ = support.run_fixture(fixture)
    assert report["classification"] == expected["classification"]
    assert report["classification"] in CLASSIFICATIONS
    assert report["challenge"]["schemes"] == expected["schemes"]
    assert report["challenge"]["classified_by"] == expected["classified_by"]
    invoice = report["invoice"] or {}
    assert invoice.get("amount_sats") == expected["amount_sats"]
    assert invoice.get("payment_hash") == expected["payment_hash"]
    codes = {f["code"] for f in report["findings"]}
    assert set(expected["finding_codes"]) <= codes, codes


# 1. A valid unpaid challenge is CHALLENGE_COMPATIBLE, never FULFILLMENT_VERIFIED.
def test_valid_unpaid_challenge_is_challenge_compatible_only():
    report, _ = report_for("le-test-ping")
    assert report["classification"] == "CHALLENGE_COMPATIBLE"
    assert report["paid_fulfillment"]["tested"] is False
    assert report["mode"] == "read-only"
    assert report["marketplace"]["listing_ready"] is False


# 2 and 11. Payment is its own scheme; a multi-scheme 402 is classified by L402 and lists the rest.
@pytest.mark.parametrize(
    "name, schemes",
    [("le-proxy-weather", ["L402", "Payment"]), ("amazap-basics-feed", ["L402", "Payment"]),
     ("major-miners-lsat-plus-l402", ["LSAT", "L402"]), ("taskhawk-l402-payment-x402", ["L402", "Payment", "x402"])],
)
def test_multi_scheme_is_classified_by_l402_and_lists_the_rest(name, schemes):
    report, _ = report_for(name)
    assert report["classification"] == "CHALLENGE_COMPATIBLE"
    assert report["challenge"]["classified_by"] == "L402"
    assert report["challenge"]["schemes"] == schemes
    assert report["challenge"]["multi_scheme"] is True
    for entry in report["challenge"]["challenges"]:
        if entry["kind"] == "Payment":
            assert "token_present" not in entry
            assert "not classic L402" in entry["note"]


def test_payment_only_402_is_not_normalized_to_l402():
    report, _ = report_for("synthetic-payment-only")
    assert report["classification"] == "INCOMPATIBLE"
    assert report["challenge"]["schemes"] == ["Payment"]
    assert report["challenge"]["classified_by"] is None
    assert "no_l402_challenge" in {f["code"] for f in report["findings"]}


def test_amazap_extra_token_param_is_reported():
    report, _ = report_for("amazap-basics-feed")
    l402 = report["challenge"]["challenges"][0]
    assert l402["extra_params"] == ["token"]
    assert l402["token_present"] is True and l402["invoice_present"] is True


# 3. Amountless invoice is incompatible with marketplace readiness.
def test_amountless_invoice_fails_marketplace_readiness():
    report, _ = report_for("synthetic-amountless-invoice")
    assert report["classification"] == "INCOMPATIBLE"
    checks = {c["name"]: c["pass"] for c in report["marketplace"]["checks"]}
    assert checks["priced_invoice"] is False
    assert report["marketplace"]["listing_ready"] is False
    assert any("priced invoice" in fix for fix in report["required_fixes"])


# 5. The paid check is refused for an invoice one sat over the cap.
def test_preflight_refuses_one_sat_over_cap():
    report, _ = report_for("le-proxy-weather", max_sats=2)  # the invoice asks 3
    assert report["preflight"]["allowed"] is False
    assert "over the 2-sat cap" in report["preflight"]["reasons"][0]
    at_cap, _ = report_for("le-proxy-weather", max_sats=3)
    assert at_cap["preflight"] == {"max_sats": 3, "invoice_sats": 3, "allowed": True, "reasons": []}


def test_preflight_refuses_methods_the_paying_tool_cannot_send():
    fixture = support.load_fixture("le-test-ping")
    fixture["request"]["method"] = "POST"
    report, _ = support.run_fixture(fixture, max_sats=10)
    assert report["preflight"]["allowed"] is False
    assert "GET and HEAD" in " ".join(report["preflight"]["reasons"])


def test_no_preflight_without_a_cap():
    report, _ = report_for("le-test-ping")
    assert report["preflight"] is None


# 12. A comma-joined WWW-Authenticate header gives the same report as separate headers.
@pytest.mark.parametrize("name", ["le-proxy-weather", "taskhawk-l402-payment-x402", "parsebit-lsat-plus-l402"])
def test_comma_joined_header_gives_the_same_report(name):
    fixture = support.load_fixture(name)
    joined = json.loads(json.dumps(fixture))
    headers = joined["responses"][0]["headers"]
    values = [v for k, v in headers if k == "WWW-Authenticate"]
    joined["responses"][0]["headers"] = [["WWW-Authenticate", ", ".join(values)]] + [
        [k, v] for k, v in headers if k != "WWW-Authenticate"
    ]
    separate_report, _ = support.run_fixture(fixture)
    joined_report, _ = support.run_fixture(joined)
    for key in ("classification", "challenge", "invoice", "binding"):
        assert joined_report[key] == separate_report[key]


# 13. A 415 on an empty-body POST is not marketplace-ready, with the section 40 fix.
def test_415_on_empty_body_post():
    report, _ = report_for("store-checkout-empty-post-415")
    assert report["classification"] == "INCOMPATIBLE"
    checks = {c["name"]: c["pass"] for c in report["marketplace"]["checks"]}
    assert checks["probe_without_body"] is False
    assert report["required_fixes"] == [
        "Issue the 402 before content-type or body validation, or provide a fixed-price, "
        "single-call route for marketplace listing."
    ]
    finding = next(f for f in report["findings"] if f["code"] == "unsupported_media_before_challenge")
    assert "empty-body POST" in finding["message"]


@pytest.mark.parametrize(
    "name, fix_start",
    [("synthetic-200-unpaid", "Place the L402 middleware before resource delivery"),
     ("synthetic-401-unpaid", "Let requests reach the L402 check before ordinary authentication"),
     ("synthetic-400-before-402", "Issue the 402 before validating paid-only parameters"),
     ("synthetic-missing-header", "Emit the canonical challenge header"),
     ("synthetic-malformed-quoting", "Quote auth-param values as RFC 7235 quoted-strings"),
     ("synthetic-expired-invoice", "Increase the invoice expiry"),
     ("synthetic-redirect-private", "Serve the paid resource from a public address")],
)
def test_defects_map_to_section_40_fixes(name, fix_start):
    report, _ = report_for(name)
    assert report["classification"] == "INCOMPATIBLE"
    assert any(fix.startswith(fix_start) for fix in report["required_fixes"]), report["required_fixes"]


def test_opaque_tokens_are_not_externally_verifiable_not_absent():
    report, _ = report_for("le-test-ping")
    binding = report["binding"]
    assert binding["token_format"] == "opaque"
    assert binding["externally_verifiable"] is False
    assert "not the same as absent" in binding["note"]


def test_declared_price_is_compared_with_the_invoice():
    report, _ = report_for("amazap-basics-feed")
    assert report["invoice"]["declared_price_sats"] == 13
    assert report["invoice"]["declared_price_matches"] is True
    fixture = support.load_fixture("amazap-basics-feed")
    fixture["responses"][0]["body"] = fixture["responses"][0]["body"].replace('"priceSats":13', '"priceSats":12')
    mismatch, _ = support.run_fixture(fixture)
    assert mismatch["classification"] == "INCOMPATIBLE"
    assert "body_price_mismatch" in {f["code"] for f in mismatch["findings"]}


def test_expired_invoice_reports_zero_remaining():
    report, _ = report_for("synthetic-expired-invoice")
    assert report["invoice"]["expired"] is True
    assert report["invoice"]["remaining_seconds"] == 0


def test_host_root_metadata_is_probed_and_reported():
    fixture = support.load_fixture("le-test-ping")
    log = []
    llms = {"url": "https://api.lightningenable.com/llms.txt", "status": 200, "headers": [], "body": "# llms"}
    report, _ = support.run_fixture(fixture, extra_responses=[llms], log=log)
    assert [e["url"] for e in log] == [
        "https://api.lightningenable.com/l402/test/ping",
        "https://api.lightningenable.com/openapi.json",
        "https://api.lightningenable.com/llms.txt",
    ]
    checks = {c["name"]: c for c in report["marketplace"]["checks"]}
    assert checks["host_root_metadata"]["pass"] is True
    assert "/llms.txt" in checks["host_root_metadata"]["detail"]
    assert all(entry["method"] == "GET" and entry["body"] is None for entry in log)


def test_metadata_is_not_probed_when_there_is_no_402():
    log = []
    report_for("synthetic-200-unpaid", log=log)
    assert len(log) == 1


def test_proxy_manifest_link_is_noted_for_amazap_prefill():
    report, _ = report_for("le-proxy-weather")
    note = next(f for f in report["findings"] if f["code"] == "proxy_manifest_link")
    assert "host root" in note["message"]


def test_secret_in_unpaid_body_is_flagged_by_kind_only():
    fixture = support.load_fixture("le-test-ping")
    leaked = "nostr+walletconnect://fixture-string-wallet?relay=wss://relay.example&secret=fixture-string-nwc"
    fixture["responses"][0]["body"] = json.dumps({"debug": leaked})
    report, _ = support.run_fixture(fixture)
    finding = next(f for f in report["security"] if f["code"] == "unpaid_body_secret")
    assert finding["message"] == "The unpaid response body contains: nwc_connection_string."


def test_evidence_section_holds_only_safe_correlators():
    report, _ = report_for("le-test-ping")
    assert report["evidence"] == {
        "timestamp": "2026-10-12T20:37:45Z",
        "url": "https://api.lightningenable.com/l402/test/ping",
        "method": "GET",
        "statuses": [402],
        "amount_sats": 1,
        "payment_hash": "0f3203bd58a26bc984ca6409047213f92da6afcd3e19e394382c7d465e68d7df",
        "latency_ms": 150,
        "classification": "CHALLENGE_COMPATIBLE",
    }


# Transport outcomes, URL hygiene, and decoded-macaroon binding: the rulings
# that bind the analysis to the probe's and the macaroon reader's real behavior.

def _single_response_fixture(url, status, headers=(), body="", method="GET", dns=None):
    return {
        "observed_at": "2026-10-12T20:37:45Z",
        "dns": dns or {},
        "request": {"method": method, "url": url},
        "responses": [{"url": url, "status": status, "headers": [list(h) for h in headers], "body": body}],
    }


def _run_with_transport(url, send, *, method="GET", headers=None, body=None, allow_private=False):
    import l402_analyze
    import l402_check

    request = l402_analyze.ProbeRequest(url=url, method=method, headers=dict(headers or {}), body=body)
    return l402_check.run_mode_a(
        request, timeout=5.0, allow_private=allow_private, max_sats=None,
        now=support.observed({"observed_at": "2026-10-12T20:37:45Z"}),
        resolver=support.fake_resolver({}), transport=send,
    )


def test_a_timeout_and_a_refused_connection_are_inconclusive_and_distinct():
    def times_out(target, method, headers, body, timeout):
        raise TimeoutError("fixture-string-slow")

    def refuses(target, method, headers, body, timeout):
        raise ConnectionRefusedError("fixture-string-refused")

    slow, _ = _run_with_transport("https://api.example.com/paid", times_out)
    closed, _ = _run_with_transport("https://api.example.com/paid", refuses)
    assert slow["classification"] == closed["classification"] == "INCONCLUSIVE"
    assert slow["transport"]["error"] == "timeout"
    assert closed["transport"]["error"] == "network"
    assert "transport_timeout" in {f["code"] for f in slow["findings"]}
    assert "transport_network" in {f["code"] for f in closed["findings"]}
    assert slow["required_fixes"] == closed["required_fixes"] == []


def test_a_refused_first_target_is_inconclusive_and_its_userinfo_is_never_reported():
    url = "https://fixture-user:fixture-string-pass@api.example.com/paid?api_key=abc&url=https%3A%2F%2Fe.com"
    log = []
    report, secrets = _run_with_transport(url, support.fake_transport([], log))
    assert log == []
    assert report["classification"] == "INCONCLUSIVE"
    assert "refused_target" in {f["code"] for f in report["findings"]}
    assert report["target"]["url"] == "https://api.example.com/paid?api_key=REDACTED&url=https%3A%2F%2Fe.com"
    assert "fixture-string-pass" not in json.dumps(report)
    assert "fixture-string-pass" in secrets
    assert "pass a header" not in report["findings"][0]["message"]


def test_query_credentials_are_redacted_in_the_target_every_hop_and_the_final_url():
    ping = support.load_fixture("le-test-ping")["responses"][0]
    first = "https://api.example.com/paid?api_key=fixture-string-k1&q=1"
    final = "https://api.example.com/next?access%5Ftoken=fixture-string%2Bk2&sig=ab&q=2"
    log = []
    send = support.fake_transport([
        {"url": first, "status": 302, "headers": [["Location", final]]},
        {"url": final, "status": 402, "headers": ping["headers"], "body": ping["body"]},
    ], log)
    report, secrets = _run_with_transport(first, send)
    assert report["classification"] == "CHALLENGE_COMPATIBLE"
    assert report["target"]["url"] == "https://api.example.com/paid?api_key=REDACTED&q=1"
    assert report["transport"]["redirects"] == [
        {"url": "https://api.example.com/paid?api_key=REDACTED&q=1", "status": 302}]
    assert report["transport"]["final_url"] == "https://api.example.com/next?access%5Ftoken=REDACTED&sig=REDACTED&q=2"
    text = json.dumps(report)
    for value in ("fixture-string-k1", "fixture-string%2Bk2", "fixture-string+k2", "sig=ab"):
        assert value not in text
    assert {"fixture-string-k1", "fixture-string%2Bk2", "fixture-string+k2"} <= secrets


def _query_secrets(value):
    ping = support.load_fixture("le-test-ping")["responses"][0]
    url = f"https://api.example.com/paid?token={value}"
    send = support.fake_transport([{"url": url, "status": 402, "headers": ping["headers"], "body": ping["body"]}])
    report, secrets = _run_with_transport(url, send)
    assert report["target"]["url"] == "https://api.example.com/paid?token=REDACTED"
    return secrets


def test_a_query_credential_of_eight_or_more_characters_joins_the_scrub_set():
    assert "abcd1234" in _query_secrets("abcd1234")


def test_a_query_credential_under_eight_characters_is_redacted_but_not_scrubbed_globally():
    assert "abcd123" not in _query_secrets("abcd123")


def test_safe_url_redacts_by_raw_key_and_keeps_the_rest_as_given():
    from l402_analyze import safe_url

    url = "https://u:p@h.example/x?Token=a%2Fb&page=2&passwd=&flag&credential=c#frag"
    assert safe_url(url) == "https://h.example/x?Token=REDACTED&page=2&passwd=&flag&credential=REDACTED"


def test_a_query_string_is_kept_as_given():
    report, _ = report_for("toon-extract-single-l402")
    assert report["target"]["url"] == "https://l402.mainnet.toonprotocol.dev/extract?url=https%3A%2F%2Fexample.com"
    assert report["evidence"]["url"] == report["target"]["url"]


def test_a_credential_header_is_refused_before_any_request():
    import l402_http

    log = []
    with pytest.raises(l402_http.CredentialHeaderError):
        report_for("le-test-ping", headers={"Authorization": "fixture-string-auth"}, log=log)
    assert log == []


def test_a_redirect_downgrade_is_incompatible():
    fixture = _single_response_fixture(
        "https://api.example.com/paid", 302, headers=[("Location", "http://api.example.com/paid")])
    report, _ = support.run_fixture(fixture)
    assert report["classification"] == "INCOMPATIBLE"
    finding = next(f for f in report["findings"] if f["code"] == "redirect_downgrade")
    assert finding["fix"] == "Never redirect from https to http; keep the paid resource on https."
    assert report["evidence"]["statuses"] == [302]


def test_a_cross_origin_307_with_a_body_is_inconclusive_not_a_server_defect():
    fixture = _single_response_fixture(
        "https://api.example.com/paid", 307, headers=[("Location", "https://other.example.com/paid")], method="POST")
    log = []
    report, _ = support.run_fixture(fixture, body=b"{}", log=log)
    assert len(log) == 1
    assert report["classification"] == "INCONCLUSIVE"
    assert "redirect_body_not_resent" in {f["code"] for f in report["findings"]}
    assert report["evidence"]["statuses"] == [307]
    assert report["transport"]["redirects"] == [{"url": "https://api.example.com/paid", "status": 307}]


def test_a_redirect_into_a_blocked_range_records_one_status_per_response():
    report, _ = report_for("synthetic-redirect-private")
    assert report["evidence"]["statuses"] == [302]


def test_a_redirect_from_local_http_to_public_http_gets_its_own_message():
    log = []
    send = support.fake_transport([
        {"url": "http://localhost:8080/paid", "status": 302, "headers": [["Location", "http://api.example.com/paid"]]},
    ], log)
    report, _ = _run_with_transport("http://localhost:8080/paid", send, allow_private=True)
    finding = next(f for f in report["findings"] if f["code"] == "redirect_not_https")
    assert report["classification"] == "INCOMPATIBLE"
    assert "from https" not in finding["message"]
    assert "plain http" in finding["message"] and "public" in finding["message"]
    assert finding["fix"] == "Serve the resource over https; public endpoints must use https."
    assert len(log) == 1


@pytest.mark.parametrize("status, classification", [(429, "INCONCLUSIVE"), (503, "INCONCLUSIVE"), (404, "INCOMPATIBLE")])
def test_other_statuses_before_the_challenge(status, classification):
    report, _ = support.run_fixture(_single_response_fixture("https://api.example.com/paid", status))
    assert report["classification"] == classification


def test_a_405_is_inconclusive_with_a_rerun_note_not_a_server_fix():
    report, _ = support.run_fixture(_single_response_fixture(
        "https://api.example.com/paid", 405, headers=[("Allow", "POST")]))
    finding = next(f for f in report["findings"] if f["code"] == "method_not_allowed")
    assert report["classification"] == "INCONCLUSIVE"
    assert finding["fix"] is None
    assert report["required_fixes"] == []
    assert report["rerun"] == ["Rerun the check with the method the endpoint accepts."]
    assert "POST" in finding["message"]
    assert "unexpected_status" not in {f["code"] for f in report["findings"]}


def test_no_rerun_note_without_a_caller_side_cause():
    report, _ = report_for("le-test-ping")
    assert report["rerun"] == []


def _with_challenge_headers(name, transform):
    fixture = support.load_fixture(name)
    headers = fixture["responses"][0]["headers"]
    fixture["responses"][0]["headers"] = transform(headers)
    return fixture


def test_a_missing_token_is_absent_not_opaque():
    fixture = _with_challenge_headers("le-proxy-weather", lambda headers: [
        [k, v.replace('macaroon="fixture-string-macaroon", ', "")] for k, v in headers])
    report, _ = support.run_fixture(fixture)
    assert report["classification"] == "INCOMPATIBLE"
    assert "missing_token" in {f["code"] for f in report["findings"]}
    assert report["binding"]["token_format"] == "absent"
    assert "not the same as absent" not in report["binding"]["note"]


def test_a_duplicate_param_outside_the_l402_challenge_is_info_only():
    fixture = _with_challenge_headers("le-proxy-weather", lambda headers: [
        [k, v + ', realm="fixture-string-realm"' if v.startswith("Payment ") else v] for k, v in headers])
    report, _ = support.run_fixture(fixture)
    findings = {f["code"]: f for f in report["findings"]}
    assert report["classification"] == "CHALLENGE_COMPATIBLE"
    assert "duplicate_params" not in findings
    assert findings["duplicate_params_other_scheme"]["severity"] == "info"
    assert "Payment" in findings["duplicate_params_other_scheme"]["message"]


def test_a_duplicate_param_in_the_l402_challenge_is_incompatible():
    fixture = _with_challenge_headers("le-proxy-weather", lambda headers: [
        [k, v + ', macaroon="fixture-string-second"' if v.startswith("L402 ") else v] for k, v in headers])
    report, _ = support.run_fixture(fixture)
    assert report["classification"] == "INCOMPATIBLE"
    assert "duplicate_params" in {f["code"] for f in report["findings"]}


def test_two_l402_challenges_use_the_first_and_warn():
    fixture = _with_challenge_headers("le-proxy-weather", lambda headers: [
        h for h in headers if h[0] == "WWW-Authenticate" and h[1].startswith("L402 ")] * 2 + [
        h for h in headers if not (h[0] == "WWW-Authenticate" and h[1].startswith("L402 "))])
    report, _ = support.run_fixture(fixture)
    finding = next(f for f in report["findings"] if f["code"] == "multiple_l402_challenges")
    assert finding["severity"] == "warning"
    assert report["classification"] == "CHALLENGE_COMPATIBLE"
    assert report["invoice"]["amount_sats"] == 3


def test_a_malformed_challenge_is_rejected_before_its_invoice_is_decoded():
    report, _ = report_for("synthetic-malformed-quoting")
    codes = {f["code"] for f in report["findings"]}
    assert report["invoice"] is None and report["binding"] is None
    assert "missing_invoice" not in codes and "invalid_invoice" not in codes
    assert report["challenge"]["parse_errors"] and all(isinstance(e, str) for e in report["challenge"]["parse_errors"])


def _with_macaroon(name, token):
    fixture = support.load_fixture(name)
    fixture["responses"][0]["headers"] = [
        [k, v.replace('macaroon="fixture-string-macaroon"', f'macaroon="{token}"')] for k, v in fixture["responses"][0]["headers"]
    ]
    return fixture


def test_a_decoded_macaroon_bound_to_the_invoice_hash_reports_its_bindings():
    from test_l402_macaroon import build_v2, lightning_labs_identifier

    weather = support.load_fixture("le-proxy-weather")["expected"]["payment_hash"]
    token = build_v2(lightning_labs_identifier(weather), ["method=GET", "path=/forecast", "expires=1791923855"])
    report, secrets = support.run_fixture(_with_macaroon("le-proxy-weather", token))
    binding = report["binding"]
    assert report["classification"] == "CHALLENGE_COMPATIBLE"
    assert binding["token_format"] == "v2"
    assert binding["externally_verifiable"] is True
    assert binding["payment_hash_bound"] is True
    assert binding["bound_to"] == {"method": ["method"], "path": ["path"], "expiry": ["expires"]}
    assert token in secrets and token not in json.dumps(report)


def test_a_decoded_macaroon_without_binding_caveats_is_reported_as_unbound_not_opaque():
    from test_l402_macaroon import build_v2

    report, _ = support.run_fixture(_with_macaroon("le-proxy-weather", build_v2(b"fixture-string-id", [])))
    binding = report["binding"]
    assert binding["token_format"] == "v2"
    assert binding["externally_verifiable"] is True
    assert binding["bound_to"] == {}
    assert "no first-party caveats" in binding["note"]


def test_a_macaroon_carrying_a_different_payment_hash_is_incompatible():
    from test_l402_macaroon import build_v2, lightning_labs_identifier

    token = build_v2(lightning_labs_identifier("00" * 32), [])
    report, _ = support.run_fixture(_with_macaroon("le-proxy-weather", token))
    assert report["classification"] == "INCOMPATIBLE"
    assert report["binding"]["payment_hash_bound"] is False
    assert "payment_hash_unbound" in {f["code"] for f in report["findings"]}


def test_no_report_wording_claims_verification():
    for name in support.fixture_names():
        report, _ = report_for(name)
        text = json.dumps({k: v for k, v in report.items() if k not in ("classification", "evidence")}).lower()
        assert "verified" not in text, name
