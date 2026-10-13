"""Report rendering: the Markdown follows templates/report.md, and no output carries a secret."""
import json
import re

import pytest

import l402_check_support as support
import l402_report
from test_shared_references import CLASSIFICATIONS

TEMPLATE = support.SKILL_DIR / "templates" / "report.md"


def headings(markdown: str) -> list[str]:
    return re.findall(r"^#{1,2} (.+)$", markdown, flags=re.MULTILINE)


def both(report, secrets):
    return l402_report.to_json(report, secrets), l402_report.to_markdown(report, secrets)


def test_template_lists_the_spec_sections_in_order():
    assert headings(TEMPLATE.read_text(encoding="utf-8")) == ["Lightning Enable L402 Compatibility Report", *l402_report.SECTIONS]


def test_template_classification_line_names_the_five_classifications():
    line = next(row for row in TEMPLATE.read_text(encoding="utf-8").splitlines()
                if row.startswith("- Classification:"))
    assert tuple(re.findall(r"[A-Z]+(?:_[A-Z]+)+|INCOMPATIBLE|INCONCLUSIVE", line)) == CLASSIFICATIONS


def test_rendered_markdown_follows_the_template():
    report, secrets = support.run_fixture(support.load_fixture("le-proxy-weather"))
    markdown = l402_report.to_markdown(report, secrets)
    assert headings(markdown) == headings(TEMPLATE.read_text(encoding="utf-8"))
    header = markdown.split("\n## Summary", 1)[0]
    for label in ("- Target: GET https://", "- Checked at: 2026-10-12T20:37:45Z", "- Mode: read-only",
                  "- Classification: CHALLENGE_COMPATIBLE"):
        assert label in header


def test_preflight_verdict_appears_under_paid_fulfillment():
    report, secrets = support.run_fixture(support.load_fixture("le-proxy-weather"), max_sats=2)
    section = l402_report.to_markdown(report, secrets).split("## Paid fulfillment", 1)[1].split("##", 1)[0]
    assert "Not tested" in section
    assert "capped at 2 sats: not allowed: the invoice asks 3 sats, over the 2-sat cap" in section


@pytest.mark.parametrize("name", support.fixture_names())
def test_json_is_valid_and_round_trips(name):
    report, secrets = support.run_fixture(support.load_fixture(name))
    assert json.loads(l402_report.to_json(report, secrets)) == json.loads(json.dumps(report))


def test_scrub_removes_known_secrets_bolt11_and_l402_authorization_values():
    preimage = support.preimage_from_seed("fixture-string-preimage-1")
    invoice = support.first_invoice(support.load_fixture("le-test-ping"))
    text = (f"known fixture-string-header-value; invoice {invoice}; "
            f"header L402 fixture-string-macaroon-AAAAAAAAAAAA:{preimage}")
    scrubbed = l402_report.scrub(text, {"fixture-string-header-value"})
    assert "fixture-string-header-value" not in scrubbed
    assert invoice not in scrubbed
    assert preimage not in scrubbed
    assert scrubbed.count("[REDACTED]") == 3


def test_payment_hashes_survive_scrubbing():
    payment_hash = "0f3203bd58a26bc984ca6409047213f92da6afcd3e19e394382c7d465e68d7df"
    assert l402_report.scrub(f"payment hash {payment_hash}") == f"payment hash {payment_hash}"


# 9 and 14. No output, JSON or Markdown, carries an invoice, macaroon, token, or credential header.
# The read-only check refuses credential headers before any request (l402_http),
# so the caller's credential rides in the query string here, the one place it can.
def _with_query_credential(fixture: dict, value: str) -> dict:
    original = fixture["request"]["url"]
    url = original + ("&" if "?" in original else "?") + f"api_key={value}"
    fixture["request"]["url"] = url
    for response in fixture["responses"]:
        if response["url"] == original:
            response["url"] = url
    return fixture


@pytest.mark.parametrize("name", support.fixture_names())
def test_output_never_contains_secrets(name):
    fixture = _with_query_credential(support.load_fixture(name), "fixture-string-api-key-value")
    report, secrets = support.run_fixture(fixture)
    forbidden = support.all_secret_strings(fixture) | {"fixture-string-api-key-value"}
    for text in both(report, secrets):
        for value in forbidden:
            assert value not in text
        assert not re.search(r"\bln(?:bc|tb)[0-9a-z]{50,}", text)
        assert "fixture-string-macaroon" not in text
        assert "fixture-string-token" not in text


