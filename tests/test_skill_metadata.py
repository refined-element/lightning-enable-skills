"""Format guards for the skill files themselves.

A skill is only loadable if its ``SKILL.md`` starts with well-formed YAML
frontmatter carrying a ``name`` and a ``description``: Claude reads every
skill's description up front and loads the body on demand, so a broken fence or
a ``name`` that disagrees with the folder means the skill silently never
triggers. That failure is invisible in review -- the file looks fine -- which is
exactly the kind of thing a test should hold.

Three things are pinned here:

1. **Frontmatter shape.** Fenced, parseable, ``name`` matches the directory and
   the slug rules, ``description`` present and inside the length limit.
2. **The README index.** Every skill folder appears in the top-level README
   table. The table is how a human finds a skill; a skill missing from it is
   effectively unpublished.
3. **Custody language.** "non-custodial", "self-custody", and "trustless" are
   banned across the repo's prose. The payment provider and the wallet ARE
   custodians -- saying otherwise is a compliance claim this project does not
   make. See the custody-language convention in the Lightning Enable docs.
   "No KYB" / "no KYC" copy is banned for the same reason: it is a compliance
   claim, not a feature.
4. **Links between skills resolve.** A ``../<skill>/`` link in any skill file
   must point at a skill folder that exists. Skills get merged and retired, and
   a link to a deleted sibling sends the agent to a file that is not there.

The frontmatter parser below is deliberately small and stdlib-only (CI installs
nothing but pytest). It handles the two forms these files use: ``key: value``
and a ``key: >-`` folded block.
"""
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIR = REPO_ROOT / "skills"
README = REPO_ROOT / "README.md"

# Claude's limits for a skill's frontmatter.
MAX_NAME_LENGTH = 64
MAX_DESCRIPTION_LENGTH = 1024
NAME_PATTERN = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")

# Words that would misdescribe who holds the funds.
BANNED_CUSTODY_TERMS = ("non-custodial", "noncustodial", "self-custody", "trustless")

# Compliance claims this project does not make: "no KYC" / "no-KYB" standing as
# a claim (at the end of a clause, or followed by a word such as "required" or
# "checks"), and "without KYC". A bare substring would also flag words that merely
# contain the letters, so the pattern matches the claim, not the characters.
COMPLIANCE_CLAIM = re.compile(
    r"\bno[- ]ky[bc]\b"
    r"(?=\s*(?:[,.;:!?)\]*_`]|$|\s(?:is\s+|are\s+)?"
    r"(?:required|needed|necessary|checks?|verification|step|steps|process|paperwork|hoops)\b))"
    r"|\bwithout\s+(?:any\s+|a\s+)?ky[bc]\b",
    re.IGNORECASE | re.MULTILINE,
)

# `](../<name>/...)` or `](../<name>)`: a relative link from one skill to another.
SIBLING_LINK = re.compile(r"\]\(\.\./([a-z0-9-]+)(?:[/)#])")


def skill_dirs():
    return sorted(p for p in SKILLS_DIR.iterdir() if p.is_dir())


def skill_ids():
    return [p.name for p in skill_dirs()]


def parse_frontmatter(text: str) -> dict:
    """Parse the leading ``---`` fenced block into a dict.

    Supports ``key: value`` and folded (``key: >-``) blocks, which is everything
    these skill files use. Raises AssertionError with a readable message rather
    than returning junk, because a malformed fence is the bug under test.
    """
    lines = text.splitlines()
    assert lines and lines[0].strip() == "---", "SKILL.md must open with a '---' frontmatter fence"

    try:
        closing = next(i for i, line in enumerate(lines[1:], start=1) if line.strip() == "---")
    except StopIteration:  # pragma: no cover - only hit by a malformed file
        raise AssertionError("frontmatter fence is never closed with '---'")

    data: dict[str, str] = {}
    key = None
    folded: list[str] = []

    def flush():
        if key is not None:
            data[key] = " ".join(folded).strip()

    for line in lines[1:closing]:
        if not line.strip():
            continue
        if line[:1].isspace():  # continuation of a folded block
            assert key is not None, f"indented line before any key: {line!r}"
            folded.append(line.strip())
            continue
        flush()
        assert ":" in line, f"frontmatter line is not 'key: value': {line!r}"
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()
        folded = [] if value in (">-", ">", "|", "|-") else [value]

    flush()
    return data


