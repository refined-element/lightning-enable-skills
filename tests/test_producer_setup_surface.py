"""Pin the producer-setup skill to the real `l402_producer` tool surface.

``producer-setup`` is the one skill that drives a multi-action tool through a
long sequence, and a wrong argument name there fails at the worst possible
moment: mid-flow, after the agent has already spent ~100 sats creating an
account. The MCP rejects the call, the agent improvises, and the human is left
with a half-configured merchant.

So the argument names are pinned to the tool's own input schema. The
action-by-action argument check runs over every skill in
``test_tool_arguments_surface.py``, which owns the schema table; this module
holds the assertions that are specific to ``producer-setup``: it names all eight
actions, avoids the REST layer's field names, and spells the shared arguments
the way its own note says.

Two traps this catches:

* ``list_challenges`` filters on **``challenge_status``**, not ``status`` --
  ``status`` is already taken by the action of the same name.
* ``add_endpoint`` takes ``path`` + ``endpoint_id``, not the API's underlying
  ``pathPattern``. The REST body and the tool argument are not the same shape.
"""
from pathlib import Path

import pytest

# The action table lives with the all-skills argument check.
from test_tool_arguments_surface import ARGS_BY_TOOL

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILL = REPO_ROOT / "skills" / "producer-setup" / "SKILL.md"

ARGS_BY_ACTION = ARGS_BY_TOOL["l402_producer"]

# Names that read plausibly but are not on the tool: the REST layer's own field
# names, and the status/challenge_status collision.
NEVER_ON_THE_TOOL = ("path_pattern", "pathPattern", "priority", "targetUrl")


@pytest.fixture(scope="module")
def skill_text() -> str:
    return SKILL.read_text(encoding="utf-8")


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
