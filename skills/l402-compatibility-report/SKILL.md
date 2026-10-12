---
name: l402-compatibility-report
description: >-
  Diagnose whether an endpoint correctly implements L402 (HTTP 402 with a
  Lightning invoice, a macaroon, and a preimage) and whether it is ready for
  buyers and marketplaces such as Amazap. Inspects the unpaid 402 challenge
  without spending: every WWW-Authenticate scheme, the invoice amount, payment
  hash, and expiry, resource binding, and listing readiness. Optionally runs
  one explicitly approved, capped paid test through HTTP 2xx fulfillment. Use
  when a developer asks to check, test, debug, or diagnose an L402
  endpoint ("is my L402 endpoint working", "why won't my endpoint list on
  Amazap", "check this paywall", "run an L402 compatibility report"), or after
  producer-setup, create-l402-proxy, or l402-server-integration to prove the
  result. Do NOT use to buy something for its content (use
  pay-l402-anywhere), to find a paid API (use discover-paid-apis), or to build
  a paywall (use producer-setup, create-l402-proxy, or l402-server-integration).
---

# L402 compatibility report

Tell a developer, precisely, how far their endpoint gets through the L402 flow:
does the unpaid request get a well-formed challenge with a priced invoice, does
a paid request get the resource, and is it ready for a marketplace listing. The
check is deterministic: a standard-library Python script makes the unpaid
request, parses the challenge, decodes the invoice, and writes the report.

The default check never pays. A paid check is a separate step: one payment, at
an amount the human approved, through the Lightning Enable MCP. Lightning
Enable does not hold funds; the payment provider facilitates custody and
settlement.

## What is automated, and what is not

**Automated:** the unpaid request, URL safety checks, bounded redirects,
challenge parsing, invoice decoding, binding analysis, the marketplace checks,
the preflight verdict for a paid check, evidence validation, and the report in
Markdown or JSON.

**Not automated. The human decides these:**

- **Which endpoint, method, and parameters** to check.
- **Whether to pay,** for the paid check, at the exact amount, on the exact
  endpoint.
- **Whether to list** the endpoint anywhere. This skill never publishes.

## What you need

- Python 3.10 or later. The script uses the standard library only.
- For the read-only check: nothing else. No wallet, no account, no API key.
- For the paid check: the
  [Lightning Enable MCP](https://github.com/refined-element/lightning-enable-mcp)
  connected to a wallet that returns preimages (NWC, LND, or Strike). If no
  wallet is connected, use [`agent-wallet-setup`](../agent-wallet-setup/) first.
- Tools the paid check uses:
  - `budget`: `action="status"` for the caps and what the session has left.
  - `get_balance`: the real funds.
  - `access_l402_resource`: fetches a URL with GET or HEAD and pays an L402
    challenge up to `max_sats`. One call is the whole paid flow.
  - `receipts`: `source="durable"` for the wallet's receipt of the payment.

Argument names below are the Python server's `snake_case`. The .NET server takes
the same arguments in `camelCase`: `max_sats` → `maxSats`, `confirmation_nonce`
→ `confirmationNonce`.

The six classifications, the redaction rules, and the ambiguous-payment rule
are shared with the other skills in
[L402 verification levels](https://github.com/refined-element/lightning-enable-skills/blob/main/references/l402-verification-levels.md).
This skill states the parts it needs below.

## Flow

### 0. Ask what to check

In one message, get:

1. **The URL** and, if it isn't `GET`, the method. Query parameters go in the
   URL.
2. **Non-secret headers or a body,** only if the endpoint needs them before it
   can answer: `Accept`, a content type, or a harmless custom header. `--header`
   takes non-secret headers only. The script refuses credential-bearing header
   names with an error: `Authorization`, `Cookie`, `Proxy-Authorization`, and
   any name containing `key`, `token`, `secret`, `password`, or `session`, in
   any case. There is no other way to pass them. An endpoint that needs its own
   credential before it will issue a 402 is out of scope for this check: report
   it as "401 before challenge", with the fix from the table under What can go
   wrong.
3. **Whether a paid check is wanted,** and if so the most it may cost, in sats.

### 1. Run the read-only check

From this skill's folder:

```bash
python scripts/l402_check.py "https://api.example.com/forecast?city=paris"
python scripts/l402_check.py "https://api.example.com/search" --method POST --header "Accept=application/json"
```

Add `--max-sats <cap>` when a paid check might follow; the report then carries
a preflight verdict. Add `--json` for machine-readable output, and save it when
a paid check follows:

```bash
python scripts/l402_check.py "https://api.example.com/forecast" --max-sats 50 --json > mode-a.json
```

The script makes one unpaid request, then requests `/openapi.json` and
`/llms.txt` at the host root (where Amazap's listing prefill looks). It refuses
localhost, loopback, private, link-local, and cloud metadata addresses,
non-HTTPS public URLs, and redirects into any of those. `--allow-private` admits
local targets, and plain HTTP to them, only when the human is deliberately
testing a local development server on this machine.

### 2. Read the report back

Show the human the classification and the summary, then the sections that
matter:

- **`CHALLENGE_COMPATIBLE`:** the unpaid challenge is valid and the invoice is
  priced. Say plainly that paid fulfillment was **not tested**.
- **`INCOMPATIBLE`:** read the Required fixes section. Each defect maps to one
  fix (see the table below).
- **`INCONCLUSIVE`:** a timeout, a refused target, a server error, or a DNS
  failure. Say which; don't guess.

A response that offers several schemes (`L402` and `Payment`, `LSAT` and
`L402`, or `L402`, `Payment`, and `x402`) is normal. The report classifies the
endpoint by its `L402` challenge (or `LSAT` when there is no `L402`) and lists
the others. `Payment` is its own
scheme, never L402.

### 3. Decide on the paid check

Only when the human asked for it, and only when the preflight says `allowed`:

- The read-only check is `CHALLENGE_COMPATIBLE`.
- The method is GET or HEAD. `access_l402_resource` refuses every other method
  before any payment, so a POST endpoint stops at the read-only check.
- The invoice amount is at or below the human's cap.
- The endpoint and parameters are final, and repeating the call has no harmful
  side effects.

State the payment and **stop for a yes**: "I will call `GET <url>` once through
your Lightning wallet. It costs `<amount>` sats; the cap is `<cap>`. Go ahead?"

### 4. Check the leash

```
budget(action="status")
get_balance()
```

If the session budget or the balance can't cover the amount, stop and say so.
Report only that the balance covers the amount, never the figure, unless the
person asks for it.

### 5. Pay once

```
access_l402_resource(url="<exact url from step 1>", max_sats=<the approved cap>)
```

One call requests the URL, pays the 402's invoice, and retries with the
`Authorization: L402 <macaroon>:<preimage>` header. A server may mint a fresh
invoice for each 402, so the paid invoice need not be the one in the read-only
report; `max_sats` is what bounds it.

- **`requiresConfirmation: true`:** the code went to the human, never to you.
  Ask for it and repeat the same call with `confirmation_nonce="<code>"`.
- **`alreadyPaid: true`:** money moved and the retry failed. **Don't call
  again.** Go to step 6 with what you have.
- **A budget denial or an invoice over `max_sats`:** nothing was paid. Report
  it.
- **Anything else (a tool error, a timeout, or `success: false` without
  `alreadyPaid`):** the outcome is unknown. **Don't call again.** Go to step 6.

Never start a second payment while the first is pending or its outcome is
unknown.

### 6. Record the evidence

Read the payment's receipt:

```
receipts(source="durable")
```

Pick the receipts written since step 5 for this URL and copy each one's
`paymentHash` and `amountSats` into `evidence.json`. The MCP stores the payment
hash as SHA-256 of the preimage, never the preimage itself, so a receipt holds
no credential. The default paid check never moves the token: leave
`payment.l402Token` where it is. Write `evidence.json` with no credential in it
(the script refuses a file that holds one):

```json
{
  "cap_sats": 50,
  "tool_result": {
    "success": true,
    "status_code": 200,
    "content_type": "application/json",
    "body_length": 812,
    "paid_sats": 21,
    "already_paid": false,
    "requires_confirmation": false
  },
  "payments": [{"amount_sats": 21, "status": "settled", "payment_hash": "<64 hex>"}],
  "expected": {"status": 200, "content_type": "application/json"}
}
```

| Evidence field | Python server result | .NET server result |
|---|---|---|
| `status_code` | not returned; leave it out (success implies 2xx) | `statusCode` |
| `content_type` | not returned; leave it out | `contentType` |
| `body_length` | length of `response` | length of `content` |
| `paid_sats` | `paid_sats` | `payment.amountSats` |
| `already_paid` | `alreadyPaid` | `alreadyPaid` |
| `requires_confirmation` | `requiresConfirmation` | `requiresConfirmation` |
| `payments[]` | receipts' `amountSats`, `status`, `paymentHash` | the same |

`expected` is optional: the status and content type the human expects.

### 7. Validate the evidence

`--mode-a` adds the read-only report from step 1:

```bash
python scripts/l402_check.py --evidence evidence.json --mode-a mode-a.json
```

The script compares the receipt's payment hash with the invoice payment hash
from Mode A, and with the macaroon identifier's payment hash when Mode A exposed
one, and the report states whether they match. It also checks that the
authorized retry returned 2xx and that exactly one payment was recorded at or
under the cap. It prints the payment hash and the amount, never a credential. A
run with no preimage and no receipt hash is `INCONCLUSIVE`.

**Optional stronger check.** When the result carries `payment.l402Token` (the
.NET server does), the script can also check the preimage itself. This is the
only way to pass it:

```bash
printf '%s' '<token>' | python scripts/l402_check.py --evidence evidence.json --mode-a mode-a.json --credential-stdin
```

`printf` is a shell builtin, so the token reaches the script on stdin, never as
a script argument. The command text is still visible to anyone who sees the
tool call. Never repeat the token in chat, and never write it to a file.

### 8. Hand off

- **Fix the endpoint:** the producer skills own the server side:
  [`producer-setup`](../producer-setup/),
  [`create-l402-proxy`](../create-l402-proxy/), or
  [`l402-server-integration`](../l402-server-integration/).
- **Keep using it as a buyer:** [`pay-l402-anywhere`](../pay-l402-anywhere/).

## Classifications

| Classification | Means |
|---|---|
| `CHALLENGE_COMPATIBLE` | A valid unpaid L402 challenge and a priced invoice were observed. Paid fulfillment was not tested. |
| `PAYMENT_COMPATIBLE` | The payment is confirmed: the wallet reports terminal success and SHA-256 of the preimage equals the invoice payment hash. The authorized retry then returned a definitive answer that is not a 2xx meeting the stated expectations, such as a `500`, a `403`, or another `402`. |
| `FULFILLMENT_VERIFIED` | Request, 402, payment, authorized retry, expected 2xx result: all of it worked. |
| `MARKETPLACE_READY` | `FULFILLMENT_VERIFIED`, plus every listing check and a paid amount equal to the quote. |
| `INCOMPATIBLE` | A deterministic protocol or transport defect prevents the flow. |
| `INCONCLUSIVE` | The check couldn't decide: the payment is pending or unknown (no terminal wallet result, or no preimage obtained), the authorized retry was ambiguous (a timeout, a dropped connection, or no answer), the unpaid request timed out or hit a server error or a DNS failure, the target was refused, or the behavior was opaque. |

After a paid call that didn't deliver the resource, the classification is
`PAYMENT_COMPATIBLE` or `INCONCLUSIVE`. In both cases keep the correlators (the
payment hash, the amount, and the time) and never originate a replacement
payment. Recovery goes through the seller's claim or status path, or through
the person who owns the wallet.

Never call an endpoint "L402 verified", or "verified" in any form, after a
read-only check.

## What can go wrong

| Symptom | Likely cause | Fix to recommend |
|---|---|---|
| Unpaid request gets `200` | The resource is served before the paywall | Place the L402 middleware before resource delivery. |
| Unpaid request gets `401` ("401 before challenge") | Ordinary auth runs first | Let requests reach the L402 check before ordinary authentication where paid access is intended. |
| `400` or `422` before any 402 | Input validation runs first | Issue the 402 before validating paid-only parameters, or provide a probe-safe route. |
| `415` on an empty-body POST | Content-type validation runs first | Issue the 402 before body validation, or provide a fixed-price, single-call route for listing. |
| `402` with no `WWW-Authenticate` | The challenge header is missing | Emit `WWW-Authenticate: L402 macaroon="...", invoice="..."`. |
| Parse error naming an offset | Bad quoting or escaping | Quote values as RFC 7235 quoted-strings and separate parameters with commas. |
| Only `Payment` or `x402` offered | No L402 challenge | Add an L402 challenge beside the other schemes. |
| Amountless invoice | No price in the invoice | Use a priced invoice; marketplaces and bounded wallets refuse amountless ones. |
| Expired or short-lived invoice | Quote window too short | Increase the invoice expiry. |
| Body price differs from the invoice | Stale metadata | Make the invoice authoritative and correct the body. |
| Preimage mismatch | Wrong hash or encoding on the server | Validate the preimage encoding and SHA-256 it against the invoice payment hash. |
| Paid retry gets another `402` | Authorization parsing or binding | Inspect authorization serialization and token/resource binding. |
| Paid, then a `5xx` or no answer | Fulfillment failed after payment | Keep the payment hash; add claim or status recovery. Never repay. |
| Target refused | Private, loopback, metadata, or plain-HTTP public URL | Use the public HTTPS URL. `--allow-private` is for deliberate local testing only. |

## Safety rules

- **The read-only check never pays.** It is the default, and a `402` is a quote,
  not proof of delivery.
- **One paid call, after an explicit yes,** at an amount at or under the cap,
  on the exact endpoint the human approved. Never raise a limit.
- **Never a replacement payment** after a paid call that didn't deliver,
  whether the payment is confirmed, pending, or ambiguous. Keep the payment
  hash, the amount, and the time, and stop.
- **Never echo secrets.** Invoice strings, preimages, macaroons, tokens,
  authorization headers, NWC connection strings, and API keys stay out of your
  output. The script prints the payment hash and the amount only.
- **Credentials never go in a command-line argument,** the evidence file, or
  any other file. `--header` refuses credential-bearing headers. The default
  paid check never moves the token; the optional stronger check pipes it on
  stdin, and you never repeat it in chat.
- **Never claim verification you didn't do.** Report the exact classification.
- **Never publish.** Listing on a marketplace is the human's decision.

## What this is NOT

- **Not custody.** Lightning Enable does not hold funds; the payment provider
  facilitates custody and settlement.
- **Not a load test or a security audit.** It sends one unpaid request (plus two
  metadata requests) and, at most, one paid call.
- **Not a marketplace listing.** It reports readiness; it never lists anything.
- **Not a signature check.** It decodes the invoice and reads the macaroon's
  public parts; only the issuer can check a macaroon signature.

## Example

On the .NET server:

> User: "Check my weather endpoint before I list it. If the challenge looks
> right, test it for real, up to 10 sats."
>
> 1. `python scripts/l402_check.py "https://api.example.com/forecast?city=paris" --max-sats 10 --json > mode-a.json`
>    → `CHALLENGE_COMPATIBLE`: one `L402` challenge plus `Payment`, 3 sats,
>    expires in 24 hours, opaque token, no `llms.txt` or `openapi.json` at the
>    host root. Preflight: allowed.
> 2. "The unpaid challenge is valid; paid delivery is not tested yet. I will
>    call `GET https://api.example.com/forecast?city=paris` once. It costs 3
>    sats; your cap is 10. Go ahead?" The human says yes.
> 3. `budget(action="status")` and `get_balance()` → the budget and the balance
>    cover 3 sats.
> 4. `access_l402_resource(url="https://api.example.com/forecast?city=paris", max_sats=10)`
>    → paid 3 sats, 200, JSON body.
> 5. `receipts(source="durable")` → one settled 3-sat receipt with its payment
>    hash. Copy the hash and the amount into `evidence.json`, then run
>    `python scripts/l402_check.py --evidence evidence.json --mode-a mode-a.json`
>    → `FULFILLMENT_VERIFIED`, with one gap for listing: publish `llms.txt` or
>    `openapi.json` at the host root.

On the Python server, the same run ends `INCONCLUSIVE` when the receipt has no
payment hash: the result carries no preimage, so neither a preimage nor a hash
is available to check.
