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
  and only ``FULFILLMENT_VERIFIED`` unlocks "ready";
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
SELLER_SKILLS: tuple[str, ...] = ("producer-setup", "create-l402-proxy", "l402-server-integration")
# The seller skills whose endpoint is a proxy on api.lightningenable.com.
PROXY_SKILLS: tuple[str, ...] = ("producer-setup", "create-l402-proxy")
# The seller skills whose API runs the L402 middleware on its own host.
NATIVE_SKILLS: tuple[str, ...] = ("l402-server-integration",)
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
def test_handoff_names_only_the_five_classifications(target):
    named = set(CLASSIFICATION_NAME.findall(handoff_text(target)))
    assert named <= set(CLASSIFICATIONS), f"{target} names {sorted(named - set(CLASSIFICATIONS))}"
    assert "FULFILLMENT_VERIFIED" in named
    assert "MARKETPLACE_READY" not in raw_handoff_text(target)


@pytest.mark.parametrize("target", HANDOFF_TARGETS)
def test_handoff_hard_codes_no_amazap_figures(target):
    hits = AMAZAP_FIGURE.findall(handoff_text(target))
    assert not hits, (
        f"{target} hard-codes {hits}; Amazap's margin, floor, limits, and counts go "
        f"only under '{DATED_HEADING}'"
    )


@pytest.mark.parametrize("target", HANDOFF_TARGETS)
def test_handoff_counts_a_pay_l402_challenge_payment_as_paid(target):
    text = handoff_text(target)
    for phrase in ("pay_l402_challenge", "counts as paid", "does not pay again"):
        assert phrase in text, f"{target} is missing {phrase!r}"


@pytest.mark.parametrize("target", HANDOFF_TARGETS)
@pytest.mark.parametrize("phrase", (
    "either wallet",
    # "by hand" alone also matches "example parameters by hand".
    "made by hand, outside both tools",
    "a wallet that can pay this endpoint",
))
def test_handoff_states_the_mirrored_payment_rules(target, phrase):
    assert phrase in handoff_text(target), f"{target} is missing {phrase!r}"


# Only proxies share a host; an API on its own domain owns its host.
@pytest.mark.parametrize("target", ("reference", *PROXY_SKILLS))
def test_proxy_handoff_matches_rows_by_url_not_the_host_alone(target):
    assert "not the host alone" in handoff_text(target), f"{target} is missing 'not the host alone'"


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
@pytest.mark.parametrize("phrase", (
    "Never draft a duplicate",
    "before any paid gate",
    "No answer means no",
    "hidden: false",
))
def test_step_checks_the_row_asks_first_and_reads_back_visibility(skill, phrase):
    assert phrase in flat(amazap_step(skill)), f"{skill} is missing {phrase!r}"


@pytest.mark.parametrize("skill", PROXY_SKILLS)
def test_proxy_steps_match_rows_by_endpoint_url(skill):
    assert "match the full endpoint URL the row stores" in flat(amazap_step(skill))


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


@pytest.mark.parametrize("skill", SELLER_SKILLS)
@pytest.mark.parametrize("phrase", (
    "with the same method",
    "`--mode-a mode-a.json`",
    "token piped on stdin",
    "If that token is gone",
    "with a different method",
    "Python MCP server",
))
def test_step_reuses_a_self_test_payment_instead_of_paying_again(skill, phrase):
    assert phrase in flat(amazap_step(skill)), f"{skill} is missing {phrase!r}"


@pytest.mark.parametrize("skill", SELLER_SKILLS)
def test_step_runs_the_gate_before_list_my_endpoint(skill):
    step = flat(amazap_step(skill))
    tool = step.find("`list_my_endpoint`")
    assert tool >= 0, f"{skill} never names `list_my_endpoint`"
    for gate_text in ("**Gate.**", "python scripts/l402_check.py"):
        gate = step.find(gate_text)
        assert 0 <= gate < tool, f"{skill}: {gate_text!r} must come before `list_my_endpoint`"
    draft = step.find("**Draft, never publish.** Only once the gate passes")
    assert draft >= 0 and draft < tool, f"{skill}: the draft bullet must open with 'Only once the gate passes'"


