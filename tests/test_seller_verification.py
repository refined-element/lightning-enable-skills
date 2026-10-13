"""Text guards for the core seller verification step and its pay-once rules.

Every seller skill (``producer-setup``, ``create-l402-proxy``, and
``l402-server-integration``) checks its new endpoint with the Lightning Enable
L402 compatibility report before the hand-off. The generic rules live in
``references/l402-verification-levels.md`` under "Verifying your own
endpoint"; each skill carries a "Verify your endpoint" step that records its
self-test payment as evidence and pays at most once.

``pay_once_text`` reads those rules from the levels reference or from a
skill's "Verify your endpoint" step. Like the rest of the suite these are text
guards; nothing opens a socket or pays.
"""
import re

import pytest

from test_amazap_seller_handoff import (
    CLASSIFICATION_NAME,
    EM_DASH,
    HAND_OFF_HEADING,
    LOOSE_VERIFIED,
    PROXY_SKILLS,
    REPO_ROOT,
    SELLER_SKILLS,
    SKILLS_DIR,
    STEP_HEADING,
    VERIFIED_SELLERS,
    amazap_step,
    flat,
    read,
    readme_step,
    section_at,
)
from test_shared_references import CLASSIFICATIONS, CUSTODY

LEVELS = REPO_ROOT / "references" / "l402-verification-levels.md"
LEVELS_HEADING = "## Verifying your own endpoint"
VERIFY_HEADING = re.compile(r"^### (\d+)\. Verify your endpoint[ \t]*$", re.MULTILINE)
PAY_ONCE_TARGETS = ("levels", *SELLER_SKILLS)
REPORT_URL = (
    "https://github.com/refined-element/lightning-enable-skills/tree/main/"
    "skills/l402-compatibility-report"
)
READ_ONLY_COMMAND = re.compile(r"`python scripts/l402_check\.py <url>[^`]*`")
PAY_ONCE_OPENING = "made no payment for this endpoint by any means"
PAY_ONCE_OTHERWISE = "otherwise the cases below apply and the agent never pays again"
# Present wherever the pay-once rules live.
VERIFY_RULES = (
    "non-HTTPS",
    "`200` to an unpaid request",
    "`400`, `415`, or `422`",
    "challenge-compatible, fulfillment unverified",
    "never twice",
    "pay_l402_challenge",
    "counts as paid",
    "does not pay again",
    "either wallet",
    "made by hand, outside both tools",
    "a wallet that can pay this endpoint",
    "(a testnet invoice doesn't count)",
    "with the same method",
    "token piped on stdin",
    "If that token is gone",
    "with a different method",
    "Python MCP server",
    "`GET` or `HEAD`",
)


def levels_section() -> str:
    text = read(LEVELS)
    start = text.find(f"\n{LEVELS_HEADING}\n")
    assert start >= 0, f"references/l402-verification-levels.md has no '{LEVELS_HEADING}' section"
    return section_at(text, start + 1)


def verify_step(skill: str) -> str:
    text = read(SKILLS_DIR / skill / "SKILL.md")
    match = VERIFY_HEADING.search(text)
    assert match, f"skills/{skill}/SKILL.md has no '### N. Verify your endpoint' step"
    return section_at(text, match.start())


def raw_pay_once_text(target: str) -> str:
    return levels_section() if target == "levels" else verify_step(target)


def pay_once_text(target: str) -> str:
    return flat(raw_pay_once_text(target))


def lines(section: str) -> int:
    return len(section.rstrip("\n").splitlines())


ROOT_README = REPO_ROOT / "README.md"


def root_row(skill: str) -> str:
    rows = [line for line in read(ROOT_README).splitlines()
            if line.startswith("|") and f"(skills/{skill}/)" in line]
    assert len(rows) == 1, rows
    return rows[0]


@pytest.mark.parametrize("skill", ("producer-setup", "create-l402-proxy"))
def test_root_readme_seller_rows_lead_with_the_registry(skill):
    row = root_row(skill)
    assert "publish to the Lightning Enable registry" in row
    assert "verify" in row
    assert "amazap" not in row.lower()


