"""Paid check (Mode B): validate the recorded evidence of one paid call. Nothing here pays.

Each fixture in tests/fixtures/l402-evidence records what access_l402_resource
returned and what the wallet receipt shows. ``test_preimage_seed`` stands in
for the credential the agent pipes on stdin: the test derives a 64-hex
preimage from it at runtime and removes the key before evaluation, so no
preimage is stored in the repo.
"""
import json
import re

import pytest

import l402_check_support as support
import l402_evidence
import l402_report
from test_l402_macaroon import build_v2, lightning_labs_identifier

SEED_1_HASH = "65e0276b37174dbbdfecc0de804298820c9bb69500d080314b7cc6609d82c88c"
SEED_2_HASH = "3767717728be78a60971cd3e247c920985642a81311e9b9376c27c23cab2c6cb"


def mode_a(root_metadata_ok: bool = False) -> dict:
    extra = []
    if root_metadata_ok:
        extra = [{"url": "https://api.lightningenable.com/llms.txt", "status": 200, "headers": [], "body": "# llms"}]
    report, _ = support.run_fixture(support.load_fixture("le-test-ping"), extra_responses=extra)
    return report


def evidence_for(name: str, *, root_metadata_ok: bool = False):
    evidence = support.load_evidence(name)
    seed = evidence.pop("test_preimage_seed")
    evidence["mode_a_report"] = mode_a(root_metadata_ok)
    return evidence, (support.preimage_from_seed(seed) if seed else None)


def paid_codes(report: dict) -> set[str]:
    return {f["code"] for f in report["findings"]}


@pytest.mark.parametrize(
    "name, classification, code",
    [
        ("fulfilled-2xx", "FULFILLMENT_VERIFIED", "marketplace_gaps"),
        ("preimage-mismatch", "INCOMPATIBLE", "preimage_mismatch"),
        # A confirmed payment and a definitive non-2xx answer: PAYMENT_COMPATIBLE.
        ("paid-retry-402", "PAYMENT_COMPATIBLE", "paid_retry_402"),
        ("second-payment", "INCONCLUSIVE", "multiple_payments"),
        ("multiple-payments", "INCONCLUSIVE", "multiple_payments"),
        ("ambiguous-fulfillment", "INCONCLUSIVE", "ambiguous_fulfillment"),
        ("pending-payment", "INCONCLUSIVE", "payment_pending"),
        ("paid-over-cap", "INCONCLUSIVE", "paid_over_cap"),
        ("preimage-not-surfaced", "INCONCLUSIVE", "preimage_unchecked"),
        ("credential-absent-with-receipt", "INCONCLUSIVE", "preimage_unchecked"),
        ("credential-present-no-comparable-hash", "INCONCLUSIVE", "no_hash_to_compare"),
        ("2xx-missing-expectations", "PAYMENT_COMPATIBLE", "unexpected_result"),
        ("awaiting-confirmation", "INCONCLUSIVE", "awaiting_confirmation"),
    ],
)
def test_evidence_classification(name, classification, code):
    evidence, preimage = evidence_for(name)
    report = l402_evidence.evaluate(evidence, preimage)
    assert report["mode"] == "paid"
    assert report["classification"] == classification
    assert code in paid_codes(report)


# 6. The paid check proves preimage/payment-hash correspondence.
def test_matching_preimage_is_checked_against_the_receipt_hash():
    evidence, preimage = evidence_for("fulfilled-2xx")
    report = l402_evidence.evaluate(evidence, preimage)
    paid = report["paid_fulfillment"]
    assert paid["preimage_check"] == "matched"
    assert paid["hash_sources"] == [{"source": "wallet receipt", "payment_hash": SEED_1_HASH, "match": True}]


@pytest.mark.parametrize("prefix", ["", "L402 ", "LSAT ", "Authorization: L402 "])
def test_l402_token_forms_are_split_and_hashed(prefix):
    evidence, preimage = evidence_for("fulfilled-2xx")
    report = l402_evidence.evaluate(evidence, f"{prefix}fixture-string-macaroon:{preimage}")
    assert report["paid_fulfillment"]["preimage_check"] == "matched"


