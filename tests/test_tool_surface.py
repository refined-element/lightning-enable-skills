"""Pin every skill to the Lightning Enable MCP 2.x tool surface.

Why this exists: MCP 2.0.0 consolidated the one-tool-per-operation surface into
action-based tools and introduced tool profiles. Profiles are listing-only. In
the server source, every pre-2.0 name (``get_budget_status``,
``create_l402_challenge``, ``discover_agent_services``, ...) is a deprecated
alias that still dispatches under every profile, but the server LISTS the old
names only under ``full``. The default profile is ``standard``, which lists only
the 2.x names, and hosts offer an agent only the tools the server lists. A skill
that names an old alias therefore points the agent at a tool it cannot see on a
default install. The aliases are removed in 3.0.0, after which the call fails
under every profile. See "Tool profiles and old tool names" in the MCP README:
https://github.com/refined-element/lightning-enable-mcp#tool-profiles-and-old-tool-names

The canonical inventory is the MCP's own guard tests
(``dotnet/tests/LightningEnable.Mcp.Tests/ToolInventoryTests.cs`` and the
Python ``test_server.py``). The lists below mirror the ``standard`` profile as of
MCP 2.1.0; when the MCP adds or renames a tool, update them from those tests,
never from memory.

Four things are pinned, per skill file:

1. **No banned names.** An old alias anywhere in a ``SKILL.md``, a skill
   ``README.md``, a skill's ``references/*.md``, or the docstrings of a skill's
   ``scripts/*.py`` fails, with the 2.x replacement in the message.
2. **Every skill drives something.** Each ``SKILL.md`` names at least one
   current tool, so a skill that calls nothing cannot ship. Prose is full of
   identifiers, so the test does not try to validate every backticked token.
3. **Action tools carry their discriminator.** ``budget``, ``wallet_ops``,
   ``l402_producer``, and ``agent_services`` take ``action=``; ``receipts``
   takes ``source=``. A call without it, or with a value the tool does not
   accept, is rejected by the server at runtime.
4. **Arguments are snake_case.** Skills write the Python server's argument
   names and say once that the .NET server takes the camelCase equivalents.
   A camelCase argument in a call contradicts that note.

Stdlib + pytest only; CI installs nothing else.
"""
import ast
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIR = REPO_ROOT / "skills"
README = REPO_ROOT / "README.md"

# Old name -> what to write instead. Advertised only by the `full` profile and
# removed in MCP 3.0.0.
BANNED_TOOL_NAMES = {
    "get_budget_status": 'budget(action="status")',
    "configure_budget": 'budget(action="tighten", per_request=..., per_session=...)',
    "check_wallet_balance": "get_balance()",
    "get_all_balances": "get_balance()",
    "get_receipts": 'receipts(source="durable")',
    "get_payment_history": 'receipts(source="session")',
    "confirm_payment": (
        "the confirmation flow: re-call the same payment tool with "
        'confirmation_nonce="<code>" (verify_confirmation_code only verifies)'
    ),
    "create_l402_challenge": 'l402_producer(action="create", resource=..., price_sats=...)',
    "verify_l402_payment": 'l402_producer(action="verify", macaroon=..., preimage=...)',
    "discover_agent_services": 'agent_services(action="discover", ...)',
    "request_agent_service": 'agent_services(action="request", ...)',
    "settle_agent_service": 'agent_services(action="settle", ...)',
    "publish_agent_capability": 'agent_services(action="publish", ...)',
    "unpublish_agent_capability": 'agent_services(action="unpublish", ...)',
    "publish_agent_attestation": 'agent_services(action="attest", ...)',
    "get_agent_reputation": 'agent_services(action="reputation", ...)',
    "get_btc_price": 'wallet_ops(action="price")',
    "exchange_currency": 'wallet_ops(action="exchange", ...)',
    "send_onchain": 'wallet_ops(action="send_onchain", ...)',
}

# `send_onchain` survives as an ACTION of wallet_ops, so it is only banned when
# it is not used as an action: either the value of `action=` / `action: `, or
# prose that names it as one ("the `send_onchain` action").
ALLOWED_AS_ACTION_VALUE = {"send_onchain"}
ACTION_VALUE_PREFIX = re.compile(r"""action[\s=:"'`]*$""")
ACTION_VALUE_SUFFIX = re.compile(r"""^[`'"]?\s+actions?\b""")

# The `standard` profile (the default) as of MCP 2.1.0.
ALLOWED_TOOLS = (
    "setup_wallet",
    "pay_invoice",
    "pay_l402_challenge",
    "access_l402_resource",
    "test_l402_payment",
    "discover_api",
    "create_invoice",
    "check_invoice_status",
    "get_balance",
    "budget",
    "receipts",
    "wallet_ops",
    "verify_confirmation_code",
    "create_lightning_enable_account",
    "renew_lightning_enable_subscription",
    "l402_producer",
    "agent_services",
)

# Action tools: discriminator argument and the values the server accepts
# (ACTION_TOOLS in the MCP's python tools/consolidated.py).
ACTION_TOOLS = {
    "budget": ("action", {"status", "tighten"}),
    "receipts": ("source", {"durable", "session"}),
    "wallet_ops": ("action", {"price", "exchange", "send_onchain"}),
    "l402_producer": (
        "action",
        {
            "create",
            "verify",
            "configure_receive",
            "status",
            "create_proxy",
            "add_endpoint",
            "publish",
            "list_challenges",
        },
    ),
    "agent_services": (
        "action",
        {"discover", "request", "settle", "publish", "unpublish", "attest", "reputation"},
    ),
}

# Digits are in the word class on purpose: `create_l402_challenge` has to match
# as one word.
WORD = "A-Za-z0-9_"