def test_root_readme_native_row_names_its_manifest_not_the_registry():
    # The registry lists Lightning Enable proxies, not an API on its own domain.
    row = root_row("l402-server-integration")
    assert "its own L402 manifest" in row and "verify" in row
    # The manifest step is an offer: the human approves and deploys it.
    assert "optionally publish its own L402 manifest" in row and "you approve and deploy it" in row
    assert "registry" not in row.lower() and "amazap" not in row.lower()


def test_root_readme_report_row_brands_the_lightning_enable_report():
    assert "The Lightning Enable L402 compatibility report" in root_row("l402-compatibility-report")


def test_root_readme_paragraph_names_the_direct_path_before_amazap():
    text = flat(read(ROOT_README))
    direct = text.find("publish to the Lightning Enable registry, where buyers' agents find an endpoint with "
                       "`discover_api` and pay it directly from their own wallets")
    amazap = text.find("can also draft an optional listing on")
    assert 0 <= direct < amazap
    assert "the Lightning Enable L402 compatibility report, checks any seller's endpoint" in text
    paragraph = text[text.find("**Buy + sell, end to end:**"):text.find("## What works where")]
    assert CUSTODY in paragraph, "the Buy + sell paragraph carries the custody sentence verbatim"


def test_root_readme_names_the_three_skills_that_run_the_report_before_their_hand_off():
    # sell-this and offer-agent-service have no report step and no hand-off,
    # so the sentence names the three skills that do, not "the seller skills".
    text = flat(read(ROOT_README))
    assert ("The three skills that build a paid endpoint, `producer-setup`, `create-l402-proxy`, and "
            "`l402-server-integration`, run it before their hand-off.") in text
    assert "The seller skills run it" not in text


def test_levels_reference_puts_verification_before_the_profiles():
    text = read(LEVELS)
    verifying = text.find(f"\n{LEVELS_HEADING}\n")
    profiles = text.find("\n## Optional marketplace profiles\n")
    assert 0 <= verifying < profiles


def test_levels_section_verifies_the_endpoint_not_a_listing():
    # The verify rules are platform-neutral: they check the endpoint, and the
    # self-test is the paid evidence. A marketplace profile is read only for an
    # optional listing and never changes the result.
    section = flat(levels_section())
    assert "amazap" not in section.lower()
    assert section.lower().count("listing") == 1
    for phrase in ("the seller skill's own self-test is its paid evidence",
                   "The report's optional marketplace profiles never change this result",
                   "only for an optional listing"):
        assert phrase in section, phrase


@pytest.mark.parametrize("target", PAY_ONCE_TARGETS)
def test_pay_once_rules_are_all_there(target):
    text = pay_once_text(target)
    missing = [rule for rule in VERIFY_RULES if rule not in text]
    assert not missing, f"{target} is missing {missing}"


# "counts as paid" also appears in the different-method and by-hand cases, so
# pin the pay_l402_challenge case itself (create-l402-proxy names its step).
PAY_L402_CHALLENGE_COUNTS = re.compile(r"`pay_l402_challenge`(?: \([^)]*\))? counts as paid")


@pytest.mark.parametrize("target", PAY_ONCE_TARGETS)
def test_a_pay_l402_challenge_payment_counts_as_paid(target):
    assert PAY_L402_CHALLENGE_COUNTS.search(pay_once_text(target)), (
        f"{target}: a payment through `pay_l402_challenge` counts as paid, so the agent never pays again"
    )


@pytest.mark.parametrize("target", PAY_ONCE_TARGETS)
def test_read_only_command_carries_max_sats(target):
    commands = READ_ONLY_COMMAND.findall(pay_once_text(target))
    assert commands, f"{target} never shows the read-only command"
    # Each part is its own substring, so flag order never matters; the shared
    # order is `<url> --json --max-sats <cap>`.
    for part in ("<url>", "--json", "--max-sats <cap>"):
        missing = [command for command in commands if part not in command]
        assert not missing, f"{target}: the paid check needs a capped JSON read-only report: {missing}"


