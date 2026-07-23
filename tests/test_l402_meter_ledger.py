"""Guardrail tests for skills/l402-meter/scripts/ledger.py.

Pins the fix from PR #3. The regression these guard against: a corrupt, missing,
or wrong-cwd ledger being read as "nothing spent this session" so the
``[STOP] OVER BUDGET`` check was silently skipped -- a warning that works when
you don't need it and goes silent when you do.

The contract being pinned:
  * exit 0  -> ok
  * exit 1  -> usage
  * exit 2  -> ledger unreadable == spend is UNKNOWN, do not spend
"""
import importlib.util
import json
import sys
import uuid

import pytest


# --------------------------------------------------------------------------- #
# THE headline regression: a corrupt ledger must never read as "0 spent".
# This is the test the mutation check reverts the fix against (must go RED).
# --------------------------------------------------------------------------- #

def test_corrupt_ledger_fails_loud_not_silent_zero(run_ledger, tmp_path):
    """A corrupt ledger secretly holding 999 sats must NOT print 'nothing spent'
    and exit 0. It must fail loud: [STOP] LEDGER UNREADABLE, exit 2."""
    ledger = tmp_path / "corrupt.json"
    # Truncated/garbled JSON that nonetheless contains a big spend -- the exact
    # shape of the baseline audit failure (999 sats reported as "nothing spent").
    ledger.write_text('{"entries": [{"sats": 999, "what": "expensive call"}', encoding="utf-8")

    result = run_ledger("show", "--budget", "50", ledger_file=ledger)

    assert result.returncode == 2, (
        "corrupt ledger must exit 2 (spend UNKNOWN), got "
        f"{result.returncode}: {result.stdout!r}"
    )
    assert "[STOP] LEDGER UNREADABLE" in result.stdout
    # The precise silent-failure symptoms must be absent.
    assert "nothing spent" not in result.stdout.lower()
    assert "0/50" not in result.stdout


def test_corrupt_ledger_does_not_skip_the_budget_block(run_ledger, tmp_path):
    """The budget block must not be silently skipped on a corrupt ledger: the
    over-budget spend cannot be quietly rendered as under budget."""
    ledger = tmp_path / "corrupt2.json"
    ledger.write_text("this is not json at all", encoding="utf-8")

    result = run_ledger("show", "--budget", "50", ledger_file=ledger)

    # Either way the guard is enforced, never bypassed: it fails closed (exit 2)
    # rather than printing an under-budget bar.
    assert result.returncode == 2
    assert "[WARN]" not in result.stdout  # must not pretend we are merely near budget
    assert "Budget: 0/" not in result.stdout


# --------------------------------------------------------------------------- #
# Missing ledger: a KNOWN zero (first run) -- must still render the budget.
# --------------------------------------------------------------------------- #

def test_missing_ledger_is_known_zero_and_still_renders_budget(run_ledger, tmp_path):
    ledger = tmp_path / "does-not-exist.json"
    assert not ledger.exists()

    result = run_ledger("show", "--budget", "50", ledger_file=ledger)

    assert result.returncode == 0
    assert "nothing spent this session" in result.stdout
    # The budget block must run even with no entries: a ceiling the agent asked
    # about always gets an answer.
    assert "0/50" in result.stdout
    assert "[STOP]" not in result.stdout


def test_missing_ledger_is_not_treated_as_unreadable(run_ledger, tmp_path):
    """Missing (known zero) and corrupt (unknown) are different states."""
    ledger = tmp_path / "missing.json"
    result = run_ledger("show", ledger_file=ledger)
    assert result.returncode == 0
    assert "LEDGER UNREADABLE" not in result.stdout


# --------------------------------------------------------------------------- #
# Wrong cwd: the ledger path must resolve next to the skill, never to cwd.
# --------------------------------------------------------------------------- #

