---
name: pay-l402-anywhere
description: >-
  Use when the user asks the agent to access, fetch, or pay for a resource or
  API that is gated behind Lightning payment — i.e. a request returns HTTP 402
  Payment Required, or the user says things like "pay for this API", "use my
  Lightning wallet to get X", "access this paid endpoint", "buy the data behind
  this L402 wall", or "find and pay a paid API for Y". Gives any agent — running
  in Hermes, Claude Code, Claude Desktop, or Cursor — the ability to pay L402
  challenges anywhere on the web from a small, bounded Nostr Wallet Connect (NWC)
  wallet, account-lessly, with a human in the confirmation loop and a hard budget
  ceiling. Setup (Hermes + NWC for mobile) is documented separately; this skill
  is the runtime procedure the agent follows once a wallet is connected.
---

# Pay L402 anywhere

Give an agent the ability to pay for anything on the internet that speaks
[L402](https://github.com/lightninglabs/L402) — the HTTP 402 + Lightning +
macaroon standard — from a **bounded wallet it cannot overspend**. This is the
consumer wedge: no account, no card, no subscription, just a few sats per call
and a human saying yes.

The [Lightning Enable MCP](https://github.com/refined-element/lightning-enable-mcp)
does the paying. Your job is to drive it safely: discover, check affordability,
confirm, pay, verify.

## What you need

- **Lightning Enable MCP** connected, with a funded wallet. For the "pay
  anywhere" case the wallet must return Lightning **preimages** — use **NWC**
  (CoinOS, Alby Hub, CLINK), **LND**, or **Strike**. OpenNode does **not** return
  preimages and cannot satisfy L402.
- Tools this skill uses:
  - `access_l402_resource` — fetch a URL and auto-pay the L402 challenge if one
    comes back (the happy path).
  - `pay_l402_challenge` — pay a challenge you already hold.
  - `discover_api` — search the L402 registry, or fetch a specific API's manifest.
  - `get_budget_status` / `check_wallet_balance` — know the ceiling and the funds
    before spending.
  - `confirm_payment` — used only when a payment exceeds the auto-approve
    threshold (the server prints a code to its console for the human).

## Flow

### 1. Know the leash before you spend
Before the first payment in a session, check both the soft and hard limits:
- `get_budget_status` — the MCP's configured per-request / per-session caps.
- `check_wallet_balance` — the actual funds. **The wallet balance is the real
  leash**: a 5,000-sat wallet cannot spend 50,000 sats no matter what any prompt
  says.

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
access_l402_resource(url="https://…")
```
The MCP requests the URL, and if it gets `402 Payment Required` with a Lightning
invoice + macaroon, it pays the invoice through your NWC wallet, gets the
preimage, retries with `Authorization: L402 <macaroon>:<preimage>`, and returns
the `200 OK` body.

If you already hold a challenge, use `pay_l402_challenge` instead.

### 4. Handle the confirmation gate
If a payment is **over the auto-approve threshold**, the MCP does **not** pay
silently. It prints a confirmation code to its **console** (visible to the human
operator, never returned to you). Ask the **human** for that code, then re-call
the original payment tool with its confirmation-nonce parameter. Never invent or
guess a code — you cannot read the server's console, and that's the point.

### 5. Verify and report
Confirm you got a `200` and the content you expected. Report the sats spent and
what it bought. If you're tracking a session budget, this is where the
[`l402-meter`](../l402-meter/) skill logs the call.

## Safety rules

- **Confirmation before spending, always.** Honor the MCP's thresholds; when it
  asks for a human code, get it from the human. No self-approval.
- **Budget-aware, every call.** Cross-check `get_budget_status`; the
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

The agent-side procedure above assumes a wallet is already connected. For the
human-facing setup — installing Hermes, creating a CoinOS NWC wallet, wiring it
into `~/.lightning-enable/config.json`, and reaching it from Telegram/Signal on
your phone — see **[Run L402 anywhere: Hermes + NWC](https://docs.lightningenable.com/products/l402-microtransactions/hermes-nwc-setup)**.

## Example

> User: "Use my Lightning wallet to pull the premium forecast from that weather
> API — but don't blow past 200 sats."
>
> → `get_budget_status` + `check_wallet_balance` (4,800 sats, cap 500/call) →
> "you're good, under your 200 ceiling" → `access_l402_resource(url=…)` → 402 →
> pays 150 sats via NWC → preimage → 200 OK → "Got the forecast, spent 150 sats,
> 4,650 left."
