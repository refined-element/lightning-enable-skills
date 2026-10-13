"""Text guards for discover-paid-apis: two labeled sources, one bounded trial.

``discover-paid-apis`` searches two sources and labels every row: the Lightning
Enable registry (``discover_api``) and Amazap (its MCP tools when the host
lists them, otherwise the public products API). It compares at most five
candidates and makes at most one bounded trial purchase. The shared Amazap
buyer rules live in ``references/amazap-marketplace.md``, under "Discovery
versus purchase" and "Two wallets"; the skill links them by GitHub URL,
because a skill installs by copying one folder.

Like the rest of the suite these are text guards: nothing opens a socket or
pays. They hold the spec's Workstream A acceptance tests in guard form:

1. search reads both sources, labels each row, and spends nothing;
2. one bounded purchase, with the cap that applies to each path;
3. a quote over the cap is refused and nothing is bought;
4. a stale quote is shown again, never bought automatically;
5. sensitive input is never sent without the user's approval;
6. a paid failure is reported as Amazap credits and never replaced by a
   second buy without asking;
7. a URL the user already has goes to ``pay-l402-anywhere``;
8. without Amazap's tools, the public products API, never a claim of MCP
   access;
9. the MCP ``budget`` never bounds an Amazap buy (two wallets);
10. no steer toward paying an Amazap listing's ``endpointUrl`` directly;
11. ``approval_required`` stops the buy.

``fixtures/amazap-products.json`` is a captured-shape sample of
``GET https://amazap.com/api/products`` (shape observed on 2026-10-12) with
placeholder names. It pins the row fields the skill reads, so a recaptured
fixture with a renamed field fails here before the skill reads a field that no
longer exists.
"""
import json
import re
from pathlib import Path

import pytest

import test_skill_metadata
import test_tool_surface
from test_amazap_seller_handoff import (
    AMAZAP_FIGURE,
    EM_DASH,
    LOOSE_VERIFIED,
    flat,
    read,
    reference_section,
    section_at,
)
from test_shared_references import CUSTODY

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILL_DIR = REPO_ROOT / "skills" / "discover-paid-apis"
SKILL = SKILL_DIR / "SKILL.md"
README = SKILL_DIR / "README.md"
ROOT_README = REPO_ROOT / "README.md"
REFERENCE = REPO_ROOT / "references" / "amazap-marketplace.md"
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "amazap-products.json"

REFERENCE_BASE = (
    "https://github.com/refined-element/lightning-enable-skills/blob/main/"
    "references/amazap-marketplace.md"
)
REFERENCE_LINKS = (
    REFERENCE_BASE + "#discovery-versus-purchase",
    REFERENCE_BASE + "#two-wallets",
)
LIVE_LINKS = (
    "https://amazap.com/llms.txt",
    "https://amazap.com/mcp",
    "https://amazap.com/credits",
)

# Amazap's MCP tools the buyer flow names by capability. None is a Lightning
# Enable MCP tool, so test_tool_surface.py does not know them.
AMAZAP_TOOLS = (
    "search_catalog",
    "describe_sku",
    "quote",
    "buy",
    "orders",
    "get_order",
    "balance",
    "spend_summary",
    "report_outcome",
    "claim_failed_call",
    "report_sku",
    "top_up",
)
# The products-API row fields the skill reads (spec section 5).
ROW_FIELDS = (
    "priceSats",
    "totalSats",
    "feeBps",
    "healthStatus",
    "listingState",
    "hidden",
    "buyable",
    "paidSuccesses",
    "paidFailures",
    "lastPaidSuccessAt",
    "schemaConfidence",
    "trust.label",
    "inputSchema.fields",
)
PRODUCTS_PARAMS = (
    "q",
    "protocol",
    "category",
    "source",
    "healthyOnly",
    "synthetic",
    "limit",
    "offset",
)

