---
name: l402-client-integration
description: >-
  Wire the human's own Python, .NET, or TypeScript code to pay L402 APIs
  automatically with the open-source L402 client libraries (l402-requests on
  PyPI and npm, L402Requests on NuGet): pick the package, configure a
  preimage-returning wallet through environment variables, set budget limits,
  handle the library's errors, and prove the wiring with a test call that costs
  about 1 sat. Use when the user is a developer editing their own codebase and
  says things like "add L402 support to my app", "my code gets a 402 with a
  Lightning invoice", "call a paid API from Python/.NET/TypeScript", "integrate
  l402-requests", or "my agent framework needs to pay per call". Do NOT use when
  an agent should pay interactively through the Lightning Enable MCP (use
  pay-l402-anywhere), or to charge for the user's own API (use
  l402-server-integration). The MCP is optional for this skill.
---

# L402 client integration

You are a coding assistant working in the human's own repository. This skill
turns "my code gets a 402 with a Lightning invoice" into a few lines of code: one
of the open-source L402 client libraries detects the 402, pays the invoice from a
wallet the human configures, and retries with `Authorization: L402
<macaroon>:<preimage>`. The caller gets back an ordinary HTTP response.

The money moves from the human's wallet to the API seller's wallet or payment
provider. **Lightning Enable does not hold funds; the wallet (or the payment
provider) facilitates custody and settlement.** The libraries are MIT-licensed
HTTP clients and need no Lightning Enable account.

## What is automated, and what is not

**Automated:** choosing the package for the project's language, adding the
dependency, writing the client code, the budget configuration, error handling,
`.gitignore` hygiene, and one test call against a public endpoint that charges
about 1 sat.

**Not automated: the human supplies or approves these.**

- **A Lightning wallet that returns payment preimages**, with its credential in
  an environment variable: LND, an NWC (Nostr Wallet Connect) wallet such as
  CoinOS, CLINK, or Alby Hub, or Strike. This skill does not create or fund a
  wallet. For guided wallet setup, use the `agent-wallet-setup` skill.
- **The spending limits.** Per request, per hour, and per day, in sats.
- **An explicit yes before the first paid call**, after you show the diff.

## What you need

- The project's language and HTTP stack. Python, .NET, and TypeScript or
  JavaScript (Node 18 or later) are covered.
- A wallet credential the human sets in their own shell or secret store. You
  never read it back or print it.
- The ability to run the project's tests and one script.

The Lightning Enable MCP is not required. If it is installed, `test_l402_payment`
proves the wallet works before you write any code, but that is optional.

Versions this skill was checked against: `l402-requests` 0.8.0 (PyPI),
`L402Requests` 0.11.0 (NuGet), and `l402-requests` 0.8.0 (npm). If the project
pins older versions, read that version's README before you copy a snippet.

## Flow

### 0. Preconditions and human checkpoints

Before you edit anything, ask in one message and wait for the answers:

1. **Which wallet?** "Which Lightning wallet should this code pay from: LND, an
   NWC wallet, or Strike? Set its credential as an environment variable in your
   shell or secret store; do not paste it here." If the human pastes a
   credential anyway, do not repeat it, do not write it into any file, and tell
   them to rotate it if it reached a shared log.
2. **What limits?** "What is the most one call may cost, and the most per hour
   and per day?" The library defaults are 1,000 sats per request, 10,000 per
   hour, and 50,000 per day. Smaller is safer.
3. **Which domains?** "Which API hosts may this code pay?" Every library takes a
   domain allowlist, and a short list is the strongest guard you have.

### 1. Pick the package

| Language | Install | Import | One call |
|---|---|---|---|
| Python 3.10+ | `pip install l402-requests` | `import l402_requests` | `l402_requests.get(url)` |
| .NET 8 or 10 | `dotnet add package L402Requests` | `using L402Requests;` | `await client.GetAsync(url)` on an `L402HttpClient` |
| TypeScript / Node 18+ | `npm install l402-requests` | `import { get } from 'l402-requests';` | `await get(url)` |

The Python and npm packages share the name `l402-requests`; the .NET package is
`L402Requests`. Repositories: `refined-element/l402-requests` (Python),
`refined-element/l402-dotnet` (.NET), and `refined-element/l402-ts` (TypeScript).

Quick starts, as the READMEs give them:

```python
import l402_requests

response = l402_requests.get("https://api.example.com/paid-resource")
print(response.json())
```

