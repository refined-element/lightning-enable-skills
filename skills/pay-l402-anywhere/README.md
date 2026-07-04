# pay-l402-anywhere

**Give an agent a bounded Lightning wallet and it can pay for anything on the web that speaks L402 — no account, no card, a human yes in the loop.**

This is the consumer wedge for agent commerce. Most "agent pays for things" demos
have a deployment problem: the agent needs a wallet *and* a host before it can pay
for anything. Pair a small [Nostr Wallet Connect](https://nwc.dev) wallet with the
[Lightning Enable MCP](https://github.com/refined-element/lightning-enable-mcp)
and that problem disappears — the agent can pay [L402](https://github.com/lightninglabs/L402)
challenges anywhere, from a wallet it can't overspend.

## Why it's interesting

- **Pay the open web per-request.** Any URL that returns `402 Payment Required`
  with a Lightning invoice becomes payable — API calls, premium data, content —
  for a few sats, account-lessly.
- **The wallet is the leash.** Fund a dedicated wallet with only what the agent
  may spend. A 5,000-sat wallet can't spend 50,000, no matter what a prompt says —
  the strongest guardrail is the balance itself, with the MCP's budget caps and a
  human confirmation gate on top.
- **Runs on your phone.** With [Hermes](https://hermes-agent.nousresearch.com) as
  the host, the same setup reaches you over Telegram, Signal, WhatsApp, and other
  chat platforms — no hosted MCP to build or trust.

## How it works

1. **Check the leash** — `get_budget_status` + `check_wallet_balance` before the
   first payment; state the ceiling to the user.
2. **Find it (optional)** — `discover_api` searches the L402 registry and shows
   what you can afford.
3. **Pay it** — `access_l402_resource(url=…)` does the whole 402 → pay → retry →
   200 dance through your NWC wallet.
4. **Confirm over-threshold spends** — the MCP prints a code to its console for
   the human; the agent asks for it, then re-calls with the confirmation nonce.
5. **Report** — sats spent and what it bought.

## Requirements

- [Lightning Enable MCP](https://github.com/refined-element/lightning-enable-mcp)
  with a **preimage-returning** wallet: NWC (CoinOS, Alby Hub, CLINK), LND, or
  Strike. OpenNode can't do L402 (no preimage).
- A recommended host: **Hermes** (mobile), Claude Code / Desktop, or Cursor.

## Setup

Full beginner setup — Hermes + a CoinOS NWC wallet + the config file, end to end —
is at **[Run L402 anywhere: Hermes + NWC](https://docs.lightningenable.com/products/l402-microtransactions/hermes-nwc-setup)**.

## Safety

- Confirms before every over-threshold payment; never self-approves.
- Budget-aware on every call — most-restrictive limit wins.
- One L402 payment at a time (each 402 mints a fresh invoice + macaroon).
- Never echoes the NWC string, preimages, or macaroons.

Pairs naturally with [`l402-meter`](../l402-meter/) for a visible running spend total.
