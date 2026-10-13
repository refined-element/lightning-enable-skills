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
longer exists. ``fixtures/amazap-product-detail.json`` holds two bodies of
``GET https://amazap.com/api/products/<slug>``, each wrapping one row in
``product``: a paused row that search also listed, and, marked by a ``note``, a
row hidden from search (``hidden: true``) in a shape observed earlier the same
day. Search has done both, so the skill handles both.
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
DETAIL_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "amazap-product-detail.json"

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
# The spec's trust labels. A live trust.label leads with one of these and can
# add detail after a ":" or "," ("Verified: delivered 6 times").
TRUST_LABELS = ("Verified", "Working", "Limited track record", "Having trouble")
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


def detail_examples() -> list[dict]:
    return json.loads(DETAIL_FIXTURE.read_text(encoding="utf-8"))


def detail_rows() -> list[dict]:
    return [example["product"] for example in detail_examples()]


def all_rows() -> list[dict]:
    """Every captured row: the search sample and the detail bodies."""
    return rows() + detail_rows()


def leading_label(label: str) -> str:
    """The part of a trust.label before any ":" or ","."""
    return re.split(r"[:,]", label, maxsplit=1)[0].strip()


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
    for row in all_rows():
        field(row, name)  # a KeyError names the missing field


def test_fixture_input_fields_have_the_documented_shape():
    for row in all_rows():
        for item in row["inputSchema"]["fields"]:
            assert {"name", "type", "required", "in"} <= set(item), item
            assert item["in"] in {"body", "query", "path"}, item


def test_every_trust_label_leads_with_a_spec_value():
    for row in all_rows():
        label = row["trust"]["label"]
        assert leading_label(label) in TRUST_LABELS, label


def test_fixture_covers_the_rows_the_skill_must_handle():
    # Search may list a paused or degraded row, so the skill reads
    # listingState and buyable on every row instead of trusting search.
    leads = {leading_label(row["trust"]["label"]) for row in rows()}
    assert {"Verified", "Having trouble"} <= leads
    # Every live Verified label carried detail as of 2026-10-12; quote it whole, never trimmed.
    labels = [row["trust"]["label"] for row in rows()]
    assert any(leading_label(label) == "Verified" and label != "Verified" for label in labels)
    assert any(row["buyable"] is False and row["listingState"] == "paused" for row in rows())
    assert any(row["buyable"] is True for row in rows())


def test_detail_fixture_wraps_each_row_in_product():
    examples = detail_examples()
    assert len(examples) == 2
    for example in examples:
        assert set(example) <= {"product", "note"}, example.keys()
        assert isinstance(example["product"], dict)


def test_detail_fixture_covers_a_listed_paused_row_and_a_hidden_one():
    listed, hidden = detail_examples()
    # As observed late on 2026-10-12: a paused row search also lists.
    assert "note" not in listed
    assert listed["product"]["hidden"] is False and listed["product"]["listingState"] == "paused"
    assert listed["product"]["slug"] in {row["slug"] for row in rows()}
    # As observed earlier the same day: absent from search, returned by slug.
    assert hidden["note"].strip() and "hidden: true" in hidden["note"]
    assert hidden["product"]["hidden"] is True and hidden["product"]["buyable"] is False
    assert hidden["product"]["slug"] not in {row["slug"] for row in rows()}


def test_fixture_total_is_not_always_price_plus_fee():
    # Seen live on 2026-10-12: an all-in total above the seller price plus the
    # fee. This is why the skill shows totalSats and never sums the parts.
    assert any(row["totalSats"] != row["priceSats"] + row["feeSats"] for row in rows())


def test_fixture_uses_placeholder_names():
    for row in all_rows():
        for key in ("name", "provider", "slug"):
            assert row[key].startswith("fixture-string-"), (key, row[key])
        assert re.match(r"^https://fixture-string-[a-z0-9-]+\.example/", row["endpointUrl"])


# --- The shared reference: buyer rules and two wallets ----------------------


def discovery_section() -> str:
    return flat(reference_section("## Discovery versus purchase"))


def wallets_section() -> str:
    return reference_section("## Two wallets")


