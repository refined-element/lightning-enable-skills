---
name: lightning-enable-account
description: >-
  Keep a Lightning Enable account healthy from the agent: read the plan, how it
  is paid, and the paid-through date; explain the account's state in plain
  words; renew or prepay the Agentic Commerce plan in sats over L402 with
  renew_lightning_enable_subscription after an explicit human yes; and confirm
  the credit landed. Use when the user asks "what plan am I on", "is my account
  paid", "when does my trial end", "renew my subscription in sats", "keep my
  account on the paid plan", "did my renewal go through", or when an API call
  returns 403 with action_required renew_subscription. Do NOT use to create an
  account (use producer-setup), to sell an API or a one-off resource (use
  create-l402-proxy or sell-this), to pay someone else's L402 endpoint (use
  pay-l402-anywhere), or to change card billing (send the human to the
  dashboard or support@lightningenable.com).
---

# Lightning Enable account

Read where the account stands, say it in plain words, and, with the human's
yes, pay the next period in sats from the agent's own wallet. No card, no
checkout page. The account is the one behind the configured merchant API key.

When sats move: the payment settles with the payment provider of the Lightning
Enable account that receives renewals. **Lightning Enable does not hold funds;
the payment provider facilitates custody and settlement.**

## What this skill does, and what it does not

**Does:** read the plan, subscription status, payment method, and paid-through
date; work out whether a sats renewal is open and why not if it is closed;
renew or prepay in sats; confirm the credit; read a lapse `403`.

