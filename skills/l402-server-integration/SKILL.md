---
name: l402-server-integration
description: >-
  Add an in-process L402 paywall to the human's own Express or ASP.NET Core API
  with Lightning Enable's open-source middleware (l402-express on npm,
  L402Server.AspNetCore on NuGet), so callers pay sats per request while the API
  keeps its own domain, auth, and observability. Covers the proxy-versus-native
  choice, prerequisites, install, pricing patterns, resource binding,
  idempotency, configuration, troubleshooting, and a self-test. Use when the
  user is a developer editing their own codebase and says things like "add an
  L402 paywall to my API", "charge sats per request in my ASP.NET / Express
  app", "native L402 middleware", or "keep my own auth and still charge over
  Lightning". Do NOT use to put an API behind a paid proxy without code changes
  (use create-l402-proxy), to sell a one-off resource (use sell-this), or to
  make the user's code pay someone else's L402 API (use
  l402-client-integration).
---

# L402 server integration

You are a coding assistant working in the human's own repository. This skill adds
Lightning Enable's **native** L402 middleware to their API: a request to a paid
route without a credential gets `402 Payment Required` with a Lightning invoice;
a request carrying `Authorization: L402 <macaroon>:<preimage>` is verified and
served. The API stays on its own domain, behind its own auth, rate limits, and
logging.

