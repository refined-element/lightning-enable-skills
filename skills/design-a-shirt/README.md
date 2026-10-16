# design-a-shirt

**An agent designs a custom T-shirt from a PNG, pays for it over Lightning, and hands you the approval and the shipping address.**

Give the agent a picture, or ask it to make one with an image model, and say
"put this on a shirt". It checks the artwork against the print specs, uploads
it to a Lightning Enable store, pays the design fee over
[L402](https://github.com/lightninglabs/L402), and shows you a Printful mockup.
You approve the design yourself on the store's page. The agent quotes the shirt
to your state and ZIP, pays after your yes, and gives you a private link where
you enter the address. Printful prints and ships it.

The store is one deployment of Lightning Enable's
[Run your own Lightning store](https://docs.lightningenable.com/products/run-your-own-store)
product, so the same skill works on any store built on it. Lightning Enable
does not hold funds; the payment provider facilitates custody and settlement.

## Why it's interesting

- **Agent-made, person-approved.** The agent handles the files, the payments
  and the quote. The two decisions that matter, approving the design for
  manufacture and the address, stay with you, on pages the agent never fills
  in.
- **No account, no card.** Two Lightning invoices: a small design fee, then the
  shirt. Each is an L402 exchange the store verifies cryptographically.
- **Checked before you pay.** `scripts/check_artwork.py` runs the store's print
  checks locally (size, transparency, DPI, empty margins, contrast with the
  shirt), so a file that would waste the design fee never gets uploaded.
- **Sell it too, where the store allows.** An approved design can be published
  as a listing other people buy, after the store operator reviews it.

## How it works

1. **Specs and artwork.** Read the store's custom catalog, make or check the
   PNG (transparent background, 3,600 x 4,800 px ideal, PNG only).
2. **Upload** (free), then **pay the design fee** (Payment A, 1,000 sats by
   default) with `pay_invoice` and repeat the request with the L402 credential.
3. **Mockup.** Poll the design until Printful's mockup is ready.
4. **You approve** on the store's approval page, from a private link the agent
   gives you. The agent never approves.
5. **Quote** by size, state and ZIP (continental US and DC), then **you say yes**
   to the total in sats.
6. **Pay the shirt** (Payment B). It is above typical auto-approve limits, so
   the MCP asks you for a confirmation code first.
7. **You enter the address** on the private claim page. The agent tracks the
   order to delivery.
8. **Optional:** publish the design as a listing, on a store that has
   publishing on.

## What you need

- [Lightning Enable MCP](https://github.com/refined-element/lightning-enable-mcp)
  2.x with a wallet that returns preimages: NWC (CoinOS, Alby Hub, CLINK), LND,
  or Strike. OpenNode cannot complete an L402 payment.
- A shell with `curl`, and Python 3.10+ (Pillow optional, for the pixel checks).
- Enough sats for the design fee and one shirt (tens of thousands of sats).

## Try it

> "Put this drawing on a black T-shirt, size L. I'm in Philadelphia, 19103."

## Safety

- You approve the design and confirm the rights to the artwork; the agent never
  ticks those boxes, and there is no route that lets it.
- Every amount is shown before it is paid, and the shirt waits for your yes.
  Above the auto-approve threshold the MCP sends a confirmation code to you,
  never to the agent.
- Your name and street address go only into the claim page; the agent asks for
  size, state and ZIP only.
- The design and order tokens, macaroons and preimages stay private. The only
  links that carry a token are the two the agent hands you.
- Lightning payments are final and there are no automatic refunds; technical
  failures are retried free of charge. Exceptions: support@lightningenable.com.

## Where it fits

Buying the store's ready-made merchandise is the plain catalog checkout in the
store's [skills.md](https://store.lightningenable.com/skills.md). Paying any
other L402 endpoint is [`pay-l402-anywhere`](../pay-l402-anywhere/). Setting up
a wallet from nothing is [`agent-wallet-setup`](../agent-wallet-setup/).
