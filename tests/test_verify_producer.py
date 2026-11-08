"""Guards for the verify-producer skill.

The skill walks an agent through proxy ownership verification on the Lightning
Enable API (lightning-enable feat/producer-verification):
``GET /api/proxy/{proxyId}/verification``, ``POST .../verification/token`` and
``POST .../verify``, then public listing through the manifest settings endpoint.
``scripts/verify.sh`` makes the calls. The ways it goes wrong are mostly textual:

* **The token.** It is shown once, and issuing a new one unverifies and unlists a
  proxy verified by a live check. A skill that re-issues casually drops a listing.
* **The reasons.** ``POST verify`` explains a failure in a ``reason`` string built
  by ``ProxyVerificationService``. The skill matches those strings, so they are
  pinned here exactly as the service writes them.
* **The rules.** Pending records nothing; a daily re-check; three consecutive
  failures unlist; ``grandfathered`` and ``platform`` need no action.
* **Custody and figures.** Lightning Enable does not hold funds; no price-like
  figure appears anywhere.

The script tests run ``verify.sh`` against a fake ``curl`` placed first on
``PATH``, so nothing touches the network. Stdlib + pytest only.
"""
import os
import re
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

from test_sell_with_lightning_address import (
    BANNED_CUSTODY_WORDS,
    CUSTODY_SENTENCES,
    PRICE_LIKE,
    SIBLING_LINK,
    flat,
    read,
    table_rows,
)
from test_skill_metadata import MAX_DESCRIPTION_LENGTH, parse_frontmatter

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIR = REPO_ROOT / "skills"
SKILL_DIR = SKILLS_DIR / "verify-producer"
SKILL = SKILL_DIR / "SKILL.md"
SKILL_README = SKILL_DIR / "README.md"
SCRIPT = SKILL_DIR / "scripts" / "verify.sh"
ROOT_README = REPO_ROOT / "README.md"
SIBLING = SKILLS_DIR / "sell-with-lightning-address" / "SKILL.md"

FILES = (SKILL, SKILL_README)

ENDPOINTS = (
    "GET /api/proxy/{proxyId}/verification",
    "POST /api/proxy/{proxyId}/verification/token",
    "POST /api/proxy/{proxyId}/verify",
    "PUT /api/proxy/{proxyId}/manifest/settings",
)

# ProxyVerificationService (reason fragments, verbatim) and the controller's 409.
REASON_FRAGMENTS = (
    "The target URL cannot be verified: ",
    "The target host was refused before any request: ",
    "the host check did not finish within ",
    "the host check failed (",
    "answered with a redirect (HTTP ",
    "), which is not followed",
    "is larger than 4096 bytes",
    "is not valid JSON",
    'has no "verify" field',
    '"verify" must be a string or an array of strings',
    "\"verify\" does not contain this proxy's current token",
    "no TXT record at _lightning-enable.",
    "contains this proxy's current token",
    "without X-Lightning-Enable-Verify",
    "X-Lightning-Enable-Verify does not carry this proxy's current token",
    "no answer within ",
    "could not be reached (",
    "failed (",
    "s, so nothing was recorded. Try again.",
    "The verification token was re-issued while this check ran. Publish the new token and check again.",
)
ERROR_CODES = (
    "verification_token_required",
    "ownership_verification_required",
    "plan_feature_disabled",
    "listing_verification_failed",
)

REQUIRED_SECTIONS = (
    "## What you need",
    "## Flow",
    "### 1. Read the state",
    "### 2. Get the token",
    "### 3. Publish the token by one method",
    "### 4. Run the check",
    "### 5. Poll while DNS or a deploy settles",
    "### 6. Offer public listing",
    "## States that need no action",
    "## Errors",
    "### Before the token",
    "### After the token",
    "### During the check",
    "## Safety rules",
    "## Example",
)

SUBCOMMANDS = ("state", "token", "write-well-known", "verify", "poll", "list")


def section(heading: str) -> str:
    text = read(SKILL)
    start = text.find(f"\n{heading}\n")
    assert start >= 0, f"no {heading!r} section"
    level = heading.split(" ", 1)[0]
    stops = [text.find(f"\n{'#' * n} ", start + 1) for n in range(1, len(level) + 1)]
    stops = [s for s in stops if s > 0]
    return text[start : min(stops) if stops else len(text)]


def rows(heading: str) -> list[list[str]]:
    return [r for r in table_rows(section(heading)) if r and r[0] not in ("Error", "`reason` contains")]


