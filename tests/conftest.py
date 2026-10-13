"""Shared pytest configuration for the skill guard suite.

Most tests here read the skill files as text. Nothing runs a payment or needs a
wallet, and only one test opens a socket (a loopback server on 127.0.0.1), so
CI installs pytest and nothing else.

What the suite holds, and where:

* ``test_skill_metadata.py``: each ``SKILL.md`` has loadable frontmatter, an H1,
  and a row in the top-level README table; no skill uses misleading custody
  language or makes a KYB/KYC claim; and relative links between skills point at
  folders that exist.
* ``test_tool_surface.py``: skills call the Lightning Enable MCP 2.x tool names
  that the default ``standard`` profile advertises, never the deprecated aliases,
  in their markdown, their ``references/`` notes, the repo-level ``references/``
  notes, and their scripts' docstrings.
* ``test_tool_arguments_surface.py``: every skill's ``l402_producer`` and
  ``agent_services`` calls match the tools' real input schemas, action by action.
* ``test_producer_setup_surface.py``: the ``producer-setup`` skill names every
  ``l402_producer`` action and avoids the REST layer's field names.
* ``test_shared_references.py``: the repo-level ``references/`` notes, and that
  the guards above scan them.
* ``test_l402_*.py``: the ``l402-compatibility-report`` skill. These are
  behavioral tests of its standard-library script, run offline against the
  fixtures in ``fixtures/l402-challenges`` and ``fixtures/l402-evidence``, plus
  text guards on its ``SKILL.md``. ``l402_check_support.py`` holds their shared
  helpers (fixture loading, fake DNS, fake HTTP); it has no ``test_`` prefix, so
  pytest does not collect it.

The suite has no shared pytest fixtures. Each module resolves the repo root from
its own path, so any test file can run on its own. Cross-module imports: the
``l402_producer`` action table, which ``test_producer_setup_surface.py`` reads
from ``test_tool_arguments_surface.py``; the guard file lists, which
``test_shared_references.py`` and ``test_l402_skill_text.py`` read from the
guard modules; the classification list and custody sentence in
``test_shared_references.py``; and the macaroon builders that
``test_l402_evidence.py`` reads from ``test_l402_macaroon.py``. pytest puts
``tests/`` on the import path for all of them.
"""
