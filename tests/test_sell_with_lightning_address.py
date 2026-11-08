"""Text guards for the sell-with-lightning-address skill.

This skill drives the two-phase ``POST /api/producer/claim`` endpoint: phase 1
answers 402, the agent pays, phase 2 sends the SAME body with
``Authorization: L402 <macaroon>:<preimage>``. The ways it goes wrong are all
textual, which is why these are text guards:

* **Money.** The paid token is bound to the body, so a skill that tells the
  agent to rebuild the body, or to POST without the header after paying,
  charges the operator twice or strands the payment. The pay-once rules and
  "a refusal before payment costs nothing" must be stated.
* **Figures.** Every price, trial length and renewal figure comes from the
  quote (``GET /api/producer/claim``). A number written into the skill goes
  stale the day pricing moves, and an agent repeats it to the operator as fact.
* **Custody.** Lightning Enable does not hold funds; the wallet provider
  facilitates custody and settlement. The repo-wide guard in
  ``test_skill_metadata.py`` bans three words; this skill also never says
  "decentralized".
* **Errors.** Every error code the claim endpoint can return is in the table,
  so the agent never invents a cause.

The frontmatter, README-row, and sibling-link checks that run over every skill
live in ``test_skill_metadata.py``; this module re-asserts them for this skill
by name so a failure reads as this skill's.

Stdlib + pytest only; CI installs nothing else.
"""
import re
from pathlib import Path

import pytest

from test_skill_metadata import MAX_DESCRIPTION_LENGTH, parse_frontmatter

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIR = REPO_ROOT / "skills"
SKILL_DIR = SKILLS_DIR / "sell-with-lightning-address"
SKILL = SKILL_DIR / "SKILL.md"
SKILL_README = SKILL_DIR / "README.md"
ROOT_README = REPO_ROOT / "README.md"

FILES = (SKILL, SKILL_README)

# Every code ProducerClaimService and ProducerClaimController return
# (lightning-enable, feat/producer-claim). The first eleven are the brief's;
# the rest are what the code actually sends.
ERROR_CODES = (
    "invalid_target_url",
    "invalid_price",
    "invalid_lightning_address",
    "invalid_recovery",
    "terms_required",
    "connect_not_available",
    "claim_body_mismatch",
    "plan_limit_reached",
    "receive_lane_already_configured",
    "payment_provider_busy",
    "payment_provider_rejected",
    "invalid_receive",
    "invalid_name",
    "invalid_description",
    "invalid_authorization",
    "invalid_l402_token",
    "merchant_exists",
    "claim_contended",
    "claim_unavailable",
    "challenge_persist_failed",
    "upstream_unavailable",
)

REQUIRED_SECTIONS = (
    "## What you need",
    "## Flow",
    "### 1. Read the quote",
    "## Errors",
    "## Safety rules",
    "## Example",
)

BANNED_CUSTODY_WORDS = ("non-custodial", "noncustodial", "self-custody", "trustless", "decentralized")
CUSTODY_SENTENCES = (
    "Lightning Enable does not hold funds",
    "your wallet provider facilitates custody and settlement",
)

# A figure next to a unit is a price (or a trial length) written from memory.
# Field names such as `price.sats` or `renew.quoteSats` are fine: no digit.
PRICE_LIKE = (
    re.compile(r"\d[\d,._]*\s*-?\s*(?:sats?|satoshis?|msats?|usd|cents?|¢)\b", re.IGNORECASE),
    re.compile(r"[$€£]\s?\d"),
    re.compile(r"\b\d+[\s-]*days?\b", re.IGNORECASE),
    re.compile(r"\"\w*(?:sats|cents|days)\"\s*:\s*\d", re.IGNORECASE),
)

SIBLING_LINK = re.compile(r"\]\(\.\./([a-z0-9-]+)(?:[/)#])")


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def flat(text: str) -> str:
    """Collapse line wraps so phrase checks do not depend on where prose breaks."""
    return re.sub(r"\s+", " ", text)


def errors_section() -> str:
    text = read(SKILL)
    start = text.find("\n## Errors\n")
    assert start >= 0, "SKILL.md has no '## Errors' section"
    end = text.find("\n## ", start + 1)
    return text[start : end if end > 0 else len(text)]


