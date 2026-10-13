"""Text guards for the optional Amazap seller handoff.

The three seller skills (``producer-setup``, ``create-l402-proxy``, and
``l402-server-integration``) end with an optional step: after the self-test,
offer to draft an Amazap listing that the human reviews and submits. The full
rules live in one shared note, ``references/amazap-marketplace.md``; each skill
carries a compact step that states the readiness gate and the approval boundary
and links the note's Seller handoff section by its GitHub URL, because a skill
installs by copying one folder.

Like the rest of the suite these are text guards; nothing opens a network
connection. They hold the spec's seller-handoff acceptance tests in guard form:

* the gate rejects a private or non-HTTPS URL, a ``200`` to an unpaid request,
  and a ``400``/``415``/``422`` to a bodyless request;
* a read-only result is labeled "challenge-compatible, fulfillment unverified",
  and only ``FULFILLMENT_VERIFIED`` or ``MARKETPLACE_READY`` unlocks "ready";
* the agent drafts but never publishes, and never invents a contact email;
* nothing is called listed or live before it is read back, and "listed" is kept
  apart from "verified paid delivery";
* the seller price and Amazap's all-in price are presented separately;
* on ``api.lightningenable.com`` the human supplies the listing fields by hand;
* a price change means re-running Amazap's checks.

Amazap's margin, floor, limits, and counts are another company's live values,
so they may appear only under the reference's dated observation heading.
"""
import re
from pathlib import Path

import pytest

import test_skill_metadata
import test_tool_arguments_surface
import test_tool_surface
from test_shared_references import CLASSIFICATIONS, CUSTODY

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIR = REPO_ROOT / "skills"
REFERENCE = REPO_ROOT / "references" / "amazap-marketplace.md"
REFERENCE_URL = (
    "https://github.com/refined-element/lightning-enable-skills/blob/main/"
    "references/amazap-marketplace.md#seller-handoff"
)
LIVE_PAGES = (
    "https://amazap.com/sell",
    "https://amazap.com/sell/guide/list-l402-endpoint-on-amazap",
    "https://amazap.com/llms.txt",
)
READ_BACK = "GET https://amazap.com/api/products/<slug>"
DATED_HEADING = "## Observed on 2026-10-12"
REFERENCE_SECTIONS = (
    "## Amazap facts are external",
    "## Live pages",
    "## Discovery versus purchase",
    "## Two wallets",
    "## Merchant of record and the all-in price",
    "## Verification terminology",
    "## Seller handoff",
    "### Readiness gate",
    "### Handoff flow",
    "### Human approval boundary",
    "### Listing-copy template",
    "### Post-listing verification",
    DATED_HEADING,
    "## Custody",
)

# The seller skills whose Amazap step is guarded; Tasks 2 to 4 add one each.
SELLER_SKILLS: tuple[str, ...] = ("producer-setup",)
# The seller skills whose endpoint is a proxy on api.lightningenable.com.
PROXY_SKILLS: tuple[str, ...] = ("producer-setup",)
HANDOFF_TARGETS = ("reference", *SELLER_SKILLS)

STEP_HEADING = re.compile(r"^### (\d+)\. Optional: list on Amazap[ \t]*$", re.MULTILINE)
HAND_OFF_HEADING = re.compile(r"^### (\d+)\. Hand off[ \t]*$", re.MULTILINE)

# Present in the reference and in every skill's step (spec section 20).
GATE_RULES = (
    "non-HTTPS",
    "`200` to an unpaid request",
    "`400`, `415`, or `422`",
    "challenge-compatible, fulfillment unverified",
    "`FULFILLMENT_VERIFIED`",
    "`list_my_endpoint`",
    "example parameters by hand",
    "separately",
    "all-in",
    "re-run Amazap's checks",
    "never twice",
    "listed or live until",
    READ_BACK,
    "`hidden`, `listingState`, and `healthStatus`",
    "verified paid delivery",
    "human enters",
)
APPROVAL_BOUNDARY = (
    "submit the listing",
    "accept seller terms",
    "provide or infer a contact email",
    "opt into announcements",
    "publish a Nostr handle",
    "change the endpoint's price",
    "claim a commercial relationship",
)
READINESS_ITEMS = (
    "public HTTPS",
    "`402 Payment Required`",
    "`L402` or `LSAT`",
    "priced BOLT11 invoice",
    "no body",
    "8 seconds",
    "safe example value",
    "one bounded real payment",
    "`2xx`",
    "Replay behavior",
    "secrets",
    "title, description, category, and price",
    "`GET` or `HEAD`",
    "`preimage_unchecked`",
)
LISTING_FIELDS = (
    "**Name:**",
    "**Description:**",
    "**Category:**",
    "**Method and endpoint:**",
    "**Example parameters:**",
    "**Price:**",
    "**Failure behavior:**",
)

EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
HYPE = re.compile(r"\b(?:revolutionary|autonomous|instant|real-time)\b|\bany API\b", re.IGNORECASE)
BANNED_WORDS = ("non-custodial", "noncustodial", "self-custody", "trustless", "decentralized")
# An affirmative listing claim: "is listed", "is now live", "are live".
LISTING_CLAIM = re.compile(r"\b(?:is|are|was|now)\s+(?:now\s+)?(?:listed|live)\b", re.IGNORECASE)
NEGATIONS = ("never", "not ", "until", "before", "n't")
# Lowercase "verified" outside FULFILLMENT_VERIFIED, "unverified", and the
# phrase "verified paid delivery".
LOOSE_VERIFIED = re.compile(r"(?<![A-Za-z_])verified\b(?! paid delivery)")
CLASSIFICATION_NAME = re.compile(
    r"\b(?:[A-Z]+_)+(?:COMPATIBLE|VERIFIED|READY)\b|\bINCOMPATIBLE\b|\bINCONCLUSIVE\b"
)
# Amazap's margin, floor, limits, and counts: dated-note material only.
AMAZAP_FIGURE = re.compile(
    r"\bbps\b|\d\s*%|\bsat floor\b|\bsats? per (?:call|day|session)\b"
    r"|\b\d{1,3}(?:,\d{3})+ product pages\b",
    re.IGNORECASE,
)
EM_DASH = "\u2014"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def flat(text: str) -> str:
    return " ".join(text.split())


def section_at(text: str, start: int) -> str:
    """The heading that starts at ``start`` and its body, up to the next heading
    of the same or a higher level."""
    level = len(text[start:].split(" ", 1)[0])
    rest = text[start + level:]
    end = re.search(rf"^#{{1,{level}}} ", rest, re.MULTILINE)
    return text[start:start + level + end.start()] if end else text[start:]


def amazap_step(skill: str) -> str:
    text = read(SKILLS_DIR / skill / "SKILL.md")
    match = STEP_HEADING.search(text)
    assert match, f"skills/{skill}/SKILL.md has no '### N. Optional: list on Amazap' step"
    return section_at(text, match.start())


def readme_step(skill: str) -> str:
    text = read(SKILLS_DIR / skill / "README.md")
    start = text.find("\n## Optional: list on Amazap\n")
    assert start >= 0, f"skills/{skill}/README.md has no '## Optional: list on Amazap' section"
    return section_at(text, start + 1)


def reference_section(heading: str) -> str:
    text = read(REFERENCE)
    start = text.find(f"\n{heading}\n")
    assert start >= 0, f"references/amazap-marketplace.md has no '{heading}' heading"
    return section_at(text, start + 1)


def undated_reference() -> str:
    return read(REFERENCE).replace(reference_section(DATED_HEADING), "")


def handoff_text(target: str) -> str:
    """Flat text of the reference (without its dated note) or of one skill's step."""
    return flat(undated_reference() if target == "reference" else amazap_step(target))


def raw_handoff_text(target: str) -> str:
    return read(REFERENCE) if target == "reference" else amazap_step(target)


# --- The reference itself -------------------------------------------------


def test_reference_exists():
    assert REFERENCE.is_file()


def test_reference_is_scanned_by_the_repo_guards():
    assert REFERENCE in test_skill_metadata.markdown_files()
    assert REFERENCE in test_tool_surface.scanned_files()
    assert REFERENCE in test_tool_arguments_surface.skill_docs()