Lightning Enable mints the invoice and macaroon and verifies the credential
through its hosted producer API. The sats settle with the merchant's own payment
provider or wallet. **Lightning Enable does not hold funds; the payment provider
(or the merchant's wallet) facilitates custody and settlement.** The middleware
and the SDK under it are MIT-licensed HTTP-client glue; no key material or
protocol code runs in the human's app.

## What is automated, and what is not

**Automated:** the proxy-versus-native decision, installing the package, wiring
the middleware, pricing the routes, resource binding, configuration, the
troubleshooting checks, and the self-test plan.

**Not automated: the human supplies or approves these.**

- **A Lightning Enable merchant API key** on a plan that includes L402, and a
  receive wallet configured on that merchant (see step 1).
- **The prices,** route by route or as one flat price.
- **An explicit yes before any paid self-test**, after you show the diff.

## What you need

- An Express 4 or 5 app on Node 18 or later, or an ASP.NET Core app on .NET 8 or
  later. Other stacks can call the producer API directly; see the
  [Producer API Reference](https://docs.lightningenable.com/products/agentic-commerce/producer-api-reference).
- The merchant API key, set by the human as an environment variable or in the
  app's secret store. You never read it back or print it.
- The ability to run the project's tests.

Versions this skill was checked against: `l402-express` 0.2.0 and `l402-server`
0.2.0 (npm), `L402Server.AspNetCore` 0.2.0 and `L402Server` 0.2.0 (NuGet). Step 4
explains the one behavior that differs in 0.1.x.

## Flow

### 0. Decide: proxy or native

From the [Native Integration](https://docs.lightningenable.com/products/agentic-commerce/native-integration)
docs page:

| | **Proxy mode** | **Native mode** |
|---|---|---|
| Setup time | ~5 minutes in the dashboard | One `install` + one line of middleware |
| Code changes to your API | None | Add one middleware registration |
| Traffic flows through Lightning Enable | Yes | **No** (your domain, your servers) |
| You can keep your existing auth | Difficult (Authorization header is consumed by L402) | Yes |
| Custom observability / rate limiting | Limited | Full control |
| Best for | Public APIs, experiments, no-existing-auth | Commercial APIs, anything with sensitive infrastructure |

Choose native when the API has its own authentication, custom rate limiting,
observability the human wants to keep, or a host whose DNS they cannot change.
If none of that applies and they want no code changes, stop and use the
[`create-l402-proxy`](../create-l402-proxy/) skill instead. For a single paid
file or answer, use [`sell-this`](../sell-this/).

One thing to check before you start: native mode reads the `Authorization`
header. If the API already authenticates with `Authorization: Bearer …` on the
same routes, the two schemes compete for one header. Ask the human how their
callers will send both before you wire anything.

### 1. Prerequisites

Confirm each of these before you write code. If the Lightning Enable MCP is
installed with the merchant key, `l402_producer(action="status")` reports all of
them and spends nothing; otherwise the human checks the dashboard.

- **A merchant API key.** Generated at **Dashboard → Settings → API Keys**. If the
  human has no account, the [`producer-setup`](../producer-setup/) skill creates
  one with a ~100-sat L402 payment, or they sign up at
  [lightningenable.com](https://www.lightningenable.com).
- **A plan that includes L402.** Agentic Commerce and Agentic Commerce Business
  include it, and so does the Free Producer Sandbox within its caps: a limit on
  distinct endpoints for the life of the account, on challenges per month, and
  on the price of one challenge. The server sets the plan prices; point the human
  at [lightningenable.com](https://www.lightningenable.com) for them.
- **A receive wallet on the merchant.** Without one, minting a challenge fails
  with `payment_provider_not_configured`. Strike (the default lane) or the
  merchant's own wallet over NWC fits L402; OpenNode is a legacy option that does
  not surface preimages and fits L402 poorly. Set it under **Dashboard →
  Settings → Payment Provider**, or with
  `l402_producer(action="configure_receive")` from the MCP (the
  `create-l402-proxy` and `producer-setup` skills walk through it).

Read the status output as the source of truth: plan tier, `l402Enabled`, and the
receiving wallet (`configured`, `provider`). Report the wallet as `<set>` or
`<not set>`; never print a connection string or key.

### 2. Install and wire the middleware

**Express** (from the `l402-express` README):

```bash
npm install l402-express l402-server
```

```ts
import express from "express";
import { l402 } from "l402-express";

const app = express();

// Gate everything under /api/premium behind a 100 sat L402 payment.
app.use("/api/premium", l402({
  apiKey: process.env.LIGHTNING_ENABLE_API_KEY!,
  priceSats: 100,
}));

app.get("/api/premium/weather", (_req, res) => {
  res.json({ temp: 72 });
});

app.listen(3000);
```

Routes not mounted under `l402(...)` pass through untouched, so paid and free
routes mix freely.

**ASP.NET Core** (from the `L402Server.AspNetCore` README):

```bash
dotnet add package L402Server.AspNetCore
```

`L402Server`, the SDK, comes in transitively.

```csharp
using L402Server.AspNetCore;

var builder = WebApplication.CreateBuilder(args);

builder.Services.AddL402AspNetCore(opts =>
{
    opts.ApiKey = builder.Configuration["LightningEnable:ApiKey"]!;
});

var app = builder.Build();
app.UseRouting();
app.UseL402();
app.MapControllers();
app.Run();
```

```csharp
[ApiController]
[Route("api/premium")]
public class PremiumController : ControllerBase
{
    [HttpGet("weather")]
    [L402(PriceSats = 100)]
    public IActionResult Weather() => Ok(new { temp = 72 });
}
```

Endpoints without `[L402]` pass through ungated. **Pipeline order matters:**
`UseL402()` goes after `UseRouting()` (it reads `[L402]` from the matched
endpoint) and before the endpoint executor:

```csharp
app.UseRouting();
app.UseAuthentication();   // any other auth middleware
app.UseAuthorization();
app.UseL402();             // ← here
app.MapControllers();
```

For minimal APIs, attach the attribute as metadata:

```csharp
app.MapGet("/api/premium/weather", () => new { temp = 72 })
    .WithMetadata(new L402Attribute { PriceSats = 100 });
```

### 3. Price the routes

**Express**

- One price for a mount: `app.use("/api/premium", l402({ ..., priceSats: 100 }))`.
- Different prices per sub-path: one `app.use` per prefix.
- Per route in a router:

```js
router.get("/forecast", l402({ apiKey: KEY, priceSats: 100 }), forecastHandler);
router.get("/historical", l402({ apiKey: KEY, priceSats: 50 }), historyHandler);
router.get("/free-info", freeInfoHandler);  // not gated
```

- Function-form, derived from the request (may return a number or a promise):

```ts
app.use("/api/llm", l402({
  apiKey: process.env.LIGHTNING_ENABLE_API_KEY!,
  priceSats: (req) => req.query.model === "premium" ? 500 : 100,
}));
```

- Several mounts can share one SDK client, and its connection pool:

```js
import { L402Server } from "l402-server";
import { l402 } from "l402-express";

const client = new L402Server({ apiKey: process.env.LIGHTNING_ENABLE_API_KEY });

app.use("/api/cheap", l402({ client, priceSats: 10 }));
app.use("/api/premium", l402({ client, priceSats: 500 }));
```

**ASP.NET Core**

- Per route: `[L402(PriceSats = 100)]` on an action, optionally with
  `Description` (shown in the payer's wallet) and `Resource` (see step 4).
- Per controller: put `[L402(PriceSats = 100)]` on the class; an action-level
  `[L402]` overrides it for that action.
- Global flat price for everything through the middleware:

```csharp
app.UseL402(opts => opts.DefaultPriceSats = 100);
```

- Function-form. `PriceSelector` returns `ValueTask<int?>`; a non-null value
  wins, and `null` falls through to the attribute, then `DefaultPriceSats`:

```csharp
app.UseL402(opts =>
{
    opts.PriceSelector = ctx => ValueTask.FromResult<int?>(
        ctx.Request.Query["model"] == "premium" ? 500 : 100);
});
```

Use the docs page's `ValueTask.FromResult<int?>(...)` form shown here: the
package README's `ValueTask.FromResult(...)` produces a `ValueTask<int>`, which
does not match the property's `ValueTask<int?>` type.

Prices are whole sats, 1 or more. In ASP.NET Core a price that resolves below 1
is **not** charged: the middleware logs a warning and lets the request through
ungated. In Express it fails the request with a 502. Validate any computed price.

### 4. Bind each token to the right resource

Every challenge binds the macaroon to a resource: by default the request path
(Express: `req.path`; ASP.NET Core: `HttpContext.Request.Path`). Override it with
`resource` (Express, static or function) or with `Resource` on `[L402]` and
`ResourceSelector` on the options (ASP.NET Core).

**On 0.2.0 and later, the middleware enforces that binding by default.** It sends
the resolved resource with every verification, so Lightning Enable rejects a
token bought for a different path. Opt out with `verifyResource: false`
(Express) or `opts.EnforceResourceOnVerify = false` (ASP.NET Core) only if you
compare the resource yourself.

**On 0.1.x it does not.** If the project pins 0.1.x, the docs warning applies:

> Current versions (`l402-express` 0.1.x, `l402-server` 0.1.x) call the verify
> endpoint with **only the macaroon and preimage**; they do not pass or compare
> the request path or amount. Merchant binding and expiry are always enforced by
> the hosted API, but a token bought for one of your routes will also pass
> verification on a *different* route gated under the same API key, within the
> token's validity window (60 minutes by default).

The ASP.NET Core page says the same of `L402Server.AspNetCore` and `L402Server`
0.1.x. The fix is to upgrade to 0.2.0. If the human cannot upgrade and gates
**multiple prices or resources** under one key, assert the resource in the
handler. Express, from the docs:

```js
router.get("/forecast", l402({ apiKey: KEY, priceSats: 100 }), (req, res) => {
  if (res.locals.l402.resource !== req.path) {
    return res.status(401).json({ error: "Token was purchased for a different resource" });
  }
  res.json({ forecast: "7-day data..." });
});
```

ASP.NET Core, from the docs:

```csharp
[HttpGet("weather"), L402(PriceSats = 100)]
public IActionResult Weather()
{
    var result = (VerificationResult)HttpContext.Items[L402HttpContextKeys.VerificationResult]!;
    if (result.Resource != HttpContext.Request.Path)
    {
        return Unauthorized(new { error = "Token was purchased for a different resource" });
    }
    return Ok(new { temp = 72 });
}
```

Three binding details that bite:

- **Express mount paths.** Under `app.use("/api/premium", l402(...))`, Express
  strips the mount prefix, so the bound resource is `/weather`, not
  `/api/premium/weather`. To bind the full path, pass
  `resource: (req) => req.baseUrl + req.path`.
- **Route parameters multiply resources.** `/items/1` and `/items/2` are two
  resources. Each distinct resource counts against the Free Producer Sandbox
  endpoint cap for the life of the account, and a buyer pays separately for
  each. If one payment should cover a family of URLs, bind a canonical resource
  (`[L402(Resource = "...")]`, `ResourceSelector`, or `resource`).
- **Paying clients cache by path prefix.** The L402 client libraries cache a
  credential under the host plus the first two path segments and present it to
  sibling paths. With enforcement on, a sibling path bound separately answers
  401, and those clients return the 401 without paying. If one purchase should
  cover several routes, bind them to one canonical resource at one price.

### 5. Decide how challenges are reused

When a request mints a challenge without an idempotency key, Lightning Enable
reuses one challenge per caller, resource, and price while the invoice is live,
and it identifies the caller by the IP address of the connection it sees. With
native middleware, that connection comes from **your server**, not the end
caller, so every buyer of the same route at the same price inside that window
receives the same invoice. Once one buyer pays it, the others' wallets fail to
pay an invoice that is already settled.

If more than one caller may buy the same route at the same time, set
`idempotencyKey` (Express) or `IdempotencyKeySelector` (ASP.NET Core). The value
is sent as `X-Idempotency-Key`. Make it identify the **caller, the resource, and
the price** together. Lightning Enable binds a live key to one resource and
price, and reusing it for a different one returns 409 `idempotency_key_reuse`,
which the middleware surfaces as a 502. A key over 200 characters is refused
with 400 `invalid_idempotency_key`, also surfaced as a 502.
Every minted challenge counts toward the plan's monthly challenge volume
whether or not anyone pays it.

### 6. What the caller sees

Without a credential:

```http
HTTP/1.1 402 Payment Required
Content-Type: application/json
WWW-Authenticate: L402 macaroon="AgELbWFjYXJvb24...", invoice="lnbc1u1p3..."

{
  "error": "Payment Required",
  "l402": {
    "macaroon": "AgELbWFjYXJvb24...",
    "invoice": "lnbc1u1p3...",
    "amount_sats": 100,
    "payment_hash": "abc123...",
    "expires_at": "2026-05-12T01:00:00Z",
    "resource": "/api/premium/weather"
  }
}
```

With a valid `Authorization: L402 <macaroon>:<preimage>`: your handler runs and
returns its normal 200. A token stays valid for the token-validity window (60
minutes by default), so a caller can reuse it for that resource; if a route
needs strict single use, track `paymentHash` in your handler.

Other outcomes:

- **401** `{ "error": "Unauthorized", "message": ... }`: the credential failed
  verification (wrong resource, expired, wrong merchant). Override with
  `onInvalidToken` (Express) or `OnInvalidToken` (ASP.NET Core); your handler
  then owns the whole response.
- **502** `{ "error": "Bad Gateway", "message": ... }`: the middleware could not
  get a usable answer from Lightning Enable. The `message` carries the reason;
  step 9 maps the common ones.

### 7. Read the verified credential

After a successful verification the middleware hands the result to your code:
the resource, `amountSats` / `AmountSats`, and `paymentHash` / `PaymentHash`.
Use it for usage logging and per-endpoint analytics.

```js
app.get("/api/premium/weather", (_req, res) => {
  const { resource, amountSats, paymentHash } = res.locals.l402;
  console.log(`Served ${resource} for ${amountSats} sats (${paymentHash})`);
  res.json({ temp: 72 });
});
```

```csharp
[HttpGet("weather"), L402(PriceSats = 100)]
public IActionResult Weather()
{
    var result = (VerificationResult)HttpContext.Items[L402HttpContextKeys.VerificationResult]!;
    _logger.LogInformation(
        "Served {Resource} for {Sats} sats ({Hash})",
        result.Resource, result.AmountSats, result.PaymentHash);
    return Ok(new { temp = 72 });
}
```

In a controller, read `HttpContext` through the property, as shown. MVC does not
bind `HttpContext` as an action parameter, so the package README's
`Weather(HttpContext ctx)` variant does not work in a controller; in a minimal
API handler the parameter is injected. `VerificationResult` lives in the
`L402Server` namespace, so add `using L402Server;`.

The payment hash is safe to log. Never log the `Authorization` header, the
macaroon, or the preimage.

### 8. Configuration reference

**The API key.** Express reads it from wherever you pass `apiKey`; the README uses
`process.env.LIGHTNING_ENABLE_API_KEY`. ASP.NET Core reads it from configuration
key `LightningEnable:ApiKey`, which the environment variable
`LightningEnable__ApiKey` or the app's secret store supplies. Never commit it; if
the project uses `.env`, confirm `.env` is in `.gitignore` first.

**The base URL.** Both default to `https://api.lightningenable.com`. Override it
only to test against another Lightning Enable instance: `baseUrl` (Express, when
you pass `apiKey`; with `client`, set it on `new L402Server({ ... })`) or
`opts.BaseUrl` inside `AddL402AspNetCore` (ASP.NET Core).

Express options (`l402({...})`):

| Option | Default | Notes |
|---|---|---|
| `apiKey` or `client` | one is required | Mutually exclusive. `client` is a shared `L402Server`. |
| `priceSats` | required | Number or function; 1 or more. |
| `resource` | `req.path` | Bound as the macaroon's path caveat. |
| `description` | none | Shown in the payer's wallet. |
| `idempotencyKey` | none sent | See step 5. |
| `verifyResource` | same as `resource` | `false` turns off server-side path enforcement. |
| `baseUrl` | `https://api.lightningenable.com` | Honored only with `apiKey`. |
| `onInvalidToken` | sends 401 | `(req, res, failure, next)`; must respond or call `next`. |

The SDK client (`new L402Server({...})`) also takes `timeoutMs` (default 10000)
and `fetch`, which lets tests stub the producer API.

ASP.NET Core options (`app.UseL402(opts => ...)`, `L402AspNetCoreOptions`):

| Option | Default | Notes |
|---|---|---|
| `DefaultPriceSats` | `null` | Flat price when no `[L402]` applies. |
| `PriceSelector` | `null` | `Func<HttpContext, ValueTask<int?>>`; `null` falls through. |
| `ResourceSelector` | request path | Bound as the macaroon's path caveat. |
| `DescriptionSelector` | `null` | Shown in the payer's wallet. |
| `IdempotencyKeySelector` | `null` | See step 5. |
| `EnforceResourceOnVerify` | `true` | `false` turns off server-side path enforcement. |
| `OnInvalidToken` | sends 401 | `Func<HttpContext, VerificationResult, ValueTask>`; your callback owns the response. |

The SDK options (`L402ServerOptions`, set in `AddL402AspNetCore`) are `ApiKey`,
`BaseUrl`, and `Timeout` (default 10 seconds).

### 9. Troubleshoot

| Symptom | Likely cause | Do this |
|---|---|---|
| 502 on every request | The middleware cannot reach Lightning Enable, or the key is wrong | Check the key is set (report `<set>` / `<not set>`), outbound access to `api.lightningenable.com`, and that the subscription is active. Read the 502's `message`. |
| 502 whose message is a plan or subscription error, such as `l402_not_enabled` | The producer API answered 403: L402 is not enabled on the plan, the trial ended, or the subscription lapsed | Check the plan in the dashboard or with `l402_producer(action="status")`. |
| 502 with `payment_provider_not_configured` | No receive wallet on the merchant | Configure one (step 1), then retry. |
| 502 with `idempotency_key_reuse` | One live idempotency key was reused for a different resource or price | Include the resource and price in the key (step 5). |
| 502 naming a plan cap (`plan_endpoint_limit`, `plan_price_limit`, `plan_volume_limit`) | A Free Producer Sandbox cap | Lower the price, reuse resources, or add billing. Do not work around a cap. |
| Every request returns 402, even after payment | The `Authorization` header is not reaching the app | Behind a reverse proxy or load balancer, confirm it forwards `Authorization`. |
| `[L402]` attributes do nothing | `UseL402()` is before `UseRouting()` or after `MapControllers()` | Fix the pipeline order (step 2). |
| A paid route serves free | ASP.NET Core resolved a price below 1, or the route is outside the Express mount | Check the computed price and the mount path. |
| 401 on a sibling route right after a purchase | The token is bound to the first route and enforcement is on | Intended. Bind a canonical resource if one purchase should cover both (step 4). |
| Second buyer's payment fails while the first succeeded | Shared challenge with no idempotency key | Set a per-caller key (step 5). |

### 10. Self-test

1. **Run the project's own tests.** For unit tests with no network, inject the
   HTTP layer: Express takes a `client` built with `new L402Server({ apiKey, fetch: mockFetch })`;
   on .NET, `L402ServerClient` has a constructor overload that accepts an external
   `HttpClient`, which you can build on a fake `HttpMessageHandler`.
2. **Show the human the diff.**
3. **Prove the 402 for free.** Start the app and request a paid route with no
   credential. A 402 with a `WWW-Authenticate: L402 ...` header and the JSON body
   above proves the key, the plan, and the receive wallet. Nothing is paid.
4. **Pay once, with the human's yes.** Set a staging route to 1 sat. Then either:
   - From code: use the [`l402-client-integration`](../l402-client-integration/)
     skill's client snippet with a 10-sat cap and the route's URL. This works
     against `localhost`.
   - From the MCP, once the API is deployed at a public URL:
     `access_l402_resource(url="<public route URL>", max_sats=10)`. It sends GET or
     HEAD only, and it refuses `localhost` and private addresses on purpose, so it
     cannot test a local server.
   Expect 402, then a payment of 1 sat, then 200 with your handler's response.
5. **Run one payment at a time.** Each 402 mints a fresh challenge; parallel
   attempts cross invoices.

If the paying wallet is the same one the merchant receives into, some wallets
refuse to pay their own invoice. That is wallet policy, not a broken route: pay
from a second wallet, or stop at step 3. The docs also describe testing with an
OpenNode dev (testnet) key on the merchant, where no real money moves; see
"Testing your integration" on the Native Integration page.

If the MCP has the merchant key, `l402_producer(action="list_challenges",
challenge_status="paid")` lists challenges that have been paid, where the
deployment supports that route.

### 11. Hand off

Tell the human, plainly:

- **Where the API lives:** on their own domain, unchanged. Lightning Enable mints
  and verifies; it never sees the response bodies or the human's own auth.
- **Where the money goes:** every sat a buyer pays settles to the merchant's
  payment provider or wallet. **Lightning Enable does not hold funds**, and it
  takes no per-transaction cut; the plan is a flat subscription.
- **What changed:** packages added, files edited, routes priced and at what
  price, the binding and idempotency choices, and the configuration key the app
  reads (the name, not the value).
- **What to watch:** the plan's caps, and sales in the dashboard or with
  `l402_producer(action="list_challenges", challenge_status="paid")`.
- **Where to read more:** the
  [Native Integration](https://docs.lightningenable.com/products/agentic-commerce/native-integration),
  [Express](https://docs.lightningenable.com/products/agentic-commerce/native-integration-express),
  and [ASP.NET Core](https://docs.lightningenable.com/products/agentic-commerce/native-integration-aspnet)
  docs pages; the package repositories
  [le-server-l402-express-node](https://github.com/refined-element/le-server-l402-express-node),
  [le-server-l402-node](https://github.com/refined-element/le-server-l402-node),
  [le-server-l402-aspnetcore-dotnet](https://github.com/refined-element/le-server-l402-aspnetcore-dotnet),
  and [le-server-l402-dotnet](https://github.com/refined-element/le-server-l402-dotnet);
  and the runnable examples
  [l402-example-node](https://github.com/refined-element/l402-example-node) and
  [l402-example-aspnet](https://github.com/refined-element/l402-example-aspnet).

### 12. Optional: list on Amazap

[Amazap](https://amazap.com/sell) is a storefront where agents find and buy
L402 endpoints. Listing there is optional distribution, and the human decides.
Offer it only after the self-test (step 10), once the API is deployed at a
public HTTPS URL, and only as an offer; no answer means no.

- **Existing row first.** A published API can already be in Amazap's catalog,
  imported from 402 Index. Search by service name,
  `GET https://amazap.com/api/products?q=<service name>`, and page with
  `limit` and `offset` until `offset >= total` before you conclude there is
  no row. Match the full endpoint URL the row stores (a route URL or the API's
  base URL) against this API. Search skips hidden rows, so when the human
  knows a slug, also read `GET https://amazap.com/api/products/<slug>`, and
  look for the service in https://amazap.com/sitemap.xml. If a row exists,
  report its `hidden`, `listingState`, and `healthStatus`, and let the human
  decide with Amazap whether to refresh it. Never draft a duplicate listing.
- **Ask first.** Ask whether the human wants an Amazap listing before any paid
  gate check, so no sats are spent on a listing they don't want. No answer
  means no.
- **Gate.** First, with the human's explicit yes, set the route's chosen price
  in the code (shown as a diff) and have it deployed, so the read-only check
  below quotes the price you would list. Then run
  [`l402-compatibility-report`](../l402-compatibility-report/)
  on the route's public URL with the method you would list:
  `python scripts/l402_check.py <url> --json --max-sats <cap> --output mode-a.json`
  from that skill's folder, with the human's cap in sats (add
  `--method POST` for a `POST` route). Its paid check reads that saved report.
  Continue only when the read-only report's invoice amount equals the chosen
  price. If `l402-compatibility-report` is not installed, the listing is not
  ready; give the human its GitHub URL,
  https://github.com/refined-element/lightning-enable-skills/tree/main/skills/l402-compatibility-report.
  Take the `classification` field from the JSON. Offer the listing as ready
  only at `FULFILLMENT_VERIFIED` or `MARKETPLACE_READY`, and only once example
  parameters are known, replay behavior is understood, no error or output
  exposes a secret, and the human has chosen title, description, category,
  and price. On the API's own domain, `MARKETPLACE_READY` is the target:
  beyond `FULFILLMENT_VERIFIED` it needs a mainnet invoice, a 402 to a
  bodyless request within 8 seconds, no redirect between the listed URL and
  the 402, an `openapi.json` or `llms.txt` at the host root (see Fields), and
  a paid amount equal to the read-only quote. `CHALLENGE_COMPATIBLE` is the
  most the read-only check can return for a correct endpoint: say
  "challenge-compatible, fulfillment unverified", and do not offer the listing
  as ready until the paid check below lifts it. A private, loopback, link-local, or
  non-HTTPS URL, a non-mainnet invoice or a 402 slower than 8 seconds, a `200`
  to an unpaid request, or a `400`, `415`, or `422` to a request with no body
  is not listing-ready. Step 10's testnet key and a slow cold start are the
  usual causes of the middle two; fix them in the deployment, never by paying
  again. The last case means the 402 must come before body validation: in
  ASP.NET Core, step 2's pipeline order; in Express, mount the `l402`
  middleware before any body validator on the route.
- **Pay once.** Pay for the gate once, never twice. A test against `localhost`
  doesn't count. The paid check runs on `GET` or `HEAD` only, so a `POST`,
  `PUT`, or `DELETE` route stays at `CHALLENGE_COMPATIBLE` here and is never
  offered as ready. If the self-test (step 10) made no payment for this
  endpoint by any means, run the report's paid check once, with the human's
  yes; otherwise the cases below apply and the agent never pays again. The
  paid check needs a
  wallet that can pay this endpoint: if step 10 stopped at the free 402
  because the wallet refused to pay its own invoice, do not attempt the paid
  check with the same wallet, and the listing is not ready. If step 10 paid
  this exact public URL with the same method through `access_l402_resource`,
  from either wallet (the merchant's own or a second one), record that call as
  the evidence (steps 6 and 7 of `l402-compatibility-report`, with
  `--mode-a mode-a.json` and that call's token piped on stdin) instead of
  paying again. If that token is gone, the listing is not ready; do not pay
  again. A self-test payment of a testnet invoice, such as one made with step
  10's testnet key, is not reuse evidence: the listing is not ready in that
  run, and the agent does not pay again. A step 10 payment of this URL with a different method also counts as
  paid: the listing is not ready; do not pay again. A payment through
  `pay_l402_challenge` counts as paid. The agent has no tool that fetches the
  resource with a token it already holds, and `access_l402_resource` would pay
  again, so in that run the gate stays at `CHALLENGE_COMPATIBLE`: the listing
  is not ready, and the agent does not pay again. A step 10 payment of this
  public URL from code (the `l402-client-integration` snippet), or one made by
  hand, outside both tools, also counts as paid: the listing is not ready in
  that run, and the agent does not pay again. If the human wants the paid
  check later, they choose it in a later run, and the skill says plainly that
  it is a second payment for this endpoint. Without the token the paid check
  ends `INCONCLUSIVE`, so a paid check through the Python MCP server is never
  offered as ready.
- **Draft, never publish.** Only once the gate passes, call Amazap's read-only
  `list_my_endpoint` tool when the host lists it; otherwise give the human
  https://amazap.com/sell and a draft built from the reference's listing-copy
  template. Show the draft beside the current Amazap seller terms, linked
  live.
- **Fields.** Amazap prefills the title, description, category, and example
  parameters from `openapi.json` or `llms.txt` at the root of the API's own
  host. Without either, the human supplies the title, description, category,
  and example parameters by hand. Adding one of those files is a code change:
  show the diff first.
- **Two prices.** Show the seller price (the invoice amount the route's code
  sets) and Amazap's all-in shopper price separately, never added together;
  the all-in figure comes from Amazap's draft or page. Amazap locks the price
  at listing time, so list the route at the human's chosen price, not step
  10's staging price, and after any price change in the code the seller must
  re-run Amazap's checks. The order matters: the chosen price goes in before
  the gate's read-only check (see Gate). A 1-sat token from step 10 then fails
  the report's `stable_price` check against the new quote, so its result is
  at most `FULFILLMENT_VERIFIED`, which is ready; if the token no longer
  verifies after the price change, the result is lower and not ready. Either
  way the agent never pays again to reach `MARKETPLACE_READY`.
- **The human decides.** Without the human's explicit approval, never submit
  the listing, accept seller terms, provide or infer a contact email, opt into
  announcements, publish a Nostr handle, change the endpoint's price, or claim
  a commercial relationship among any of Lightning Enable, Amazap, or Amboss.
  The human enters the contact email and submits. Submitting publishes the
  listing automatically once Amazap's checks pass, so the human reviews the
  email, the copy, both prices, and the terms first.
- **Read back.** Never call the endpoint listed or live until you have read
  its product page or `GET https://amazap.com/api/products/<slug>` and checked
  `hidden`, `listingState`, and `healthStatus`. Before you say "listed", the
  row's endpoint URL and displayed seller price must match this route;
  otherwise report the row's state and that it may be an imported row, not
  this listing. Call it listed only when the row also has `hidden: false` or
  the page shows the listing as buyable; otherwise report those three fields.
  Listed is not verified paid delivery.

Lightning Enable does not hold funds; the payment provider facilitates custody
and settlement. Full rules, including the listing-copy template:
[Amazap marketplace: Seller handoff](https://github.com/refined-element/lightning-enable-skills/blob/main/references/amazap-marketplace.md#seller-handoff).

## Safety rules

- **Show the diff and get an explicit yes before any paid call.** The free 402
  check needs no yes; a payment does.
- **One L402 payment at a time.**
- **Never print secrets.** The merchant API key, wallet credentials, macaroons,
  and preimages stay out of your output, the code, logs, and commits. Report
  `<set>` or `<not set>`.
- **The prices are the human's call.** Do not invent them, and never quote plan
  prices; the server sets those.
- **Do not weaken enforcement** (`verifyResource: false`,
  `EnforceResourceOnVerify = false`) without a handler-side check in its place.
- **Run the project's tests** before you report the change as done.

## What this is NOT

- **Not custody.** Lightning Enable does not hold funds; the payment provider (or
  the merchant's wallet) facilitates custody and settlement.
- **Not a proxy.** Traffic never flows through Lightning Enable. For a paid proxy
  with no code changes, use `create-l402-proxy`.
- **Not demand.** A paywall creates a way to get paid, not buyers. Do not promise
  revenue.
- **Not a per-transaction fee.** The subscription is flat; every sat a buyer pays
  settles to the merchant.

## Example

> User: "Add an L402 paywall to our ASP.NET Core API: 25 sats for
> `/api/reports/{id}`, everything else free. We keep our own JWT auth on other
> routes."
>
> 1. Native is right: own auth, own domain. Confirm the paid route does not also
>    need `Authorization: Bearer`.
> 2. `l402_producer(action="status")`: L402 enabled, receive wallet `<set>`.
> 3. `dotnet add package L402Server.AspNetCore`; `AddL402AspNetCore` reading
>    `LightningEnable:ApiKey`; `app.UseL402()` after `UseAuthorization()`.
> 4. `[L402(PriceSats = 25, Resource = "/api/reports")]` on the action, so one
>    purchase covers every report id and the Free Producer Sandbox counts one
>    endpoint. (Bind per id instead if each report is sold separately.)
> 5. `IdempotencyKeySelector` built from the caller, the resource, and the price.
> 6. Tests pass; show the diff. Request the route with no credential: 402 with
>    `WWW-Authenticate: L402`.
> 7. With a yes, set staging to 1 sat and pay it once from code with a 10-sat cap:
>    402, 1 sat, 200.
> 8. Hand off: "Reports cost 25 sats, settled to your Strike account. Lightning
>    Enable mints and verifies; your API and auth are unchanged."
