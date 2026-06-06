# l402-meter

**A running satoshi meter and guardrail for an agent's Lightning spending.**

When you let an agent pay for things over L402, you want to *see* the spend add
up and get warned **before** a budget is blown — not discover it after the fact.
This skill keeps a live per-session meter, shows it on demand (and proactively),
and stops the agent before it crosses the line.

## Why it's interesting

- **Visibility.** A running ledger of every paid call — what it bought and what
  it cost — with a budget bar.
- **Warn before the wall.** The Lightning Enable MCP enforces a *hard* budget (it
  refuses payments past the limit). This adds a *soft* layer: a ⚠️ at 80% and a
  ⛔ at 100%, so you (and the agent) see it coming.
- **Useful to anyone running paid agents** — not tied to any specific store or
  API. Drop it alongside `cited-answer`, `restock-from-photo`, or any skill that
  spends sats.

## How it works

1. Agree a ceiling and check real state with `get_budget_status` /
   `check_wallet_balance`.
2. After each paid call, the agent logs it: `ledger.py add <sats> "<what>"`.
3. `ledger.py show --budget <ceiling>` renders the table, total, and a budget
   bar with warn/stop markers.
4. The agent honors the markers — warns at 80%, stops at 100%, and never routes
   around the MCP's hard limit.

The "most restrictive budget wins": the MCP's enforced cap and your session
ceiling are both respected.

## Requirements

- [Lightning Enable MCP](https://github.com/refined-element/lightning-enable-mcp).
- Python 3 (stdlib only).

## Example

> "Do the research but keep me under 50 sats and tell me where I'm at."

→ resets the meter → logs each 5-sat call → at 40/50 it warns you → it won't
cross 50 without asking. You always know exactly what's been spent.