# --------------------------------------------------------------------------- #
# Shape
# --------------------------------------------------------------------------- #

def test_frontmatter_is_valid_and_routes_other_cases_away():
    front = parse_frontmatter(read(SKILL))
    assert front.get("name") == "verify-producer"
    description = front.get("description", "")
    assert description and len(description) <= MAX_DESCRIPTION_LENGTH
    assert "Use when" in description and "Do NOT use" in description
    assert "list my endpoint publicly" in description
    for other in ("sell-with-lightning-address", "producer-setup", "create-l402-proxy"):
        assert other in description, other


@pytest.mark.parametrize("heading", REQUIRED_SECTIONS)
def test_required_sections_are_present(heading: str):
    assert re.search(rf"^{re.escape(heading)}\s*$", read(SKILL), re.MULTILINE), heading


def test_flow_steps_are_numbered_in_order():
    numbers = [int(n) for n in re.findall(r"^### (\d+)\. ", section("## Flow"), re.MULTILINE)]
    assert numbers == list(range(1, len(numbers) + 1)) and len(numbers) == 6, numbers


def test_skill_is_listed_in_the_root_readme_sell_table():
    text = read(ROOT_README)
    sell = text[text.find("### Sell") : text.find("### Build")]
    assert "(skills/verify-producer/)" in sell


def test_sell_with_lightning_address_ends_with_a_verify_next_pointer():
    last = read(SIBLING).rstrip("\n").splitlines()[-1]
    assert last.startswith("**Verify next:**") and "](../verify-producer/)" in last


# --------------------------------------------------------------------------- #
# The contract
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_endpoints_are_named_exactly(endpoint: str):
    assert endpoint in flat(read(SKILL))


@pytest.mark.parametrize(
    "value",
    ("/.well-known/lightning-enable.json", '{"verify":"<token>"}', "_lightning-enable.{target host}",
     "X-Lightning-Enable-Verify: <token>", "`well-known`", "`dns-txt`", "`header`"),
)
def test_methods_carry_the_exact_locations(value: str):
    assert value in section("### 3. Publish the token by one method")


def test_each_method_says_what_it_proves():
    table = [r for r in table_rows(section("### 3. Publish the token by one method")) if r[0].startswith("`")]
    proves = {r[0]: r[2] for r in table if len(r) == 3}
    assert "web root" in proves["`well-known`"]
    assert "DNS zone" in proves["`dns-txt`"]
    assert "responses" in proves["`header`"]


def test_publish_step_splits_on_deploy_access():
    publish = flat(section("### 3. Publish the token by one method"))
    assert "**You have deploy access to the target host:**" in publish
    assert "scripts/verify.sh write-well-known <proxyId> <path>" in publish
    assert "**You don't:** hand the operator both alternatives below" in publish
    assert "`_lightning-enable.api`" in publish, "the zone-appending trap"


@pytest.mark.parametrize("field", ("verified", "method", "tokenIssued", "listed", "failures",
                                   "nextCheckAt", "instructions", "tokenPlaceholder"))
def test_state_section_names_the_state_fields(field: str):
    assert f"`{field}`" in section("### 1. Read the state") or f".{field}`" in section("### 1. Read the state")


def test_token_is_taken_from_the_claim_or_issued_once():
    token = flat(section("### 2. Get the token"))
    assert "`verification.token`" in token and "`verification.verifyEndpoint`" in token
    assert "**The token is shown once**" in token
    assert "`token: null`" in token, "a replayed claim carries no token"
    assert "`--reissue`" in token and "unverified and unlisted" in token


def test_check_handles_pending_and_reasons():
    check = flat(section("### 4. Run the check"))
    assert "**`pending: true`:**" in check and "`retryAfterSeconds`" in check
    assert "**recorded nothing**" in check
    assert "never contains the token" in check


def test_poll_is_bounded():
    poll = flat(section("### 5. Poll while DNS or a deploy settles"))
    assert "scripts/verify.sh poll <proxyId>" in poll
    assert "up to 5 attempts" in poll and "up to 10" in poll
    assert "A failed manual `verify` on a proxy that is already verified counts toward the three-failure drop" in poll
    assert "Don't poll a proxy that is already verified." in poll