def test_reference_has_every_section_in_order():
    text = read(REFERENCE)
    positions = []
    for heading in REFERENCE_SECTIONS:
        index = text.find(f"\n{heading}\n")
        assert index >= 0, f"missing heading: {heading}"
        positions.append(index)
    assert positions == sorted(positions), "the reference's sections are out of order"


def test_reference_links_the_live_pages():
    text = read(REFERENCE)
    missing = [url for url in LIVE_PAGES if url not in text]
    assert not missing, f"the reference must link the live pages: {missing}"


def test_reference_links_the_verification_levels():
    assert "(l402-verification-levels.md)" in read(REFERENCE)


def test_reference_readiness_gate_lists_every_item():
    gate = flat(reference_section("### Readiness gate"))
    missing = [item for item in READINESS_ITEMS if item not in gate]
    assert not missing, f"the readiness gate is missing: {missing}"


def test_reference_listing_template_has_every_field():
    template = reference_section("### Listing-copy template")
    missing = [field for field in LISTING_FIELDS if field not in template]
    assert not missing, f"the listing-copy template is missing: {missing}"


def test_reference_hype_words_appear_only_on_the_avoid_line():
    offending = [
        line for line in read(REFERENCE).splitlines()
        if HYPE.search(line) and not line.startswith("- **Avoid**")
    ]
    assert not offending, f"hype words outside the avoid line: {offending}"


def test_reference_carries_a_dated_observation_note():
    dated = reference_section(DATED_HEADING)
    assert "A snapshot, not a rule." in dated
    assert AMAZAP_FIGURE.search(dated), "the dated note should hold the observed figures"


def test_reference_describes_the_relationship_as_collaboration():
    text = flat(read(REFERENCE))
    assert "collaboration or ecosystem support" in text
    for match in re.finditer(r"partner", text, flags=re.IGNORECASE):
        before = text[max(0, match.start() - 80):match.start()].lower()
        assert "never" in before or "not " in before, "partnership is only ever negated"


def test_reference_checks_for_an_existing_row_first():
    text = flat(reference_section("### Handoff flow"))
    for phrase in ("402 Index", "sitemap.xml", "Never draft a duplicate listing"):
        assert phrase in text, phrase


def test_reference_states_the_two_wallet_rule():
    assert "`budget` and `get_balance` don't see Amazap credits" in flat(read(REFERENCE))


def test_reference_sends_proxy_sellers_to_fill_fields_by_hand():
    text = flat(reference_section("### Handoff flow"))
    assert "`api.lightningenable.com`" in text
    assert "title, description, category, and example parameters by hand" in text


# --- Rules shared by the reference and every skill's step ------------------


@pytest.mark.parametrize("target", HANDOFF_TARGETS)
def test_handoff_states_the_gate_and_its_labels(target):
    text = handoff_text(target)
    missing = [rule for rule in GATE_RULES if rule not in text]
    assert not missing, f"{target} is missing: {missing}"


@pytest.mark.parametrize("target", HANDOFF_TARGETS)
def test_handoff_states_the_approval_boundary(target):
    text = handoff_text(target)
    missing = [rule for rule in APPROVAL_BOUNDARY if rule not in text]
    assert not missing, f"{target} is missing: {missing}"


@pytest.mark.parametrize("target", HANDOFF_TARGETS)
def test_handoff_claims_no_listing_before_read_back(target):
    text = handoff_text(target)
    for match in LISTING_CLAIM.finditer(text):
        before = text[max(0, match.start() - 80):match.start()].lower()
        assert any(word in before for word in NEGATIONS), (
            f"{target}: '{match.group(0)}' reads as a listing claim; say it only "
            "after the product page or API row is read back"
        )


@pytest.mark.parametrize("target", HANDOFF_TARGETS)
def test_handoff_uses_verified_only_for_paid_delivery(target):
    hits = LOOSE_VERIFIED.findall(handoff_text(target))
    assert not hits, f"{target}: 'verified' only in 'verified paid delivery' or a classification"


@pytest.mark.parametrize("target", HANDOFF_TARGETS)
def test_handoff_invents_no_contact_email(target):
    hits = EMAIL.findall(raw_handoff_text(target))
    assert not hits, f"{target} writes an email address: {hits}; the human enters the contact email"


