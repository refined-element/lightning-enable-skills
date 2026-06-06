#!/usr/bin/env python3
"""
ledger.py — a running meter for an agent's L402 spending this session.

Keeps a tiny local ledger so the agent can show a live total and warn before a
budget is blown. State is a JSON file (default ./.l402-meter.json, override with
the L402_METER_FILE env var). Sats only — no wallet access, no secrets.

  ledger.py add <sats> <description...>      # record a paid call
  ledger.py show [--budget <sats>]           # render the meter (+ % of budget)
  ledger.py reset                            # clear the session ledger
"""
import json
import os
import sys

STATE = os.environ.get("L402_METER_FILE", ".l402-meter.json")


def _load():
    try:
        with open(STATE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"entries": []}


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
        return
    print("| # | What | Sats |")
    print("|---|------|------|")
    for i, e in enumerate(entries, 1):
        print(f"| {i} | {e['what']} | {e['sats']} |")
    print(f"| | **Total** | **{total}** |")
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
    if cmd == "add" and len(argv) >= 4:
        add(argv[2], " ".join(argv[3:]))
    elif cmd == "show":
        budget = None
        if "--budget" in argv:
            budget = argv[argv.index("--budget") + 1]
        show(budget)
    elif cmd == "reset":
        _save({"entries": []})
        print("meter reset.")
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
