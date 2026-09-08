"""Pin the producer-setup skill to the real `l402_producer` tool surface.

``producer-setup`` is the one skill that drives a multi-action tool through a
long sequence, and a wrong argument name there fails at the worst possible
moment: mid-flow, after the agent has already spent ~100 sats creating an
account. The MCP rejects the call, the agent improvises, and the human is left
with a half-configured merchant.

So the argument names are pinned to the tool's own input schema (see
``l402_producer`` in the Lightning Enable MCP,
``tools/consolidated.py`` for Python and ``Tools/L402ProducerTool.cs`` for
.NET). The Python server takes snake_case and the .NET server takes the
camelCase equivalent of the same name; both spellings are accepted here, since
the skill has to be readable by an agent talking to either.

Two traps this catches:

* ``list_challenges`` filters on **``challenge_status``**, not ``status`` --
  ``status`` is already taken by the action of the same name.
* ``add_endpoint`` takes ``path`` + ``endpoint_id``, not the API's underlying
  ``pathPattern``. The REST body and the tool argument are not the same shape.
"""
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILL = REPO_ROOT / "skills" / "producer-setup" / "SKILL.md"

# The l402_producer input schema, per action. Snake_case is the Python spelling;
# the .NET tool takes the camelCase equivalent, which the test derives.
ARGS_BY_ACTION = {
    "create": {"resource", "price_sats", "description"},
    "verify": {"macaroon", "preimage"},
    "configure_receive": {"nwc_connection_string"},
    "status": {"limit"},
    "create_proxy": {"name", "target_base_url", "description", "default_price_sats"},
    "add_endpoint": {"proxy_id", "endpoint_id", "path", "http_method", "summary", "price_sats"},
    "publish": {"proxy_id", "service_name", "service_description", "categories"},
    "list_challenges": {"challenge_status", "limit", "offset"},
}

# Names that read plausibly but are not on the tool: the REST layer's own field
# names, and the status/challenge_status collision.
NEVER_ON_THE_TOOL = ("path_pattern", "pathPattern", "priority", "targetUrl")

CALL = re.compile(r"l402_producer\(", re.MULTILINE)
ACTION = re.compile(r"""action\s*=\s*["'](\w+)["']""")
KEYWORD = re.compile(r"(\w+)\s*=")


def camel(name: str) -> str:
    head, *rest = name.split("_")
    return head + "".join(word.capitalize() for word in rest)


def accepted(action: str) -> set[str]:
    names = ARGS_BY_ACTION[action]
    return {"action", *names, *(camel(n) for n in names)}


def producer_calls(text: str) -> list[str]:
    """Every ``l402_producer(...)`` call in the file, argument text only."""
    calls = []
    for match in CALL.finditer(text):
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


@pytest.fixture(scope="module")
def skill_text() -> str:
    return SKILL.read_text(encoding="utf-8")


def test_every_documented_call_names_a_real_action(skill_text: str):
    calls = producer_calls(skill_text)
    assert calls, "the skill documents no l402_producer calls -- did the file move?"
    for call in calls:
        action = ACTION.search(call)
        assert action, f"l402_producer call with no action=: {call!r}"
        assert action.group(1) in ARGS_BY_ACTION, (
            f"{action.group(1)!r} is not an l402_producer action. Valid: "
            f"{sorted(ARGS_BY_ACTION)}"
        )


def test_every_documented_argument_is_on_the_tool(skill_text: str):
    for call in producer_calls(skill_text):
        action = ACTION.search(call).group(1)
        allowed = accepted(action)
        used = set(KEYWORD.findall(call))
        unknown = sorted(used - allowed)
        assert not unknown, (
            f"l402_producer action={action} does not take {unknown}. "
            f"It takes: {sorted(allowed - {'action'})}"
        )


def test_the_skill_documents_all_eight_actions(skill_text: str):
    missing = [a for a in ARGS_BY_ACTION if f"action=\"{a}\"" not in skill_text]
    assert not missing, (
        f"producer-setup should name every l402_producer action at least once; "
        f"missing: {missing}"
    )


@pytest.mark.parametrize("name", NEVER_ON_THE_TOOL)
def test_skill_avoids_names_that_are_not_on_the_tool(skill_text: str, name: str):
    assert name not in skill_text, (
        f"{name!r} is a REST-layer field, not an l402_producer argument -- "
        "the tool call would be rejected"
    )


def test_list_challenges_filter_is_challenge_status(skill_text: str):
    # The one collision worth its own test: `status` is an ACTION, so the filter
    # argument had to be renamed. Documenting `status=` here would look right and
    # fail at runtime.
    assert 'challenge_status="paid"' in skill_text or "challenge_status=" in skill_text, (
        "document the list_challenges filter as challenge_status=, never status="
    )


@pytest.mark.parametrize(
    "camel_arg",
    ["nwcConnectionString=", "maxSats=", "perRequest=", "perSession=", "confirmationNonce="],
)
def test_shared_tool_calls_use_the_documented_spelling(skill_text: str, camel_arg: str):
    # The skill declares that it writes the Python server's snake_case argument
    # names, so a camelCase ARGUMENT contradicts its own note. Response FIELDS
    # are camelCase in both packages, which is why the needle carries the "=".
    assert camel_arg not in skill_text, (
        f"{camel_arg} is the .NET spelling; the skill documents snake_case "
        "arguments and maps the camelCase equivalents once, up front"
    )


def test_openapi_url_shape_is_documented(skill_text: str):
    assert "/l402/proxy/" in skill_text and "openapi.json" in skill_text, (
        "publish returns a per-proxy OpenAPI document at "
        "/l402/proxy/{proxyId}/openapi.json -- the skill should say so"
    )
