"""Guards for the sell-with-lightning-address skill.

The skill drives the producer claim (``GET``/``POST /api/producer/claim``) through
``l402_producer(action="sell_url")``, with ``scripts/claim.sh`` as the curl
fallback for an MCP without that action. The ways it goes wrong are mostly
textual, so most of these are text guards:

* **Money.** The paid token is bound to the body. A skill that tells the agent to
  rebuild the body, or to run phase 1 again after paying, charges the operator
  twice or strands the payment.
* **The key.** A replayed claim rotates the account's API key (``keyRotated:
  true``) and the old key stops working. A skill that says "the key appears once"
  or "never overwrite a stored key" makes the agent keep a dead key.
* **Figures.** Every price, trial length and renewal figure comes from the quote.
* **Custody.** Lightning Enable does not hold funds; the wallet provider
  facilitates custody and settlement. This skill also never says "decentralized".
* **Errors.** Every code the claim endpoint, its status route, and ``sell_url``
  return is named, grouped by whether the payment has been made.

The script tests run ``claim.sh`` locally on paths that stop before any network
call. Stdlib + pytest only; CI installs nothing else.
"""
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from test_skill_metadata import MAX_DESCRIPTION_LENGTH, parse_frontmatter

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIR = REPO_ROOT / "skills"
SKILL_DIR = SKILLS_DIR / "sell-with-lightning-address"
SKILL = SKILL_DIR / "SKILL.md"
SKILL_README = SKILL_DIR / "README.md"
SCRIPT = SKILL_DIR / "scripts" / "claim.sh"
ROOT_README = REPO_ROOT / "README.md"

FILES = (SKILL, SKILL_README)

# Server codes: ProducerClaimService, ProducerClaimController (claim and status
# routes), lightning-enable feat/producer-claim.
SERVER_CODES = (
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
    "claim_failed",
    "challenge_persist_failed",
    "upstream_unavailable",
    "authentication_required",
    "no_claim",
)
# Codes sell_url adds for answers that carry none (lightning-enable-mcp feat/sell-url).
TOOL_CODES = ("feature_not_enabled", "rate_limited", "network_error", "price_changed")
ERROR_CODES = SERVER_CODES + TOOL_CODES

# Free to fix and resend: refused before any invoice existed.
BEFORE_PAYMENT_ROWS = (
    "invalid_target_url",
    "invalid_price",
    "invalid_lightning_address",
    "invalid_recovery",
    "terms_required",
    "invalid_name",
    "invalid_description",
    "invalid_receive",
    "connect_not_available",
    "payment_provider_busy",
    "payment_provider_rejected",
    "upstream_unavailable",
    "challenge_persist_failed",
    "claim_unavailable",
    "feature_not_enabled",
    "rate_limited",
    "network_error",
)
# Retry with the same body and token after payment (sell_url's retryable set plus
# retryAfterPaymentAlso in shared/l402-producer-sell-url.json).
RETRY_AFTER_PAYMENT = (
    "claim_contended",
    "claim_failed",
    "payment_provider_busy",
    "upstream_unavailable",
    "challenge_persist_failed",
    "rate_limited",
    "network_error",
    "invalid_lightning_address",
    "invalid_target_url",
)
# Only reachable when an API key is sent; never a row of their own.
KEY_ONLY_CODES = ("plan_limit_reached", "receive_lane_already_configured")

REQUIRED_SECTIONS = (
    "## What you need",
    "## Flow",
    "### 1. Read the quote",
    "### 3. Claim with `sell_url`",
    "### 4. Store the API key",
    "## Check status later",
    "## Fallback without `sell_url`",
    "## Errors",
    "### Before payment: free",
    "### After payment: the payment is spent",
    "## Safety rules",
    "## Example",
)

BANNED_CUSTODY_WORDS = ("non-custodial", "noncustodial", "self-custody", "trustless", "decentralized")
CUSTODY_SENTENCES = (
    "Lightning Enable does not hold funds",
    "your wallet provider facilitates custody and settlement",
)

# A figure next to a unit is a price (or a trial length) written from memory.
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


def section(heading: str, text: str | None = None) -> str:
    """From ``heading`` to the next heading of the same or a higher level."""
    text = read(SKILL) if text is None else text
    start = text.find(f"\n{heading}\n")
    assert start >= 0, f"no {heading!r} section"
    level = heading.split(" ", 1)[0]
    stops = [text.find(f"\n{'#' * n} ", start + 1) for n in range(1, len(level) + 1)]
    stops = [s for s in stops if s > 0]
    return text[start : min(stops) if stops else len(text)]