@pytest.mark.parametrize("phrase", (
    "Amazap does not replace the Lightning Enable registry",
    "Search, describe, and quote never spend.",
    "`totalSats`, the figure the buyer pays",
    "never add the seller price and the fee yourself",
    "`trust.label`",
    "A hidden row is not a candidate; never fetch one by slug to show or buy it.",
    "read `listingState` and `buyable` on every row",
    "can also be hidden from search and still be returned by",
    "That detail response wraps the row in `product`.",
    NON_GOAL,
    "never present a listing's `endpointUrl` as a cheaper way to pay the seller",
    "show each row as its source returned it",
    DIRECT_PAY_SCOPE,
    "`quote_id`, `total_cost`, `max_total_sats`, and `accept_terms`",
    "the current Amazap terms (https://amazap.com/terms)",
    "A stale quote returns a fresh quote in the error and charges nothing",
    "Repeating a `quote_id` never charges twice.",
    "A basket is one buy.",
    "`approval_required`",
    "re-credits a failed paid call as Amazap credits, never cash",
    "`claim_failed_call` within the window Amazap states (see https://amazap.com/credits)",
    SENSITIVE,
    "At most one trial purchase per run",
    "(../skills/discover-paid-apis/)",
))
def test_reference_states_the_buyer_rules(phrase):
    assert phrase in discovery_section(), f"Discovery versus purchase is missing {phrase!r}"


def test_reference_no_longer_defers_the_buyer_rules():
    assert "belong with the buyer skill that adopts it" not in flat(read(REFERENCE))


@pytest.mark.parametrize("phrase", (
    CAP_RULE,
    "`max_total_sats`",
    "Never present `budget` status or `get_balance` as bounding an Amazap buy.",
    "`balance` and `spend_summary`",
    "auto-approve amount",
))
def test_reference_two_wallets_names_the_cap_for_each_path(phrase):
    assert phrase in flat(wallets_section()), f"Two wallets is missing {phrase!r}"


def test_reference_cap_table_has_a_row_per_path():
    rows_by_path = {row[0]: row for row in table_rows(wallets_section())}
    amazap = rows_by_path.get("Amazap `buy`")
    assert amazap and "`max_total_sats`" in amazap[2] and "Amazap account limits" in amazap[2]
    direct = [row for path, row in rows_by_path.items() if "`access_l402_resource`" in path]
    assert direct and "MCP `budget` limits" in direct[0][2]
    # The direct path is for a registry result or a URL the user already has,
    # never for a listing Amazap surfaced.
    assert "Lightning Enable registry result" in direct[0][0]
    assert "a URL the user already has" in direct[0][0]


def test_reference_keeps_the_claim_window_in_the_dated_note():
    # The re-credit window is Amazap's figure: dated note only.
    assert "72" not in discovery_section()
    assert "72-hour window for `claim_failed_call`" in flat(reference_section("## Observed on 2026-10-12"))


def test_reference_keeps_the_mcp_budget_off_every_amazap_row():
    hits = amazap_rows_with_the_mcp_budget(read(REFERENCE))
    assert not hits, f"an Amazap row names the MCP budget: {hits}"


def test_reference_never_says_the_mcp_budget_bounds_an_amazap_buy():
    hits = budget_claims(read(REFERENCE))
    assert not hits, f"the MCP budget never bounds an Amazap buy: {hits}"


# --- The skill: search and compare ------------------------------------------


def test_description_names_both_sources_and_keeps_the_routing():
    front = test_skill_metadata.parse_frontmatter(read(SKILL))
    description = front["description"]
    for phrase in (
        "Lightning Enable registry and Amazap",
        "label each source",
        "at most one bounded trial purchase",
        "(use pay-l402-anywhere)",
        "(use cited-answer)",
        "(use agent-wallet-setup)",
    ):
        assert phrase in description, f"the description is missing {phrase!r}"


def test_skill_links_the_reference_sections_and_live_pages():
    text = read(SKILL)
    missing = [url for url in (*REFERENCE_LINKS, *LIVE_LINKS) if url not in text]
    assert not missing, f"discover-paid-apis must link {missing}"


