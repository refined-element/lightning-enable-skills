"""Shared pytest configuration for the skill guard suite.

Every test here reads the skill files as text. Nothing runs a payment, opens a
network connection, or needs a wallet, so CI installs pytest and nothing else.

What the suite holds, and where:

* ``test_skill_metadata.py``: each ``SKILL.md`` has loadable frontmatter, an H1,
  and a row in the top-level README table; no skill uses misleading custody
  language or makes a KYB/KYC claim; and relative links between skills point at
  folders that exist.
* ``test_tool_surface.py``: skills call the Lightning Enable MCP 2.x tool names
  that the default ``standard`` profile advertises, never the deprecated aliases,
  in their markdown, their ``references/`` notes, and their scripts' docstrings.
* ``test_tool_arguments_surface.py``: every skill's ``l402_producer`` and
  ``agent_services`` calls match the tools' real input schemas, action by action.
* ``test_producer_setup_surface.py``: the ``producer-setup`` skill names every
  ``l402_producer`` action and avoids the REST layer's field names.

The suite has no shared fixtures. Each module resolves the repo root from its own
path, so any test file can run on its own. The one cross-module import is the
``l402_producer`` action table, which ``test_producer_setup_surface.py`` reads
from ``test_tool_arguments_surface.py``; pytest puts ``tests/`` on the import
path for both.
"""
