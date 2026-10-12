# discover-paid-apis

**Find a paid API, see what it costs and how many calls you can afford, then try it once.**

APIs that charge per call over Lightning publish an
[L402](https://github.com/lightninglabs/L402) manifest: what they do, which
endpoints they have, and what each call costs. Many of them are listed in a
public registry. This skill searches that registry for what you asked for, lays
the candidates out with their prices against your wallet and budget, reads the
one you pick without paying, and makes a single paid call only after you say yes.

## Why it's interesting

- **You see the price before anything moves.** Searching the registry and
  reading a manifest are free. The only payment is one call you approved, at a
  price you saw.
- **Affordability is computed, not guessed.** Each result shows how many calls
  your session budget and your wallet balance cover. An unknown price reads
  "unknown", never "free".
- **It works on sites outside the registry too.** Name a site and the skill
  looks for an L402 manifest at its well-known paths.
- **It ends with evidence.** The paid call's result, the sats spent, and the
  session receipt, so you know what you bought and what it cost.

## How it works

1. **Ask** what the API should do and the most one trial call may cost.
2. **Read the budget and balance** with `budget action=status` and
   `get_balance`.
3. **Search** with `discover_api` (`query`, `category`, or both), or read a
   named site's manifest with `discover_api url=...`.
4. **Present a short table:** name, what it does, price per call, calls you can
   afford. You pick one.
5. **Read its manifest, unpaid:** endpoints, methods, and prices. Lightning
   Enable proxies also serve an OpenAPI document at
   `/l402/proxy/{proxyId}/openapi.json`.
6. **One paid call,** after you say yes to the stated price:
   `access_l402_resource` with `max_sats` set to that price.
7. **Report** the result faithfully and the sats spent, from
   `receipts source=session`, then hand off to
   [`pay-l402-anywhere`](../pay-l402-anywhere/) for ongoing use or
   [`cited-answer`](../cited-answer/) for research.

## Requirements

- The [Lightning Enable MCP](https://github.com/refined-element/lightning-enable-mcp)
  server, connected to a funded wallet that returns preimages (NWC, LND, or
  Strike). If that isn't set up yet, run
  [`agent-wallet-setup`](../agent-wallet-setup/) first.
- No Lightning Enable account.

## Try it

> "Find me a weather API I can pay for over Lightning, and try it once. Spend no
> more than 20 sats."

## Safety

- One paid call, after an explicit yes, at a price you saw. Never several paid
  calls to compare APIs.
- The call never pays more than `max_sats`, which never exceeds your ceiling or
  the session budget.
- Larger payments need a confirmation code that goes to you, never to the agent.
- The agent reports only what the call returned, says when a response was
  truncated, and says so when nothing matched or nothing is affordable.
- Macaroons, preimages, and L402 tokens never appear in the agent's output.
- Lightning Enable does not hold funds; the wallet facilitates custody and
  settlement.

## What it doesn't do

It doesn't vouch for a seller, set up a wallet, or call endpoints that need POST
(the paying tool is read-only: GET and HEAD). For listing your own API in the
registry, see [`producer-setup`](../producer-setup/).
