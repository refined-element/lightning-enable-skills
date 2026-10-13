# Amazap marketplace

Shared rules for every skill in this repository that touches
[Amazap](https://amazap.com), a storefront and remote MCP where agents search
a catalog of pay-per-call APIs and digital services and buy calls over
Lightning. Sellers can list a public L402 endpoint there as an extra
distribution channel.

Amazap is optional. A seller can use Lightning Enable without it, and a buyer
can pay a known L402 URL directly with
[`pay-l402-anywhere`](../skills/pay-l402-anywhere/). Lightning Enable and
Amazap are separate products: Lightning Enable helps a developer create, price,
test, and run an L402 endpoint; Amazap helps agents find and buy listed
endpoints. Describe the relationship as collaboration or ecosystem support.
Never claim a partnership or any other commercial relationship among any of
Lightning Enable, Amazap, or Amboss.

## Amazap facts are external

Everything below about Amazap describes another company's live product. Its
prices, margin, limits, terms, and catalog change without notice. Say "current
Amazap seller terms" or "current Amazap quote", link the live page, and fetch
any figure you need instead of quoting one from this note. The dated
observations near the end are a snapshot, not a rule.

## Live pages

| What | Where |
|---|---|
| Seller flow: the listing form and the seller terms | https://amazap.com/sell |
| Seller listing guide | https://amazap.com/sell/guide/list-l402-endpoint-on-amazap |
| Agent documentation, including the current margin and limits | https://amazap.com/llms.txt |
| Product search API | `GET https://amazap.com/api/products` |
| One product, including a hidden one | `GET https://amazap.com/api/products/<slug>` |
| Product pages | `https://amazap.com/p/<slug>` |
| Every product page | https://amazap.com/sitemap.xml |
| Remote MCP | https://amazap.com/mcp |

## Discovery versus purchase

- **Discovery is read-only.** Amazap's `search_catalog` MCP tool, or
  `GET https://amazap.com/api/products?q=<terms>` paged with `limit` and
  `offset` until `offset >= total`, finds listings and spends nothing. Fetch
  the API with a plain HTTP GET, never with `access_l402_resource`. A
  search result may include paused, degraded, or failing rows. Paused,
  degraded, or failing rows are shown, not bought; read `listingState`,
  `healthStatus`, and `buyable` on every row. A row can also be hidden from
  search and still be returned by `GET https://amazap.com/api/products/<slug>`, with
  `hidden: true`. That detail response wraps the row in `product`.
- **Purchase spends Amazap credits.** Amazap's own `quote` and `buy` tools buy
  a listing; Lightning Enable's tools don't.
  [`discover-paid-apis`](../skills/discover-paid-apis/) holds the full buyer
  flow; the rules below apply to every Amazap buy.
- **Name an Amazap tool only when the host lists it.** Amazap's tools
  (`search_catalog`, `list_my_endpoint`, and the rest) exist only when the
  person has connected Amazap's MCP. Without them, use the public pages and API
  above, and never claim Amazap MCP access you don't have.

Every Amazap buy follows these rules:

- **Two sources, labeled.** Amazap does not replace the Lightning Enable
  registry. A buyer skill searches both and labels every row with its source.
- **Spending.** Search, describe, and quote never spend. `buy` is the only
  call that spends Amazap credits.
- **The all-in price is the price.** Show `totalSats`, the figure the buyer
  pays, with `priceSats` (the seller price) and `feeBps` beside it.
  Read `feeBps` from the row, and never add the seller price and the fee
  yourself; the all-in total can differ from that sum.
- **Trust as reported.** Read `trust.label` and the paid track record
  (`paidSuccesses`, `paidFailures`, `lastPaidSuccessAt`). A row imported from
  a directory such as 402 Index is a directory entry, not a record of Amazap
  delivering it.
- **Hidden rows.** A hidden row is not a candidate; never fetch one by slug
  to show or buy it.
- **No direct-pay steer.** Never steer a buyer away from Amazap's all-in price
  toward direct payment of a listing Amazap surfaced. Amazap's margin funds
  its failed-call credits, so never present a listing's `endpointUrl` as a
  cheaper way to pay the seller. When the same service appears in both
  sources, show each row as its source returned it. Direct payment through
  `pay-l402-anywhere` is for a URL the user already has.
- **The `buy` contract.** `buy` requires `quote_id`, `total_cost`,
  `max_total_sats`, and `accept_terms`. Check the quoted total against the
  user's cap before the yes, set `max_total_sats` to the quoted total, and
  set `accept_terms` only after the user has agreed to the current Amazap
  terms (https://amazap.com/terms and https://amazap.com/credits). A stale
  quote returns a fresh quote in the error and charges nothing; show the
  fresh total with the current Amazap terms links again, and get a new yes
  before buying. Repeating a `quote_id` never charges twice. A basket is one
  buy. Above Amazap's auto-approve amount the person confirms, or `buy`
  returns `approval_required`; stop there and never work around it.
- **Failed paid calls.** Amazap re-credits a failed paid call as Amazap
  credits, never cash: automatically, or through `claim_failed_call` within
  the window Amazap states (see https://amazap.com/credits). After a
  delivered call, `report_outcome` is optional.
- **Sensitive input.** Never send secrets, private URLs, authenticated pages,
  credentials, personal data, or proprietary content as a purchase input
  unless the user explicitly approved that disclosure.
- **One trial.** At most one trial purchase per run unless the user
  explicitly asks for more, and never a second candidate after a paid failure
  without asking.

## Two wallets

An Amazap `buy` spends prepaid Amazap credits, which the buyer adds with
Amazap's `top_up` tool, under Amazap's account limits. A direct L402 payment
spends the Lightning Enable MCP wallet, under the MCP's `budget` limits. The
two never bound each other: `budget` and `get_balance` don't see Amazap
credits, and Amazap's limits don't apply to the MCP wallet.

| Path | Wallet | Caps that apply |
|---|---|---|
| Amazap `buy` | Prepaid Amazap credits, added with `top_up` | The user's cap, checked against the quoted total before the yes, and the Amazap account limits; `max_total_sats` is set to the quoted total |
| A Lightning Enable registry result, or a URL the user already has, paid directly (`access_l402_resource`) | The Lightning Enable MCP wallet | The user's cap and the MCP `budget` limits |

State which cap applies to which path before any purchase. Never present
`budget` status or `get_balance` as bounding an Amazap buy. Amazap's own
`balance` and `spend_summary` tools, when the host lists them, report the
remaining credits and the account's current limits; read them there each
time. `top_up` creates a Lightning invoice for the human to pay and moves no
sats itself. A buy at or under Amazap's auto-approve amount needs no
confirmation on Amazap's side; a buyer skill still asks the user before its
one trial.

## Merchant of record and the all-in price

Amazap is currently the merchant of record for purchases made through its
storefront: it buys each call from the seller and sets the shopper's all-in
price. One listing has two prices:

- the **seller price**, the amount on the seller's own invoice; and
- the **all-in shopper price**, which Amazap sets and shows on its draft, its
  product page, and its quotes.

Present them separately. Never add a margin to the seller price yourself, and
never present one number as both. The all-in figure comes from Amazap's own
draft or page. Lightning Enable is not responsible for Amazap's pricing,
margin, credits, terms, or ranking.

## Verification terminology

Use the six classifications in
[L402 verification levels](l402-verification-levels.md) exactly. For a
listing:

- `CHALLENGE_COMPATIBLE` means "challenge-compatible, fulfillment unverified".
  A `402` is a quote, not proof that anything gets delivered.
- `FULFILLMENT_VERIFIED` is the minimum for calling an endpoint ready to list.
- `MARKETPLACE_READY` is the target only for an endpoint on its own host. A
  Lightning Enable proxy on `api.lightningenable.com` stops at
  `FULFILLMENT_VERIFIED` (see Prefill under Seller handoff).
- **Listed** means Amazap's product page or products API row has been read
  back and shows the listing as visible: the row has `hidden: false`, or the
  product page renders the listing as buyable. Otherwise report the row's
  state (`hidden`, `listingState`, `healthStatus`), not "listed".
  **Verified paid delivery** means a paid call
  through the listing returned the promised result. One doesn't imply the
  other.

## Seller handoff

The seller skills ([`producer-setup`](../skills/producer-setup/),
[`create-l402-proxy`](../skills/create-l402-proxy/), and
[`l402-server-integration`](../skills/l402-server-integration/)) end with an
optional step that offers an Amazap listing. These are its full rules.

### Readiness gate

Don't offer the listing as ready until every item passes:

1. The endpoint is public HTTPS. A private, loopback, link-local, or
   non-HTTPS URL is not listing-ready.
2. An unpaid request returns `402 Payment Required`. A `200` to an unpaid
   request means the resource isn't gated; fix that first.
3. `WWW-Authenticate` carries an `L402` or `LSAT` challenge with a priced
   BOLT11 invoice. Other schemes beside it are fine.
4. The HTTP method and the resource path are the ones you will list.
5. An unpaid request with that method and no body gets the `402` within
   8 seconds. That is what Amazap's listing probe sends: one call, the listed
   method, no body, no `HEAD`. A `400`, `415`, or `422` before the `402` fails
   the probe, so the route can't be listed as it is. A cart checkout that
   validates its body first is the usual example.
6. The required request parameters, and a safe example value for each, are
   known.
7. A paid retry has been tested with one bounded real payment and returned a
   `2xx` with the promised content.
8. Replay behavior is understood: how long a paid token stays valid, and
   whether a second request with it is served.
9. Neither errors nor output expose secrets.
10. The human has chosen the public title, description, category, and price.

Run [`l402-compatibility-report`](../skills/l402-compatibility-report/) for the
protocol items. Its read-only check
(`python scripts/l402_check.py <url> --max-sats <cap> --json --output mode-a.json`
from that skill's folder, with the human's cap in sats, adding
`--method POST` for a `POST` route) covers items 1 to 5 and saves the report
its paid check reads; its paid check covers item 7. `--max-sats` is required
here: the paid check runs only when that report's preflight says `allowed`.
If `l402-compatibility-report` is not installed, the listing is not ready;
give the human its GitHub URL,
https://github.com/refined-element/lightning-enable-skills/tree/main/skills/l402-compatibility-report.
Take the `classification` field from the JSON report, which is the script's
contract (`report_version` 1), not from the Markdown:

- **`INCOMPATIBLE`:** not listing-ready. Give the fix the report names.
- **`CHALLENGE_COMPATIBLE`:** the most the read-only check can return for a
  correct endpoint. Say "challenge-compatible, fulfillment unverified", and do
  not offer the listing as ready until the paid check below lifts it.
- **`PAYMENT_COMPATIBLE` or `INCONCLUSIVE`:** paid delivery wasn't proven, so
  the listing isn't ready.
- **`FULFILLMENT_VERIFIED`:** ready, once items 6, 8, 9, and 10 hold. Pass on
  the report's `paid_fulfillment.hash_source`: for an opaque token the
  preimage was matched against the wallet's recorded payment, not the invoice.
- **`MARKETPLACE_READY`:** the target for an endpoint on its own host. The
  same remaining items apply. On `api.lightningenable.com`, the host-root
  metadata check doesn't count for a proxy (see Prefill below), so report such
  a proxy as
  `FULFILLMENT_VERIFIED` at most, never as `MARKETPLACE_READY` on the strength
  of that check.

Three limits of the paid check:

- It runs on `GET` or `HEAD` only, because `access_l402_resource` sends
  nothing else. A `POST` route stops at `CHALLENGE_COMPATIBLE` through these
  skills, so it isn't offered as ready.
- It needs the credential. `FULFILLMENT_VERIFIED` and `PAYMENT_COMPATIBLE`
  both require the paid call's token piped to the script on stdin (step 7 of
  `l402-compatibility-report`). Without it the paid check ends `INCONCLUSIVE`
  with `preimage_unchecked`, and a wallet receipt never upgrades that. The
  Python MCP server returns the token only on the `alreadyPaid` path, which is
  `INCONCLUSIVE` anyway, so a paid check through it doesn't unlock the listing
  either.
- Pay once for the gate, never twice. If the self-test made no payment for
  this endpoint by any means (a testnet invoice doesn't count), run the
  compatibility report's paid check once,
  with the human's yes; otherwise the cases below apply and the agent never
  pays again. The paid check needs a wallet that can pay this
  endpoint: if the self-test was skipped because the wallet refused to pay its
  own invoice, do not attempt the paid check with the same wallet, and the
  listing is not ready. If the self-test already paid this exact public URL,
  with the same method, through `access_l402_resource`, from either wallet
  (the seller's own or a second one), record that call as the evidence
  (steps 6 and 7 of `l402-compatibility-report`, with the
  read-only report above as `--mode-a` and that call's token piped on stdin)
  instead of paying again. If that token is gone, the listing is not ready; do
  not pay again. A self-test payment of a testnet invoice moved no real money
  for this endpoint, so it is neither reuse evidence nor a payment for the
  gate: once the endpoint quotes a mainnet invoice at the chosen price, run
  the paid check once, with the human's yes. A self-test that paid this URL with a different method also
  counts as paid; the listing is not ready; do not pay again. A payment
  through `pay_l402_challenge` counts as paid. The agent has no tool that
  fetches the resource with a token it already holds, and
  `access_l402_resource` would pay again, so in that run the gate stays at
  `CHALLENGE_COMPATIBLE`: the listing is not ready, and the agent does not pay
  again. A self-test payment made by hand, outside both tools, also counts
  as paid: the listing is not ready in that run, and the agent does not pay
  again. If the human wants the paid check later, they choose it in a later
  run, and the skill says plainly that it is a second payment for this
  endpoint.

### Handoff flow

1. Finish the seller skill through its self-test and its hand-off.
2. Check for an existing Amazap row. A published Lightning Enable endpoint can
   already be in Amazap's catalog, imported from 402 Index. Search by service
   name, `GET https://amazap.com/api/products?q=<service name>`, and page
   with `limit` and `offset` until `offset >= total` before you conclude
   there is no row; a host search returns every Lightning Enable proxy.
   Every Lightning Enable proxy shares `api.lightningenable.com`, so match
   the full endpoint URL the row stores (a per-route URL or the proxy's base
   URL), not the host alone. Search skips hidden rows, so when the human
   knows a slug, also read
   `GET https://amazap.com/api/products/<slug>`, and look for the service in
   https://amazap.com/sitemap.xml. If a row exists, report its `hidden`,
   `listingState`, and `healthStatus`, and let the human decide with Amazap
   whether to refresh it. Never draft a duplicate listing on your own.
3. Ask whether the human wants Amazap distribution, before any paid gate
   check, so no sats are spent on a listing they don't want. No answer means
   no.
4. If yes, run the readiness gate above.
5. When the gate passes, call Amazap's `list_my_endpoint` tool when the host
   lists it. It probes the endpoint and returns a draft and a link to the
   seller form; it is read-only and publishes nothing. Without the tool, give
   the human https://amazap.com/sell and a draft built from the listing-copy
   template below.
6. Present the draft beside the current Amazap seller terms, linked live, and
   the all-in shopper price from Amazap's own draft or page.
7. The human reviews the contact email, the listing copy, the current margin
   and all-in price, and the terms.
8. The human submits the listing. Submitting the form publishes the listing
   automatically once Amazap's checks pass, so the human reviews everything in
   step 7 before submitting.
9. Read the listing back (post-listing verification, below) before you report
   anything about it.

**Prefill.** Amazap prefills the title, description, category, and example
parameters from `openapi.json` or `llms.txt` at the root of the endpoint's
host. Without them, it derives example parameters from parameter names in the
402 body. A Lightning Enable proxy serves its own `openapi.json` and manifest
under `/l402/proxy/{proxyId}/`, which the root lookup doesn't read, and the
root of `api.lightningenable.com` describes Lightning Enable itself. On
`api.lightningenable.com`, the host-root `openapi.json` and `llms.txt`
describe the platform, not the proxy, so the host-root metadata check doesn't
count for a proxy. The handoff reports such a proxy as `FULFILLMENT_VERIFIED`
at most, even when the script's report says `MARKETPLACE_READY`, and never as
`MARKETPLACE_READY` on that basis. Tell the human to supply the title,
description, category, and example parameters by hand. For an API on its own
domain, an `openapi.json` or `llms.txt` at the host root gives the prefill
something accurate to read.

**Price lock.** Amazap reads the price from the probe's invoice and locks it at
listing time; each buy pays the live invoice only when it fits the stored
price. After any price change, the seller must re-run Amazap's checks on the
seller page, or buys stop fitting the stored price.

### Human approval boundary

You may, without asking: probe the endpoint, generate listing copy, call the
read-only `list_my_endpoint` tool when the host lists it, give the human the
draft and the seller URL, and open the seller page when the host can.

You must not, without the human's explicit approval:

- submit the listing;
- accept seller terms;
- provide or infer a contact email (Amazap requires one; the human enters it);
- opt into announcements;
- publish a Nostr handle;
- change the endpoint's price;
- claim a commercial relationship among any of Lightning Enable, Amazap, or
  Amboss.

### Listing-copy template

- **Name:** the outcome, specific ("Hourly forecast for one city"), not the
  technology.
- **Description:** the input supplied, the output returned, its freshness,
  material limits, and typical latency when the self-test measured it.
- **Category:** one narrow category.
- **Method and endpoint:** the exact public method and URL.
- **Example parameters:** a safe, working, non-secret example.
- **Price:** the seller price, the current invoice amount. Show Amazap's
  all-in shopper price on its own line, taken from Amazap's draft, never
  computed.
- **Failure behavior:** known timeouts, empty results, and unsupported inputs.
- **Avoid** "revolutionary", "autonomous", "instant", "real-time", and "any API" unless the self-test showed it.

### Post-listing verification

Never call an endpoint listed or live until you have read it back:

1. Read the product page (`https://amazap.com/p/<slug>`) or the public API row
   (`GET https://amazap.com/api/products/<slug>`).
2. Confirm the product name, provider, endpoint, displayed price, protocol,
   and `buyable`. Before you say "listed", the row's endpoint URL and
   displayed seller price must match this endpoint; otherwise report the row's
   state and that it may be an imported row, not this listing.
3. Check `hidden`, `listingState`, and `healthStatus`. A hidden or paused row
   isn't live, even though the single-product API still returns it.
4. Record the public URL for the human.
5. Make a paid marketplace purchase only when the human separately authorizes
   one. It spends Amazap credits, not the MCP wallet.
6. Report "listed" and "verified paid delivery" as two separate facts. A
   listing read back with no paid purchase through it counts as listed only.

## Observed on 2026-10-12

A snapshot, not a rule. Fetch the current values from the live pages before
you quote any of them.

- Amazap's `list_my_endpoint` description and https://amazap.com/llms.txt
  stated a 2,500 bps (25%) standard shopper margin with a 7-sat floor, while
  rows imported from 402 Index showed `feeBps` 2000.
- New Amazap accounts had limits of 500 sats per call, 2,000 sats per day, and
  1,000 sats per session, and buys of 50 sats or less auto-approved.
- The sitemap listed 1,423 product pages.
- `trust.short` read Verified, Working, Limited record, or Having trouble.
  `trust.label` began with Verified, Working, Limited track record, or Having
  trouble, and sometimes added detail ("Verified: delivered 6 times").
- Early in the day, some rows were absent from search and the detail
  endpoint returned them with `hidden: true`. Later the same day, search
  listed paused rows with `hidden: false` and `buyable: false`.
- Some rows had a `totalSats` above `priceSats` plus `feeSats`.
- The credit terms stated a 72-hour window for `claim_failed_call`.
- A listing marked Partial credit only re-credited less than the full price
  after a failed paid call.

## Custody

Lightning Enable does not hold funds; the payment provider facilitates custody
and settlement. Amazap credits are governed by Amazap's current terms.
