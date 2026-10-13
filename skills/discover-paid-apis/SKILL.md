---
name: discover-paid-apis
description: >-
  Use when the user needs to find, compare, and optionally try a paid API or
  digital service. Search the Lightning Enable registry and Amazap, label each
  source, show current price and trust signals, then make at most one bounded
  trial purchase with approval. Use when the user has no URL yet ("find me a
  weather / finance / health API I can pay for", "what paid APIs are out
  there", "is there an L402 API for X", "search Amazap for X", "try a paid
  API"). Do NOT use to pay a URL the user already has (use pay-l402-anywhere),
  to answer a research question with cited paid data (use cited-answer), to
  sell or list an API (use producer-setup or create-l402-proxy), or to connect
  a wallet from nothing (use agent-wallet-setup).
---

# Discover paid APIs

Find something worth paying for, see what it costs before spending anything,
and try it once. You search two sources and label every row with the one it
came from:

- **The Lightning Enable registry,** searched with `discover_api`. Each
  listing points at an L402 manifest with the endpoints and their prices. A
  registry result is paid directly from the Lightning Enable MCP wallet.
- **Amazap** ([amazap.com](https://amazap.com)), a storefront where agents
  search a catalog of pay-per-call APIs and digital services and buy calls
  with prepaid Amazap credits. Amazap does not replace the Lightning Enable
  registry; it is a second source.

You search, the human picks, you read the details for free, and at most one
paid trial shows whether the service delivers.

Lightning Enable does not hold funds; the payment provider facilitates custody
and settlement. Amazap credits are governed by the current Amazap credit
terms (https://amazap.com/credits).

Amazap is another company's live product. Its fees, limits, terms, and catalog
change without notice, so read them from the current Amazap pages
(https://amazap.com/llms.txt, https://amazap.com/mcp,
https://amazap.com/credits) each time, never from memory. The shared rules
for buying through Amazap are in the
[Amazap reference](https://github.com/refined-element/lightning-enable-skills/blob/main/references/amazap-marketplace.md#discovery-versus-purchase),
with its
[two-wallet rule](https://github.com/refined-element/lightning-enable-skills/blob/main/references/amazap-marketplace.md#two-wallets).

## What is automated, and what is not

**Automated:** checking which tools the host lists, reading the MCP budget and
balance, searching both sources, the comparison, reading a manifest or a
listing's input schema without paying, the quote, the one trial purchase, and
the receipt.

**Not automated. The human decides these:**

- **What to look for:** the outcome they need, not just a category.
- **Which candidate to try,** from the comparison you present.
- **Whether to pay,** at the moment of payment, with the all-in price and the
  cap that applies stated.
- **What input to disclose,** when it holds anything sensitive.
- **Whether to accept the current Amazap terms,** before an Amazap buy.

## What you need

- The [Lightning Enable MCP](https://github.com/refined-element/lightning-enable-mcp)
  server, for the registry search and the direct path. To pay a registry
  result it needs a wallet that returns preimages (NWC, LND, or Strike). If
  `get_balance` or `setup_wallet` says no wallet is configured, the registry
  can still be searched but not paid; use
  [`agent-wallet-setup`](../agent-wallet-setup/) to connect one.
- Optionally, Amazap's MCP (https://amazap.com/mcp), for an Amazap buy. Its
  tools exist only when the host lists them. Without them, Amazap search still
  works through the public products API, and an Amazap buy isn't available in
  this run.
- No Lightning Enable account.
- Lightning Enable MCP tools this skill uses:
  - `budget`: `action="status"` for the MCP limits and what the session has
    left.
  - `get_balance`: the MCP wallet's funds.
  - `discover_api`: searches the registry (`query`, `category`) or reads one
    API's manifest (`url`). It never pays.
  - `access_l402_resource`: fetches a URL with GET or HEAD and pays an L402
    challenge up to `max_sats`.
  - `receipts`: `source="session"` lists this session's payments.
- Amazap MCP tools, named by capability, only when the host lists them:
  - search and inspect, which never spend: `search_catalog`, `describe_sku`,
    and `quote`;
  - the one call that spends Amazap credits: `buy`;
  - credits and limits: `balance`, `spend_summary`, and `top_up` (creates a
    Lightning invoice for the human to pay and moves no sats itself);
  - after a buy: `orders`, `get_order`, `report_outcome`,
    `claim_failed_call`, and `report_sku`.

  Hosts add their own prefixes to these names, so match a tool on its name and
  description, not on one exact qualified name.

Argument names below are the Python server's `snake_case`. The .NET server takes
the same arguments in `camelCase`: `budget_aware` → `budgetAware`, `max_sats` →
`maxSats`, `confirmation_nonce` → `confirmationNonce`. Response fields are
`camelCase` in both ports, with two exceptions this skill meets: `discover_api`
answers in `snake_case` in both (`manifest_url`, `default_price_sats`,
`affordable_calls`), and `access_l402_resource` shapes a paid result differently
in each port (step 6 has the table).

## Flow

### 0. Ask what the human wants

Collect, in one message, what you can't infer:

1. **The outcome:** the result they need ("tomorrow's forecast for Berlin",
   not just "weather"), how fresh it must be, what input they will supply,
   and what output format they want.
2. **The trial ceiling:** the most one trial may cost, all-in, in sats, and
   whether a paid trial is authorized at all.
3. **Restrictions:** providers to avoid, and any limits on data handling,
   jurisdiction, or content.

Use obvious defaults when the risk is low. Ask only when the answer changes
what gets bought or what data leaves. Searching, describing, and quoting never
spend, so steps 1 to 5 need no yes. Step 6 pays, and needs its own yes.

### 1. Check the tools and the MCP leash

- **Which tools does the host list?** Note whether Amazap's tools are present.
  If they aren't, say so plainly: Amazap search uses the public products API,
  and an Amazap buy needs Amazap's MCP (https://amazap.com/mcp). Never claim
  Amazap MCP access you don't have.
- **The MCP leash, for the direct path only:**

  ```
  budget(action="status")
  get_balance()
  ```

  Note the sats the session budget has left and the wallet balance; the
  smaller one bounds a direct L402 payment. If the budget reports that no
  price is available and the limits are in USD, payments are refused until a
  price source recovers; say so. These numbers are for the Lightning Enable
  registry path only. They don't see Amazap credits and never bound an Amazap
  buy.
- **Amazap credits, when Amazap's tools are listed:** `balance` or
  `spend_summary` returns the remaining Amazap credits and the account's
  current limits. Read them; don't assume them.

### 2. Search both sources

Amazap does not replace the Lightning Enable registry, so search both. Put
the outcome in the search terms. Run at least one refinement when the first
results are empty, too broad, or mostly irrelevant. Searching never spends.

**The Lightning Enable registry, with `discover_api`.**

```
discover_api(query="weather")
discover_api(category="finance")
discover_api(query="forecast", category="data")
```

Pass `query`, `category`, or both. `budget_aware` defaults to `true`, which adds
`affordable_calls` to each result and a `budget` block (`remaining_sats`,
`session_spent_sats`) to the response. Each result can carry `name`,
`description`, `categories`, `endpoint_count`, `default_price_sats`,
`manifest_url`, `proxy_base_url`, and `documentation_url`. A search returns up to
20 results.

The registry is `L402_REGISTRY_URL` if set, otherwise
`LIGHTNING_ENABLE_API_URL`, otherwise `https://api.lightningenable.com`.

- **"Lightning Enable Account Activation" in the results:** that entry is the
  account signup, listed for unfiltered and signup-style searches. It is not a
  data API. Leave it out of the comparison.
- **No results:** the response says so and suggests other keywords. Try a
  broader keyword or a category once. Never invent an API.
- **A registry error or redirect:** the response names the registry URL it
  called. Report it, and carry on with Amazap.
- **The human names a site:** `discover_api(url="https://api.example.com")`
  looks for a manifest at `/.well-known/l402-manifest.json`,
  `/.well-known/l402.json`, `/l402-manifest.json`, and `/l402.json`, then at
  the URL itself. A URL that ends in `.json` is tried first. Use what it
  returns in step 4.

**Amazap, through its MCP.** When the host lists `search_catalog`, call it
with the outcome terms. It hides demo and unhealthy listings by default, and
each result carries an all-in price, a quote, and a ready-to-use buy call.
Do not run it; `buy` waits for the trial step and the human's yes.

**Amazap, without its MCP.** Use the read-only public products API:

```
GET https://amazap.com/api/products?q=weather&limit=50&offset=0
```

It takes `q`, `protocol`, `category`, `source`, `healthyOnly`, `synthetic`,
`limit` (at most 200), and `offset`, and answers with `products`, `total`,
`limit`, and `offset`. Page with `offset` until `offset >= total`. Stop
sooner once you have enough relevant rows to pick five.
`GET https://amazap.com/api/products/<idOrSlug>` returns one row, wrapped in
`product`, with its `inputSchema.fields[]`. This path reads; it can't buy.

For every row:

- **Label every row** with its source: "Lightning Enable registry" or
  "Amazap". Label any other configured registry by its own name.
- **Paused or degraded rows are shown, not bought.** A search result may
  include paused or degraded rows, so read `listingState` and `buyable` on
  every row.
- **Hidden rows are dropped.** A row can also be hidden from search and still
  be returned by slug, with `hidden: true`. A hidden row is not a candidate,
  to show or to buy. Don't fetch one by slug to work around that.
- **A directory row is not a delivery record.** Many Amazap rows are imported
  from directories such as 402 Index. Read `trust.label` and the paid track
  record instead of assuming Amazap has delivered the service.
- **The same service in both sources.** Show each row as its source returned
  it. Never frame a price difference as a reason to bypass Amazap. Never steer
  a buyer away from Amazap's all-in price toward direct payment of a listing
  Amazap surfaced. Amazap's margin funds its failed-call credits. Direct
  payment through `pay-l402-anywhere` is for a URL the user already has.

### 3. Compare at most five candidates

Show at most five candidates, one row each:

| Source | Product and provider | Protocol and rail | All-in price | Inputs | Trust and health | Buyable now | Wallet |
|---|---|---|---|---|---|---|---|

- **All-in price.** For an Amazap row, show `totalSats`, the all-in figure the
  buyer pays, with `priceSats` (the seller price) and `feeBps` as its
  breakdown. Never add `priceSats` and the fee yourself; the all-in total can
  differ from that sum. For a registry row, show `default_price_sats`, or "see
  the manifest" when there is none. When neither source gives a fixed price,
  write "quote required".
- **Inputs.** For an Amazap row, list `inputSchema.fields[]` (each field's
  `name`, `type`, `required`, and `in`: `body`, `query`, or `path`) with
  `schemaConfidence`. For a registry row, step 4 reads them from the manifest.
- **Trust and health, exactly as reported.** For an Amazap row, show
  `trust.label`, `healthStatus`, and `listingState`, and the paid record
  (`paidSuccesses`, `paidFailures`, `lastPaidSuccessAt`) when present. Quote
  `trust.label` as returned. For example, it may start with Verified, Working,
  Limited track record, or Having trouble, and add detail; those are observed
  values, not a fixed list, so quote it as returned. Never upgrade a label.
- **Buyable now.** `buyable` for an Amazap row, read with `listingState` and
  `hidden`; drop any row with `hidden: true`. Show a row with
  `buyable: false`, and never buy it.
- **Protocol and rail.** `protocol`, `paymentAsset`, and `paymentNetwork` for
  an Amazap row; L402 over Lightning for a registry row.
- **Wallet.** "Amazap credits" for an Amazap row, "MCP wallet" for a registry
  row. Step 5 states the caps for each.
- **Affordability, for a registry row.** `affordable_calls` counts against the
  session budget, and the wallet balance divided by the price counts against
  the funds; show the smaller, and say which one binds.
  `affordable_calls: "unknown"` means the price or the budget could not be
  determined: show "unknown" and treat the API as not proven affordable,
  never as free or unlimited.
- **Data sharing.** Say who receives the input: for an Amazap row, Amazap and
  the seller behind the listing; for a registry row, the seller's endpoint.
- **Unknown values.** Leave a cell blank when its source doesn't report it;
  never fill it with a guess.

Recommend one candidate, with a one-sentence reason. Prefer a reliable, clearly
specified service over the cheapest. When the same service is in both sources,
base the recommendation on reliability and clarity, never on the price
difference between the rows. Never mention a listing's `endpointUrl` as a way
to pay the seller directly.

If nothing matched or nothing is affordable, say so plainly instead of
stretching a weak match. Then let the human pick one.

### 4. Read the manifest, unpaid

```
discover_api(url="<manifest_url>")
```

This never pays. It returns `service` (name, description, `base_url`,
categories), `l402` (`default_price_sats`, payment flow, capabilities), and
`endpoints`. Each endpoint carries `path`, `method`, `summary`, and
`pricing.base_price_sats`, plus `affordable_calls` and, when a BTC price is
available, `cost_usd`.

Pick the endpoint with the human. Build its URL from `service.base_url` and the
endpoint's `path`, and check two things before going on:

- **The method is GET or HEAD.** `access_l402_resource` refuses every other
  method before any request or payment. A POST-only endpoint is outside this
  skill. Tell the human: paying one takes an HTTP client that captures the 402
  challenge, `pay_l402_challenge` to pay it (the manual path in
  [`pay-l402-anywhere`](../pay-l402-anywhere/)), or an L402 client library
  ([`l402-client-integration`](../l402-client-integration/)).
- **The price fits** the human's trial ceiling and the session budget.

**Lightning Enable proxies publish an OpenAPI document too.** A registry entry
whose `proxy_base_url` looks like `https://api.lightningenable.com/l402/proxy/{proxyId}`
also serves `/l402/proxy/{proxyId}/openapi.json` (OpenAPI 3.1, with an
`x-payment` extension carrying each operation's price) beside its
`/l402/proxy/{proxyId}/.well-known/l402-manifest.json`. `discover_api` reads the
manifest, not the OpenAPI document. If you need the request parameters the
manifest doesn't list, fetch the OpenAPI document with a 1-sat cap, so a
mislabeled paid URL can't spend more than that:

```
access_l402_resource(url="<proxy_base_url>/openapi.json", max_sats=1)
```

It should come back with no payment. If it reports one, tell the human.

### 5. Confirm, then make ONE paid call

State the call before you make it, and **stop for a yes**: "I will call
`GET <endpoint url>`, which costs `<price>` sats. Your trial ceiling is
`<ceiling>`. Go ahead?"

After the yes:

```
access_l402_resource(url="<endpoint url>", max_sats=<the listed price>)
```

Set `max_sats` to the listed price, never above the human's trial ceiling. The
budget checks `max_sats`, and the call refuses an invoice above it, so a seller
who raised the price since the listing can't take more than the human approved.

The two ports shape a successful result differently:

| | Python server | .NET server |
|---|---|---|
| Sats paid | `paid_sats` | `payment.amountSats` |
| Response body | `response` (truncated past 5,000 characters) | `content` |
| No charge | `paid_sats` is null | `payment.paid` is false |

Both carry `receipt_written`, which says whether the durable receipt landed. The
.NET result also carries `payment.l402Token`; it contains the preimage, so never
show it.

- **Success:** report the sats paid and the body, as above.
- **`requiresConfirmation: true`:** the amount is above the auto-approve tier.
  The code went to the human, never to you. Ask for it, then repeat the call with
  the same `url` and `max_sats` and `confirmation_nonce="<code>"`. Codes are
  bound to the amount, the tool, and the URL. Never guess one.
- **Refused with `requiresConfirmation: false`:** no human can receive a code on
  this server (a hosted deployment with the `refuse` channel). Stop; retrying
  won't help.
- **A budget denial:** the error names the limit (the Python server adds it as
  `denialReason` under `"Payment denied by budget policy"`). Report it. Don't
  retry with a smaller `max_sats` to squeeze under a cap.
- **The invoice costs more than `max_sats`:** nothing was paid. Tell the human
  the real price and ask again.
- **`alreadyPaid: true`:** the payment went through but the endpoint failed or
  redirected afterward. **Do not pay again**, and don't call that URL again in
  this skill: a fresh call to a paid URL can mint and pay a second invoice. The
  result carries an `l402Token`; it contains the preimage, so never show it.
  Tell the human the sats paid and the error, and stop.

### 6. Show the result and the spend

```
receipts(source="session")
```

Report:

- **What came back,** faithfully. Summarize the `response`, quote its key
  figures, and say when it was truncated. Never claim data the call did not
  return.
- **What it cost:** the sats paid from the call, matched against the session
  receipt.
- **What is left:** the session budget and the balance, re-read with
  `budget(action="status")` if the human wants the exact number.

### 7. Hand off

- **To keep using this API:** [`pay-l402-anywhere`](../pay-l402-anywhere/), with
  the endpoint URL and its price.
- **To answer a research question with paid data and citations:**
  [`cited-answer`](../cited-answer/).
- **To list an API of their own in the same registry:**
  [`producer-setup`](../producer-setup/).

## What can go wrong

| Symptom | Likely cause | Do this |
|---|---|---|
| `discover_api` returns no results | Nothing in the registry matches | Try one broader keyword or a category, then tell the human. Never invent an API. |
| Registry returned an error status or a redirect | The registry is down, or `L402_REGISTRY_URL` / `LIGHTNING_ENABLE_API_URL` points somewhere wrong | Report the `registry_url` from the response. The human can still name a site for `discover_api(url=...)`. |
| "Could not find an L402 manifest" with `tried_urls` | The site publishes no L402 manifest at the well-known paths | Show the human the paths tried. Without a manifest, the price is unknown; don't guess it. |
| `redirect_location` in a `discover_api(url=...)` result | The URL redirects, and the tool doesn't follow redirects | Call `discover_api` again with the redirect target, if the human agrees it is the same site. |
| A URL refused before any request | It resolves to a private or internal address | Deliberate SSRF (server-side request forgery) protection. Use a public URL. |
| `affordable_calls: "unknown"` | The price or the budget could not be determined | Treat it as not proven affordable. Read the manifest for the price; check `budget(action="status")`. |
| `access_l402_resource` refuses the method | The endpoint needs POST or another non-read method | Outside this skill. Point the human at `pay_l402_challenge` (in `pay-l402-anywhere`) or an L402 client library. |
| A budget denial | A per-payment or per-session cap | Report the limit the error names. Only the human changes the config file. |
| `requiresConfirmation: true` | The amount is above the auto-approve tier | Ask the human for the code, then repeat the same call with `confirmation_nonce`. |
| Payments refused while no BTC price is available | USD limits can't be checked during a price outage | Expected: the budget fails closed. Sats caps and `autoApproveSats` keep small payments working. |
| `alreadyPaid: true` | Paid, then the endpoint errored or redirected | Do not pay again or call the URL again. Report the sats paid and the error. |
| "No wallet configured", or the payment returns no preimage | No wallet, or an OpenNode or Primal NWC wallet | Run `agent-wallet-setup` and connect NWC (Alby Hub, CoinOS, CLINK), LND, or Strike. |

## Safety rules

- **Free reads first, one paid call last.** Searching and reading manifests
  never pay. Pay only after the human picked an endpoint and said yes to its
  price.
- **One L402 payment at a time.** Finish one 402, pay, access cycle before
  starting another. Never fan out paid calls across several APIs to compare
  them.
- **Respect the caps.** `max_sats` never exceeds the human's trial ceiling or
  the session budget. Never raise a limit.
- **Never claim a result the call did not return,** and say when a response was
  truncated.
- **Say when nothing is affordable** or nothing matched, instead of stretching a
  weak match.
- **Never echo secrets.** The `l402Token`, macaroons, and preimages stay out of
  your output.
- **A listing is not an endorsement.** The registry lists what sellers publish.
  Tell the human what the manifest says, not what you assume about the seller.

## What this is NOT

- **Not custody.** Lightning Enable does not hold funds; the wallet facilitates
  custody and settlement.
- **Not a subscription.** Each paid call is a single Lightning payment, and the
  human approves it.
- **Not a review service.** You report the listing, the manifest, and what one
  call returned. You don't vouch for the seller.
- **Not wallet setup.** If no wallet is connected, use
  [`agent-wallet-setup`](../agent-wallet-setup/) first.

## Example

> User: "Is there a weather API I can pay for? Spend at most 20 sats trying it."
>
> 1. `budget(action="status")` → 480 sats left this session.
>    `get_balance()` → 4,700 sats.
> 2. `discover_api(query="weather")` → three results.
> 3. Present the table: "Forecast API, 10 sats a call, 48 calls (session budget
>    binds); Marine Weather, 25 sats, over your 20-sat trial ceiling; Air Quality,
>    price unknown." The human picks Forecast API.
> 4. `discover_api(url="<manifest_url>")` → `GET /forecast` at 10 sats.
>    "I will call `GET https://.../forecast`, which costs 10 sats. Go ahead?"
>    The human says yes.
> 5. `access_l402_resource(url="https://.../forecast?lat=40.71&lon=-74.00",
>    max_sats=10)` → paid 10 sats, a five-day forecast.
> 6. `receipts(source="session")` shows the 10-sat payment. "Five-day forecast
>    for New York, highs of 18 to 22 °C. Spent 10 sats; 470 left in this
>    session. To keep using it, pay-l402-anywhere takes it from here."