def test_wrong_cwd_decoy_ledger_is_ignored(run_ledger, tmp_path):
    """A stray .l402-meter.json in the current directory must have no power.

    Running from another directory (no L402_METER_FILE override) must resolve to
    the skill-local ledger, not read the cwd decoy as the session spend. The
    decoy is over budget; if it were picked up we'd see 999 / OVER BUDGET.
    """
    decoy = tmp_path / ".l402-meter.json"
    decoy.write_text(
        json.dumps({"entries": [{"sats": 999, "what": "decoy in cwd"}]}),
        encoding="utf-8",
    )

    # No ledger_file -> uses the default skill-local path, run from tmp_path.
    result = run_ledger("show", "--budget", "50", cwd=tmp_path)

    assert result.returncode == 0
    assert "999" not in result.stdout
    assert "OVER BUDGET" not in result.stdout


def test_state_path_is_cwd_independent_and_skill_local(monkeypatch, tmp_path):
    """Cause #3 of the fix, pinned at the source: STATE resolves next to the
    skill and is identical regardless of the process working directory."""
    from conftest import DEFAULT_LEDGER

    monkeypatch.delenv("L402_METER_FILE", raising=False)

    def load_state_from(cwd):
        monkeypatch.chdir(cwd)
        name = f"ledger_probe_{uuid.uuid4().hex}"
        spec = importlib.util.spec_from_file_location(name, DEFAULT_LEDGER)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.STATE

    cwd_a = tmp_path / "a"
    cwd_b = tmp_path / "b"
    cwd_a.mkdir()
    cwd_b.mkdir()

    state_a = load_state_from(cwd_a)
    state_b = load_state_from(cwd_b)

    from pathlib import Path

    assert state_a == state_b, "STATE must not depend on the current directory"
    assert Path(state_a).is_absolute()
    assert Path(state_a).name == ".l402-meter.json"
    assert "l402-meter" in state_a  # lives under the skill folder
    # And crucially: NOT a cwd-relative path.
    assert Path(state_a) != (cwd_a / ".l402-meter.json")


# --------------------------------------------------------------------------- #
# The guard fires when it should: genuinely over budget -> STOP.
# --------------------------------------------------------------------------- #

def test_over_budget_ledger_triggers_stop(run_ledger, tmp_path):
    ledger = tmp_path / "over.json"
    ledger.write_text(
        json.dumps({"entries": [{"sats": 60, "what": "big call"}]}),
        encoding="utf-8",
    )
    result = run_ledger("show", "--budget", "50", ledger_file=ledger)
    assert result.returncode == 0
    assert "[STOP] OVER BUDGET" in result.stdout
    assert "60/50" in result.stdout


def test_exactly_at_budget_triggers_stop(run_ledger, tmp_path):
    """Boundary: total == budget is OVER (total >= budget), not merely a warn."""
    ledger = tmp_path / "exact.json"
    ledger.write_text(
        json.dumps({"entries": [{"sats": 50, "what": "spent it all"}]}),
        encoding="utf-8",
    )
    result = run_ledger("show", "--budget", "50", ledger_file=ledger)
    assert result.returncode == 0
    assert "[STOP] OVER BUDGET" in result.stdout


def test_warn_at_80_percent(run_ledger, tmp_path):
    ledger = tmp_path / "warn.json"
    ledger.write_text(
        json.dumps({"entries": [{"sats": 40, "what": "getting close"}]}),
        encoding="utf-8",
    )
    result = run_ledger("show", "--budget", "50", ledger_file=ledger)
    assert result.returncode == 0
    assert "[WARN]" in result.stdout
    assert "[STOP]" not in result.stdout


def test_under_80_percent_neither_warn_nor_stop(run_ledger, tmp_path):
    ledger = tmp_path / "safe.json"
    ledger.write_text(
        json.dumps({"entries": [{"sats": 30, "what": "well under"}]}),
        encoding="utf-8",
    )
    result = run_ledger("show", "--budget", "50", ledger_file=ledger)
    assert result.returncode == 0
    assert "[WARN]" not in result.stdout
    assert "[STOP]" not in result.stdout
    assert "60%" in result.stdout


# --------------------------------------------------------------------------- #
# The legitimate empty / first-run case still works.
# --------------------------------------------------------------------------- #