def table_rows(text: str) -> list[list[str]]:
    rows = []
    for line in text.splitlines():
        if line.startswith("|") and not line.startswith("|---") and not line.startswith("| Code |"):
            rows.append([c.strip() for c in line.strip().strip("|").split("|")])
    return rows


# --------------------------------------------------------------------------- #
# Shape
# --------------------------------------------------------------------------- #

def test_frontmatter_is_valid_and_says_when_to_use_it():
    front = parse_frontmatter(read(SKILL))
    assert front.get("name") == "sell-with-lightning-address"
    description = front.get("description", "")
    assert description and len(description) <= MAX_DESCRIPTION_LENGTH
    assert "Use when" in description
    assert "charge for this API" in description
    assert "sell_url" in description
    for other in ("producer-setup", "sell-this", "pay-l402-anywhere"):
        assert other in description, f"description should route {other!r} cases away"


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.name)
def test_one_conversation_not_one_turn(path: Path):
    # Step 2 stops for an explicit yes, so it is one conversation, not one turn.
    assert "one conversation turn" not in flat(read(path))
    assert "one turn" not in flat(read(path))


@pytest.mark.parametrize("heading", REQUIRED_SECTIONS)
def test_required_sections_are_present(heading: str):
    assert re.search(rf"^{re.escape(heading)}\s*$", read(SKILL), re.MULTILINE), heading


def test_flow_steps_are_numbered_in_order():
    flow = section("## Flow")
    numbers = [int(n) for n in re.findall(r"^### (\d+)\. ", flow, re.MULTILINE)]
    assert numbers == list(range(1, len(numbers) + 1)), numbers


def test_skill_is_listed_in_the_root_readme_sell_table():
    text = read(ROOT_README)
    sell = text[text.find("### Sell") : text.find("### Build")]
    assert "(skills/sell-with-lightning-address/)" in sell


# --------------------------------------------------------------------------- #
# sell_url is the main path; curl is the fallback
# --------------------------------------------------------------------------- #

def test_sell_url_is_the_primary_path():
    text = read(SKILL)
    call = text.find('l402_producer(action="sell_url", target_url=')
    fallback = text.find("\n## Fallback without `sell_url`\n")
    assert 0 <= call < fallback, "the sell_url call comes before the fallback section"


def test_sell_url_call_passes_the_accepted_terms():
    claim = section("### 3. Claim with `sell_url`")
    assert 'accept_terms="<terms.version>"' in claim
    assert "confirmation_nonce=" in claim
    assert "exactly the same arguments" in flat(claim)


def test_quote_is_read_before_any_claim():
    text = read(SKILL)
    assert 0 <= text.find("### 1. Read the quote") < text.find("### 3. Claim with `sell_url`")


@pytest.mark.parametrize(
    "field",
    ("pricingNote", "bodyRule", "price.sats", "covers", "renewal", "terms.version",
     "terms.url", "limits.minProxyPriceSats", "limits.maxProxyPriceSats", "enabled"),
)
def test_quote_section_names_the_quote_fields(field: str):
    assert f"`{field}`" in section("### 1. Read the quote")


def test_pricing_note_is_shown_word_for_word():
    quote = flat(section("### 1. Read the quote"))
    assert "`pricingNote`: **show it to the operator word for word.**" in quote


def test_recovery_email_trap_is_raised_before_payment():
    ask = flat(section("### 2. Ask once, then wait"))
    assert "Does this email already have a Lightning Enable account?" in ask
    assert "refused only **after** payment (`merchant_exists`)" in ask


@pytest.mark.parametrize(
    "rule", ("public hostname that resolves", "standard HTTPS port", "no custom port",
             "refused before payment"),
)
def test_target_url_rules(rule: str):
    assert rule in flat(section("## What you need"))


def test_listing_requires_verification_and_points_at_verify_producer():
    text = flat(read(SKILL))
    assert "public listing requires ownership verification" in text
    assert "The proxy works by direct URL meanwhile." in text
    assert "The claim response carries the verification token and instructions (`verification`)" in text
    assert "the next step is the [`verify-producer`](../verify-producer/) skill" in text
    assert text.rstrip().endswith("prove ownership with [`verify-producer`](../verify-producer/).")


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.name)
def test_no_stale_verification_wording(path: Path):
    text = flat(read(path)).lower()
    for stale in ("not available yet", "until verification ships", "until ownership verification ships"):
        assert stale not in text, stale


