"""The commit that skill files pin their self-referential links to.

Why skill files pin a commit at all: an installed ``SKILL.md`` is hash-verified,
but a link inside it to ``blob/main/...`` is not. Several of those links are
operative -- ``discover-paid-apis/SKILL.md`` says "follow the row for that
outcome in <link>" about money-spending rules -- so an agent following its
verified instructions would fetch and apply whatever ``main`` says at that
moment. Pinning the link closes that: the agent reads the reviewed bytes.

``main`` must not appear in a self-referential link in any file an agent loads
(``skills/*/SKILL.md``) or any file those link to (``references/*.md``).
``test_install_skills.py`` enforces both that and the single-ref rule.

**On repoint:** when ``references/`` content changes, set ``SKILL_LINK_REF`` to a
commit that carries the new content, in a commit of its own, BEFORE the manifest
for that release is generated. A link may legitimately pin an older commit than
the skill file containing it, as long as the cited content at that commit is the
content the skill means -- which is why this is a reviewed constant rather than
something derived automatically.

Not collected by pytest: no ``test_`` prefix, same convention as
``l402_check_support.py``.
"""

# refs/heads/main at the time these links were frozen. The `references/` content
# at this commit is byte-identical to this checkout's, so the pinned links serve
# exactly the documents in this repository.
SKILL_LINK_REF = "587a7b7f5e867cde0bf3a0bc2a65bfbce48c42a0"

SELF_REPO = "github.com/refined-element/lightning-enable-skills"
