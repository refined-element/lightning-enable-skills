---
name: create-l402-proxy
description: >-
  Put an existing, publicly reachable HTTP API behind a paid L402 proxy on a
  Lightning Enable account that already exists: check the account and receive
  wallet, create the proxy, price each route, publish it to the L402 registry,
  prove it charges with one self-test purchase, and watch the sales. Use when
  the user already has a Lightning Enable API key and says "create a proxy",
  "wrap my API with L402", "charge per call for this API", "add a paid route",
  "publish my endpoint to the registry", or "change the price of my endpoint".
  Do NOT use when there is no account or API key yet (use producer-setup), to
  charge once for a single file or answer (use sell-this), to add L402 inside
  the API's own code so it keeps its own domain and auth (use
  l402-server-integration), or to buy someone else's endpoint (use
  pay-l402-anywhere).
---

# Create an L402 proxy

Turn an API the human already runs into a pay-per-call service. Lightning
Enable stands in front of the API at a public proxy URL. Every call to that URL
answers HTTP 402 Payment Required with a Lightning invoice and a macaroon until
the caller pays. A caller that pays and presents the proof gets the upstream
response. This is the L402 protocol: HTTP 402 plus a Lightning payment as the
credential.

**Lightning Enable does not hold funds; the wallet (or the payment provider)
facilitates custody and settlement.** Lightning Enable mints the challenge,
verifies the proof, and forwards the paid call. It never takes a percentage of
the sats.

This skill starts from an account that exists. If the human has no Lightning
Enable account or API key, stop and use [`producer-setup`](../producer-setup/)
instead: it creates the account and then runs these same steps.

## When to use something else