def test_lightning_labs_macaroon_hash_is_compared_alongside_the_receipt():
    evidence, preimage = evidence_for("fulfilled-2xx")
    macaroon = build_v2(lightning_labs_identifier(SEED_1_HASH), [])
    report = l402_evidence.evaluate(evidence, f"L402 {macaroon}:{preimage}")
    assert report["classification"] == "FULFILLMENT_VERIFIED"
    assert report["paid_fulfillment"]["hash_sources"] == [
        {"source": "macaroon identifier", "payment_hash": SEED_1_HASH, "match": True},
        {"source": "wallet receipt", "payment_hash": SEED_1_HASH, "match": True},
    ]


def test_lightning_labs_macaroon_alone_is_a_comparable_hash():
    evidence, preimage = evidence_for("credential-present-no-comparable-hash")
    macaroon = build_v2(lightning_labs_identifier(SEED_1_HASH), [])
    report = l402_evidence.evaluate(evidence, f"L402 {macaroon}:{preimage}")
    assert report["paid_fulfillment"]["preimage_check"] == "matched"
    assert report["classification"] == "FULFILLMENT_VERIFIED"


def test_macaroon_bound_to_another_hash_is_a_mismatch():
    evidence, preimage = evidence_for("fulfilled-2xx")
    macaroon = build_v2(lightning_labs_identifier(SEED_2_HASH), [])
    report = l402_evidence.evaluate(evidence, f"L402 {macaroon}:{preimage}")
    assert report["paid_fulfillment"]["preimage_check"] == "mismatch"
    assert report["classification"] == "INCOMPATIBLE"
    assert "preimage_mismatch" in paid_codes(report)


def test_credential_without_any_comparable_hash_is_inconclusive():
    evidence, preimage = evidence_for("credential-present-no-comparable-hash")
    report = l402_evidence.evaluate(evidence, f"L402 fixture-string-macaroon:{preimage}")
    assert report["paid_fulfillment"]["preimage_check"] == "no_hash_source"
    assert report["paid_fulfillment"]["hash_sources"] == []
    assert report["classification"] == "INCONCLUSIVE"
    assert "no_hash_to_compare" in paid_codes(report)


def test_malformed_preimage_is_inconclusive():
    evidence, _ = evidence_for("fulfilled-2xx")
    report = l402_evidence.evaluate(evidence, "fixture-string-macaroon:not-hex")
    assert report["paid_fulfillment"]["preimage_check"] == "malformed"
    assert report["classification"] == "INCONCLUSIVE"


# Without the credential, a receipt is supporting evidence and never upgrades the class.
def test_receipt_without_credential_is_recorded_but_never_upgrades():
    evidence, preimage = evidence_for("credential-absent-with-receipt", root_metadata_ok=True)
    assert preimage is None
    report = l402_evidence.evaluate(evidence, None)
    assert report["classification"] == "INCONCLUSIVE"
    assert report["paid_fulfillment"]["preimage_check"] == "not_available"
    receipt = report["paid_fulfillment"]["receipts"][0]
    assert receipt["payment_hash"] == SEED_1_HASH
    assert receipt["amount_sats"] == 1
    assert receipt["status"] == "settled"
    assert receipt["context"].startswith("fixture-string-receipt-context")
    assert report["evidence"]["payment_hash"] == SEED_1_HASH


def test_paid_402_without_the_credential_is_inconclusive_not_payment_compatible():
    evidence, _ = evidence_for("paid-retry-402")
    report = l402_evidence.evaluate(evidence, None)
    assert report["classification"] == "INCONCLUSIVE"
    assert "preimage_unchecked" in paid_codes(report)
    assert "paid_retry_402" not in paid_codes(report)


# 7. A successful authorized retry is FULFILLMENT_VERIFIED.
def test_successful_retry_is_fulfillment_verified():
    evidence, preimage = evidence_for("fulfilled-2xx")
    report = l402_evidence.evaluate(evidence, preimage)
    assert report["classification"] == "FULFILLMENT_VERIFIED"
    assert report["evidence"]["statuses"] == [402, 200]
    assert report["evidence"]["payment_hash"] == SEED_1_HASH
    assert report["evidence"]["amount_sats"] == 1


