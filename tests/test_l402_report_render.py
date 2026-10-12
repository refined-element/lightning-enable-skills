"""Report rendering: the Markdown follows templates/report.md, and no output carries a secret."""
import json
import re

import pytest

import l402_check_support as support
import l402_report

TEMPLATE = support.SKILL_DIR / "templates" / "report.md"


def headings(markdown: str) -> list[str]:
    return re.findall(r"^#{1,2} (.+)$", markdown, flags=re.MULTILINE)


def both(report, secrets):
    return l402_report.to_json(report, secrets), l402_report.to_markdown(report, secrets)


def test_template_lists_the_spec_sections_in_order():
    assert headings(TEMPLATE.read_text(encoding="utf-8")) == ["L402 Compatibility Report", *l402_report.SECTIONS]


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


def test_json_is_valid_and_round_trips():
    report, secrets = support.run_fixture(support.load_fixture("amazap-basics-feed"))
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
    assert not any(secret in s for s in strings)
    assert secret not in l402_report.to_markdown(report, {secret})
