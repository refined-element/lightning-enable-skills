"""Guards for the repo-level ``references/`` notes that several skills share.

``references/l402-verification-levels.md`` is the single source of the five
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
    "INCOMPATIBLE",
    "INCONCLUSIVE",
)
CLASSIFICATION_PATTERN = r"\b(?:[A-Z]+_)+(?:COMPATIBLE|VERIFIED|READY)\b|\bINCOMPATIBLE\b|\bINCONCLUSIVE\b"
# The optional marketplace profile section, in the shared reference and in the
# report skill. Profile statuses and the retired MARKETPLACE_READY name may
# appear only inside it.
PROFILES_HEADING = "## Optional marketplace profiles"
CUSTODY = "Lightning Enable does not hold funds; the payment provider facilitates custody and settlement."


def section_bounds(body: str, heading: str) -> tuple[int, int] | None:
    """(start, end) of the level-2 ``heading`` section in ``body``, or None."""
    start = body.find(f"\n{heading}\n")
    if start < 0:
        return None
    end = body.find("\n## ", start + 1)
    return start, (end if end >= 0 else len(body))


def without_section(body: str, heading: str) -> str:
    bounds = section_bounds(body, heading)
    return body if bounds is None else body[:bounds[0]] + body[bounds[1]:]


def section_text(body: str, heading: str) -> str:
    bounds = section_bounds(body, heading)
    return "" if bounds is None else body[bounds[0]:bounds[1]]


def text() -> str:
    return REFERENCE.read_text(encoding="utf-8")


def test_reference_exists():
    assert REFERENCE.is_file()


def test_reference_names_exactly_the_five_classifications():
    body = text()
    for name in CLASSIFICATIONS:
        assert f"`{name}`" in body
    core = without_section(body, PROFILES_HEADING)
    named = set(re.findall(CLASSIFICATION_PATTERN, core))
    assert named == set(CLASSIFICATIONS)
    assert "MARKETPLACE_READY" not in core


def test_fulfillment_verified_is_the_top_classification():
    body = " ".join(text().split())
    assert "`FULFILLMENT_VERIFIED` is the top classification" in body


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
