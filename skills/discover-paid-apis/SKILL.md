---
name: discover-paid-apis
description: >-
  Use when the user needs to find, compare, and optionally try a paid API or
  digital service. Search the Lightning Enable registry, and Amazap as an
  additional source; label each source, explain the two ways to buy (direct
  L402 from the user's wallet, or Amazap credits), show current price and the
  signals each source reports, then make at most one bounded trial purchase
  with approval. Use when the user has no URL yet ("find me a weather /
  finance / health API I can pay for", "what paid APIs are out there", "is
  there an L402 API for X", "search Amazap for X", "try a paid API"). Do NOT
  use to pay a URL the user already has (use pay-l402-anywhere), to answer a
  research question with cited paid data (use cited-answer), to sell or list
  an API (use producer-setup or create-l402-proxy), or to connect a wallet
  from nothing (use agent-wallet-setup).
---

# Discover paid APIs

Find something worth paying for, see what it costs before spending anything,
and try it once. You search the Lightning Enable registry first, and Amazap as
an additional source, and label every row with the one it came from:

- **The Lightning Enable registry,** searched with `discover_api`. Each
  listing points at an L402 manifest with the endpoints and their prices. A
  registry result is paid directly over L402 from the Lightning Enable MCP
  wallet.
- **Amazap** ([amazap.com](https://amazap.com)), a separate marketplace where
  agents search a catalog of pay-per-call APIs and digital services and buy
  calls with prepaid Amazap credits. Amazap does not replace the Lightning
  Enable registry; it is an additional source, and the user can leave it out.

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
[Amazap reference](https://github.com/refined-element/lightning-enable-skills/blob/587a7b7f5e867cde0bf3a0bc2a65bfbce48c42a0/references/amazap-marketplace.md#discovery-versus-purchase),
with its
[two-wallet rule](https://github.com/refined-element/lightning-enable-skills/blob/587a7b7f5e867cde0bf3a0bc2a65bfbce48c42a0/references/amazap-marketplace.md#two-wallets).

## Two ways to buy

Before any purchase, tell the human how each candidate would be bought. The
two paths are separate payment systems, and the human makes the final choice.

- **Direct L402, for a Lightning Enable registry result.** It pays from the
  user's own connected Lightning wallet through the Lightning Enable MCP: the
  invoice amount goes from that wallet to the API's seller, and any Lightning
  routing fee is paid by the user's wallet on top. The payment is direct
  L402: the preimage the payment returns is the proof that unlocks access.
  Lightning Enable's spending controls apply: the MCP `budget` caps and its
  confirmation codes. It needs no Amazap account and no Amazap credits.
- **Amazap, for an Amazap listing.** It buys through Amazap's MCP with
  prepaid Amazap credits, at Amazap's all-in price, under the current Amazap
  terms and Amazap's account limits. Amazap adds marketplace discovery, trust
  indicators such as `trust.label` and a paid track record, and its own
  purchasing features, such as re-crediting a failed paid call as Amazap
  credits.

Neither path's limits govern the other: the MCP `budget` never bounds an
Amazap buy, and Amazap's limits never bound a direct payment.

## What is automated, and what is not

**Automated:** checking which tools the host lists, reading the MCP budget and
balance, searching both sources, the comparison, reading a manifest or a
listing's input schema without paying, the quote, the one trial purchase, and
the receipt.

**Not automated. The human decides these:**

- **What to look for:** the outcome they need, not just a category.
- **Which candidate to try,** from the comparison you present.
- **Whether to pay,** at the moment of payment, with the quoted price and the
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
  - `receipts`: `source="session"` lists this session's payments, with no
    payment hash; `source="durable"` returns the wallet's receipt of a
    payment, with its `paymentHash`.
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
2. **The user's cap:** the most one trial may cost, in sats, checked against
   the quoted price (step 5), and whether a paid trial is authorized at all.
3. **Restrictions:** providers to avoid, and any limits on data handling,
   jurisdiction, or content.

Use obvious defaults when the risk is low. Ask only when the answer changes
what gets bought or what data leaves. Searching, describing, and quoting never
spend, so steps 1 to 5 need no yes. Step 6 pays, and needs its own yes.

### 1. Check the tools and the MCP leash

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
- **Which tools does the host list?** Note whether Amazap's tools are present.
  If they aren't, say so plainly: Amazap search uses the public products API,
  and an Amazap buy needs Amazap's MCP (https://amazap.com/mcp). Never claim
  Amazap MCP access you don't have.
- **Amazap credits, when Amazap's tools are listed:** `balance` or
  `spend_summary` returns the remaining Amazap credits and the account's
  current limits. Read them; don't assume them.

### 2. Search both sources

Search the Lightning Enable registry first. Amazap does not replace the
Lightning Enable registry; search it too, as an additional source, unless the
user asked to leave it out. Put the outcome in the search terms. Run at least
one refinement when the first results are empty, too broad, or mostly
irrelevant. Searching never spends.

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
each result carries Amazap's all-in price, a quote, and a ready-to-use buy
call.
Do not run that buy call; `buy` waits for the trial step and the human's yes.

**Amazap, without its MCP.** Use the read-only public products API:

```
GET https://amazap.com/api/products?q=weather&limit=50&offset=0
```

Fetch it with a plain HTTP GET (the host's fetch tool), never with
`access_l402_resource`: that tool pays any 402 it meets, and searching never
spends.

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
  payment is for a Lightning Enable registry result or a URL the user already
  has. This rule covers listings Amazap surfaced; it never applies to a result
  the Lightning Enable registry returned, which is its own candidate with its
  own price.

### 3. Compare at most five candidates

Show at most five candidates, one row each:

| Source | Product and provider | Protocol and rail | Quoted price | Inputs | Signals | Buyable now | Wallet |
|---|---|---|---|---|---|---|---|

- **Quoted price** (step 5 defines it for each path). For an Amazap row, show
  `totalSats`, the all-in figure the buyer pays, with `priceSats` (the seller
  price) and `feeBps` beside it. Never add `priceSats` and the fee yourself;
  Amazap's all-in total can differ from that sum. For a registry row, show
  `default_price_sats`, the invoice amount, or "see the manifest" when there
  is none. When neither source gives a fixed price, write "quote required".
- **Inputs.** For an Amazap row, list `inputSchema.fields[]` (each field's
  `name`, `type`, `required`, and `in`: `body`, `query`, or `path`) with
  `schemaConfidence`. For a registry row, step 4 reads them from the manifest.
- **Signals, exactly as each source reports them.** For a registry row, show
  `default_price_sats`, `endpoint_count`, the `manifest_url`, the OpenAPI URL
  when the row is a Lightning Enable proxy (`<proxy_base_url>/openapi.json`),
  and the affordability below. For an Amazap row, show `trust.label`,
  `healthStatus`, and `listingState`, and the paid record (`paidSuccesses`,
  `paidFailures`, `lastPaidSuccessAt`) when present. Quote `trust.label` as
  returned. For example, it may start with Verified, Working, Limited track
  record, or Having trouble, and add detail; those are observed values, not a
  fixed list. Never upgrade a label. A signal one source doesn't report reads
  "not reported by this source", which is neutral, never a warning.
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
- **Unknown values.** Write "not reported by this source" when a source
  doesn't report a value; never fill a cell with a guess.

Before the human picks, say which way each candidate is bought (see
[Two ways to buy](#two-ways-to-buy)). Recommend one candidate, with a
one-sentence reason drawn from the rows: fit to the outcome, a clear
specification, and the signals its own source reports. Prefer a reliable,
clearly specified service over the cheapest. Never rank a row up or down for
its source, and never drop a row to favor the other source. When the same
service is in both sources, show both rows with their own prices and their
own way to buy; recommend the service, not one of its two rows, and leave the
choice between the rows to the human. A price difference between the two rows
is never a reason to pick one of them. Never mention a listing's
`endpointUrl` as a way to pay the seller directly.

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
`GET https://amazap.com/api/products/<idOrSlug>` with the same plain HTTP GET
as in step 2, never with `access_l402_resource`. Fill each required field in
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
- **Show the quoted price in sats.** The quoted price is the figure the
  user's cap is checked against, and it differs by path. For an Amazap row, it
  is Amazap's all-in total (`totalSats`), paid in Amazap credits. For a
  registry result, it is the invoice amount, which is what the user's cap and
  the MCP budget count; any Lightning routing fee is paid on top, within the
  wallet's fee limit.
- **Say who receives the input,** as in step 3.

State which cap applies to which path before any purchase.

| Path | Wallet | Caps that apply |
|---|---|---|
| Amazap `buy` | Prepaid Amazap credits, added with `top_up` | The user's cap, checked against the quoted total before the yes, and the Amazap account limits; `max_total_sats` is set to the quoted total |
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

**Over the cap, refuse.** If the quoted price is above the lowest cap that
applies to its path, refuse and buy nothing; say the price and the cap. A
31-sat quote against a 30-sat cap is a refusal, not a negotiation.

Search, describe, and quote never spend.

### 6. Buy one trial

At most one trial purchase per run, unless the user explicitly asks for more.

Buy only when every item holds:

- the user authorized a paid trial, or an existing policy explicitly permits
  it;
- the quoted price is within the lowest cap that applies to its path;
- the input passed the check in step 4;
- the quote is fresh and matches the final parameters;
- the service is buyable: `buyable: true` on an Amazap row, which is also
  neither paused (`listingState`) nor degraded or failing (`healthStatus`);
- any required human confirmation is complete.

A paused or degraded row stays unbought this run, even with `buyable: true`,
and so does a failing one. Step 2 shows such a row; it is not a candidate to
buy.

State the purchase and **stop for a yes**, in the words of its path:

- **An Amazap buy:** "I will buy one call to `<listing>` from Amazap for
  `<total>` sats all-in, paid from Amazap credits, within your `<cap>`-sat
  cap. `<who>` receives your input. Go ahead?" Amazap auto-approves small
  buys on its own side; this skill still asks the user first.
- **A direct payment:** "I will buy one call to `<listing>` from the
  Lightning Enable registry for `<price>` sats, the invoice amount, paid from
  your MCP wallet. Your `<cap>`-sat cap and the MCP budget count that invoice
  amount; any Lightning routing fee is paid on top, within the wallet's fee
  limit. The seller's endpoint receives your input. Go ahead?"

For an Amazap buy, the same yes also covers the current Amazap terms. Add:
"Buying through Amazap means accepting its current terms
(https://amazap.com/terms and https://amazap.com/credits). Do you accept
them and go ahead?" A bare "Go ahead?" is never consent to the terms, so
it never sets `accept_terms`.

**Through Amazap, with `buy`.** These rules hold on every Amazap buy. The
full mechanics, with retries, baskets, top-ups, and a row for each Amazap
`buy` error, are in
[Amazap marketplace: Buying through Amazap](https://github.com/refined-element/lightning-enable-skills/blob/587a7b7f5e867cde0bf3a0bc2a65bfbce48c42a0/references/amazap-marketplace.md#buying-through-amazap).

```
buy(<the listing and parameters from the quote>,
    quote_id="<quoteId from the current quote>",
    total_cost=<that quote's total>,
    max_total_sats=<that quote's total>,
    accept_terms=<only after the user agreed to the current Amazap terms>)
```

- Start from the buy call that `search_catalog`, `describe_sku`, or `quote`
  returned, and keep its listing and parameters. Pass `quote_id` and
  `total_cost` from the current quote, and set `max_total_sats` to the quoted
  total, not to the user's cap. The user's cap is checked against that total
  before the yes; `max_total_sats` then holds the buy to the exact total the
  user approved. That call arrives with `accept_terms` and `max_total_sats`
  already filled in; never send it as it came.
- Set `accept_terms` only after showing the current Amazap terms
  (https://amazap.com/terms and https://amazap.com/credits) and getting the
  user's agreement in the same yes as the purchase.
- **A stale quote.** When `buy` reports a stale quote, the stale attempt
  charged nothing. Show the fresh quote from the error, and check that its
  total is still within the user's cap. Show the current Amazap terms links
  again and get a new yes before buying on it. Never buy on the fresh quote
  automatically.
- **`approval_required`.** The total is above Amazap's auto-approve amount.
  Stop, and ask the person to confirm the exact quote in Amazap; nothing is
  charged until they do. Never re-quote or split the purchase to get around
  it. Once they say they approved it, the same `quote_id` can be bought once.
- **Before any retry,** check `get_order` or `orders` for whether the buy
  went through. Repeating a `quote_id` never charges twice.
- **Too few credits:** ask before `top_up`. The human chooses the amount and
  pays the invoice; a top-up paid from the MCP wallet follows the Safety
  rules below.

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
or `get_order` returns the order. For a direct payment, read the wallet's
receipt of the payment and what the MCP budget has left:

```
receipts(source="durable")
budget(action="status")
```

Pick the receipt written since step 6 for this URL and take its
`paymentHash`, `amountSats`, and `status`, and its `feeSats` when the receipt
reports one. `amountSats` is the invoice amount; `feeSats`, an optional
field, is the fee the wallet paid on top. The MCP stores the payment hash as
SHA-256 of the preimage, never the preimage itself, so a receipt holds no
credential. Read the payment hash only from `receipts(source="durable")`: the
session receipts carry no payment hash on either port.

Report:

- the requested outcome;
- the delivered result, faithfully: summarize it, quote its key figures, say
  when it was truncated, and never claim data the call did not return;
- the sats charged: for an Amazap buy, the all-in `chargedSats` from Amazap's
  receipt; for a direct payment, the invoice amount (`amountSats`) and, when
  the receipt reports a fee (`feeSats`), that fee beside it, never one
  combined figure;
- the remaining Amazap credits or the remaining MCP budget, whichever wallet
  paid, when available;
- the source, the provider, and the listing used;
- an order or receipt id safe to keep: the Amazap order id, or, for a direct
  payment, the `paymentHash` from `receipts(source="durable")`;
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
  publishes to the Lightning Enable registry.

## What can go wrong

| Symptom | Likely cause | Do this |
|---|---|---|
| `discover_api` returns no results | Nothing in the registry matches | Try one broader keyword or a category, then say so. Never invent an API. |
| Registry returned an error status or a redirect | The registry is down, or `L402_REGISTRY_URL` / `LIGHTNING_ENABLE_API_URL` points somewhere wrong | Report the `registry_url` from the response, and carry on with Amazap. |
| Amazap's products API or MCP is unreachable or errors | Amazap is down, or the host can't reach it | Report it, and carry on with the Lightning Enable registry. Never claim Amazap results you didn't get. |
| "Could not find an L402 manifest" with `tried_urls` | The site publishes no L402 manifest at the well-known paths | Show the human the paths tried. Without a manifest, the price is unknown; don't guess it. |
| `redirect_location` in a `discover_api(url=...)` result | The URL redirects, and the tool doesn't follow redirects | Call `discover_api` again with the redirect target, if the human agrees it is the same site. |
| A URL refused before any request | It resolves to a private or internal address | Deliberate SSRF (server-side request forgery) protection. Use a public URL. |
| `affordable_calls: "unknown"` | The price or the budget could not be determined | Treat it as not proven affordable. Read the manifest for the price; check `budget(action="status")`. |
| Amazap's tools aren't listed | Amazap's MCP isn't connected in this host | Search with `GET https://amazap.com/api/products`. For a buy, point the human at https://amazap.com/mcp. Never claim Amazap MCP access. |
| An Amazap row shows `buyable: false` | The listing isn't payable now | Show it, unless it has `hidden: true`; a hidden row is dropped. Never buy it. |
| An Amazap row is paused, degraded, or failing | `listingState` or `healthStatus` says so | Show it as not buyable, and never buy it, even with `buyable: true`. |
| `buy` reports a stale quote, `approval_required`, `terms_required`, `not_yet_supported`, or an Amazap account limit; too few credits; or a paid Amazap call failed | An Amazap buy outcome | Follow the row for that outcome in [Amazap marketplace: Buying through Amazap](https://github.com/refined-element/lightning-enable-skills/blob/587a7b7f5e867cde0bf3a0bc2a65bfbce48c42a0/references/amazap-marketplace.md#buying-through-amazap). Never buy on an old yes, never work around `approval_required`, and never buy a replacement without asking. |
| The user already has the URL | Nothing to discover | Hand off to `pay-l402-anywhere`. That handoff is for a URL the user already has, never for a listing Amazap surfaced. |
| The input holds something sensitive | Secrets, a private or logged-in URL, credentials, personal data, or proprietary content | Don't send it unless the user explicitly approved that disclosure. Say what you found, and buy nothing. |
| No fresh quote, or it doesn't match the parameters | Quote failure | Nothing was charged. Never buy on an old or mismatched quote. Quote again, or pick another candidate with the user. |
| The quoted price is above the user's cap | Policy refusal | Refuse and buy nothing; say the price and the cap. Never raise the cap or split the purchase to fit under it. |
| A budget denial on the direct path | Policy refusal: a per-payment or per-session cap on the MCP wallet | Report the limit the error names. Don't retry with a smaller `max_sats` to squeeze under it. Only the human changes the config file. |
| Payments refused while no BTC price is available | USD limits on the MCP wallet can't be checked during a price outage | Expected on the direct path: USD limits fail closed. When the operator set sats-denominated limits, small payments may keep working during a price outage. |
| `requiresConfirmation: true` | The amount is above the MCP auto-approve tier | Ask the human for the code, then repeat the same call with `confirmation_nonce`. Never guess a code. |
| The invoice costs more than `max_sats` | The seller raised the price since the listing | Nothing was paid. Tell the human the real price, and ask again only if it is within the user's cap; never above the user's cap. Never guess a price. |
| The payment didn't go through | Payment failure: a wallet, route, or invoice error | Report it, and check the outcome before any retry. Never retry with a smaller cap or `max_sats` to squeeze under a limit. |
| The outcome of a buy or a payment is unclear | A dropped connection or a timeout | Check before any retry: `get_order` or `orders` on the Amazap path, `receipts(source="session")` on the direct path. A pending or unclear payment is never replaced by a second one. |
| `alreadyPaid: true` | Provider failure after a direct payment: paid, then the endpoint errored or redirected | Do not pay again or call the URL again. Report the sats paid and the error. |
| The result doesn't match the listing | A malformed result, after payment | Report it as a malformed result, and quote what came back; never claim data it lacks. On Amazap, offer `report_sku` with the user's approval. Don't buy or pay again without asking. |
| The user, or the person approving in Amazap, says no | User-declined approval | Stop. Nothing was charged. Report that nothing was bought. |
| `access_l402_resource` refuses the method | The endpoint needs POST or another non-read method | Outside the direct path. Point the human at `pay_l402_challenge` (in `pay-l402-anywhere`) or an L402 client library. |
| "No wallet configured", or the payment returns no preimage | No MCP wallet, or an OpenNode or Primal NWC wallet | Run `agent-wallet-setup` and connect NWC (Alby Hub, CoinOS, CLINK), LND, or Strike. |

## Safety rules

- **Free reads first, one paid trial last.** Searching, describing, quoting,
  and reading manifests never pay. Pay only after the human picked a
  candidate and said yes to its quoted price, within the user's cap.
- **At most one trial purchase per run,** unless the user explicitly asks for
  more. Never fan out paid calls across several services to compare them,
  and never buy a second candidate after a paid failure without asking.
- **One payment at a time.** Finish one 402, pay, access cycle, or one `buy`,
  before starting another. Before any retry, check `get_order` or `orders` on
  the Amazap path, or `receipts(source="session")` on the direct path. A
  pending or unclear payment is never replaced by a second one.
- **The right cap for the right wallet.** An Amazap buy spends Amazap credits
  under the user's cap, checked before the yes, and the Amazap account
  limits, with `max_total_sats` set to the quoted total. A direct payment
  spends the MCP wallet under the user's cap and the MCP budget. The MCP
  budget never bounds an Amazap buy. Pay a top-up from the MCP wallet only
  when the human explicitly asks to pay it from the MCP wallet. Then it is
  its own `pay_invoice` payment: the human chooses the amount and says yes to
  it, the user's cap doesn't cover it, and the MCP `budget` limits do. Never
  raise a limit.
- **No direct-pay steer.** Never steer a buyer away from Amazap's all-in price
  toward direct payment of a listing Amazap surfaced. Never offer an Amazap
  listing's `endpointUrl` as a cheaper way to pay. Direct payment is for a
  Lightning Enable registry result or a URL the user already has. This rule
  covers listings Amazap surfaced; it never applies to a result the Lightning
  Enable registry returned.
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

The names, the trust label, and the sats figures are illustrative, not
registry or Amazap data.

> User: "Find me a weather API and try one forecast for Berlin. Spend at most
> 30 sats."
>
> 1. `budget(action="status")` shows 480 sats left this session and
>    `get_balance()` shows 4,700 sats, for the direct path only. The host also
>    lists Amazap's tools; Amazap's `balance` shows enough credits and the
>    account's current limits.
> 2. `discover_api(query="weather forecast")` returns two registry results.
>    `search_catalog` with "weather forecast" returns three Amazap rows.
> 3. Five candidates, each labeled "Lightning Enable registry" or "Amazap",
>    and each with its way to buy: direct L402 from the MCP wallet, or Amazap
>    credits. Recommended: `example-weather` from the registry, because it
>    fits the request most directly: its listing describes a forecast by city
>    name, which matches "Berlin", and the budget covers 48 calls at its
>    10-sat default price. Its trust label reads "not reported by this
>    source". The trade-off: picking it gives up the delivery track record
>    the Amazap row `fixture-string-forecast` reports, "Verified: delivered 6
>    times", and that row takes latitude and longitude instead of a city.
>    Either fits; the human picks `example-weather`.
> 4. `discover_api(url="<manifest_url>")` shows `GET /forecast` at 10 sats,
>    taking `city`: nothing sensitive. The seller's endpoint receives it.
> 5. The manifest price is the quote: 10 sats, paid from the MCP wallet,
>    within the 30-sat cap and the MCP budget.
> 6. "I will buy one call to `example-weather` from the Lightning Enable
>    registry for 10 sats, the invoice amount, paid from your MCP wallet. Your
>    30-sat cap and the MCP budget count that invoice amount; any Lightning
>    routing fee is paid on top, within the wallet's fee limit. The seller's
>    endpoint receives your city. Go ahead?" The human says yes.
>    `access_l402_resource(url="<endpoint url>", max_sats=<the listed price>)`
>    pays 10 sats and returns the forecast.
> 7. `receipts(source="durable")` gives the payment's `paymentHash`. "You
>    asked for tomorrow's forecast for Berlin: a high of 14 °C and light rain.
>    Charged 10 sats from your MCP wallet; `budget(action="status")` shows
>    what's left. Source: Lightning Enable registry, listing
>    `example-weather`, payment hash `<payment hash>`. Fulfilled."
>
> Had the quote been 31 sats, step 5 would have refused and bought nothing.
> Had the human picked the Amazap row `fixture-string-forecast` from
> `fixture-string-provider-a` instead, the Amazap path would run. Its
> `trust.label` reads "Verified: delivered 6 times". The row shows
> `buyable: true` and is neither paused, degraded, nor failing. Its inputs are
> `latitude` and `longitude`, which Amazap and the seller receive. The quote
> is 13 sats all-in, paid from Amazap credits, within the 30-sat cap and the
> Amazap account limits. The yes would be: "I will buy one call to
> `fixture-string-forecast` from Amazap for 13 sats all-in, paid from Amazap
> credits, within your 30-sat cap. Amazap and the seller receive your
> latitude and longitude. Buying through Amazap means accepting its current
> terms (https://amazap.com/terms and https://amazap.com/credits). Do you
> accept them and go ahead?" On that yes, `buy` with the quote's `quote_id`
> and `total_cost`, `max_total_sats=13`, and `accept_terms` set on that yes
> delivers the forecast; the receipt's `balanceAfterSats` shows the credits
> left, and the order id `<order id>` identifies the purchase.