| The human wants to | Use |
|---|---|
| Start from nothing: no account, no API key | [`producer-setup`](../producer-setup/) |
| Charge once for one file, report, or answer | [`sell-this`](../sell-this/) |
| Keep the API on its own domain and its own auth, with L402 checked inside the API's code | [`l402-server-integration`](../l402-server-integration/) |
| Click through a form instead of letting the agent drive | The dashboard [proxy setup walkthrough](https://docs.lightningenable.com/products/agentic-commerce/proxy-setup-walkthrough) |
| Buy someone else's L402 endpoint | [`pay-l402-anywhere`](../pay-l402-anywhere/) |

## What you need

- **[Lightning Enable MCP](https://github.com/refined-element/lightning-enable-mcp)**
  (Model Context Protocol server) with the merchant API key loaded, from
  `LIGHTNING_ENABLE_API_KEY` or `~/.lightning-enable/config.json`.
- **A receive wallet on the account**: Strike, OpenNode, or a Nostr Wallet
  Connect (NWC) wallet. Without one, no challenge can mint, because there is no
  wallet to issue the invoice.
- **The upstream API**: a public base URL with a domain name, not an IP
  address, on port 80 or 443. Lightning Enable refuses localhost, internal host
  names, addresses that resolve to a private network, and other ports.
- **The routes to sell and the price per call, in sats**, from the human.
- **For the self-test**: a wallet that returns Lightning preimages (NWC, LND, or
  Strike) with enough sats for one call.

Tools this skill uses:

- `l402_producer`, which holds the whole seller side behind one tool. Actions
  used here: `status`, `configure_receive`, `create_proxy`, `add_endpoint`,
  `publish`, and `list_challenges`. Pass only the arguments tagged for your
  action.
- `access_l402_resource` and `pay_l402_challenge` for the self-test purchase.
- `budget` to tighten the spend caps before the self-test.

Argument names below are the Python server's `snake_case`. The .NET server
takes the same arguments in `camelCase`: `target_base_url` is `targetBaseUrl`,
`default_price_sats` is `defaultPriceSats`, `proxy_id` is `proxyId`,
`endpoint_id` is `endpointId`, `http_method` is `httpMethod`, `price_sats` is
`priceSats`, `service_description` is `serviceDescription`, and
`challenge_status` is `challengeStatus`. Response fields are `camelCase` in
both.

## How the proxy decides what to charge

Read this before you set any price. Two numbers exist, and only one of them is
the charge:

- **`default_price_sats` on `create_proxy` is what the proxy charges** for every
  path under it that has no pricing rule of its own. The MCP has no action that
  writes a per-route pricing rule, so on a proxy created by this skill,
  `default_price_sats` is the price of every call.
- **`price_sats` on `add_endpoint` is what the route advertises**: it goes into
  the public manifest and the OpenAPI document. It does not change what the
  proxy charges.

So, from the MCP: **charge one price per proxy, and pass that same number as
`price_sats` on every `add_endpoint` call**, so what buyers read matches what
they pay. If the human wants different prices on different routes, or wants to
change a price later, that happens in the dashboard (see step 7).

## Flow

### 0. Preconditions

Read the account first. `status` is read-only and spends nothing:

```
l402_producer(action="status")
```

Check four things in the result:

1. **The key works.** "API key required" means the MCP has no key loaded. If the
   human has one, they set `LIGHTNING_ENABLE_API_KEY` or add it to
   `~/.lightning-enable/config.json`, then restart the MCP. If they have none,
   switch to [`producer-setup`](../producer-setup/).
2. **L402 is on.** `merchant.l402Enabled` and `merchant.isActive` are both
   `true`. Otherwise stop; see 403 `l402_not_enabled` under "What can go wrong".
3. **A receive wallet is set.** `receive.configured` is `true`. Report the
   wallet as `receive.provider` plus `<set>` or `<not set>`; never print a key or
   a connection string. If nothing is configured, wire the MCP's own NWC wallet:

   ```
   l402_producer(action="configure_receive")
   ```

   With no argument, it reuses the NWC wallet this MCP pays from and switches the
   account's provider to `nwc`. Success reads `provider: "nwc"`,
   `nwcConnectionString: "<set>"`, and `usedMcpWallet: true`. If the MCP's
   wallet is LND, Strike, or OpenNode, the tool refuses and names it, because
   none of those is a connection string. Ask the human for an NWC string from
   CoinOS, Alby Hub, or CLINK and pass it once, without echoing it:
   `l402_producer(action="configure_receive", nwc_connection_string="nostr+walletconnect://…")`.
   If the result says the string was stored but the provider switch failed,
   retry the same call; retrying is safe.
4. **Proxy room on the plan.** `proxies.count` is how many proxies the account
   has. The Free Producer Sandbox allows 1 proxy, and a proxy that was taken
   down still counts. If the account is at its cap, reuse the existing proxy
   (go to step 2 with its id, which the human can read on the dashboard's
   Proxies page) or add billing.

Then get the human's answers in one message and **stop and wait**:

- The upstream base URL, and whether it needs its own credentials. The proxy
  forwards the caller's headers and strips the incoming `Authorization` header;
  it does not store or inject upstream credentials. An API that needs a key
  needs a small auth-adding front on the human's own infrastructure, and the
  proxy points at that front instead.
- The routes to sell (path and HTTP method), with a one-line summary each.
- The price per call in sats.
- A spend ceiling for the self-test: one call at that price.

### 1. Create the proxy

```
l402_producer(action="create_proxy", name="<service name>",
              target_base_url="https://<upstream>",
              description="<what the API does>",
              default_price_sats=<price per call>)
```

Always pass `default_price_sats`. Left out, it falls back to the server's
default, which is not the human's price.

- **Success:** returns `proxyId`, `proxyUrl`, and `publicBaseUrl`. Keep
  `proxyId`; every later call needs it. From this point every request under
  `publicBaseUrl` answers 402 until it is paid.
- **400, private address:** the upstream resolves to localhost or a private
  network. That block is deliberate server-side request forgery (SSRF)
  protection. Ask for a public URL, or a tunnel to the upstream.
- **402 `plan_proxy_limit`:** the plan's proxy cap. Reuse the existing proxy or
  add billing.

### 2. Price each route

One call per route. `endpoint_id` is a short id, stable and unique on the proxy;
`path` is the route on the upstream; `price_sats` is the same number as
`default_price_sats` (see "How the proxy decides what to charge"):

```
l402_producer(action="add_endpoint", proxy_id="<proxyId>",
              endpoint_id="forecast", path="/forecast", http_method="GET",
              price_sats=<price per call>,
              summary="<what one call returns>")
```

- **Success:** returns the endpoint and its absolute `url`, the address a paying
  agent calls. Keep the first `GET` route's `url` for the self-test.
- **400 "already exists":** that `endpoint_id`, or that method and path, is
  already on the proxy. An endpoint cannot be overwritten from the MCP; pick a
  different `endpoint_id`, or edit the existing one in the dashboard.
- **`validationErrors`:** a field failed validation. The body names it; fix it
  and call again.

A paid call keeps its path through the proxy: a request to
`publicBaseUrl + "/forecast"` reaches `target_base_url + "/forecast"`.

### 3. Publish

```
l402_producer(action="publish", proxy_id="<proxyId>",
              service_description="<one line for the registry>",
              categories=["<category>"])
```

`service_name` renames the listed service when it should differ from the
proxy's name.

- **Success:** returns `openapiUrl`, which is
  `/l402/proxy/{proxyId}/openapi.json` (an OpenAPI 3.1 document whose every
  operation carries an `x-payment` extension with the price and challenge
  shape), and `manifestUrl`, which is
  `/l402/proxy/{proxyId}/.well-known/l402-manifest.json` (the JSON manifest that
  agents and the L402 registry read). **Capture both.**
- **Rename failed:** nothing was published and nothing changed. Fix the name and
  call again.
- **422 `listing_verification_failed`:** the listing check found no price above
  0 on this proxy. Confirm `default_price_sats` and publish again.
- **402 `plan_feature_disabled`:** the plan does not include registry listing.
  Read the message to the human.

### 4. Self-test: buy one call

Read the OpenAPI document first. It is public and costs nothing:

```
access_l402_resource(url="<openapiUrl>", max_sats=1)
```

Pass `max_sats=1` even though the read is free: the budget gate checks
`max_sats` before it fetches anything, and the default is 1000.

Expect 200 with no payment and an `x-payment` price on each operation. Read it
the way a stranger would: nothing private belongs in a path, a summary, or the
description.

Then set the leash and buy one call. Get the human's explicit yes first, naming
the price:

```
budget(action="tighten", per_request=<price + a few>, per_session=<spent + price + a few>)
access_l402_resource(url="<endpoint url>", max_sats=<price + a few>)
```

`spent` is this session's spend so far, from `budget(action="status")`.
The session cap counts what this session already spent: the budget gate
denies a payment when spent plus `max_sats` exceeds the runtime session cap,
so a session cap equal to the ceiling alone would shrink the ceiling by
whatever was spent before.

- **Success:** 402, the MCP pays the invoice, gets the preimage, retries with
  `Authorization: L402 <macaroon>:<preimage>`, and returns 200 with the
  upstream's response. The amount paid should equal `default_price_sats`. If it
  differs from the advertised price, the route and the proxy disagree: fix that
  in the dashboard before sharing anything.
- **The wallet refuses to pay:** some wallets will not pay an invoice they
  issued themselves, which is what a self-test against the same wallet asks.
  That is wallet policy, not a broken endpoint. Pay from a second wallet, or
  stop at the 402: a 402 carrying an invoice already proves the challenge mints.
- **A confirmation code is needed:** the payment is over the auto-approve
  threshold. The MCP prints a code to its console, where the human can read it
  and you cannot. Ask the human for it and re-call with
  `confirmation_nonce="<code>"`. Never guess a code.
- **The route is `POST`, `PUT`, or `DELETE`:** `access_l402_resource` sends
  `GET` or `HEAD` only. Test a `GET` route, or stop at the 402.

If you captured the 402 yourself instead of letting the tool follow it, pay it
with `pay_l402_challenge(invoice="<bolt11>", macaroon="<macaroon>", max_sats=<cap>)`.

**One payment at a time.** Each 402 mints a fresh invoice and macaroon, so
parallel attempts cross invoices and fail. Finish one 402, pay, 200 cycle before
starting another.

### 5. See the sale

The filter is `challenge_status`, not `status` (`status` is an action):

```
l402_producer(action="list_challenges", challenge_status="paid")
```

The paid challenge comes back with its resource, `amountSats`, `paidAt`, and
payment hash, never a macaroon or a preimage. A minted challenge is not a paid
one, so read the `paid` filter rather than the first row you see. `limit` and
`offset` page the list. If the action reports that the route is unavailable,
read the recent challenges from `l402_producer(action="status")` instead.

### 6. Verify your endpoint

Check the route the way a buyer's agent meets it, with the Lightning Enable
L402 compatibility report,
[`l402-compatibility-report`](../l402-compatibility-report/). This step reads;
step 4's purchase is its paid evidence. If `l402-compatibility-report` is not
installed, paid delivery stays unverified and no classification is
available: say so, and give the human its GitHub URL,
https://github.com/refined-element/lightning-enable-skills/tree/main/skills/l402-compatibility-report.

- **Read-only check.** From that skill's folder, run it on the `url` of the
  route step 4 tested (from step 2), with that route's `http_method` from
  step 2 and the human's cap in sats: `python scripts/l402_check.py <url> --json --max-sats <cap> --output mode-a.json`
  (add `--method POST` for a `POST` route). Take the `classification` field
  from the JSON, never from the Markdown. `INCOMPATIBLE` comes with its fix:
  a private, loopback, link-local, or non-HTTPS URL, a `200` to an unpaid
  request, or a `400`, `415`, or `422` to a request with no body each has
  one. `CHALLENGE_COMPATIBLE` is the most the read-only check can return for
  a correct endpoint: say "challenge-compatible, fulfillment unverified", and
  do not report paid delivery as proven until the paid evidence below lifts
  it.
- **Pay once, never twice.** The paid check runs on `GET` or `HEAD` only, so
  a `POST`, `PUT`, or `DELETE` route stays at `CHALLENGE_COMPATIBLE`. Step 4
  buys the first `GET` route. If the self-test (step 4) made no payment for
  this endpoint by any means (a testnet invoice doesn't count), run that
  skill's paid check once, with the human's yes; otherwise the cases below
  apply and the agent never pays again. The paid check needs a wallet that
  can pay this endpoint: if step 4 stopped at the 402 because the wallet
  refused to pay its own invoice, do not attempt the paid check with the same
  wallet, and paid delivery stays unverified. If step 4 paid this exact URL
  with the same method through `access_l402_resource`, from either wallet,
  record that call as the evidence (steps 6 and 7 of
  `l402-compatibility-report`, with `--mode-a mode-a.json` and that call's
  token piped on stdin) instead of paying again. If that token is gone, paid
  delivery stays unverified; do not pay again. A self-test payment of a
  testnet invoice moved no real money for this endpoint, so it is neither
  reuse evidence nor the one paid check: once the endpoint quotes a mainnet
  invoice at the chosen price, run the paid check once, with the human's
  yes. A step 4 payment of this URL with a different method also counts as
  paid: paid delivery stays unverified; do not pay again. A payment through
  `pay_l402_challenge` (step 4's captured-402 path) counts as paid. The agent
  has no tool that fetches the resource with a token it already holds, and
  `access_l402_resource` would pay again, so in that run the result stays at
  `CHALLENGE_COMPATIBLE`, and the agent does not pay again. A self-test
  payment made by hand, outside both tools, also counts as paid: paid
  delivery stays unverified in that run, and the agent does not pay again.
  If the human wants the paid check later, they choose it in a later run, and
  the skill says plainly that it is a second payment for this endpoint.
  Without the token the paid check ends `INCONCLUSIVE`, so a paid check
  through the Python MCP server never proves paid delivery.
- **Report the result.** `FULFILLMENT_VERIFIED` means the request, the 402,
  the payment, the authorized retry, and the expected 2xx all worked, with
  the preimage matched to the payment hash. Pass on the report's
  `paid_fulfillment.hash_source`: for an opaque token the preimage was matched
  against the wallet's recorded payment, not the invoice. The report's
  optional Amazap profile matters only for step 8 and never changes this
  result.

### 7. Hand off

Tell the human, in this order:

- **What to share:** the OpenAPI URL and the manifest URL.
- **How buyers find and pay you:** `publish` listed the proxy in the
  Lightning Enable registry. A buyer's agent finds it with
  `discover_api(query="<words from the service description>")`, or reads the
  manifest URL directly with `discover_api(url="<manifest URL>")`, then pays
  each call from its own wallet over L402: `access_l402_resource`, the
  [`pay-l402-anywhere`](../pay-l402-anywhere/) skill, or any L402 client. No
  marketplace account or credits are involved, and every sat settles to the
  account's receive wallet. Each paid call shows up in
  `l402_producer(action="list_challenges", challenge_status="paid")`; the
  dashboard's Endpoints page shows challenges minted per endpoint, not
  payments.
- **What step 6 showed:** the report's classification, the payment hash, and
  the amount, never a credential. `FULFILLMENT_VERIFIED` is the complete
  result.
- **How to watch sales:**
  `l402_producer(action="list_challenges", challenge_status="paid")`. For a
  push notice instead of polling, set a webhook URL in the dashboard under
  **Settings**, then **Webhooks**: Lightning Enable sends one
  `l402.challenge.paid` event per paid challenge. See the
  [webhooks reference](https://docs.lightningenable.com/api-reference/webhooks).
- **How to add a route:** one more `l402_producer(action="add_endpoint", …)`
  call on the same proxy, with its own `endpoint_id` and the same `price_sats`.
  The route sells at `default_price_sats`.
- **How to change a price:** in the dashboard, not the MCP. Re-running
  `add_endpoint` with the same `endpoint_id` is refused as a duplicate, and no
  MCP action changes `default_price_sats`. On the proxy's **Pricing** tab,
  change **Default Fallback Price** to change what every route charges. To give
  one route its own price, edit that route's price, then confirm the yellow
  **Sync** chip so the charge matches the advertised price. Challenges already
  minted keep the price they carry.
- **The plan's caps:** the Free Producer Sandbox allows 1 proxy, 3 distinct
  resource paths for the life of the account, 200 challenges a month, and 1,000
  sats at most per challenge. A paid Agentic Commerce plan lifts them. The
  [`lightning-enable-account`](../lightning-enable-account/) skill reads the
  plan and renews it; for plans, see
  [lightningenable.com](https://www.lightningenable.com). Do not quote a plan
  price from memory.

### 8. Optional: list on Amazap

The setup is complete at step 7. [Amazap](https://amazap.com/sell), a
separate marketplace, can extend it with more distribution. Offer it once,
after the hand-off, as an option; no answer means no.

- **Ask first.** Ask whether the human wants an Amazap listing. No answer
  means no. Only after a yes, look for an existing row, imported from 402
  Index: match the full endpoint URL the row stores, not the host alone.
  Never draft a duplicate listing.
- **Gate.** Reuse the step 6 report; never pay again for a listing. Offer the
  listing as ready only when its `classification` is `FULFILLMENT_VERIFIED`
  and its `marketplace_profiles.amazap.status` is `READY`, and only once
  example parameters are known, replay behavior is understood, no error or
  output exposes a secret, and the human has chosen title, description,
  category, and price. Without that report, the listing is not ready.
- **Draft, never publish.** Only once the gate passes, call Amazap's
  read-only `list_my_endpoint` tool when the host lists it, or give the human
  https://amazap.com/sell. On `api.lightningenable.com` the human supplies
  the title, description, category, and example parameters by hand.
- **The human decides.** Show the seller price (`default_price_sats` unless
  the route has its own price in the dashboard) and Amazap's all-in price
  separately. Without the human's explicit approval, never submit the
  listing, accept seller terms, provide or infer a contact email, opt into
  announcements, publish a Nostr handle, change the endpoint's price, or
  claim a commercial relationship among any of Lightning Enable, Amazap, or
  Amboss. The human enters the contact email and submits. Submitting
  publishes the listing automatically once Amazap's checks pass. After any
  price change in the dashboard, re-run Amazap's checks.
- **Read back.** Never call the route listed or live until you have read
  `GET https://amazap.com/api/products/<slug>` and checked `hidden`,
  `listingState`, and `healthStatus`; call it listed only with
  `hidden: false` and when the row's endpoint URL and seller price match this
  route. Listed is not verified paid delivery.

Lightning Enable does not hold funds; the payment provider facilitates custody
and settlement. Full rules:
[Amazap marketplace: Seller handoff](https://github.com/refined-element/lightning-enable-skills/blob/main/references/amazap-marketplace.md#seller-handoff).

## What can go wrong

### How a producer error arrives

A failed `l402_producer` action returns `success: false` with the API's own
words: `error` (a stable slug or the prose), `message` or `detail` (what
happened this time), `errorType` (the problem `type` URI, such as
`https://lightningenable.com/problems/l402_not_enabled`), `httpStatus`, and
`validationErrors` when a field failed. **Read the slug, then repeat the message
to the human.** Never invent a cause the body does not give you, and never
retry a call that failed on a cap.

| Symptom | Likely cause | Do this |
|---|---|---|
| "API key required" | The MCP has no merchant key loaded | Set `LIGHTNING_ENABLE_API_KEY` or add the key to `~/.lightning-enable/config.json`, restart the MCP, then re-run `l402_producer(action="status")`. No key at all: use `producer-setup`. |
| 400 on `create_proxy`, private address | The upstream is an IP address, localhost, or an internal host, resolves to a private network, or uses a port other than 80 or 443 | Deliberate SSRF block. Give a public URL with a domain name, or tunnel the upstream first. |
| 402 `plan_proxy_limit` | The plan's proxy cap (1 on the Free Producer Sandbox, and a retired proxy still counts) | Reuse the existing proxy, delete an unused one in the dashboard, or add billing. |
| 402 `plan_endpoint_limit` | The account is at its cap of distinct resource paths (3 for the life of a Free Producer Sandbox account) | Reuse a path that already sold, or add billing. |
| 402 `plan_price_limit` | The price is above the plan's per-challenge cap (1,000 sats on the Free Producer Sandbox) | Lower the price, or add billing. |
| 402 `plan_volume_limit` | The month's challenge allowance is spent (200 on the Free Producer Sandbox) | Wait for the month to roll over, or add billing. |
| `endpoint_retired` | An operator retired that resource path | Use a different path, or ask support to clear the retirement. |
| `validationErrors` on a call | A field failed validation, often a bad URL or a name that is too long | Fix the named field and call again. |
| 400 "already exists" on `add_endpoint` | The `endpoint_id`, or the method and path, is already on the proxy | Use a different `endpoint_id`, or edit the route in the dashboard. |
| 422 `listing_verification_failed` on `publish` | The proxy has no price above 0 | Check `default_price_sats`, then publish again. |
| 500 or 503 when a challenge mints, `payment_provider_not_configured`, or `challenge_persist_failed` | No receive wallet, or the mint could not be recorded | Re-run `l402_producer(action="configure_receive")`, then `action="status"`. A challenge that cannot be recorded is refused, never served unrecorded. |
| 403 `l402_not_enabled` | The trial ended, the plan does not include L402, or the account is inactive | Check `l402_producer(action="status")` for the plan and subscription status. |
| The self-test payment is refused | The wallet will not pay its own invoice | Pay from a second wallet, or stop at the 402. |
| The amount paid differs from the advertised price | `price_sats` on the route differs from `default_price_sats` | Set them equal, or set the route's charge in the dashboard and confirm **Sync**. |

## Safety rules

- **Get an explicit yes before the self-test payment**, naming the price.
- **Tighten the budget before you spend**, not after.
- **Never echo secrets.** API keys, NWC connection strings, Strike keys, LND
  macaroons, L402 macaroons, and preimages never appear in your output. Report
  `<set>` or `<not set>`.
- **One L402 payment at a time.**
- **The upstream and the price are the human's call.** Do not proxy an API whose
  terms forbid resale, and do not proxy one that needs the human's private
  credentials without saying so.
- **Nothing private in public fields.** Paths, summaries, the service
  description, the manifest, and the OpenAPI document are public.

## What this is NOT

- **Not a fee on sales.** Lightning Enable charges a flat subscription. Every
  satoshi a buyer pays settles to the configured wallet.
- **Not custody.** Lightning Enable does not hold funds; the wallet or the
  payment provider facilitates custody and settlement.
- **Not demand.** A published proxy is a way to get paid, not a stream of
  buyers. Do not promise revenue.

## Example

> User: "Wrap my weather API with L402, 10 sats a call. The forecast route is
> GET /forecast."
>
> 1. `l402_producer(action="status")`: plan `individual` (Agentic Commerce),
>    `l402Enabled: true`, receive `nwc` `<set>`, 0 proxies.
> 2. Ask for the base URL and a self-test ceiling. The human gives
>    `https://api.example-weather.dev` and 20 sats.
> 3. `l402_producer(action="create_proxy", name="Weather API",
>    target_base_url="https://api.example-weather.dev",
>    description="Hourly forecasts", default_price_sats=10)` returns
>    `proxyId: "weather-api"`.
> 4. `l402_producer(action="add_endpoint", proxy_id="weather-api",
>    endpoint_id="forecast", path="/forecast", http_method="GET",
>    price_sats=10, summary="Hourly forecast for one location")`.
> 5. `l402_producer(action="publish", proxy_id="weather-api",
>    service_description="Hourly weather forecasts", categories=["weather"])`
>    returns the OpenAPI and manifest URLs.
> 6. `access_l402_resource` on the OpenAPI URL with `max_sats=1`: 200, free.
>    With the human's yes, and nothing spent yet this session,
>    `budget(action="tighten", per_request=20, per_session=20)`, then
>    `access_l402_resource(url="<endpoint url>", max_sats=20)`: 402, paid 10
>    sats, 200 forecast.
> 7. `l402_producer(action="list_challenges", challenge_status="paid")` shows
>    the sale.
> 8. `python scripts/l402_check.py <endpoint url> --json --max-sats 20 --output mode-a.json`
>    → `CHALLENGE_COMPATIBLE`; recording item 6's self-test call as the
>    evidence turns it into `FULFILLMENT_VERIFIED`, with no second payment.
> 9. Hand off: "Live and charging 10 sats a call, listed in the Lightning
>    Enable registry, where agents find it with `discover_api` and pay from
>    their own wallets. Share the two URLs; change prices in the dashboard."
