# L402 verification levels

Shared vocabulary for every skill in this repository that checks, lists, or
buys an L402 endpoint. When a skill reports how far an endpoint got, it uses
these five classifications, these redaction rules, and this payment rule.
[`l402-compatibility-report`](../skills/l402-compatibility-report/), the
Lightning Enable L402 compatibility report, produces them; the other skills
quote them.

## The five classifications

Use these names exactly, in capitals, as written.

| Classification | Means | Needs |
|---|---|---|
| `CHALLENGE_COMPATIBLE` | A valid unpaid L402 challenge and a priced invoice were observed. Paid fulfillment was not tested. | One unpaid request. |
| `PAYMENT_COMPATIBLE` | The payment is confirmed: the wallet reports terminal success and the SHA-256 hash of the preimage from the credential equals the payment hash from the source the report names (see [Which payment hash](#which-payment-hash)). The authorized retry then returned a definitive answer that is not a 2xx meeting the stated expectations, such as a `500`, a `403`, or another `402`, so delivery of the resource was not proven. | One paid call, the credential from it (its preimage must hash to the payment hash), and a definitive retry answer that is not a 2xx meeting the stated expectations. A wallet receipt alone never suffices. |
| `FULFILLMENT_VERIFIED` | The whole flow worked: request, 402, payment, authorized retry, expected 2xx result, with the preimage matched against the payment hash from the source the report names. | One paid call, the credential from it (its preimage must hash to the payment hash), and a 2xx result that meets the stated expectations. A wallet receipt alone never suffices. |
| `INCOMPATIBLE` | A deterministic protocol or transport defect prevents the flow. | Any check. |
| `INCONCLUSIVE` | The check couldn't decide: the payment is pending or unknown (no terminal wallet result, or no preimage obtained), the preimage went unchecked because no credential was available (`preimage_unchecked`; a wallet receipt never upgrades this), the authorized retry was ambiguous (a timeout, a dropped connection, or no answer), a server error, a DNS failure, an opaque behavior, or a refused target. | Any check. |

A read-only check stops at `CHALLENGE_COMPATIBLE`. Never call an endpoint
"L402 verified", or "verified" in any form, when only the unpaid challenge was
checked. A `402` is a quote, not proof that anything gets delivered.

`FULFILLMENT_VERIFIED` is the top classification. A correct, paid, fulfilled
endpoint gets it whether or not any marketplace's extra expectations are met.

### Which payment hash

The preimage is compared with one of two hashes, and a report names the one it
used:

- **The macaroon identifier's payment hash,** when the token is readable
  (Lightning Labs format). The identifier is the server's own challenge, so a
  match ties the preimage to the invoice the server issued.
- **The wallet receipt's payment hash,** for an opaque token. The wallet
  records it as SHA-256 of the same preimage, so a match ties the token to the
  wallet's recorded payment, not to the invoice.

## Classic L402 and other 402 schemes

- **Classic L402** is `WWW-Authenticate: L402 macaroon="...", invoice="..."`,
  answered with `Authorization: L402 <macaroon>:<preimage>`. `LSAT` is its
  older name and is classified the same way.
- **`Payment`** (the MPP and `draft-httpauth-payment` scheme) is its own
  scheme. Report it separately and never normalize it to L402, even when it
  carries the same invoice.
- **`x402`** and any other scheme are reported by name. Detect `x402`
  wherever it appears, in the `402` response body or in `X-PAYMENT` headers,
  not only as a `WWW-Authenticate` scheme.
- **Several schemes in one response are normal.** Lightning Enable and Amazap
  Basics both send `L402` and `Payment`; some servers send `LSAT` and `L402`,
  or `L402`, `Payment`, and `x402`. Classify the endpoint by its `L402`
  challenge (or `LSAT` when there is no `L402`), and list every other scheme.
- Separate headers and one comma-joined header mean the same thing
  (RFC 7235). Treat them identically.
- An opaque token makes resource binding **not externally verifiable**. That
  isn't the same as unbound; say which one you mean.

## Secret redaction

Reports, logs, and chat output never contain:

- invoice strings (BOLT11);
- preimages;
- macaroons or tokens;
- `Authorization` header values;
- NWC connection strings;
- API keys;
- wallet balances, unless the person asked and approved;
- private request bodies.

Report the payment hash and the amount instead. A payment hash is safe to
share; it identifies the payment and can't spend anything. Report a
credential as set or not set, never its value.

## The ambiguous-payment rule

Never start a replacement payment while a payment is pending or its outcome
is unknown. When a paid call didn't deliver the resource, classify it by
what you know:

- **Payment confirmed, definitive answer.** The wallet reports terminal
  success, the SHA-256 hash of the preimage from the credential equals the
  payment hash from the named source (see Which payment hash), and the
  authorized retry returned a definitive answer that is not a 2xx meeting the
  stated expectations, such as a `500`, a `403`, or another `402`. Classify
  the check `PAYMENT_COMPATIBLE`.
- **Payment or retry ambiguous.** The payment is pending or unknown (no
  terminal wallet result, or no preimage obtained), the preimage went
  unchecked because no credential was available, or the retry outcome is
  ambiguous (a timeout, a dropped connection, or no answer). Classify the
  check `INCONCLUSIVE`.

In both cases:

1. Keep the correlators: the payment hash, the amount, and the time.
2. Don't pay again, and never originate a replacement payment. Recovery goes
   through the seller's claim or status path, or through the person who owns
   the wallet.

A second recorded payment for one check is a finding in its own right. Stop
and reconcile from the wallet receipts.

## Verifying your own endpoint

The seller skills ([`producer-setup`](../skills/producer-setup/),
[`create-l402-proxy`](../skills/create-l402-proxy/), and
[`l402-server-integration`](../skills/l402-server-integration/)) check a new
endpoint with [`l402-compatibility-report`](../skills/l402-compatibility-report/)
before they hand it off. The check reads; the seller skill's own self-test is
its paid evidence. These are the rules for that step.

1. Run the read-only check on the public URL, with the method a buyer will
   use: `python scripts/l402_check.py <url> --json --max-sats <cap> --output mode-a.json`
   from that skill's folder, with the human's cap in sats (add `--method POST`
   for a `POST` route). Take the `classification` field from the JSON report,
   which is the script's contract (`report_version` 2), not from the
   Markdown. If `l402-compatibility-report` is not installed, paid delivery
   stays unverified and no classification is available; give the human its
   GitHub URL,
   https://github.com/refined-element/lightning-enable-skills/tree/main/skills/l402-compatibility-report.
2. Read the result:
   - `INCOMPATIBLE`: give the fix the report names. A private, loopback,
     link-local, or non-HTTPS URL, a `200` to an unpaid request, or a `400`,
     `415`, or `422` to a request with no body each has one.
   - `CHALLENGE_COMPATIBLE`: the most the read-only check can return for a
     correct endpoint. Say "challenge-compatible, fulfillment unverified", and
     do not report paid delivery as proven until the paid evidence below lifts
     it.
   - `PAYMENT_COMPATIBLE` or `INCONCLUSIVE`: paid delivery wasn't proven.
   - `FULFILLMENT_VERIFIED`: the whole paid flow worked. Pass on the report's
     `paid_fulfillment.hash_source`: for an opaque token the preimage was
     matched against the wallet's recorded payment, not the invoice.
3. Pay once, never twice, under the three limits below.

Three limits of the paid check:

- It runs on `GET` or `HEAD` only, because `access_l402_resource` sends
  nothing else. A `POST` route stops at `CHALLENGE_COMPATIBLE` through these
  skills.
- It needs the credential. `FULFILLMENT_VERIFIED` and `PAYMENT_COMPATIBLE`
  both require the paid call's token piped to the script on stdin (step 7 of
  `l402-compatibility-report`). Without it the paid check ends `INCONCLUSIVE`
  with `preimage_unchecked`, and a wallet receipt never upgrades that. The
  Python MCP server returns the token only on the `alreadyPaid` path, which is
  `INCONCLUSIVE` anyway, so a paid check through the Python MCP server never
  proves paid delivery either.
- Pay once, never twice. If the self-test made no payment for this endpoint
  by any means (a testnet invoice doesn't count), run the compatibility
  report's paid check once, with the human's yes; otherwise the cases below
  apply and the agent never pays again. The paid check needs a wallet that
  can pay this endpoint: if the self-test was skipped because the wallet
  refused to pay its own invoice, do not attempt the paid check with the same
  wallet, and paid delivery stays unverified. If the self-test already paid
  this exact public URL, with the same method, through `access_l402_resource`,
  from either wallet (the seller's own or a second one), record that call as
  the evidence (steps 6 and 7 of `l402-compatibility-report`, with the
  read-only report above as `--mode-a` and that call's token piped on stdin)
  instead of paying again. If that token is gone, paid delivery stays
  unverified; do not pay again. A self-test payment of a testnet invoice moved
  no real money for this endpoint, so it is neither reuse evidence nor the one
  paid check: once the endpoint quotes a mainnet invoice at the chosen price,
  run the paid check once, with the human's yes. A self-test that paid this
  URL with a different method also counts as paid; paid delivery stays
  unverified; do not pay again. A payment through `pay_l402_challenge` counts
  as paid. The agent has no tool that fetches the resource with a token it
  already holds, and `access_l402_resource` would pay again, so in that run
  the result stays at `CHALLENGE_COMPATIBLE`: paid delivery stays unverified,
  and the agent does not pay again. A self-test payment made by hand, outside
  both tools, also counts as paid: paid delivery stays unverified in that run,
  and the agent does not pay again. If the human wants the paid check later,
  they choose it in a later run, and the skill says plainly that it is a
  second payment for this endpoint.

The report's optional marketplace profiles never change this result; a seller
skill reads them only for an optional listing.

## Optional marketplace profiles

A marketplace can expect more than L402 does. The report checks those
expectations in a separate profile, `marketplace_profiles.<name>` in the JSON
report and the last section of the Markdown. A profile never changes the
classification, never adds a finding or a required fix, and never makes a
correct endpoint read as deficient. A seller lists on a marketplace only by
choice.

The one profile today is `amazap`, for an optional listing on
[Amazap](https://amazap.com/sell) (see [Amazap marketplace](amazap-marketplace.md)).
Its `status` is one of:

| Status | Means |
|---|---|
| `READY` | The classification is `FULFILLMENT_VERIFIED` and every required check passed. |
| `NOT_READY` | A required check failed, or the classification is `INCOMPATIBLE` or `PAYMENT_COMPATIBLE`. |
| `NOT_CHECKED` | Nothing failed, but readiness needs a paid check that reaches `FULFILLMENT_VERIFIED`: a read-only run, an `INCONCLUSIVE` paid check, or a required check that could not be judged. |

Required checks: `public_https`, `priced_invoice`, `mainnet_invoice`,
`probe_without_body` (Amazap's listing probe sends the listed method with no
body), `within_probe_window` (the 402 within 8 seconds), `stable_path` (no
redirect before the 402), and, after a paid check, `synchronous_response` (a
2xx other than `202 Accepted`) and `stable_price` (the paid amount equals the
read-only quote; Amazap pays a live invoice only when it fits the price it
stored at listing time, so a price that moves breaks buys). Advisory checks
never decide the status: `host_root_metadata` (`openapi.json` or `llms.txt` at
the host root, where Amazap's listing prefill looks; probed only when the check
runs with `--profile amazap`, and "Not probed" on every host without it). With
the flag, on `api.lightningenable.com` the host-root files describe the
Lightning Enable platform, not the endpoint, so the check says to supply the
listing fields by hand. Without the flag, the Markdown shows the profile as one
line and the JSON keeps it in full with `requested: false`.

Report version 1 called a `READY` Amazap profile `MARKETPLACE_READY` and
reported it as a sixth classification. Version 2 has no such classification;
read `marketplace_profiles.amazap.status`.

## Custody

Lightning Enable does not hold funds; the payment provider facilitates custody
and settlement.