# --------------------------------------------------------------------------- #
# The key: stored once per issue, replaced on rotation
# --------------------------------------------------------------------------- #

def test_key_rotation_is_handled_in_the_main_path():
    store = flat(section("### 4. Store the API key"))
    assert "**`keyRotated: true`:**" in store
    assert "every earlier key for this account stopped working" in store
    assert "Replace any key stored earlier for this claim." in store
    assert "Each further redeem rotates the key again." in store


def test_key_rotation_is_handled_in_the_fallback():
    fallback = flat(section("## Fallback without `sell_url`"))
    assert "`keyRotated: true`" in fallback
    assert "replace any key stored earlier for this claim" in fallback
    assert "Each further phase 2 rotates the key again" in fallback


def test_skill_never_says_the_key_is_shown_only_once():
    # The server re-issues the key on a replay; "never again" makes the agent
    # ignore the only working key.
    text = flat(read(SKILL)).lower()
    for stale in ("never again", "appears in this one answer", "only the first answer"):
        assert stale not in text, stale


def test_do_not_overwrite_has_the_same_claim_exception():
    text = flat(read(SKILL))
    assert "that older key came from an earlier run of this same claim" in text
    assert "holds a key from an earlier run of this claim" in text


def test_authenticated_claim_has_no_key_to_store():
    assert "`apiKey` is null or missing without `keyRotated`" in flat(section("### 4. Store the API key"))


def test_files_holding_the_key_are_chmod_600():
    text = flat(read(SKILL))
    assert "Any file holding a key gets `chmod 600`." in text
    assert "saves `response.json` with mode 600" in text


def test_hand_off_names_the_proxy_and_manifest_urls():
    handoff = section("### 5. Hand off")
    assert "`proxyUrl`" in handoff and "`manifestUrl`" in handoff and "`paidThrough`" in handoff


def test_recovery_is_explained_in_one_sentence():
    assert "Recovery matters because without it the API key is the only credential" in flat(read(SKILL))


# --------------------------------------------------------------------------- #
# Payment and the fallback body
# --------------------------------------------------------------------------- #

def test_payment_header_field_works_on_both_mcp_servers():
    text = read(SKILL)
    assert "`usage.headerValue`" in text
    # `authorization_header` exists only on the Python server.
    assert "authorization_header" not in text


def test_fallback_pays_with_a_capped_pay_l402_challenge():
    call = re.search(r"pay_l402_challenge\(([^)]*)\)", section("## Fallback without `sell_url`"))
    assert call
    for arg in ("invoice=", "macaroon=", "max_sats="):
        assert arg in call.group(1)


@pytest.mark.parametrize(
    "field",
    ('"targetUrl"', '"name"', '"receive": { "lightningAddress"', '"listPublicly"',
     '"acceptTerms": "<terms.version from the quote, copied exactly>"'),
)
def test_fallback_body_carries_the_request_fields(field: str):
    assert field in section("## Fallback without `sell_url`")


def test_fallback_states_the_body_rule():
    fallback = flat(section("## Fallback without `sell_url`"))
    assert "As `bodyRule` says" in fallback
    assert "the payment is not refunded" in fallback


@pytest.mark.parametrize(
    "rule",
    (
        "A refusal before payment costs nothing.",
        "After payment, resend the identical body with the same token.",
        "Never rebuild, reformat, or edit it after paying.",
        "never pay again",
        "Do not pay again.",
    ),
)
def test_pay_once_rules_are_stated(rule: str):
    assert rule in flat(read(SKILL))


def test_status_section_names_the_fields_and_errors():
    status = flat(section("## Check status later"))
    assert "/api/producer/claim/status" in status and "`X-API-Key`" in status
    for field in ("lane", "status", "proxyActive", "proxyId", "proxyUrl", "manifestUrl",
                  "paidThrough", "renew", "recovery"):
        assert f"`{field}`" in status, field
    assert "401 `authentication_required`" in status and "404 `no_claim`" in status


def test_self_test_is_offered_as_mint_pay_verify():
    selftest = section("### 6. Offer the self-test")
    for step in ("**Mint:**", "**Pay:**", "**Verify:**"):
        assert step in selftest
    assert "access_l402_resource(" in selftest
    assert "](../sell-this/)" in selftest


# --------------------------------------------------------------------------- #
# Errors
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("code", ERROR_CODES)
def test_every_error_code_is_named(code: str):
    assert re.search(rf"(?<![a-z_]){code}(?![a-z_])", read(SKILL)), code


