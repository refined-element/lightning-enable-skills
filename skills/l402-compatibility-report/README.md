# l402-compatibility-report

**Find out exactly how far an endpoint gets through L402, without spending a sat, then test paid delivery with one approved payment.**

An [L402](https://github.com/lightninglabs/L402) endpoint answers an unpaid
request with `402 Payment Required`, a Lightning invoice, and a macaroon, and
serves the resource once the caller pays and presents the preimage. Many things
can go wrong on the way: the resource leaks out unpaid, ordinary auth answers
first, the challenge header is malformed, the invoice has no amount or expires
too soon. This skill checks each step and writes a report that says which one
fails and how to fix it.

## Why it's interesting

- **The default check never pays.** One unpaid request, decoded down to the
  invoice's amount, payment hash, and expiry, with no wallet needed.
- **Honest about what was tested.** A valid challenge is
  `CHALLENGE_COMPATIBLE`, not "verified". Paid delivery needs a paid check:
  `FULFILLMENT_VERIFIED`, the top result, needs the preimage matched to the
  payment hash and the expected 2xx.
- **Multi-scheme aware.** Servers that offer `L402` beside `Payment`, `LSAT`, or
  `x402` are normal; the report classifies the L402 challenge and lists the
  rest, and never treats `Payment` as L402.
- **Marketplace-minded.** It checks what a listing probe such as Amazap's needs:
  a 402 for a bodyless request within 8 seconds, a priced mainnet invoice, and
  `openapi.json` or `llms.txt` at the host root.
- **Secret-safe output.** The report holds the payment hash and the amount,
  never an invoice string, macaroon, preimage, or authorization header.

## How it works

1. **Read-only check:** `python scripts/l402_check.py <url>` makes one unpaid
   request (refusing private, loopback, and metadata addresses), parses every
   `WWW-Authenticate` challenge, decodes the BOLT11 invoice, and reports.
2. **Paid check, only with your yes:** the agent pays once with the Lightning
   Enable MCP's `access_l402_resource`, capped at the amount you approved.
3. **Evidence check:** the agent pipes the paid call's L402 token to
   `l402_check.py --evidence ... --credential-stdin`, which checks that SHA-256
   of the preimage equals the payment hash in the token's macaroon (when it is
   in Lightning Labs format) and in the wallet receipt (when you supplied its
   `paymentHash`), that the paid retry returned the expected 2xx, and that
   exactly one payment happened. The macaroon's hash ties the preimage to the
   server's challenge; for an opaque token the receipt's hash ties the token
   to the wallet's recorded payment, not to the invoice, and the report names
   which source it used. `FULFILLMENT_VERIFIED` and `PAYMENT_COMPATIBLE` both
   require that token. Without it (the Python MCP server usually returns
   none), the result is `INCONCLUSIVE` with `preimage_unchecked`; the receipt
   is supporting evidence and never upgrades it.
4. **Report:** Markdown or JSON, from `templates/report.md`, with one precise
   fix per defect.

## Requirements

- Python 3.10 or later. Standard library only.
- For the paid check: the
  [Lightning Enable MCP](https://github.com/refined-element/lightning-enable-mcp)
  connected to a wallet that returns preimages (NWC, LND, or Strike). See
  [`agent-wallet-setup`](../agent-wallet-setup/).

## Try it

> "Run an L402 compatibility report on https://api.example.com/forecast. Don't
> pay anything."

> "Check my endpoint before I list it on Amazap, and if the challenge is good,
> test it for real for up to 10 sats."

## Safety

- The read-only check never pays.
- At most one paid call, after an explicit yes, capped with `max_sats`. Never a
  replacement payment after a paid call that didn't deliver, whether the
  payment is confirmed, pending, or ambiguous.
- No credential goes in a command-line argument or a file. The script refuses
  credential-bearing request headers and takes the L402 token only on stdin,
  through a `printf` recipe (or its PowerShell equivalent). The token shows in
  that command text and stays reusable until its expiry, so the paid check
  runs against the cheapest route. No credential appears in the output.
- An endpoint that needs its own credential before it will issue a 402 is out
  of scope; the report calls it "401 before challenge".
- Lightning Enable does not hold funds; the payment provider facilitates custody
  and settlement.

## What it doesn't do

It doesn't list anything on a marketplace, check macaroon signatures (only the
issuer can), or load-test an endpoint. To fix what it finds, use
[`producer-setup`](../producer-setup/),
[`create-l402-proxy`](../create-l402-proxy/), or
[`l402-server-integration`](../l402-server-integration/).