# --------------------------------------------------------------------------- #
# Shape
# --------------------------------------------------------------------------- #

def test_frontmatter_is_valid_and_says_when_to_use_it():
    front = parse_frontmatter(read(SKILL))
    assert front.get("name") == "sell-with-lightning-address"
    description = front.get("description", "")
    assert description and len(description) <= MAX_DESCRIPTION_LENGTH
    assert "Use when" in description
    # The moment of intent, in the operator's words, so a search lands here.
    assert "charge for this API" in description
    # Points away to the lanes and skills it does not cover.
    for other in ("producer-setup", "sell-this", "pay-l402-anywhere"):
        assert other in description, f"description should route {other!r} cases away"


@pytest.mark.parametrize("heading", REQUIRED_SECTIONS)
def test_required_sections_are_present(heading: str):
    assert re.search(rf"^{re.escape(heading)}\s*$", read(SKILL), re.MULTILINE), (
        f"SKILL.md is missing {heading!r}"
    )


def test_flow_steps_are_numbered_in_order():
    numbers = [int(n) for n in re.findall(r"^### (\d+)\. ", read(SKILL), re.MULTILINE)]
    assert numbers == list(range(1, len(numbers) + 1)), numbers


def test_skill_is_listed_in_the_root_readme_sell_table():
    text = read(ROOT_README)
    sell = text[text.find("### Sell") : text.find("### Build")]
    assert "(skills/sell-with-lightning-address/)" in sell


# --------------------------------------------------------------------------- #
# The endpoint contract, as the skill states it
# --------------------------------------------------------------------------- #

def test_skill_reads_the_quote_before_posting():
    text = read(SKILL)
    quote = text.find("curl -sS https://api.lightningenable.com/api/producer/claim")
    post = text.find("-X POST https://api.lightningenable.com/api/producer/claim")
    assert 0 <= quote < post, "GET the quote first, then POST the claim"


@pytest.mark.parametrize(
    "field",
    ("price.sats", "covers.days", "covers.plan", "terms.version", "terms.url",
     "limits.minProxyPriceSats", "limits.maxProxyPriceSats"),
)
def test_skill_shows_the_quote_fields(field: str):
    assert f"`{field}`" in read(SKILL)


@pytest.mark.parametrize(
    "field",
    ('"targetUrl"', '"name"', '"receive": { "lightningAddress"', '"listPublicly"', '"acceptTerms"'),
)
def test_body_carries_the_request_fields(field: str):
    assert field in read(SKILL)


def test_accept_terms_is_the_quotes_terms_version():
    text = flat(read(SKILL))
    assert '"acceptTerms": "<terms.version from the quote, copied exactly>"' in text


def test_listing_is_pending_verification_and_the_proxy_works_by_direct_url():
    text = flat(read(SKILL))
    assert "stays unlisted until ownership verification ships" in text
    assert "The proxy works by direct URL meanwhile." in text


def test_skill_never_asks_for_the_connect_lane():
    assert "never `receive.connect`" in read(SKILL)


def test_phase_two_sends_the_same_body_with_the_l402_header():
    text = read(SKILL)
    assert "`Authorization: L402 <macaroon>:<preimage>`" in text or "L402 <macaroon>:<preimage>" in text
    posts = re.findall(r"curl -sS -X POST[^`]*?(?=```)", text, re.DOTALL)
    assert len(posts) == 2, "one phase-1 POST and one phase-2 POST"
    body_args = {re.search(r"--data-binary (\S+)", p).group(1) for p in posts}
    assert len(body_args) == 1, f"both phases must send the same body file, got {body_args}"
    assert "Authorization" not in posts[0] and "auth.header" not in posts[0]
    assert "auth.header" in posts[1]


@pytest.mark.parametrize(
    "rule",
    (
        "A refusal before payment costs nothing.",
        "After payment, resend the identical body with the same token.",
        "Never rebuild, reformat, or edit it after paying.",
        "Never POST without the `Authorization` header again",
        "do not pay again",
    ),
)
def test_pay_once_rules_are_stated(rule: str):
    assert rule in flat(read(SKILL))