@pytest.mark.parametrize("code", BEFORE_PAYMENT_ROWS)
def test_before_payment_codes_have_a_row(code: str):
    rows = [r for r in table_rows(section("### Before payment: free")) if f"`{code}`" in r[0]]
    assert len(rows) == 1, f"{code}: {len(rows)} rows"
    assert len(rows[0]) == 3 and all(rows[0]), rows[0]


def test_after_payment_retry_list_names_each_code():
    after = section("### After payment: the payment is spent")
    retry = flat(after[: after.find("| Code |")])
    assert "for these codes only:" in retry
    for code in RETRY_AFTER_PAYMENT:
        assert f"`{code}`" in retry, code


@pytest.mark.parametrize("code", ("claim_body_mismatch", "merchant_exists", "invalid_l402_token"))
def test_after_payment_codes_have_a_row(code: str):
    rows = [r for r in table_rows(section("### After payment: the payment is spent")) if f"`{code}`" in r[0]]
    assert len(rows) == 1 and len(rows[0]) == 3 and all(rows[0]), rows


def test_after_payment_stop_hands_over_the_payment_hash_only():
    after = flat(section("### After payment: the payment is spent"))
    assert "give the operator the `paymentHash`" in after
    assert "never the macaroon or the preimage" in after


@pytest.mark.parametrize("code", KEY_ONLY_CODES)
def test_key_only_codes_get_no_row(code: str):
    for heading in ("### Before payment: free", "### After payment: the payment is spent"):
        assert not [r for r in table_rows(section(heading)) if f"`{code}`" in r[0]], (code, heading)


def test_lightning_address_row_names_the_min_and_max_bounds():
    row = next(r for r in table_rows(section("### Before payment: free"))
               if "`invalid_lightning_address`" in r[0])
    assert "`minSendableSats`" in row[1] and "`maxSendableSats`" in row[1]


def test_errors_section_states_the_payment_rule():
    assert ("A refusal before payment costs nothing. After payment, resend the identical "
            "body with the same token.") in flat(section("## Errors"))


# --------------------------------------------------------------------------- #
# Words and figures
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("path", FILES + (SCRIPT,), ids=lambda p: p.name)
def test_no_banned_custody_words(path: Path):
    text = read(path).lower()
    assert not [w for w in BANNED_CUSTODY_WORDS if w in text]


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.name)
def test_custody_sentence_is_present(path: Path):
    text = flat(read(path))
    for sentence in CUSTODY_SENTENCES:
        assert sentence in text, f"{path.name} should say {sentence!r}"


@pytest.mark.parametrize("path", FILES + (SCRIPT,), ids=lambda p: p.name)
def test_no_price_like_figures(path: Path):
    text = read(path)
    # In a shell script `$1` is an argument, not a price.
    patterns = [p for p in PRICE_LIKE if not (path.suffix == ".sh" and p.pattern.startswith("[$"))]
    hits = sorted({m.group(0) for pattern in patterns for m in pattern.finditer(text)})
    assert not hits, f"{path.name} writes figures {hits}; read them from the quote"


@pytest.mark.parametrize("sample", ("costs 100 sats", "a 30-day trial", "$10", '"sats": 21', "1,000 sat"))
def test_the_price_guard_catches_figures(sample: str):
    assert any(p.search(sample) for p in PRICE_LIKE), sample


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.name)
def test_links_to_sibling_skills_resolve(path: Path):
    names = set(SIBLING_LINK.findall(read(path)))
    assert names
    missing = sorted(n for n in names if not (SKILLS_DIR / n / "SKILL.md").is_file())
    assert not missing, missing


def test_skill_links_sell_this_and_producer_setup():
    assert {"sell-this", "producer-setup"} <= set(SIBLING_LINK.findall(read(SKILL)))


# --------------------------------------------------------------------------- #
# scripts/claim.sh
# --------------------------------------------------------------------------- #

def test_skill_references_the_script_for_every_fallback_step():
    fallback = section("## Fallback without `sell_url`")
    for sub in ("phase1", "save-auth", "phase2", "store-key-file", "clean"):
        assert f"claim.sh {sub}" in fallback, sub
    assert "scripts/claim.sh status" in section("## Check status later")
    assert "scripts/claim.sh quote" in section("### 1. Read the quote")


