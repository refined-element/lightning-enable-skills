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
2. **The user's cap:** the most one trial may cost, all-in, in sats, and
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
Do not run that buy call; `buy` waits for the trial step and the human's yes.

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
- **Paused, degraded, or failing rows are shown, not bought.** A search
  result may include paused, degraded, or failing rows, so read
  `listingState`, `healthStatus`, and `buyable` on every row.
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
  values, not a fixed list. Never upgrade a label.
- **Buyable now.** For an Amazap row, read `buyable` with `listingState`,
  `healthStatus`, and `hidden`; drop any row with `hidden: true`. Show "no"
  for a paused, degraded, or failing row, even when `buyable` is true. Show
  a row with `buyable: false`, and never buy it.
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

### 4. Read the details, unpaid

**A registry result.**

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
  method before any request or payment. A POST-only endpoint is outside the
  direct path of this skill. Tell the human: paying one takes an HTTP client
  that captures the 402 challenge, `pay_l402_challenge` to pay it (the manual
  path in [`pay-l402-anywhere`](../pay-l402-anywhere/)), or an L402 client
  library ([`l402-client-integration`](../l402-client-integration/)).
- **The price fits** the user's cap and the session budget.

**Lightning Enable proxies publish an OpenAPI document too.** A registry entry
whose `proxy_base_url` looks like `https://api.lightningenable.com/l402/proxy/{proxyId}`
also serves `/l402/proxy/{proxyId}/openapi.json` (OpenAPI 3.1, with an
`x-payment` extension carrying each operation's price) beside its
`/l402/proxy/{proxyId}/.well-known/l402-manifest.json`. `discover_api` reads the
manifest, not the OpenAPI document. If you need request parameters the
manifest doesn't list, read `<proxy_base_url>/openapi.json` with a plain HTTP
GET that can't pay, when the host has one, or give the human the URL to open.
Never read it with `access_l402_resource`: that tool pays any 402 it meets, and
this step never spends.

**An Amazap row.** When the schema is unclear or `schemaConfidence` is low,
call `describe_sku` when the host lists it, or read
`GET https://amazap.com/api/products/<idOrSlug>`. Fill each required field in
`inputSchema.fields[]` from the user's input. Neither call spends.

**Check the input before it leaves.** Never send secrets, private URLs,
authenticated pages, credentials, personal data, or proprietary content as a
purchase input unless the user explicitly approved that disclosure. If the
input holds any of these without that approval, don't send it: say what you
found, and buy nothing. A private or logged-in URL is the common case.

### 5. Quote, and state the cap that applies

Before any payment:

- **Get a fresh quote.** An Amazap search or `describe_sku` result already
  carries one; call `quote` only when the quantity or the parameters change.
  For a registry result, the manifest price is the quote, and the 402 challenge
  confirms it.
- **Match it** to the exact listing, parameters, quantity, and account.
- **Show the exact all-in total in sats.**
- **Say who receives the input,** as in step 3.

State which cap applies to which path before any purchase.

| Path | Wallet | Caps that apply |
|---|---|---|
| Amazap `buy` | Prepaid Amazap credits, added with `top_up` | The user's cap, passed as `max_total_sats`, and the Amazap account limits |
| Lightning Enable registry result paid directly | The Lightning Enable MCP wallet | The user's cap and the MCP `budget` limits |

The Lightning Enable MCP `budget` and `get_balance` don't see Amazap credits
and never bound an Amazap buy, and Amazap's limits never bound a direct
payment from the MCP wallet. Never present `budget` status or `get_balance` as
bounding an Amazap buy.

Read the Amazap account limits and its auto-approve amount from `balance` or
`spend_summary` each time, as in step 1; they change, so never hard-code them.
The Amazap limits are per call, per day, and per session. Above the
auto-approve amount, the person confirms the buy in Amazap, or `buy` returns
`approval_required` and charges nothing.

**Over the cap, refuse.** If the all-in total is above the lowest cap that
applies to its path, refuse and buy nothing; say the total and the cap. A
31-sat quote against a 30-sat cap is a refusal, not a negotiation.

Search, describe, and quote never spend.

### 6. Buy one trial

At most one trial purchase per run, unless the user explicitly asks for more.

Buy only when every item holds:

- the user authorized a paid trial, or an existing policy explicitly permits
  it;
- the all-in total is within the lowest cap that applies to its path;
- the input passed the check in step 4;
- the quote is fresh and matches the final parameters;
- the service is buyable: `buyable: true` on an Amazap row, which is also
  neither paused (`listingState`) nor degraded or failing (`healthStatus`);
- any required human confirmation is complete.

A paused or degraded row stays unbought this run, even with `buyable: true`,
and so does a failing one. Step 2 shows such a row; it is not a candidate to
buy.

State the purchase and **stop for a yes**: "I will buy one call to
`<listing>` from `<source>` for `<total>` sats all-in, paid from `<wallet>`,
within your `<cap>`-sat cap. `<who>` receives your input. Go ahead?" Amazap
auto-approves small buys on its own side; this skill still asks the user
first.

For an Amazap buy, the same yes also covers the current Amazap terms. Add:
"Buying through Amazap means accepting its current terms
(https://amazap.com/terms and https://amazap.com/credits). Do you accept
them and go ahead?" A bare "Go ahead?" is never consent to the terms, so
it never sets `accept_terms`.

**Through Amazap, with `buy`.**

```
buy(<the listing and parameters from the quote>,
    quote_id="<quoteId from the current quote>",
    total_cost=<that quote's total>,
    max_total_sats=<the user's cap>,
    accept_terms=<only after the user agreed to the current Amazap terms>)
```

- Start from the buy call that `search_catalog`, `describe_sku`, or `quote`
  returned, and keep its listing and parameters. Pass `quote_id` and
  `total_cost` from the current quote, and set `max_total_sats` to the user's
  cap. That call arrives with `accept_terms` and `max_total_sats` already
  filled in; never send it as it came.
- Set `accept_terms` only after showing the current Amazap terms
  (https://amazap.com/terms and https://amazap.com/credits) and getting the
  user's agreement in the same yes as the purchase.
- **A stale quote.** When `buy` reports a stale quote, the stale attempt
  charged nothing, and the error carries a fresh quote. Show the fresh quote
  from the error, check that its total is still within the cap, and confirm
  with the user that the terms are unchanged. Then state the fresh total and
  get a new yes before buying with its `quote_id` and `total_cost`. The first
  yes never covers a different total. Never buy on the fresh quote
  automatically.
- **`approval_required`.** The total is above Amazap's auto-approve amount,
  and the person must confirm it in Amazap. Stop, and ask the person to
  confirm the exact quote in Amazap; nothing is charged until they do. Never
  re-quote or split the purchase to get around it. Once they say they
  approved it, the same `quote_id` can be bought once.
- **Retries.** When the outcome is unclear (a dropped connection, a
  timeout), check before any retry: `get_order` or `orders` shows whether the
  buy went through. Repeating a `quote_id` never charges twice, so a retry
  with the same `quote_id` is safe once the order shows none. A new quote is
  a new purchase.
- **Baskets.** A basket is one buy. Put several listings in one buy only when
  the user asked for more than one call.
- **Credits short.** If `balance` shows too few credits, ask before `top_up`.
  The human chooses the top-up amount. `top_up` returns a Lightning invoice
  and a QR code for the human to pay; let the host show that result to the
  human, and never copy the invoice into your own message. Never pay the invoice
  from the Lightning Enable MCP wallet unless the human explicitly asks. If
  they do, it is a separate payment with `pay_invoice`, and the human says
  yes to that exact amount first. The user's cap doesn't cover a top-up: it
  bounds the trial, not the credits added. The MCP `budget` limits do bound
  that payment, because it leaves the MCP wallet. Then read `balance` again
  before buying.

**Directly, for a Lightning Enable registry result, with
`access_l402_resource`.**

```
access_l402_resource(url="<endpoint url>", max_sats=<the listed price>)
```

This path is for a registry result. Never point it at an Amazap listing's
`endpointUrl`. Set `max_sats` to the listed price, never above the user's
cap. The budget checks `max_sats`, and the call refuses an invoice above it,
so a seller who raised the price since the listing can't take more than the
human approved.

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

### 7. Report the receipt

For an Amazap buy, the receipt carries the sats charged and the balance after
(`chargedSats`, `balanceAfterSats`) and the remaining Amazap limits; `orders`
or `get_order` returns the order. For a direct payment, read this session's
receipts and what the MCP budget has left:

```
receipts(source="session")
budget(action="status")
```

Report:

- the requested outcome;
- the delivered result, faithfully: summarize it, quote its key figures, say
  when it was truncated, and never claim data the call did not return;
- the sats charged, all-in;
- the remaining Amazap credits or the remaining MCP budget, whichever wallet
  paid, when available;
- the source, the provider, and the listing used;
- an order or receipt id safe to keep: the Amazap order id, or the payment
  hash of a direct payment;
- whether fulfillment succeeded.

Never print invoices, preimages, macaroons, OAuth tokens, NWC strings, wallet
credentials, or full payment authorization headers.

After a delivered Amazap buy, offer `report_outcome`, with the user's
approval. It is optional and spends nothing.

### 8. When a paid trial fails

Name what happened, as one of: quote failure, policy refusal, payment failure,
provider failure, malformed result, or user-declined approval.

- **Quote failure:** no fresh quote could be had, or it doesn't match the
  parameters. Nothing was charged.
- **Policy refusal:** a cap, an Amazap account limit, the MCP budget, or the
  input check refused the purchase. Report the limit the refusal names.
  Nothing was charged.
- **Payment failure:** the payment didn't go through. Report it, and don't
  retry with a smaller cap to squeeze under a limit.
- **Provider failure:** paid, and the service failed or returned nothing.
- **Malformed result:** paid, and the result doesn't match what the listing
  promised.
- **User-declined approval:** the user, or the person approving in Amazap,
  said no. Nothing was charged.

After a paid failure:

- Never buy a second candidate after a paid failure without asking. Ask
  before trying another paid listing.
- **Through Amazap:** a failed paid call is re-credited as Amazap credits,
  never cash. Say whether the re-credit was automatic (the order shows it). If
  it wasn't, offer `claim_failed_call`, within the window the current Amazap
  credit terms state (https://amazap.com/credits); read the window there.
  Some listings re-credit less than the full price; the same terms say which.
  With the user's approval, offer `report_sku` for a listing that misbehaves.
- **Directly:** follow the `alreadyPaid` rule in step 6. Don't pay again, and
  don't call the URL again.
- A pending or unclear payment is never replaced by a second one. Check it
  before any retry: `get_order` or `orders` on the Amazap path,
  `receipts(source="session")` on the direct path.

### 9. Hand off

- **A URL the user already has:** [`pay-l402-anywhere`](../pay-l402-anywhere/)
  pays it directly. That handoff applies to URLs the user already has, not to
  listings Amazap surfaced.
- **To keep using a registry API:** `pay-l402-anywhere`, with the endpoint URL
  and its price.
- **To keep using an Amazap listing:** buy it through Amazap again, one quote
  per call.
- **To answer a research question with paid data and citations:**
  [`cited-answer`](../cited-answer/).
- **To sell an API of their own:** [`producer-setup`](../producer-setup/), which
  can also draft an optional Amazap listing.

## What can go wrong

| Symptom | Likely cause | Do this |
|---|---|---|
| `discover_api` returns no results | Nothing in the registry matches | Try one broader keyword or a category, then say so. Never invent an API. |
| Registry returned an error status or a redirect | The registry is down, or `L402_REGISTRY_URL` / `LIGHTNING_ENABLE_API_URL` points somewhere wrong | Report the `registry_url` from the response, and carry on with Amazap. |
| "Could not find an L402 manifest" with `tried_urls` | The site publishes no L402 manifest at the well-known paths | Show the human the paths tried. Without a manifest, the price is unknown; don't guess it. |
| `redirect_location` in a `discover_api(url=...)` result | The URL redirects, and the tool doesn't follow redirects | Call `discover_api` again with the redirect target, if the human agrees it is the same site. |
| A URL refused before any request | It resolves to a private or internal address | Deliberate SSRF (server-side request forgery) protection. Use a public URL. |
| `affordable_calls: "unknown"` | The price or the budget could not be determined | Treat it as not proven affordable. Read the manifest for the price; check `budget(action="status")`. |
| Amazap's tools aren't listed | Amazap's MCP isn't connected in this host | Search with `GET https://amazap.com/api/products`. For a buy, point the human at https://amazap.com/mcp. Never claim Amazap MCP access. |
| An Amazap row shows `buyable: false` | The listing isn't payable now | Show it, and never buy it. |
| An Amazap row is paused, degraded, or failing | `listingState` or `healthStatus` says so | Show it as not buyable, and never buy it, even with `buyable: true`. |
| The user already has the URL | Nothing to discover | Hand off to `pay-l402-anywhere`. That handoff is for a URL the user already has, never for a listing Amazap surfaced. |
| The input holds something sensitive | Secrets, a private or logged-in URL, credentials, personal data, or proprietary content | Don't send it unless the user explicitly approved that disclosure. Say what you found, and buy nothing. |
| No fresh quote, or it doesn't match the parameters | Quote failure | Nothing was charged. Never buy on an old or mismatched quote. Quote again, or pick another candidate with the user. |
| `buy` reports a stale quote | The quote expired, or the parameters changed | Nothing was charged. Show the fresh quote from the error. If its total is within the user's cap and the terms are unchanged, state that total and get a new yes before buying. |
| The all-in total is above the user's cap | Policy refusal | Refuse and buy nothing; say the total and the cap. Never raise the cap or split the purchase to fit under it. |
| `buy` refuses on an Amazap account limit | Policy refusal: a per-call, per-day, or per-session Amazap limit | Nothing was charged. Report the limit the error names. Only the account owner changes it, on Amazap. |
| A budget denial on the direct path | Policy refusal: a per-payment or per-session cap on the MCP wallet | Report the limit the error names. Don't retry with a smaller `max_sats` to squeeze under it. Only the human changes the config file. |
| Payments refused while no BTC price is available | USD limits on the MCP wallet can't be checked during a price outage | Expected on the direct path: the budget fails closed. Sats caps and `autoApproveSats` keep small payments working. |
| `buy` returns `approval_required` | The total is above Amazap's auto-approve amount | Stop. The person confirms the exact quote in Amazap; nothing is charged until they do. Never re-quote or split the purchase to get around it. Once they say they approved it, the same `quote_id` can be bought once. |
| `buy` returns `terms_required` | `accept_terms` was missing | Show the current Amazap terms (https://amazap.com/terms and https://amazap.com/credits) and ask again, in one yes for the purchase and the terms. Set `accept_terms` only on that yes. |
| `buy` returns `not_yet_supported` | A listing payable only in a stablecoin | Not buyable in sats. Pick another candidate with the user. |
| Too few credits for the trial | The Amazap account needs a top-up | Ask before `top_up`; the human chooses the amount and pays the invoice. Paid from the MCP wallet, the top-up is its own `pay_invoice` payment, with its own yes on that exact amount: outside the user's cap, and inside the MCP `budget` limits. |
| `requiresConfirmation: true` | The amount is above the MCP auto-approve tier | Ask the human for the code, then repeat the same call with `confirmation_nonce`. Never guess a code. |
| The invoice costs more than `max_sats` | The seller raised the price since the listing | Nothing was paid. Tell the human the real price, and ask again only if it is within the user's cap; never above the user's cap. Never guess a price. |
| The payment didn't go through | Payment failure: a wallet, route, or invoice error | Report it, and check the outcome before any retry. Never retry with a smaller cap or `max_sats` to squeeze under a limit. |
| The outcome of a buy or a payment is unclear | A dropped connection or a timeout | Check before any retry: `get_order` or `orders` on the Amazap path, `receipts(source="session")` on the direct path. A pending or unclear payment is never replaced by a second one. |
| A paid Amazap call failed | Provider failure after payment: the service failed or returned nothing | Re-credited as Amazap credits, never cash. Say whether it was automatic; if not, offer `claim_failed_call` within the window the current Amazap credit terms state. Don't buy a replacement without asking. |
| `alreadyPaid: true` | Provider failure after a direct payment: paid, then the endpoint errored or redirected | Do not pay again or call the URL again. Report the sats paid and the error. |
| The result doesn't match the listing | A malformed result, after payment | Report it as a malformed result, and quote what came back; never claim data it lacks. On Amazap, offer `report_sku` with the user's approval. Don't buy or pay again without asking. |
| The user, or the person approving in Amazap, says no | User-declined approval | Stop. Nothing was charged. Report that nothing was bought. |
| `access_l402_resource` refuses the method | The endpoint needs POST or another non-read method | Outside the direct path. Point the human at `pay_l402_challenge` (in `pay-l402-anywhere`) or an L402 client library. |
| "No wallet configured", or the payment returns no preimage | No MCP wallet, or an OpenNode or Primal NWC wallet | Run `agent-wallet-setup` and connect NWC (Alby Hub, CoinOS, CLINK), LND, or Strike. |

## Safety rules

- **Free reads first, one paid trial last.** Searching, describing, quoting,
  and reading manifests never pay. Pay only after the human picked a
  candidate and said yes to its all-in price, within the user's cap.
- **At most one trial purchase per run,** unless the user explicitly asks for
  more. Never fan out paid calls across several services to compare them,
  and never buy a second candidate after a paid failure without asking.
- **One payment at a time.** Finish one 402, pay, access cycle, or one `buy`,
  before starting another. Before any retry, check `get_order` or `orders` on
  the Amazap path, or `receipts(source="session")` on the direct path. A
  pending or unclear payment is never replaced by a second one.
- **The right cap for the right wallet.** An Amazap buy spends Amazap credits
  under the user's cap, passed as `max_total_sats`, and the Amazap account
  limits. A direct payment spends the MCP wallet under the user's cap and the
  MCP budget. The MCP budget never bounds an Amazap buy. A top-up paid from
  the MCP wallet is its own `pay_invoice` payment: the human chooses the
  amount and says yes to it, the user's cap doesn't cover it, and the MCP
  `budget` limits do. Never raise a limit.
- **No direct-pay steer.** Never steer a buyer away from Amazap's all-in price
  toward direct payment of a listing Amazap surfaced. Never offer an Amazap
  listing's `endpointUrl` as a cheaper way to pay. Direct payment is for a
  URL the user already has.
- **Sensitive input stays with the user** unless they explicitly approved
  sending it. That covers secrets, private URLs, authenticated pages,
  credentials, personal data, or proprietary content.
- **Never claim a result the call did not return,** and say when a response
  was truncated. Say when nothing matched or nothing is affordable, instead
  of stretching a weak match.
- **Never echo secrets.** Never print invoices, preimages, macaroons, OAuth
  tokens, NWC strings, wallet credentials, or full payment authorization
  headers. The `l402Token` holds the preimage, so it stays out too.
- **A listing is not an endorsement.** Report a trust label as the source gave
  it, not what you assume about the seller.

## What this is NOT

- **Not custody.** Lightning Enable does not hold funds; the payment provider
  facilitates custody and settlement.
- **Not Amazap.** This skill reads Amazap's public API and drives Amazap's own
  tools when the host lists them. It doesn't set Amazap's prices, fees,
  credits, terms, or ranking.
- **Not a subscription.** Each trial is a single purchase, and the human
  approves it.
- **Not a review service.** You report the listing, its trust signals, and what
  one call returned. You don't vouch for the seller.
- **Not wallet setup.** If no wallet is connected, use
  [`agent-wallet-setup`](../agent-wallet-setup/) first.

## Example

The names are placeholders, and the sats figures are illustrative, not
Amazap terms.

> User: "Find me a weather API and try one forecast for Berlin. Spend at most
> 30 sats."
>
> 1. The host lists Amazap's tools. `budget(action="status")` shows 480 sats
>    left this session and `get_balance()` shows 4,700 sats, for the direct
>    path only. Amazap's `balance` shows enough credits and the account's
>    current limits.
> 2. `discover_api(query="weather forecast")` returns two registry results.
>    `search_catalog` with "weather forecast" returns three Amazap rows.
> 3. Five candidates, each labeled "Lightning Enable registry" or "Amazap".
>    Recommended: `fixture-string-forecast` from `fixture-string-provider-a`
>    on Amazap, because its `trust.label` reads "Verified: delivered 6 times"
>    with 0 paid failures and a high-confidence schema. The human picks it.
> 4. Its inputs are `latitude` and `longitude`: nothing sensitive. Amazap and
>    the seller receive them.
> 5. The quote is 13 sats all-in, paid from Amazap credits, within the 30-sat
>    cap and the Amazap account limits.
> 6. "I will buy one call to `fixture-string-forecast` from Amazap for 13 sats
>    all-in, paid from Amazap credits, within your 30-sat cap. Amazap and the
>    seller receive your latitude and longitude. Buying through Amazap means
>    accepting its current terms (https://amazap.com/terms and
>    https://amazap.com/credits). Do you accept them and go ahead?" The human
>    says yes. `buy` with the quote's `quote_id` and `total_cost`,
>    `max_total_sats=30`, and `accept_terms` set on that yes delivers the
>    forecast.
> 7. "You asked for tomorrow's forecast for Berlin: a high of 14 °C and light
>    rain. Charged 13 sats all-in from Amazap credits; the receipt's
>    `balanceAfterSats` shows the credits left. Source: Amazap, listing
>    `fixture-string-forecast` from `fixture-string-provider-a`, the order id
>    `<order id>`. Fulfilled." Then offer `report_outcome`.
>
> Had the quote been 31 sats, step 5 would have refused and bought nothing.
> Had the human picked a Lightning Enable registry result instead, the direct
> path would pay it from the MCP wallet with
> `access_l402_resource(url="<endpoint url>", max_sats=<the listed price>)`,
> within the 30-sat cap and the MCP budget.
