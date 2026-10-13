"""Text guards for the l402-compatibility-report SKILL.md and README.md."""
import re

import pytest

import l402_check_support as support
import test_tool_surface
from test_shared_references import CLASSIFICATIONS, CUSTODY

SKILL = support.SKILL_DIR / "SKILL.md"
README = support.SKILL_DIR / "README.md"
REFERENCE_URL = "https://github.com/refined-element/lightning-enable-skills/blob/main/references/l402-verification-levels.md"


def flat(path):
    return " ".join(path.read_text(encoding="utf-8").split())


def test_skill_names_exactly_the_six_classifications():
    text = SKILL.read_text(encoding="utf-8")
    named = set(re.findall(r"\b(?:[A-Z]+_)+(?:COMPATIBLE|VERIFIED|READY)\b|\bINCOMPATIBLE\b|\bINCONCLUSIVE\b", text))
    assert named == set(CLASSIFICATIONS)


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
