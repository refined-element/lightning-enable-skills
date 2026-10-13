# create-l402-proxy

**Charge per call for an API you already run, on the Lightning Enable account you already have.**

You have an API and a Lightning Enable account. This skill has your agent put
the API behind a paid proxy: every call answers HTTP 402 Payment Required with
a Lightning invoice until the caller pays, and then the call goes through. The
agent creates the proxy, prices each route, publishes it to the L402 registry
so other agents can find it, and buys one call from it to prove it charges.

Lightning Enable does not hold funds; the wallet (or the payment provider)
facilitates custody and settlement. Lightning Enable charges a flat
subscription and never takes a cut of the sats.

## What you need

- [Lightning Enable MCP](https://github.com/refined-element/lightning-enable-mcp)
  installed, with your merchant API key in `LIGHTNING_ENABLE_API_KEY` or
  `~/.lightning-enable/config.json`. No account yet? Use
  [`producer-setup`](../producer-setup/) instead; it creates one.
- A receive wallet on the account: Strike, OpenNode, or a Nostr Wallet Connect
  (NWC) wallet. The agent can wire the MCP's own NWC wallet for you.
- An API reachable on the public internet, with a domain name, on port 80 or
  443. Localhost and private addresses are refused on purpose.
- The price per call in sats, and a few sats in a wallet that returns preimages
  (NWC, LND, or Strike) for the one self-test call.

## Try it

> "Wrap my weather API at https://api.example-weather.dev with L402, 10 sats a
> call for GET /forecast."

## What it does

1. Reads the account with `l402_producer action=status`: plan, receive wallet,
   proxy count. Wires a receive wallet with `configure_receive` if there is
   none.
2. Asks you for the upstream URL, the routes, the price, and a self-test
   ceiling, then waits.
3. `create_proxy`, then one `add_endpoint` per route, then `publish`. You get
   two public links: a per-proxy OpenAPI 3.1 document at
   `/l402/proxy/{proxyId}/openapi.json`, with an `x-payment` price on every
   operation, and the JSON manifest at
   `/l402/proxy/{proxyId}/.well-known/l402-manifest.json`.
4. Reads the OpenAPI document for free, then, with your yes, buys one call:
   402, pay, 200.
5. Shows the sale with `list_challenges challenge_status=paid` and tells you
   what to share and how to manage it.

## One thing to know about prices

From the MCP, the proxy charges its **default price** for every route. The
price on each route is what the manifest advertises; the skill sets both to the
same number so buyers pay what they read. To charge different prices on
different routes, or to change a price later, use the
[dashboard](https://docs.lightningenable.com/products/agentic-commerce/proxy-setup-walkthrough):
the **Pricing** tab's **Default Fallback Price**, and the **Sync** chip on a
route whose price you edit.

## Plan caps

The Free Producer Sandbox allows 1 proxy, 3 distinct resource paths for the
life of the account, 200 challenges a month, and 1,000 sats at most per
challenge. A paid Agentic Commerce plan lifts them; see
[lightningenable.com](https://www.lightningenable.com) for plans.

## Safety

- One explicit yes before the self-test payment, with the price stated.
- The budget is tightened before the payment, never after.
- Keys, connection strings, macaroons, and preimages are never echoed; the
  agent reports `<set>` or `<not set>`.
- One L402 payment at a time.
- Everything in the manifest is public, so nothing private goes in a path or a
  description.

## Optional: list on Amazap

After the self-test, the agent can offer one more step: a draft listing on
[Amazap](https://amazap.com/sell), a storefront where agents find and buy L402
endpoints. It first checks whether Amazap already carries the proxy (imported
from 402 Index) and asks whether you want a listing before it spends anything
on a paid check. It offers the listing as ready only after
[`l402-compatibility-report`](../l402-compatibility-report/) shows that paid
delivery worked, then drafts the copy and stops. Because a proxy lives on
`api.lightningenable.com`, you fill in the title, description, category, and
example parameters yourself. You review the draft, the current Amazap seller
terms, and the two prices (yours and Amazap's all-in price), enter your
contact email, and submit it yourself; submitting publishes the listing once
Amazap's checks pass. After any price change in the dashboard, re-run Amazap's
checks. The agent never calls the proxy listed until it has read the listing
back from Amazap. Lightning Enable does not hold funds; the payment provider
facilitates custody and settlement. Details:
[Amazap marketplace: Seller handoff](https://github.com/refined-element/lightning-enable-skills/blob/main/references/amazap-marketplace.md#seller-handoff).

## Other ways to do this

- Prefer clicking? The dashboard
  [proxy setup walkthrough](https://docs.lightningenable.com/products/agentic-commerce/proxy-setup-walkthrough)
  covers the same steps.
- Need the API to keep its own domain and its own auth?
  [`l402-server-integration`](../l402-server-integration/) checks L402 inside
  the API's code instead of in front of it.
- Selling a single file or answer rather than an API?
  [`sell-this`](../sell-this/).

## What it doesn't do

It doesn't create an account, fund a wallet, or bring buyers. It gets an API
charging per call; finding buyers is still your job.
