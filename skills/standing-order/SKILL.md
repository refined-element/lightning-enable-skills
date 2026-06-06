---
name: standing-order
description: >-
  Set up and run recurring restock orders paid over Lightning — remember what to
  reorder and how often, surface which items are due, and reorder them on
  confirmation each cycle (no card on file, Lightning per cycle). Use when the
  user wants a repeating purchase ("reorder my ghee every month", "set up a
  standing order", "what restocks are due", "subscribe me to this but on
  Lightning"). Pairs with restock-from-photo.
---

# Standing order

Recurring commerce, the Lightning way: **no stored card, no server-side
auto-charge** — the skill remembers what you reorder and how often, tells you
what's **due**, and reorders each item over L402 **with your confirmation every
cycle**. The human-yes-per-cycle isn't a limitation; it's the feature (you're
never silently charged, and there's no card on file to leak).

## What you need

- **Lightning Enable MCP** with a funded wallet (`pay_l402_challenge` /
  `pay_invoice`, `get_budget_status`).
- `scripts/standing_orders.py` (the recurring ledger) and `scripts/le_shopify.py`
  (the same store helper used by `restock-from-photo`). Python 3, stdlib only.

## Setting up a standing order

1. Identify the product + store (use `le_shopify.py catalog <slug>` to get the
   exact `variantId` and price; see `restock-from-photo` for photo-based ID).
2. Agree the cadence (e.g. every 30 days) and the buyer location (`US-FL-34787`).
3. Record it:
   ```
   python scripts/standing_orders.py add <slug> <variantId> <cadenceDays> <buyerLocation> "<label>"
   ```

## Running due orders

This skill does NOT run on a timer by itself. It runs when **you** check in
("any restocks due?"), or when wired to a scheduler you control (e.g. a
scheduled Claude task). When invoked:

1. **List what's due:**
   ```
   python scripts/standing_orders.py due
   ```
   Returns the orders whose cadence has elapsed (or never ordered).

2. **For each due item, run the normal restock purchase** (same flow as
   `restock-from-photo`), one at a time:
   - `le_shopify.py checkout <slug> <variantId> <buyerLocation>` → 402 + invoice
     + totals.
   - `get_budget_status` → ensure headroom.
   - **Confirm with the user** — show product + price (sats) and ask yes/no.
     *Every cycle. Always.*
   - On yes: pay the invoice with the MCP wallet → preimage.
   - `le_shopify.py complete <slug> <variantId> <buyerLocation> <macaroon> <preimage>`
     → claim URL.
   - Give the user the claim URL to finish shipping.

3. **Mark it ordered** so the cadence resets:
   ```
   python scripts/standing_orders.py mark-ordered <id>
   ```

## Managing standing orders

- `standing_orders.py list` — all orders + which are due.
- `standing_orders.py remove <id>` — cancel one.

## Safety rules

- **Confirm every cycle before paying.** A standing order is a *reminder to
  offer*, never a license to auto-charge.
- **Respect the budget** (`get_budget_status`) on every purchase.
- Only `mark-ordered` after a payment actually succeeds — never pre-emptively.
- One item at a time; re-confirm quantity if more than one.

## Example

> User: "Reorder my Great Ghee every month."
> → `standing_orders.py add greatghee 49883267432641 30 US-FL-34787 "Great Ghee"`
>
> 4 weeks later — User: "Anything due?"
> → `standing_orders.py due` → Great Ghee is due → checkout → confirm "$39, ~N
> sats? yes" → pay → claim URL → `mark-ordered 1`.