@pytest.mark.parametrize("phrase", (
    "`discover_api`",
    "`search_catalog`",
    "GET https://amazap.com/api/products",
    "GET https://amazap.com/api/products/<idOrSlug>",
    "Amazap does not replace the Lightning Enable registry",
    "**Label every row** with its source",
    "Run at least one refinement",
    "Searching never spends.",
    "Page with `offset` until `offset >= total`.",
    "`limit` (at most 200)",
    "This path reads; it can't buy.",
    "Don't fetch one by slug to work around that.",
    "A row can also be hidden from search and still be returned by slug",
    "read `listingState`, `healthStatus`, and `buyable` on every row",
    "Never frame a price difference as a reason to bypass Amazap.",
    NON_GOAL,
    DIRECT_PAY_SCOPE,
    # search_catalog hands back a ready buy call; searching must not run it.
    "Do not run that buy call; `buy` waits for the trial step and the human's yes.",
    "Stop sooner once you have enough relevant rows to pick five.",
    "**Paused, degraded, or failing rows are shown, not bought.**",
    "**Hidden rows are dropped.**",
))
def test_search_reads_both_sources_and_labels_every_row(phrase):
    assert phrase in skill_section("### 2. Search both sources"), f"step 2 is missing {phrase!r}"


@pytest.mark.parametrize("param", PRODUCTS_PARAMS)
def test_public_search_names_every_documented_parameter(param):
    assert f"`{param}`" in skill_section("### 2. Search both sources")


def test_amazap_tools_are_named_only_when_the_host_lists_them():
    text = flat(read(SKILL))
    for phrase in (
        "only when the host lists them",
        "Never claim Amazap MCP access you don't have.",
        "Amazap search uses the public products API",
        "https://amazap.com/mcp",
        "governed by the current Amazap credit terms (https://amazap.com/credits)",
    ):
        assert phrase in text, f"discover-paid-apis is missing {phrase!r}"


@pytest.mark.parametrize("tool", AMAZAP_TOOLS)
def test_skill_names_each_amazap_tool(tool):
    assert f"`{tool}`" in read(SKILL), f"discover-paid-apis never names `{tool}`"


@pytest.mark.parametrize("name", ROW_FIELDS)
def test_comparison_reads_every_row_field(name):
    assert f"`{name}" in skill_section("### 3. Compare at most five candidates"), (
        f"step 3 never reads `{name}`"
    )


@pytest.mark.parametrize("phrase", (
    "Show at most five candidates",
    "| Source |",
    "with a one-sentence reason",
    "Prefer a reliable, clearly specified service over the cheapest.",
    "never on the price difference between the rows",
    "`totalSats`, the all-in figure the buyer pays",
    "Never add `priceSats` and the fee yourself",
    "quote required",
    "Quote `trust.label` as returned",
    "Never upgrade a label.",
    "`buyable: false`, and never buy it",
    "drop any row with `hidden: true`",
    # The trust.label prefixes are observed values, not a closed list.
    "For example, it may start with Verified",
    "Say who receives the input",
    "never as free or unlimited",
))
def test_comparison_rules(phrase):
    assert phrase in skill_section("### 3. Compare at most five candidates"), (
        f"step 3 is missing {phrase!r}"
    )


def test_endpoint_url_appears_only_in_a_prohibition():
    sentences = [s for s in prose_sentences(read(SKILL)) if "endpointUrl" in s]
    assert sentences, "say plainly that a listing's endpointUrl is never a way to pay directly"
    loose = [s for s in sentences if not NEGATION.search(s)]
    assert not loose, f"endpointUrl outside a prohibition: {loose}"


@pytest.mark.parametrize("doc", GUARDED_DOCS, ids=lambda p: p.name)
def test_doc_carries_the_custody_sentence(doc):
    assert CUSTODY in flat(read(doc))


@pytest.mark.parametrize("doc", GUARDED_DOCS, ids=lambda p: p.name)
def test_doc_has_no_em_dashes_or_banned_words(doc):
    text = read(doc)
    assert EM_DASH not in text, f"{doc.name} uses an em-dash"
    hits = [word for word in BANNED_WORDS if word in text.lower()]
    assert not hits, f"{doc.name} uses {hits}"


@pytest.mark.parametrize("doc", GUARDED_DOCS, ids=lambda p: p.name)
def test_doc_hard_codes_no_amazap_figures(doc):
    hits = AMAZAP_FIGURE.findall(flat(read(doc)))
    assert not hits, (
        f"{doc.name} hard-codes {hits}; Amazap's fees, limits, and counts are "
        "read live, and dated figures live only in the shared reference"
    )


