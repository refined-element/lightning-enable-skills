"""Text guards for the l402-compatibility-report SKILL.md and README.md."""
import re

import pytest

import l402_check_support as support
import test_skill_metadata
import test_tool_surface
from test_shared_references import (
    CLASSIFICATION_PATTERN,
    CLASSIFICATIONS,
    CUSTODY,
    PROFILES_HEADING,
    section_text,
    without_section,
)

SKILL = support.SKILL_DIR / "SKILL.md"
README = support.SKILL_DIR / "README.md"
SHARED_REFERENCE = support.REPO_ROOT / "references" / "l402-verification-levels.md"
REFERENCE_URL = "https://github.com/refined-element/lightning-enable-skills/blob/main/references/l402-verification-levels.md"


def flat(path):
    return " ".join(path.read_text(encoding="utf-8").split())


def test_skill_names_exactly_the_five_classifications():
    core = without_section(SKILL.read_text(encoding="utf-8"), PROFILES_HEADING)
    named = set(re.findall(CLASSIFICATION_PATTERN, core))
    assert named == set(CLASSIFICATIONS)
    assert "MARKETPLACE_READY" not in core


@pytest.mark.parametrize("path", (SKILL, README), ids=lambda p: p.name)
def test_custody_sentence(path):
    assert CUSTODY in flat(path)


@pytest.mark.parametrize("path", (SKILL, README), ids=lambda p: p.name)
def test_l402_verified_appears_only_as_a_prohibition(path):
    text = flat(path)
    for match in re.finditer(r"L402 verified", text, flags=re.IGNORECASE):
        assert "never" in text[max(0, match.start() - 60):match.start()].lower()


def test_paid_check_is_one_capped_access_l402_resource_call():
    text = flat(SKILL)
    calls = re.findall(r"access_l402_resource\(([^`]*?)\)(?:`|\s|,|$)", text)
    assert calls
    for call in calls:
        # The paid call repeats the checked request: the same url and method, and a cap.
        assert re.match(r'url="[^"]+", method="[^"]+", ', call), call
        assert "max_sats=" in call, call
    assert re.search(r'access_l402_resource\(url="[^"]+", method="[^"]+", headers=\{', text)
    assert "GET or HEAD" in text
    assert "Never start a second payment" in text
    assert "stop for a yes" in text


def test_read_only_check_is_the_default_and_never_pays():
    text = flat(SKILL)
    assert "The default check never pays." in text
    assert "--allow-private" in text


def test_skill_links_the_shared_reference():
    assert (support.REPO_ROOT / "references" / "l402-verification-levels.md").is_file()
    assert REFERENCE_URL in SKILL.read_text(encoding="utf-8")


def test_every_script_is_scanned_by_the_tool_surface_guard():
    scanned = set(test_tool_surface.scanned_files())
    for script in sorted(support.SCRIPTS.glob("*.py")):
        assert script in scanned


# --- Branding: the Lightning Enable L402 compatibility report ----------------


def test_skill_and_readme_brand_the_lightning_enable_report():
    assert "\n# Lightning Enable L402 compatibility report\n" in SKILL.read_text(encoding="utf-8")
    assert "The Lightning Enable L402 compatibility report" in flat(README)


def test_shared_reference_names_the_lightning_enable_report():
    assert "the Lightning Enable L402 compatibility report" in flat(SHARED_REFERENCE)


def test_skill_intro_first_sentence_names_lightning_enable():
    # The first sentence after the title names Lightning Enable, so an agent
    # reading top-down knows whose capability this is before anything else.
    body = SKILL.read_text(encoding="utf-8").split("\n# Lightning Enable L402 compatibility report\n", 1)[1]
    first_sentence = " ".join(body.split())
    first_sentence = first_sentence[:first_sentence.index(". ") + 1]
    assert "Lightning Enable" in first_sentence, first_sentence


def test_description_leads_with_l402_correctness_not_a_marketplace():
    description = test_skill_metadata.parse_frontmatter(SKILL.read_text(encoding="utf-8"))["description"]
    assert description.startswith("Run the Lightning Enable L402 compatibility report")
    assert "Optional marketplace profiles are reported separately and never change the result." in description
    assert "Amazap" not in description


# --- Marketplace profiles stay optional and in their own section --------------


def test_marketplace_ready_and_profile_statuses_appear_only_in_the_profiles_section():
    text = SKILL.read_text(encoding="utf-8")
    outside = without_section(text, PROFILES_HEADING)
    assert "MARKETPLACE_READY" not in outside
    assert "NOT_READY" not in outside
    section = " ".join(section_text(text, PROFILES_HEADING).split())
    for phrase in ("`MARKETPLACE_READY`", "`NOT_READY`", "`NOT_CHECKED`", "never changes the classification",
                   "`marketplace_profiles.amazap.status`", "`--profile amazap`"):
        assert phrase in section, phrase


def test_amazap_appears_only_in_the_profiles_section():
    # Case-insensitive, so the `--profile amazap` flag and the
    # `marketplace_profiles.amazap` key count too: the core flow, the
    # classifications, the safety rules, and the example are marketplace-free.
    text = SKILL.read_text(encoding="utf-8")
    assert text.count(f"\n{PROFILES_HEADING}\n") == 1
    assert "amazap" not in without_section(text, PROFILES_HEADING).lower()
    assert "Amazap" in section_text(text, PROFILES_HEADING)


def test_profiles_section_follows_the_core_flow_and_classifications():
    text = SKILL.read_text(encoding="utf-8")
    profiles = text.index(f"\n{PROFILES_HEADING}\n")
    for core in ("\n## Flow\n", "\n## Classifications\n"):
        assert text.index(core) < profiles, core


def test_profiles_section_states_the_profile_is_optional_and_for_a_listing():
    section = " ".join(section_text(SKILL.read_text(encoding="utf-8"), PROFILES_HEADING).split())
    for phrase in ("only when the human wants a marketplace listing",
                   "never makes a correct endpoint read as deficient",
                   "`stable_price`", "`host_root_metadata`"):
        assert phrase in section, phrase
    # stable_price is required (Amazap pays only at the price it stored); host-root metadata is advisory.
    required, advisory = section.split("One advisory check never decides the status", 1)
    assert "`stable_price`" in required and "`stable_price`" not in advisory
    assert "`host_root_metadata`" in advisory and "`host_root_metadata`" not in required


def test_a_valid_endpoint_never_reads_as_deficient_for_lacking_marketplace_metadata():
    text = flat(SKILL)
    assert ("a correct, paid, fulfilled endpoint is `FULFILLMENT_VERIFIED` with or without any "
            "marketplace's metadata") in text
    step2 = SKILL.read_text(encoding="utf-8").split("### 2. Read the report back", 1)[1].split("\n### ", 1)[0]
    step2 = " ".join(step2.split())
    assert "only when the human wants a marketplace listing" in step2
    assert "never a gap in the endpoint" in step2


def test_readme_names_amazap_once_as_an_optional_profile():
    readme = README.read_text(encoding="utf-8")
    assert flat(README).count("Amazap") == 1
    assert "**Optional marketplace profiles.**" in flat(README)
    try_it = readme.split("\n## Try it\n", 1)[1].split("\n## ", 1)[0]
    assert "Amazap" not in try_it


def test_example_ends_on_fulfillment_verified_as_complete():
    example = flat(SKILL).split("## Example", 1)[1]
    assert "`FULFILLMENT_VERIFIED`: the whole paid flow worked." in example
    assert "gap for listing" not in example
    assert "before I list it" not in example
