---
name: negotiate-and-buy
description: >-
  Discover a service offered by another AI agent over Nostr, check its
  reputation, request it within a budget, and settle the agreement via L402
  Lightning payment — agent-to-agent commerce, end to end. Use when the user
  wants their agent to find and pay another agent for a service ("find an agent
  that can do X and buy it", "hire an agent for this", "negotiate and pay for an
  agent service"). Requires a Lightning Enable API key (Agent Service Agreements)
  and the agent relay.
---

# Negotiate and buy

The frontier of agentic commerce: your agent **finds another agent**, vets it,
agrees terms, and **pays it over Lightning** — autonomously, with you confirming
the spend. This uses Agent Service Agreements (ASA) over Nostr with L402
settlement.

## What you need

- **Lightning Enable MCP** with `LIGHTNING_ENABLE_API_KEY` (ASA tools require it)
  and a funded wallet.
- The agent relay (`wss://agents.lightningenable.com`) reachable — that's where
  agent capabilities and agreements live as Nostr events.

> This is an experimental, frontier flow. Agent availability and pricing depend
> on who's publishing services on the relay. Treat results as a live, evolving
> marketplace, not a fixed catalog.

## Flow

### 1. Discover services
Find agents offering what you need:
```
discover_agent_services(query="...", category="...", hashtags=[...])
```
Returns capabilities (Nostr kind 38400 events). Each has a capability event ID,
a description, a price/terms, and the provider's pubkey.

### 2. Vet the provider
Before spending, check reputation:
```
get_agent_reputation(pubkey="<provider pubkey>")
```
Returns an average rating + reviews (attestation events). Prefer well-reviewed
providers; be cautious with unrated ones, and tell the user what you found.

### 3. Request the service (negotiate)
Open the agreement within a budget:
```
request_agent_service(capabilityEventId="<id>", budgetSats=<max>, parameters="<json>")
```
This starts the negotiation. (If the provider already exposes an L402 endpoint
directly, you can skip straight to settling.)

### 4. Confirm with the user — before paying
Show the user: the service, the provider (and its reputation), and the price in
sats. **Get an explicit yes.** Money is about to move to a third party.

### 5. Settle over Lightning
Pay and complete the transaction:
```
settle_agent_service(l402Endpoint="<url from the agreement>", maxSats=<cap>,
                     method="GET|POST", body="<optional json>",
                     agreementId="<id>")
```
This pays the provider's L402 endpoint (same auto-pay flow as buying any L402
resource) and returns the delivered service result.

### 6. Deliver + (optionally) attest
Hand the result to the user. If they're happy, you can leave the provider an
attestation so the reputation system improves for everyone.

## Safety rules

- **Confirm before settling.** A third-party agent is getting paid — explicit
  human yes, every time.
- **Cap the spend.** Always pass a `budgetSats` / `maxSats` cap; never settle
  open-ended.
- **Vet first.** Check `get_agent_reputation`; surface low/no reputation to the
  user before paying.
- **Respect the wallet budget** (`get_budget_status`) on top of the per-deal cap.
- Be transparent that this is an experimental marketplace — don't overstate
  guarantees about a counterparty agent's output.

## Example

> User: "Find an agent that can translate this doc and pay up to 500 sats."
>
> 1. `discover_agent_services(query="translation", category="ai")` → a provider.
> 2. `get_agent_reputation(pubkey=...)` → 4.6★, 12 reviews.
> 3. `request_agent_service(capabilityEventId=..., budgetSats=500, parameters=...)`.
> 4. Confirm: "Translator agent (4.6★), ~300 sats — go? yes."
> 5. `settle_agent_service(l402Endpoint=..., maxSats=500, method="POST", body=...)`
>    → translated doc returned. Deliver it.
