"""The L402 challenge fixtures are well formed and hold no live credential.

Captured fixtures keep their expired, unpaid invoices (the decoder tests need
them) but every macaroon and token value is a ``fixture-string-`` placeholder,
so a secret scanner has nothing to flag and nothing here can authorize a call.
"""
import re

import pytest

import l402_check_support as support

REQUIRED_KEYS = {"name", "origin", "observed_at", "dns", "request", "responses", "expected"}
EXPECTED_KEYS = {"classification", "schemes", "classified_by", "amount_sats", "payment_hash", "finding_codes"}
CAPTURED = {
    "le-proxy-weather", "le-content-guide", "le-test-ping", "amazap-basics-feed", "toon-extract-single-l402",
    "l402kit-worldstate-single-l402", "major-miners-lsat-plus-l402", "parsebit-lsat-plus-l402",
    "taskhawk-l402-payment-x402", "store-checkout-empty-post-415", "ppq-200-unpaid",
}
SYNTHETIC = {
    "synthetic-missing-header", "synthetic-malformed-quoting", "synthetic-amountless-invoice",
    "synthetic-expired-invoice", "synthetic-payment-only", "synthetic-400-before-402",
    "synthetic-401-unpaid", "synthetic-redirect-private",
}


def test_every_expected_fixture_exists():
    assert set(support.fixture_names()) == CAPTURED | SYNTHETIC


@pytest.mark.parametrize("name", support.fixture_names())
def test_fixture_shape(name):
    fixture = support.load_fixture(name)
    assert set(fixture) == REQUIRED_KEYS
    assert fixture["name"] == name
    assert set(fixture["expected"]) == EXPECTED_KEYS
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", fixture["observed_at"])
    assert fixture["request"]["url"].startswith("https://")
    for response in fixture["responses"]:
        assert {"url", "status", "headers", "body"} <= set(response)


@pytest.mark.parametrize("name", support.fixture_names())
def test_fixture_macaroons_and_tokens_are_placeholders(name):
    for header in support.www_authenticate(support.load_fixture(name)):
        for key, value in re.findall(r'\b(macaroon|token)="([^"]*)"', header):
            assert value.startswith("fixture-string-"), f"{name}: {key} is not a placeholder"


@pytest.mark.parametrize("name", support.fixture_names())
def test_fixture_bodies_carry_no_live_macaroon(name):
    for response in support.load_fixture(name)["responses"]:
        for value in re.findall(r'"(?:macaroon|token|preimage)"\s*:\s*"([^"]*)"', response["body"]):
            assert value.startswith("fixture-string-")


def test_no_fixture_uses_a_secret_style_name():
    for path in sorted(support.CHALLENGES.glob("*.json")):
        text = path.read_text(encoding="utf-8")
        assert not re.search(r'"(?:secret|key)-[a-z0-9-]+"', text), path.name