@pytest.mark.parametrize("doc", GUARDED_DOCS, ids=lambda p: p.name)
def test_doc_never_calls_a_listing_verified(doc):
    # Amazap's "Verified" label is quoted with a capital V; a lowercase
    # "verified" would be this skill's own claim, which it never makes.
    hits = LOOSE_VERIFIED.findall(flat(read(doc)))
    assert not hits, f"{doc.name} makes a 'verified' claim"


def test_trust_bullet_says_quote_as_returned_once():
    step = skill_section("### 3. Compare at most five candidates")
    assert "so quote it as returned" not in step, "say 'Quote `trust.label` as returned' once"


# --- The skill: quote, one bounded trial, receipt, failures -----------------


def test_quote_states_the_cap_for_each_path():
    step = skill_section("### 5. Quote, and state the cap that applies")
    assert CAP_RULE in step
    assert TWO_WALLET_RULE in step
    assert "Never present `budget` status or `get_balance` as bounding an Amazap buy." in step
    rows_by_path = {row[0]: row for row in table_rows(read(SKILL))}
    amazap = rows_by_path.get("Amazap `buy`")
    assert amazap and "`max_total_sats`" in amazap[2] and "Amazap account limits" in amazap[2]
    direct = rows_by_path.get("Lightning Enable registry result paid directly")
    assert direct and "MCP `budget` limits" in direct[2]


@pytest.mark.parametrize("doc", GUARDED_DOCS, ids=lambda p: p.name)
def test_mcp_budget_never_bounds_an_amazap_buy(doc):
    text = read(doc)
    assert not budget_claims(text), f"{doc.name}: {budget_claims(text)}"
    assert not amazap_rows_with_the_mcp_budget(text), (
        f"{doc.name}: an Amazap row names the MCP budget: {amazap_rows_with_the_mcp_budget(text)}"
    )


def test_over_cap_quote_is_refused():
    step = skill_section("### 5. Quote, and state the cap that applies")
    assert "above the lowest cap that applies to its path, refuse and buy nothing" in step
    assert "A 31-sat quote against a 30-sat cap is a refusal" in step
    assert "Search, describe, and quote never spend." in step


@pytest.mark.parametrize("phrase", (
    "Read the Amazap account limits and its auto-approve amount from `balance` or `spend_summary`",
    "never hard-code them",
    "or `buy` returns `approval_required` and charges nothing",
))
def test_quote_reads_the_amazap_limits_live(phrase):
    step = skill_section("### 5. Quote, and state the cap that applies")
    assert phrase in step, f"step 5 is missing {phrase!r}"


@pytest.mark.parametrize("phrase", (
    "At most one trial purchase per run, unless the user explicitly asks for more.",
    "the all-in total is within the lowest cap that applies to its path",
    "the service is buyable",
    "**stop for a yes**",
    "this skill still asks the user first",
    "set `max_total_sats` to the user's cap",
    "Set `accept_terms` only after showing the current Amazap terms",
    "https://amazap.com/terms",
    "the stale attempt charged nothing",
    "Show the fresh quote from the error",
    "Never buy on the fresh quote automatically.",
    "`approval_required`",
    "Stop, and ask the person to confirm the exact quote in Amazap",
    "Never re-quote or split the purchase to get around it.",
    "Repeating a `quote_id` never charges twice",
    "A basket is one buy.",
    "ask before `top_up`",
    "never copy the invoice into your own message",
    "Never point it at an Amazap listing's `endpointUrl`.",
))
def test_trial_purchase_rules(phrase):
    assert phrase in skill_section("### 6. Buy one trial"), f"step 6 is missing {phrase!r}"


@pytest.mark.parametrize("phrase", (
    # Step 2 shows paused or degraded rows and never buys them, whatever
    # `buyable` says.
    "A paused or degraded row stays unbought this run, even with `buyable: true`, and so does a failing one.",
    # A stale quote's fresh quote is a new price: the cap and a new yes apply.
    "its total is still within the cap",
))
def test_trial_purchase_respects_listing_state_and_the_cap(phrase):
    assert phrase in skill_section("### 6. Buy one trial"), f"step 6 is missing {phrase!r}"