@pytest.mark.parametrize("target", HANDOFF_TARGETS)
def test_handoff_carries_the_custody_sentence(target):
    assert CUSTODY in handoff_text(target)


@pytest.mark.parametrize("target", HANDOFF_TARGETS)
def test_handoff_avoids_banned_words(target):
    text = handoff_text(target).lower()
    hits = [word for word in BANNED_WORDS if word in text]
    assert not hits, f"{target} uses {hits}"


@pytest.mark.parametrize("target", HANDOFF_TARGETS)
def test_handoff_names_only_the_six_classifications(target):
    named = set(CLASSIFICATION_NAME.findall(handoff_text(target)))
    assert named <= set(CLASSIFICATIONS), f"{target} names {sorted(named - set(CLASSIFICATIONS))}"
    assert "FULFILLMENT_VERIFIED" in named


@pytest.mark.parametrize("target", HANDOFF_TARGETS)
def test_handoff_hard_codes_no_amazap_figures(target):
    hits = AMAZAP_FIGURE.findall(handoff_text(target))
    assert not hits, (
        f"{target} hard-codes {hits}; Amazap's margin, floor, limits, and counts go "
        f"only under '{DATED_HEADING}'"
    )


@pytest.mark.parametrize("target", HANDOFF_TARGETS)
def test_handoff_has_no_em_dashes(target):
    assert EM_DASH not in raw_handoff_text(target), f"{target} uses an em-dash"


# --- Each seller skill's step and README -----------------------------------


@pytest.mark.parametrize("skill", SELLER_SKILLS)
def test_step_comes_right_after_the_hand_off(skill):
    text = read(SKILLS_DIR / skill / "SKILL.md")
    hand_off = HAND_OFF_HEADING.search(text)
    step = STEP_HEADING.search(text)
    assert hand_off and step, f"{skill} needs both a Hand off step and the Amazap step"
    assert hand_off.start() < step.start()
    assert int(step.group(1)) == int(hand_off.group(1)) + 1, (
        f"{skill}: the Amazap step should be numbered right after Hand off"
    )


@pytest.mark.parametrize("skill", SELLER_SKILLS)
def test_step_links_the_reference_the_seller_page_and_the_report(skill):
    step = amazap_step(skill)
    assert REFERENCE_URL in step, "link the reference by its GitHub URL; skills install one folder"
    assert "https://amazap.com/sell" in step
    assert "(../l402-compatibility-report/)" in step


@pytest.mark.parametrize("skill", SELLER_SKILLS)
def test_step_runs_the_read_only_check_and_pays_at_most_once(skill):
    step = flat(amazap_step(skill))
    assert "python scripts/l402_check.py <url> --json" in step
    assert "never twice" in step
    assert "`GET` or `HEAD` only" in step


@pytest.mark.parametrize("skill", SELLER_SKILLS)
def test_step_names_amazap_tools_only_when_the_host_lists_them(skill):
    step = flat(amazap_step(skill))
    assert "`list_my_endpoint`" in step and "when the host lists it" in step


@pytest.mark.parametrize("skill", SELLER_SKILLS)
def test_step_has_no_hype_words(skill):
    hits = HYPE.findall(amazap_step(skill))
    assert not hits, f"{skill} uses {hits}"


@pytest.mark.parametrize("skill", PROXY_SKILLS)
def test_proxy_steps_send_the_seller_to_fill_the_fields_by_hand(skill):
    step = flat(amazap_step(skill))
    assert "`api.lightningenable.com`" in step
    assert "title, description, category, and example parameters by hand" in step


@pytest.mark.parametrize("skill", SELLER_SKILLS)
def test_readme_describes_the_optional_step(skill):
    raw = readme_step(skill)
    text = flat(raw)
    for phrase in (REFERENCE_URL, CUSTODY, "contact email", "submit it yourself",
                   "(../l402-compatibility-report/)"):
        assert phrase in text, f"{skill}/README.md is missing {phrase!r}"
    assert EM_DASH not in raw
    assert not EMAIL.findall(raw)
    for match in LISTING_CLAIM.finditer(text):
        before = text[max(0, match.start() - 80):match.start()].lower()
        assert any(word in before for word in NEGATIONS), match.group(0)
