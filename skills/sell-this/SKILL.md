---
name: sell-this
description: >-
  Turn a resource (a file, an answer, an API endpoint, a piece of work) into a
  paid endpoint by minting an L402 challenge that charges sats for access, then
  verifying payment before delivering. Use when the user wants to SELL or
  monetize access to something to another agent or person over Lightning ("charge
  for this", "sell access to this", "put this behind a paywall", "monetize this").
  This is the PRODUCER side of L402. Requires a Lightning Enable API key with an
  Agentic Commerce subscription.
---

# Sell this

Make the agent a **seller**, not just a buyer. Point at a resource, set a price
in sats, and mint an L402 challenge that anyone (human or agent) must pay to
access. When they pay and present the token, verify it before you hand over the
goods. This is the other half of agentic commerce — agents that can both buy
*and* sell.

## What you need

- **Lightning Enable MCP** with `LIGHTNING_ENABLE_API_KEY` set (Agentic Commerce
  subscription) — the producer tools `create_l402_challenge` and
  `verify_l402_payment` require it.
- A resource to sell and a price the user sets.

## Flow

### 1. Create the challenge (the paywall)

Use `create_l402_challenge`:
- `resource` — a URL, service name, or description of what you're selling.
- `priceSats` — the price in satoshis (the user decides).
- `description` — optional, shown on the Lightning invoice.

It returns a **Lightning invoice** + a **macaroon**. Together these are the 402
challenge you present to the buyer:
> *"402 Payment Required — pay this invoice, then send back the token
> `<macaroon>:<preimage>`."*

Share the invoice + macaroon with the buyer (paste them, or hand them to the
requesting agent).

### 2. Verify payment before delivering

When the buyer pays, they get a **preimage** (proof of payment) and send you the
token `macaroon:preimage`. Verify it with `verify_l402_payment`:
- `macaroon` — the base64 macaroon from the token.
- `preimage` — the hex preimage from the token.

**Only deliver the resource if verification succeeds.** If it fails, do not hand
anything over — they haven't paid (or the token is forged/expired).

### 3. Deliver

On a verified token, deliver the resource (send the file, return the answer,
grant the access). Done — you just sold something over Lightning, no account or
card on either side.

## Safety rules

- **Never deliver before `verify_l402_payment` succeeds.** The preimage is the
  proof; no valid preimage = no payment = no delivery.
- **Set the price with the user**; don't guess what to charge.
- **Don't leak the resource** in the challenge `description` or `resource`
  fields — those are public on the invoice. Describe what's for sale, don't
  include the payload.
- One token proves one payment; don't accept a reused/forged token.

## Example

> User: "Charge 100 sats for this market summary I wrote."
>
> 1. `create_l402_challenge(resource="market-summary-2026-06", priceSats=100,
>    description="Daily market summary")` → invoice + macaroon.
> 2. Share: "Pay this invoice, then send me `<macaroon>:<preimage>`."
> 3. Buyer pays → sends token. `verify_l402_payment(macaroon, preimage)` → valid.
> 4. Deliver the summary.