def test_script_is_executable_in_git():
    out = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "ls-files", "-s", "--", "skills/sell-with-lightning-address/scripts/claim.sh"],
        capture_output=True, text=True,
    ).stdout
    if not out.strip():
        pytest.skip("claim.sh is not committed in this checkout")
    assert out.split()[0] == "100755", f"claim.sh must be committed executable: {out!r}"


def test_both_posts_send_the_same_body_file_and_only_phase2_authorizes():
    text = read(SCRIPT)
    phase1 = text[text.find("  phase1)") : text.find("  save-auth)")]
    phase2 = text[text.find("  phase2)") : text.find("  store-key-file)")]
    body = '--data-binary @"$DIR/body.json"'
    assert body in phase1 and body in phase2
    assert "auth.header" in phase2 and '-H @"$DIR/auth.header"' in phase2
    assert '-H @"$DIR/auth.header"' not in phase1


def test_script_keeps_secrets_off_the_command_line():
    text = read(SCRIPT)
    assert "umask 077" in text
    assert "-H @-" in text, "the API key goes to curl on stdin"
    assert "Authorization: L402" not in text.replace("Authorization: L402 <macaroon>", "")


BASH = shutil.which("bash")
needs_bash = pytest.mark.skipif(BASH is None, reason="bash not available")


def run_script(tmp_path: Path, *args: str, stdin: str = ""):
    env = os.environ.copy()
    env["LE_CLAIM_DIR"] = (tmp_path / "claim").as_posix()
    env["LE_API_BASE"] = "https://claim.invalid"  # never reached by these tests
    return subprocess.run(
        [BASH, SCRIPT.as_posix(), *args], input=stdin, capture_output=True, text=True, env=env
    )


@needs_bash
def test_script_without_a_command_prints_usage(tmp_path: Path):
    result = run_script(tmp_path)
    assert result.returncode == 2
    assert "phase1" in result.stderr and "phase2" in result.stderr


@needs_bash
def test_phase1_refuses_once_the_claim_is_paid(tmp_path: Path):
    state = tmp_path / "claim"
    state.mkdir()
    (state / "body.json").write_text("{}", encoding="utf-8")
    (state / "auth.header").write_text("Authorization: L402 m:p\n", encoding="utf-8")
    result = run_script(tmp_path, "phase1")
    assert result.returncode != 0
    assert "never phase1 again" in result.stderr
    assert not (state / "challenge.json").exists(), "no request was made"


@needs_bash
def test_phase2_needs_the_saved_header(tmp_path: Path):
    state = tmp_path / "claim"
    state.mkdir()
    (state / "body.json").write_text("{}", encoding="utf-8")
    result = run_script(tmp_path, "phase2")
    assert result.returncode != 0 and "auth.header" in result.stderr


@needs_bash
def test_save_auth_accepts_only_an_l402_header_value(tmp_path: Path):
    bad = run_script(tmp_path, "save-auth", stdin="Bearer abc\n")
    assert bad.returncode != 0
    assert not (tmp_path / "claim" / "auth.header").exists()

    good = run_script(tmp_path, "save-auth", stdin="L402 bWFj:00ff\n")
    assert good.returncode == 0, good.stderr
    saved = (tmp_path / "claim" / "auth.header").read_text(encoding="utf-8")
    assert saved == "Authorization: L402 bWFj:00ff\n"
    assert "bWFj:00ff" not in good.stdout, "the token is never echoed"


@needs_bash
def test_store_key_file_writes_the_rotated_key_over_the_old_one(tmp_path: Path):
    state = tmp_path / "claim"
    state.mkdir()
    old = tmp_path / "claim-example-api-a1b2.key"
    old.write_text("le_old_dead_key\n", encoding="utf-8")
    (state / "response.json").write_text(
        '{"apiKey":"le_new_key","proxy":{"proxyId":"example-api-a1b2"},'
        '"replayed":true,"keyRotated":true}',
        encoding="utf-8",
    )
    result = run_script(tmp_path, "store-key-file")
    assert result.returncode == 0, result.stderr
    assert old.read_text(encoding="utf-8") == "le_new_key\n"
    assert "le_new_key" not in result.stdout


@needs_bash
def test_store_key_file_refuses_a_null_key(tmp_path: Path):
    state = tmp_path / "claim"
    state.mkdir()
    (state / "response.json").write_text(
        '{"apiKey":null,"proxy":{"proxyId":"x"},"replayed":true,"keyRotated":false}', encoding="utf-8"
    )
    result = run_script(tmp_path, "store-key-file")
    assert result.returncode != 0 and "apiKey is null" in result.stderr
