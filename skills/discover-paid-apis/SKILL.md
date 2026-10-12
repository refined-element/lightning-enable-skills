---
name: discover-paid-apis
description: >-
  Find paid APIs that speak L402, show what each costs and how many calls the
  wallet and budget can afford, read the chosen API's manifest without paying,
  then make ONE paid call after an explicit yes and report the sats spent. Use
  when the user is looking for a paid API or data source and does not have a URL
  yet ("find me a weather / finance / health API I can pay for", "what paid APIs
  are out there", "is there an L402 API for X", "try a paid API"). Do NOT use to
  pay a URL the user already has (use pay-l402-anywhere), to answer a research
  question with cited paid data (use cited-answer), to sell an API (use
  producer-setup or create-l402-proxy), or when no wallet is connected yet (use
  agent-wallet-setup first).
---

# Discover paid APIs

Find something worth paying for, see what it costs before spending anything, and
try it once. The L402 registry lists APIs that charge per call over Lightning;
each listing points at a manifest with the endpoints and their prices. You
search, the human picks, you read the manifest for free, and one paid call
proves the API answers.

**Lightning Enable does not hold funds; the wallet facilitates custody and
settlement.** Each sat goes from the human's wallet to the API's seller.

## What is automated, and what is not

**Automated:** reading the budget and balance, searching the registry, the
affordability math, reading a manifest without paying, the one paid call, and
the spend report.

**Not automated. The human decides these:**

- **What to look for:** a topic, a category, or a site they already know.
- **Which API to try,** from the table you present.
- **Whether to pay,** at the moment of payment, with the price stated.

## What you need

- The [Lightning Enable MCP](https://github.com/refined-element/lightning-enable-mcp)
  server, connected to a wallet that returns preimages (NWC, LND, or Strike). If
  `get_balance` or `setup_wallet` says no wallet is configured, stop and use
  [`agent-wallet-setup`](../agent-wallet-setup/).
- No Lightning Enable account. Searching and paying need only the wallet.
- Tools this skill uses:
  - `budget`: `action="status"` for the limits and what the session has left.
  - `get_balance`: the real funds.
  - `discover_api`: searches the registry (`query`, `category`) or reads one
    API's manifest (`url`). It never pays.
  - `access_l402_resource`: fetches a URL with GET or HEAD and pays an L402
    challenge up to `max_sats`.
  - `receipts`: `source="session"` lists this session's payments.

Argument names below are the Python server's `snake_case`. The .NET server takes
the same arguments in `camelCase`: `budget_aware` → `budgetAware`, `max_sats` →
`maxSats`, `confirmation_nonce` → `confirmationNonce`. Response fields are
`camelCase` in both ports, with two exceptions this skill meets: `discover_api`
answers in `snake_case` in both (`manifest_url`, `default_price_sats`,
`affordable_calls`), and `access_l402_resource` shapes a paid result differently
in each port (step 5 has the table).

## Flow

### 0. Ask what the human wants

Get two answers, in one message:

1. **What to find:** "What should the API do?" A keyword (`weather`,
   `geocoding`), a category (`ai`, `data`, `finance`), or a site the human
   already knows.
2. **The ceiling for a trial call:** "What is the most one test call may cost?"
   In sats.

Searching and reading manifests cost nothing, so you don't need a yes for steps
1 to 4. Step 5 pays, and needs its own yes.

### 1. Read the budget and the balance

```
budget(action="status")
get_balance()
```

Note two numbers: the sats the session budget has left, and the wallet balance.
The smaller one bounds how much the agent can spend. If the budget reports that
no price is available and the limits are in USD, payments are refused until a
price source recovers; say so before you search.

### 2. Search the registry

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
  data API. Leave it out of the table.
- **No results:** the response says so and suggests other keywords. Try a
  broader keyword or a category once, then tell the human nothing matched. Never
  invent an API.
- **A registry error or redirect:** the response names the registry URL it
  called. Report it; the human can still name a site for step 4.

**The human names a site instead.** `discover_api(url="https://api.example.com")`
looks for a manifest at `/.well-known/l402-manifest.json`,
`/.well-known/l402.json`, `/l402-manifest.json`, and `/l402.json`, then at the
URL itself. A URL that ends in `.json` is tried first. Skip to step 4 with what
it returns.

### 3. Present a short table

Show the human the real candidates, cheapest first:

| API | What it does | Price per call | Calls you can afford |
|---|---|---|---|
| `name` | one line from `description` | `default_price_sats` sats | the smaller of `affordable_calls` and balance ÷ price |

- **Calls you can afford:** `affordable_calls` counts against the session
  budget; the wallet balance divided by the price counts against the funds. Show
  the smaller, and say which one binds.
- **`affordable_calls: "unknown"`** means the price or the budget could not be
  determined. Show "unknown" and treat the API as not proven affordable. Never
  read it as free or unlimited.
- **No `default_price_sats`:** the listing has no default price. Write "see the
  manifest" and let step 4 answer it.
- **Nothing affordable:** say so plainly. The human can fund the wallet, raise
  their limits in the config file themselves, or pick a cheaper API.

Let the human pick one.

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