def test_empty_ledger_first_run_renders_zero_budget(run_ledger, tmp_path):
    ledger = tmp_path / "empty.json"
    ledger.write_text(json.dumps({"entries": []}), encoding="utf-8")
    result = run_ledger("show", "--budget", "50", ledger_file=ledger)
    assert result.returncode == 0
    assert "nothing spent this session" in result.stdout
    assert "0/50" in result.stdout
    assert "[STOP]" not in result.stdout


def test_empty_ledger_show_without_budget(run_ledger, tmp_path):
    ledger = tmp_path / "empty2.json"
    ledger.write_text(json.dumps({"entries": []}), encoding="utf-8")
    result = run_ledger("show", ledger_file=ledger)
    assert result.returncode == 0
    assert "nothing spent this session" in result.stdout


# --------------------------------------------------------------------------- #
# "Unknown cost is not a free one": malformed entries are unreadable too.
# --------------------------------------------------------------------------- #

def test_entry_missing_sats_is_unreadable(run_ledger, tmp_path):
    ledger = tmp_path / "nosats.json"
    ledger.write_text(json.dumps({"entries": [{"what": "no cost recorded"}]}), encoding="utf-8")
    result = run_ledger("show", "--budget", "50", ledger_file=ledger)
    assert result.returncode == 2
    assert "[STOP] LEDGER UNREADABLE" in result.stdout


def test_entry_nonnumeric_sats_is_unreadable(run_ledger, tmp_path):
    ledger = tmp_path / "badsats.json"
    ledger.write_text(json.dumps({"entries": [{"sats": "lots", "what": "x"}]}), encoding="utf-8")
    result = run_ledger("show", "--budget", "50", ledger_file=ledger)
    assert result.returncode == 2
    assert "[STOP] LEDGER UNREADABLE" in result.stdout


def test_top_level_not_a_dict_is_unreadable(run_ledger, tmp_path):
    ledger = tmp_path / "list.json"
    ledger.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
    result = run_ledger("show", ledger_file=ledger)
    assert result.returncode == 2
    assert "[STOP] LEDGER UNREADABLE" in result.stdout


# --------------------------------------------------------------------------- #
# add must refuse on a corrupt ledger (never overwrite history); reset must work.
# --------------------------------------------------------------------------- #

def test_add_on_corrupt_ledger_refuses_and_preserves_file(run_ledger, tmp_path):
    ledger = tmp_path / "corrupt_add.json"
    original = "CORRUPT-ledger-holding-999-sats-of-history"
    ledger.write_text(original, encoding="utf-8")

    result = run_ledger("add", "5", "sneak in one more", ledger_file=ledger)

    assert result.returncode == 2
    assert "[STOP] LEDGER UNREADABLE" in result.stdout
    # The corrupt history must NOT be clobbered by a lone new entry.
    assert ledger.read_text(encoding="utf-8") == original


def test_reset_on_corrupt_ledger_succeeds(run_ledger, tmp_path):
    """reset is the escape hatch: it must clear even an unreadable ledger."""
    ledger = tmp_path / "corrupt_reset.json"
    ledger.write_text("totally broken {{{", encoding="utf-8")

    result = run_ledger("reset", ledger_file=ledger)

    assert result.returncode == 0
    assert "meter reset" in result.stdout
    assert json.loads(ledger.read_text(encoding="utf-8")) == {"entries": []}


# --------------------------------------------------------------------------- #
# Happy path sanity: add accumulates and show totals correctly.
# --------------------------------------------------------------------------- #

def test_add_then_show_records_and_totals(run_ledger, tmp_path):
    ledger = tmp_path / "session.json"
    assert run_ledger("add", "5", "FRED USD/JPY", ledger_file=ledger).returncode == 0
    assert run_ledger("add", "7", "weather API", ledger_file=ledger).returncode == 0

    result = run_ledger("show", "--budget", "50", ledger_file=ledger)
    assert result.returncode == 0
    assert "**12**" in result.stdout  # running total
    assert "12/50" in result.stdout
    assert "[STOP]" not in result.stdout


def test_no_args_is_usage_exit_1(run_ledger, tmp_path):
    result = run_ledger(ledger_file=tmp_path / "unused.json")
    assert result.returncode == 1
