#!/usr/bin/env python3
"""
receipt.py — render a satoshi receipt for paid L402 calls.

Reads a JSON array of paid calls from stdin (or argv[1]) and prints a markdown
receipt: one row per call plus totals. Each entry: {"source", "sats", "what"}.

  echo '[{"source":"FRED USD/JPY","sats":5,"what":"DEXJPUS"}]' | python receipt.py

"sats" is required on every entry: a call whose cost we can't read is an UNKNOWN
cost, not a free one, and a receipt that under-reports the total is worse than
no receipt. Such an entry is an error, never a 0.
"""
import json
import sys


def load():
    raw = sys.argv[1] if len(sys.argv) > 1 else sys.stdin.read()
    data = json.loads(raw)
    if not isinstance(data, list):
        raise ValueError("expected a JSON array of {source, sats, what}")
    for i, c in enumerate(data, 1):
        if not isinstance(c, dict) or "sats" not in c:
            raise ValueError(f"call {i} has no sats — its cost is unknown")
        try:
            c["sats"] = int(c["sats"])
        except (TypeError, ValueError):
            raise ValueError(
                f"call {i} has a non-numeric sats value: {c['sats']!r}") from None
    return data


def main():
    try:
        calls = load()
    except Exception as e:  # noqa: BLE001
        print(f"receipt error: {e}")
        return 1

    total = sum(c["sats"] for c in calls)
    print("| # | Source | What it bought | Sats |")
    print("|---|--------|----------------|------|")
    for i, c in enumerate(calls, 1):
        print(f"| {i} | {c.get('source','?')} | {c.get('what','')} | {c['sats']} |")
    print(f"| | | **Total** | **{total}** |")
    print()
    print(f"**{len(calls)} paid calls | {total} sats | 0 accounts | 0 API keys | 0 human payments**")
    return 0


if __name__ == "__main__":
    sys.exit(main())
