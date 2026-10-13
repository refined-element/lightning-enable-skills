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
Never claim a partnership or any other commercial relationship between
Lightning Enable, Amazap, and AMBOSS.

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
  `offset` until `offset >= total`, finds listings and spends nothing. Search
  leaves out rows whose health is failing and rows that are paused;
  `GET https://amazap.com/api/products/<slug>` still returns such a row, with
  `hidden: true`.
- **Purchase spends Amazap credits.** Amazap's own `quote` and `buy` tools buy
  a listing; Lightning Enable's tools don't. The buyer-side rules for that path
  belong with the buyer skill that adopts it.
- **Name an Amazap tool only when the host lists it.** Amazap's tools
  (`search_catalog`, `list_my_endpoint`, and the rest) exist only when the
  person has connected Amazap's MCP. Without them, use the public pages and API
  above, and never claim Amazap MCP access you don't have.

## Two wallets

An Amazap `buy` spends prepaid Amazap credits, which the buyer adds with
Amazap's `top_up` tool, under Amazap's account limits. A direct L402 payment
spends the Lightning Enable MCP wallet, under the MCP's `budget` limits. The
two never bound each other: `budget` and `get_balance` don't see Amazap
credits, and Amazap's limits don't apply to the MCP wallet.

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
- `MARKETPLACE_READY` is the target.
- **Listed** means Amazap's product page or products API row has been read
  back and shows the listing. **Verified paid delivery** means a paid call
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
(`python scripts/l402_check.py <url> --json --output mode-a.json` from that
skill's folder, adding `--method POST` for a `POST` route) covers items 1 to 5
and saves the report its paid check reads; its paid check covers item 7. Take
the `classification` field from the JSON report, which is the script's
contract (`report_version` 1), not from the Markdown:

- **`INCOMPATIBLE`:** not listing-ready. Give the fix the report names.
- **`CHALLENGE_COMPATIBLE`:** say "challenge-compatible, fulfillment
  unverified" and don't offer the listing as ready.
- **`PAYMENT_COMPATIBLE` or `INCONCLUSIVE`:** paid delivery wasn't proven, so
  the listing isn't ready.
- **`FULFILLMENT_VERIFIED`:** ready, once items 6, 8, 9, and 10 hold. Pass on
  the report's `paid_fulfillment.hash_source`: for an opaque token the
  preimage was matched against the wallet's recorded payment, not the invoice.
- **`MARKETPLACE_READY`:** the target. The same remaining items apply.

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
- Pay once for the gate, never twice. When the skill's own self-test already
  paid this exact public URL, with the same method, through
  `access_l402_resource`, record that call as the evidence (steps 6 and 7 of
  `l402-compatibility-report`, with the read-only report above as `--mode-a`
  and that call's token piped on stdin) instead of paying again. If that token
  is no longer at hand, the listing isn't ready; say so rather than paying a
  second time on your own. Otherwise, run that skill's paid check, which asks
  for its own yes.

### Handoff flow

1. Finish the seller skill through its self-test and its hand-off.
2. Run the readiness gate above.
3. Check for an existing Amazap row. A published Lightning Enable endpoint can
   already be in Amazap's catalog, imported from 402 Index. Search
   `GET https://amazap.com/api/products?q=<service name or host>`. Search
   skips hidden rows, so when the human knows a slug, also read
   `GET https://amazap.com/api/products/<slug>`, and look for the service in
   https://amazap.com/sitemap.xml. If a row exists, report its `hidden`,
   `listingState`, and `healthStatus`, and let the human decide with Amazap
   whether to refresh it. Never draft a duplicate listing on your own.
4. Ask whether the human wants Amazap distribution. No answer means no.
5. If yes, call Amazap's `list_my_endpoint` tool when the host lists it. It
   probes the endpoint and returns a draft and a link to the seller form; it
   is read-only and publishes nothing. Without the tool, give the human
   https://amazap.com/sell and a draft built from the listing-copy template
   below.
6. Present the draft beside the current Amazap seller terms, linked live, and
   the all-in shopper price from Amazap's own draft or page.
7. The human reviews the contact email, the listing copy, the current margin
   and all-in price, and the terms.
8. The human submits the listing.
9. Read the listing back (post-listing verification, below) before you report
   anything about it.

**Prefill.** Amazap prefills the title, description, category, and example
parameters from `openapi.json` or `llms.txt` at the root of the endpoint's
host. Without them, it derives example parameters from parameter names in the
402 body. A Lightning Enable proxy serves its own `openapi.json` and manifest
under `/l402/proxy/{proxyId}/`, which the root lookup doesn't read, and the
root of `api.lightningenable.com` describes Lightning Enable itself. So on
`api.lightningenable.com`, the human supplies the title, description,
category, and example parameters by hand. That platform `llms.txt` can also
make a host-root metadata check pass on the platform's text rather than the
proxy's. For an API on its own domain, an `openapi.json` or `llms.txt` at the
host root gives the prefill something accurate to read.

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
- claim a commercial relationship between Lightning Enable, Amazap, and AMBOSS.

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
   and `buyable`.
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
- Lightning Enable's rows on Amazap, imported from 402 Index, were failing and
  hidden earlier that day and had mostly recovered after Amazap's author fixed
  an issue on Amazap's side: 44 of 46 visible, 39 buyable, four paused after
  one paid failure each, and one still failing.

## Custody

Lightning Enable does not hold funds; the payment provider facilitates custody
and settlement. Amazap credits are governed by Amazap's current terms.