def test_unmet_expectation_is_payment_compatible():
    evidence, preimage = evidence_for("fulfilled-2xx")
    evidence["expected"]["content_type"] = "text/csv"
    report = l402_evidence.evaluate(evidence, preimage)
    assert report["classification"] == "PAYMENT_COMPATIBLE"
    assert "expected_content_type" in next(f for f in report["findings"] if f["code"] == "unexpected_result")["message"]


def test_empty_body_on_a_get_misses_expectations():
    evidence, preimage = evidence_for("fulfilled-2xx")
    evidence["tool_result"]["body_length"] = 0
    report = l402_evidence.evaluate(evidence, preimage)
    assert report["classification"] == "PAYMENT_COMPATIBLE"
    assert "non_empty_body" in next(f for f in report["findings"] if f["code"] == "unexpected_result")["message"]


def test_head_request_does_not_need_a_body():
    evidence, preimage = evidence_for("fulfilled-2xx")
    evidence["mode_a_report"]["target"]["method"] = "HEAD"
    evidence["tool_result"]["body_length"] = 0
    report = l402_evidence.evaluate(evidence, preimage)
    assert report["classification"] == "FULFILLMENT_VERIFIED"
    assert "non_empty_body" not in {c["name"] for c in report["paid_fulfillment"]["expectations"]}


@pytest.mark.parametrize("status, code", [(403, "paid_retry_rejected"), (500, "paid_retry_failed"), (502, "paid_retry_failed")])
def test_definitive_non_2xx_after_a_confirmed_payment_is_payment_compatible(status, code):
    evidence, preimage = evidence_for("paid-retry-402")
    evidence["tool_result"]["status_code"] = status
    report = l402_evidence.evaluate(evidence, preimage)
    assert report["classification"] == "PAYMENT_COMPATIBLE"
    assert code in paid_codes(report)


@pytest.mark.parametrize("status", [None, 408, 429, 504])
def test_no_answer_or_a_timeout_after_payment_is_inconclusive(status):
    evidence, preimage = evidence_for("ambiguous-fulfillment")
    if status is not None:
        evidence["tool_result"]["status_code"] = status
    report = l402_evidence.evaluate(evidence, preimage)
    assert report["classification"] == "INCONCLUSIVE"
    assert "ambiguous_fulfillment" in paid_codes(report)


def test_two_payments_cap_the_result_at_inconclusive_even_when_everything_else_passes():
    evidence, preimage = evidence_for("second-payment", root_metadata_ok=True)
    evidence["expected"] = {"status": 200, "content_type": "application/json"}
    report = l402_evidence.evaluate(evidence, preimage)
    assert report["classification"] == "INCONCLUSIVE"
    assert report["paid_fulfillment"]["payments_recorded"] == 2
    assert report["paid_fulfillment"]["payment_hashes"] == [SEED_1_HASH, SEED_2_HASH]


# The quote's hash and the paid hash are compared as information, never as a finding.
@pytest.mark.parametrize("same", [False, True])
def test_quote_and_paid_hashes_are_compared_as_information_only(same):
    evidence, preimage = evidence_for("credential-absent-with-receipt")
    quoted = evidence["mode_a_report"]["invoice"]["payment_hash"]
    if same:
        evidence["payments"][0]["payment_hash"] = quoted
    baseline = l402_evidence.evaluate(evidence_for("credential-absent-with-receipt")[0], None)
    report = l402_evidence.evaluate(evidence, None)
    paid = report["paid_fulfillment"]
    assert paid["quote_payment_hash"] == quoted
    assert paid["quote_hash_matches"] is same
    assert paid_codes(report) == paid_codes(baseline)
    assert report["classification"] == baseline["classification"]