def test_buy_call_carries_the_four_required_arguments():
    calls = test_tool_surface.calls_to("buy", read(SKILL))
    assert calls, "show the buy call"
    for argument in ("quote_id=", "total_cost=", "max_total_sats=<the user's cap>", "accept_terms="):
        assert all(argument in call for call in calls), f"every buy call needs {argument}"


@pytest.mark.parametrize("phrase", (
    "Never send secrets, private URLs, authenticated pages, credentials, personal data, or proprietary content",
    "unless the user explicitly approved that disclosure",
    "don't send it",
    "buy nothing",
))
def test_sensitive_input_is_never_sent_without_approval(phrase):
    assert phrase in skill_section("### 4. Read the details, unpaid"), f"step 4 is missing {phrase!r}"


PAYING_CALLS = ("access_l402_resource", "buy", "pay_l402_challenge", "pay_invoice", "top_up")
UNPAID_STEPS = (
    "### 0. Ask what the human wants",
    "### 1. Check the tools and the MCP leash",
    "### 2. Search both sources",
    "### 3. Compare at most five candidates",
    "### 4. Read the details, unpaid",
    "### 5. Quote, and state the cap that applies",
)


@pytest.mark.parametrize("heading", UNPAID_STEPS)
def test_steps_before_the_trial_make_no_call_that_can_pay(heading):
    # Step 0 promises that steps 1 to 5 need no yes, so none of them may call
    # a tool that can spend, not even with a 1-sat cap.
    step = skill_section(heading)
    calls = {tool: test_tool_surface.calls_to(tool, step) for tool in PAYING_CALLS}
    assert not any(calls.values()), f"{heading} calls a tool that can pay: {calls}"


def test_reading_details_uses_only_read_only_tools():
    step = skill_section("### 4. Read the details, unpaid")
    assert 'discover_api(url="<manifest_url>")' in step
    assert "Never read it with `access_l402_resource`" in step
    assert not re.search(r"max_sats=1\b", read(SKILL)), "no 1-sat fetch: reading a document never pays"


def test_step_references_match_the_numbering():
    assert "steps 1 to 5 need no yes. Step 6 pays, and needs its own yes." in skill_section(
        "### 0. Ask what the human wants"
    )
    assert "Step 5 states the caps" in skill_section("### 3. Compare at most five candidates")
    assert "| Path | Wallet | Caps that apply |" in skill_section(
        "### 5. Quote, and state the cap that applies"
    )
    assert "(step 6 has the table)" in flat(read(SKILL))
    assert "| | Python server | .NET server |" in skill_section("### 6. Buy one trial")


def test_old_steps_are_gone():
    text = read(SKILL)
    for heading in (
        "### 4. Read the manifest, unpaid",
        "### 5. Confirm, then make ONE paid call",
        "### 6. Show the result and the spend",
        "### 7. Hand off",
    ):
        assert heading not in text, f"the old heading {heading!r} is still there"
    headings = re.findall(r"^### (\d+)\. ", text, re.MULTILINE)
    assert headings == [str(n) for n in range(10)], f"steps run 0 to 9 once each: {headings}"


def test_tool_arguments_use_the_pinned_spellings():
    text = read(SKILL)
    for tool, allowed in (("discover_api", DISCOVER_API_ARGS), ("access_l402_resource", ACCESS_ARGS)):
        calls = test_tool_surface.calls_to(tool, text)
        assert calls, f"no {tool}(...) call"
        for call in calls:
            used = set(KEYWORD.findall(test_tool_surface.without_string_literals(call)))
            assert used <= allowed, f"{tool}({call}) uses {sorted(used - allowed)}"
            assert "amazap" not in call.lower(), f"{tool} never targets an Amazap listing"


@pytest.mark.parametrize("phrase", (
    "the sats charged",
    "the remaining Amazap credits or the remaining MCP budget, whichever wallet paid",
    "the source, the provider, and the listing used",
    "an order or receipt id safe to keep",
    "whether fulfillment succeeded",
    SECRETS,
    "offer `report_outcome`, with the user's approval",
))
def test_receipt_reports_spend_and_delivery_without_secrets(phrase):
    assert phrase in skill_section("### 7. Report the receipt"), f"step 7 is missing {phrase!r}"


def test_receipt_reports_the_all_in_charge():
    assert "the sats charged, all-in" in skill_section("### 7. Report the receipt")


