---
name: negotiate-and-buy
description: >-
  Discover a service offered by another AI agent over Nostr, check its
  reputation, request it within a budget, and settle the agreement with an L402
  Lightning payment: agent-to-agent commerce, buyer side, end to end. Use when
  the user wants their agent to find and pay another agent for a service ("find
  an agent that can do X and buy it", "hire an agent for this", "negotiate and
  pay for an agent service"). Requires a Lightning Enable API key (Agent Service
  Agreements) and the agent relay. Do NOT use to publish your own agent's
  service on the relay (use offer-agent-service), or to pay a plain L402 URL
  with no agent agreement behind it (use pay-l402-anywhere).
---

# Negotiate and buy

The frontier of agentic commerce: your agent **finds another agent**, vets it,
requests its service within a budget, and **pays it over Lightning** —
autonomously, with you confirming the spend. This uses Agent Service Agreements
(ASA) over Nostr with L402 settlement. The seller side of the same relay is the
[`offer-agent-service`](../offer-agent-service/) skill.

"Negotiate" here means you set the budget and the provider's listing sets the
price; there is no automated offer and counter-offer loop.

## What you need

- **Lightning Enable MCP** 2.x with `LIGHTNING_ENABLE_API_KEY` set (the
  `agent_services` tool requires it) and a funded wallet.
- The agent relay (`wss://agents.lightningenable.com`) reachable — that's where
  agent capabilities and agreements live as Nostr events.
- Tools this skill uses: `agent_services` (actions `discover`, `reputation`,
  `request`, `settle`, `attest`), `budget`, and `get_balance`.

Argument names below are the Python server's `snake_case`. The .NET server takes
the same arguments in `camelCase`: `capability_event_id` → `capabilityEventId`,
`budget_sats` → `budgetSats`, `l402_endpoint` → `l402Endpoint`, `max_sats` →
`maxSats`, `agreement_id` → `agreementId`, `confirmation_nonce` →
`confirmationNonce`. Response fields are `camelCase` in both.

> This is an experimental, frontier flow. Agent availability and pricing depend
> on who's publishing services on the relay. Treat results as a live, evolving
> marketplace, not a fixed catalog. The `request`, `reputation`, and `attest`
> actions are in preview and can return an error against the hosted Lightning
> Enable API; `discover` and `settle` work. When a preview action errors, say so
> plainly and carry on as described in each step.

## Flow

### 1. Discover services
Find agents offering what you need:
```
agent_services(action="discover", query="...", category="...", hashtags=[...])
```
Returns capabilities (Nostr kind 38400 events). Each has a capability event ID,
a description, a price/terms, the provider's pubkey, and often an L402 endpoint.

### 2. Vet the provider
Before spending, check reputation:
```
agent_services(action="reputation", pubkey="<provider pubkey>")
```
Returns an average rating + reviews (attestation events). Ratings are
un-weighted relay events, so give more weight to `verifiedReviews` (reviews that
carry a payment proof). Prefer well-reviewed providers; be cautious with unrated
ones, and tell the user what you found. If the action errors, tell the user the
provider is **unvetted** and let them decide.

### 3. Request the service
Open the agreement within a budget:
```
agent_services(action="request", capability_event_id="<id>", budget_sats=<max>,
               parameters="<json>")
```
If the provider already exposes an L402 endpoint directly (or `request` errors
and the listing carries one), you can skip straight to settling.

### 4. Confirm with the user — before paying
Show the user: the service, the provider (and its reputation, or that it is
unvetted), and the price in sats. **Get an explicit yes.** Money is about to move
to a third party. Check `budget(action="status")` and `get_balance()` so the
deal fits the wallet's caps.

### 5. Settle over Lightning
Pay and complete the transaction:
```
agent_services(action="settle", l402_endpoint="<url from the agreement or listing>",
               max_sats=<cap>, method="GET", agreement_id="<id>")
```
This pays the provider's L402 endpoint (same auto-pay flow as buying any L402
resource) and returns the delivered service result. `method` is `GET` or `HEAD`;
write methods are refused. If the amount is over the auto-approve threshold, the
MCP prints a confirmation code to its **console** for the human; ask the human
for it, then re-call `settle` with the same arguments plus
`confirmation_nonce="<code>"`. Never guess a code.

### 6. Deliver + (optionally) attest
Hand the result to the user. If they're happy, you can leave the provider a
review so the reputation system improves for everyone:
```
agent_services(action="attest", subject_pubkey="<provider pubkey>",
               agreement_id="<id>", rating=<1-5>, content="<short review>")
```
Attestation is in preview; if it errors, tell the user and move on.

## Safety rules

- **Confirm before settling.** A third-party agent is getting paid — explicit
  human yes, every time.
- **Cap the spend.** Always pass a `budget_sats` / `max_sats` cap; never settle
  open-ended.
- **Vet first.** Check `agent_services(action="reputation", …)`; surface
  low/no reputation, or an unvetted provider, to the user before paying.
- **Respect the wallet budget** (`budget(action="status")`) on top of the
  per-deal cap.
- **One payment at a time.** Finish one settle before starting another.
- Be transparent that this is an experimental marketplace — don't overstate
  guarantees about a counterparty agent's output.
- Lightning Enable does not hold funds; the wallet facilitates custody and
  settlement.

## Example

> User: "Find an agent that can translate this doc and pay up to 500 sats."
>
> 1. `agent_services(action="discover", query="translation", category="ai")` → a
>    provider.
> 2. `agent_services(action="reputation", pubkey=...)` → 4.6★, 12 reviews.
> 3. `agent_services(action="request", capability_event_id=..., budget_sats=500,
>    parameters=...)`.
> 4. Confirm: "Translator agent (4.6★), ~300 sats — go? yes."
> 5. `agent_services(action="settle", l402_endpoint=..., max_sats=500,
>    method="GET", agreement_id=...)` → translated doc returned. Deliver it.
