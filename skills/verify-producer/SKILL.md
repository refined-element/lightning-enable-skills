---
name: verify-producer
description: >-
  Prove that the operator controls the API behind a Lightning Enable proxy, so
  the proxy can be listed publicly: get the verification token (from the claim
  response, or issue one), publish it by the one method the agent or the
  operator can actually perform (a well-known file, a DNS TXT record, or a
  response header), run the check, poll a pending check, explain any failure
  reason, then offer to turn on public listing. Use when the operator wants a
  claimed or existing proxy listed ("list my endpoint publicly", "verify my
  proxy", "prove I own this API", "why is my proxy unlisted",
  "ownership_verification_required"). Do NOT use to create the paid endpoint in
  the first place (use sell-with-lightning-address, producer-setup, or
  create-l402-proxy), or to check how an endpoint behaves over L402 (use
  l402-compatibility-report).
---

# Verify producer ownership

A Lightning Enable proxy sits in front of an API (its *target*) and charges a
Lightning payment for each call. Anyone with an account can point a proxy at
any public URL, so before a proxy is listed publicly, its owner proves control
of the target: they publish a token that only they received, in a place only
the target's owner can write to, and Lightning Enable looks for it.

Verification is a tier, not a gate. An unverified proxy keeps working by its
direct URL; verification adds public listing (the L402 registry, agent
discovery, and Nostr), the verified mark buyers read in the manifest
(`verified`, `verification_method`, `verified_at`), and, for a proxy created by
the one-payment claim, removes the extra limit on payment challenges
(`unverified_proxy_rate_limited`).

Nothing here pays or moves money. Lightning Enable does not hold funds; your
wallet provider facilitates custody and settlement.

The proxy comes first: [`sell-with-lightning-address`](../sell-with-lightning-address/)
(one paid claim), [`producer-setup`](../producer-setup/) (no account yet), or
[`create-l402-proxy`](../create-l402-proxy/) (existing account).

## What you need

- **A shell with `curl`** and this skill's `scripts/verify.sh`. Every
  subcommand takes plain words (a proxy ID, a path, a number), keeps the API key
  off the command line, and stores the token in a file with mode 600.
- **The merchant API key.** `verify.sh` reads `lightningEnableApiKey` from
  `~/.lightning-enable/config.json`, or the first line of the file named by
  `LE_KEY_FILE`. A claim that found `config.json` already holding a key stored
  its own in `~/.lightning-enable/claim-<proxyId>.key`; then run
  `LE_KEY_FILE=~/.lightning-enable/claim-<proxyId>.key scripts/verify.sh ...`.
- **The proxy ID**, for example `forecast-api-a1b2`: `proxyId` in the claim
  result, `scripts/claim.sh status` from the sibling skill, the dashboard's
  proxy list, or `GET /api/proxy`.
- **One way to publish on the target**, decided in step 2: deploy access to the
  target host's web root, the DNS zone for the target's hostname, or the API's
  response headers.
