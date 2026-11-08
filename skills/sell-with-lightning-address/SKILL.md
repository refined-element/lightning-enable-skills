---
name: sell-with-lightning-address
description: >-
  Turn a URL plus a Lightning Address into a paid L402 endpoint in one
  conversation turn: read the claim quote, pay one L402 challenge from the
  agent's wallet, and get back a proxy URL that charges per call, a manifest
  URL, and a Lightning Enable API key. No account, dashboard, or wallet
  credentials needed. Use when the operator wants to charge for an API they
  already run and has a Lightning Address ("charge for this API", "put my API
  behind Lightning", "monetize this endpoint", "make this URL paid"). Do NOT use
  to receive with Strike, OpenNode, or an NWC wallet (use producer-setup or
  create-l402-proxy), to charge for one file or answer (use sell-this), or to
  pay for someone else's endpoint (use pay-l402-anywhere).
---

# Sell with a Lightning Address

Give Lightning Enable a URL and a Lightning Address; get back a URL that
charges. One L402 payment to `POST /api/producer/claim` creates the Lightning
Enable account, points it at the operator's Lightning Address, and puts the
URL behind a paid proxy. Buyers pay per call, and every payment goes to the
operator's Lightning Address.

Lightning Enable does not hold funds; your wallet provider facilitates custody
and settlement. Lightning Enable asks the Lightning Address for an invoice on
each challenge and stores no wallet credential.

This is the one-call path. For a Strike, OpenNode, or NWC receive wallet, use
[`producer-setup`](../producer-setup/) (no account yet) or
[`create-l402-proxy`](../create-l402-proxy/) (existing account). To charge for a
single resource rather than a whole URL, use [`sell-this`](../sell-this/).

## What you need

- **[Lightning Enable MCP](https://github.com/refined-element/lightning-enable-mcp)**
  with a funded spending wallet that returns preimages (NWC, LND, or Strike),
  and a shell with `curl`. Tools this skill uses:
  - `budget` (`action="status"`) and `get_balance`: the ceiling and the funds.
  - `pay_l402_challenge`: pays the claim's 402 and returns the
    `Authorization` header value.
  - `access_l402_resource`: the optional self-test purchase.
- From the operator:
  - **Target URL:** `https`, a public hostname (no IP address), at most 500
    characters, no `user:password@`, no `#fragment`.
  - **Lightning Address:** `name@domain` from a wallet provider that supports
    Lightning Addresses (LUD-16).
  - **Name** for the service, 1 to 100 characters. Optionally a description
    of up to 500 characters and a price per call in sats.
  - **Optional recovery:** an email address or a Nostr public key (64 hex
    characters). Recovery matters because without it the API key is the only
    credential: lose the key and nobody can give the account back.
  - **Listing:** whether to list the endpoint publicly.

Argument names below are the Python server's `snake_case`. The .NET server takes
the same arguments in `camelCase` (`max_sats` becomes `maxSats`). HTTP request
and response fields are `camelCase`.

The base URL is `https://api.lightningenable.com`. Keep state in
`~/.lightning-enable/claim/`, outside any repository:

```bash
mkdir -p ~/.lightning-enable/claim && chmod 700 ~/.lightning-enable/claim
```

## Flow

Read the quote first, then ask the operator everything in one message. After
their yes, steps 3 to 8 run without stopping.

### 1. Read the quote

```bash
curl -sS https://api.lightningenable.com/api/producer/claim
```

The quote is free and changes nothing. Read, never assume:

- `enabled`: if `false`, or the request answers 404, claims are off on this
  deployment. Stop and say so.
- `price.sats` (and `price.usdCents`): what the claim costs.
  `price.validForSeconds` says how long the figure holds.
- `covers.days` and `covers.plan`: the trial the claim buys.
- `renewal.baseSats`, `renewal.periodDays`, `renewal.endpoint`: what keeps the
  account on its plan after the trial.
- `limits.minProxyPriceSats` and `limits.maxProxyPriceSats`: the allowed price
  per call.
- `terms.version` and `terms.url`: the terms the operator accepts.
- `listing.available` and `listing.note`: whether public listing is live yet.

Never quote a price, a trial length, or a renewal figure from memory or from
this file. Always read them from the quote.

### 2. Ask once, then wait

In one message, show the operator the quote (claim price, trial, renewal, terms
version and link) and ask for whatever is still missing: target URL, Lightning
Address, name, price per call, recovery (email, Nostr key, or none), and
whether to list publicly. Ask them to accept the terms by version.

Then **stop and wait for an explicit yes.** The next steps spend their money.

Before going on, check that the claim fits the wallet's leash:
`budget(action="status")` and `get_balance()`. If `price.sats` is over the
per-request cap, the session cap, or the balance, stop and say which.

On listing: a claimed endpoint stays unlisted until ownership verification
ships, which is not available yet. The proxy works by direct URL meanwhile.
`listPublicly` records the operator's wish for later.

### 3. Write the body once

Write the body to a file exactly once, and send that file in both phases.
**Never rebuild, reformat, or edit it after paying.** The paid token is bound
to the body: a different target URL, Lightning Address, or recovery makes the
payment unusable.

`~/.lightning-enable/claim/body.json`, then `chmod 600` it:

```json
{
  "targetUrl": "<target URL>",
  "name": "<service name>",
  "description": "<optional; leave the field out if none>",
  "defaultPriceSats": <price per call; leave the field out for the default>,
  "receive": { "lightningAddress": "<name@domain>" },
  "recovery": { "email": "<address>" },
  "listPublicly": <true or false>,
  "acceptTerms": "<terms.version from the quote, copied exactly>"
}
```

`recovery` is `{ "email": "…" }`, `{ "nostrPubkey": "…" }`, or left out. Send
`receive.lightningAddress` only; never `receive.connect`.

### 4. Phase 1: get the 402

POST with no `Authorization` header and no `X-API-Key`:

```bash
curl -sS -X POST https://api.lightningenable.com/api/producer/claim \
  -H "Content-Type: application/json" \
  --data-binary @"$HOME/.lightning-enable/claim/body.json" \
  -o "$HOME/.lightning-enable/claim/challenge.json" -w "%{http_code}\n"
```

- **402:** `challenge.json` holds `invoice`, `macaroon`, `paymentHash`,
  `expiresAt`, and `priceSats`. Keep the file. If `priceSats` is above the
  `price.sats` the operator approved, stop and show the new figure before
  paying.
- **Any 4xx or 5xx:** see the error table. **A refusal before payment costs
  nothing.** Fix the named field in `body.json` (rewrite the whole file) and
  POST again.

Every validation runs before an invoice exists: the URL (including a DNS check
that it is not private), the price, the Lightning Address (it must resolve, and
the price per call must fit its limits), recovery, and terms.

### 5. Pay the 402

```
pay_l402_challenge(invoice="<invoice>", macaroon="<macaroon>", max_sats=<priceSats from the 402>)
```

- **Success:** the result's `authorization_header` is
  `L402 <macaroon>:<preimage>`. Save it immediately, before anything else, as
  one line, `Authorization: <authorization_header>`, in
  `~/.lightning-enable/claim/auth.header`, then `chmod 600` it. Never print it.
- **Confirmation code requested:** the amount is over the auto-approve
  threshold. Ask the operator for the code from the MCP's console and re-call
  with `confirmation_nonce="<code>"`. Never guess a code.
- **Payment fails:** nothing was charged. Report the wallet's error and stop.

From here on the claim is paid. **Never POST without the `Authorization`
header again** for this claim: that mints a new invoice and charges twice.

### 6. Phase 2: redeem

POST the same file with the saved header:

```bash
curl -sS -X POST https://api.lightningenable.com/api/producer/claim \
  -H "Content-Type: application/json" \
  -H @"$HOME/.lightning-enable/claim/auth.header" \
  --data-binary @"$HOME/.lightning-enable/claim/body.json" \
  -o "$HOME/.lightning-enable/claim/response.json" -w "%{http_code}\n"
```

`-H @file` reads the header from the file, so the token never appears on a
command line.

- **200 with `replayed: false`:** done. Go to step 7.
- **200 with `replayed: true`:** an earlier phase 2 already succeeded. The body
  has everything except `apiKey`, which only the first answer carried.
- **Anything else after payment:** resend the identical body with the same
  token. Do not edit `body.json` and do not pay again. The token is good until
  the challenge's `expiresAt`; redeem before then. The error table says which
  codes clear on a retry.

### 7. Store the API key, once

`apiKey` appears in this one answer and never again. Store it before you report
anything:

- If `~/.lightning-enable/config.json` has no `lightningEnableApiKey`, add the
  key there under that name. The MCP reads it after a restart, and the
  `l402_producer` tool then works on the new account.
- If a key is already there, it belongs to another account: do not overwrite
  it. Write the new key to `~/.lightning-enable/claim-<proxyId>.key` and
  `chmod 600` it.

Tell the operator which file holds the key, and that it is the account's
credential (the only one if `recovery` is `none`). Do not print the key. Then
delete `body.json`, `challenge.json`, `auth.header`, and `response.json`.

### 8. Hand off

Report from the response:

- **Proxy URL:** `proxy.url`. Every request under it answers 402 until paid.
  Share this.
- **Manifest URL:** `proxy.manifest`, which agents read to find the price. The
  OpenAPI document is `proxy.openapi`.
- **Receive lane:** `receive.lane` and `receive.status` (`live`).
- **Paid through:** `paidThrough`, and how to renew: `renew.endpoint`,
  `renew.quoteSats`, `renew.periodDays`. Renewing in sats is the
  [`lightning-enable-account`](../lightning-enable-account/) skill.
- **Listing:** `listing.listed` and `listing.reason`. Repeat each entry in
  `warnings` word for word.
- **Where the key is stored** (step 7).

### 9. Offer the self-test

Offer one purchase of the new endpoint, with the operator's yes and a cap of
the price per call:

1. **Mint:** request a `GET` path under `proxy.url` with no payment; it should
   answer 402 with an invoice for the price per call. This costs nothing.
2. **Pay:** `access_l402_resource(url="<proxy.url><path>", max_sats=<price per call>)`.
   The MCP pays the invoice and retries with the token.
3. **Verify:** the retry answers 200 with the upstream's response, and the sats
   arrive at the operator's Lightning Address.

Run one payment at a time. For the full check of a seller's endpoint and its
pay-once rules, follow step 6 of [`producer-setup`](../producer-setup/), which
uses [`l402-compatibility-report`](../l402-compatibility-report/). To charge for
one resource on the new account, or to verify a buyer's token with
`l402_producer(action="verify", macaroon=…, preimage=…)` after restarting the
MCP, use [`sell-this`](../sell-this/). To receive with a Strike, OpenNode, or
NWC wallet instead, use [`create-l402-proxy`](../create-l402-proxy/).

## Errors

Errors are RFC 9457 problem JSON. Branch on `error` (the code), and repeat
`detail` to the operator. Extra fields ride alongside, such as
`minSendableSats` and `maxSendableSats`. A `Retry-After` header, when present,
says how many seconds to wait.

**A refusal before payment costs nothing. After payment, resend the identical
body with the same token.**

| Code | Status | Tell the operator | Retry helps? |
|---|---|---|---|
| `invalid_target_url` | 400 | The URL must be `https` on a public hostname, at most 500 characters, with no IP address, credentials, or `#fragment`; `detail` names the problem. A private or internal address is refused on purpose. | Before payment: no; fix the URL. After payment: only if the cause was DNS that has since recovered. |
| `invalid_price` | 400 | The price per call must be between `minProxyPriceSats` and `maxProxyPriceSats` from the problem body. | No; change the price before paying. |
| `invalid_lightning_address` | 400 | Either the address does not resolve (check the spelling, and that the provider supports Lightning Addresses), or the price per call is outside what the address accepts: between `minSendableSats` and `maxSendableSats`. | Before payment: no; fix the address or the price. After payment: yes, if the wallet provider was briefly down. |
| `invalid_recovery` | 400 | Give an email or a 64-hex-character Nostr public key, not both. Disposable email is refused, and a Nostr key already bound to another account is refused. | No; fix or drop recovery before paying. |
| `terms_required` | 400 | `acceptTerms` must equal the quote's `terms.version` exactly; the problem body carries `termsVersion` and `termsUrl`. Show the terms again and ask. | No; re-read the quote and get acceptance. |
| `invalid_name` / `invalid_description` | 400 | The name is required, 1 to 100 characters; the description is at most 500. | No; fix the field. |
| `invalid_receive` / `connect_not_available` | 400 / 501 | This skill sends `receive.lightningAddress` only. The connect hand-off for Strike, OpenNode, and NWC is not available; use `producer-setup` or `create-l402-proxy`. | No. |
| `claim_body_mismatch` | 402 | The body changed after payment. | Yes: resend the original body with the same token. Never pay again for an edited body without the operator's yes. |
| `invalid_l402_token` | 401 | The token is invalid, expired, or not for a claim. | No. If it expired after payment, tell the operator and stop; a new claim is a new payment. |
| `invalid_authorization` | 400 | The `Authorization` header was malformed. It must be `L402 <macaroon>:<preimage>`. | Yes, after fixing the header file. |
| `plan_limit_reached` | 403 | Only when claiming onto an existing account with `X-API-Key`: that plan's proxy cap is reached. | No; claim without the key, or upgrade. |
| `receive_lane_already_configured` | 409 | Only with `X-API-Key`: that account already has a different receive wallet, and a claim never replaces it. | No; claim without the key, or change the wallet in the dashboard. |
| `merchant_exists` | 409 | After payment: an account already uses that recovery email. | Resend the same body and token with that account's `X-API-Key` header added. |
| `payment_provider_busy` | 503 | The wallet provider did not return an invoice. Nothing was invoiced or charged. | Yes, after `Retry-After`. |
| `payment_provider_rejected` | 503 | The wallet provider refused to create the invoice. Nothing was charged. | No; it repeats until the provider side changes. Stop and report it. |
| `upstream_unavailable` / `challenge_persist_failed` | 503 | A transient failure; nothing was invoiced. | Yes, shortly. |
| `claim_contended` | 503 | After payment, a proxy id could not be allocated; nothing was created. | Yes: same body, same token, after `Retry-After`. |
| `claim_unavailable` | 503 | Claims are not available on this deployment right now. | No retry loop; check the quote again later. |
| (no code) | 404 / 429 | 404: claims are off on this deployment. 429: too many claim requests from this address. | 404: no. 429: yes, after waiting. |

If a paid claim keeps failing with the same code, stop. Give the operator the
`paymentHash` from `challenge.json` (never the macaroon or the preimage) and
point them at [lightningenable.com](https://www.lightningenable.com) for
support.

## Safety rules

- **Explicit yes before paying.** Show the quoted price and terms first.
- **Pay once.** One phase 1, one payment, then only phase 2 retries with the
  same token.
- **The body is written once and sent twice.** Never edit it after paying.
- **Never echo secrets:** the API key, the macaroon, the preimage, and the
  `Authorization` header stay in files, never in chat.
- **No figures from memory.** Every price, trial, and renewal figure comes from
  the quote or the response.
- **The operator owns the decisions:** the URL, the address, the price, the
  recovery, the listing, and the terms. Do not sell an API whose terms forbid
  resale.

## Example

> Operator: "Charge for my API at https://api.example-weather.dev, pay to
> alice@example-wallet.com."
>
> 1. `curl` the quote: enabled; claim price, trial, renewal, and terms version
>    read from it.
> 2. One message: the quote, plus "Name? Price per call? Recovery email or Nostr
>    key? List publicly? Do you accept terms version `<terms.version>`?" The
>    operator answers and says yes. `budget(action="status")` fits.
> 3. Write `body.json` once. Phase 1: 402 with `priceSats` equal to the quote.
> 4. `pay_l402_challenge(invoice="<invoice>", macaroon="<macaroon>",
>    max_sats=<priceSats>)`, then save `authorization_header` to `auth.header`.
> 5. Phase 2 with the same file and the header: 200. Store `apiKey` in
>    `~/.lightning-enable/config.json`; delete the state files.
> 6. Hand off: proxy URL, manifest URL, Lightning Address lane live, paid
>    through `<paidThrough>`, unlisted until verification ships, key stored in
>    `~/.lightning-enable/config.json`. Offer the self-test.
