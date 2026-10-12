# shop-l402-store

**Buy a real product from a Lightning Enable Shopify store, paid over Lightning, for yourself or as a gift.**

"Order more of this." "Send my friend a jar of ghee." "Reorder my ghee." The agent
finds the product, opens an [L402](https://github.com/lightninglabs/L402)
checkout, pays the Lightning invoice from your Lightning Enable MCP wallet once
you say yes, and finishes the order. You get a claim link to enter your shipping
address, or, for a gift, the agent ships it to the recipient's address for you.

This skill replaces three earlier skills: `restock-from-photo`, `gift-it`, and
`standing-order`.

## Why it's interesting

- **No account, no card, no checkout page.** An agent completes a real purchase
  with a Lightning payment. You stay in the confirmation loop, not the payment
  plumbing.
- **A photo is optional.** Show the agent the jar or the box and it identifies
  the product. Your words decide whether to buy; the agent never decides on its
  own that you are running low.
- **Gifts are one request.** Name the person and the address, confirm the total,
  and the order ships to them.
- **Lightning Enable does not hold funds.** The sats settle with the store's
  payment provider; the wallet and the payment provider facilitate custody and
  settlement.

## How it works

1. **Identify** the product and the store, from what you say or from a photo.
   Known stores are in [`references/stores.md`](references/stores.md); others
   come from the L402 registry with `discover_api`, or from the store's slug.
2. **Look up** the exact variant and price in the store's live catalog.
3. **Open the checkout** with only the ship-to zip, which sets sales tax. The
   store answers HTTP 402 with a Lightning invoice and the total in dollars and
   sats.
4. **Check the budget** with `get_balance` and `budget`.
5. **Ask you to confirm** the product, the store, the total, and the
   destination.
6. **Pay** with `pay_l402_challenge`, then complete the checkout to get the
   claim link.
7. **Finish shipping:** you enter your own address on the store's claim page, or,
   for a gift, the agent reads the recipient's address back to you and submits
   it.

For a regular reorder, ask again when you run low, or set up a scheduled task in
your own host that runs this skill. The skill keeps no ledger, and every order
still needs your yes.

## What you need

- [Lightning Enable MCP](https://github.com/refined-element/lightning-enable-mcp)
  installed, with a funded wallet that returns Lightning preimages: NWC, LND, or
  Strike. OpenNode cannot complete an L402 purchase.
- Claude Code or Claude Desktop, where a shell and a local MCP are both
  available. The Claude mobile app supports remote MCP connectors only, so this
  skill does not run there. To shop from a phone, see
  [Hermes + NWC](https://docs.lightningenable.com/products/agentic-commerce/hermes-nwc-setup).
- Python 3. The helper script uses the standard library only and holds no
  credentials.
- Your zip code, or the recipient's for a gift. For a gift, also the recipient's
  name and full address.

## Try it

> "Send my mom a jar of Great Ghee. She's at 1 Main St, Orlando FL 32801."

## Safety

- **Confirms before every payment**, with the product, the store, the total in
  dollars and sats, and where it ships.
- **One order at a time**, inside your configured spending limits.
- **Never invents an address.** Before payment it uses only the zip. For a gift
  it reads the full address back to you before submitting it.
- **Never prints the macaroon or the preimage.**
- **Your own address goes on the store's claim page**, which collects it by
  design.

## What it doesn't do

It doesn't buy from stores that have not connected Lightning Enable, pay for API
calls (use [`pay-l402-anywhere`](../pay-l402-anywhere/)), or buy from the
Lightning Enable merchandise store at store.lightningenable.com, which uses a
separate API that the MCP handles with `access_l402_resource`. It doesn't
reorder on its own schedule.
