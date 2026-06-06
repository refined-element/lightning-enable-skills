# cited-answer

**Answer a question by buying exactly the data it needs — per call, over Lightning — and cite every figure.**

Ask a research or data question. Instead of guessing (or making you wire up an
API key and billing for every source), the agent **discovers** paid data on the
L402 registry, **buys only what it needs** one call at a time over Lightning,
writes a **cited** answer where every number traces to a paid call, and shows
you the **satoshi receipt**.

This is the [yen-carry research demo](https://github.com/refined-element/l402-research-agent)
turned into a reusable skill: an AI doing real research by paying its own way,
account-lessly.

## Why it's interesting

- **No accounts, no keys.** The agent pays per call with sats. There's no FRED
  login, no signup, no billing relationship — the kind of sub-cent, per-request
  transaction the card/Stripe/API-key economy can't do.
- **Real data beats vibes.** Because it pays for *actual* figures, it catches
  things a confident guess misses — and it tells you when the data contradicts
  the obvious story.
- **You see the receipt.** Total sats, number of calls, zero accounts. Full
  transparency on what was spent and what it bought.

## How it works

1. Sets a sats budget ceiling with you and checks wallet headroom
   (`get_budget_status`).
2. Finds sources with `discover_api` (the L402 API registry / agent-commerce.store).
3. Buys each needed dataset with `access_l402_resource` (which runs the
   `402 → pay → retry` cycle automatically).
4. Writes the answer grounded in what it bought, citing each figure.
5. Renders a receipt with `scripts/receipt.py`.

## Requirements

- [Lightning Enable MCP](https://github.com/refined-element/lightning-enable-mcp)
  with a funded wallet.
- A small sats budget you're comfortable spending.
- Python 3 (stdlib only) for the receipt formatter.

## Safety

- Respects the budget ceiling you set — asks before exceeding it.
- Only cites figures a paid call actually returned; never dresses a guess up as
  sourced.
- Buys the cheapest sufficient source; doesn't over-spend.

## Example

> "Write me a sourced take on the 2024 yen carry-trade unwind — up to 25 sats."

→ discovers FRED on agent-commerce.store → buys USD/JPY, Nikkei, VIX, and the
US 10-year yield (5 sats each) → writes the analysis with every figure cited →
**receipt: 20 sats, 4 calls, 0 accounts.**
