---
name: cited-answer
description: >-
  Answer a research / data question by discovering and BUYING exactly the paid
  data needed over L402 (per-call, no account), then writing an answer with
  citations and a satoshi receipt. Use when the user wants a factual, sourced
  answer that benefits from real paid data (market figures, economic series,
  weather, etc.) and is willing to spend a small amount of sats. Do NOT use for
  questions answerable from general knowledge or free sources, to browse paid
  APIs without a research question (use discover-paid-apis), or to pay a URL
  the user already has (use pay-l402-anywhere).
---

# Cited answer

Turn a question into a **sourced answer paid for per-call over L402** — discover
the data, buy only what you need, cite every figure, and show the receipt. This
is agentic commerce as a research tool: the agent pays its own way for exactly
the inputs it needs, account-lessly.

## What you need

- **Lightning Enable MCP** with a funded wallet (`discover_api`,
  `access_l402_resource`, `budget`, `receipts`). The general paying procedure,
  including the confirmation gate, lives in
  [`pay-l402-anywhere`](../pay-l402-anywhere/); this skill adds the research
  and citation layer on top.
- A small sats budget the user is comfortable spending.

Argument names below are the Python server's `snake_case`. The .NET server takes
the same arguments in `camelCase` (`max_sats` → `maxSats`).

## Flow

1. **Clarify the question** enough to know what data would actually support it.
   Decide which figures need *real, current* data vs. general knowledge.

2. **Set a budget ceiling** with the user up front (for example, "up to 25
   sats"). Check `budget(action="status")` so you know your headroom before
   spending anything.

3. **Discover sources** with `discover_api` (search the L402 registry, for
   example `discover_api(query="...")`). With `budget_aware` on, it annotates how
   many calls you can afford. Prefer the cheapest source that has the data.

4. **Buy only what you need, one call at a time.** Use
   `access_l402_resource(url="...", max_sats=<per-call cap>)` on each endpoint —
   it runs the full `402 → pay → retry` cycle and returns the data. Track what
   you spent on each call (source + sats + what it bought). If a call needs a
   confirmation code, ask the human for it and re-call with
   `confirmation_nonce="<code>"`; never guess one.

5. **Stay under budget.** Re-check `budget(action="status")` as you go; stop
   before exceeding the ceiling and tell the user if you need more.

6. **Write the answer** grounded in the purchased data. Every figure must trace
   to a specific paid call. If the real data contradicts the obvious narrative,
   say so — that's the value of paying for real data over guessing.

7. **Show the receipt.** Build a JSON array of your paid calls and render it:
   ```
   echo '[{"source":"FRED USD/JPY","sats":5,"what":"DEXJPUS series"}, ...]' \
     | python scripts/receipt.py
   ```
   Cross-check your list against `receipts(source="session")` so the receipt
   matches what the wallet paid. Present the cited answer, then the receipt
   (total sats, calls, 0 accounts).

## Safety / honesty rules

- **Respect the budget ceiling.** Never blow past it; ask first.
- **Cite honestly.** Only claim a figure if a paid call actually returned it.
  Don't dress up a guess as sourced.
- **Cheapest-sufficient source wins** — don't over-buy.
- If no affordable source has the data, say so plainly rather than inventing it.

## Example

> User: "Write me a sourced take on the 2024 yen carry-trade unwind. Up to 25 sats."
>
> → `budget(action="status")` → ok. `discover_api(query="finance")` → finds FRED on
> agent-commerce.store. → `access_l402_resource` for USD/JPY, Nikkei, VIX,
> 10-yr (5 sats each). → write the analysis, every number traced to a call,
> noting the data distinguishes the Aug-2024 unwind from the bigger Apr-2025
> shock. → `receipt.py` → "20 sats, 4 calls, 0 accounts, 0 API keys."
