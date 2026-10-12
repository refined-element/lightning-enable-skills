"""Shared pytest configuration for the skill guard suite.

Every test here reads the skill files as text. Nothing runs a payment, opens a
network connection, or needs a wallet, so CI installs pytest and nothing else.

What the suite holds, and where:

* ``test_skill_metadata.py``: each ``SKILL.md`` has loadable frontmatter, an H1,
  and a row in the top-level README table, and no skill uses misleading custody
  language.
* ``test_tool_surface.py``: skills call the Lightning Enable MCP 2.x tool names
  that the default ``standard`` profile advertises, never the deprecated aliases,
  and relative links between skills point at folders that exist.
* ``test_producer_setup_surface.py``: the ``producer-setup`` skill's
  ``l402_producer`` calls match the tool's real input schema, action by action.

The suite has no shared fixtures. Each module resolves the repo root from its own
path, so any test file can run on its own.
"""
