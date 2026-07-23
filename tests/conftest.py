"""Shared fixtures for the spend-guardrail test suite.

These tests pin the guardrails fixed in PR #3 ("make spend guardrails fail loud
instead of reading unknown state as zero"). The whole job of these skills is to
warn an agent *before* it overspends, and the bug was that the warning went
silent in exactly the states that matter: a corrupt ledger, a missing ledger,
and a wrong-cwd ledger all collapsed into ``{"entries": []}`` -> "nothing spent"
-> the budget block was skipped. A corrupt ledger holding 999 sats printed
"nothing spent this session" and exited 0.

Each test drives the real skill script as a subprocess -- the same
``python scripts/<name>.py ...`` invocation an agent uses -- so the exit code
(which is load-bearing: exit 2 == spend UNKNOWN, do not spend) is exercised
exactly as in production, not just the Python return value.

The script under test can be overridden with the ``LEDGER_UNDER_TEST`` /
``STANDING_UNDER_TEST`` env vars. That is the hook the mutation check uses to
point this same suite at a reverted (pre-fix) copy and prove the tests go red.
"""
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_LEDGER = REPO_ROOT / "skills" / "l402-meter" / "scripts" / "ledger.py"
DEFAULT_STANDING = REPO_ROOT / "skills" / "standing-order" / "scripts" / "standing_orders.py"


def ledger_script() -> Path:
    return Path(os.environ.get("LEDGER_UNDER_TEST", str(DEFAULT_LEDGER)))


def standing_script() -> Path:
    return Path(os.environ.get("STANDING_UNDER_TEST", str(DEFAULT_STANDING)))


@pytest.fixture
def run_ledger():
    """Run ledger.py as a subprocess.

    ``ledger_file`` sets L402_METER_FILE; when left None the env var is
    *removed* so a test never accidentally reads (or writes) the developer's
    real skill-local ledger. ``cwd`` runs the process from another directory.
    """

    def _run(*args, ledger_file=None, cwd=None):
        env = os.environ.copy()
        env.pop("L402_METER_FILE", None)
        if ledger_file is not None:
            env["L402_METER_FILE"] = str(ledger_file)
        return subprocess.run(
            [sys.executable, str(ledger_script()), *args],
            capture_output=True,
            text=True,
            cwd=str(cwd) if cwd is not None else None,
            env=env,
        )

    return _run


@pytest.fixture
def run_standing():
    """Run standing_orders.py as a subprocess (see ``run_ledger`` for semantics)."""

    def _run(*args, orders_file=None, cwd=None):
        env = os.environ.copy()
        env.pop("L402_STANDING_ORDERS_FILE", None)
        if orders_file is not None:
            env["L402_STANDING_ORDERS_FILE"] = str(orders_file)
        return subprocess.run(
            [sys.executable, str(standing_script()), *args],
            capture_output=True,
            text=True,
            cwd=str(cwd) if cwd is not None else None,
            env=env,
        )

    return _run
