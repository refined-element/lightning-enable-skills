---
name: l402-compatibility-report
description: >-
  Run the Lightning Enable L402 compatibility report on an L402 endpoint. It
  checks, without spending, that an unpaid request gets a valid HTTP 402
  challenge (every WWW-Authenticate scheme, a priced invoice, its payment hash
  and expiry, resource binding), then, with one explicitly approved, capped
  payment, that the paid retry delivers, with the preimage checked against the
  payment hash. Optional marketplace profiles are reported separately and never
  change the result. Use when a developer asks to check, test, debug, or
  diagnose an L402 endpoint ("is my L402 endpoint working", "check this
  paywall", "run an L402 compatibility report", "check my endpoint before I
  list it on a marketplace"), or after producer-setup, create-l402-proxy, or
  l402-server-integration to check the result. Do NOT use to buy something for
  its content (use pay-l402-anywhere), to find a paid API (use
  discover-paid-apis), or to build a paywall (use producer-setup,
  create-l402-proxy, or l402-server-integration).
---

# Lightning Enable L402 compatibility report

The Lightning Enable L402 compatibility report tells a developer, precisely, how
far their endpoint gets through the L402 flow: does the unpaid request get a
well-formed challenge with a priced invoice, and does a paid request get the
resource. The check works on any L402 endpoint, whoever runs it. It is
deterministic: a standard-library Python script makes the unpaid request,
parses the challenge, decodes the invoice, and writes the report.

Marketplace readiness is optional and separate. The report carries it in its
last section, as optional marketplace profiles (see Optional marketplace
profiles) that never change the classification: a correct, paid, fulfilled
endpoint is `FULFILLMENT_VERIFIED` with or without any marketplace's metadata.

The default check never pays. A paid check is a separate step: one payment, at
an amount the human approved, through the Lightning Enable MCP. Lightning
Enable does not hold funds; the payment provider facilitates custody and
settlement.

## What is automated, and what is not

**Automated:** the unpaid request, URL safety checks, bounded redirects,
challenge parsing, invoice decoding, binding analysis, the optional
marketplace profile, the preflight verdict for a paid check, evidence
validation, and the report in Markdown or JSON.

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

The five classifications, the redaction rules, and the ambiguous-payment rule
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
   any name containing `key`, `token`, `secret`, `password`, `session`, `auth`,
   `macaroon`, `credential`, or `preimage`, in any case. It also refuses
   `Host`, `Content-Length`, `Transfer-Encoding`, and `Connection`, a name that
   is not a plain HTTP header name, and a value with a CR, LF, NUL, or
   non-Latin-1 character. There is no other way to pass them. An endpoint that
   needs its own credential before it will issue a 402 is out of scope for this
   check: report it as "401 before challenge", with the fix from the table under
   What can go wrong.
3. **Whether a paid check is wanted,** and if so the most it may cost, in sats.

### 1. Run the read-only check

From this skill's folder:

```bash
python scripts/l402_check.py "https://api.example.com/forecast?city=paris"
python scripts/l402_check.py "https://api.example.com/search" --method POST --header "Accept=application/json"
```

Add `--max-sats <cap>` when a paid check might follow; the report then carries
a preflight verdict. Add `--json` for machine-readable output, and save it with
`--output` when a paid check follows:

```bash
python scripts/l402_check.py "https://api.example.com/forecast" --max-sats 50 --json --output mode-a.json
```

Use `--output`, not shell redirection: it writes UTF-8 on every platform,
while Windows PowerShell 5.1 redirects `>` as UTF-16. The script still reads a
UTF-16 file that starts with a byte order mark.

The script makes one unpaid request. It refuses localhost, loopback, private,
link-local, and cloud metadata addresses, non-HTTPS public URLs, and redirects
into any of those. `--allow-private` admits local targets, and plain HTTP to
them, only when the human is deliberately testing a local development server
on this machine. Add a marketplace profile flag only when the human wants a
marketplace listing; the Optional marketplace profiles section below names it
and the extra requests it makes.

### 2. Read the report back

Show the human the classification and the summary, then the sections that
matter:

- **`CHALLENGE_COMPATIBLE`:** the unpaid challenge is valid and the invoice is
  priced. Say plainly that paid fulfillment was **not tested**.
- **`INCOMPATIBLE`:** read the Required fixes section. Each defect maps to one
  fix (see the table below).
- **`INCONCLUSIVE`:** a timeout, a refused target, a server error, a DNS
  failure, a `405` (the method the check used isn't served; rerun with the
  method the endpoint accepts), a `408`, `425`, or `429` (try again later), or
  a cross-origin redirect of a request with a body, which the script doesn't
  resend. Say which; don't guess.

The report's last section, Optional marketplace profiles, is not part of the
result. Bring it up only when the human wants a marketplace listing; even then,
an expectation a marketplace adds is that marketplace's requirement, never a
gap in the endpoint.

A response that offers several schemes (`L402` and `Payment`, `LSAT` and
`L402`, or `L402`, `Payment`, and `x402`) is normal. The report classifies the
endpoint by its `L402` challenge (or `LSAT` when there is no `L402`) and lists
the others. `Payment` is its own scheme, never L402.

### 3. Decide on the paid check

Only when the human asked for it, and only when the preflight says `allowed`:

- The read-only check is `CHALLENGE_COMPATIBLE`.
- The method is GET or HEAD. `access_l402_resource` refuses every other method
  before any payment, so a POST endpoint stops at the read-only check.
- The invoice amount is at or below the human's cap.
- The endpoint and parameters are final, and repeating the call has no harmful
  side effects.
- It is the cheapest route that proves the flow. Step 7 needs the token, which
  shows in the command text and stays reusable until its expiry.

State the payment and **stop for a yes**: "I will call `<method> <url>` once
through your Lightning wallet. It costs `<amount>` sats; the cap is `<cap>`. Go ahead?"

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
access_l402_resource(url="<exact url from step 1>", method="<the step 1 method>", headers={"Accept": "application/json"}, max_sats=<the approved cap>)
```

Repeat the request step 1 checked: the same `url`, the same `method`, and in
`headers` the same non-secret headers you gave `--header` (leave `headers` out
when step 1 had none). A `HEAD` check paid as a `GET`, or an endpoint that
depends on `Accept` paid without it, tests a different request than the report
describes. The Python server takes `headers` as an object; the .NET server
takes it as a JSON object in a string: `headers='{"Accept": "application/json"}'`.

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
`paymentHash`, `amountSats`, `status`, `context`, and `timestamp` into
`evidence.json`. The
MCP stores the payment hash as SHA-256 of the preimage, never the preimage
itself, so a receipt holds no credential. A receipt is supporting evidence: it
records what the wallet paid, but it can't prove the preimage belongs to the
endpoint's challenge. Keep `payment.l402Token` out of the file; step 7 pipes it.
Write `evidence.json` with no credential in it (the script refuses a file that
holds one):

```json
{
  "cap_sats": 50,
  "method": "GET",
  "recorded_at": "2026-10-12T21:00:05Z",
  "tool_result": {
    "success": true,
    "status_code": 200,
    "content_type": "application/json",
    "body_length": 812,
    "paid_sats": 21,
    "already_paid": false,
    "requires_confirmation": false
  },
  "payments": [{"amount_sats": 21, "status": "settled", "payment_hash": "<64 hex>", "context": "<receipt context>", "timestamp": "<receipt timestamp>"}],
  "expected": {"status": 200, "content_type": "application/json"}
}
```

| Evidence field | Python server result | .NET server result |
|---|---|---|
| `status_code` | not returned; leave it out (no status is ever inferred, so the result is `INCONCLUSIVE`) | `statusCode` |
| `content_type` | not returned; leave it out (an expected content type then can't be judged) | `contentType` |
| `body_length` | length of `response` | length of `content` |
| `paid_sats` | `paid_sats` | `payment.amountSats` |
| `already_paid` | `alreadyPaid` | `alreadyPaid` |
| `requires_confirmation` | `requiresConfirmation` | `requiresConfirmation` |
| `payments[]` | receipts' `amountSats`, `status`, `paymentHash`, `context`, `timestamp` | the same |
| the credential | `payment.l402Token`, only on the `alreadyPaid` path; piped in step 7, never in this file. That result has no `status_code`, so the outcome is still `INCONCLUSIVE` | `payment.l402Token`, piped in step 7, never in this file |

`method` is optional: the method you passed in step 5. The script refuses
evidence whose `method` differs from the read-only check's, and judges the
result by that one method (a `HEAD` result needs no body). `recorded_at` is
optional: when you wrote the file, in UTC; the report's `paid_checked_at` uses
the latest receipt `timestamp`, else `recorded_at`. `expected` is optional: the
status and content type the human expects.

### 7. Validate the evidence

`FULFILLMENT_VERIFIED` and `PAYMENT_COMPATIBLE` require the credential. When
the result carries `payment.l402Token` (the .NET server does; the Python
server only on the `alreadyPaid` path), pipe it to the script with this
recipe, the only way to pass it; `--mode-a` adds the read-only report from
step 1:

```bash
printf '%s' '<token>' | python scripts/l402_check.py --evidence evidence.json --mode-a mode-a.json --credential-stdin
```

In a POSIX shell (bash, zsh), `printf` is a builtin, so the token reaches the
script on stdin, never as a script argument. The token is still visible in the
command text to anyone who sees the tool call, and it stays reusable until its
expiry. That is why the paid check runs against the cheapest route. On Windows
PowerShell, the equivalent is to pipe the token from a variable:

```powershell
$token | python scripts/l402_check.py --evidence evidence.json --mode-a mode-a.json --credential-stdin
```

The same visibility caveat applies to the command that sets the variable.
Never repeat the token in chat, and never write it to a file. `--evidence` and
`--mode-a` take file paths, never `-`: stdin carries the token only, and the
script refuses to read the token from a terminal.

Pipe the whole token, `<macaroon>:<preimage>`; the script refuses a bare
preimage. It checks that SHA-256 of the preimage equals the payment hash inside
the token's macaroon identifier (Lightning Labs format) when it can read one,
and equals the receipt's `paymentHash` when you supplied it. The macaroon's
hash ties the preimage to the server's own challenge. For an opaque token the
receipt's hash is the only comparison, and it ties the token to the wallet's
recorded payment, not to the invoice. The report names the source it used in
`paid_fulfillment.hash_source` and in its summary. It also requires an
authorized retry with a reported 2xx status that meets the stated
expectations, and exactly one payment recorded at or under the cap, with the
tool's `paid_sats` and the receipts agreeing. It prints the payment hash and
the amount, never a credential.

Without the credential, because you chose not to pipe it or because the Python
server returned none, run the same command without `printf` and without
`--credential-stdin`:

```bash
python scripts/l402_check.py --evidence evidence.json --mode-a mode-a.json
```

The result is then `INCONCLUSIVE` with the finding `preimage_unchecked`. The
receipt's hash, amount, and context are recorded as supporting evidence and
never upgrade the classification.

The report also compares the Mode A invoice's payment hash with the paid
payment hash, as information only. A mismatch is normal, because a server may
mint a fresh invoice for each 402, and it is never a finding.

Paid-check finding codes, and the checks the paid check adds to the optional
marketplace profile, as the report prints them:

- **Nothing to evaluate (`INCONCLUSIVE`):** `paid_check_without_challenge` (the
  read-only check wasn't `CHALLENGE_COMPATIBLE`), `awaiting_confirmation` (the
  call waits for the human's code; nothing was paid), `no_payment`.
- **Payment not settled or not single (`INCONCLUSIVE`):** `payment_pending` (no
  terminal wallet success), `paid_over_cap` (the larger of `paid_sats` and the
  receipts' sum is over the cap), `paid_amount_mismatch` (`paid_sats` and the
  receipts disagree), `multiple_payments` (more than one payment for one check;
  reconcile from the receipts).
- **Preimage not confirmed (`INCONCLUSIVE`):** `preimage_unchecked` (nothing
  piped, a bare preimage, a missing preimage, or not 64 hex characters; a
  receipt never upgrades it), `no_hash_to_compare` (the macaroon isn't in
  Lightning Labs format and there's no receipt `paymentHash`),
  `receipt_mismatch` (SHA-256 of the preimage differs from the receipt's
  `paymentHash` and there's no macaroon hash, likely the wrong receipt; when
  the macaroon hash matches, the macaroon governs and this is information
  only).
- **Server defect (`INCOMPATIBLE`):** `preimage_mismatch` (SHA-256 of the
  preimage differs from the hash in the macaroon identifier, so the server's
  own challenge disagrees with the paid preimage).
- **Retry ambiguous (`INCONCLUSIVE`):** `ambiguous_fulfillment` (no reported
  status, or 408, 425, 429, 502, 503, or 504), `result_unreported` (the
  evidence omits `body_length`, or `content_type` when one is expected).
- **Paid but not delivered (`PAYMENT_COMPATIBLE`):** `paid_retry_402`,
  `paid_retry_rejected` (another 4xx), `paid_retry_failed` (a 5xx or another
  non-2xx answer), `unexpected_result` (a 2xx that misses the stated
  expectations).
- **Optional marketplace profile, never the classification:** the paid check
  adds `synchronous_response` (a reported 2xx other than `202 Accepted`) and
  `stable_price` (the paid amount equals the read-only quote) to the profile.
  Optional marketplace profiles says how they count.

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
| `PAYMENT_COMPATIBLE` | The payment is confirmed: the wallet reports terminal success and SHA-256 of the preimage from the piped credential equals the payment hash in the macaroon identifier, or, for an opaque token, the receipt's hash, which ties the token to the wallet's recorded payment, not to the invoice. The authorized retry then returned a definitive answer that is not a 2xx meeting the stated expectations, such as a `500`, a `403`, or another `402`. |
| `FULFILLMENT_VERIFIED` | Request, 402, payment, authorized retry, expected 2xx result: all of it worked, and SHA-256 of the preimage from the piped credential matched the payment hash in the macaroon identifier, or, for an opaque token, the receipt's hash (the report names which). Requires the credential. |
| `INCOMPATIBLE` | A deterministic protocol or transport defect prevents the flow. |
| `INCONCLUSIVE` | The check couldn't decide: the payment is pending or unknown (no terminal wallet result, or no preimage obtained), no credential was piped so the preimage went unchecked (`preimage_unchecked`; a receipt never upgrades this), the authorized retry was ambiguous (a timeout, a dropped connection, or no answer), the unpaid request timed out or hit a server error or a DNS failure, the target was refused, or the behavior was opaque. |

After a paid call that didn't deliver the resource, the classification is
`PAYMENT_COMPATIBLE` or `INCONCLUSIVE`. In both cases keep the correlators (the
payment hash, the amount, and the time) and never originate a replacement
payment. Recovery goes through the seller's claim or status path, or through
the person who owns the wallet.

Never call an endpoint "L402 verified", or "verified" in any form, after a
read-only check.

**The JSON report is the contract.** Tools and gates read `--json`, never the
Markdown: `report_version` (2), `mode`, `classification`, `evidence`, and
`marketplace_profiles`, the optional marketplace checks, which never change
`classification`. After a paid check, `paid_fulfillment` adds `hash_source`,
`paid_checked_at`, and `evidence_source` ("agent-recorded access_l402_resource
result": validated, never independently observed). Version 2 dropped the
version 1 marketplace classification; a reader that gated on it reads the
profile's status instead (see Optional marketplace profiles).

## Optional marketplace profiles

A marketplace can expect more than L402 does. The report checks those
expectations in a separate profile, `marketplace_profiles.<name>` in the JSON
and the last section of the Markdown. A profile never changes the
classification, never adds a finding or a required fix, and never makes a
correct endpoint read as deficient.

The one profile today is `amazap`, for an optional listing on
[Amazap](https://amazap.com/sell). The report always carries it; bring it up
only when the human wants a marketplace listing. Add `--profile amazap` to the
read-only check only then: it also requests `/openapi.json` and `/llms.txt` at
the host root, where Amazap's listing prefill looks. Without it the read-only
check makes exactly one unpaid request (plus any redirects it follows), the
Markdown shows the profile as one line, and the JSON keeps it in full with
`requested: false`. The paid check reuses the read-only report's profile.

Its `status` is `READY` (the classification is `FULFILLMENT_VERIFIED` and
every required check passed), `NOT_READY` (a required check failed, or the
classification is `INCOMPATIBLE` or `PAYMENT_COMPATIBLE`), or `NOT_CHECKED`
(nothing failed, but readiness needs a paid check that reaches
`FULFILLMENT_VERIFIED`). Required checks: `public_https`, `priced_invoice`,
`mainnet_invoice`, `probe_without_body` (Amazap's listing probe sends the
listed method with no body), `within_probe_window` (the 402 within 8 seconds),
`stable_path` (no redirect), and, after a paid check, `stable_price` (the
paid amount equals the read-only quote, because Amazap pays a live invoice
only when it fits the price stored at listing time) and
`synchronous_response`. One advisory check never decides the status:
`host_root_metadata` (`openapi.json` or `llms.txt` at the host root, where
Amazap's prefill looks; probed only with `--profile amazap`, and "Not probed"
on every host without it). With the flag, on `api.lightningenable.com` the
host-root files describe the Lightning Enable platform, not the endpoint, so
the check says to supply the listing fields by hand. Whichever status it
shows, the profile never changes the classification.

Report version 1 called a `READY` Amazap profile `MARKETPLACE_READY` and
reported it as a classification. Version 2 has no such classification; read
`marketplace_profiles.amazap.status` instead.

## What can go wrong

| Symptom | Likely cause | Fix to recommend |
|---|---|---|
| Unpaid request gets `200` | The resource is served before the paywall | Place the L402 middleware before resource delivery. |
| Unpaid request gets `401` ("401 before challenge") | Ordinary auth runs first | Let requests reach the L402 check before ordinary authentication where paid access is intended. |
| `400` or `422` before any 402 | Input validation runs first | Issue the 402 before validating paid-only parameters, or provide a probe-safe route. |
| `415` on an empty-body POST | Content-type validation runs first | Issue the 402 before body validation, or provide a fixed-price, single-call route whose unpaid request with no body gets the 402. |
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
  any other file. `--header` refuses credential-bearing headers. The token
  reaches the script only on stdin, through the `printf` recipe in step 7 (or
  its PowerShell equivalent). It shows in that command text and stays reusable
  until its expiry, so the paid check runs against the cheapest route, and you
  never repeat the token in chat.
- **A receipt never upgrades the classification.** Without the credential, the
  paid check is `INCONCLUSIVE` with `preimage_unchecked`.
- **Never claim verification you didn't do.** Report the exact classification.
- **Never publish.** Listing on a marketplace is the human's decision.

## What this is NOT

- **Not custody.** Lightning Enable does not hold funds; the payment provider
  facilitates custody and settlement.
- **Not a load test or a security audit.** It sends one unpaid request (plus
  two host-root requests, only with a marketplace profile flag) and, at most,
  one paid call.
- **Not a marketplace listing.** Its optional marketplace profiles report
  readiness; it never lists anything.
- **Not a signature check.** It decodes the invoice and reads the macaroon's
  public parts; only the issuer can check a macaroon signature.

## Example

On the .NET server:

> User: "Check my weather endpoint. If the challenge looks right, test it for
> real, up to 10 sats."
>
> 1. `python scripts/l402_check.py "https://api.example.com/forecast?city=paris" --max-sats 10 --json --output mode-a.json`
>    → `CHALLENGE_COMPATIBLE`: one `L402` challenge plus `Payment`, 3 sats,
>    expires in 24 hours, opaque token. Preflight: allowed.
> 2. "The unpaid challenge is valid; paid delivery is not tested yet. I will
>    call `GET https://api.example.com/forecast?city=paris` once. It costs 3
>    sats; your cap is 10. Go ahead?" The human says yes.
> 3. `budget(action="status")` and `get_balance()` → the budget and the balance
>    cover 3 sats.
> 4. `access_l402_resource(url="https://api.example.com/forecast?city=paris", method="GET", max_sats=10)`,
>    the same request step 1 checked (it sent no extra headers)
>    → paid 3 sats, 200, JSON body.
> 5. `receipts(source="durable")` → one settled 3-sat receipt. Copy its hash,
>    amount, status, and context into `evidence.json`, then pipe the token with
>    `printf '%s' '<token>' | python scripts/l402_check.py --evidence evidence.json --mode-a mode-a.json --credential-stdin`
>    → `FULFILLMENT_VERIFIED`: the whole paid flow worked. The token is opaque,
>    so the report names the receipt's hash as its source: the token matches
>    the wallet's recorded payment, not the invoice. The Mode A and paid
>    payment hashes differ, which the report notes as information only. The
>    report's optional marketplace profile, in its own section at the end,
>    stays out of the answer: the developer didn't ask about a listing.

On the Python server, which returns a token only on the `alreadyPaid` path, the
same run ends `INCONCLUSIVE` with `preimage_unchecked`. The receipt is recorded as supporting evidence and
doesn't upgrade it.
