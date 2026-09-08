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
  - `l402_producer` — the whole seller side behind one verb, with actions
    `configure_receive`, `status`, `create_proxy`, `add_endpoint`, `publish`,
    `list_challenges`, `create`, and `verify`. Pass only the arguments tagged
    for your action.
  - `access_l402_resource` / `pay_l402_challenge` — the self-test purchase.
  - `receipts` — the durable payment log, for the hand-off.

Argument names below are the Python server's `snake_case`. The .NET server takes
the same arguments in `camelCase` — `target_base_url` → `targetBaseUrl`,
`challenge_status` → `challengeStatus`. Nothing else differs.

Two actions need a newer Lightning Enable API than the one deployed in
production: `configure_receive` (the NWC receiving lane) and `list_challenges`
(the challenge-listing route). Run `l402_producer(action="status")` first — it
degrades gracefully and reports what the deployment you are pointed at supports.

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
  `setup_wallet(nwc_connection_string="nostr+walletconnect://…")`. It validates
  the string and probes the wallet before writing anything.
- **It refuses to write the config:** an environment variable already selects a
  wallet, and a config file would be ignored. The tool names the variable — ask
  the human to unset it and try again.
- **The probe fails or times out:** the relay is unreachable or the secret is
  wrong. Try another NIP-47 wallet (see the table below).

Confirm the funds and set the leash:

```
get_balance()
budget(action="tighten", per_request=<ceiling>, per_session=<ceiling>)
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
create_lightning_enable_account(email="<the user's email>", max_sats=<ceiling>)
```

- **Success:** it returns the merchant API key and writes it to
  `~/.lightning-enable/config.json`. Do not print the key. Say "stored" instead.
- **Confirmation gate:** if the payment is over the auto-approve threshold, the
  MCP prints a confirmation code to its **console**, where the human can read it
  and you cannot. Ask the **human** for the code, then re-call the same tool with
  `confirmation_nonce="<code>"`. Never guess a code.
- **Restart:** the API-key-gated tools (`l402_producer`, `agent_services`) load
  their key at startup. Tell the human to restart the MCP — in Claude Code or
  Claude Desktop, that means restarting the app.

After the restart, confirm the key is live:

```
l402_producer(action="status")
```

- **Success:** it reports the merchant (plan tier, subscription status,
  `l402Enabled`), the receiving wallet (`provider`, `configured`,
  `nwcConnectionString: "<set>"` or `"<unset>"`), the proxy count, the onboarding
  checklist, and the most recent challenges. Read it as the source of truth for
  every later step — `status` is read-only and spends nothing.
- **"API key required":** the restart has not happened yet, so the tool has no
  key. Ask the human to restart. Do **not** retry the signup — that pays a
  second time.
- **`checklistError` or `challengesError` set:** the rest of the report is still
  good. A `challengesError` here usually means the deployment predates the
  challenge-listing route, which also rules out `list_challenges` in step 5.

`status` takes an optional `limit` (1-50) for how many recent challenges to
include.

### 3. Point the receive wallet at the agent's own wallet

Payments for the new endpoint have to land somewhere. Set the merchant's receive
wallet to the same NWC wallet the MCP pays from:

```
l402_producer(action="configure_receive")
```

With no argument it reuses the NWC wallet this MCP already pays with: it stores
the connection string on the merchant, then switches the account's payment
provider to `nwc`.

- **Success:** the response reads `provider: "nwc"`,
  `nwcConnectionString: "<set>"`, and `usedMcpWallet: true`. Report it that way —
  the string itself is never returned, and you must never print it.
- **The MCP's wallet is not NWC:** an LND, Strike, or OpenNode credential is not
  a connection string, so the tool refuses and names the wallet it found. Ask the
  human for an NWC string from a wallet app that has one (CoinOS, Alby Hub, or
  CLINK), then pass it:
  `l402_producer(action="configure_receive", nwc_connection_string="nostr+walletconnect://…")`.
- **Stored but not switched:** if the provider switch fails after the string is
  saved, the response says so and asks you to retry the same action. Retrying is
  safe.
- **Any other failure:** stop and fix it here. Without a receiving wallet, every
  challenge mint in step 5 fails, because there is no wallet to issue the
  invoice.

Lightning Enable mints invoices on that wallet and polls it for payment — no
webhook to configure, and it never holds the funds.

### 4. Create the proxy, price an endpoint, publish

```
l402_producer(action="create_proxy", name="<service name>",
              target_base_url="https://<upstream>",
              description="<what the API does>", default_price_sats=<price>)
```

