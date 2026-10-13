"""Paid check (Mode B): validate the recorded evidence of one paid call. Nothing here pays.

Each fixture in tests/fixtures/l402-evidence records what access_l402_resource
returned and what the wallet receipt shows. ``test_preimage_seed`` stands in
for the credential the agent pipes on stdin: the test derives a 64-hex
preimage from it at runtime and removes the key before evaluation, so no
preimage is stored in the repo. The credential is always an
``L402 <macaroon>:<preimage>`` token: the macaroon is an opaque placeholder,
or, when ``test_macaroon_hash`` is set, a Lightning Labs macaroon whose
identifier carries that hash, built in code at runtime.
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
SEED_1_PREIMAGE = support.preimage_from_seed("fixture-string-preimage-1")
# Not a Lightning Labs macaroon: it carries no payment hash, so only the receipt is comparable.
OPAQUE_MACAROON = "fixture-string-macaroon"


def mode_a(root_metadata_ok: bool = False) -> dict:
    extra = []
    if root_metadata_ok:
        extra = [{"url": "https://api.lightningenable.com/llms.txt", "status": 200, "headers": [], "body": "# llms"}]
    report, _ = support.run_fixture(support.load_fixture("le-test-ping"), extra_responses=extra)
    return report


def evidence_for(name: str, *, root_metadata_ok: bool = False):
    evidence = support.load_evidence(name)
    seed = evidence.pop("test_preimage_seed")
    macaroon_hash = evidence.pop("test_macaroon_hash", None)
    evidence["mode_a_report"] = mode_a(root_metadata_ok)
    if not seed:
        return evidence, None
    preimage = support.preimage_from_seed(seed)
    macaroon = build_v2(lightning_labs_identifier(macaroon_hash), []) if macaroon_hash else OPAQUE_MACAROON
    return evidence, f"L402 {macaroon}:{preimage}"


def paid_codes(report: dict) -> set[str]:
    return {f["code"] for f in report["findings"]}


@pytest.mark.parametrize(
    "name, classification, code",
    [
        ("fulfilled-2xx", "FULFILLMENT_VERIFIED", "marketplace_gaps"),
        # Receipt-only mismatch: likely the wrong receipt, so the payment is unconfirmed.
        ("preimage-mismatch", "INCONCLUSIVE", "receipt_mismatch"),
        ("receipt-mismatch", "INCONCLUSIVE", "receipt_mismatch"),
        # The server's own macaroon disagrees with the paid preimage.
        ("macaroon-mismatch", "INCOMPATIBLE", "preimage_mismatch"),
        # The macaroon match governs; the receipt disagreement is information.
        ("macaroon-match-receipt-mismatch", "FULFILLMENT_VERIFIED", "receipt_mismatch"),
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
    evidence, credential = evidence_for(name)
    report = l402_evidence.evaluate(evidence, credential)
    assert report["mode"] == "paid"
    assert report["classification"] == classification
    assert code in paid_codes(report)


# 6. The paid check proves preimage/payment-hash correspondence.
def test_matching_preimage_is_checked_against_the_receipt_hash():
    evidence, credential = evidence_for("fulfilled-2xx")
    report = l402_evidence.evaluate(evidence, credential)
    paid = report["paid_fulfillment"]
    assert paid["preimage_check"] == "matched"
    assert paid["hash_sources"] == [{"source": "wallet receipt", "payment_hash": SEED_1_HASH, "match": True}]


@pytest.mark.parametrize("prefix", ["", "L402 ", "LSAT ", "Authorization: L402 "])
def test_l402_token_forms_are_split_and_hashed(prefix):
    evidence, credential = evidence_for("fulfilled-2xx")
    report = l402_evidence.evaluate(evidence, f"{prefix}fixture-string-macaroon:{SEED_1_PREIMAGE}")
    assert report["paid_fulfillment"]["preimage_check"] == "matched"


def test_lightning_labs_macaroon_hash_is_compared_alongside_the_receipt():
    evidence, credential = evidence_for("fulfilled-2xx")
    macaroon = build_v2(lightning_labs_identifier(SEED_1_HASH), [])
    report = l402_evidence.evaluate(evidence, f"L402 {macaroon}:{SEED_1_PREIMAGE}")
    assert report["classification"] == "FULFILLMENT_VERIFIED"
    assert report["paid_fulfillment"]["hash_sources"] == [
        {"source": "macaroon identifier", "payment_hash": SEED_1_HASH, "match": True},
        {"source": "wallet receipt", "payment_hash": SEED_1_HASH, "match": True},
    ]


def test_an_opaque_token_names_the_receipt_as_the_hash_source_and_never_claims_the_invoice():
    evidence, credential = evidence_for("fulfilled-2xx")
    report = l402_evidence.evaluate(evidence, credential)
    assert report["classification"] == "FULFILLMENT_VERIFIED"
    assert report["paid_fulfillment"]["hash_source"] == "wallet receipt"
    assert "wallet receipt's payment hash" in report["summary"]
    assert "not to the invoice" in report["summary"]
    markdown = l402_report.to_markdown(report)
    assert "Hash source: the wallet receipt's payment hash" in markdown
    assert "not to the invoice" in markdown


def test_a_readable_macaroon_names_the_macaroon_identifier_as_the_hash_source():
    evidence, credential = evidence_for("fulfilled-2xx")
    macaroon = build_v2(lightning_labs_identifier(SEED_1_HASH), [])
    report = l402_evidence.evaluate(evidence, f"L402 {macaroon}:{SEED_1_PREIMAGE}")
    assert report["paid_fulfillment"]["hash_source"] == "macaroon identifier"
    assert "payment hash in the macaroon identifier" in report["summary"]
    assert "wallet receipt" not in report["summary"]
    assert "Hash source: the macaroon identifier's payment hash" in l402_report.to_markdown(report)


@pytest.mark.parametrize("status, classification", [(200, "MARKETPLACE_READY"), (500, "PAYMENT_COMPATIBLE")])
def test_every_confirmed_summary_names_the_hash_source(status, classification):
    evidence, credential = evidence_for("fulfilled-2xx", root_metadata_ok=True)
    evidence["tool_result"]["status_code"] = status
    report = l402_evidence.evaluate(evidence, credential)
    assert report["classification"] == classification
    assert "wallet receipt's payment hash" in report["summary"]


def test_without_a_credential_there_is_no_hash_source():
    evidence, _ = evidence_for("fulfilled-2xx")
    report = l402_evidence.evaluate(evidence, None)
    assert report["paid_fulfillment"]["hash_source"] is None
    assert "Hash source: none compared" in l402_report.to_markdown(report)


def test_lightning_labs_macaroon_alone_is_a_comparable_hash():
    evidence, credential = evidence_for("credential-present-no-comparable-hash")
    macaroon = build_v2(lightning_labs_identifier(SEED_1_HASH), [])
    report = l402_evidence.evaluate(evidence, f"L402 {macaroon}:{SEED_1_PREIMAGE}")
    assert report["paid_fulfillment"]["preimage_check"] == "matched"
    assert report["classification"] == "FULFILLMENT_VERIFIED"


def test_macaroon_bound_to_another_hash_is_a_mismatch():
    evidence, credential = evidence_for("fulfilled-2xx")
    macaroon = build_v2(lightning_labs_identifier(SEED_2_HASH), [])
    report = l402_evidence.evaluate(evidence, f"L402 {macaroon}:{SEED_1_PREIMAGE}")
    assert report["paid_fulfillment"]["preimage_check"] == "mismatch"
    assert report["classification"] == "INCOMPATIBLE"
    assert "preimage_mismatch" in paid_codes(report)


def test_receipt_only_mismatch_is_inconclusive_and_asks_for_the_right_receipt():
    evidence, credential = evidence_for("receipt-mismatch")
    report = l402_evidence.evaluate(evidence, credential)
    finding = next(f for f in report["findings"] if f["code"] == "receipt_mismatch")
    assert finding["severity"] == "warning"
    assert "preimage_mismatch" not in paid_codes(report)
    assert report["paid_fulfillment"]["preimage_check"] == "mismatch"
    assert report["paid_fulfillment"]["hash_sources"] == [
        {"source": "wallet receipt", "payment_hash": SEED_2_HASH, "match": False}]
    assert not any("SHA-256" in fix for fix in report["required_fixes"])
    assert any("receipt" in note and "does not pay again" in note for note in report["rerun"])


def test_macaroon_mismatch_is_incompatible_with_a_server_fix():
    evidence, credential = evidence_for("macaroon-mismatch")
    report = l402_evidence.evaluate(evidence, credential)
    assert report["classification"] == "INCOMPATIBLE"
    assert report["paid_fulfillment"]["hash_sources"][0] == {
        "source": "macaroon identifier", "payment_hash": SEED_2_HASH, "match": False}
    assert "receipt_mismatch" not in paid_codes(report)
    assert any("SHA-256" in fix for fix in report["required_fixes"])


def test_macaroon_and_receipt_both_disagreeing_is_incompatible():
    evidence, credential = evidence_for("macaroon-mismatch")
    evidence["payments"][0]["payment_hash"] = SEED_2_HASH
    report = l402_evidence.evaluate(evidence, credential)
    assert report["classification"] == "INCOMPATIBLE"
    assert "preimage_mismatch" in paid_codes(report)


def test_macaroon_match_governs_when_only_the_receipt_disagrees():
    evidence, credential = evidence_for("macaroon-match-receipt-mismatch", root_metadata_ok=True)
    report = l402_evidence.evaluate(evidence, credential)
    assert report["classification"] == "MARKETPLACE_READY"
    paid = report["paid_fulfillment"]
    assert paid["preimage_check"] == "matched"
    assert paid["hash_sources"] == [
        {"source": "macaroon identifier", "payment_hash": SEED_1_HASH, "match": True},
        {"source": "wallet receipt", "payment_hash": SEED_2_HASH, "match": False},
    ]
    finding = next(f for f in report["findings"] if f["code"] == "receipt_mismatch")
    assert finding["severity"] == "info"
    assert "preimage_mismatch" not in paid_codes(report)
    assert report["evidence"]["payment_hash"] == SEED_1_HASH


def test_credential_without_any_comparable_hash_is_inconclusive():
    evidence, credential = evidence_for("credential-present-no-comparable-hash")
    report = l402_evidence.evaluate(evidence, f"L402 fixture-string-macaroon:{SEED_1_PREIMAGE}")
    assert report["paid_fulfillment"]["preimage_check"] == "no_hash_source"
    assert report["paid_fulfillment"]["hash_sources"] == []
    assert report["classification"] == "INCONCLUSIVE"
    assert "no_hash_to_compare" in paid_codes(report)


def test_malformed_preimage_is_inconclusive():
    evidence, _ = evidence_for("fulfilled-2xx")
    report = l402_evidence.evaluate(evidence, "fixture-string-macaroon:not-hex")
    assert report["paid_fulfillment"]["preimage_check"] == "malformed"
    assert report["classification"] == "INCONCLUSIVE"


def test_bare_preimage_is_refused_with_a_clear_message():
    evidence, _ = evidence_for("fulfilled-2xx")
    report = l402_evidence.evaluate(evidence, SEED_1_PREIMAGE)
    assert report["paid_fulfillment"]["preimage_check"] == "no_macaroon"
    assert report["paid_fulfillment"]["hash_sources"] == []
    assert report["classification"] == "INCONCLUSIVE"
    message = next(f for f in report["findings"] if f["code"] == "preimage_unchecked")["message"]
    assert "bare preimage" in message and "<macaroon>:<preimage>" in message
    assert SEED_1_PREIMAGE not in json.dumps(report)


@pytest.mark.parametrize("credential", ["L402 fixture-string-macaroon:", "fixture-string-macaroon:  "])
def test_macaroon_with_an_empty_preimage_says_the_preimage_is_missing(credential):
    evidence, _ = evidence_for("fulfilled-2xx")
    report = l402_evidence.evaluate(evidence, credential)
    assert report["paid_fulfillment"]["preimage_check"] == "missing_preimage"
    message = next(f for f in report["findings"] if f["code"] == "preimage_unchecked")["message"]
    assert "preimage is missing" in message
    assert "no credential was piped" not in message


def test_uppercase_preimage_is_hashed_and_both_cases_are_scrubbed():
    evidence, _ = evidence_for("fulfilled-2xx")
    token = f"L402 Fixture-String-Macaroon:{SEED_1_PREIMAGE.upper()}"
    report = l402_evidence.evaluate(evidence, token)
    assert report["paid_fulfillment"]["preimage_check"] == "matched"
    secrets = l402_evidence.credential_secrets(token)
    assert {"Fixture-String-Macaroon", SEED_1_PREIMAGE, SEED_1_PREIMAGE.upper(),
            f"Fixture-String-Macaroon:{SEED_1_PREIMAGE.upper()}", token} <= secrets


def test_credential_secrets_never_holds_a_tiny_value():
    secrets = l402_evidence.credential_secrets("L402 m:a")
    assert all(len(s) >= 8 for s in secrets)
    assert "a" not in secrets and "m" not in secrets
    assert l402_evidence.credential_secrets(None) == set()


def test_short_bad_preimage_is_not_added_to_the_scrub_list():
    secrets = l402_evidence.credential_secrets("fixture-string-macaroon:abc")
    assert "abc" not in secrets
    assert "fixture-string-macaroon" in secrets
    assert "fixture-string-macaroon:abc" in secrets


@pytest.mark.parametrize("prefix", ["L402 ", "LSAT ", "Authorization: L402 "])
def test_a_credential_with_no_colon_adds_the_bare_macaroon_as_a_secret(prefix):
    secrets = l402_evidence.credential_secrets(f"{prefix}fixture-string-macaroon-only")
    assert "fixture-string-macaroon-only" in secrets


# Without the credential, a receipt is supporting evidence and never upgrades the class.
def test_receipt_without_credential_is_recorded_but_never_upgrades():
    evidence, credential = evidence_for("credential-absent-with-receipt", root_metadata_ok=True)
    assert credential is None
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
    evidence, credential = evidence_for("fulfilled-2xx")
    report = l402_evidence.evaluate(evidence, credential)
    assert report["classification"] == "FULFILLMENT_VERIFIED"
    assert report["evidence"]["statuses"] == [402, 200]
    assert report["evidence"]["payment_hash"] == SEED_1_HASH
    assert report["evidence"]["amount_sats"] == 1


def test_unmet_expectation_is_payment_compatible():
    evidence, credential = evidence_for("fulfilled-2xx")
    evidence["expected"]["content_type"] = "text/csv"
    report = l402_evidence.evaluate(evidence, credential)
    assert report["classification"] == "PAYMENT_COMPATIBLE"
    assert "expected_content_type" in next(f for f in report["findings"] if f["code"] == "unexpected_result")["message"]


def test_empty_body_on_a_get_misses_expectations():
    evidence, credential = evidence_for("fulfilled-2xx")
    evidence["tool_result"]["body_length"] = 0
    report = l402_evidence.evaluate(evidence, credential)
    assert report["classification"] == "PAYMENT_COMPATIBLE"
    assert "non_empty_body" in next(f for f in report["findings"] if f["code"] == "unexpected_result")["message"]


def test_head_request_does_not_need_a_body():
    evidence, credential = evidence_for("fulfilled-2xx")
    evidence["mode_a_report"]["target"]["method"] = "HEAD"
    evidence["tool_result"]["body_length"] = 0
    report = l402_evidence.evaluate(evidence, credential)
    assert report["classification"] == "FULFILLMENT_VERIFIED"
    assert "non_empty_body" not in {c["name"] for c in report["paid_fulfillment"]["expectations"]}


@pytest.mark.parametrize("checked, paid", [("GET", "get"), ("HEAD", "HEAD")])
def test_evidence_naming_the_checked_method_is_accepted(checked, paid):
    evidence, credential = evidence_for("fulfilled-2xx")
    evidence["mode_a_report"]["target"]["method"] = checked
    evidence["method"] = paid
    assert l402_evidence.evaluate(evidence, credential)["classification"] == "FULFILLMENT_VERIFIED"


@pytest.mark.parametrize("checked, paid", [("HEAD", "GET"), ("GET", "HEAD")])
def test_a_paid_call_with_another_method_is_refused(checked, paid):
    # A HEAD check paid as a GET (or the reverse) tested a different request than the report describes.
    evidence, credential = evidence_for("fulfilled-2xx")
    evidence["mode_a_report"]["target"]["method"] = checked
    evidence["method"] = paid
    with pytest.raises(l402_evidence.EvidenceError, match="same method and non-secret headers"):
        l402_evidence.evaluate(evidence, credential)


@pytest.mark.parametrize("value", ["", "G E T", 5, "fixture-string-method-name"])
def test_a_malformed_evidence_method_is_refused(value):
    evidence, credential = evidence_for("fulfilled-2xx")
    evidence["method"] = value
    with pytest.raises(l402_evidence.EvidenceError, match="evidence.method must be") as caught:
        l402_evidence.evaluate(evidence, credential)
    assert "fixture-string" not in str(caught.value)


@pytest.mark.parametrize("status, code", [(403, "paid_retry_rejected"), (500, "paid_retry_failed"), (501, "paid_retry_failed")])
def test_definitive_non_2xx_after_a_confirmed_payment_is_payment_compatible(status, code):
    evidence, credential = evidence_for("paid-retry-402")
    evidence["tool_result"]["status_code"] = status
    report = l402_evidence.evaluate(evidence, credential)
    assert report["classification"] == "PAYMENT_COMPATIBLE"
    assert code in paid_codes(report)


@pytest.mark.parametrize("status", [None, 408, 429, 502, 503, 504])
def test_no_answer_or_a_timeout_after_payment_is_inconclusive(status):
    evidence, credential = evidence_for("ambiguous-fulfillment")
    if status is not None:
        evidence["tool_result"]["status_code"] = status
    report = l402_evidence.evaluate(evidence, credential)
    assert report["classification"] == "INCONCLUSIVE"
    assert "ambiguous_fulfillment" in paid_codes(report)


# A status is never inferred: success without a status_code is not a 2xx.
def test_success_without_a_status_is_inconclusive_and_never_claims_200():
    evidence, credential = evidence_for("fulfilled-2xx", root_metadata_ok=True)
    del evidence["tool_result"]["status_code"]
    report = l402_evidence.evaluate(evidence, credential)
    assert report["classification"] == "INCONCLUSIVE"
    assert "ambiguous_fulfillment" in paid_codes(report)
    assert report["paid_fulfillment"]["status"] is None
    assert report["evidence"]["statuses"] == [402]
    assert "200" not in report["summary"]
    assert "returned 200" not in l402_report.to_markdown(report)


@pytest.mark.parametrize("field", ["body_length", "content_type"])
def test_unreported_result_fields_are_inconclusive_not_payment_compatible(field):
    evidence, credential = evidence_for("fulfilled-2xx")
    del evidence["tool_result"][field]
    report = l402_evidence.evaluate(evidence, credential)
    assert report["classification"] == "INCONCLUSIVE"
    assert "result_unreported" in paid_codes(report)
    assert "unexpected_result" not in paid_codes(report)


def test_a_definitive_miss_outranks_an_unreported_field():
    evidence, credential = evidence_for("fulfilled-2xx")
    del evidence["tool_result"]["body_length"]
    evidence["expected"]["content_type"] = "text/csv"
    report = l402_evidence.evaluate(evidence, credential)
    assert report["classification"] == "PAYMENT_COMPATIBLE"


def test_tool_and_receipt_amounts_that_disagree_are_inconclusive():
    evidence, credential = evidence_for("fulfilled-2xx", root_metadata_ok=True)
    evidence["tool_result"]["paid_sats"] = 3
    report = l402_evidence.evaluate(evidence, credential)
    assert report["classification"] == "INCONCLUSIVE"
    assert "paid_amount_mismatch" in paid_codes(report)
    assert report["paid_fulfillment"]["paid_sats"] == 3


def test_the_cap_holds_against_the_larger_of_tool_and_receipt_amounts():
    evidence, credential = evidence_for("fulfilled-2xx")
    evidence["cap_sats"] = 2
    evidence["tool_result"]["paid_sats"] = 5
    report = l402_evidence.evaluate(evidence, credential)
    assert report["classification"] == "INCONCLUSIVE"
    assert {"paid_over_cap", "paid_amount_mismatch"} <= paid_codes(report)


def test_two_payments_cap_the_result_at_inconclusive_even_when_everything_else_passes():
    evidence, credential = evidence_for("second-payment", root_metadata_ok=True)
    evidence["expected"] = {"status": 200, "content_type": "application/json"}
    report = l402_evidence.evaluate(evidence, credential)
    assert report["classification"] == "INCONCLUSIVE"
    assert report["paid_fulfillment"]["payments_recorded"] == 2
    assert report["paid_fulfillment"]["payment_hashes"] == [SEED_1_HASH, SEED_2_HASH]


# The quote's hash and the paid hash are compared as information, never as a finding.
@pytest.mark.parametrize("same", [False, True])
def test_quote_and_paid_hashes_are_compared_as_information_only(same):
    evidence, credential = evidence_for("credential-absent-with-receipt")
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
    evidence, credential = evidence_for("fulfilled-2xx", root_metadata_ok=True)
    report = l402_evidence.evaluate(evidence, credential)
    assert report["classification"] == "MARKETPLACE_READY"
    assert report["marketplace"]["listing_ready"] is True

    without_metadata, credential = evidence_for("fulfilled-2xx")
    assert l402_evidence.evaluate(without_metadata, credential)["classification"] == "FULFILLMENT_VERIFIED"

    unproven, _ = evidence_for("preimage-not-surfaced", root_metadata_ok=True)
    assert l402_evidence.evaluate(unproven, None)["classification"] == "INCONCLUSIVE"


def test_price_change_between_quote_and_payment_blocks_marketplace_ready():
    evidence, credential = evidence_for("fulfilled-2xx", root_metadata_ok=True)
    evidence["tool_result"]["paid_sats"] = 2
    evidence["payments"][0]["amount_sats"] = 2
    report = l402_evidence.evaluate(evidence, credential)
    assert report["classification"] == "FULFILLMENT_VERIFIED"
    gaps = next(f for f in report["findings"] if f["code"] == "marketplace_gaps")
    assert "stable_price" in gaps["message"]


def test_accepted_but_deferred_response_blocks_marketplace_ready():
    evidence, credential = evidence_for("fulfilled-2xx", root_metadata_ok=True)
    evidence["tool_result"]["status_code"] = 202
    del evidence["expected"]["status"]
    report = l402_evidence.evaluate(evidence, credential)
    assert report["classification"] == "FULFILLMENT_VERIFIED"
    gaps = next(f for f in report["findings"] if f["code"] == "marketplace_gaps")
    assert "synchronous_response" in gaps["message"]


# 8. Paid success then ambiguous fulfillment: INCONCLUSIVE, correlators kept, no repay.
def test_ambiguous_fulfillment_keeps_correlators_and_never_suggests_paying_again():
    evidence, credential = evidence_for("ambiguous-fulfillment")
    report = l402_evidence.evaluate(evidence, credential)
    assert report["classification"] == "INCONCLUSIVE"
    assert report["evidence"]["payment_hash"] == SEED_1_HASH
    assert report["evidence"]["amount_sats"] == 1
    text = l402_report.to_markdown(report)
    assert "do not pay again" in text.lower()
    assert "retry the payment" not in text.lower()


@pytest.mark.parametrize("name", sorted(p.stem for p in support.EVIDENCE.glob("*.json")
                                        if p.stem != "evidence-file-with-credential-key-refused"))
def test_no_report_ever_suggests_paying_again(name):
    evidence, credential = evidence_for(name)
    text = l402_report.to_markdown(l402_evidence.evaluate(evidence, credential)).lower()
    assert "retry the payment" not in text
    assert re.search(r"(?<!not )(?<!never )(?<!don't )pay again", text) is None
    assert "verified" not in text.replace("fulfillment_verified", "")


def test_a_paid_check_after_a_failed_read_only_check_is_inconclusive():
    evidence, credential = evidence_for("fulfilled-2xx")
    evidence["mode_a_report"] = support.run_fixture(support.load_fixture("synthetic-amountless-invoice"))[0]
    report = l402_evidence.evaluate(evidence, credential)
    assert report["classification"] == "INCONCLUSIVE"
    assert "paid_check_without_challenge" in paid_codes(report)


@pytest.mark.parametrize("key", ["preimage", "l402Token", "l402_token", "macaroon", "credential", "Authorization",
                                 "token", "PREIMAGE", "Macaroon", "l402-token", "L402-Token"])
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
    # fullmatch: a trailing newline is not a valid hash.
    ("payments", [{"amount_sats": 1, "status": "settled", "payment_hash": SEED_1_HASH + "\n"}]),
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
    evidence, credential = evidence_for("fulfilled-2xx")
    first = l402_evidence.evaluate(evidence, credential)
    again, _ = evidence_for("fulfilled-2xx")
    again["mode_a_report"] = first
    with pytest.raises(l402_evidence.EvidenceError):
        l402_evidence.evaluate(again, credential)


def test_paid_report_keeps_the_rerun_key_and_fills_the_paid_sections():
    evidence, credential = evidence_for("credential-absent-with-receipt")
    report = l402_evidence.evaluate(evidence, credential)
    assert isinstance(report["rerun"], list)
    assert any("--credential-stdin" in note for note in report["rerun"])
    assert report["paid_fulfillment"]["tested"] is True
    assert report["replay"]["tested"] is False
    markdown = l402_report.to_markdown(report)
    section = markdown.split("## Paid fulfillment", 1)[1].split("\n## ", 1)[0]
    assert "fixture-string-receipt-context" in section
    assert SEED_1_HASH in section


def test_paid_report_says_its_facts_are_agent_recorded():
    evidence, credential = evidence_for("fulfilled-2xx")
    report = l402_evidence.evaluate(evidence, credential)
    assert report["report_version"] == 1
    assert report["paid_fulfillment"]["evidence_source"] == "agent-recorded access_l402_resource result"
    text = l402_report.to_json(report)
    assert next(iter(json.loads(text))) == "report_version"
    assert "Evidence source: agent-recorded access_l402_resource result" in l402_report.to_markdown(report)


@pytest.mark.parametrize("timestamps, recorded_at, wanted", [
    (["2026-10-12T21:00:01.000Z"], "2026-10-12T21:05:00Z", "2026-10-12T21:00:01.000Z"),
    ([None], "2026-10-12T21:05:00Z", "2026-10-12T21:05:00Z"),
    ([None], None, None),
])
def test_paid_checked_at_prefers_the_receipt_then_the_recorded_time(timestamps, recorded_at, wanted):
    evidence, credential = evidence_for("fulfilled-2xx")
    for payment, stamp in zip(evidence["payments"], timestamps):
        if stamp:
            payment["timestamp"] = stamp
    if recorded_at:
        evidence["recorded_at"] = recorded_at
    report = l402_evidence.evaluate(evidence, credential)
    assert report["paid_fulfillment"]["paid_checked_at"] == wanted
    assert f"paid check at {wanted or 'unknown'}" in l402_report.to_markdown(report)


def test_paid_checked_at_is_the_latest_receipt_time():
    evidence, credential = evidence_for("multiple-payments")
    stamps = ["2026-10-12T21:00:09.000Z", "2026-10-12T21:00:01.000Z"]
    for payment, stamp in zip(evidence["payments"], stamps):
        payment["timestamp"] = stamp
    report = l402_evidence.evaluate(evidence, credential)
    assert report["paid_fulfillment"]["paid_checked_at"] == "2026-10-12T21:00:09.000Z"


def test_a_non_string_recorded_at_is_refused():
    evidence, credential = evidence_for("fulfilled-2xx")
    evidence["recorded_at"] = 1760302800
    with pytest.raises(l402_evidence.EvidenceError, match="evidence.recorded_at must be"):
        l402_evidence.evaluate(evidence, credential)


def test_paid_report_never_contains_the_credential():
    evidence, credential = evidence_for("fulfilled-2xx")
    token = f"L402 fixture-string-macaroon:{SEED_1_PREIMAGE}"
    report = l402_evidence.evaluate(evidence, token)
    secrets = {token, "fixture-string-macaroon", SEED_1_PREIMAGE}
    for text in (l402_report.to_json(report, secrets), l402_report.to_markdown(report, secrets)):
        assert SEED_1_PREIMAGE not in text
        assert "fixture-string-macaroon" not in text
        assert SEED_1_HASH in text


def test_the_report_dict_itself_holds_no_credential_even_unscrubbed():
    evidence, credential = evidence_for("fulfilled-2xx")
    macaroon = build_v2(lightning_labs_identifier(SEED_1_HASH), [])
    token = f"L402 {macaroon}:{SEED_1_PREIMAGE}"
    report = l402_evidence.evaluate(evidence, token)
    raw = json.dumps(report)
    assert SEED_1_PREIMAGE not in raw
    assert macaroon not in raw
    assert SEED_1_HASH in raw
    secrets = l402_evidence.credential_secrets(token)
    assert {SEED_1_PREIMAGE, macaroon} <= secrets
    assert SEED_1_PREIMAGE not in l402_report.to_markdown(report, secrets)


def test_evidence_errors_never_carry_the_credential():
    evidence, credential = evidence_for("fulfilled-2xx")
    evidence["cap_sats"] = 0
    with pytest.raises(l402_evidence.EvidenceError) as caught:
        l402_evidence.evaluate(evidence, credential)
    assert SEED_1_PREIMAGE not in str(caught.value)
    assert OPAQUE_MACAROON not in str(caught.value)


def emitted_codes() -> set[str]:
    source = (support.SCRIPTS / "l402_evidence.py").read_text(encoding="utf-8")
    return set(re.findall(r'Finding\(\s*"([a-z0-9_]+)"', source))


def test_skill_md_documents_every_paid_finding_code_the_module_emits():
    codes = emitted_codes()
    assert {"preimage_unchecked", "receipt_mismatch", "result_unreported", "paid_amount_mismatch"} <= codes
    text = (support.SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    section = text.split("Paid-check finding codes", 1)[1].split("\n### ", 1)[0]
    missing = sorted(code for code in codes | {"stable_price", "synchronous_response"} if f"`{code}`" not in section)
    assert missing == []