@pytest.mark.parametrize("kind", FAILURE_KINDS)
def test_failure_kinds_are_distinguished(kind):
    assert kind in skill_section("### 8. When a paid trial fails"), f"step 8 never names {kind!r}"


@pytest.mark.parametrize("phrase", (
    "Never buy a second candidate after a paid failure without asking.",
    "Ask before trying another paid listing.",
    "re-credited as Amazap credits, never cash",
    "`claim_failed_call`",
    # The claim window is Amazap's figure: read it from the live credit terms.
    "within the window the current Amazap credit terms state",
    "`report_sku`",
    "never replaced by a second one",
))
def test_paid_failure_never_triggers_a_second_buy(phrase):
    assert phrase in skill_section("### 8. When a paid trial fails"), f"step 8 is missing {phrase!r}"


def test_claim_window_is_never_hard_coded():
    # The reference keeps the observed window in its dated note only.
    assert not re.search(r"\b\d+[- ]hours?\b", flat(read(SKILL))), "read the claim window live"


def test_known_url_hands_off_to_pay_l402_anywhere():
    step = skill_section("### 9. Hand off")
    assert "**A URL the user already has:** [`pay-l402-anywhere`](../pay-l402-anywhere/)" in step
    assert "not to listings Amazap surfaced" in step


# --- Fix round 1: top-ups, direct-path stops, row state, yes, one cap name --


@pytest.mark.parametrize("phrase", (
    "The human chooses the top-up amount.",
    "it is a separate payment with `pay_invoice`, and the human says yes to that exact amount first",
    "The user's cap doesn't cover a top-up",
    "The MCP `budget` limits do bound that payment",
))
def test_top_up_paid_from_the_mcp_wallet_is_its_own_payment(phrase):
    assert phrase in skill_section("### 6. Buy one trial"), f"step 6 is missing {phrase!r}"


@pytest.mark.parametrize("phrase", (
    "Set `max_sats` to the listed price, never above the user's cap.",
    "Never guess one.",
    "Don't retry with a smaller `max_sats` to squeeze under a cap.",
    "**Do not pay again**",
))
def test_direct_path_stops(phrase):
    assert phrase in skill_section("### 6. Buy one trial"), f"step 6 is missing {phrase!r}"


def test_comparison_shows_unhealthy_rows_as_not_buyable():
    step = skill_section("### 3. Compare at most five candidates")
    assert 'Show "no" for a paused, degraded, or failing row, even when `buyable` is true.' in step
    assert "`healthStatus`, and `hidden`" in step


@pytest.mark.parametrize("phrase", (
    "state the fresh total and get a new yes before buying with its `quote_id` and `total_cost`",
    "The first yes never covers a different total.",
))
def test_stale_quote_needs_a_new_yes(phrase):
    assert phrase in skill_section("### 6. Buy one trial"), f"step 6 is missing {phrase!r}"


@pytest.mark.parametrize("phrase", (
    "For an Amazap buy, the same yes also covers the current Amazap terms.",
    "Do you accept them and go ahead?",
    'A bare "Go ahead?" is never consent to the terms, so it never sets `accept_terms`.',
    "That call arrives with `accept_terms` and `max_total_sats` already filled in; never send it as it came.",
    "getting the user's agreement in the same yes as the purchase",
))
def test_the_yes_covers_the_amazap_terms(phrase):
    assert phrase in skill_section("### 6. Buy one trial"), f"step 6 is missing {phrase!r}"


def test_unclear_outcome_is_checked_before_any_retry():
    assert (
        "When the outcome is unclear (a dropped connection, a timeout), check before any "
        "retry: `get_order` or `orders` shows whether the buy went through."
    ) in skill_section("### 6. Buy one trial")
    assert (
        "Check it before any retry: `get_order` or `orders` on the Amazap path, "
        '`receipts(source="session")` on the direct path.'
    ) in skill_section("### 8. When a paid trial fails")


def test_one_name_for_the_cap():
    text = flat(read(SKILL))
    assert "ceiling" not in text.lower(), "call it the user's cap, never a trial ceiling"
    assert "stated cap" not in text, "call it the user's cap"
    assert "**The user's cap:**" in skill_section("### 0. Ask what the human wants")