- **Success:** returns `proxyId` and `publicBaseUrl`. Keep both — the next two
  calls need the id, and every request under that base URL now answers 402 until
  it is paid.
- **400 with an SSRF or private-address error:** the upstream resolves to
  localhost or a private IP. Lightning Enable refuses to proxy it — that block is
  deliberate, not a bug. Ask for a publicly reachable URL or a tunnel.
- **402 `plan_proxy_limit`:** the plan caps concurrent proxies (the Free Producer
  Sandbox allows 1). Reuse the existing proxy or add billing.

Price one route. `endpoint_id` is a short stable id, unique on the proxy; `path`
is the route on the upstream:

```
l402_producer(action="add_endpoint", proxy_id="<id>", endpoint_id="forecast",
              path="/forecast", http_method="GET", price_sats=<price>,
              summary="<what one call buys>")
```

- **Success:** returns the endpoint plus the absolute `url` a paying agent calls.
  Keep that URL for the self-test.
- **402 `plan_price_limit`:** the price is above the plan's per-challenge cap.
  Lower it, or add billing.
- **402 `plan_endpoint_limit`:** the account is at its endpoint cap. On the Free
  Producer Sandbox that is 3 distinct resource paths, counted for the life of the
  account.

Start with **one** priced route. More routes are one call each, and step 6 tells
the human how to add them.

Publish it:

```
l402_producer(action="publish", proxy_id="<id>",
              service_description="<one line for the registry>",
              categories=["<category>"])
```

`service_name` renames the listed service if you need a different name from the
proxy's.

- **Success:** returns `openapiUrl`
  (`/l402/proxy/{proxyId}/openapi.json` — OpenAPI 3.1, with an `x-payment`
  extension carrying the price and challenge shape on every operation) and
  `manifestUrl`
  (`/l402/proxy/{proxyId}/.well-known/l402-manifest.json`). **Capture both.** The
  OpenAPI document is what a buyer's own tooling reads; the manifest is what
  agents and the L402 registry read.
- **Rename failed:** nothing is published and nothing is changed. Fix the name
  and call again.

For a resource you are not proxying — a file, a report, a one-off answer — skip
the proxy entirely and use `l402_producer(action="create", …)` to mint a single
challenge and `l402_producer(action="verify", …)` to check the payer's token.
That flow is the [`sell-this`](../sell-this/) skill.

### 5. Self-test: buy your own endpoint

Read the OpenAPI document first, unpaid:

```
access_l402_resource(url="<OpenAPI URL>")
```

It should return 200 with no payment, and price the route under `x-payment`. The
document is public — check that nothing sensitive leaked into the path, the
summary, or the service description.

Now buy one call, at the `url` that `add_endpoint` returned:

```
access_l402_resource(url="<endpoint url>", max_sats=<price + a few>)
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
`pay_l402_challenge(invoice="<bolt11>", macaroon="<macaroon>", max_sats=<cap>)`
instead.

Run one payment at a time. Each 402 mints a fresh invoice and macaroon; parallel
attempts cross invoices and fail.

Confirm the sale landed. The filter argument is `challenge_status`, not `status`
— `status` is already an action:

```
l402_producer(action="list_challenges", challenge_status="paid")
```

The paid challenge comes back with its resource, `amountSats`, `paidAt`, and
payment hash — never a macaroon or a preimage. A minted challenge is not a paid
one, so filter on `paid` rather than reading the first row you see. `limit` and
`offset` page the list.

If this action reports that the route is unavailable, the deployment predates the
challenge-listing route. Fall back to `l402_producer(action="status")`, which
carries the recent challenges too.

### 6. Hand off

Tell the human, in this order:

- **What to share:** the OpenAPI URL and the manifest URL. Published endpoints
  also appear in the L402 registry, where other agents discover them with
  `discover_api`.
- **What to watch:** `l402_producer(action="list_challenges", challenge_status="paid")`
  for sales, `l402_producer(action="status")` for the account, and
  `receipts(action="durable")` for the wallet's own payment log.
- **How to add an endpoint:** one `l402_producer(action="add_endpoint", …)` call
  per route on the same proxy, each with its own `endpoint_id`.
- **How to change a price:** re-run `add_endpoint` for that `endpoint_id` with
  the new `price_sats`. Challenges already minted keep the price they carry.
- **What the trial means:** the Fast Lane account runs a **30-day trial with no
  card**. Reminder emails arrive 7 days and 1 day before it ends. Add billing and
  the account stays on the paid plan; do nothing and it drops to the **Free
  Producer Sandbox** — a smaller free tier, not a shutdown, with a cap on
  endpoints, monthly challenges, and price per challenge. Endpoints already
  published keep serving within those caps.

State this as fact, not as a sales pitch, and do not quote plan prices from
memory — point at [lightningenable.com](https://www.lightningenable.com) instead.

## What can go wrong

### How a producer error arrives

A failed `l402_producer` action returns `success: false` with the API's own
words: `error` (a stable slug or the prose), `message` / `detail` (what happened
this time), `errorType` (the RFC 9457 `type` URI, such as
`https://lightningenable.com/problems/l402_not_enabled`), `httpStatus`, and
`validationErrors` when a field failed validation. **Read the slug, then repeat
the message to the human.** Never invent a cause the body does not give you, and
never retry a call that failed on a cap.

