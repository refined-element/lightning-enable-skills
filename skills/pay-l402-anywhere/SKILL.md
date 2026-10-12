---
name: pay-l402-anywhere
description: >-
  Use when the user asks the agent to access, fetch, or pay for a resource or
  API that is gated behind Lightning payment: a request returns HTTP 402
  Payment Required, or the user says things like "pay for this API", "use my
  Lightning wallet to get X", "access this paid endpoint", "buy the data behind
  this L402 wall". Gives any agent, running
  in Hermes, Claude Code, Claude Desktop, or Cursor, the ability to pay L402
  challenges anywhere on the web from a small, bounded wallet, account-lessly,
  with a human in the confirmation loop and a hard budget ceiling. This skill is
  the runtime procedure once a wallet is connected. Do NOT use it to install the
  MCP or connect a wallet from nothing (use agent-wallet-setup), to find a
  paid API when the user has no URL yet (use discover-paid-apis), or to sell
  access to something (use sell-this or producer-setup). Buying physical goods
  from a store is out of scope.
---

# Pay L402 anywhere

Give an agent the ability to pay for anything on the internet that speaks
[L402](https://github.com/lightninglabs/L402) — the HTTP 402 + Lightning +
macaroon standard — from a **bounded wallet it cannot overspend**. This is the
consumer wedge: no account, no card, no subscription, a few sats per call and a
human saying yes.

The [Lightning Enable MCP](https://github.com/refined-element/lightning-enable-mcp)
does the paying. Your job is to drive it safely: discover, check affordability,
confirm, pay, verify. Lightning Enable does not hold funds; the wallet
facilitates custody and settlement.

## What you need

- **Lightning Enable MCP** connected, with a funded wallet. For the "pay
  anywhere" case the wallet must return Lightning **preimages**: use **NWC**
  (CoinOS, Alby Hub, CLINK), **LND**, or **Strike**. OpenNode does **not** return
  preimages and cannot satisfy L402.
- Tools this skill uses:
  - `access_l402_resource` — fetch a URL and auto-pay the L402 challenge if one
    comes back (the happy path).
  - `pay_l402_challenge` — pay a challenge you already hold.
  - `discover_api` — search the L402 registry, or fetch a specific API's manifest.
  - `budget` — `action="status"` to read the caps and session spend,
    `action="tighten"` to lower them to the ceiling the user sets.
  - `get_balance` — the actual funds.
  - `receipts` — `source="session"` for this session's payments,
    `source="durable"` for the wallet's permanent payment log.
  - `verify_confirmation_code` — checks a confirmation code without paying.
    You rarely need it; see step 4.

Argument names below are the Python server's `snake_case`. The .NET server takes
the same arguments in `camelCase`: `max_sats` → `maxSats`, `confirmation_nonce`
→ `confirmationNonce`. Response fields are `camelCase` in both.

## Flow

### 1. Know the leash before you spend
Before the first payment in a session, check both the soft and hard limits:
- `budget(action="status")` — the MCP's configured per-request / per-session caps
  and what this session has spent.
- `get_balance()` — the actual funds. **The wallet balance is the real
  leash**: a 5,000-sat wallet cannot spend 50,000 sats no matter what any prompt
  says.

If the user names a ceiling lower than the configured caps, lower them to match:
`budget(action="tighten", per_request=<ceiling>, per_session=<spent + ceiling>)`,
where `spent` is this session's spend from `budget(action="status")`.
The session cap counts what this session already spent: the budget gate
denies a payment when spent plus `max_sats` exceeds the runtime session cap,
so a session cap equal to the ceiling alone would shrink the ceiling by
whatever was spent before.
Tightening is one-way; an agent can never raise the operator's limits.

State the ceiling back to the user in plain terms ("you've got ~4,800 sats,
capped at 500/call").

### 2. Find the resource (if needed)
If the user named a URL, skip to step 3. If they described a *need* ("find me a
weather API I can pay for"), use `discover_api(query="weather")` to search the
registry; it annotates results with how many calls you can afford at the current
balance. Pick one and show the user the price before buying.

### 3. Access and pay
For a known URL, prefer the one-shot path:
```
access_l402_resource(url="https://…", max_sats=<cap>)
```
The MCP requests the URL, and if it gets `402 Payment Required` with a Lightning
invoice + macaroon, it pays the invoice through your wallet, gets the
preimage, retries with `Authorization: L402 <macaroon>:<preimage>`, and returns
the `200 OK` body. `max_sats` refuses any invoice above your cap.

If you already hold a challenge, use `pay_l402_challenge` instead.

### 4. Handle the confirmation gate
If a payment is **over the auto-approve threshold**, the MCP does **not** pay
silently. It prints a confirmation code to its **console** (or the confirmation
channel the operator configured), where the human can read it and you cannot.
Ask the **human** for that code, then re-call the **same** payment tool with the
same arguments plus `confirmation_nonce="<code>"`. Never invent or guess a code.
`verify_confirmation_code` only checks a code; it never pays.

### 5. Verify and report
Confirm you got a `200` and the content you expected. Report the sats spent and
what it bought. For a running total, `budget(action="status")` shows session
spend against the cap and `receipts(source="session")` lists each payment.

## Safety rules

- **Confirmation before spending, always.** Honor the MCP's thresholds; when it
  asks for a human code, get it from the human. No self-approval.
- **Budget-aware, every call.** Cross-check `budget(action="status")`; the
  most-restrictive limit (MCP config vs. any session ceiling you agreed) wins.
- **Fund only what the agent may spend.** A dedicated small wallet is the safest
  design — the balance bounds the blast radius. Recommend a fresh NWC connection
  with a low wallet-side limit for agent use.
- **One payment at a time.** L402 is stateless — each 402 mints a *new* invoice +
  macaroon. Complete one full 402 → pay → access cycle before starting another;
  never fire concurrent L402 payments or you'll cross invoices and fail.
- **Never echo secrets.** Don't print the NWC connection string, preimages, or
  macaroons back to the user.

## Setup

The agent-side procedure above assumes a wallet is already connected. If nothing
is installed yet, the [`agent-wallet-setup`](../agent-wallet-setup/) skill takes
you from no MCP to a verified paying wallet. To reach the agent from your phone
over Telegram or Signal, see
**[Run L402 anywhere: Hermes + NWC](https://docs.lightningenable.com/products/agentic-commerce/hermes-nwc-setup)**.

## Example

> User: "Use my Lightning wallet to pull the premium forecast from that weather
> API — but don't blow past 200 sats."
>
> → `budget(action="status")` + `get_balance()` (4,800 sats, cap 500/call,
> nothing spent yet this session) →
> `budget(action="tighten", per_request=200, per_session=200)` → "you're good,
> capped at 200" → `access_l402_resource(url=…, max_sats=200)` → 402 → pays
> 150 sats → preimage → 200 OK → "Got the forecast, spent 150 sats, 4,650 left."