def test_the_paying_tool_is_named_and_called_with_a_cap():
    text = read(SKILL)
    assert "`pay_l402_challenge`" in text
    call = re.search(r"pay_l402_challenge\(([^)]*)\)", text)
    assert call, "show the pay_l402_challenge call"
    for arg in ("invoice=", "macaroon=", "max_sats="):
        assert arg in call.group(1)


def test_the_api_key_is_stored_once_and_the_location_is_named():
    text = flat(read(SKILL))
    assert "### 7. Store the API key, once" in read(SKILL)
    assert "~/.lightning-enable/config.json" in text
    assert "`lightningEnableApiKey`" in text
    assert "do not overwrite it" in text
    assert "Tell the operator which file holds the key" in text
    assert "Do not print the key." in text


def test_hand_off_names_the_proxy_and_manifest_urls():
    text = read(SKILL)
    assert "`proxy.url`" in text and "`proxy.manifest`" in text


def test_recovery_is_explained_in_one_sentence():
    assert ("Recovery matters because without it the API key is the only credential"
            in flat(read(SKILL)))


def test_self_test_is_offered_as_mint_pay_verify():
    text = read(SKILL)
    start = text.find("### 9. Offer the self-test")
    assert start >= 0
    section = text[start:text.find("\n## ", start)]
    for step in ("**Mint:**", "**Pay:**", "**Verify:**"):
        assert step in section
    assert "access_l402_resource(" in section
    assert "](../sell-this/)" in section


# --------------------------------------------------------------------------- #
# Errors
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("code", ERROR_CODES)
def test_every_error_code_has_a_table_row(code: str):
    rows = [line for line in errors_section().splitlines()
            if line.startswith("|") and f"`{code}`" in line]
    assert len(rows) == 1, f"{code} should appear in exactly one error-table row, got {len(rows)}"
    cells = [c.strip() for c in rows[0].strip("|").split("|")]
    assert len(cells) == 4 and all(cells), f"{code}: every column filled: {cells}"


def test_error_table_has_the_four_columns():
    assert "| Code | Status | Tell the operator | Retry helps? |" in errors_section()


def test_lightning_address_row_names_the_min_and_max_bounds():
    row = next(line for line in errors_section().splitlines() if "`invalid_lightning_address`" in line)
    assert "`minSendableSats`" in row and "`maxSendableSats`" in row


def test_errors_section_states_the_payment_rule():
    section = flat(errors_section())
    assert ("A refusal before payment costs nothing. After payment, resend the identical "
            "body with the same token.") in section


# --------------------------------------------------------------------------- #
# Words and figures
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("path", FILES, ids=lambda p: p.name)
def test_no_banned_custody_words(path: Path):
    text = read(path).lower()
    hits = [w for w in BANNED_CUSTODY_WORDS if w in text]
    assert not hits, f"{path.name} uses {hits}"


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.name)
def test_custody_sentence_is_present(path: Path):
    text = flat(read(path))
    for sentence in CUSTODY_SENTENCES:
        assert sentence in text, f"{path.name} should say {sentence!r}"


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.name)
def test_no_price_like_figures(path: Path):
    text = read(path)
    hits = sorted({m.group(0) for pattern in PRICE_LIKE for m in pattern.finditer(text)})
    assert not hits, (
        f"{path.name} writes figures {hits}. Prices, trials and renewals come from "
        "the quote; never write them into the skill."
    )


@pytest.mark.parametrize("sample", ("costs 100 sats", "a 30-day trial", "$10", '"sats": 21', "1,000 sat"))
def test_the_price_guard_catches_figures(sample: str):
    # Guard the guard: a pattern that matches nothing passes every file.
    assert any(p.search(sample) for p in PRICE_LIKE), sample


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.name)
def test_links_to_sibling_skills_resolve(path: Path):
    names = set(SIBLING_LINK.findall(read(path)))
    assert names, f"{path.name} should link to the skills it hands off to"
    missing = sorted(n for n in names if not (SKILLS_DIR / n / "SKILL.md").is_file())
    assert not missing, f"{path.name} links to missing skills: {missing}"


def test_skill_links_sell_this_and_producer_setup():
    names = set(SIBLING_LINK.findall(read(SKILL)))
    assert {"sell-this", "producer-setup"} <= names