def whole_word(name: str) -> re.Pattern:
    return re.compile(rf"(?<![{WORD}]){re.escape(name)}(?![{WORD}])")


def skill_dirs() -> list[Path]:
    return sorted(p for p in SKILLS_DIR.iterdir() if p.is_dir())


def skill_docs() -> list[Path]:
    """Each skill's SKILL.md and README.md, plus the top-level README."""
    files = [README]
    for skill in skill_dirs():
        files.extend(p for p in (skill / "SKILL.md", skill / "README.md") if p.is_file())
    return files


def scanned_files() -> list[Path]:
    """Everything an agent may read: the docs, reference notes, and scripts."""
    files = skill_docs()
    files.extend(sorted((REPO_ROOT / "references").glob("*.md")))
    for skill in skill_dirs():
        files.extend(sorted((skill / "references").glob("*.md")))
        files.extend(sorted((skill / "scripts").glob("*.py")))
    return files


def scanned_segments(path: Path) -> list[tuple[int, str]]:
    """(first line, text) pairs to scan. A script contributes its docstrings
    only: an agent reads a script's usage text, and code identifiers are not
    tool calls."""
    text = path.read_text(encoding="utf-8")
    if path.suffix != ".py":
        return [(1, text)]
    segments = []
    for node in ast.walk(ast.parse(text)):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            doc = ast.get_docstring(node, clean=False)
            if doc:
                first = node.body[0].lineno if node.body else 1
                segments.append((first, doc))
    return segments


def rel(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT)).replace("\\", "/")


def calls_to(tool: str, text: str) -> list[str]:
    """Argument text of every ``tool(...)`` call in ``text``, parens balanced."""
    calls = []
    for match in re.finditer(rf"(?<![{WORD}]){re.escape(tool)}\(", text):
        depth = 0
        for i in range(match.end() - 1, len(text)):
            if text[i] == "(":
                depth += 1
            elif text[i] == ")":
                depth -= 1
                if depth == 0:
                    calls.append(text[match.end():i])
                    break
    return calls


def without_string_literals(args: str) -> str:
    # A URL or JSON payload inside quotes can contain `name=` pairs that are not
    # tool arguments (`?pageSize=10`).
    return re.sub(r""""[^"]*"|'[^']*'""", '""', args)


@pytest.mark.parametrize("doc", scanned_files(), ids=rel)
def test_no_deprecated_tool_names(doc: Path):
    hits = []
    for first_line, text in scanned_segments(doc):
        for old, replacement in BANNED_TOOL_NAMES.items():
            for match in whole_word(old).finditer(text):
                if old in ALLOWED_AS_ACTION_VALUE and (
                    ACTION_VALUE_PREFIX.search(text[max(0, match.start() - 40):match.start()])
                    or ACTION_VALUE_SUFFIX.search(text[match.end():match.end() + 20])
                ):
                    continue
                line = first_line + text.count("\n", 0, match.start())
                hits.append(f"line {line}: {old} -> use {replacement}")
    assert not hits, (
        f"{rel(doc)} uses MCP tool names that only the deprecated `full` profile "
        "advertises (removed in MCP 3.0.0):\n  " + "\n  ".join(hits)
    )


@pytest.mark.parametrize("skill_dir", skill_dirs(), ids=lambda p: p.name)
def test_skill_names_at_least_one_current_tool(skill_dir: Path):
    skill_file = skill_dir / "SKILL.md"
    assert skill_file.is_file(), f"{skill_dir.name} has no SKILL.md"
    text = skill_file.read_text(encoding="utf-8")
    # A tool counts when it is backticked or called: `get_balance` or
    # budget(...). Bare prose like "the budget" does not count.
    named = sorted(
        tool
        for tool in ALLOWED_TOOLS
        if re.search(rf"(?<![{WORD}]){re.escape(tool)}(?=[`(])", text)
    )
    assert named, (
        f"{skill_dir.name}/SKILL.md names no current Lightning Enable MCP tool. "
        f"A skill must drive at least one of: {', '.join(ALLOWED_TOOLS)}"
    )


@pytest.mark.parametrize("doc", skill_docs(), ids=rel)
def test_action_tool_calls_carry_a_valid_discriminator(doc: Path):
    text = doc.read_text(encoding="utf-8")
    problems = []
    for tool, (discriminator, values) in ACTION_TOOLS.items():
        for args in calls_to(tool, text):
            found = re.search(rf"""(?<![{WORD}]){discriminator}\s*=\s*["'](\w+)["']""", args)
            if not found:
                hint = ""
                if tool == "receipts" and re.search(r"(?<![A-Za-z0-9_])action\s*=", args):
                    hint = " (receipts takes source=, not action=)"
                problems.append(f"{tool}({args.strip()}) has no {discriminator}=...{hint}")
            elif found.group(1) not in values:
                problems.append(
                    f"{tool}({args.strip()}): {discriminator}={found.group(1)!r} is not one "
                    f"of {sorted(values)}"
                )
    assert not problems, f"{rel(doc)}:\n  " + "\n  ".join(problems)


@pytest.mark.parametrize("doc", skill_docs(), ids=rel)
def test_tool_call_arguments_are_snake_case(doc: Path):
    text = doc.read_text(encoding="utf-8")
    problems = []
    for tool in ALLOWED_TOOLS:
        for args in calls_to(tool, text):
            for name in re.findall(r"([A-Za-z_][A-Za-z0-9_]*)\s*=", without_string_literals(args)):
                if any(ch.isupper() for ch in name):
                    problems.append(f"{tool}(... {name}= ...)")
    assert not problems, (
        f"{rel(doc)} writes camelCase tool arguments: {sorted(set(problems))}. "
        "Skills use the Python server's snake_case names and note once that the "
        ".NET server takes the camelCase equivalents."
    )
