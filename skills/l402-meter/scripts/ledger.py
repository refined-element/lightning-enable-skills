#!/usr/bin/env python3
"""
ledger.py — a running meter for an agent's L402 spending this session.

Keeps a tiny local ledger so the agent can show a live total and warn before a
budget is blown. Sats only — no wallet access, no secrets.

State is a JSON file: the L402_METER_FILE env var if set, else .l402-meter.json
next to the skill. Deliberately NOT relative to the current directory — a
cwd-relative ledger silently reads as "nothing spent" the moment the agent runs
from somewhere else.

  ledger.py add <sats> <description...>      # record a paid call
  ledger.py show [--budget <sats>]           # render the meter (+ % of budget)
  ledger.py reset                            # clear the session ledger

Markers are ASCII ([WARN] / [STOP]), not emoji, so the meter renders on any
console — a guardrail that crashes on encoding is worse than no guardrail.

Exit codes: 0 ok, 1 usage, 2 ledger unreadable (spend UNKNOWN — do not spend).
"""
import json
import os
import sys

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE = os.environ.get("L402_METER_FILE") or os.path.join(SKILL_DIR, ".l402-meter.json")


class LedgerUnreadable(Exception):
    """The ledger exists but can't be trusted — spend is UNKNOWN, not zero."""


def _load():
    try:
        with open(STATE, "r", encoding="utf-8") as f:
            d = json.load(f)
    except FileNotFoundError:
        # No ledger yet: genuinely nothing recorded. A KNOWN zero.
        return {"entries": []}
    except (json.JSONDecodeError, OSError) as e:
        # The ledger exists but won't parse/read. Unknown spend must never
        # collapse into "nothing spent" — that is the state the meter exists for.
        raise LedgerUnreadable(str(e)) from e
    if not isinstance(d, dict) or not isinstance(d.get("entries"), list):
        raise LedgerUnreadable('malformed ledger: expected {"entries": [...]}')
    for i, e in enumerate(d["entries"], 1):
        if not isinstance(e, dict) or "sats" not in e:
            raise LedgerUnreadable(f"entry {i} has no sats — its cost is unknown")
        try:
            e["sats"] = int(e["sats"])
        except (TypeError, ValueError):
            raise LedgerUnreadable(
                f"entry {i} has a non-numeric sats value: {e['sats']!r}") from None
    return d


def _save(d):
    with open(STATE, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=2)


def add(sats, desc):
    d = _load()
    d["entries"].append({"sats": int(sats), "what": desc})
    _save(d)
    total = sum(e["sats"] for e in d["entries"])
    print(f"recorded: {sats} sats — {desc}  (session total: {total} sats)")


def show(budget=None):
    d = _load()
    entries = d["entries"]
    total = sum(e["sats"] for e in entries)
    if not entries:
        print("L402 meter: nothing spent this session.")
    else:
        print("| # | What | Sats |")
        print("|---|------|------|")
        for i, e in enumerate(entries, 1):
            print(f"| {i} | {e['what']} | {e['sats']} |")
        print(f"| | **Total** | **{total}** |")
    # The budget check runs whether or not there are entries: a ceiling the agent
    # asked about always gets an answer.
    if budget is not None:
        budget = int(budget)
        pct = (100 * total / budget) if budget else 0
        bar_len = 20
        filled = min(bar_len, int(bar_len * total / budget)) if budget else bar_len
        bar = "#" * filled + "-" * (bar_len - filled)
        print(f"\nBudget: {total}/{budget} sats  [{bar}] {pct:.0f}%")
        if total >= budget:
            print("[STOP] OVER BUDGET - stop spending and tell the user.")
        elif pct >= 80:
            print("[WARN] Over 80% of budget - warn the user before the next paid call.")


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 1
    cmd = argv[1]
    try:
        if cmd == "add" and len(argv) >= 4:
            add(argv[2], " ".join(argv[3:]))
        elif cmd == "show":
            budget = None
            if "--budget" in argv:
                budget = argv[argv.index("--budget") + 1]
            show(budget)
        elif cmd == "reset":
            # The escape hatch: deliberately does NOT read the old ledger, so a
            # corrupt one can always be cleared.
            _save({"entries": []})
            print("meter reset.")
        else:
            print(__doc__)
            return 1
    except LedgerUnreadable as e:
        print("[STOP] LEDGER UNREADABLE - spend this session is UNKNOWN, not zero.")
        print(f"  file:  {STATE}")
        print(f"  cause: {e}")
        print("Do not make paid calls. Tell the user, then either fix the file or run")
        print("`ledger.py reset` to start a fresh ledger (this discards the history).")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