def test_listing_step_explains_the_rules():
    listing = flat(section("### 6. Offer public listing"))
    assert 'l402_producer(action="publish", proxy_id="<proxyId>")' in listing
    assert "scripts/verify.sh list <proxyId>" in listing
    assert "**Daily re-check.**" in listing and "**The three-failure rule.**" in listing
    assert "three consecutive failed checks" in listing
    assert "never deleted or deactivated" in listing
    assert "Listing doesn't come back by itself." in listing


def test_grandfathered_and_platform_need_no_action():
    states = flat(section("## States that need no action"))
    assert "**`grandfathered`:**" in states and "**`platform`:**" in states
    assert "Neither needs anything from the operator." in states


# --------------------------------------------------------------------------- #
# Errors
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("fragment", REASON_FRAGMENTS)
def test_reason_strings_are_quoted_exactly(fragment: str):
    assert fragment in section("### During the check"), fragment


@pytest.mark.parametrize("code", ERROR_CODES)
def test_error_codes_have_a_row(code: str):
    found = [r for r in rows("### After the token") if f"`{code}`" in r[0]]
    assert len(found) == 1 and len(found[0]) == 3 and all(found[0]), found


@pytest.mark.parametrize("heading", ("### Before the token", "### After the token", "### During the check"))
def test_every_error_row_has_three_filled_cells(heading: str):
    table = rows(heading)
    assert table
    for row in table:
        assert len(row) == 3 and all(row), row


def test_before_the_token_covers_auth_missing_proxy_and_rate_limit():
    first_cells = " ".join(r[0] for r in rows("### Before the token"))
    for status in ("401", "404", "429", "`000`"):
        assert status in first_cells, status


# --------------------------------------------------------------------------- #
# Words, figures, links
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("path", FILES + (SCRIPT,), ids=lambda p: p.name)
def test_no_banned_custody_words(path: Path):
    text = read(path).lower()
    assert not [w for w in BANNED_CUSTODY_WORDS if w in text]


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.name)
def test_custody_sentence_is_present(path: Path):
    for sentence in CUSTODY_SENTENCES:
        assert sentence in flat(read(path)), sentence


@pytest.mark.parametrize("path", FILES + (SCRIPT,), ids=lambda p: p.name)
def test_no_price_like_figures(path: Path):
    text = read(path)
    patterns = [p for p in PRICE_LIKE if not (path.suffix == ".sh" and p.pattern.startswith("[$"))]
    hits = sorted({m.group(0) for pattern in patterns for m in pattern.finditer(text)})
    assert not hits, f"{path.name} writes figures {hits}"


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.name)
def test_links_to_sibling_skills_resolve(path: Path):
    names = set(SIBLING_LINK.findall(read(path)))
    assert names
    missing = sorted(n for n in names if not (SKILLS_DIR / n / "SKILL.md").is_file())
    assert not missing, missing


@pytest.mark.parametrize("anchor", ("#states-that-need-no-action", "#during-the-check", "#after-the-token",
                                    "#before-the-token"))
def test_in_page_anchors_resolve(anchor: str):
    text = read(SKILL)
    assert f"]({anchor})" in text
    slug = anchor[1:].replace("-", " ")
    assert re.search(rf"^#+ {re.escape(slug)}\s*$", text, re.MULTILINE | re.IGNORECASE), anchor


# --------------------------------------------------------------------------- #
# scripts/verify.sh
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("sub", SUBCOMMANDS)
def test_skill_references_every_subcommand(sub: str):
    assert re.search(rf"scripts/verify\.sh {re.escape(sub)}\b", read(SKILL)), sub
    assert f"  {sub})" in read(SCRIPT), f"verify.sh has no {sub} branch"


def test_script_is_executable_in_git():
    out = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "ls-files", "-s", "--", "skills/verify-producer/scripts/verify.sh"],
        capture_output=True, text=True,
    ).stdout
    if not out.strip():
        pytest.skip("verify.sh is not committed in this checkout")
    assert out.split()[0] == "100755", f"verify.sh must be committed executable: {out!r}"


def test_script_keeps_the_key_off_the_command_line():
    text = read(SCRIPT)
    assert "umask 077" in text
    assert "-H @-" in text and "X-API-Key: %s" in text


BASH = shutil.which("bash")
needs_bash = pytest.mark.skipif(BASH is None, reason="bash not available")