def test_native_step_points_the_prefill_at_the_apis_own_host_root():
    step = flat(amazap_step("l402-server-integration"))
    assert "at the root of the API's own host" in step
    assert "A test against `localhost` doesn't count." in step


@pytest.mark.parametrize("skill", NATIVE_SKILLS)
def test_native_step_carries_no_proxy_only_rule(skill):
    step = flat(amazap_step(skill))
    assert "before body validation" in step
    # Proxy-only rules: an API on its own domain owns its host and its host root.
    for phrase in ("not the host alone", "`api.lightningenable.com`"):
        assert phrase not in step, f"{skill} carries the proxy-only rule {phrase!r}"


ROOT_README = REPO_ROOT / "README.md"


def test_root_readme_mentions_the_step_in_a_sentence_not_a_row():
    text = read(ROOT_README)
    assert "(references/amazap-marketplace.md)" in text
    assert "https://amazap.com/sell" in text
    # discover-paid-apis searches Amazap, so its row names Amazap; no other row may.
    rows = [
        line for line in text.splitlines()
        if line.startswith("|") and "amazap" in line.lower()
        and "(skills/discover-paid-apis/)" not in line
    ]
    assert not rows, f"Amazap is an optional seller step, not a skill; no table row: {rows}"


def test_root_readme_offers_the_step_after_any_self_test_for_the_human_to_submit():
    text = flat(read(ROOT_README))
    assert "After the self-test, `producer-setup`" in text
    assert "After a paid self-test" not in text, "the step follows any self-test, paid or not"
    assert "review and submit yourself" in text


# --- Final-review guards ---------------------------------------------------

READ_ONLY_COMMAND = re.compile(r"`python scripts/l402_check\.py <url>[^`]*`")
NOT_READY_UNTIL_PAID = "do not offer the listing as ready until the paid check below lifts it"
FULL_READY_CONDITION = (
    "and only once example parameters are known, replay behavior is understood, "
    "no error or output exposes a secret, and the human has chosen title, "
    "description, category, and price"
)
PAY_ONCE_OPENING = "made no payment for this endpoint by any means"
PAY_ONCE_OTHERWISE = "otherwise the cases below apply and the agent never pays again"
SUBMITTING_PUBLISHES = re.compile(
    r"Submitting (?:the form )?publishes the listing automatically once Amazap's checks pass"
)
REPORT_URL = (
    "https://github.com/refined-element/lightning-enable-skills/tree/main/"
    "skills/l402-compatibility-report"
)


@pytest.mark.parametrize("target", HANDOFF_TARGETS)
def test_handoff_read_only_command_carries_max_sats(target):
    commands = READ_ONLY_COMMAND.findall(handoff_text(target))
    assert commands, f"{target} never shows the read-only command"
    missing = [command for command in commands if "--max-sats <cap>" not in command]
    assert not missing, f"{target}: the paid check needs a capped read-only report: {missing}"


@pytest.mark.parametrize("target", HANDOFF_TARGETS)
def test_handoff_challenge_compatible_waits_for_the_paid_check(target):
    text = handoff_text(target)
    assert NOT_READY_UNTIL_PAID in text, f"{target} is missing {NOT_READY_UNTIL_PAID!r}"
    # The read-only check returns CHALLENGE_COMPATIBLE for a correct endpoint,
    # so stopping there would skip the paid check entirely.
    assert 'fulfillment unverified" and stop' not in text, f"{target} stops before the paid check"


@pytest.mark.parametrize("skill", SELLER_SKILLS)
def test_step_ready_condition_names_the_whole_gate(skill):
    assert FULL_READY_CONDITION in flat(amazap_step(skill)), (
        f"{skill}: FULFILLMENT_VERIFIED alone covers neither replay nor secrets"
    )