@pytest.mark.parametrize("target", PAY_ONCE_TARGETS)
def test_pay_once_opens_with_any_payment_by_any_means(target):
    text = pay_once_text(target)
    for phrase in (PAY_ONCE_OPENING, PAY_ONCE_OTHERWISE):
        assert phrase in text, f"{target} is missing {phrase!r}"
    for stale in ("did not pay this exact", "did not already pay"):
        assert stale not in text, f"{target} still opens pay-once with {stale!r}"
    assert text.find(PAY_ONCE_OPENING) < text.find("If that token is gone")


@pytest.mark.parametrize("target", PAY_ONCE_TARGETS)
def test_a_testnet_payment_is_neither_evidence_nor_the_one_paid_check(target):
    text = pay_once_text(target)
    assert "(a testnet invoice doesn't count)" in text, target
    start = text.find("A self-test payment of a testnet invoice")
    assert start >= 0, f"{target} has no testnet sentence"
    sentence = text[start:text.find(". A ", start) + 1]
    neither = "neither reuse evidence nor the one paid check"
    for phrase in (neither, "run the paid check once, with the human's yes"):
        assert phrase in sentence, f"{target}: the testnet sentence is missing {phrase!r}"
    assert "does not pay again" not in sentence, f"{target}: a testnet payment must not end the run"


@pytest.mark.parametrize("target", PAY_ONCE_TARGETS)
def test_without_the_report_skill_paid_delivery_is_not_proven(target):
    text = pay_once_text(target)
    wanted = "`l402-compatibility-report` is not installed, paid delivery stays unverified"
    assert wanted in text, target
    assert REPORT_URL in text, f"{target} must give the report skill's GitHub URL"
    # Without the report there is no classification at all, so nothing
    # may be reported as CHALLENGE_COMPATIBLE or better.
    assert "no classification is available" in text, target


@pytest.mark.parametrize("target", PAY_ONCE_TARGETS)
def test_challenge_compatible_waits_for_the_paid_evidence(target):
    text = pay_once_text(target)
    wanted = "do not report paid delivery as proven until the paid evidence below lifts it"
    assert wanted in text, f"{target} is missing {wanted!r}"
    assert 'fulfillment unverified" and stop' not in text, f"{target} stops before the paid evidence"


@pytest.mark.parametrize("skill", SELLER_SKILLS)
def test_skill_runs_the_read_only_check_and_reuses_the_self_test(skill):
    text = pay_once_text(skill)
    commands = READ_ONLY_COMMAND.findall(text)
    assert any("<url>" in command and "--json" in command for command in commands), (
        f"{skill} never runs the read-only check with --json"
    )
    for phrase in ("`GET` or `HEAD` only", "`--mode-a mode-a.json`"):
        assert phrase in text, f"{skill} is missing {phrase!r}"


def test_native_check_runs_on_the_public_url_at_the_chosen_price():
    text = pay_once_text("l402-server-integration")
    assert "A test against `localhost` doesn't count." in text
    assert "before body validation" in text
    check = text.find("python scripts/l402_check.py")
    assert check >= 0
    for phrase in ("with the human's explicit yes, set the route's chosen price", "(shown as a diff)",
                   "have it deployed"):
        at = text.find(phrase)
        assert 0 <= at < check, f"{phrase!r} must come before the read-only check"
    assert "Continue only when the read-only report's invoice amount equals the chosen price" in text