```csharp
using L402Requests;

using var client = new L402HttpClient();
var response = await client.GetAsync("https://api.example.com/paid-resource");
Console.WriteLine(await response.Content.ReadAsStringAsync());
```

```typescript
import { get } from 'l402-requests';

const response = await get("https://api.example.com/paid-resource");
console.log(await response.json());
```

Prefer an explicit client object over the module-level shortcut in real code,
because the client object is where the budget, the wallet, and the credential
cache live. Python also ships `AsyncL402Client` for `asyncio` code, and the .NET
package registers with `IHttpClientFactory` through `AddL402HttpClient`:

```csharp
// In Program.cs
builder.Services.AddL402HttpClient("myapi", options =>
{
    options.MaxSatsPerRequest = 500;
    options.MaxSatsPerHour = 5000;
    options.AllowedDomains = ["api.example.com"];
});
```

The Python README also has drop-in tool wrappers for LangChain, AG2 (AutoGen),
and CrewAI; the .NET README has a Semantic Kernel plugin. Use those when the
project is built on one of those frameworks.

### 2. Configure the wallet

All three libraries detect the wallet from environment variables, in the same
order:

| Priority | Wallet | Environment variables | Pays L402 |
|---|---|---|---|
| 1 | LND | `LND_REST_HOST` + `LND_MACAROON_HEX` (`LND_TLS_CERT_PATH` optional in Python and .NET) | Yes |
| 2 | NWC | `NWC_CONNECTION_STRING` | Yes (CoinOS, CLINK, Alby Hub) |
| 3 | Strike | `STRIKE_API_KEY` | Yes |
| 4 | OpenNode | `OPENNODE_API_KEY` | **No** |

Rules that matter:

- **OpenNode cannot pay L402.** It returns no preimage, so a payment would settle
  and still buy no access. All three libraries refuse before any funds move, but
  OpenNode is still auto-detected: an `OPENNODE_API_KEY`-only setup resolves to a
  wallet that rejects every 402. Switch the human to LND, NWC, or Strike.
- **The first configured wallet wins.** If both `LND_*` and `STRIKE_API_KEY` are
  set, the code pays from LND. Ask which one the human means, and have them unset
  the others.