# 10. Marketplace classification needs paid fulfillment plus metadata and bounded execution.
def test_marketplace_ready_needs_fulfillment_and_every_listing_check():
    evidence, preimage = evidence_for("fulfilled-2xx", root_metadata_ok=True)
    report = l402_evidence.evaluate(evidence, preimage)
    assert report["classification"] == "MARKETPLACE_READY"
    assert report["marketplace"]["listing_ready"] is True

    without_metadata, preimage = evidence_for("fulfilled-2xx")
    assert l402_evidence.evaluate(without_metadata, preimage)["classification"] == "FULFILLMENT_VERIFIED"

    unproven, _ = evidence_for("preimage-not-surfaced", root_metadata_ok=True)
    assert l402_evidence.evaluate(unproven, None)["classification"] == "INCONCLUSIVE"


def test_price_change_between_quote_and_payment_blocks_marketplace_ready():
    evidence, preimage = evidence_for("fulfilled-2xx", root_metadata_ok=True)
    evidence["tool_result"]["paid_sats"] = 2
    evidence["payments"][0]["amount_sats"] = 2
    report = l402_evidence.evaluate(evidence, preimage)
    assert report["classification"] == "FULFILLMENT_VERIFIED"
    gaps = next(f for f in report["findings"] if f["code"] == "marketplace_gaps")
    assert "stable_price" in gaps["message"]


def test_accepted_but_deferred_response_blocks_marketplace_ready():
    evidence, preimage = evidence_for("fulfilled-2xx", root_metadata_ok=True)
    evidence["tool_result"]["status_code"] = 202
    del evidence["expected"]["status"]
    report = l402_evidence.evaluate(evidence, preimage)
    assert report["classification"] == "FULFILLMENT_VERIFIED"
    gaps = next(f for f in report["findings"] if f["code"] == "marketplace_gaps")
    assert "synchronous_response" in gaps["message"]


# 8. Paid success then ambiguous fulfillment: INCONCLUSIVE, correlators kept, no repay.
def test_ambiguous_fulfillment_keeps_correlators_and_never_suggests_paying_again():
    evidence, preimage = evidence_for("ambiguous-fulfillment")
    report = l402_evidence.evaluate(evidence, preimage)
    assert report["classification"] == "INCONCLUSIVE"
    assert report["evidence"]["payment_hash"] == SEED_1_HASH
    assert report["evidence"]["amount_sats"] == 1
    text = l402_report.to_markdown(report)
    assert "do not pay again" in text.lower()
    assert "retry the payment" not in text.lower()


@pytest.mark.parametrize("name", sorted(p.stem for p in support.EVIDENCE.glob("*.json")
                                        if p.stem != "evidence-file-with-credential-key-refused"))
def test_no_report_ever_suggests_paying_again(name):
    evidence, preimage = evidence_for(name)
    text = l402_report.to_markdown(l402_evidence.evaluate(evidence, preimage)).lower()
    assert "retry the payment" not in text
    assert re.search(r"(?<!not )(?<!never )(?<!don't )pay again", text) is None
    assert "verified" not in text.replace("fulfillment_verified", "")


def test_a_paid_check_after_a_failed_read_only_check_is_inconclusive():
    evidence, preimage = evidence_for("fulfilled-2xx")
    evidence["mode_a_report"] = support.run_fixture(support.load_fixture("synthetic-amountless-invoice"))[0]
    report = l402_evidence.evaluate(evidence, preimage)
    assert report["classification"] == "INCONCLUSIVE"
    assert "paid_check_without_challenge" in paid_codes(report)


@pytest.mark.parametrize("key", ["preimage", "l402Token", "l402_token", "macaroon", "credential", "Authorization",
                                 "token", "PREIMAGE", "Macaroon"])
def test_credentials_inside_the_evidence_file_are_refused(key):
    evidence, _ = evidence_for("fulfilled-2xx")
    evidence["tool_result"][key] = "fixture-string-credential"
    with pytest.raises(l402_evidence.EvidenceError) as caught:
        l402_evidence.evaluate(evidence, None)
    assert "stdin" in str(caught.value)
    assert "fixture-string-credential" not in str(caught.value)


def test_credential_nested_in_a_list_is_refused():
    evidence, _ = evidence_for("fulfilled-2xx")
    evidence["payments"][0]["extra"] = [{"Token": "fixture-string-credential"}]
    with pytest.raises(l402_evidence.EvidenceError):
        l402_evidence.evaluate(evidence, None)