@pytest.mark.parametrize("target", HANDOFF_TARGETS)
def test_handoff_pay_once_opens_with_any_payment_by_any_means(target):
    text = handoff_text(target)
    for phrase in (PAY_ONCE_OPENING, PAY_ONCE_OTHERWISE):
        assert phrase in text, f"{target} is missing {phrase!r}"
    # "did not pay this exact URL" is true after a pay_l402_challenge, by-hand,
    # or from-code payment, and would invite a second payment.
    for stale in ("did not pay this exact", "did not already pay"):
        assert stale not in text, f"{target} still opens pay-once with {stale!r}"
    assert text.find(PAY_ONCE_OPENING) < text.find("If that token is gone")


@pytest.mark.parametrize("target", HANDOFF_TARGETS)
def test_handoff_says_a_testnet_payment_is_not_a_payment_for_the_gate(target):
    text = handoff_text(target)
    # A testnet payment moved no real money for this endpoint: it is not reuse
    # evidence, and it doesn't use up the one mainnet paid check.
    assert "(a testnet invoice doesn't count)" in text, target
    start = text.find("A self-test payment of a testnet invoice")
    assert start >= 0, f"{target} has no testnet sentence"
    sentence = text[start:text.find(". A ", start) + 1]
    for phrase in ("neither reuse evidence nor a payment for the gate",
                   "run the paid check once, with the human's yes"):
        assert phrase in sentence, f"{target}: the testnet sentence is missing {phrase!r}"
    assert "does not pay again" not in sentence, f"{target}: a testnet payment must not end the run"


@pytest.mark.parametrize("target", HANDOFF_TARGETS)
def test_handoff_without_the_report_skill_is_not_ready(target):
    text = handoff_text(target)
    assert "`l402-compatibility-report` is not installed, the listing is not ready" in text, target
    assert REPORT_URL in text, f"{target} must give the report skill's GitHub URL"


@pytest.mark.parametrize("target", HANDOFF_TARGETS)
def test_handoff_says_submitting_publishes(target):
    assert SUBMITTING_PUBLISHES.search(handoff_text(target)), f"{target} must say submitting publishes"


@pytest.mark.parametrize("skill", SELLER_SKILLS)
def test_readme_says_submitting_publishes_and_re_runs_after_a_price_change(skill):
    text = flat(readme_step(skill))
    for phrase in ("submitting publishes the listing once Amazap's checks pass",
                   "After any price change", "re-run Amazap's checks"):
        assert phrase in text, f"{skill}/README.md is missing {phrase!r}"


@pytest.mark.parametrize("skill", SELLER_SKILLS)
def test_step_asks_before_the_gate(skill):
    step = flat(amazap_step(skill))
    ask = step.find("**Ask first.**")
    gate = step.find("**Gate.**")
    assert 0 <= ask < gate, f"{skill}: ask about Amazap before any paid gate check"


def test_reference_asks_before_the_gate():
    flow = flat(reference_section("### Handoff flow"))
    ask = flow.find("Ask whether the human wants Amazap distribution")
    gate = flow.find("run the readiness gate above")
    assert 0 <= ask < gate, "the reference must ask about Amazap before the gate"


# The core no longer depends on host-root metadata, so nothing caps a proxy.
CAP_PHRASES = (
    "`FULFILLMENT_VERIFIED` at most",
    "is the ceiling",
    "doesn't count for a proxy",
    "stops at `FULFILLMENT_VERIFIED`",
)


@pytest.mark.parametrize("target", HANDOFF_TARGETS)
def test_no_handoff_caps_a_proxy_below_the_top_classification(target):
    text = handoff_text(target)
    hits = [phrase for phrase in CAP_PHRASES if phrase in text]
    assert not hits, f"{target} still caps a proxy: {hits}"


def test_native_step_sets_the_price_with_a_yes_and_a_deploy_before_the_gate():
    step = flat(amazap_step("l402-server-integration"))
    check = step.find("python scripts/l402_check.py")
    assert check >= 0
    for phrase in ("with the human's explicit yes, set the route's chosen price",
                   "(shown as a diff)", "have it deployed"):
        at = step.find(phrase)
        assert 0 <= at < check, f"{phrase!r} must come before the read-only check"
    assert "Continue only when the read-only report's invoice amount equals the chosen price" in step