| Symptom | Likely cause | Do this |
|---|---|---|
| `setup_wallet` probe fails or times out | Relay unreachable, or a bad NWC secret | Try another NIP-47 wallet — Alby Hub, CoinOS, or CLINK. Primal's NWC does not return preimages and cannot do L402. |
| `setup_wallet` refuses to write the config | An environment variable already selects a wallet, so the file would be ignored | Ask the human to unset the variable the tool names, then reconnect. |
| `l402_producer` missing, or it answers "API key required" | The MCP has not restarted, so the new API key is not loaded | Restart the MCP, then re-run `l402_producer(action="status")`. Do not re-run signup — that pays twice. |
| `configure_receive` refuses with a wallet name | The MCP's own wallet is LND, Strike, or OpenNode, which is not a connection string | Get an NWC string from CoinOS, Alby Hub, or CLINK and pass `nwc_connection_string`. |
| `configure_receive` or `list_challenges` reports the route is unavailable | The deployment predates the NWC receiving lane and the challenge-listing route | Check `l402_producer(action="status")` for what the deployment supports; `status` also carries recent challenges. |
| 500 when a challenge mints, or `challenge_persist_failed` | No receiving wallet, or the mint could not be recorded | Re-run `l402_producer(action="configure_receive")`, then `action="status"`. A challenge that cannot be recorded is refused rather than served unrecorded. |
| 403 `l402_not_enabled` | Trial ended, the plan does not include L402, or the account is inactive | Check `l402_producer(action="status")` for the plan and subscription status. Adding billing restores the paid plan. |
| 409 `idempotency_key_reuse` | The same idempotency key came back with different challenge parameters | Do not retry with the same key. Change the resource or price, or let a fresh call mint a new challenge. |
| 400 on `create_proxy`, private address | The upstream resolves to localhost or a private IP | Deliberate SSRF block. Give a publicly reachable URL, or tunnel the upstream first. |
| 402 `plan_proxy_limit` / `plan_endpoint_limit` / `plan_price_limit` / `plan_volume_limit` | A plan cap: proxies, distinct endpoint paths, price per challenge, or monthly challenge volume | Reuse an existing proxy or route, lower the price, or add billing. Do not work around a cap. |
| `endpoint_retired` | An operator soft-retired that resource path | Use a different path, or ask an operator to clear the retirement. |
| `validationErrors` on a create call | A field failed validation — often a bad URL or a name that is too long | Fix the named field and call again. The body says which one. |
| The self-test payment is refused | The wallet will not pay its own invoice | Pay from a second wallet, or skip the purchase — the 402 already proves the mint. |
| A payment needs a confirmation code | The amount is over the auto-approve threshold | Ask the human to read the code from the MCP's console, then re-call with `confirmation_nonce`. |

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
>    `budget(action="tighten", per_request=200, per_session=200)`.
> 3. `create_lightning_enable_account(email="…", max_sats=200)` → paid 100 sats,
>    key stored. "Restart the MCP, then I will keep going."
> 4. `l402_producer(action="status")` → Individual trial, receive `<unset>`.
> 5. `l402_producer(action="configure_receive")` → provider `nwc`, wallet `<set>`.
> 6. `l402_producer(action="create_proxy", name="Weather API",
>    target_base_url="https://api.example-weather.dev", default_price_sats=10)` →
>    `l402_producer(action="add_endpoint", proxy_id="weather-api",
>    endpoint_id="forecast", path="/forecast", price_sats=10)` →
>    `l402_producer(action="publish", proxy_id="weather-api")` → OpenAPI +
>    manifest URLs.
> 7. `access_l402_resource` on the endpoint URL → 402 → paid 10 sats → 200
>    forecast. `l402_producer(action="list_challenges", challenge_status="paid")`
>    shows the sale.
> 8. Hand off: "Live and charging 10 sats a call. Share the OpenAPI URL. Spent
>    110 sats. Trial ends in 30 days; without billing it drops to the Free
>    Producer Sandbox."