@pytest.fixture(scope="module")
def readme_text() -> str:
    return README.read_text(encoding="utf-8")


@pytest.mark.parametrize("skill_dir", skill_dirs(), ids=skill_ids())
def test_skill_has_valid_frontmatter(skill_dir: Path):
    skill_file = skill_dir / "SKILL.md"
    assert skill_file.is_file(), f"{skill_dir.name} has no SKILL.md"

    front = parse_frontmatter(skill_file.read_text(encoding="utf-8"))

    name = front.get("name", "")
    assert name == skill_dir.name, (
        f"frontmatter name {name!r} must match the folder name {skill_dir.name!r} -- "
        "they are how the skill is addressed"
    )
    assert len(name) <= MAX_NAME_LENGTH
    assert NAME_PATTERN.match(name), f"{name!r} must be lowercase words joined by hyphens"

    description = front.get("description", "")
    assert description, f"{skill_dir.name} has no description -- it would never trigger"
    assert len(description) <= MAX_DESCRIPTION_LENGTH, (
        f"{skill_dir.name} description is {len(description)} chars, over the "
        f"{MAX_DESCRIPTION_LENGTH} limit"
    )
    # A description that never says when to use the skill is a description that
    # triggers on everything or nothing.
    assert "use" in description.lower(), f"{skill_dir.name} description must say when to use it"


@pytest.mark.parametrize("skill_dir", skill_dirs(), ids=skill_ids())
def test_skill_body_has_a_heading(skill_dir: Path):
    body = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
    _, _, after_frontmatter = body.partition("\n---\n")
    assert re.search(r"^# \S", after_frontmatter, re.MULTILINE), (
        f"{skill_dir.name}: SKILL.md needs an H1 title under the frontmatter"
    )


@pytest.mark.parametrize("skill_dir", skill_dirs(), ids=skill_ids())
def test_skill_is_listed_in_the_readme_table(skill_dir: Path, readme_text: str):
    link = f"(skills/{skill_dir.name}/)"
    assert link in readme_text, (
        f"{skill_dir.name} is missing from the README skills table -- add a row "
        f"linking to {link}"
    )


def markdown_files() -> list[Path]:
    docs_dir = REPO_ROOT / "docs"
    docs = list(docs_dir.rglob("*.md")) if docs_dir.is_dir() else []
    return sorted([README, *SKILLS_DIR.rglob("*.md"), *docs])


def rel(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT)).replace("\\", "/")


@pytest.mark.parametrize("markdown_file", markdown_files(), ids=rel)
def test_prose_avoids_banned_custody_terms(markdown_file: Path):
    text = markdown_file.read_text(encoding="utf-8").lower()
    hits = [term for term in BANNED_CUSTODY_TERMS if term in text]
    assert not hits, (
        f"{markdown_file.name} uses {hits} -- the wallet and the payment provider are "
        "custodians. Say 'Lightning Enable does not hold funds; the wallet facilitates "
        "custody and settlement' instead."
    )


@pytest.mark.parametrize("markdown_file", markdown_files(), ids=rel)
def test_prose_makes_no_kyb_or_kyc_claims(markdown_file: Path):
    text = markdown_file.read_text(encoding="utf-8")
    hits = sorted({m.group(0) for m in COMPLIANCE_CLAIM.finditer(text)})
    assert not hits, (
        f"{rel(markdown_file)} uses {hits}. KYB and KYC belong to the payment "
        "provider; this repo makes no claim about them."
    )


# Only files at the top of a skill folder: from there `../<name>/` is a sibling
# skill. From `skills/<name>/references/`, `../scripts/` is the skill's own folder.
@pytest.mark.parametrize(
    "markdown_file", sorted(SKILLS_DIR.glob("*/*.md")), ids=rel
)
def test_links_between_skills_resolve(markdown_file: Path):
    text = markdown_file.read_text(encoding="utf-8")
    missing = sorted(
        {name for name in SIBLING_LINK.findall(text) if not (SKILLS_DIR / name).is_dir()}
    )
    assert not missing, (
        f"{rel(markdown_file)} links to skills that do not exist: {missing}. "
        "Point the link at the skill that replaced it, or remove it."
    )