- Optionally, the [Lightning Enable MCP](https://github.com/refined-element/lightning-enable-mcp):
  `l402_producer` with `action="publish"` turns on the listing in step 6.

All three endpoints take the key as `X-API-Key` and live on
`https://api.lightningenable.com`:

| Endpoint | What it does | `verify.sh` |
|---|---|---|
| `GET /api/proxy/{proxyId}/verification` | The state and the exact instructions for this proxy. Never returns the token. | `state` |
| `POST /api/proxy/{proxyId}/verification/token` | Issues a token, shown once; replaces any earlier one. | `token` |
| `POST /api/proxy/{proxyId}/verify` | Runs the check now. | `verify`, `poll` |

The two `POST` calls allow 10 requests per minute per API key. Another
account's proxy answers 404, the same as one that does not exist.

## Flow

### 1. Read the state

Run `scripts/verify.sh state <proxyId>` and read:

- `verified` and `method`. If `verified` is `true` with `method` `well-known`,
  `dns-txt`, or `header`, the proxy is already verified: skip to step 6. Do
  **not** issue a new token; that unverifies and unlists it.
- `method` `grandfathered` or `platform`: see
  [States that need no action](#states-that-need-no-action).
- `tokenIssued`: whether a token exists. The token itself can never be read
  back.
- `listed`, `failures`, `lastCheckedAt`, `nextCheckAt`.
- `instructions`: for this proxy, `instructions.methods[]` (each with `method`,
  `url`, `recordName`, `headerName`, `body`, and `value`), with the literal
  `<token>` (`instructions.tokenPlaceholder`) wherever the token goes, plus
  `tokenEndpoint`, `verifyEndpoint`, and `note`. Take the file URL, the TXT
  record name, and the header URL from here, not from memory.

### 2. Get the token

The token proves ownership for listing only: it can't call the API, move
money, or change the account. It is still a credential, so keep it in its file
and publish it only where step 3 puts it.

- **From the claim response.** A claim answer carries `verification.token`,
  `verification.instructions`, and `verification.verifyEndpoint`. If the claim
  ran through the sibling skill's curl fallback, copy the token before
  `claim.sh clean` deletes the response:
  `scripts/verify.sh token <proxyId> --from-claim` (or pass the response file
  after `--from-claim`). A replayed claim answer carries `token: null`, and the
  `sell_url` tool result doesn't include the `verification` block, so in those
  cases issue one.
- **Otherwise, issue one:** `scripts/verify.sh token <proxyId>`. It saves the
  token to `~/.lightning-enable/verify-<proxyId>.token` (mode 600) and prints
  the answer with the token redacted. **The token is shown once**; only its
  hash is stored, so a lost token means issuing a new one.

Issuing a token replaces the old one: the old token stops working, and a proxy
verified by a live check becomes unverified and unlisted until the new token is
published and verified. `verify.sh token` refuses, before any request, when a
token file for this proxy already exists or the proxy is verified by a live
check. Pass `--reissue` only after the operator says yes to that. Each proxy
has its own token; two proxies on one host need two tokens.

### 3. Publish the token by one method

Choose the one method you or the operator can actually perform. One is enough.
In every value, replace `<token>` with the token. The *target host* is the
hostname of the target base URL, subdomain included: for
`https://api.example.com/v1` it is `api.example.com`, not `example.com`.

| Method | Where the token goes | What it proves |
|---|---|---|
| `well-known` | `https://{target host}/.well-known/lightning-enable.json` serving `{"verify":"<token>"}` | Control of the web root of the target host. |
| `dns-txt` | A TXT record named `_lightning-enable.{target host}` whose value is the token | Control of the DNS zone for the target's hostname. |
| `header` | An `X-Lightning-Enable-Verify: <token>` response header at the target base URL | Control of the API's responses at the target base URL only. |

Buyers see the method in `verification_method`, so prefer the first one that
fits.

**You have deploy access to the target host:** write the file with
`scripts/verify.sh write-well-known <proxyId> <path>`, where `<path>` is the
site's web root directory (it creates `.well-known/lightning-enable.json`) or
the file itself. A file that already lists other proxies' tokens keeps them, as
an array: `{"verify":["<token 1>","<token 2>"]}`. Then deploy it. The file must:

- be served at the root of the target host over HTTPS on port 443, with a valid,
  publicly trusted certificate, whatever path the target base URL has;
- answer a `2xx` status directly, with no redirect, as valid JSON under 4 KB.

**You don't:** hand the operator both alternatives below, with the token filled
in (read it with `head -n 1 ~/.lightning-enable/verify-<proxyId>.token`; it
becomes public once published, but don't post it anywhere else), and wait for
them to say it's done.

- **DNS TXT record**, for whoever manages DNS for the target's hostname:

  | Field | Value |
  |---|---|
  | Name | `_lightning-enable.{target host}` (`recordName` from step 1) |
  | Type | `TXT` |
  | Value | the token, and nothing else: no prefix such as `lightning-enable-verify=` |

  Many DNS providers append the zone to the name entered: in the zone
  `example.com`, enter `_lightning-enable.api`, or the record becomes
  `_lightning-enable.api.example.com.example.com`. A new record can take a few
  minutes to reach every resolver; `dig +short TXT _lightning-enable.{target host}`
  shows what public DNS returns.
- **Response header**, for whoever owns the API's code:
  `X-Lightning-Enable-Verify: <token>` on the response from the target base URL
  with a trailing slash (`https://api.example.com/v1/`), for `HEAD` and `GET`.
  Any status counts except a redirect (`3xx`), so a root that answers `401` or
  `404` works as long as the header is on it. Several tokens are separated by
  commas.

### 4. Run the check

Run `scripts/verify.sh verify <proxyId>` once. The check tries `well-known`,
then `dns-txt`, then `header`, and stops at the first that finds the token. It
never follows a redirect.

- **`verified: true`:** `method` says which one matched. Go to step 6.
- **`verified: false`:** `reason` says what each method saw, in order,
  separated by semicolons, for example
  `well-known: /.well-known/lightning-enable.json answered HTTP 404; dns-txt: no TXT record at _lightning-enable.api.example.com; header: HEAD answered HTTP 401 without X-Lightning-Enable-Verify; GET answered HTTP 401 without X-Lightning-Enable-Verify`.
  Read the part for the method you chose; the other two failing is expected.
  Explain it to the operator in plain words using
  [During the check](#during-the-check), fix what it names, and check again.
  The reason never contains the token.
- **`pending: true`:** the check ran past its time limit and **recorded
  nothing**; it is not a failure. Wait `retryAfterSeconds` (also sent as
  `Retry-After`) and check again. `reason` says what the check learned before it
  stopped.

`verify.sh verify` exits 0 when verified, 3 when pending, 4 when not verified,
and 1 on an HTTP error.

### 5. Poll while DNS or a deploy settles

After a DNS change, or while a deploy rolls out, run
`scripts/verify.sh poll <proxyId>`: up to 5 attempts (pass a number up to 10),
waiting `retryAfterSeconds` after a pending check and 60 seconds
(`LE_POLL_INTERVAL`) after a failed one, and stopping at the first success.
Waits are capped at 120 seconds (`LE_MAX_WAIT`). If it ends unverified, stop and
explain the last `reason`; don't start another round without a change on the
target.

Each failed check adds one to `failures`. A failed manual `verify` on a proxy
that is already verified counts toward the three-failure drop in step 6 just
like a failed daily re-check, so polling a verified proxy can unlist it. Don't
poll a proxy that is already verified.

### 6. Offer public listing

A verified proxy is not listed until the owner turns listing on: `listed` stays
`false`. Ask the operator whether to list it publicly, then, with their yes:

```
l402_producer(action="publish", proxy_id="<proxyId>")
```

This calls `PUT /api/proxy/{proxyId}/manifest/settings` with
`manifestEnabled` and `manifestPubliclyListed` set to `true`. The MCP uses the
key in `~/.lightning-enable/config.json`; if the claim's key is in a
`claim-<proxyId>.key` file instead, or there is no MCP, run
`scripts/verify.sh list <proxyId>` with `LE_KEY_FILE` set. See
[After the token](#after-the-token) for the listing errors.

Then tell the operator how it stays listed:

- **Daily re-check.** Lightning Enable re-checks every verified proxy once a
  day; `nextCheckAt` shows the next run. Leave the token published for as long
  as the proxy should stay verified. A passing check resets `failures` to 0; a
  failing one adds one, and the proxy stays verified.
- **The three-failure rule.** When a daily re-check finds three consecutive
  failed checks, the proxy becomes unverified: it is unlisted from the
  registry, agent discovery, and Nostr, and a claimed proxy is limited again.
  The proxy keeps working by its direct URL; it is never deleted or
  deactivated. The re-check allows more time than `verify`, but a server that
  stops answering counts as failing.
- **Recovery.** Publish the token again (or issue a new one), verify, and turn
  listing back on. Listing doesn't come back by itself.

## States that need no action

The operator may see two `method` values that no check produces:

- **`grandfathered`:** the proxy was already publicly listed when ownership
  verification was introduced. It stays verified and listed, the daily
  re-check skips it, and issuing a token does not unlist it. To replace it with
  a real method, publish a token and verify; until a check succeeds it keeps
  its standing.
- **`platform`:** a Shopify store entry that Lightning Enable operates. Its
  target is Lightning Enable's own host, so the platform vouches for it, and
  the daily re-check skips it.

Neither needs anything from the operator. Say so and stop.

## Errors

Repeat `error` and `message` (or `detail`) to the operator. `Retry-After`, when
present, says how many seconds to wait. Nothing here charges anything, so a
retry costs only rate limit.

### Before the token

`state` and `token` (steps 1 and 2).

| Error | Tell the operator | Then |
|---|---|---|
| 401 `Merchant authentication required`, or the key is refused | The API key is missing, wrong, or no longer works (a replayed claim rotates the key). | Point `LE_KEY_FILE` at the current key, or store it in `config.json`. No blind retry. |
| 404 `Proxy not found` | No proxy with that ID on this account. Another account's proxy answers the same. | Check the proxy ID. No retry. |
| 429 | Too many requests: the `POST` calls allow 10 per minute per key. | Wait `Retry-After`, then once more. |
| `exists: you already hold a token` (`verify.sh`) | A token for this proxy is already saved locally. | Publish that one. Only with a yes, `--reissue`. |
| `this proxy is verified` (`verify.sh`) | A new token would unverify and unlist it. | Stop, or `--reissue` with a yes. |
| `has no verification.token` (`verify.sh --from-claim`) | The claim answer was a replay or the `sell_url` result, which carries no token. | `scripts/verify.sh token <proxyId>`. |
| HTTP `000` | No answer reached the agent. | Run it again. |

### After the token

`verify`, `poll`, and the listing (steps 4 to 6).

| Error | Tell the operator | Then |
|---|---|---|
| 409 `verification_token_required` | This proxy has no token yet (`tokenEndpoint` is in the problem body). | Issue one (step 2), publish it, verify. |
| 401, 404, 429, HTTP `000` | As [before the token](#before-the-token). | As above. |
| 422 `ownership_verification_required` on listing | The proxy isn't verified, or lost verification while the request ran (`verify_endpoint` names the check). Other settings were saved. | Verify (step 4), then list again. |
| 402 `plan_feature_disabled` on listing | The account's plan doesn't include registry listing. Read `message` to the operator. | Stop. No retry. |
| 422 `listing_verification_failed` on listing | The listing gate refused the proxy for another reason, often no price above zero on its routes. Read `message`. | Fix what it names, then list again. |

### During the check

`verify` answered 200 with `verified: false` or `pending: true`. Match the
`reason` text exactly; the reason never contains the token.

| `reason` contains | What it means | Then |
|---|---|---|
| `The target URL cannot be verified: ` | The proxy's target uses an IP address, `localhost` or an internal domain, a port other than 80 or 443, or a scheme other than `http` or `https`. No method ran. | Point the proxy at the API's public hostname, then issue a token and verify again. |
| `The target host was refused before any request: ` | The host resolves to a private, loopback, or link-local address, or doesn't resolve. No request or TXT lookup was made. | Fix the target. No retry until then. |
| `the host check did not finish within ` or `the host check failed (` | Lightning Enable couldn't look up the target host in time. | Retry; if it persists, check the hostname's DNS. |
| `answered HTTP 404` (for `/.well-known/lightning-enable.json`) | The file isn't at the host root, or a CDN still caches the old `404`. | Check the path and host; purge the cache. Then retry. |
| `answered with a redirect (HTTP ` ... `), which is not followed` | Redirects never count: apex to `www`, `/v1` to `/v1/`, or a sign-in page. | Serve the file, or the header, on the target itself, without the redirect. |
| `is larger than 4096 bytes` | The file is too big. | Serve only the `verify` field. |
| `is not valid JSON` | The file doesn't parse. | Serve exactly `{"verify":"<token>"}`, straight quotes, no comments. |
| `has no "verify" field` | The key is missing or misspelled. | The key is `verify`, in lowercase. |
| `"verify" must be a string or an array of strings` | The value isn't quoted. | Quote the token, or use an array of quoted tokens. |
| `"verify" does not contain this proxy's current token` | An old or mistyped token, or a cached old file. | Publish the latest token; purge the cache. |
| `no TXT record at _lightning-enable.` | No record at that name yet, or it hasn't propagated. | Check the name (the zone-appending trap in step 3), then `poll`. |
| `contains this proxy's current token` (after `no TXT record at ...`) | Records exist at the name, but none is exactly the current token. | Remove quotes, prefixes, and old tokens. |
| `without X-Lightning-Enable-Verify` | The base URL answered without the header. | Add it to every response there, including errors and `HEAD`. |
| `X-Lightning-Enable-Verify does not carry this proxy's current token` | The header has a different value. | Publish the latest token. |
| `no answer within ` | One request timed out. | Make the file or base URL answer quickly (no cold start), or use `dns-txt`. Retry. |
| `could not be reached (` | The connection failed: `NameResolutionError` (the hostname doesn't resolve), `ConnectionError` (nothing answered, or refused), `SecureConnectionError` (the TLS certificate is expired, self-signed, or for another host). | Check that the host answers HTTPS on port 443 with a valid certificate, for example `curl -I https://{target host}/.well-known/lightning-enable.json`. |
| `failed (` | An unexpected error type, named in the parentheses. | Retry once; if it repeats, contact support. |
| `the check did not finish within ` ... `s, so nothing was recorded. Try again.` | `pending: true`: the whole check ran out of time. Not a failure. | Wait `retryAfterSeconds`, then `verify` or `poll`. |
| `The verification token was re-issued while this check ran. Publish the new token and check again.` | A new token replaced the one this check found. | Publish the new token, then verify. |

For anything else, give the operator the `reason` word for word and point them
at [Verify ownership of your API](https://docs.lightningenable.com/products/agentic-commerce/verify-ownership)
and [lightningenable.com](https://www.lightningenable.com) for support.

## Safety rules

- **Read the state first.** Never issue a token for a proxy verified by a live
  check without the operator's yes: it unverifies and unlists it.
- **The token stays in its file.** Publish it only in the file, the TXT record,
  or the header; never in chat logs, issues, or commits other than the deployed
  well-known file. Never print the API key.
- **Change only what you were given access to.** Write the well-known file only
  to a site you deploy; otherwise give the operator the records and wait.
- **Bounded checks.** `poll` runs at most 10 attempts; stop when it ends and
  explain the reason instead of looping.
- **The operator owns the listing.** Turn it on only after they say yes.

## Example

> Operator: "List my endpoint forecast-api-a1b2 publicly."
>
> 1. `scripts/verify.sh state forecast-api-a1b2`: `verified: false`,
>    `tokenIssued: true`, target host `api.example.com`.
> 2. The claim ran through `sell_url`, so there's no token to hand:
>    `scripts/verify.sh token forecast-api-a1b2` saves a new one.
> 3. No deploy access to `api.example.com`. Tell the operator: a TXT record
>    named `_lightning-enable.api.example.com` (enter `_lightning-enable.api`
>    if the provider appends `example.com`) with the token as its value, or the
>    `X-Lightning-Enable-Verify` header at `https://api.example.com/v1/`.
>    The operator adds the TXT record.
> 4. `scripts/verify.sh poll forecast-api-a1b2`: the first attempt says
>    `no TXT record at _lightning-enable.api.example.com`; the second answers
>    `verified: true`, `method: dns-txt`.
> 5. "Verified by DNS. List it publicly?" Yes:
>    `l402_producer(action="publish", proxy_id="forecast-api-a1b2")`.
> 6. Explain the daily re-check, the three-failure rule, and that the TXT record
>    stays in place.
