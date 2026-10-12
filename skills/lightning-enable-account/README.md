# lightning-enable-account

**Check your Lightning Enable plan and paid-through date, renew in sats with a human yes, and understand what a lapse does.**

Agentic Commerce is payable two ways: by card through the dashboard checkout, or
in sats over [L402](https://github.com/lightninglabs/L402) from a Lightning
wallet. Both buy the same plan. This skill handles the sats side from the
agent: it reads where the account stands, tells you in plain words, and, when
you say yes, pays the next period from the agent's own wallet. No card, no
checkout page.

## What it does

1. **Reads the account.** `l402_producer` with `action="status"` for the plan
   and subscription status, plus the renewal quote
   (`GET /api/merchant/subscription/renew`) for the paid-through date, the
   price, and whether a sats renewal is open. The quote has no side effects and
   still answers after the account lapses.
2. **Explains it.** Which plan you are on, how it is paid, the date it is paid
   through, the days left, and, if a sats renewal is closed, why (an active card
   subscription, the Business plan, the 365-day prepay cap).
3. **Renews, with your yes.** It shows the quoted sats and the paid-through date
   the payment produces, checks the wallet and the budget, waits for your yes,
   then calls `renew_lightning_enable_subscription` capped at the quoted price.
4. **Verifies.** It reads the credit back from the subscription endpoint and
   the wallet's durable receipt log.
5. **Reads a lapse.** An API call that returns `403` with
   `action_required: "renew_subscription"` and a `renew.endpoint` means the
   sats period ended. The skill tells that apart from a card problem or a
   disabled account.

The server sets the price. The skill never quotes one from memory; see
[lightningenable.com](https://www.lightningenable.com) for plans.

## What you need

- [Lightning Enable MCP](https://github.com/refined-element/lightning-enable-mcp)
  **2.1.0 or later** (the version that adds the renewal tool).
- Your merchant API key, in `LIGHTNING_ENABLE_API_KEY` or in
  `~/.lightning-enable/config.json`. The environment variable wins when both
  are set. Restart the MCP after a key is written.
- To renew: a funded wallet that returns Lightning preimages, such as a Nostr
  Wallet Connect (NWC) wallet (CoinOS, Alby Hub, CLINK), an LND node, or Strike.
  OpenNode and Primal cannot pay an L402 challenge.
- Optional: a shell for the two read-only `curl` calls. Without one, the
  dashboard's Settings page shows the same plan, paid-through date, and renewal
  price.

## Try it

> "What plan is my Lightning Enable account on, and when does it run out? If
> it's close, renew it in sats."

## Who can renew in sats

The Free Producer Sandbox, a Fast Lane trial (the paid period starts when the
trial ends, so you lose no trial days), a sats-paid account whether it is still
running or has lapsed, and an account whose card subscription is canceled. A
card subscription in any other state has to be canceled in the dashboard first,
so the card is never charged alongside the sats. The Business plan is arranged
through support@lightningenable.com.

## What happens if you do not renew

Nothing charges you automatically. When the paid-through date passes, API calls
answer `403` with the renew endpoint. Within a day the account moves to the Free
Producer Sandbox: your key keeps working within the free limits, the account
stays active, and you can pay again at any time.

## Safety

- An explicit human yes before every payment, with the quoted sats stated.
- The cap (`max_sats`) is set to the quoted price. Above the operator's
  auto-approve threshold the MCP sends a confirmation code to the human, never
  to the agent.
- One payment at a time, and never a second call to "check": every call to the
  renewal tool pays a fresh invoice.
- If a payment leaves the wallet but the renewal does not complete, the agent
  stops and gives you the payment hash for support@lightningenable.com instead
  of paying again.
- Secrets stay secret: the API key, NWC connection strings, macaroons, and
  preimages are never printed. The agent reports `<set>` or `<not set>`.

Where the sats go: the payment settles with the payment provider of the
Lightning Enable account that receives renewals. Lightning Enable does not hold
funds; the payment provider facilitates custody and settlement.

## What it does not do

It does not create an account (use [`producer-setup`](../producer-setup/)),
change card billing (use the [dashboard](https://api.lightningenable.com/dashboard)
or support@lightningenable.com), sell anything (use
[`create-l402-proxy`](../create-l402-proxy/) or [`sell-this`](../sell-this/)),
or pay someone else's endpoint (use [`pay-l402-anywhere`](../pay-l402-anywhere/)).

More detail: [Renew in sats](https://docs.lightningenable.com/getting-started/activate-with-lightning#renew-in-sats).