def test_secret_found_in_the_body_is_never_echoed():
    fixture = support.load_fixture("le-test-ping")
    fixture["responses"][0]["body"] = json.dumps({"debug": "nostr+walletconnect://fixture-string-wallet"})
    report, secrets = support.run_fixture(fixture)
    for text in both(report, secrets):
        assert "walletconnect" not in text


# A read-only check never claims verification, in any wording.
@pytest.mark.parametrize("name", support.fixture_names())
def test_read_only_output_never_claims_verification(name):
    report, secrets = support.run_fixture(support.load_fixture(name))
    for text in both(report, secrets):
        assert "verified" not in text.lower()


# Rulings made after the brief: rerun notes, binding states, and wider scrubbing.

def _section(markdown: str, name: str) -> str:
    return markdown.split(f"## {name}\n", 1)[1].split("\n## ", 1)[0]


def _with_macaroon(name, token):
    fixture = support.load_fixture(name)
    fixture["responses"][0]["headers"] = [
        [k, v.replace('macaroon="fixture-string-macaroon"', f'macaroon="{token}"')]
        for k, v in fixture["responses"][0]["headers"]
    ]
    return fixture


def test_rerun_notes_are_their_own_section_before_required_fixes():
    url = "https://api.example.com/paid"
    fixture = {
        "observed_at": "2026-10-12T20:37:45Z",
        "dns": {},
        "request": {"method": "GET", "url": url},
        "responses": [{"url": url, "status": 405, "headers": [["Allow", "POST"]], "body": ""}],
    }
    report, secrets = support.run_fixture(fixture)
    markdown = l402_report.to_markdown(report, secrets)
    assert l402_report.SECTIONS.index("Rerun notes") == l402_report.SECTIONS.index("Required fixes") - 1
    assert "- Rerun the check with the method the endpoint accepts." in _section(markdown, "Rerun notes")
    assert _section(markdown, "Required fixes").strip() == "- None."
    assert json.loads(l402_report.to_json(report, secrets))["rerun"] == report["rerun"]


def test_an_empty_rerun_list_renders_none():
    report, secrets = support.run_fixture(support.load_fixture("le-test-ping"))
    assert _section(l402_report.to_markdown(report, secrets), "Rerun notes").strip() == "- None."


def test_an_absent_token_is_rendered_plainly_never_as_unverifiable():
    fixture = support.load_fixture("le-proxy-weather")
    fixture["responses"][0]["headers"] = [
        [k, v.replace('macaroon="fixture-string-macaroon", ', "")] for k, v in fixture["responses"][0]["headers"]
    ]
    report, secrets = support.run_fixture(fixture)
    section = _section(l402_report.to_markdown(report, secrets), "Authorization and binding")
    assert "Token format: absent" in section
    assert "not externally verifiable" not in section


def test_an_opaque_token_is_not_externally_verifiable():
    report, secrets = support.run_fixture(support.load_fixture("le-proxy-weather"))
    assert report["binding"]["token_format"] == "opaque"
    section = _section(l402_report.to_markdown(report, secrets), "Authorization and binding")
    assert "Bound to: not externally verifiable" in section


def test_a_decoded_macaroon_with_no_binding_caveats_shows_none_found():
    from test_l402_macaroon import build_v2

    report, secrets = support.run_fixture(_with_macaroon("le-proxy-weather", build_v2(b"fixture-string-id", [])))
    section = _section(l402_report.to_markdown(report, secrets), "Authorization and binding")
    assert "Bound to: none found in caveats" in section


def test_binding_categories_are_listed_with_their_caveat_keys():
    report, secrets = support.run_fixture(support.load_fixture("le-proxy-weather"))
    report["binding"].update(token_format="v2", bound_to={"payment_hash": ["payment_hash"], "method": ["method"]})
    section = _section(l402_report.to_markdown(report, secrets), "Authorization and binding")
    assert "Bound to: payment_hash (payment_hash); method (method)" in section


