"""RFC 7235 WWW-Authenticate parsing for the l402-compatibility-report script."""
import pytest

import l402_check_support as support
import l402_challenge


def www_authenticate(name: str) -> list[str]:
    fixture = support.load_fixture(name)
    return [v for k, v in fixture["responses"][0]["headers"] if k.lower() == "www-authenticate"]


@pytest.mark.parametrize(
    "name, kinds",
    [
        ("le-proxy-weather", ["L402", "Payment"]),
        ("amazap-basics-feed", ["L402", "Payment"]),
        ("toon-extract-single-l402", ["L402"]),
        ("major-miners-lsat-plus-l402", ["LSAT", "L402"]),
        ("taskhawk-l402-payment-x402", ["L402", "Payment", "x402"]),
    ],
)
def test_captured_headers_parse_cleanly(name, kinds):
    result = l402_challenge.parse(www_authenticate(name))
    assert result.errors == []
    assert [c.kind for c in result.challenges] == kinds


def test_amazap_l402_challenge_carries_an_extra_token_param():
    result = l402_challenge.parse(www_authenticate("amazap-basics-feed"))
    l402 = result.challenges[0]
    assert sorted(l402.params) == ["invoice", "macaroon", "token"]
    payment = result.challenges[1]
    assert sorted(payment.params) == ["expires", "id", "intent", "method", "opaque", "realm", "request"]


@pytest.mark.parametrize("name", support.fixture_names())
def test_comma_joined_header_parses_like_separate_headers(name):
    headers = www_authenticate(name)
    separate = l402_challenge.parse(headers)
    joined = l402_challenge.parse([", ".join(headers)] if headers else [])
    assert [(c.kind, c.params, c.duplicate_params) for c in joined.challenges] == [
        (c.kind, c.params, c.duplicate_params) for c in separate.challenges
    ]
    assert bool(joined.errors) == bool(separate.errors)


def test_quoted_string_escapes_are_unescaped():
    result = l402_challenge.parse(['L402 macaroon="a\\"b\\\\c", invoice="d"'])
    assert result.errors == []
    assert result.challenges[0].param("macaroon") == 'a"b\\c'


def test_token_values_and_case_insensitive_names():
    result = l402_challenge.parse(["l402 MACAROON=abc, Invoice=def"])
    challenge = result.challenges[0]
    assert challenge.kind == "L402"
    assert challenge.scheme == "l402"
    assert challenge.param("macaroon") == "abc"
    assert challenge.param("INVOICE") == "def"


def test_token68_challenge_then_l402():
    result = l402_challenge.parse(['Basic dXNlcjpwYXNz==, L402 macaroon="a", invoice="b"'])
    assert result.errors == []
    assert result.challenges[0].kind == "other"
    assert result.challenges[0].token68 == "dXNlcjpwYXNz=="
    assert result.challenges[1].params == {"macaroon": "a", "invoice": "b"}


def test_duplicate_params_are_reported_not_overwritten():
    result = l402_challenge.parse(['L402 macaroon="a", macaroon="b", invoice="c"'])
    challenge = result.challenges[0]
    assert challenge.param("macaroon") == "a"
    assert challenge.duplicate_params == ["macaroon"]


def test_malformed_quoting_is_an_error_without_echoing_values():
    result = l402_challenge.parse(www_authenticate("synthetic-malformed-quoting"))
    assert result.errors
    assert "offset" in result.errors[0]
    assert "fixture-string" not in result.errors[0]
    assert "lnbc" not in result.errors[0]


def test_unterminated_quote_is_an_error():
    result = l402_challenge.parse(['L402 macaroon="fixture-string-macaroon'])
    assert result.errors == ["header 0: unterminated quoted-string at offset 5"]


def test_empty_auth_param_value_is_an_error_not_a_phantom_scheme():
    result = l402_challenge.parse(['L402 macaroon="m", invoice=, foo=bar'])
    assert [c.scheme for c in result.challenges] == ["L402"]
    assert len(result.errors) == 1


def test_bare_scheme_and_empty_input():
    assert [c.scheme for c in l402_challenge.parse(["Negotiate"]).challenges] == ["Negotiate"]
    assert l402_challenge.parse([]).challenges == []
