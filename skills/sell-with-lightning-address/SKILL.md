---
name: sell-with-lightning-address
description: >-
  Turn a URL plus a Lightning Address into a paid L402 endpoint in one
  conversation: read the claim quote, ask the operator once, pay one L402
  challenge from the agent's wallet with l402_producer sell_url, and get back a
  proxy URL that charges per call, a manifest URL, and a Lightning Enable API
  key. No account, dashboard, or wallet credentials needed. Use when the
  operator wants to charge for an API they already run and has a Lightning
  Address ("charge for this API", "put my API behind Lightning", "monetize this
  endpoint", "make this URL paid"). Do NOT use to receive with Strike,
  OpenNode, or an NWC wallet (use producer-setup or create-l402-proxy), to
  charge for one file or answer (use sell-this), or to pay for someone else's
  endpoint (use pay-l402-anywhere).
---

# Sell with a Lightning Address

Give Lightning Enable a URL and a Lightning Address; get back a URL that
charges. One L402 payment to the producer claim creates the Lightning Enable
account, points it at the operator's Lightning Address, and puts the URL behind
a paid proxy. Buyers pay per call, and every payment goes to the operator's
Lightning Address.

Lightning Enable does not hold funds; your wallet provider facilitates custody
and settlement. Lightning Enable asks the Lightning Address for an invoice on
each challenge and stores no wallet credential.

This is the one-call path. For a Strike, OpenNode, or NWC receive wallet, use
[`producer-setup`](../producer-setup/) (no account yet) or
[`create-l402-proxy`](../create-l402-proxy/) (existing account). To charge for a
single resource rather than a whole URL, use [`sell-this`](../sell-this/).

## What you need

- **[Lightning Enable MCP](https://github.com/refined-element/lightning-enable-mcp)**
  with a funded spending wallet that returns preimages (NWC, LND, or Strike).
  Tools this skill uses:
  - `l402_producer` with `action="sell_url"`: quote, phase 1, payment, and
    phase 2 in one call. It stores the API key, and calling it again with the
    same arguments resumes a paid claim instead of paying twice.
  - `budget` (`action="status"`) and `get_balance`: the ceiling and the funds.
  - `access_l402_resource`: the optional self-test purchase.
  - No `sell_url` on this MCP? Use the [curl fallback](#fallback-without-sell_url),
    which needs a shell with `curl` and this skill's `scripts/claim.sh`.
- From the operator:
  - **Target URL:** `https`, on a public hostname that resolves, on the
    standard HTTPS port (no custom port), at most 500 characters, with no IP
    address, no `user:password@`, and no `#fragment`. A host that does not
    resolve, or resolves to a private address, is refused before payment.
  - **Lightning Address:** `name@domain` from a wallet provider that supports
    Lightning Addresses (LUD-16).
  - **Name** for the service, 1 to 100 characters (the tool defaults it to the
    hostname). Optionally a description of up to 500 characters and a price per
    call in sats.
  - **Optional recovery:** an email address or a Nostr public key (64 hex
    characters). Recovery matters because without it the API key is the only
    credential: lose the key and nobody can give the account back.
  - **Listing:** whether to list the endpoint publicly.

Argument names below are the Python server's `snake_case`. The .NET server takes
the same arguments in `camelCase` (`target_url` becomes `targetUrl`). Result and
HTTP fields are `camelCase` in both.

## Flow

The operator answers once and says yes once; everything after that runs without
stopping.

### 1. Read the quote

The quote is free and changes nothing. Get it with `scripts/claim.sh quote`,
which prints `GET https://api.lightningenable.com/api/producer/claim`. Without a
shell, call
`l402_producer(action="sell_url", target_url="<url>", lightning_address="<address>")`
with no `accept_terms`: it returns the quote and sends nothing.

- `enabled`: if `false`, or the quote answers 404, claims are off on this
  deployment. Stop and say so.
- `pricingNote`: **show it to the operator word for word.** It says the claim
  price covers the first period only and renewal is a separate amount.
- `price.sats`, `covers`, `renewal`, and `terms` (`terms.version`,
  `terms.url`): what the claim costs, the trial it buys, what keeps the account
  on its plan, and the terms to accept.
- `limits.minProxyPriceSats` and `limits.maxProxyPriceSats`: the allowed price
  per call.
- `bodyRule`: the server's statement that the paid retry must send the
  identical body, and that a changed body is refused and the payment is not
  refunded. `sell_url` does this for you; the fallback must.

Never quote a price, a trial length, or a renewal figure from memory or from
this file. Always read them from the quote.

### 2. Ask once, then wait

In one message, show the quote (`pricingNote`, the claim price, the trial, the
renewal, the terms version and link) and ask for whatever is still missing:
target URL, Lightning Address, name, price per call, recovery (email, Nostr
key, or none), and whether to list publicly. Ask the operator to accept the
terms by version.

If they give a recovery email, ask: **"Does this email already have a Lightning
Enable account?"** An email that already belongs to an account is refused only
**after** payment (`merchant_exists`). If it does, use a Nostr key, no
recovery, or a different email.

On listing: public listing requires ownership verification, so a claimed
endpoint starts unlisted. The proxy works by direct URL meanwhile. The claim
response carries the verification token and instructions (`verification`),
and the next step is the [`verify-producer`](../verify-producer/) skill.
`list_publicly` records the operator's wish; listing is turned on after the
proxy is verified.

Then **stop and wait for an explicit yes.** The next step spends their money.
Before going on, check `budget(action="status")` and `get_balance()`. If
`price.sats` is over the per-request cap, the session cap, or the balance, stop
and say which.

### 3. Claim with `sell_url`

```
l402_producer(action="sell_url", target_url="<url>", lightning_address="<name@domain>",
              name="<name>", description="<description>", price_sats=<price per call>,
              recovery_email="<email>", list_publicly=<true or false>,
              accept_terms="<terms.version>")
```

Leave out the arguments the operator did not give. Use `recovery_nostr_pubkey`
instead of `recovery_email` for a Nostr key, never both.

- **`success: true` with `proxyUrl`:** the claim is done. Go to step 4.
- **`stage: "quote"`:** `accept_terms` did not match the current terms
  version. Nothing was sent or charged. Show the new terms and ask again.
- **`error: "price_changed"`:** the invoice asks for more than the quote.
  Nothing was paid. Show the new figure and call again only after a yes.
- **Confirmation code requested:** the amount is over the auto-approve
  threshold. Ask the operator for the code from the MCP's console and call
  again with the same arguments plus `confirmation_nonce="<code>"`. Never guess
  a code.
- **`success: false` with `paid: true`:** the payment is spent. Call
  `sell_url` again with **exactly the same arguments** before `tokenExpiresAt`:
  it skips the payment and redeems the saved token. Never change an argument
  after paying. If it keeps failing, see [Errors](#errors).
- **`success: false` with `paid: false`:** nothing was charged. See
  [Errors](#errors), fix the named argument, and call again.

### 4. Store the API key

`sell_url` stores the key itself and says where in `apiKeyStorage.path`:
`~/.lightning-enable/config.json` as `lightningEnableApiKey` if that slot was
empty, otherwise `~/.lightning-enable/claim-<proxyId>.key`. Tell the operator
which file holds it, and that it is the account's credential (the only one if
`recovery` is `none`). Do not repeat the key in chat.

- **`keyRotated: true`:** this claim had been redeemed before, so the server
  issued a new key and **every earlier key for this account stopped working**.
  The new key is the only valid one. Replace any key stored earlier for this
  claim. If the tool wrote the new key to `claim-<proxyId>.key` because
  `config.json` already held a key, and that older key came from an earlier run
  of this same claim, move the new key into `config.json`. Not sure whose key
  `config.json` holds? Run `scripts/claim.sh status`: a 401
  `authentication_required` means the key is dead, so replacing it loses
  nothing.
- **Each further redeem rotates the key again.** Once the key is stored, do not
  call `sell_url` with the same arguments again.
- **`apiKey` is null or missing without `keyRotated`:** the claim was made with
  an existing account's key, so it joined that account and there is nothing new
  to store.
- Any file holding a key gets `chmod 600`.

### 5. Hand off

Report from the result:

- **Proxy URL:** `proxyUrl`. Every request under it answers 402 until paid.
  Share this.
- **Manifest URL:** `manifestUrl`, which agents read to find the price.
- **Paid through:** `paidThrough`, and how to renew: `renew`. Renewing in sats
  is the [`lightning-enable-account`](../lightning-enable-account/) skill.
- **Listing:** `listing`. Repeat each entry in `warnings` word for word. To
  list publicly, verify ownership next with [`verify-producer`](../verify-producer/).
- **Where the key is stored** (step 4).

### 6. Offer the self-test

Offer one purchase of the new endpoint, with the operator's yes and a cap of
the price per call:

1. **Mint:** request a `GET` path under the proxy URL with no payment; it
   should answer 402 with an invoice for the price per call. This costs
   nothing.
2. **Pay:** `access_l402_resource(url="<proxyUrl><path>", max_sats=<price per call>)`.
   The MCP pays the invoice and retries with the token.
3. **Verify:** the retry answers 200 with the upstream's response, and the sats
   arrive at the operator's Lightning Address.

Run one payment at a time. To verify a buyer's token yourself, or to charge for
one resource on the new account, see [`sell-this`](../sell-this/).

## Check status later

With the key, `scripts/claim.sh status` (or `scripts/claim.sh status <key file>`)
calls `GET https://api.lightningenable.com/api/producer/claim/status` with the
`X-API-Key` header. It answers `lane`, `status`, `proxyActive`, `proxyId`,
`proxyUrl`, `manifestUrl`, `paidThrough`, `renew`, and `recovery`. Use it to
answer "is my endpoint live?", or to recover the hand-off details after the
claim's answer is gone.

- 401 `authentication_required`: the key is missing or no longer works.
- 404 `no_claim`: this account has no proxy made by a claim.

## Fallback without `sell_url`

For an MCP without `l402_producer(action="sell_url")`. You need a shell with
`curl`. Run `scripts/claim.sh` from this skill's folder; it keeps every flag
fixed, keeps state in `~/.lightning-enable/claim/` (mode 700, files 600), and
reads secrets from files or stdin, never from the command line.

1. **Quote and ask:** steps 1 and 2 above.
2. **Write the body once** to `~/.lightning-enable/claim/body.json` and
   `chmod 600` it. Never rebuild, reformat, or edit it after paying. As
   `bodyRule` says, the paid token is bound to this exact body; a changed body
   is refused with `claim_body_mismatch` and the payment is not refunded.

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

   `recovery` is `{ "email": "…" }`, `{ "nostrPubkey": "…" }`, or left out.
   Send `receive.lightningAddress` only; never `receive.connect`.
3. **Phase 1:** `scripts/claim.sh phase1`. A 402 prints `invoice`, `macaroon`,
   `paymentHash`, `expiresAt`, and `priceSats`, saved in `challenge.json`. If
   `priceSats` is above the approved `price.sats`, stop and ask again. Any
   other status: see [Errors](#errors). A refusal before payment costs nothing.
4. **Pay:**
   `pay_l402_challenge(invoice="<invoice>", macaroon="<macaroon>", max_sats=<priceSats>)`.
   The result's `usage.headerValue` is `L402 <macaroon>:<preimage>` on both MCP
   servers. Save it at once with `scripts/claim.sh save-auth`, passing the value
   on stdin, and never print it. A confirmation-code request works as in step 3
   above. From here on the claim is paid: `claim.sh phase1` refuses to run
   again, so it can't charge twice.
5. **Phase 2:** `scripts/claim.sh phase2` sends the same `body.json` with
   `Authorization: L402 <macaroon>:<preimage>` and saves `response.json` with
   mode 600. It prints the answer with the key redacted.
   - **200, `replayed: false`:** `apiKey` is the new key.
   - **200, `replayed: true`, `keyRotated: true`:** an earlier phase 2 already
     succeeded and this one rotated the key. The body's `apiKey` is the only
     valid key; every earlier one is dead. Store it and replace any key stored
     earlier for this claim (step 4 above).
   - **200, `replayed: true`, `keyRotated: false`:** no key in the body; the
     claim joined an existing account.
   - **Anything else, or no answer:** resend the identical body with the same
     token (`claim.sh phase2` again) before `expiresAt`, if
     [Errors](#errors) lists the code as retryable after payment. Never edit
     `body.json` and never pay again.
6. **Store the key:** if `~/.lightning-enable/config.json` has no
   `lightningEnableApiKey` (or holds a key from an earlier run of this claim),
   put the key there under that name and `chmod 600` the file. The MCP reads it
   after a restart. Otherwise run `scripts/claim.sh store-key-file`, which
   writes `~/.lightning-enable/claim-<proxyId>.key` with mode 600. Tell the
   operator which file holds it. Each further phase 2 rotates the key again,
   so once it is stored, do not redeem again.
7. **Hand off** from `response.json` (`proxy.url`, `proxy.manifest`,
   `paidThrough`, `renew`, `listing`, `warnings`), then
   `scripts/claim.sh clean`.

## Errors

The code is `error` in the result or the problem JSON. Repeat `detail` or
`message` to the operator. When there is no code (a bare 404 or 429), go by the
status; `sell_url` reports those as `feature_not_enabled` and `rate_limited`.
`Retry-After`, when present, says how many seconds to wait.

**A refusal before payment costs nothing. After payment, resend the identical
body with the same token.**

### Before payment: free

Nothing was invoiced or charged. Fix the named field and call again.

| Code | Tell the operator | Then |
|---|---|---|
| `invalid_target_url` | The URL must be `https` on a public hostname that resolves, on the standard HTTPS port, at most 500 characters, with no IP address, credentials, or `#fragment`. A private or internal address is refused on purpose. | Fix the URL. |
| `invalid_price` | The price per call must be between `minProxyPriceSats` and `maxProxyPriceSats` from the problem body. | Change the price. |
| `invalid_lightning_address` | The address does not resolve (check the spelling, and that the provider supports Lightning Addresses), or the price per call is outside what it accepts: between `minSendableSats` and `maxSendableSats`. | Fix the address or the price. |
| `invalid_recovery` | Give an email or a 64-hex-character Nostr public key, not both. Disposable email is refused, and so is a Nostr key already bound to an account. | Fix or drop recovery. |
| `terms_required` | `acceptTerms` must equal the quote's `terms.version` exactly (`termsVersion` and `termsUrl` are in the problem body). | Show the terms again and ask. |
| `invalid_name`, `invalid_description` | The name is required, 1 to 100 characters; the description is at most 500. | Fix the field. |
| `invalid_receive`, `connect_not_available` | This skill sends a Lightning Address only; the connect hand-off for Strike, OpenNode, and NWC is not available. | Use `producer-setup` or `create-l402-proxy`. |
| `payment_provider_busy`, `upstream_unavailable`, `challenge_persist_failed` | A wallet provider or the platform did not answer in time. | Wait `Retry-After` (or a few seconds) and call again. |
| `payment_provider_rejected` | The wallet provider refused to create the invoice. | Stop; a retry repeats it. |
| `claim_unavailable`, `feature_not_enabled` (404) | Claims are not available on this deployment right now. | Stop; check the quote later. No retry loop. |
| `rate_limited` (429) | Too many claim requests, from this address or from all callers together. | Wait, then call again. |
| `network_error` | No answer reached the agent. | Call again. |

### After payment: the payment is spent

**Retry with the same arguments (`sell_url`), or the same `body.json` and the
same `auth.header` (fallback), before the token's `expiresAt`, for these codes
only:** `claim_contended`, `claim_failed`, `payment_provider_busy`,
`upstream_unavailable`, `challenge_persist_failed`, `rate_limited` (429),
`network_error`, `invalid_lightning_address` (the provider may have been
briefly down), and `invalid_target_url` (DNS may have recovered). Wait
`Retry-After` when given. `sell_url` already retries a few times by itself.

| Code | Tell the operator | Then |
|---|---|---|
| `claim_body_mismatch` | The body changed after payment. | Restore the original body (`sell_url`: the original arguments) and resend with the same token. Never pay again for an edited body without a yes. |
| `merchant_exists` | An account already uses that recovery email. | Ask the operator for that account's API key, then resend the same body and token with it in an `X-API-Key` header. That claim joins their account, so its plan cap or existing wallet can still refuse it (`plan_limit_reached`, `receive_lane_already_configured`): then stop as below. |
| `invalid_l402_token`, `invalid_authorization` | The token is invalid, expired, or malformed. | A malformed `auth.header` can be saved again from the payment result. Otherwise stop as below. |
| anything else | The claim could not be completed. | Stop as below. |

**Stop:** give the operator the `paymentHash` (from the result or
`challenge.json`; never the macaroon or the preimage) and point them at
[lightningenable.com](https://www.lightningenable.com) for support. Do not pay
again.

## Safety rules

- **Explicit yes before paying.** Show `pricingNote`, the quoted price, and the
  terms first.
- **Pay once.** After paying, only redeem with the same arguments or the same
  body file and token.
- **Never change the body after paying.** `sell_url` keeps it fixed; in the
  fallback, write it once and send the file.
- **Never echo secrets:** the API key, the macaroon, the preimage, and the
  `Authorization` header stay in files, never in chat.
- **No figures from memory.** Every price, trial, and renewal figure comes from
  the quote or the result.
- **The operator owns the decisions:** the URL, the address, the price, the
  recovery, the listing, and the terms. Do not sell an API whose terms forbid
  resale.

## Example

> Operator: "Charge for my API at https://api.example-weather.dev, pay to
> alice@example-wallet.com."
>
> 1. `scripts/claim.sh quote`: enabled. Read `pricingNote`, the claim price,
>    the trial, the renewal, and the terms version.
> 2. One message: `pricingNote` word for word, the figures from the quote, and
>    "Name? Price per call? Recovery email or Nostr key? List publicly? Do you
>    accept terms version `<terms.version>`?" The operator answers and says yes.
>    `budget(action="status")` fits.
> 3. `l402_producer(action="sell_url", target_url="https://api.example-weather.dev",
>    lightning_address="alice@example-wallet.com", name="Example Weather",
>    price_sats=<price per call>, accept_terms="<terms.version>")`: success.
> 4. The key is in `~/.lightning-enable/config.json` (`apiKeyStorage.path`);
>    restart the MCP to manage the account with `l402_producer`.
> 5. Hand off: proxy URL, manifest URL, paid through `<paidThrough>`, unlisted
>    until ownership is verified (`verify-producer`), where the key is. Offer the self-test.

**Verify next:** to list the endpoint publicly, prove ownership with [`verify-producer`](../verify-producer/).