def test_native_skill_adds_the_manifest_before_it_claims_discovery():
    # Neither middleware serves a manifest, so the skill adds one in its own
    # approved step, and the hand-off says buyers need a URL until it ships.
    text = read(SKILLS_DIR / "l402-server-integration" / "SKILL.md")
    manifest = re.search(r"^### (\d+)\. Publish an L402 manifest[ \t]*$", text, re.MULTILINE)
    verify = VERIFY_HEADING.search(text)
    assert manifest and verify and int(verify.group(1)) == int(manifest.group(1)) + 1
    step = flat(section_at(text, manifest.start()))
    for phrase in ("`/.well-known/l402-manifest.json`", "`pricing.base_price_sats`", "as a diff",
                   "human's explicit yes", "`discover_api(url="):
        assert phrase in step, f"the manifest step is missing {phrase!r}"
    assert "until it is deployed, buyers reach the API only by a URL the human shares" in flat(
        hand_off("l402-server-integration"))


@pytest.mark.parametrize("target", PAY_ONCE_TARGETS)
def test_pay_once_text_names_only_core_classifications(target):
    named = set(CLASSIFICATION_NAME.findall(pay_once_text(target)))
    assert named <= set(CLASSIFICATIONS), f"{target} names {sorted(named - set(CLASSIFICATIONS))}"
    assert "MARKETPLACE_READY" not in pay_once_text(target)


@pytest.mark.parametrize("target", PAY_ONCE_TARGETS)
def test_pay_once_text_has_no_em_dash_or_loose_verified(target):
    raw = raw_pay_once_text(target)
    assert EM_DASH not in raw, f"{target} uses an em-dash"
    assert not LOOSE_VERIFIED.findall(flat(raw)), f"{target}: 'verified' only inside a classification"


# The longest Amazap step before the rebalance ran 125 lines; each now runs
# about a third of that and stays shorter than its skill's hand-off.
MAX_AMAZAP_STEP_LINES = 42
MAX_README_AMAZAP_LINES = 16


def hand_off(skill: str) -> str:
    text = read(SKILLS_DIR / skill / "SKILL.md")
    match = HAND_OFF_HEADING.search(text)
    assert match, f"skills/{skill}/SKILL.md has no '### N. Hand off' step"
    return section_at(text, match.start())


@pytest.mark.parametrize("skill", VERIFIED_SELLERS)
def test_verify_step_comes_right_before_the_hand_off_and_the_amazap_step_after_it(skill):
    text = read(SKILLS_DIR / skill / "SKILL.md")
    verify = VERIFY_HEADING.search(text)
    handoff = HAND_OFF_HEADING.search(text)
    amazap = STEP_HEADING.search(text)
    assert verify and handoff and amazap
    assert int(handoff.group(1)) == int(verify.group(1)) + 1
    assert int(amazap.group(1)) == int(handoff.group(1)) + 1


@pytest.mark.parametrize("skill", VERIFIED_SELLERS)
def test_verify_step_names_the_lightning_enable_report(skill):
    step = verify_step(skill)
    assert "(../l402-compatibility-report/)" in step
    assert "Lightning Enable L402 compatibility report" in flat(step)


@pytest.mark.parametrize("skill", VERIFIED_SELLERS)
def test_verify_step_runs_the_check_with_the_routes_method(skill):
    # The read-only check uses the route's own method, so a POST route is
    # probed as POST rather than as whatever the self-test sent.
    assert "(add `--method POST` for a `POST` route)" in flat(verify_step(skill)), skill


@pytest.mark.parametrize("skill", VERIFIED_SELLERS)
def test_amazap_read_back_matches_the_rows_url_and_price(skill):
    # An imported row for the same host can look listed; only a row whose
    # endpoint URL and seller price match this one is this listing.
    step = flat(amazap_step(skill))
    start = step.find("**Read back.**")
    assert start >= 0, f"{skill}: the Amazap step has no read-back bullet"
    assert "the row's endpoint URL and seller price match this" in step[start:], skill