FAKE_CURL = r"""#!/usr/bin/env bash
# Stands in for curl: logs its arguments and stdin, answers from numbered files.
out=""; hdr=""; prev=""
for a in "$@"; do case "$prev" in -o) out="$a";; -D) hdr="$a";; esac; prev="$a"; done
n=$(cat "$FAKE_DIR/count" 2>/dev/null || echo 0); n=$((n + 1)); echo "$n" > "$FAKE_DIR/count"
echo "$*" >> "$FAKE_DIR/args.log"
cat >> "$FAKE_DIR/stdin.log"
body="$FAKE_DIR/body.$n"; [ -f "$body" ] || body="$FAKE_DIR/body"
code="$FAKE_DIR/code.$n"; [ -f "$code" ] || code="$FAKE_DIR/code"
[ -n "$out" ] && cp "$body" "$out"
[ -n "$hdr" ] && printf 'Retry-After: 1\r\n' > "$hdr"
printf '%s' "$(cat "$code")"
"""

TOKEN = "AbCdEfGhIjKlMnOpQrStUvWxYz0123456789_-abcde"
OTHER = "ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ"


class Fake:
    def __init__(self, root: Path):
        self.root = root
        self.dir = root / "fake"
        self.bin = root / "bin"
        self.config = root / "config"
        for d in (self.dir, self.bin, self.config):
            d.mkdir()
        curl = self.bin / "curl"
        curl.write_text(FAKE_CURL, encoding="utf-8", newline="\n")
        curl.chmod(curl.stat().st_mode | stat.S_IEXEC)
        (self.config / "config.json").write_text('{"lightningEnableApiKey":"le_test_key"}', encoding="utf-8")

    def answer(self, body: str, code: int = 200, n: int | None = None):
        suffix = "" if n is None else f".{n}"
        (self.dir / f"body{suffix}").write_text(body, encoding="utf-8", newline="\n")
        (self.dir / f"code{suffix}").write_text(str(code), encoding="utf-8", newline="\n")

    @property
    def calls(self) -> list[str]:
        log = self.dir / "args.log"
        return log.read_text(encoding="utf-8").splitlines() if log.exists() else []

    def run(self, *args: str, extra_env: dict | None = None):
        env = os.environ.copy()
        env["PATH"] = str(self.bin) + os.pathsep + env.get("PATH", "")
        env["FAKE_DIR"] = self.dir.as_posix()
        env["LE_CONFIG_DIR"] = self.config.as_posix()
        env["LE_API_BASE"] = "https://verify.invalid"
        env["LE_POLL_INTERVAL"] = "0"
        env.pop("LE_KEY_FILE", None)
        env.update(extra_env or {})
        return subprocess.run([BASH, SCRIPT.as_posix(), *args], capture_output=True, text=True, env=env)


@pytest.fixture
def fake(tmp_path: Path) -> Fake:
    return Fake(tmp_path)


def state_body(verified: bool = False, method: str | None = None, token: str | None = None, **extra) -> str:
    m = "null" if method is None else f'"{method}"'
    t = "null" if token is None else f'"{token}"'
    rest = "".join(f',"{k}":{v}' for k, v in extra.items())
    return (f'{{"proxyId":"p-1","verified":{str(verified).lower()},"method":{m},"failures":0,'
            f'"tokenIssued":true,"token":{t}{rest},"instructions":{{"tokenPlaceholder":"<token>",'
            f'"methods":[{{"method":"well-known"}},{{"method":"header"}}]}}}}')


@needs_bash
def test_without_a_command_prints_usage(fake: Fake):
    result = fake.run()
    assert result.returncode == 2
    for sub in SUBCOMMANDS:
        assert sub in result.stderr, sub
    assert not fake.calls


@needs_bash
@pytest.mark.parametrize("bad", ("a/../b", "-x", "p 1", "p?x=1"))
def test_a_bad_proxy_id_is_refused_before_any_request(fake: Fake, bad: str):
    result = fake.run("state", bad)
    assert result.returncode == 1 and "proxy id" in result.stderr
    assert not fake.calls


@needs_bash
def test_token_saves_the_token_and_never_prints_it(fake: Fake):
    fake.answer(state_body(token=TOKEN))
    result = fake.run("token", "p-1")
    assert result.returncode == 0, result.stderr
    saved = fake.config / "verify-p-1.token"
    assert saved.read_text(encoding="utf-8") == TOKEN + "\n"
    assert TOKEN not in result.stdout + result.stderr
    assert '"tokenPlaceholder":"<token>"' in result.stdout, "only the token field is redacted"
    assert [c.split()[2] for c in fake.calls] == ["GET", "POST"]
    assert "/verification/token" in fake.calls[1]
    stdin = (fake.dir / "stdin.log").read_text(encoding="utf-8")
    assert "X-API-Key: le_test_key" in stdin
    assert all("le_test_key" not in c for c in fake.calls), "the key never reaches the command line"


