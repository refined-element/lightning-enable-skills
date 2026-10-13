# Lightning Enable L402 Compatibility Report

- Target: <METHOD> <redacted-safe URL>
- Checked at: <UTC timestamp, YYYY-MM-DDTHH:MM:SSZ>
- Mode: read-only | paid
- Classification: <CHALLENGE_COMPATIBLE | PAYMENT_COMPATIBLE | FULFILLMENT_VERIFIED | INCOMPATIBLE | INCONCLUSIVE>

## Summary

<One or two sentences. After a read-only check, say that paid fulfillment was not tested.>

## Transport

<Status, latency, content type, redirect chain, transport errors.>

## Challenge

<Every scheme offered, which L402 or LSAT challenge classified the endpoint, parameter names (never values), duplicates, parse errors.>

## Invoice

<Network, amount in sats, payment hash, created, expiry, remaining lifetime, description or description hash, payee when stated, route hints, declared price versus invoice.>

## Authorization and binding

<Token format ("absent" when the challenge carries no token); payment hash in the token; method, path, query, body digest, expiry, and scope caveats; "not externally verifiable" for an opaque token; "none found in caveats" for a decoded token with no binding caveats.>

## Paid fulfillment

<Read-only: "Not tested", plus the preflight verdict when a cap was given. Paid: evidence source (agent-recorded) and paid check time, cap, sats paid, payments recorded, preimage check, the hash source it used (the macaroon identifier, or for an opaque token the wallet receipt, which ties the token to the recorded payment, not to the invoice), authorized retry status, expectations.>

## Replay/idempotency

<Not tested unless a replay was run on a read-only operation with no harmful side effects.>

## Security findings

<Refused targets, blocked redirects, credentials in the unpaid body, payments over the cap, second payments.>

## Rerun notes

<Notes for the person running the check, such as rerunning with the method the endpoint accepts. Never a server fix. "None." when there are none.>

## Required fixes

<One precise fix per defect, addressed to the server owner.>

## Evidence retained

<Timestamp, safe URL and method, HTTP statuses, amount, payment hash, latency, classification. Never an invoice string, preimage, macaroon or token, authorization header, NWC URI, API key, wallet balance, or private request body.>

## Optional marketplace profiles

<Optional. One subsection per marketplace profile (### Amazap): its status (READY, NOT_READY, or NOT_CHECKED), each check with pass, fail, or not checked, "(advisory)" on a check that never decides the status, what the script cannot check, and a note. A profile never changes the classification.>
