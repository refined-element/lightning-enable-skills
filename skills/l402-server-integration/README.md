# l402-server-integration

**Charge sats per request on your own Express or ASP.NET Core API, in-process, with no proxy.**

This skill has your coding assistant (Claude Code, Cursor, Codex, or similar) add
Lightning Enable's open-source **native** [L402](https://github.com/lightninglabs/L402)
middleware to your API. A request to a paid route without a credential gets
`402 Payment Required` and a Lightning invoice; once the caller pays and presents
the proof, your handler runs as usual. Your API stays on your domain, behind your
own auth, rate limiting, and logging. Lightning Enable mints the invoice and
macaroon and verifies the credential; the sats settle with your payment provider
or wallet.

| Stack | Middleware | SDK underneath |
|---|---|---|
| Node + Express | [`l402-express`](https://www.npmjs.com/package/l402-express) | [`l402-server`](https://www.npmjs.com/package/l402-server) |
| .NET + ASP.NET Core | [`L402Server.AspNetCore`](https://www.nuget.org/packages/L402Server.AspNetCore) | [`L402Server`](https://www.nuget.org/packages/L402Server) |

## What it does

1. Checks that native mode is the right fit, not the hosted proxy.
2. Confirms the prerequisites: a merchant API key, a plan that includes L402, and
   a receive wallet on the merchant.
3. Installs the middleware and prices your routes: per route, one flat price, or
   a price computed from the request.
4. Binds each paid token to the right resource, so a token bought for one route
   does not unlock another, and handles the version difference between 0.1.x and
   0.2.0.
5. Sets up challenge reuse so concurrent buyers each get their own invoice.
6. Wires up access to the verified payment for logging, and documents the
   configuration your app reads.
7. Runs your tests, shows you the diff, proves the 402 for free, and, with your
   yes, pays one 1-sat test call.

## What you need

- An Express 4 or 5 app (Node 18 or later) or an ASP.NET Core app (.NET 8 or
  later).
- A Lightning Enable merchant API key on a plan that includes L402: Agentic
  Commerce, Agentic Commerce Business, or the Free Producer Sandbox within its
  caps. Plans and prices are at [lightningenable.com](https://www.lightningenable.com);
  the [`producer-setup`](../producer-setup/) skill can create an account for you.
- A receive wallet configured on the merchant: Strike, or your own wallet over
  NWC.

## Try it

> "Add an L402 paywall to my Express API: 10 sats per call to `/api/forecast`,
> everything else stays free."

## Safety

- Nothing is paid until you have seen the diff and said yes. The first check, a
  402 from your own route, costs nothing.
- One test payment at a time, priced at 1 sat on a staging route.
- Your merchant API key stays in an environment variable or secret store. It,
  macaroons, and preimages are never printed, logged, or committed; status is
  reported as `<set>` or `<not set>`.
- Path enforcement stays on unless a handler-side check replaces it.
- Lightning Enable does not hold funds; the payment provider (or your wallet)
  facilitates custody and settlement. There is no per-transaction cut.

## Optional: list on Amazap

Once the API is deployed at a public HTTPS URL and the self-test is done, the
agent can offer one more step: a draft listing on
[Amazap](https://amazap.com/sell), a storefront where agents find and buy L402
endpoints. It first checks whether Amazap already carries the API (possibly
imported from 402 Index) and asks whether you want a listing before it spends
anything on a paid check. It offers the listing as ready only after
[`l402-compatibility-report`](../l402-compatibility-report/) shows that paid
delivery worked on the public URL (a test against `localhost` doesn't count),
then drafts the copy and stops. Amazap fills in the title, description,
category, and example parameters from an `openapi.json` or `llms.txt` at the
root of your API's host; without one, you fill them in yourself. You review
the draft, the current Amazap seller terms, and the two prices (yours and
Amazap's all-in price), enter your contact email, and submit it yourself;
submitting publishes the listing once Amazap's checks pass. After any price
change in your code, re-run Amazap's checks. The agent never calls the API
listed until it has read the listing back from Amazap. Lightning Enable does
not hold funds; the payment provider facilitates custody and settlement.
Details:
[Amazap marketplace: Seller handoff](https://github.com/refined-element/lightning-enable-skills/blob/main/references/amazap-marketplace.md#seller-handoff).

## Related skills

- [`create-l402-proxy`](../create-l402-proxy/) to put an API behind a paid proxy
  without code changes.
- [`sell-this`](../sell-this/) for a single paid file or answer.
- [`l402-client-integration`](../l402-client-integration/) for the other side:
  making your code pay someone else's L402 API.
