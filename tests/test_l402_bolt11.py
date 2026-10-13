"""BOLT11 decoding for the l402-compatibility-report script, against captured invoices."""
import re

import pytest

import l402_check_support as support
import l402_bolt11


def captured_invoice(name: str) -> str:
    fixture = support.load_fixture(name)
    header = fixture["responses"][0]["headers"][0][1]
    return re.search(r'invoice="(ln[0-9a-z]+)"', header).group(1)


@pytest.mark.parametrize(
    "name, sats, payment_hash, expiry, timestamp",
    [
        ("le-proxy-weather", 3, "f41249023341ff317a271287643ae346fc210b620be17520c797f23cb4d35931", 86399, 1791837456),
        ("le-content-guide", 3616, "059a7dbd42b6897bc618193929c7c20ccb598072fd7191f659ee36a4e37a36a6", 86399, 1791837457),
        ("amazap-basics-feed", 13, "690e2d99ef4fbed11168642f0fa37bbb5a46e8aa68c6992ebf811e69d43cea9c", 120, 1791837458),
        ("l402kit-worldstate-single-l402", 300, "36415284c23f18f7ad491e923f2d28f99db183672dac3c260623ae675ff4be25", 14400, 1791837460),
        ("parsebit-lsat-plus-l402", 150, "9a6a29036ff7153eda6298b246fc2f503eaabcab7e82d792e8d5b52db8689476", 86400, 1791837461),
    ],
)
def test_decodes_captured_invoices(name, sats, payment_hash, expiry, timestamp):
    invoice = l402_bolt11.decode(captured_invoice(name))
    assert invoice.network == "mainnet"
    assert invoice.amount_sats == sats
    assert invoice.amount_msat == sats * 1000
    assert invoice.payment_hash == payment_hash
    assert invoice.expiry_seconds == expiry
    assert invoice.timestamp == timestamp
    assert invoice.expires_at == timestamp + expiry


def test_description_versus_description_hash():
    assert l402_bolt11.decode(captured_invoice("le-test-ping")).has_description is True
    hashed = l402_bolt11.decode(captured_invoice("l402kit-worldstate-single-l402"))
    assert hashed.has_description is False
    assert hashed.has_description_hash is True


def test_route_hints_are_counted_and_payee_is_not_recovered():
    invoice = l402_bolt11.decode(captured_invoice("amazap-basics-feed"))
    assert invoice.route_hint_count == 4
    assert invoice.payee is None  # no n field; recovering it needs the signature
    assert invoice.has_features is True


def test_amountless_invoice_has_no_amount():
    fixture = support.load_fixture("synthetic-amountless-invoice")
    raw = re.search(r'invoice="(ln[0-9a-z]+)"', fixture["responses"][0]["headers"][0][1]).group(1)
    invoice = l402_bolt11.decode(raw)
    assert invoice.amount_msat is None
    assert invoice.amount_sats is None
    assert invoice.payment_hash == "0f3203bd58a26bc984ca6409047213f92da6afcd3e19e394382c7d465e68d7df"


def test_default_expiry_is_3600_when_x_is_absent():
    assert l402_bolt11.DEFAULT_EXPIRY_SECONDS == 3600
    assert l402_bolt11.Invoice(network="mainnet", amount_msat=None, timestamp=0).expiry_seconds == 3600


@pytest.mark.parametrize(
    "hrp, expected",
    [("lnbc", ("mainnet", None)), ("lnbc10n", ("mainnet", 1000)), ("lnbc2500u", ("mainnet", 250_000_000)),
     ("lnbc1m", ("mainnet", 100_000_000)), ("lnbc10p", ("mainnet", 1)), ("lntb10n", ("testnet", 1000)),
     ("lntbs10n", ("signet", 1000)), ("lnbcrt10n", ("regtest", 1000)), ("lnbc1", ("mainnet", 100_000_000_000))],
)
def test_human_readable_part(hrp, expected):
    assert l402_bolt11._parse_hrp(hrp) == expected


@pytest.mark.parametrize("hrp", ["lnxx10n", "bc10n", "lnbc01n", "lnbc1x", "lnbc15p"])
def test_bad_human_readable_part_is_rejected(hrp):
    with pytest.raises(l402_bolt11.Bolt11Error):
        l402_bolt11._parse_hrp(hrp)


def test_bad_checksum_is_rejected_without_echoing_the_invoice():
    raw = captured_invoice("le-test-ping")
    broken = raw[:-1] + ("q" if raw[-1] != "q" else "p")
    with pytest.raises(l402_bolt11.Bolt11Error) as caught:
        l402_bolt11.decode(broken)
    assert "checksum" in str(caught.value)
    assert raw[:20] not in str(caught.value)


def test_mixed_case_is_rejected():
    raw = captured_invoice("le-test-ping")
    with pytest.raises(l402_bolt11.Bolt11Error) as caught:
        l402_bolt11.decode(raw[:10].upper() + raw[10:])
    assert "mixed case" in str(caught.value)


def test_non_ascii_is_rejected_before_any_other_check():
    with pytest.raises(l402_bolt11.Bolt11Error) as caught:
        l402_bolt11.decode("lnbc²n1fixture")
    assert "non-ASCII" in str(caught.value)


def test_not_an_invoice():
    with pytest.raises(l402_bolt11.Bolt11Error):
        l402_bolt11.decode("fixture-string-not-an-invoice")