- **A config file is the fallback.** Each library also reads
  `~/.lightning-enable/config.json` (the Lightning Enable MCP's file) when no
  environment variable is set, and a `wallets.priority` value there moves one
  wallet to the front. Environment variables always win over the file. If the
  human also runs the MCP, say so: the code may pay from the MCP's wallet.
- **NWC packaging differs by language.** Python: NWC is part of the base install;
  the `[nwc]` extra still resolves but is a no-op. .NET: built in, nothing extra.
  TypeScript: install the optional peer dependencies
  `npm install "@noble/secp256k1@^1.7.1" ws`.
- **NWC encryption.** All three auto-detect NIP-04 or NIP-44 v2 from the wallet's
  info event. If a wallet publishes none, pin it with `NWC_ENCRYPTION=nip44_v2`
  (Alby Hub) or `NWC_ENCRYPTION=nip04`. A wrong scheme shows up as a payment
  timeout, because the wallet drops requests it cannot decrypt.

Strike is the READMEs' recommendation when the human has no node: full preimage
support and no infrastructure. Primal's NWC does not return preimages and cannot
pay L402.

### 3. Set the budget

Budgets are on by default in all three libraries, and a payment over any limit
fails **before** the wallet is called.

```python
from l402_requests import L402Client, BudgetController

# Custom budget limits
client = L402Client(
    budget=BudgetController(
        max_sats_per_request=500,     # Max per single payment (default: 1000)
        max_sats_per_hour=5000,       # Hourly rolling limit (default: 10000)
        max_sats_per_day=25000,       # Daily rolling limit (default: 50000)
        allowed_domains={"api.example.com"},  # Optional domain allowlist
    )
)
```

```csharp
using var client = new L402HttpClient(new L402Options
{
    MaxSatsPerRequest = 500,     // Max per single payment (default: 1000)
    MaxSatsPerHour = 5000,       // Hourly rolling limit (default: 10000)
    MaxSatsPerDay = 25000,       // Daily rolling limit (default: 50000)
    AllowedDomains = ["api.example.com"],  // Optional domain allowlist
});
```

```typescript
import { L402Client, BudgetController } from 'l402-requests';

const client = new L402Client({
  budget: new BudgetController({
    maxSatsPerRequest: 500,     // Max per single payment (default: 1,000)
    maxSatsPerHour: 5000,       // Hourly rolling limit (default: 10,000)
    maxSatsPerDay: 25000,       // Daily rolling limit (default: 50,000)
    allowedDomains: new Set(["api.example.com"]),
  }),
});
```

Each library can switch budgets off (`budget=None` in Python,
`BudgetEnabled = false` in .NET, `budget: null` in TypeScript). Do not do that
unless the human asks for it in so many words.

**The wallet balance is the only hard ceiling.** The budget lives in memory on
one client object: it resets when the process restarts, and two processes or
two client objects each get their own allowance. Tell the human to fund the
wallet with no more than the code may spend, and to treat the budget as a
guardrail inside that.

All three libraries also refuse an invoice whose amount they cannot read
(`InvoiceAmountUnknownError` / `InvoiceAmountUnknownException`) instead of paying
it, so an amountless invoice can never skip the budget.

Every payment lands in a per-client spending log: `client.spending_log` (Python),
`client.SpendingLog` (.NET), `client.spendingLog` (TypeScript), with totals for
the last hour, by domain, and as JSON. Each record carries the macaroon and the
preimage, so never log the records whole.

### 4. Know what is cached and what is retried

- **One payment, one retry.** On a 402 the client parses the challenge, checks the
  budget, pays, and retries the request once with the credential. It does not
  loop. A 402 with no recognizable challenge is returned to you as-is.
- **Credentials are cached** in an LRU cache on the client object: 256 entries,
  one-hour time-to-live by default (.NET: `CacheMaxSize` and `CacheTtlSeconds` on
  `L402Options`; TypeScript: `maxSize` and `defaultTtlMs` on `CredentialCache`;
  Python: `max_size` and `default_ttl` on `CredentialCache`). The cache key is the
  host plus the **first two path segments**, so a credential paid at
  `/api/v1/forecast` is also presented to `/api/v1/history`.
- **What that means:** if the server issued a credential that covers both paths,
  the second call is free. If the server binds credentials to one path, it either
  answers with a fresh 402 (the library pays again) or with a 401. **On a 401 the
  library returns the 401 and pays nothing.** If you see a 401 right after a
  successful payment on a sibling path, that is the cause. Use a fresh client
  object (the cache lives on the instance), or in Python and TypeScript pass your
  own `CredentialCache` and call its `clear()`.
- **Draft-00 `Payment` challenges** (the MPP `draft-httpauth-payment-00` profile)
  are supported from Python 0.8.0, .NET 0.10.0, and TypeScript 0.8.0; those
  credentials are single-use, so they are never cached, and L402 is still
  preferred when a server offers both.

### 5. Handle the errors

Every library error derives from one base class: `L402Error` (Python and
TypeScript) or `L402Exception` (.NET). The ones to handle:

| Situation | Python | .NET | TypeScript | Funds moved |
|---|---|---|---|---|
| Over a budget limit | `BudgetExceededError` | `BudgetExceededException` | `BudgetExceededError` | No |
| Host not in the allowlist | `DomainNotAllowedError` | `DomainNotAllowedException` | `DomainNotAllowedError` | No |
| No wallet configured | `NoWalletError` | `NoWalletException` | `NoWalletError` | No |
| Wallet cannot return preimages (OpenNode) | `UnsupportedWalletError` | `UnsupportedWalletException` | `UnsupportedWalletError` | No |
| Invoice amount unreadable | `InvoiceAmountUnknownError` | `InvoiceAmountUnknownException` | `InvoiceAmountUnknownError` | No |
| Draft-00 challenge already expired | `ChallengeExpiredError` | `ChallengeExpiredException` | `ChallengeExpiredError` | No |
| Payment failed, including "payment succeeded but no preimage returned" | `PaymentFailedError` | `PaymentFailedException` | `PaymentFailedError` | **Maybe** |

`UnsupportedWalletError` and `InvoiceAmountUnknownError` are precondition
failures, not subclasses of `PaymentFailedError`, so a handler that catches only
payment failures misses them. Catch them explicitly, then fall through to the
base class. The .NET README's handler:

```csharp
using L402Requests;

using var client = new L402HttpClient();
try
{
    var response = await client.GetAsync("https://api.example.com/paid-resource");
}
catch (BudgetExceededException e)
{
    Console.WriteLine($"Over budget: {e.LimitType} limit is {e.LimitSats} sats");
}
catch (InvoiceAmountUnknownException e)
{
    Console.WriteLine($"Refused unpriceable invoice: {e.Reason}");
}
catch (UnsupportedWalletException e)
{
    Console.WriteLine($"Wallet unusable for L402: {e.WalletReason}");
}
catch (PaymentFailedException e)
{
    Console.WriteLine($"Payment failed: {e.Reason}");
}
catch (NoWalletException)
{
    Console.WriteLine("No wallet configured");
}
```

The TypeScript README's handler, which ends by rethrowing what it did not
recognize:

```typescript
import {
  L402Client,
  BudgetExceededError,
  InvoiceAmountUnknownError,
  UnsupportedWalletError,
  PaymentFailedError,
  NoWalletError,
} from 'l402-requests';

const client = new L402Client();

try {
  const response = await client.get("https://api.example.com/paid-resource");
} catch (e) {
  if (e instanceof BudgetExceededError) {
    console.log(`Over budget: ${e.limitType} limit is ${e.limitSats} sats`);
  } else if (e instanceof InvoiceAmountUnknownError) {
    console.log(`Refused unpriceable invoice: ${e.reason}`);
  } else if (e instanceof UnsupportedWalletError) {
    console.log(`Wallet unusable for L402: ${e.walletReason}`);
  } else if (e instanceof PaymentFailedError) {
    console.log(`Payment failed: ${e.reason}`);
  } else if (e instanceof NoWalletError) {
    console.log("No wallet configured");
  } else {
    throw e; // don't swallow what you didn't recognise
  }
}
```

The Python README has no handler snippet. Write the same shape with the Python
names from the table, importing them from `l402_requests`. Python's
`BudgetExceededError` carries `limit_type`, `limit_sats`, `current_sats`, and
`invoice_sats`; `PaymentFailedError` carries `reason`.

**Never wrap a paid call in an automatic retry loop.** A `PaymentFailed*` error
can mean the sats moved and the preimage did not come back ("payment succeeded
but no preimage returned"). Retrying asks the server for a fresh challenge and
pays again. Surface the error to a human instead. On .NET 0.11.0 and later, LND
and NWC wallets implement `IPaymentLookup`, which answers `Paid`, `NotPaid`, or
`Unknown` for a payment hash; the .NET README shows the call.

### 6. Keep the secrets out of the code

- Credentials come from environment variables or the deployment's secret store.
  Never hardcode an API key, an NWC string, or an LND macaroon, and never pass one
  as a literal to an explicit wallet constructor in committed code.
- If the project uses a `.env` file, confirm `.env` is listed in `.gitignore`
  before you create the file, and add it if it is missing. Commit a
  `.env.example` with variable names and empty values only.
- Do not log `Authorization` headers, macaroons, or preimages, and do not log
  spending-log records whole.
- When you report wallet status to the human, say `<set>` or `<not set>` for each
  variable. Never print a value.
- Run `git status` before you finish and make sure no credential file is staged.

### 7. Prove it with one call

Before anything spends sats:

1. **Run the project's own tests** and make sure the change builds and passes.
2. **Show the human the diff.**
3. **Ask for a yes** for one test payment of about 1 sat.

The public test endpoint is the one the Lightning Enable MCP's
`test_l402_payment` tool uses: `https://api.lightningenable.com/l402/test/ping`.
It charges 1 sat. Call it with a tight budget and an allowlist of that host only:

```python
from l402_requests import L402Client, BudgetController

client = L402Client(
    budget=BudgetController(
        max_sats_per_request=10,
        allowed_domains={"api.lightningenable.com"},
    )
)
response = client.get("https://api.lightningenable.com/l402/test/ping")
print(response.status_code)
print(f"Total spent: {client.spending_log.total_spent()} sats")
```

In .NET or TypeScript, use the budget snippet from step 3 with
`MaxSatsPerRequest = 10` / `maxSatsPerRequest: 10` and the same URL.

- **200 and about 1 sat spent:** the wallet is connected, returns preimages, and
  completes L402 end to end.
- **Run it once.** The endpoint reuses the same invoice for about 60 seconds to
  prevent double charges, so a second run in that window gets an invoice that is
  already paid and fails with a payment error. Wait a minute before retrying.
- **Any error:** match it against step 5 and the table below. Do not change the
  limits upward to make the test pass.

If the MCP is installed, `test_l402_payment()` runs the same check from the
wallet side. It takes only `confirmation_nonce`, which you need when the MCP asks
the human for a confirmation code.

### 8. Hand off

Tell the human:

- **What changed:** the package added, the files edited, and the environment
  variable names the code reads (names, not values).
- **The limits in force,** and that the wallet balance is the real ceiling.
- **What the test call proved,** and what it cost.
- **Where to read more:** the package READMEs
  ([Python](https://github.com/refined-element/l402-requests),
  [.NET](https://github.com/refined-element/l402-dotnet),
  [TypeScript](https://github.com/refined-element/l402-ts)) and the docs pages
  [L402-Requests (Python)](https://docs.lightningenable.com/tools/l402-requests),
  [L402-Requests (.NET)](https://docs.lightningenable.com/tools/l402-dotnet), and
  [L402-Requests (TypeScript)](https://docs.lightningenable.com/tools/l402-ts).
- **For the other side:** if they also want to charge for their own API, that is
  the `l402-server-integration` skill.

## What can go wrong

| Symptom | Likely cause | Do this |
|---|---|---|
| `NoWalletError` / `NoWalletException` | No wallet variable is set in the process environment | Have the human set one in the shell or secret store that runs the code, then restart the process. Check names, not values. |
| `UnsupportedWalletError` on every 402 | OpenNode is the detected wallet | Switch to LND, NWC, or Strike and unset `OPENNODE_API_KEY`. |
| Code pays from an unexpected wallet | A higher-priority variable is set, or `~/.lightning-enable/config.json` supplies one | Unset the variables you do not want; check the config file's `wallets.priority`. |
| `BudgetExceededError` | The price is over a limit the human chose | Report the price and the limit. Raise a limit only with the human's yes. |
| `DomainNotAllowedError` | The host is not on the allowlist | Confirm the host with the human before adding it. |
| `PaymentFailedError` with "no preimage returned" | The wallet paid but did not surface the preimage | Do not retry. Report it; the sats may have moved. Use a wallet that returns preimages. |
| NWC payment times out | Relay unreachable, or the wrong encryption scheme | Check the relay; set `NWC_ENCRYPTION` to `nip44_v2` or `nip04`. TypeScript: confirm the peer dependencies are installed. |
| 401 right after a successful payment on a sibling path | A cached credential was presented to a path the server binds separately | Use a fresh client object, or clear the cache, then call again. |
| Second test run fails with a payment error | The test endpoint reuses one invoice for about 60 seconds | Wait a minute and run once more. |
| 402 returned as-is, no payment | The 402 carries no L402 or `Payment` challenge the library recognizes | The server is not speaking L402. Read its docs; do not hand-roll a payment. |

## Safety rules

- **Show the diff and get an explicit yes before any paid call**, including the
  1-sat test.
- **One L402 payment at a time** while you test. Finish one 402, pay, 200 cycle
  before starting another.
- **Never print secrets.** Wallet credentials, API keys, macaroons, and
  preimages stay out of your output, the code, logs, and commits. Report `<set>` or
  `<not set>`.
- **Never raise or disable a budget** without the human asking for it.
- **Never add automatic retries around a paid call.**
- **Run the project's tests** before you report the change as done.

## What this is NOT

- **Not custody.** Lightning Enable does not hold funds; the wallet (or the payment
  provider) facilitates custody and settlement. The libraries never move funds
  anywhere except to the invoice the server presented.
- **Not a Lightning Enable account.** The client libraries work against any L402
  server and need no account or API key.
- **Not the MCP.** For an agent paying interactively with human confirmation codes
  and durable receipts, use the MCP and the `pay-l402-anywhere` skill.
- **Not a way around a budget or an API's terms.**

## Example

> User: "Our Python job calls a weather API that started returning 402 with a
> Lightning invoice. Make it pay, max 50 sats a call."
>
> 1. Ask which wallet and which limits. The human sets `STRIKE_API_KEY` in the job's
>    secret store and approves 50 per call, 2,000 per day, host
>    `api.example-weather.dev` only.
> 2. `pip install l402-requests`; add it to `requirements.txt`.
> 3. Replace the `httpx` call with an `L402Client` built with
>    `BudgetController(max_sats_per_request=50, max_sats_per_day=2000,
>    allowed_domains={"api.example-weather.dev"})`, and catch
>    `BudgetExceededError`, `NoWalletError`, `UnsupportedWalletError`, and
>    `PaymentFailedError` explicitly.
> 4. Confirm `.env` is in `.gitignore`. Report `STRIKE_API_KEY: <set>`.
> 5. Run the test suite; show the diff; get a yes.
> 6. Call `https://api.lightningenable.com/l402/test/ping` with a 10-sat cap: 200,
>    1 sat spent.
> 7. Hand off: "The job pays up to 50 sats a call from Strike, 2,000 a day, to one
>    host. The test call cost 1 sat."