@pytest.mark.parametrize("text, leaked", [
    ("debug nostr+walletconnect://fixture-string-wallet?relay=wss://r&secret=abc", "walletconnect"),
    ("Authorization: Bearer fixture-string-bearer-value", "fixture-string-bearer-value"),
    ('{"Proxy-Authorization": "Basic fixture-string-basic"}', "fixture-string-basic"),
    ('{"preimage": "' + "ab" * 32 + '"}', "ab" * 32),
    ("preimage=" + "CD" * 32, "CD" * 32),
    ('L402 macaroon="fixture-string-mac", invoice="x"', "fixture-string-mac"),
    ("token=fixture-string-tok&x=1", "fixture-string-tok"),
    ("pay LNBC10N1P4V63G3PP5PUEQ802C5F4UNPX2VSYS now", "LNBC10N1P4V63G3PP5PUEQ802C5F4UNPX2VSYS"),
    ("pay_lntbs1fixturexqqqqqqqqqqqqqqqqqqqqqqqq_now", "lntbs1fixturexqqqqqqqqqqqqqqqqqqqqqqqq"),
    # Fix round 1: preimage keys that only contain the word.
    ("payment_preimage=" + "ef" * 32, "ef" * 32),
    ('{"preimageHex": "' + "a1" * 32 + '"}', "a1" * 32),
    ('"paymentPreimage": "' + "b2" * 32 + '"', "b2" * 32),
    # Fix round 1: macaroon and token values under : as well as =, and under compound keys.
    ('{"macaroon": "fixture-string-json-mac"}', "fixture-string-json-mac"),
    ("access_token=fixture-string-access", "fixture-string-access"),
    ("macaroon: fixture-string-colon-mac", "fixture-string-colon-mac"),
    # Fix round 1: a short token still loses its preimage; simnet invoices; Payment
    # credentials; percent-encoded NWC URIs.
    ("L402 abc:" + "c3" * 32, "c3" * 32),
    ("lnsb1fixturexqqqqqqqqqqqqqqqqqqqqqqqqqq", "lnsb1fixturexqqqqqqqqqqqqqqqqqqqqqqqqqq"),
    ("Payment eyJmaXh0dXJlLXN0cmluZyI6MX0", "eyJmaXh0dXJlLXN0cmluZyI6MX0"),
    ("u=nostr%2Bwalletconnect%3A%2F%2Ffixture-string-wallet", "fixture-string-wallet"),
])
def test_scrub_catches_credentials_wherever_they_appear(text, leaked):
    scrubbed = l402_report.scrub(text)
    assert leaked not in scrubbed
    assert l402_report.REDACTED in scrubbed


def test_scrub_leaves_already_redacted_urls_as_given():
    url = "https://api.example.com/paid?token=REDACTED&city=x"
    assert l402_report.scrub(url) == url


def test_json_scrubs_a_secret_even_when_json_escapes_it():
    report, _ = support.run_fixture(support.load_fixture("le-test-ping"))
    secret = 'fixture-string-quote"value\\x'
    report["summary"] = f"echo {secret}"
    report["target"]["headers"] = {secret: "a"}
    text = l402_report.to_json(report, {secret})
    assert json.dumps(secret)[1:-1] not in text
    assert not any(secret in s for s in _json_strings(text))
    assert secret not in l402_report.to_markdown(report, {secret})


def _json_strings(text: str) -> list[str]:
    """Every key and string value in a JSON document (json.loads fails on invalid JSON)."""
    strings, stack = [], [json.loads(text)]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            strings.extend(node)
            stack.extend(node.values())
        elif isinstance(node, list):
            stack.extend(node)
        elif isinstance(node, str):
            strings.append(node)
    return strings


# Fix round 1: the review's adversarial probes. A caveat key ending in
# "Authorization:" at a line end, a quoted param inside an Authorization value,
# and an Authorization value JSON has to escape.
def test_adversarial_authorization_strings_never_leak_or_break_either_output():
    report, secrets = support.run_fixture(support.load_fixture("le-proxy-weather"))
    report["binding"]["unrecognized_caveats"] = ["X-Authorization:"]
    report["summary"] = 'Authorization: L402 macaroon="fixture-string-adv-mac"'
    report["binding"]["note"] = 'Authorization: "fixture-string-adv-quoted"'
    leaked = ("fixture-string-adv-mac", "fixture-string-adv-quoted")
    markdown = l402_report.to_markdown(report, secrets)
    assert headings(markdown) == headings(TEMPLATE.read_text(encoding="utf-8"))
    assert "- Unrecognized caveats: X-Authorization:" in markdown
    strings = _json_strings(l402_report.to_json(report, secrets))
    for value in leaked:
        assert value not in markdown
        assert not any(value in s for s in strings)


