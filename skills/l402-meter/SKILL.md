---
name: l402-meter
description: >-
  Track and cap an agent's L402 / Lightning spending across a session — keep a
  running satoshi meter, surface it on request, and warn or stop before a budget
  is blown. Use when the user wants visibility or guardrails on how much an agent
  is spending on paid API calls ("how much have I spent", "keep me under N sats",
  "watch the spending", "don't go over budget"). Complements any skill that pays
  over L402.
---

# L402 meter

A running meter and guardrail for agent spending. The Lightning Enable MCP
already enforces hard budgets; this skill makes the spend **visible** and adds a
human-friendly warn-before-you-blow-it layer on top, so paid agents don't
quietly drain a wallet.

## What you need

- **Lightning Enable MCP** (`get_budget_status`, `check_wallet_balance`,
  `get_payment_history`, `configure_budget`).
- `scripts/ledger.py` for the session tally (Python 3, stdlib only).

## Flow

### Establish the budget
At the start, agree a ceiling with the user and check the real state:
- `get_budget_status` — the MCP's configured limits + remaining.
- `check_wallet_balance` — actual funds.
- Optionally `configure_budget` to set MCP-enforced limits to match.
Reset the session meter: `python scripts/ledger.py reset`.

### Record every paid call
After each L402 / Lightning payment, log it:
```
python scripts/ledger.py add <sats> "<what it bought>"
```

### Show the meter on request (and proactively)
```
python scripts/ledger.py show --budget <ceiling_sats>
```
Renders the per-call table, the running total, and a budget bar. It prints a
**⚠️ warning at 80%** and a **⛔ stop at/over 100%**.

### Enforce
- When the meter says **⛔ over budget**, stop making paid calls and tell the
  user. Do not "just one more."
- When it says **⚠️ over 80%**, warn the user before the next paid call and let
  them decide.
- Cross-check against `get_budget_status` periodically — if the MCP's own budget
  is tighter, the most restrictive wins.

## Why two layers?

The MCP enforces a *hard* cap (it will refuse a payment past the limit). This
skill adds a *soft, visible* meter — so the user sees the spend accumulating and
gets warned **before** hitting the wall, rather than discovering it only when a
payment is refused.

## Safety rules

- The hard MCP budget is the floor of trust; never try to route around it.
- Always surface the meter when the user asks "how much have I spent."
- Most-restrictive budget wins (MCP limit vs. the session ceiling).

## Example

> User: "Do the research but keep me under 50 sats and tell me where I'm at."
>
> → `get_budget_status` → `ledger.py reset` → after each paid call
> `ledger.py add 5 "FRED USD/JPY"` → on request `ledger.py show --budget 50`
> → at 40/50 it warns; it won't cross 50 without asking.
