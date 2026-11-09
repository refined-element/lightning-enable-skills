# sell-with-lightning-address

**Give Lightning Enable a URL and a Lightning Address. Get back a URL that charges.**

This skill has your agent turn an API you already run into a paid
[L402](https://github.com/lightninglabs/L402) endpoint in one conversation.
Your agent reads the price, asks you once, pays one Lightning invoice from its
own wallet, and hands you a proxy URL. Every call to that URL answers HTTP 402
Payment Required until the caller pays, and every payment goes to your Lightning
Address.

There's no account to create first, no dashboard, and no wallet key to hand
over. Lightning Enable does not hold funds; your wallet provider facilitates
custody and settlement.

## What you need

- [Lightning Enable MCP](https://github.com/refined-element/lightning-enable-mcp)
  with a funded spending wallet that returns preimages (NWC, LND, or Strike).
  An MCP with `l402_producer` `sell_url` does the whole claim in one call; on an
  older MCP the skill falls back to `scripts/claim.sh`, which needs a shell with
  `curl`.
- An API on a public `https` hostname.
- A Lightning Address (`name@domain`) from a wallet provider that supports them.
- Optionally, a recovery email or Nostr public key. Without one, the API key is
  the only credential for the account.

## Try it

> "Charge for my API at https://api.example-weather.dev and pay me at
> alice@example-wallet.com."

## What it does

1. Reads the claim quote: the price, the trial it buys, the renewal, and the
   terms version. Nothing is quoted from memory.
2. Asks you once for anything missing and for a yes.
3. Calls `l402_producer(action="sell_url", ...)`, which sends the claim, pays
   the 402 from the agent's wallet within its ceiling, and sends the same claim
   again with the payment token.
4. Stores the new API key in a local file (mode 600) and tells you which one.
   If a retry makes the server issue a fresh key, the agent replaces the old
   one, which stops working.
5. Gives you the proxy URL and the manifest URL, and offers one self-test
   purchase.

A refusal before payment costs nothing. After payment, the agent resends the
same claim with the same token until it goes through, and never pays twice.

## Not this skill

- Receive with Strike, OpenNode, or an NWC wallet:
  [`producer-setup`](../producer-setup/) or
  [`create-l402-proxy`](../create-l402-proxy/).
- Charge for one file or answer: [`sell-this`](../sell-this/).

Public listing requires ownership verification. The endpoint works by direct
URL meanwhile; to list it, verify ownership with
[`verify-producer`](../verify-producer/).
