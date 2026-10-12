# sell-this

**Turn anything into a paid endpoint — mint an L402 paywall, verify payment, then deliver.**

Most "AI commerce" demos show an agent *buying*. This is the other half: an agent
**selling**. Point at a resource — a file, an answer, an API endpoint, a piece of
work — set a price in sats, and the agent mints an [L402](https://github.com/lightninglabs/L402)
challenge that anyone (human or another agent) must pay to access. When they pay,
the agent verifies the cryptographic proof before handing anything over.

Together with the buyer-side skills, this makes an agent a **full commerce
participant**: it can both earn and spend.

No account yet? Start with [`producer-setup`](../producer-setup/). Selling a whole
existing API rather than one resource? Use
[`create-l402-proxy`](../create-l402-proxy/).

## Why it's interesting

- **Agents as sellers.** Your agent can monetize its own output — research,
  generated content, access to a tool — with no merchant account, no Stripe, no
  checkout page. A Lightning invoice and a cryptographic receipt.
- **Account-less for the buyer.** The buyer needs no account with you. The
  preimage *is* the proof of payment.
- **Composable.** Pair it with `negotiate-and-buy` (the agent-to-agent flow) and
  two agents can transact with each other autonomously.

## How it works

1. **`l402_producer(action="create", resource, price_sats, description?)`** →
   returns a Lightning invoice + macaroon. That pair is the "402 Payment
   Required" challenge you give the buyer.
2. The buyer pays the invoice and gets a **preimage**. They send back the token
   `macaroon:preimage`.
3. **`l402_producer(action="verify", macaroon, preimage)`** → confirms payment.
   Only when it returns `valid: true` do you deliver.

## What you need

- [Lightning Enable MCP](https://github.com/refined-element/lightning-enable-mcp)
  2.x with **`LIGHTNING_ENABLE_API_KEY`** set (the Free Producer Sandbox or an
  Agentic Commerce plan) — the `l402_producer` tool requires it.

## Try it

> "Charge 100 sats for this market summary I wrote."

## Safety

- **Never deliver before verification returns `valid: true`.** No valid
  preimage = no payment.
- The price is set by you, the seller.
- Don't put the payload (the thing you're selling) into the challenge's public
  `resource`/`description` fields — describe it, don't include it.
- Lightning Enable does not hold funds; the payment provider or your own wallet
  facilitates custody and settlement.

## Example

→ mints a 100-sat L402 challenge → shares the invoice + macaroon → buyer pays and
returns the token → `l402_producer(action="verify", …)` returns `valid: true` →
the summary is delivered. A real sale over Lightning, no account or card on the
buyer's side.