NON_GOAL = (
    "Never steer a buyer away from Amazap's all-in price toward direct payment "
    "of a listing Amazap surfaced."
)
DIRECT_PAY_SCOPE = "Direct payment through `pay-l402-anywhere` is for a URL the user already has."
CAP_RULE = "State which cap applies to which path before any purchase."
TWO_WALLET_RULE = (
    "The Lightning Enable MCP `budget` and `get_balance` don't see Amazap "
    "credits and never bound an Amazap buy"
)
SENSITIVE = (
    "secrets, private URLs, authenticated pages, credentials, personal data, "
    "or proprietary content"
)
SECRETS = (
    "Never print invoices, preimages, macaroons, OAuth tokens, NWC strings, "
    "wallet credentials, or full payment authorization headers."
)
FAILURE_KINDS = (
    "quote failure",
    "policy refusal",
    "payment failure",
    "provider failure",
    "malformed result",
    "user-declined approval",
)
BANNED_WORDS = ("non-custodial", "noncustodial", "self-custody", "trustless", "decentralized")

# Argument spellings this skill may pass (the Python server's snake_case).
DISCOVER_API_ARGS = {"query", "category", "url", "budget_aware"}
ACCESS_ARGS = {"url", "max_sats", "confirmation_nonce"}

# Docs that carry the file-wide guards. Task 6 adds the skill's README.
GUARDED_DOCS: tuple[Path, ...] = (SKILL,)

# A sentence that names the MCP budget or balance AND an Amazap buy must be a
# negation: the MCP wallet's caps never bound a buy paid in Amazap credits.
MCP_BUDGET = re.compile(r"`budget[`(]|`get_balance[`(]|\bMCP (?:wallet )?budget\b", re.IGNORECASE)
AMAZAP_BUY = re.compile(r"\bAmazap `?buy`?\b|`buy[`(]", re.IGNORECASE)
AMAZAP_ROW = re.compile(r"Amazap|`buy[`(]")
NEGATION = re.compile(r"\b(?:never|not|no|don't|doesn't|isn't|aren't)\b", re.IGNORECASE)
BLOCK_START = re.compile(r"^(?:#{1,6} |[-*] |\d+\. )")
FENCE = "`" * 3  # a code fence, spelled so this file can sit inside one
SENTENCE_END = re.compile(r"(?<=[.!?])\s+|(?<=[.!?]\*\*)\s+")
# Where one clause of a sentence ends and the next begins: a semicolon, a
# colon, or a comma before a joining word. A negation only covers the MCP
# budget when it sits in the same clause as the budget mention.
CLAUSE_END = re.compile(r"[;:]\s*|,\s+(?=(?:and|but|or|so|yet|while|whereas)\b)|\s+(?=(?:but|whereas)\b)")
KEYWORD = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)\s*=")


def fixture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def rows() -> list[dict]:
    return fixture()["products"]


def field(row: dict, dotted: str):
    value = row
    for part in dotted.split("."):
        value = value[part]
    return value


def prose_sentences(text: str) -> list[str]:
    """The prose of a markdown file, one sentence per item.

    Table rows and fenced code are left out (``table_rows`` reads tables).
    Headings, list items, and blank lines start a new block, so a heading never
    runs into the sentence below it. Blockquote markers are dropped.
    """
    blocks: list[list[str]] = [[]]
    fenced = False
    for raw in text.splitlines():
        line = re.sub(r"^\s*>\s?", "", raw).strip()
        if line.startswith(FENCE):
            fenced = not fenced
            blocks.append([])
            continue
        if fenced or not line or line.startswith("|"):
            blocks.append([])
            continue
        if BLOCK_START.match(line):
            blocks.append([])
        blocks[-1].append(line)
    return [
        sentence
        for block in blocks
        if block
        for sentence in SENTENCE_END.split(" ".join(block))
        if sentence
    ]


def table_rows(text: str) -> list[list[str]]:
    return [
        [cell.strip() for cell in line.strip().strip("|").split("|")]
        for line in text.splitlines()
        if line.strip().startswith("|")
    ]


