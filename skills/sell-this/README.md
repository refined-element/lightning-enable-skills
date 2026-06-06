# sell-this

**Turn anything into a paid endpoint — mint an L402 paywall, verify payment, then deliver.**

Most "AI commerce" demos show an agent *buying*. This is the other half: an agent
**selling**. Point at a resource — a file, an answer, an API endpoint, a piece of
work — set a price in sats, and the agent mints an [L402](https://github.com/lightninglabs/L402)
challenge that anyone (human or another agent) must pay to access. When they pay,
the agent verifies the cryptographic proof before handing anything over.

Together with the buyer-side skills, this makes an agent a **full commerce
participant**: it can both earn and spend.

## Why it's interesting

- **Agents as sellers.** Your agent can monetize its own output — research,
  generated content, access to a tool — with no merchant account, no Stripe, no
  checkout page. Just a Lightning invoice and a cryptographic receipt.
- **Account-less on both ends.** The buyer needs no account with you; you need no
  payment processor. The preimage *is* the proof of payment.
- **Composable.** Pair it with `negotiate-and-buy` (the agent-to-agent flow) and
  two agents can transact with each other autonomously.

## How it works

1. **`create_l402_challenge(resource, priceSats, description?)`** → returns a
   Lightning invoice + macaroon. That pair is the "402 Payment Required"
   challenge you give the buyer.
2. The buyer pays the invoice and gets a **preimage**. They send back the token
   `macaroon:preimage`.
3. **`verify_l402_payment(macaroon, preimage)`** → confirms payment. Only then do
   you deliver.

## Requirements

- [Lightning Enable MCP](https://github.com/refined-element/lightning-enable-mcp)
  with **`LIGHTNING_ENABLE_API_KEY`** set (Agentic Commerce subscription) — the
  producer tools require it.

## Safety

- **Never deliver before verification succeeds.** No valid preimage = no payment.
- The price is set by you, the seller.
- Don't put the payload (the thing you're selling) into the challenge's public
  `resource`/`description` fields — describe it, don't include it.

## Example

> "Charge 100 sats for this market summary."

→ mints a 100-sat L402 challenge → shares the invoice + macaroon → buyer pays and
returns the token → `verify_l402_payment` confirms → the summary is delivered. A
real sale over Lightning, no account or card on either side.