@needs_bash
def test_token_refuses_when_a_token_file_exists(fake: Fake):
    (fake.config / "verify-p-1.token").write_text(TOKEN + "\n", encoding="utf-8")
    result = fake.run("token", "p-1")
    assert result.returncode == 1 and "--reissue" in result.stderr
    assert not fake.calls


@needs_bash
def test_token_refuses_to_unverify_a_live_verified_proxy(fake: Fake):
    fake.answer(state_body(verified=True, method="dns-txt"))
    result = fake.run("token", "p-1")
    assert result.returncode == 1 and "unlists" in result.stderr
    assert len(fake.calls) == 1 and fake.calls[0].split()[2] == "GET", "no token was issued"


@needs_bash
@pytest.mark.parametrize("method", ("grandfathered", "platform"))
def test_token_goes_ahead_for_a_standing_method(fake: Fake, method: str):
    fake.answer(state_body(verified=True, method=method), n=1)
    fake.answer(state_body(verified=True, method=method, token=TOKEN), n=2)
    result = fake.run("token", "p-1")
    assert result.returncode == 0, result.stderr
    assert (fake.config / "verify-p-1.token").is_file()


@needs_bash
def test_reissue_skips_the_guard(fake: Fake):
    (fake.config / "verify-p-1.token").write_text(OTHER + "\n", encoding="utf-8")
    fake.answer(state_body(token=TOKEN))
    result = fake.run("token", "p-1", "--reissue")
    assert result.returncode == 0, result.stderr
    assert [c.split()[2] for c in fake.calls] == ["POST"]
    assert (fake.config / "verify-p-1.token").read_text(encoding="utf-8") == TOKEN + "\n"


@needs_bash
def test_from_claim_copies_the_token_without_a_request(fake: Fake, tmp_path: Path):
    claim = tmp_path / "response.json"
    claim.write_text('{"apiKey":"le_x","proxy":{"proxyId":"p-1"},"verification":{"token":"%s",'
                     '"instructions":{"tokenPlaceholder":"<token>","tokenEndpoint":"/api/proxy/p-1/verification/token"},'
                     '"verifyEndpoint":"/api/proxy/p-1/verify"}}' % TOKEN, encoding="utf-8")
    result = fake.run("token", "p-1", "--from-claim", claim.as_posix())
    assert result.returncode == 0, result.stderr
    assert (fake.config / "verify-p-1.token").read_text(encoding="utf-8") == TOKEN + "\n"
    assert TOKEN not in result.stdout and not fake.calls


@needs_bash
def test_from_claim_refuses_a_replayed_claim(fake: Fake, tmp_path: Path):
    claim = tmp_path / "response.json"
    claim.write_text('{"replayed":true,"verification":{"token":null}}', encoding="utf-8")
    result = fake.run("token", "p-1", "--from-claim", claim.as_posix())
    assert result.returncode == 1 and "verify.sh token p-1" in result.stderr
    assert not (fake.config / "verify-p-1.token").exists()


@needs_bash
def test_write_well_known_into_a_web_root(fake: Fake, tmp_path: Path):
    (fake.config / "verify-p-1.token").write_text(TOKEN + "\n", encoding="utf-8")
    root = tmp_path / "www"
    root.mkdir()
    result = fake.run("write-well-known", "p-1", root.as_posix())
    assert result.returncode == 0, result.stderr
    out = root / ".well-known" / "lightning-enable.json"
    assert out.read_text(encoding="utf-8") == '{"verify":"%s"}\n' % TOKEN
    assert TOKEN not in result.stdout and not fake.calls


@needs_bash
def test_write_well_known_keeps_other_proxies_tokens(fake: Fake, tmp_path: Path):
    (fake.config / "verify-p-1.token").write_text(TOKEN + "\n", encoding="utf-8")
    out = tmp_path / "lightning-enable.json"
    out.write_text('{"verify":"%s"}\n' % OTHER, encoding="utf-8")
    assert fake.run("write-well-known", "p-1", out.as_posix()).returncode == 0
    assert out.read_text(encoding="utf-8") == '{"verify":["%s","%s"]}\n' % (OTHER, TOKEN)
    again = fake.run("write-well-known", "p-1", out.as_posix())
    assert again.returncode == 0 and "nothing changed" in again.stdout


