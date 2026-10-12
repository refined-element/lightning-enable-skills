---
name: sell-this
description: >-
  Turn a resource (a file, an answer, an API endpoint, a piece of work) into a
  paid endpoint by minting an L402 challenge that charges sats for access, then
  verifying payment before delivering. Use when the user wants to SELL or
  monetize access to something to another agent or person over Lightning ("charge
  for this", "sell access to this", "put this behind a paywall", "monetize this").
  This is the PRODUCER side of L402. Requires a Lightning Enable API key (the
  Free Producer Sandbox or an Agentic Commerce plan). Do NOT use when there is no
  account or API key yet (use producer-setup), or to put a whole existing API
  behind a priced proxy (use create-l402-proxy).
---

# Sell this

Make the agent a **seller**, not only a buyer. Point at a resource, set a price
in sats, and mint an L402 challenge that anyone (human or agent) must pay to
access. When they pay and present the token, verify it before you hand over the
goods. This is the other half of agentic commerce — agents that can both buy
*and* sell.

An account with no API key yet is the [`producer-setup`](../producer-setup/)
skill's job, and wrapping a whole API in a paid proxy is
[`create-l402-proxy`](../create-l402-proxy/); this skill charges for one
resource on an account you already have.

## What you need

- **Lightning Enable MCP** 2.x with `LIGHTNING_ENABLE_API_KEY` set (the Free
  Producer Sandbox or an Agentic Commerce plan) — the `l402_producer` tool
  requires it. This skill uses its `create` and `verify` actions.
- A resource to sell and a price the user sets.

Argument names below are the Python server's `snake_case`. The .NET server takes
the same arguments in `camelCase` (`price_sats` → `priceSats`). Response fields
are `camelCase` in both.

## Flow

### 1. Create the challenge (the paywall)

Call `l402_producer(action="create", resource=…, price_sats=…, description=…)`:
- `resource` — a URL, service name, or description of what you're selling.
- `price_sats` — the price in satoshis (the user decides).
- `description` — optional, shown on the Lightning invoice.

It returns a **Lightning invoice** + a **macaroon** (under `challenge`). Together
these are the 402 challenge you present to the buyer:
> *"402 Payment Required — pay this invoice, then send back the token
> `<macaroon>:<preimage>`."*

Share the invoice + macaroon with the buyer (paste them, or hand them to the
requesting agent).

### 2. Verify payment before delivering

When the buyer pays, they get a **preimage** (proof of payment) and send you the
token `macaroon:preimage`. Verify it with
`l402_producer(action="verify", macaroon=…, preimage=…)`:
- `macaroon` — the base64 macaroon from the token.
- `preimage` — the hex preimage from the token.

**Only deliver the resource if the result says `valid: true`.** A result with
`success: true` and `valid: false` means the call worked and the payment did
not: they haven't paid (or the token is forged/expired). Do not hand anything
over.

### 3. Deliver

On a verified token, deliver the resource (send the file, return the answer,
grant the access). Done — you sold something over Lightning, no account or
card on the buyer's side. Lightning Enable does not hold funds; the payment
provider or the merchant's own wallet facilitates custody and settlement.

## Safety rules

- **Never deliver before `l402_producer(action="verify", …)` returns
  `valid: true`.** The preimage is the proof; no valid preimage = no payment =
  no delivery.
- **Set the price with the user**; don't guess what to charge.
- **Don't leak the resource** in the challenge `description` or `resource`
  fields — those are public on the invoice. Describe what's for sale, don't
  include the payload.
- One token proves one payment; don't accept a reused/forged token.
- **Don't echo the buyer's preimage** back into the conversation once verified.

## Example

> User: "Charge 100 sats for this market summary I wrote."
>
> 1. `l402_producer(action="create", resource="market-summary-2026-06",
>    price_sats=100, description="Daily market summary")` → invoice + macaroon.
> 2. Share: "Pay this invoice, then send me `<macaroon>:<preimage>`."
> 3. Buyer pays → sends token.
>    `l402_producer(action="verify", macaroon=…, preimage=…)` → `valid: true`.
> 4. Deliver the summary.