def budget_claims(text: str) -> list[str]:
    """Sentences that put the MCP budget beside an Amazap buy without negating it.

    A negation counts only inside the clause that names the MCP budget, so
    "Amazap never pays cash, but the MCP `budget` caps an Amazap `buy`." is
    caught: its "never" belongs to another clause.
    """
    return [
        sentence
        for sentence in prose_sentences(text)
        if AMAZAP_BUY.search(sentence)
        and any(
            MCP_BUDGET.search(clause) and not NEGATION.search(clause)
            for clause in CLAUSE_END.split(sentence)
        )
    ]


def amazap_rows_with_the_mcp_budget(text: str) -> list[str]:
    """Table rows about Amazap or a `buy` that name the MCP budget or balance."""
    return [
        " | ".join(row)
        for row in table_rows(text)
        if AMAZAP_ROW.search(row[0]) and any(MCP_BUDGET.search(cell) for cell in row)
    ]


def skill_section(heading: str) -> str:
    """Flat text of the SKILL.md section that starts with ``heading``, with
    blockquote markers dropped so a quoted example reads as one run of text."""
    text = read(SKILL)
    match = re.search(rf"^{re.escape(heading)}", text, re.MULTILINE)
    assert match, f"discover-paid-apis/SKILL.md has no heading starting {heading!r}"
    return flat(re.sub(r"(?m)^\s*>\s?", "", section_at(text, match.start())))


# --- The budget-claim helper ------------------------------------------------


@pytest.mark.parametrize("sentence", (
    "The MCP `budget` caps every Amazap `buy`.",
    "Amazap never pays out cash, but the MCP `budget` caps every Amazap `buy`.",
    "Amazap credits are not cash; `get_balance()` bounds an Amazap buy.",
    "An Amazap `buy` is never automatic, and `budget(action=\"status\")` caps it.",
))
def test_budget_claims_catches_a_budget_clause_without_a_negation(sentence):
    assert budget_claims(sentence) == [sentence]


@pytest.mark.parametrize("sentence", (
    TWO_WALLET_RULE + ".",
    "Never present `budget` status or `get_balance` as bounding an Amazap buy.",
    "An Amazap `buy` spends credits, and the MCP `budget` never bounds it.",
    "The MCP `budget`, which tracks the MCP wallet, never bounds an Amazap `buy`.",
    "The MCP `budget` caps a direct L402 payment.",
))
def test_budget_claims_passes_a_negated_or_unrelated_budget_clause(sentence):
    assert budget_claims(sentence) == []


# --- The captured-shape fixture ---------------------------------------------


def test_fixture_has_the_products_api_envelope():
    data = fixture()
    assert set(data) == {"products", "total", "limit", "offset"}
    assert data["total"] == len(data["products"])
    assert data["offset"] == 0 and 0 < data["limit"] <= 200


@pytest.mark.parametrize("name", ROW_FIELDS)
def test_every_fixture_row_carries_the_fields_the_skill_reads(name):
    for row in rows():
        field(row, name)  # a KeyError names the missing field


def test_fixture_input_fields_have_the_documented_shape():
    for row in rows():
        for item in row["inputSchema"]["fields"]:
            assert {"name", "type", "required", "in"} <= set(item), item
            assert item["in"] in {"body", "query", "path"}, item


def test_fixture_covers_the_rows_the_skill_must_handle():
    shorts = {row["trust"]["short"] for row in rows()}
    assert {"Verified", "Having trouble"} <= shorts
    assert any(row["buyable"] is False for row in rows())
    assert any(row["buyable"] is True for row in rows())


def test_fixture_total_is_not_always_price_plus_fee():
    # Seen live on 2026-10-12: an all-in total above the seller price plus the
    # fee. This is why the skill shows totalSats and never sums the parts.
    assert any(row["totalSats"] != row["priceSats"] + row["feeSats"] for row in rows())


def test_fixture_uses_placeholder_names():
    for row in rows():
        for key in ("name", "provider", "slug"):
            assert row[key].startswith("fixture-string-"), (key, row[key])
        assert re.match(r"^https://fixture-string-[a-z0-9-]+\.example/", row["endpointUrl"])
