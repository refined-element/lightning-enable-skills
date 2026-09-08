---
name: producer-setup
description: >-
  Take an agent from nothing installed to a live, monetized L402 API endpoint
  that receives sats in its own Lightning wallet: connect the wallet, buy a
  Lightning Enable account with a ~100-sat L402 Fast Lane payment, wire the
  receive wallet, publish a priced endpoint in front of an upstream API, and
  prove it with a self-test purchase. Use when the user wants to START SELLING
  over Lightning and has no account, API key, or wallet wired up yet ("set me up
  to sell an API", "monetize this API over Lightning", "onboard me as an L402
  producer", "get me a paid endpoint"). Do NOT use for a one-off paywall when an
  account already exists (use sell-this), or to BUY someone else's L402 resource
  (use pay-l402-anywhere). The human supplies a funded NIP-47 wallet, a spend
  ceiling, the upstream API, and the price.
---

# Producer setup

The whole path, in one skill: nothing installed → a published, priced API
endpoint that earns sats into a wallet the agent already controls. No dashboard,
no card, no merchant account, no human in the payment plumbing — the only human
decisions are the wallet, the ceiling, the API, and the price.

Money moves wallet to wallet. **Lightning Enable does not hold funds; the wallet
facilitates custody and settlement.** Lightning Enable mints the challenge,
verifies the proof, and proxies the call.

## What is automated, and what is not

**Automated:** wallet connection, budget tightening, account creation (paid over
L402), receive-wallet wiring, proxy creation, endpoint pricing, publishing, the
self-test purchase, and the hand-off summary.

**Not automated — the human must supply these:**

- **A Lightning wallet that already exists and holds sats**, reachable over
  [NWC](https://nwc.dev) (Alby Hub, CoinOS, CLINK, or another NIP-47 wallet), or
  permission to use the wallet the MCP is already configured with. This skill
  does not create or fund a wallet.
- **A spend ceiling** for setup: about 100 sats for signup, plus the price of one
  self-test call.
- **The upstream API to sell, and the price per call.**

## What you need

- **[Lightning Enable MCP](https://github.com/refined-element/lightning-enable-mcp)**
  installed and running.
- A wallet that returns Lightning **preimages**: NWC, LND, or Strike. OpenNode
  does not return preimages and cannot pay L402 challenges.
- Tools this skill uses:
  - `setup_wallet` — reports the configured wallet, or connects one over NWC.
  - `get_balance` — the real funds.
  - `budget` — `action="status"` to read limits, `action="tighten"` to lower them.
  - `create_lightning_enable_account` — pays the ~100-sat L402 Fast Lane
    challenge and stores the merchant API key.
  - `l402_producer` — the producer verb, with actions `configure_receive`,
    `status`, `create_proxy`, `add_endpoint`, `publish`, `list_challenges`,
    `create`, and `verify`.
  - `access_l402_resource` / `pay_l402_challenge` — the self-test purchase.
  - `receipts` — the durable payment log, for the hand-off.

## Flow

### 0. Preconditions and human checkpoints

Before spending anything, get three explicit answers. Ask for all three in one
message, then **stop and wait** — steps 1 and 2 both move money.

1. **Wallet.** "Do you have a funded Lightning wallet I can reach over NWC, or
   may I use the wallet this MCP is already connected to?" If they paste an NWC
   connection string, treat it as a secret: never echo it back, never write it
   into a summary.
2. **Ceiling.** "What is the most I may spend to get you set up?" About 100 sats
   covers signup; add the price of one self-test call. Anything over roughly 200
   sats is generous.
3. **What to sell.** "Which API should I put behind the paywall, and what should
   one call cost?" You need a publicly reachable base URL, one path to price, and
   a price in sats.

Say plainly what happens next: the agent spends about 100 sats of the user's
money to create an account, and the account starts a 30-day trial with no card.

### 1. Install the MCP, connect the wallet, set the leash

If the MCP is not installed, point the human at the
[quick start](https://github.com/refined-element/lightning-enable-mcp#quick-start)
and give them the one-liner for their platform:

```
dotnet tool install -g LightningEnable.Mcp              # .NET (NuGet)
pip install lightning-enable-mcp                        # Python (PyPI)
docker pull refinedelement/lightning-enable-mcp:latest  # Docker
```

Then report the wallet. Call `setup_wallet` **with no arguments first**:

```
setup_wallet()
```

- **Success:** the wallet is configured. It reports the provider and where the
  configuration came from.
- **No wallet yet:** the same call returns the setup steps. Ask the human for an
  NWC connection string, then connect it:
  `setup_wallet(nwcConnectionString="nostr+walletconnect://…")`. It validates the
  string and probes the wallet before writing anything.
- **It refuses to write the config:** an environment variable already selects a
  wallet, and a config file would be ignored. The tool names the variable — ask
  the human to unset it and try again.
- **The probe fails or times out:** the relay is unreachable or the secret is
  wrong. Try another NIP-47 wallet (see the table below).

Confirm the funds and set the leash:

```
get_balance()
budget(action="tighten", perRequest=<ceiling>, perSession=<ceiling>)
```

`budget action="tighten"` only lowers the caps — it can never raise them above
the operator's own limits in `~/.lightning-enable/config.json`. State the result
back in plain terms: "you have about 5,000 sats; I am capped at 200 for this
setup."

**Stop here if the balance is below the ceiling.** A wallet that cannot pay the
signup challenge fails at step 2 with a less obvious error.

### 2. Create the Lightning Enable account (~100 sats over L402)

This is the Fast Lane on-ramp: pay a 100-sat L402 challenge, get an account with
a 30-day trial. No card, no checkout page.

```
create_lightning_enable_account(email="<the user's email>", maxSats=<ceiling>)
```

- **Success:** it returns the merchant API key and writes it to
  `~/.lightning-enable/config.json`. Do not print the key. Say "stored" instead.
- **Confirmation gate:** if the payment is over the auto-approve threshold, the
  MCP prints a confirmation code to its **console**, where the human can read it
  and you cannot. Ask the **human** for the code, then re-call the same tool with
  `confirmationNonce="<code>"`. Never guess a code.
- **Restart:** the API-key-gated tools (`l402_producer`, `agent_services`) load
  their key at startup. Tell the human to restart the MCP — in Claude Code or
  Claude Desktop, that means restarting the app.

After the restart, confirm the key is live:

```
l402_producer(action="status")
```

- **Success:** it reports the merchant, the plan, and the trial end date.
- **401 or "API key required":** the restart has not happened yet. Ask again;
  do not retry the signup, which would pay a second time.

### 3. Point the receive wallet at the agent's own wallet

Payments for the new endpoint have to land somewhere. Set the merchant's receive
wallet to the same NWC wallet the MCP pays from:

```
l402_producer(action="configure_receive")
```

With no wallet argument it defaults to the MCP's own NWC wallet, and sets the
merchant's payment provider to `nwc`.

- **Success:** the response shows the provider as `nwc` and the receive wallet as
  set. Report it as `<set>` — never print the connection string.
- **Failure:** stop and fix it here. Without a receive wallet, every challenge
  mint in step 5 fails, because there is no wallet to issue the invoice.

### 4. Create the proxy, price an endpoint, publish

```
l402_producer(action="create_proxy", name="<short name>",
              targetBaseUrl="https://<upstream>", defaultPriceSats=<price>)
```

- **Success:** returns a proxy ID. Keep it; the next two calls need it.
- **400 with an SSRF or private-address error:** the upstream resolves to
  localhost or a private IP. Lightning Enable refuses to proxy it — that block is
  deliberate, not a bug. Ask for a publicly reachable URL or a tunnel.
- **402 `plan_proxy_limit`:** the plan caps concurrent proxies (the Free Producer
  Sandbox allows 1). Reuse the existing proxy or add billing.

Price one path:

```
l402_producer(action="add_endpoint", proxyId="<id>", pathPattern="/v1/<path>",
              priceSats=<price>, description="<what one call buys>")
```

Start with **one** priced path. More paths are one call each, and step 6 tells
the human how to add them.

- **402 `plan_price_limit`:** the price is above the plan's per-challenge cap.
  Lower it, or add billing.
- **402 `plan_endpoint_limit`:** the account is at its endpoint cap. On the Free
  Producer Sandbox that is 3 distinct resource paths, counted for the life of the
  account.

Publish it:

```
l402_producer(action="publish", proxyId="<id>")
```

- **Success:** returns the OpenAPI URL and the manifest URL. **Capture both** —
  the OpenAPI URL is what the human hands to buyers, and the manifest is what
  agents and the L402 registry read.

### 5. Self-test: buy your own endpoint

Read the OpenAPI document first, unpaid:

```
access_l402_resource(url="<OpenAPI URL>")
```

It should return 200 with no payment, and list the priced path. Descriptions are
public — check that nothing sensitive leaked into the path or description.

Now buy one call:

```
access_l402_resource(url="<proxy base>/v1/<path>", maxSats=<price + a few>)
```

- **Success:** 402 → the MCP pays the invoice → preimage → retry with
  `Authorization: L402 <macaroon>:<preimage>` → 200 with the upstream's response.
  The endpoint is live and it charges.
- **The wallet refuses the payment:** some wallets reject paying an invoice they
  issued themselves, which is exactly what a same-wallet self-test asks them to
  do. This is a wallet policy, not a broken endpoint. Ask the human to pay from a
  second wallet, or skip the purchase and verify the mint instead — the 402 you
  already received proves the challenge mints.
- **500 on the mint:** the receive wallet is not configured. Go back to step 3.
- **403 `l402_not_enabled`:** the plan or trial state does not allow L402. Check
  `l402_producer(action="status")`.

If you already hold the challenge — because you captured the 402 rather than
letting the MCP follow it — pay it with
`pay_l402_challenge(invoice="<bolt11>", macaroon="<macaroon>", maxSats=<cap>)`
instead.

Run one payment at a time. Each 402 mints a fresh invoice and macaroon; parallel
attempts cross invoices and fail.

Confirm the sale landed:

```
l402_producer(action="list_challenges")
```

The paid challenge appears with its resource, price, and payment hash. A minted
challenge is not a paid one — look for the paid state, not just the row.

### 6. Hand off

Tell the human, in this order:

- **What to share:** the OpenAPI URL and the manifest URL. Published endpoints
  also appear in the L402 registry, where other agents discover them with
  `discover_api`.
- **What to watch:** `l402_producer(action="list_challenges")` for sales, and
  `receipts(action="durable")` for the wallet's own payment log.
- **How to add an endpoint:** one `l402_producer(action="add_endpoint", …)` call
  per path, on the same proxy.
- **How to change a price:** re-run `add_endpoint` for that path with the new
  `priceSats`. Existing unpaid challenges keep the price they were minted at.
- **What the trial means:** the Fast Lane account runs a **30-day trial with no
  card**. Reminder emails arrive 7 days and 1 day before it ends. Add billing and
  the account stays on the paid plan; do nothing and it drops to the **Free
  Producer Sandbox** — a smaller free tier, not a shutdown, with a cap on
  endpoints, monthly challenges, and price per challenge. Endpoints already
  published keep serving within those caps.

State this as fact, not as a sales pitch, and do not quote plan prices from
memory — point at [lightningenable.com](https://www.lightningenable.com) instead.

## What can go wrong

| Symptom | Likely cause | Do this |
|---|---|---|
| `setup_wallet` probe fails or times out | Relay unreachable, or a bad NWC secret | Try another NIP-47 wallet — Alby Hub, CoinOS, or CLINK. Primal's NWC does not return preimages and cannot do L402. |
| `setup_wallet` refuses to write the config | An environment variable already selects a wallet, so the file would be ignored | Ask the human to unset the variable the tool names, then reconnect. |
| `l402_producer` missing or 401 after signup | The MCP has not restarted, so the new API key is not loaded | Restart the MCP, then re-run `l402_producer(action="status")`. Do not re-run signup — that pays twice. |
| 500 when a challenge mints | The merchant has no receive wallet | Re-run `l402_producer(action="configure_receive")`, then `action="status"`. |
| 403 `l402_not_enabled` | Trial ended, plan does not include L402, or the account is inactive | Check `l402_producer(action="status")` for the plan and trial end. Adding billing restores the paid plan. |
| 400 on `create_proxy`, private address | The upstream resolves to localhost or a private IP | Deliberate SSRF block. Give a publicly reachable URL, or tunnel the upstream first. |
| 402 `plan_proxy_limit` / `plan_endpoint_limit` / `plan_price_limit` / `plan_volume_limit` | A plan cap: proxies, distinct endpoint paths, price per challenge, or monthly challenge volume | Reuse an existing proxy or path, lower the price, or add billing. Do not work around a cap. |
| The self-test payment is refused | The wallet will not pay its own invoice | Pay from a second wallet, or skip the purchase — the 402 already proves the mint. |
| A payment needs a confirmation code | The amount is over the auto-approve threshold | Ask the human to read the code from the MCP's console, then re-call with `confirmationNonce`. |

## Safety rules

- **Get an explicit yes before spending.** State the total up front: about 100
  sats for signup, plus one self-test call.
- **Tighten the budget before you spend**, not after.
- **Never echo secrets.** The NWC connection string, the merchant API key,
  macaroons, and preimages never appear in your output. Report `<set>` or
  `<not set>`.
- **One L402 payment at a time.** Finish a full 402 → pay → access cycle before
  starting another.
- **Never re-run signup to fix a missing tool.** A second run pays a second time.
  Missing gated tools nearly always mean the MCP has not restarted.
- **The price is the human's call**, and so is the upstream. Do not publish an API
  whose terms forbid resale, and do not proxy an upstream that needs the human's
  private credentials without saying so.
- **Nothing sensitive in public fields.** Path patterns, descriptions, and the
  manifest are public.

## What this is NOT

- **Not a per-transaction fee.** Lightning Enable charges a flat subscription and
  never takes a cut of the sats. Every satoshi a buyer pays settles to the
  wallet you configured.
- **Not custody.** Lightning Enable does not hold funds; the wallet facilitates
  custody and settlement. No private keys leave the wallet, and none reach
  Lightning Enable.
- **Not demand.** Publishing an endpoint creates a way to get paid, not buyers.
  Do not promise revenue.
- **Not investment advice**, and not a way around an upstream API's terms.

## Example

> User: "Set me up to sell my weather API over Lightning — 10 sats a call, budget
> 200 sats for setup."
>
> 1. Ask for the wallet, the ceiling, and the base URL. The human approves the
>    MCP's existing CoinOS wallet and gives `https://api.example-weather.dev`.
> 2. `setup_wallet()` → connected. `get_balance()` → 4,800 sats.
>    `budget(action="tighten", perRequest=200, perSession=200)`.
> 3. `create_lightning_enable_account(email="…", maxSats=200)` → paid 100 sats,
>    key stored. "Restart the MCP, then I will keep going."
> 4. `l402_producer(action="status")` → Individual trial, 30 days left.
> 5. `l402_producer(action="configure_receive")` → provider `nwc`, wallet `<set>`.
> 6. `create_proxy` → `add_endpoint(pathPattern="/v1/forecast", priceSats=10)` →
>    `publish` → OpenAPI + manifest URLs.
> 7. `access_l402_resource` on the endpoint → 402 → paid 10 sats → 200 forecast.
>    `list_challenges` shows it paid.
> 8. Hand off: "Live and charging 10 sats a call. Share the OpenAPI URL. Spent
>    110 sats. Trial ends in 30 days; without billing it drops to the Free
>    Producer Sandbox."