@pytest.mark.parametrize("skill", VERIFIED_SELLERS)
def test_hand_off_says_how_buyers_find_and_pay_you(skill):
    text = flat(hand_off(skill))
    common = ("**How buyers find and pay you:**", "`discover_api(url=", "`access_l402_resource`",
              "(../pay-l402-anywhere/)", "No marketplace account or credits")
    # The "What to watch" bullet also names the paid list_challenges call, so
    # check the seller's own view inside the buyer bullet itself.
    start = text.find("**How buyers find and pay you:**")
    end = text.find(" - **", start)
    bullet = "" if start < 0 else text[start:end] if end >= 0 else text[start:]
    # The dashboard's Endpoints page counts challenges minted, not payments, so
    # the paid view is list_challenges and the dashboard is named as minted-only.
    for phrase in ('list_challenges", challenge_status="paid")',
                   "the dashboard's Endpoints page shows challenges minted per endpoint, not payments"):
        assert phrase in bullet, f"{skill}: the buyer bullet must name {phrase!r}"
    assert "and in the dashboard" not in bullet, f"{skill}: the dashboard has no paid-calls view"
    if skill in PROXY_SKILLS:
        wanted = common + ("Lightning Enable registry", "`discover_api(query=")
    else:
        wanted = common + ("/.well-known/l402-manifest.json", "(../offer-agent-service/)",
                           "The Lightning Enable registry lists Lightning Enable proxies")
    missing = [phrase for phrase in wanted if phrase not in text]
    assert not missing, f"{skill} hand-off is missing {missing}"
    assert "amazap" not in text.lower(), f"{skill}: the hand-off is the Lightning Enable outcome"


@pytest.mark.parametrize("skill", VERIFIED_SELLERS)
def test_amazap_step_is_shorter_than_the_hand_off(skill):
    step, handoff = amazap_step(skill), hand_off(skill)
    assert lines(step) < lines(handoff), f"{skill}: Amazap {lines(step)} lines, hand-off {lines(handoff)}"
    assert lines(step) <= MAX_AMAZAP_STEP_LINES, f"{skill}: Amazap step runs {lines(step)} lines"


@pytest.mark.parametrize("skill", VERIFIED_SELLERS)
def test_amazap_step_extends_the_setup_and_reuses_the_report(skill):
    step = flat(amazap_step(skill))
    for phrase in ("The setup is complete at step", "Reuse the step", "never pay again",
                   "`marketplace_profiles.amazap.status`"):
        assert phrase in step, f"{skill} Amazap step is missing {phrase!r}"
    for gone in ("l402_check.py", "**Pay once.**", "**Existing row first.**", "MARKETPLACE_READY"):
        assert gone not in step, f"{skill} Amazap step still carries {gone!r}"


@pytest.mark.parametrize("skill", VERIFIED_SELLERS)
def test_amazap_step_asks_before_looking_for_a_row(skill):
    step = flat(amazap_step(skill))
    ask = step.find("Ask whether the human wants an Amazap listing")
    row = step.find("existing row")
    assert 0 <= ask < row, f"{skill}: ask before searching Amazap's catalog"


@pytest.mark.parametrize("skill", VERIFIED_SELLERS)
def test_readme_says_how_buyers_find_you_before_the_amazap_section(skill):
    text = read(SKILLS_DIR / skill / "README.md")
    find = text.find("\n## How buyers find you\n")
    amazap = text.find("\n## Optional: list on Amazap\n")
    assert 0 <= find < amazap, f"{skill}/README.md: 'How buyers find you' comes before the Amazap section"
    section = flat(section_at(text, find + 1))
    wanted = ["(../pay-l402-anywhere/)", "(../l402-compatibility-report/)", "No marketplace account or credits"]
    wanted.append("Lightning Enable registry" if skill in PROXY_SKILLS else "l402-manifest.json")
    missing = [phrase for phrase in wanted if phrase not in section]
    assert not missing, f"{skill}/README.md is missing {missing}"


@pytest.mark.parametrize("skill", VERIFIED_SELLERS)
def test_readme_amazap_section_is_short_and_optional(skill):
    section = readme_step(skill)
    assert "Your setup is complete without this." in flat(section)
    assert lines(section) <= MAX_README_AMAZAP_LINES, f"{skill}/README.md Amazap section runs {lines(section)} lines"
