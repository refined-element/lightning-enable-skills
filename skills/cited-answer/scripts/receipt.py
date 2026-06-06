#!/usr/bin/env python3
"""
receipt.py — render a satoshi receipt for paid L402 calls.

Reads a JSON array of paid calls from stdin (or argv[1]) and prints a markdown
receipt: one row per call plus totals. Each entry: {"source", "sats", "what"}.

  echo '[{"source":"FRED USD/JPY","sats":5,"what":"DEXJPUS"}]' | python receipt.py
"""
import json
import sys


def load():
    raw = sys.argv[1] if len(sys.argv) > 1 else sys.stdin.read()
    data = json.loads(raw)
    if not isinstance(data, list):
        raise ValueError("expected a JSON array of {source, sats, what}")
    return data


def main():
    try:
        calls = load()
    except Exception as e:  # noqa: BLE001
        print(f"receipt error: {e}")
        return 1

    total = sum(int(c.get("sats", 0)) for c in calls)
    print("| # | Source | What it bought | Sats |")
    print("|---|--------|----------------|------|")
    for i, c in enumerate(calls, 1):
        print(f"| {i} | {c.get('source','?')} | {c.get('what','')} | {int(c.get('sats',0))} |")
    print(f"| | | **Total** | **{total}** |")
    print()
    print(f"**{len(calls)} paid calls | {total} sats | 0 accounts | 0 API keys | 0 human payments**")
    return 0


if __name__ == "__main__":
    sys.exit(main())