def test_the_refused_fixture_is_refused_before_anything_else_is_read():
    # No mode_a_report at all: the credential check still wins.
    evidence = support.load_evidence("evidence-file-with-credential-key-refused")
    evidence.pop("test_preimage_seed")
    with pytest.raises(l402_evidence.EvidenceError) as caught:
        l402_evidence.evaluate(evidence, None)
    message = str(caught.value)
    assert "evidence.tool_result.payment.l402Token" in message
    assert "--credential-stdin" in message
    assert "fixture-string-credential" not in message


@pytest.mark.parametrize("field, value", [
    ("cap_sats", 0),
    ("cap_sats", "10"),
    ("cap_sats", True),
    ("tool_result", None),
    ("mode_a_report", {}),
    ("payments", {}),
    ("payments", [{"amount_sats": 1, "status": "settled", "payment_hash": "fixture-string-not-a-hash"}]),
    ("payments", [{"amount_sats": "1", "status": "settled"}]),
    ("expected", {"status": "200"}),
    ("expected", []),
])
def test_malformed_evidence_is_refused(field, value):
    evidence, _ = evidence_for("fulfilled-2xx")
    evidence[field] = value
    with pytest.raises(l402_evidence.EvidenceError):
        l402_evidence.evaluate(evidence, None)


@pytest.mark.parametrize("field, value", [("paid_sats", "1"), ("status_code", "200"), ("success", "yes"), ("body_length", -1)])
def test_malformed_tool_result_fields_are_refused(field, value):
    evidence, _ = evidence_for("fulfilled-2xx")
    evidence["tool_result"][field] = value
    with pytest.raises(l402_evidence.EvidenceError):
        l402_evidence.evaluate(evidence, None)


def test_a_paid_report_is_not_accepted_as_the_read_only_report():
    evidence, preimage = evidence_for("fulfilled-2xx")
    first = l402_evidence.evaluate(evidence, preimage)
    again, _ = evidence_for("fulfilled-2xx")
    again["mode_a_report"] = first
    with pytest.raises(l402_evidence.EvidenceError):
        l402_evidence.evaluate(again, preimage)


def test_paid_report_keeps_the_rerun_key_and_fills_the_paid_sections():
    evidence, preimage = evidence_for("credential-absent-with-receipt")
    report = l402_evidence.evaluate(evidence, preimage)
    assert isinstance(report["rerun"], list)
    assert any("--credential-stdin" in note for note in report["rerun"])
    assert report["paid_fulfillment"]["tested"] is True
    assert report["replay"]["tested"] is False
    markdown = l402_report.to_markdown(report)
    section = markdown.split("## Paid fulfillment", 1)[1].split("\n## ", 1)[0]
    assert "fixture-string-receipt-context" in section
    assert SEED_1_HASH in section


def test_paid_report_never_contains_the_credential():
    evidence, preimage = evidence_for("fulfilled-2xx")
    token = f"L402 fixture-string-macaroon:{preimage}"
    report = l402_evidence.evaluate(evidence, token)
    secrets = {token, "fixture-string-macaroon", preimage}
    for text in (l402_report.to_json(report, secrets), l402_report.to_markdown(report, secrets)):
        assert preimage not in text
        assert "fixture-string-macaroon" not in text
        assert SEED_1_HASH in text


def test_the_report_dict_itself_holds_no_credential_even_unscrubbed():
    evidence, preimage = evidence_for("fulfilled-2xx")
    macaroon = build_v2(lightning_labs_identifier(SEED_1_HASH), [])
    token = f"L402 {macaroon}:{preimage}"
    report = l402_evidence.evaluate(evidence, token)
    raw = json.dumps(report)
    assert preimage not in raw
    assert macaroon not in raw
    assert SEED_1_HASH in raw
    secrets = l402_evidence.credential_secrets(token)
    assert {preimage, macaroon} <= secrets
    assert preimage not in l402_report.to_markdown(report, secrets)