@needs_bash
def test_write_well_known_needs_a_token(fake: Fake, tmp_path: Path):
    result = fake.run("write-well-known", "p-1", tmp_path.as_posix())
    assert result.returncode == 1 and "verify.sh token p-1" in result.stderr


@needs_bash
@pytest.mark.parametrize(
    ("body", "code", "rc", "says"),
    (
        (state_body(verified=True, method="well-known"), 200, 0, "verified: true (method: well-known)"),
        (state_body(pending="true", retryAfterSeconds="1", reason='"the check did not finish within 1s, so nothing was recorded. Try again."'),
         200, 3, "pending"),
        (state_body(reason='"well-known: /.well-known/lightning-enable.json has no \\"verify\\" field"'),
         200, 4, 'has no "verify" field'),
        ('{"error":"verification_token_required"}', 409, 1, "verification_token_required"),
    ),
    ids=("verified", "pending", "failed", "no-token"),
)
def test_verify_exit_codes(fake: Fake, body: str, code: int, rc: int, says: str):
    fake.answer(body, code)
    result = fake.run("verify", "p-1")
    assert result.returncode == rc, result.stdout + result.stderr
    assert says in result.stdout
    assert len(fake.calls) == 1 and fake.calls[0].split()[2] == "POST"


@needs_bash
def test_poll_waits_out_pending_and_stops_at_success(fake: Fake):
    fake.answer(state_body(reason='"dns-txt: no TXT record at _lightning-enable.a.example"'), n=1)
    fake.answer(state_body(pending="true", retryAfterSeconds="1", reason='"x"'), n=2)
    fake.answer(state_body(verified=True, method="dns-txt"), n=3)
    result = fake.run("poll", "p-1", "5")
    assert result.returncode == 0, result.stdout + result.stderr
    assert len(fake.calls) == 3, "stops at the first success"
    assert "waiting 1s" in result.stdout


@needs_bash
def test_poll_gives_up_after_the_bound(fake: Fake):
    fake.answer(state_body(reason='"dns-txt: no TXT record at _lightning-enable.a.example"'))
    result = fake.run("poll", "p-1", "2")
    assert result.returncode == 4
    assert len(fake.calls) == 2 and "not verified after 2 attempt(s)" in result.stdout


@needs_bash
@pytest.mark.parametrize("attempts", ("0", "11", "x", "-1"))
def test_poll_refuses_an_unbounded_count(fake: Fake, attempts: str):
    result = fake.run("poll", "p-1", attempts)
    assert result.returncode == 1 and not fake.calls


@needs_bash
def test_poll_stops_on_an_error_status(fake: Fake):
    fake.answer('{"error":"Proxy not found"}', 404)
    result = fake.run("poll", "p-1", "5")
    assert result.returncode == 1 and len(fake.calls) == 1


@needs_bash
def test_list_puts_the_manifest_settings(fake: Fake):
    fake.answer('{"manifestEnabled":true,"manifestPubliclyListed":true}')
    result = fake.run("list", "p-1")
    assert result.returncode == 0, result.stderr
    call = fake.calls[0]
    assert call.split()[2] == "PUT" and "/api/proxy/p-1/manifest/settings" in call
    assert '"manifestPubliclyListed":true' in call


@needs_bash
def test_list_reports_a_refusal(fake: Fake):
    fake.answer('{"error":"ownership_verification_required","verify_endpoint":"/api/proxy/p-1/verify"}', 422)
    result = fake.run("list", "p-1")
    assert result.returncode == 1 and "ownership_verification_required" in result.stdout


@needs_bash
def test_a_key_file_overrides_config_json(fake: Fake, tmp_path: Path):
    key = tmp_path / "claim-p-1.key"
    key.write_text("le_claim_key\n", encoding="utf-8")
    fake.answer(state_body())
    result = fake.run("state", "p-1", extra_env={"LE_KEY_FILE": key.as_posix()})
    assert result.returncode == 0, result.stderr
    assert "X-API-Key: le_claim_key" in (fake.dir / "stdin.log").read_text(encoding="utf-8")


@needs_bash
def test_no_key_means_no_request(fake: Fake):
    (fake.config / "config.json").unlink()
    result = fake.run("state", "p-1")
    assert result.returncode == 1 and "LE_KEY_FILE" in result.stderr
    assert not fake.calls
