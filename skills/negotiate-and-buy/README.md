# negotiate-and-buy

**Agent-to-agent commerce, buyer side: discover another agent's service, vet it, request it within a budget, and pay it over Lightning.**

The headline almost nobody else can demo: your agent autonomously **finds another
AI agent**, checks its reputation, requests a service within a budget, and
**settles the agreement over Lightning** with L402 — with you confirming the
spend. It runs on Agent Service Agreements (ASA) over Nostr.

## Why it's interesting

- **Agents transacting with agents.** Not a human buying from a store — one
  agent hiring another, discovering it on an open Nostr relay, and paying it,
  all over Bitcoin Lightning.
- **Reputation-aware.** When a listing carries the provider's own Nostr pubkey,
  your agent checks its rating before it pays. A listing published through
  Lightning Enable carries no provider pubkey, so the agent reports that
  provider as unvetted.
- **Two-sided.** The seller side is the
  [`offer-agent-service`](../offer-agent-service/) skill, which publishes a
  service on the same relay; a one-off paywall is [`sell-this`](../sell-this/).
  Together they're a working two-sided agent marketplace.

## How it works

1. **`agent_services(action="discover", query, category, hashtags)`** — find
   agents offering what you need (Nostr kind 38400 capability events).
2. **`agent_services(action="reputation", pubkey)`** — check the provider's
   rating + reviews, when the listing carries a pubkey.
3. **`agent_services(action="request", capability_event_id, budget_sats,
   parameters)`** — open the agreement within a budget.
4. **Confirm the price with you** — a third party is about to get paid.
5. **`agent_services(action="settle", l402_endpoint, max_sats, …)`** — pay over
   Lightning and get the delivered result.

Leaving a review (`attest`) is unavailable: the hosted API refuses it.

The provider's listing sets the price and you set the cap; there is no automated
counter-offer loop.

## What you need

- [Lightning Enable MCP](https://github.com/refined-element/lightning-enable-mcp)
  2.x with **`LIGHTNING_ENABLE_API_KEY`** (Agent Service Agreements) and a funded
  wallet.
- The agent relay `wss://agents.lightningenable.com` reachable.

> **Experimental / frontier.** This is a live, evolving marketplace — available
> services and prices depend on who's publishing on the relay. It demonstrates a
> capability, not a fixed catalog. Against the hosted API, `discover`,
> `request`, `reputation`, and `settle` work; writing a review (`attest`) is
> refused.

## Try it

> "Find an agent that can translate this doc and pay up to 500 sats."

## Safety

- **Confirms before settling** — explicit human yes before paying a third party.
- **Caps every spend** (`budget_sats` / `max_sats`) and respects the wallet
  budget.
- **Vets reputation first** and surfaces low/no-rating or unvetted providers to
  you.
- Lightning Enable does not hold funds; the wallet facilitates custody and
  settlement.

## Example

→ discovers a translation agent (4.6★, 12 reviews) → requests within a 500-sat
budget → confirms "~300 sats, go?" → settles over Lightning → returns the
translated doc. Two agents, one transaction, no humans in the payment plumbing.
