"""Pin every skill's multi-action tool calls to the tools' real input schemas.

``l402_producer`` and ``agent_services`` each take one ``action`` and a flat bag
of optional arguments, each tagged in the schema with the actions that read it.
A wrong argument name fails at the worst moment: mid-flow, after the agent may
already have spent sats. The MCP rejects the call, the agent improvises, and the
human is left with a half-configured merchant or a half-finished purchase.

So every ``l402_producer(...)`` and ``agent_services(...)`` call written in any
skill file (``SKILL.md``, ``README.md``, ``references/*.md``, and the top-level
``README.md``) is checked, action by action, against the argument sets below.
They mirror the tools' own input schemas in the Lightning Enable MCP:
``tools/consolidated.py`` for Python, and ``Tools/L402ProducerTool.cs`` and
``Tools/AgentServicesTool.cs`` for .NET. The Python server takes snake_case and
the .NET server takes the camelCase equivalent of the same name; both spellings
are accepted here, since a skill has to be readable by an agent talking to
either. When the MCP changes a schema, update these sets from that source,
never from memory.

The ``producer-setup``-specific assertions (all eight actions documented, the
``challenge_status`` collision, REST-only field names) live in
``test_producer_setup_surface.py``.
"""
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIR = REPO_ROOT / "skills"
README = REPO_ROOT / "README.md"

# Per action, the arguments the schema tags with that action (snake_case).
ARGS_BY_TOOL = {
    "l402_producer": {
        "create": {"resource", "price_sats", "description"},
        "verify": {"macaroon", "preimage"},
        "configure_receive": {"nwc_connection_string"},
        "status": {"limit"},
        "create_proxy": {"name", "target_base_url", "description", "default_price_sats"},
        "add_endpoint": {
            "proxy_id",
            "endpoint_id",
            "path",
            "http_method",
            "summary",
            "price_sats",
        },
        "publish": {"proxy_id", "service_name", "service_description", "categories"},
        "list_challenges": {"challenge_status", "limit", "offset"},
    },
    "agent_services": {
        "discover": {"category", "query", "hashtags", "limit"},
        "request": {"capability_event_id", "budget_sats", "parameters"},
        # confirmation_nonce is on the Python schema only; the .NET tool has no
        # confirmation parameter for agent_services.
        "settle": {
            "l402_endpoint",
            "method",
            "body",
            "agreement_id",
            "max_sats",
            "confirmation_nonce",
        },
        "publish": {
            "service_id",
            "content",
            "categories",
            "hashtags",
            "price_sats",
            "target_url",
            "l402_endpoint",
        },
        "unpublish": {"service_id", "reason"},
        "attest": {"subject_pubkey", "agreement_id", "rating", "content", "proof"},
        "reputation": {"pubkey", "limit"},
    },
}

ACTION = re.compile(r"""(?<![A-Za-z0-9_])action\s*=\s*["'](\w+)["']""")
KEYWORD = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)\s*=")


def camel(name: str) -> str:
    head, *rest = name.split("_")
    return head + "".join(word.capitalize() for word in rest)


def accepted(tool: str, action: str) -> set[str]:
    names = ARGS_BY_TOOL[tool][action]
    return {"action", *names, *(camel(n) for n in names)}


def calls_to(tool: str, text: str) -> list[str]:
    """Argument text of every ``tool(...)`` call in ``text``, parens balanced."""
    calls = []
    for match in re.finditer(rf"(?<![A-Za-z0-9_]){re.escape(tool)}\(", text):
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
    # A URL or JSON payload inside quotes can hold `name=` pairs that are not
    # tool arguments (`?url=`).
    return re.sub(r""""[^"]*"|'[^']*'""", '""', args)


def skill_docs() -> list[Path]:
    files = [README]
    for skill in sorted(p for p in SKILLS_DIR.iterdir() if p.is_dir()):
        files.extend(p for p in (skill / "SKILL.md", skill / "README.md") if p.is_file())
        files.extend(sorted((skill / "references").glob("*.md")))
    return files


def rel(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT)).replace("\\", "/")


@pytest.mark.parametrize("doc", skill_docs(), ids=rel)
def test_multi_action_tool_calls_use_real_actions_and_arguments(doc: Path):
    text = doc.read_text(encoding="utf-8")
    problems = []
    for tool, actions in ARGS_BY_TOOL.items():
        for call in calls_to(tool, text):
            found = ACTION.search(call)
            if not found:
                # test_tool_surface.py reports a missing discriminator; nothing
                # here can be checked without one.
                continue
            action = found.group(1)
            if action not in actions:
                problems.append(
                    f"{tool}: {action!r} is not an action. Valid: {sorted(actions)}"
                )
                continue
            used = set(KEYWORD.findall(without_string_literals(call)))
            unknown = sorted(used - accepted(tool, action))
            if unknown:
                problems.append(
                    f"{tool} action={action} does not take {unknown}. "
                    f"It takes: {sorted(ARGS_BY_TOOL[tool][action])}"
                )
    assert not problems, f"{rel(doc)}:\n  " + "\n  ".join(problems)


def test_the_suite_sees_calls_to_both_tools():
    # If a refactor moved every call out of reach (a renamed folder, a new file
    # extension), the parametrized test above would pass on nothing.
    corpus = "\n".join(p.read_text(encoding="utf-8") for p in skill_docs())
    for tool in ARGS_BY_TOOL:
        assert calls_to(tool, corpus), f"no {tool}(...) call found in any skill file"