**Does not:** create an account (that is step 2 of
[`producer-setup`](../producer-setup/)), sell anything, pay someone else's
endpoint, or touch card billing. Agentic Commerce is payable two ways, by card
through the dashboard checkout or in sats over L402, and both buy the same plan.
This skill runs only the sats path. For card changes, send the human to the
[dashboard](https://api.lightningenable.com/dashboard) or
support@lightningenable.com.

## What you need

- **[Lightning Enable MCP](https://github.com/refined-element/lightning-enable-mcp)**
  (Model Context Protocol server) **2.1.0 or later** for renewal. Earlier
  versions do not have `renew_lightning_enable_subscription`.
- **The merchant API key**, loaded by the MCP. It reads
  `LIGHTNING_ENABLE_API_KEY` from the environment first and falls back to
  `lightningEnableApiKey` in `~/.lightning-enable/config.json`. The environment
  variable wins: if both are set, the file is ignored. The key-gated tools load
  the key at startup, so a key that `create_lightning_enable_account` wrote to
  the file needs an MCP restart. **Never print the key.** Report it as `<set>`
  or `<not set>`.
- **For a renewal, a funded wallet that returns Lightning preimages:** an NWC
  (Nostr Wallet Connect) wallet such as CoinOS, Alby Hub, or CLINK; an LND
  (Lightning Network Daemon) node; or Strike. OpenNode and Primal's NWC do not
  return preimages and cannot pay an L402 challenge. If no wallet is connected,
  use [`agent-wallet-setup`](../agent-wallet-setup/) first.
- Tools this skill uses:
  - `l402_producer` with `action="status"`: plan tier, subscription status,
    `l402Enabled`, receive wallet, onboarding checklist. Read-only.
  - `renew_lightning_enable_subscription`: pays the renewal's L402 challenge.
  - `get_balance`: the wallet's real funds.
  - `budget` with `action="status"`: the spend limits and approval tiers.
  - `receipts` with `source="durable"`: the wallet's own payment log.

Argument names below are the Python server's `snake_case`. The .NET server
takes the same arguments in `camelCase`: `max_sats` is `maxSats`,
`confirmation_nonce` is `confirmationNonce`. Response fields are `camelCase` in
both.

### Two reads the MCP does not cover

`l402_producer(action="status")` does **not** return the paid-through date, the
payment method, or whether a sats renewal is open. Those live in two API
routes. Both take the key in the `X-API-Key` header:

- `GET /api/merchant/subscription/renew`: **the quote.** Returns `eligible`,
  `reason`, `priceSats`, `periodDays`, `paymentMethod`, `currentPeriodEnd`,
  `periodEndIfPaid`, and `endpoint`. It creates no invoice and has no side
  effects. It is exempt from subscription enforcement, so it answers even when
  the account has lapsed and every other route returns `403`.
- `GET /api/merchant/subscription`: plan and limits plus `paymentMethod`,
  `currentPeriodEnd`, a `renewal` object (`eligible`, `reason`, `priceSats`,
  `periodDays`, `endpoint`), and `payments[]`, the last 12 sats renewal receipts
  (`paymentHash`, `amountSats`, `periodStart`, `periodEnd`, `createdAt`,
  `channel`). This route is subject to enforcement, so a lapsed account gets a
  `403` here.

If the host has a shell, read them without echoing the key. The key goes into a
shell variable and from there into the header; it never reaches the output:

```bash
LE_KEY="${LIGHTNING_ENABLE_API_KEY:-$(python3 -c 'import json, os; print(json.load(open(os.path.expanduser("~/.lightning-enable/config.json")))["lightningEnableApiKey"])')}"
curl -s https://api.lightningenable.com/api/merchant/subscription/renew -H "X-API-Key: $LE_KEY"
curl -s https://api.lightningenable.com/api/merchant/subscription -H "X-API-Key: $LE_KEY"
```

PowerShell:

```powershell
$k = $env:LIGHTNING_ENABLE_API_KEY
if (-not $k) { $k = (Get-Content -Raw "$HOME/.lightning-enable/config.json" | ConvertFrom-Json).lightningEnableApiKey }
Invoke-RestMethod https://api.lightningenable.com/api/merchant/subscription/renew -Headers @{ 'X-API-Key' = $k }
```

Never run `echo $LE_KEY`, never paste the key into a command line you show the
human, and never add `-v` to `curl` or `-Verbose` to `Invoke-RestMethod`
(verbose output can print the request headers). If the MCP points at another deployment through
`LIGHTNING_ENABLE_API_URL`, use that base URL instead.

If the host has no shell, the human can read the same facts on the dashboard's
[Settings page](https://api.lightningenable.com/dashboard/settings): plan,
payment method, paid-through date, and, when the account can renew in sats, a
**Renew with Lightning** panel that states the price and period.

## Flow

### 1. Read the account (free)

```
l402_producer(action="status")
```

- **Success:** read `merchant.planTier`, `merchant.subscriptionStatus`,
  `merchant.isActive`, `merchant.l402Enabled`, `merchant.name`, and
  `merchant.merchantId`, plus `receive.provider` and
  `receive.nwcConnectionString` (`"<set>"` or `"<unset>"`). The checklist and
  recent challenges come along too; this skill does not need them.
- **"API key required":** no key is loaded. If the human created the account in
  this session, the MCP needs a restart. Do **not** run
  `create_lightning_enable_account` again: that pays for a second account.
- **`success: false` with `httpStatus: 403`:** the account is blocked by
  subscription enforcement. This is the lapse case. Go to
  [Reading a 403](#reading-a-403) and use the quote, which still answers.

Then read the quote (and, if it answers, `GET /api/merchant/subscription`) as
shown above. The quote is the truth for the price, the period, eligibility, and
the paid-through date.

### 2. Explain the state in plain words

Name the plan from `planTier`: `free` is the **Free Producer Sandbox**,
`individual` is **Agentic Commerce**, and `l402` is the **Business** plan. Then
say how it is paid, the paid-through date, the days left, and whether a sats
renewal is open.

| What you read | What it means | Sats renewal |
|---|---|---|
| `planTier: free` | Free Producer Sandbox: a capped free tier, not a shutdown | Open. The period starts at payment. |
| `individual`, `subscriptionStatus: trialing`, quote `eligible: true`, `paymentMethod: null` | Fast Lane trial (paid in sats at signup, no card). `currentPeriodEnd` is the trial's end. | Open. The paid period starts when the trial ends, so paying early loses no trial days. |
| `individual`, `trialing` or `active`, quote `reason: StripeSubscriptionActive` | Card plan or card trial through the dashboard checkout | Closed while the card subscription is not canceled. The card is billed by Stripe; manage it in the dashboard. |
| `individual`, `active`, `paymentMethod: l402` | Paid in sats. `currentPeriodEnd` is the paid-through date. | Open. A payment adds a period to the current end, up to 365 days ahead. |
| `subscriptionStatus: canceled` (card) | The card subscription was canceled | Open. Paying in sats moves the account off Stripe. |
| `paymentMethod: bitcoin` | Paid through the legacy Bitcoin checkout | Open while that Bitcoin period runs; the sats period starts when it ends. |
| `planTier: l402`, quote `reason: BusinessPlanContactSupport` | Business plan, arranged directly | Closed. Email support@lightningenable.com. |
| quote `reason: PrepaidCapReached` | Already paid more than 365 days ahead | Closed until the paid-through date is within 365 days. |
| quote `reason: ManuallyDisabled` | An operator disabled the account | Closed. Email support@lightningenable.com. |
| quote `reason: Disabled` | Sats renewals are switched off on this deployment | Closed. Pay by card, or try later. |

Compute days left from `currentPeriodEnd`. Treat a timestamp without a `Z`
suffix as UTC; some responses omit it.

Say it the way a person would: "You are on Agentic Commerce, paid in sats
through 10 November. That is 29 days from today. You can prepay another period
in sats if you want."

### 3. Renew in sats (only with the human's yes)

1. **Quote.** Read `priceSats`, `periodDays`, and `periodEndIfPaid` from
   `GET /api/merchant/subscription/renew`. The server sets the price; do not
   quote one from memory or from this file. If the human asks what the plans
   cost, point them at [lightningenable.com](https://www.lightningenable.com).
2. **Check the wallet and the leash.**

   ```
   get_balance()
   budget(action="status")
   ```

   Stop if the balance is below `priceSats`. Note whether `priceSats` falls
   above the auto-approve tier; if it does, a confirmation code is coming.
3. **Confirm the account.** The tool renews the account behind the configured
   key, and the environment variable beats the config file. Name the account
   from `status` (`merchant.name`, `merchant.merchantId`) so the human knows
   which account they are paying for.
4. **Ask, and wait.** "Renewing Agentic Commerce costs `<priceSats>` sats for
   `<periodDays>` days. Paid through `<periodEndIfPaid>` after this payment.
   Shall I pay it from your wallet?" Do not pay without an explicit yes to that
   number.
5. **Pay.** Set the cap to the quoted price:

   ```
   renew_lightning_enable_subscription(max_sats=<priceSats>)
   ```

   `max_sats` is only the most this call may pay. The tool's built-in default
   ceiling is 50,000; always pass the quoted price instead, so the cap means
   what the human agreed to. If the invoice is above `max_sats`, the tool
   refuses before paying (`activation.paid: false`): re-read the quote, because
   the price changed, and ask again.

**Success** looks like this. It never contains the macaroon or the preimage:

```json
{
  "success": true,
  "currentPeriodEnd": "<the next paid-through date>",
  "paidSats": "<sats paid>",
  "paymentHash": "<64 hex characters>",
  "alreadyCredited": false,
  "planTier": "individual",
  "activation": { "paid": true, "amountSats": "<sats paid>" }
}
```

Report `currentPeriodEnd` and `paidSats`, and keep `paymentHash` as the
reference. Every call to the tool mints a fresh challenge, so **a second call
buys a second period.** Never call it again to "check" a renewal.

**`alreadyCredited: true`** means the server had already credited that exact
payment and charged nothing more; `currentPeriodEnd` is the date that payment
produced, which can be earlier than the account's paid-through date if a later
payment extended it. The tool always mints fresh, so this appears mainly when a
raw L402 client replays a token.

**A confirmation code.** When `max_sats` is above the operator's auto-approve
threshold, the result is `requiresConfirmation: true`. The MCP sends a 6-character
code to the human on its approval channel: its console by default, or a webhook
or file on a hosted server. The code never appears in a tool result, so you
cannot read it. Ask the human for it, then re-call with **the same**
`max_sats`:

```
renew_lightning_enable_subscription(max_sats=<same cap>, confirmation_nonce="<code from the human>")
```

The code is bound to the amount, this tool, and the renew URL, is single-use,
and expires (120 seconds by default). Never guess one. On the .NET server, a
host that supports MCP elicitation may instead show the human an approve
prompt directly. If the result says the renewal was **refused, not queued**
(`requiresConfirmation: false` with a `confirmationChannel`), no human can be
asked on this server: retrying does not help until the operator changes the
configuration.

**Paid but not credited.** If a result carries `activation.paid: true` with a
`warning`, a payment left the wallet but the renewal did not complete. **Do not
re-run the tool**: it cannot resend the same credential, so a re-run pays again.
Give the human the `paymentHash` (or the time of the call, if there is no hash)
and send them to support@lightningenable.com. `statusCode` and `errorCode` say
what the server answered.

### 4. Verify

- `GET /api/merchant/subscription`: `paymentMethod` is `l402`,
  `currentPeriodEnd` matches the tool result, and `payments[0].paymentHash`
  matches the tool's `paymentHash`. A renewal made through MCP 2.1.0 shows
  `channel: "mcp-dotnet"` or `"mcp-python"`.
- `receipts(source="durable")`: the wallet-side record. A renewal is an entry
  with `kind: "l402"` and `context: "l402_subscription_renewal"`.
- `l402_producer(action="status")`: `planTier: individual`, and the call
  succeeds again if the account had lapsed.

### 5. Hand off

Tell the human:

- **The paid-through date**, and that nothing renews by itself: there is no
  automatic sats charge.
- **What happens at the end:** API calls answer `403` with
  `action_required: "renew_subscription"` and a `renew.endpoint`. Within a day
  (a daily job at 03:30 UTC) the account moves to the Free Producer Sandbox
  and an email goes out. The key keeps working within the free limits, the
  account is never deactivated, and a sats payment restores the paid plan at
  any time. A payment after a lapse starts its period at the moment of payment.
- **How to prepay:** each payment adds one period (`periodDays`) to the later of
  today and the current paid-through date, up to 365 days ahead. Past that,
  `409 prepaid_cap_reached`.
- **Where the record lives:** `GET /api/merchant/subscription` (`payments[]`),
  the dashboard Settings page, and `receipts(source="durable")`.
- **Support:** support@lightningenable.com, with the payment hash.

## Period math

| Account state when the payment lands | The paid period runs from |
|---|---|
| Fast Lane trial | The trial's end. Paying early loses no trial days. |
| Sats period still running | The current paid-through date (the payment adds to it) |
| Lapsed, Free Producer Sandbox, or canceled card | The moment of payment |
| Legacy Bitcoin period still running | The end of that Bitcoin period |

One payment buys one period. A challenge request is refused while the account is
paid more than 365 days ahead; a token already paid is still credited.

## Reading a 403

An agent that hits a `403` in the middle of other work should come here. The raw
API body carries snake_case fields:

```json
{
  "error": "Subscription period expired",
  "message": "Your Lightning-paid subscription period has ended. Renew now with an L402 payment, or the account moves to the Free Producer Sandbox within 24 hours.",
  "subscription_status": "active",
  "current_period_end": "2026-11-10T14:03:22.0000000Z",
  "action_required": "renew_subscription",
  "renew": { "endpoint": "/api/merchant/subscription/renew" }
}
```

Branch on `action_required`, then on whether `renew` is present:

| `action_required` | Other fields | What it means | Do this |
|---|---|---|---|
| `renew_subscription` | `renew.endpoint` present | The sats-paid period ended | Run step 3. The renew endpoint is exempt from enforcement. |
| `renew_subscription` | no `renew` | A card subscription is canceled, unpaid, incomplete, or expired | Read the quote. If `eligible`, sats renewal works; if `reason` is `StripeSubscriptionActive`, the card must be canceled or fixed in the dashboard first. |
| `subscribe` | `current_plan` | A paid tier with no subscription, for example a Fast Lane trial that ended minutes ago | Read the quote. Sats renewal is usually open. If nobody pays, a Fast Lane trial account moves to the Free Producer Sandbox. |
| `update_payment_method` | `subscription_status: past_due` | The card payment failed | Card billing: send the human to the dashboard. Sats renewal is closed while the card subscription exists. |
| `contact_support` | `support_email` | The account is inactive or disabled | Email support@lightningenable.com. Do not try to pay. |
| `upgrade_plan` | `feature`, `required_plan` | A feature the plan does not include | Not a lapse. On the Free Producer Sandbox, a sats renewal buys Agentic Commerce; confirm with the human first. |

**Through the MCP**, `l402_producer` reports the same refusal in its own shape:
`success: false`, `httpStatus: 403`, `errorCode` carrying the API's `error`
string (such as `"Subscription period expired"`), and `error` carrying the
message. It does not pass `action_required` through, so read the quote to decide.

## What can go wrong

The tool reports the server's slug as `errorCode` and the HTTP status as
`statusCode`. **`activation.paid` decides everything:** `false` means nothing
was charged; `true` means sats left the wallet, so never re-run the tool.

| Symptom | Likely cause | Do this |
|---|---|---|
| `409 stripe_subscription_active` | A card subscription that is not canceled (active, trialing, past due, unpaid, incomplete, or paused) | The human cancels it in the dashboard billing portal, then renew in sats. Or keep paying by card. |
| `409 business_plan_contact_support` | The account is on the Business plan | Email support@lightningenable.com. |
| `409 prepaid_cap_reached` | Already paid more than 365 days ahead; the body carries `currentPeriodEnd` | Wait until the paid-through date is within 365 days. |
| `403 account_disabled` | An operator disabled the account | Email support@lightningenable.com. |
| `429` | More than 5 challenge requests a minute from this key | Wait a minute. |
| `503 l402_subscription_unavailable` or `l402_subscription_misconfigured` | Sats renewals are off or not set up on this deployment | Try later, pay by card, or email support. |
| `503 upstream_unavailable` or `challenge_persist_failed`, unpaid | No invoice was issued | Try again shortly, once. |
| `503 renewal_contended`, after paying | Another request was updating the account; nothing was credited yet | Through the tool: do not re-run (that pays again); send the payment hash to support. A raw L402 client retries the same request with the same `Authorization` header once, after `Retry-After`. |
| `401 invalid_l402_token`, after paying | The token was refused, for example because it was minted below a price that rose before it was redeemed. This refusal is permanent for that token. | Through the tool: do not re-run; send the payment hash to support (a payment at the old price is never credited). A raw L402 client holding an **unpaid** old-price challenge mints a fresh one instead. |
| A `409`, `403`, or `503` after paying with a raw L402 client | The cause is fixable and nothing was credited | Keep the token. It stays redeemable for 7 days after its challenge was issued; redeem it once the cause is fixed. It is credited at most once. |
| "Invoice amount ... exceeds maximum" | The price is above `max_sats` | Re-read the quote and ask the human again. Nothing was paid. |
| "denied by budget policy" | The budget caps do not allow `max_sats` | Show `budget(action="status")`. Only the operator can raise the caps. |
| "No wallet configured" | The MCP has no wallet | Connect one with [`agent-wallet-setup`](../agent-wallet-setup/). |
| The API key was rejected (`statusCode: 401`, unpaid) | Wrong or revoked key, or the environment variable points at another account | Check which key is loaded; never print it. |
| The wallet paid but no preimage came back | OpenNode or Primal NWC | Use a wallet that returns preimages; send the payment hash to support for the payment already made. |

Full error bodies: [error reference](https://docs.lightningenable.com/api-reference/errors#lightning-renewal-errors).

## Safety rules

- **Explicit human yes before any payment**, with the quoted sats and period
  stated. A standing instruction to "keep the account paid" still needs a yes
  per payment unless the human set that up in the operator's approval tiers.
- **One L402 payment at a time.** Finish one 402, pay, and credit cycle before
  starting another.
- **Never re-run the renewal tool to check or to recover.** Every call pays a
  fresh invoice. Verify with the reads in step 4.
- **Never print secrets:** the API key, NWC connection strings, macaroons,
  preimages, Strike keys, LND macaroons. Report `<set>` or `<not set>`.
- **Never quote a price from memory.** The quote is the price.
- **Stay inside the budget.** `budget(action="tighten")` can lower the caps
  before a payment; nothing in this skill raises them.

## Example

> User: "Is my Lightning Enable account still paid? If it's running out, renew
> it in sats."
>
> 1. `l402_producer(action="status")` → Agentic Commerce, `active`, account
>    "Weather API Co" (merchant 412).
> 2. Quote → `eligible: true`, `paymentMethod: l402`, paid through
>    18 October, `periodEndIfPaid` 17 November.
> 3. "You are on Agentic Commerce, paid in sats through 18 October, 6 days from
>    today. Renewing costs `<priceSats>` sats for 30 days and moves the date to
>    17 November. Pay it from your wallet?" The human says yes.
> 4. `get_balance()` → enough. `budget(action="status")` → inside the
>    auto-approve tier.
> 5. `renew_lightning_enable_subscription(max_sats=<priceSats>)` → `success`,
>    paid through 17 November, payment hash kept.
> 6. `GET /api/merchant/subscription` → `payments[0]` matches the hash.
>    `receipts(source="durable")` shows `l402_subscription_renewal`.
> 7. "Renewed. Paid through 17 November. Nothing renews by itself; I can
>    prepay again closer to the date."
