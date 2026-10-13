"""Guards for the repo-level ``references/`` notes that several skills share.

``references/l402-verification-levels.md`` is the single source of the six
classifications, the redaction rules, and the ambiguous-payment rule. It sits
outside ``skills/``, so these tests also make sure the existing custody, KYC,
and tool-name guards scan it.
"""
import re
from pathlib import Path

import test_skill_metadata
import test_tool_arguments_surface
import test_tool_surface

REPO_ROOT = Path(__file__).resolve().parent.parent
REFERENCE = REPO_ROOT / "references" / "l402-verification-levels.md"
CLASSIFICATIONS = (
    "CHALLENGE_COMPATIBLE",
    "PAYMENT_COMPATIBLE",
    "FULFILLMENT_VERIFIED",
    "MARKETPLACE_READY",
    "INCOMPATIBLE",
    "INCONCLUSIVE",
)
CUSTODY = "Lightning Enable does not hold funds; the payment provider facilitates custody and settlement."


def text() -> str:
    return REFERENCE.read_text(encoding="utf-8")


def test_reference_exists():
    assert REFERENCE.is_file()


def test_reference_names_exactly_the_six_classifications():
    body = text()
    for name in CLASSIFICATIONS:
        assert f"`{name}`" in body
    named = set(re.findall(r"\b(?:[A-Z]+_)+(?:COMPATIBLE|VERIFIED|READY)\b|\bINCOMPATIBLE\b|\bINCONCLUSIVE\b", body))
    assert named == set(CLASSIFICATIONS)


def test_reference_covers_redaction_ambiguity_and_schemes():
    body = " ".join(text().split())
    for phrase in (
        "invoice strings",
        "preimages",
        "macaroons or tokens",
        "NWC connection strings",
        "Never start a replacement payment while a payment is pending",
        "never normalize it to L402",
        "Several schemes in one response are normal",
        "not externally verifiable",
    ):
        assert phrase in body, phrase


def test_reference_carries_the_custody_sentence():
    assert CUSTODY in " ".join(text().split())


def test_l402_verified_appears_only_as_a_prohibition():
    body = " ".join(text().split())
    for match in re.finditer(r"L402 verified", body, flags=re.IGNORECASE):
        assert "never" in body[max(0, match.start() - 60):match.start()].lower()


def test_shared_references_are_covered_by_the_repo_guards():
    assert REFERENCE in test_skill_metadata.markdown_files()
    assert REFERENCE in test_tool_surface.scanned_files()
    assert REFERENCE in test_tool_arguments_surface.skill_docs()
