# producer-setup

**From nothing installed to a live paid API on the agent's own wallet — no human in the payment plumbing.**

Every other producer story starts after the boring part: you already have an
account, an API key, a merchant record, a payment provider. This skill *is* the
boring part, done by the agent. Point it at an API and a price, and it connects
a wallet, buys itself an account over [L402](https://github.com/lightninglabs/L402)
for about 100 sats, wires the receive wallet, publishes a priced endpoint, and
then buys one call from itself to prove the thing charges.

The human supplies four things: a funded Lightning wallet, a spend ceiling, the
API to sell, and the price. Everything between those decisions is a tool call.

## Why it's interesting

- **The signup form is the protocol.** Account creation is a 100-sat L402
  payment, not a checkout page. No card, no form, no waiting for a human to click
  through a dashboard — the agent pays for its own account with its own wallet.
- **The money lands in a wallet you already control.** The receive wallet is the
  same [NWC](https://nwc.dev) wallet the agent pays from. Lightning Enable does
  not hold funds; the wallet facilitates custody and settlement.
- **It proves the sale, not a status page.** Before the hand-off, the agent
  makes one real purchase against the new endpoint: 402, pay, 200. You watch
  the sale land in `list_challenges`, and the compatibility report reuses that
  call as its paid evidence, before anyone calls the endpoint live.
- **Flat subscription, no cut.** Lightning Enable never takes a percentage of the
  sats. Every satoshi a buyer pays settles to your wallet.

## How it works

1. **Ask first** — the wallet, the ceiling (~100 sats plus one test call), and
   what to sell at what price. Two of the steps below move money.
2. **Connect and bound the wallet** — `setup_wallet` (NWC-first), `get_balance`,
   then `budget action=tighten` so the agent runs on a short leash.
3. **Buy an account** — `create_lightning_enable_account` pays the ~100-sat Fast
   Lane challenge and stores the API key. The MCP restarts once so the
   producer tools unlock.
4. **Wire the receive wallet** — `l402_producer action=configure_receive` points
   the merchant at the same NWC wallet, so sales land where you expect. With no
   argument it reuses the MCP's own wallet; it refuses (and says so) if that
   wallet is LND, Strike, or OpenNode, since none of those is a connection
   string.
5. **Publish a priced endpoint** — `create_proxy` → `add_endpoint` → `publish`,
   which hands back a per-proxy OpenAPI 3.1 document at
   `/l402/proxy/{proxyId}/openapi.json` (every operation carries an `x-payment`
   extension with the price) and the JSON manifest agents and the L402 registry
   read.
6. **Self-test** — `access_l402_resource` against the new endpoint, then
   `list_challenges challenge_status=paid` to see the sale land.
7. **Verify**: `l402-compatibility-report` checks the endpoint and records the
   self-test call as its paid evidence instead of paying again.
8. **Hand off**: what to share, what to watch, how to add endpoints and change
   prices, what happens when the 30-day trial ends, and how the agent renews
   the plan in sats with `renew_lightning_enable_subscription` (MCP 2.1.0 or
   later).

## Requirements

- [Lightning Enable MCP](https://github.com/refined-element/lightning-enable-mcp)
  installed (NuGet, pip, or Docker).
- A **funded** wallet that returns Lightning preimages: NWC (Alby Hub, CoinOS,
  CLINK), LND, or Strike. OpenNode cannot pay L402 challenges. This skill does
  not create or fund a wallet.
- A publicly reachable upstream API. Private and localhost addresses are refused
  on purpose — that is SSRF protection, not a bug.

## Caveats

- **Two actions need a newer Lightning Enable API than the one in production
  today.** `configure_receive` needs the NWC receiving lane and `list_challenges`
  needs the challenge-listing route; both ship with the API release this version
  targets. `create`, `verify`, `create_proxy`, `add_endpoint`, and `publish` work
  against every build. Run `l402_producer action=status` first — it degrades
  gracefully and reports what the deployment you are pointed at supports.
- **Argument names differ by package.** The Python server takes `snake_case`
  (`target_base_url`, `challenge_status`); the .NET server takes the camelCase
  equivalents. The skill documents the Python spelling and names the mapping.

## Safety

- Explicit human yes before any spend, with the total stated up front.
- The budget is tightened before the first payment, never after.
- Secrets stay secret: the NWC string, the API key, macaroons, and preimages are
  never echoed — the agent reports `<set>` instead.
- One L402 payment at a time, and never a second signup to fix a missing tool
  (that pays twice; the real cause is almost always a missed MCP restart).

## How buyers find you

Publishing lists the endpoint in the Lightning Enable registry. Any agent with
the Lightning Enable MCP finds it with `discover_api` and pays each call from
its own wallet over L402, with `access_l402_resource`,
[`pay-l402-anywhere`](../pay-l402-anywhere/), or any L402 client. No
marketplace account or credits are involved, and every sat settles to your
wallet. Before the hand-off, the agent checks the endpoint with
[`l402-compatibility-report`](../l402-compatibility-report/), the Lightning
Enable L402 compatibility report, and records the self-test call as its paid
evidence instead of paying again.

## Optional: list on Amazap

Your setup is complete without this. For more distribution, the agent can
offer a draft listing on [Amazap](https://amazap.com/sell), a separate
marketplace, after the hand-off. It asks first, reuses the compatibility
report instead of paying again, drafts the copy, and stops. You review the
draft, the current Amazap seller terms, and both prices, enter your contact
email, and submit it yourself; submitting publishes the listing once
Amazap's checks pass. After any price change, re-run Amazap's checks. The
agent never calls the endpoint listed until it has read the listing back
from Amazap. Lightning Enable does not hold funds; the payment provider
facilitates custody and settlement. Details:
[Amazap marketplace: Seller handoff](https://github.com/refined-element/lightning-enable-skills/blob/main/references/amazap-marketplace.md#seller-handoff).

## What it doesn't do

It doesn't create a wallet, fund one, generate demand, or promise revenue. It
gets you a live endpoint that can charge — buyers are still your problem.

## Example

> "Set me up to sell my weather API over Lightning — 10 sats a call, 200 sats
> budget for setup."

→ connects the wallet → pays 100 sats for an account → wires the receive wallet →
publishes `/forecast` at 10 sats → buys one call from itself → checks it with
the compatibility report → "Live and charging, listed in the Lightning Enable
registry. Share this OpenAPI URL. Spent 110 sats. Trial ends in 30 days;
without billing it drops to the Free Producer Sandbox."

Pairs with [`sell-this`](../sell-this/) once the account exists (one-off paywalls
without a proxy). To keep the setup spend visible, ask the agent for
`budget(action="status")` and `receipts(source="durable")`.
