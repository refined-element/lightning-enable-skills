# l402-client-integration

**Make your own Python, .NET, or TypeScript code pay L402 APIs, with limits you choose.**

Some APIs answer a request with `402 Payment Required` and a Lightning invoice.
That is the [L402](https://github.com/lightninglabs/L402) protocol: pay the
invoice, present the proof, get the response. This skill has your coding
assistant (Claude Code, Cursor, Codex, or similar) wire one of the open-source
L402 client libraries into your codebase so those calls pay and succeed on their
own, inside a budget you set.

| Language | Package | Repository |
|---|---|---|
| Python | [`l402-requests`](https://pypi.org/project/l402-requests/) | [refined-element/l402-requests](https://github.com/refined-element/l402-requests) |
| .NET | [`L402Requests`](https://www.nuget.org/packages/L402Requests) | [refined-element/l402-dotnet](https://github.com/refined-element/l402-dotnet) |
| TypeScript | [`l402-requests`](https://www.npmjs.com/package/l402-requests) | [refined-element/l402-ts](https://github.com/refined-element/l402-ts) |

## What it does

1. Asks you which wallet the code pays from, what the limits are, and which API
   hosts it may pay.
2. Adds the right package and writes the client code, with a per-request, hourly,
   and daily budget and a domain allowlist.
3. Explains which wallet the library will pick (LND, then NWC, then Strike; OpenNode
   cannot pay L402) and how credentials are cached and retried.
4. Adds explicit handling for the library's errors: over budget, no wallet,
   unusable wallet, unreadable invoice, and failed payment.
5. Keeps credentials in environment variables and out of commits.
6. Runs your tests, shows you the diff, and, with your yes, makes one test call
   to a public endpoint that costs about 1 sat.

## What you need

- A Lightning wallet that returns payment preimages: LND, an NWC (Nostr Wallet
  Connect) wallet such as CoinOS, CLINK, or Alby Hub, or Strike. OpenNode does
  not return preimages and cannot pay L402.
- Its credential set as an environment variable where your code runs. You set it
  yourself; the assistant never needs to see it.
- No Lightning Enable account. The libraries work against any L402 server. The
  Lightning Enable MCP is optional.

## Try it

> "My Python service gets a 402 with a Lightning invoice from a paid API. Add L402
> support, cap it at 50 sats a call and 2,000 a day, and only for that host."

## Safety

- Nothing is paid until you have seen the diff and said yes.
- Budgets are on by default and the assistant does not raise or disable them
  without your say-so. The budget lives in memory, so the wallet balance is the
  real ceiling: fund the wallet with no more than the code may spend.
- No automatic retries around paid calls. A failed payment can still have moved
  sats, so it goes to a human.
- Secrets stay secret: wallet credentials, API keys, macaroons, and preimages are
  never printed, logged, or committed. Status is reported as `<set>` or
  `<not set>`.
- Lightning Enable does not hold funds; the wallet (or the payment provider)
  facilitates custody and settlement.

## Related skills

- [`pay-l402-anywhere`](../pay-l402-anywhere/) when an agent should pay
  interactively through the MCP instead of your code paying on its own.
- [`l402-server-integration`](../l402-server-integration/) to charge for your
  own API.