def test_redacted_keys_get_distinct_suffixes_and_keep_their_values():
    report, _ = support.run_fixture(support.load_fixture("le-test-ping"))
    report["target"]["headers"] = {"fixture-string-key-one": "1", "fixture-string-key-two": "2"}
    data = json.loads(l402_report.to_json(report, {"fixture-string-key-one", "fixture-string-key-two"}))
    assert data["target"]["headers"] == {"[REDACTED]#1": "1", "[REDACTED]#2": "2"}


def test_placeholder_values_in_fix_text_survive():
    report, secrets = support.run_fixture(support.load_fixture("synthetic-missing-header"))
    assert 'WWW-Authenticate: L402 macaroon="...", invoice="..."' in l402_report.to_markdown(report, secrets)


# Fix round 2: with nothing secret in the report, nothing may be redacted. A
# finding rendered "missing_token: message" read to the scrubber as a token value.
def _absent_token_fixture():
    fixture = support.load_fixture("le-proxy-weather")
    fixture["responses"][0]["headers"] = [
        [k, v.replace('macaroon="fixture-string-macaroon", ', "")] for k, v in fixture["responses"][0]["headers"]
    ]
    return fixture


def _method_not_allowed_fixture():
    url = "https://api.example.com/paid"
    return {
        "observed_at": "2026-10-12T20:37:45Z",
        "dns": {},
        "request": {"method": "GET", "url": url},
        "responses": [{"url": url, "status": 405, "headers": [["Allow", "POST"]], "body": ""}],
    }


@pytest.mark.parametrize("fixture", [
    *[pytest.param(support.load_fixture(name), id=name) for name in support.fixture_names()],
    pytest.param(_absent_token_fixture(), id="absent-token"),
    pytest.param(_method_not_allowed_fixture(), id="method-not-allowed"),
])
def test_a_report_with_no_secrets_renders_without_redaction(fixture):
    report, _ = support.run_fixture(fixture, max_sats=2)
    for text in both(report, frozenset()):
        assert l402_report.REDACTED not in text


def test_a_hex_secret_is_scrubbed_whatever_its_case():
    preimage = support.preimage_from_seed("fixture-string-preimage-1")
    mixed = preimage[:32].upper() + preimage[32:]
    report, secrets = support.run_fixture(support.load_fixture("le-test-ping"))
    report["summary"] = f"lower {preimage}; upper {preimage.upper()}; mixed {mixed}"
    for text in both(report, secrets | {preimage}):
        assert preimage not in text.lower()
    assert l402_report.scrub(report["summary"], {preimage.upper()}).count(l402_report.REDACTED) == 3


def test_finding_rows_render_code_in_brackets():
    report, secrets = support.run_fixture(_absent_token_fixture())
    section = _section(l402_report.to_markdown(report, secrets), "Challenge")
    assert "- [missing_token] The L402 challenge has no macaroon or token parameter." in section


def test_no_rendered_row_reads_as_a_token_value():
    report, secrets = support.run_fixture(support.load_fixture("le-proxy-weather"))
    section = _section(l402_report.to_markdown(report, secrets), "Authorization and binding")
    assert "Token payment hash: not externally verifiable" in section
    assert l402_report.REDACTED not in section


def test_optional_marketplace_profiles_is_the_last_section():
    assert l402_report.SECTIONS[-1] == "Optional marketplace profiles"
    assert "Marketplace readiness" not in l402_report.SECTIONS
    report, secrets = support.run_fixture(support.load_fixture("le-proxy-weather"))
    markdown = l402_report.to_markdown(report, secrets)
    core, tail = markdown.split("\n## Optional marketplace profiles\n", 1)
    assert "### Amazap" in tail
    assert "- Status: NOT_CHECKED" in tail
    assert "(advisory)" in tail
    assert "never changes the classification" in tail
    assert "marketplace-ready" not in core.lower()
    assert "host_root_metadata" not in core
