# L402 verification levels

Shared vocabulary for every skill in this repository that checks, lists, or
buys an L402 endpoint. When a skill reports how far an endpoint got, it uses
these six classifications, these redaction rules, and this payment rule.
[`l402-compatibility-report`](../skills/l402-compatibility-report/) produces
them; the other skills quote them.

## The six classifications

Use these names exactly, in capitals, as written.

| Classification | Means | Needs |
|---|---|---|
| `CHALLENGE_COMPATIBLE` | A valid unpaid L402 challenge and a priced invoice were observed. Paid fulfillment was not tested. | One unpaid request. |
| `PAYMENT_COMPATIBLE` | The payment is confirmed: the wallet reports terminal success and the SHA-256 hash of the preimage from the credential equals the payment hash from the source the report names (see [Which payment hash](#which-payment-hash)). The authorized retry then returned a definitive answer that is not a 2xx meeting the stated expectations, such as a `500`, a `403`, or another `402`, so delivery of the resource was not proven. | One paid call, the credential from it (its preimage must hash to the payment hash), and a definitive retry answer that is not a 2xx meeting the stated expectations. A wallet receipt alone never suffices. |
| `FULFILLMENT_VERIFIED` | The whole flow worked: request, 402, payment, authorized retry, expected 2xx result, with the preimage matched against the payment hash from the source the report names. | One paid call, the credential from it (its preimage must hash to the payment hash), and a 2xx result that meets the stated expectations. A wallet receipt alone never suffices. |
| `MARKETPLACE_READY` | `FULFILLMENT_VERIFIED`, plus public https, a priced mainnet invoice, a 402 for a bodyless request within 8 seconds, a stable URL, `openapi.json` or `llms.txt` at the host root, and a paid amount equal to the quote. | Everything above. |
| `INCOMPATIBLE` | A deterministic protocol or transport defect prevents the flow. | Any check. |
| `INCONCLUSIVE` | The check couldn't decide: the payment is pending or unknown (no terminal wallet result, or no preimage obtained), the preimage went unchecked because no credential was available (`preimage_unchecked`; a wallet receipt never upgrades this), the authorized retry was ambiguous (a timeout, a dropped connection, or no answer), a server error, a DNS failure, an opaque behavior, or a refused target. | Any check. |

A read-only check stops at `CHALLENGE_COMPATIBLE`. Never call an endpoint
"L402 verified", or "verified" in any form, when only the unpaid challenge was
checked. A `402` is a quote, not proof that anything gets delivered.

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

## Custody

Lightning Enable does not hold funds; the payment provider facilitates custody
and settlement.
