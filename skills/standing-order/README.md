# standing-order

**Recurring restock over Lightning — no card on file, no silent charges, a human yes every cycle.**

A subscription you actually control. The skill remembers what you reorder and how
often, tells you what's **due**, and reorders each item over L402 — but it
**confirms with you every cycle** and pays per cycle over Lightning. There's no
stored card and no server-side auto-charge.

## Why it's interesting

- **Recurring commerce without the usual baggage.** No card on file to leak, no
  surprise renewal charge, no "we'll bill you unless you cancel." Each cycle the
  agent *offers*; you say yes; it pays over Lightning.
- **The human-in-the-loop is the point.** You're never charged without confirming
  — which is exactly what people wish subscriptions did.
- **Builds on `restock-from-photo`.** Same store helper, same purchase flow —
  this just adds the "remember and remind" layer.

## How it works

1. **Set it up:** record a product + store + cadence + your zip
   (`standing_orders.py add ...`).
2. **Check what's due** whenever you ask, or via a scheduler you control
   (`standing_orders.py due`).
3. **Reorder due items** through the normal restock flow — checkout → **confirm
   the price** → pay from the MCP wallet → get a claim link to finish shipping.
4. **Mark it ordered** so the cadence resets (only after payment succeeds).

There is no built-in timer; nothing happens until you (or a scheduler you set up)
ask "anything due?" — by design.

## Requirements

- [Lightning Enable MCP](https://github.com/refined-element/lightning-enable-mcp)
  with a funded wallet.
- Python 3 (stdlib only). Self-contained — bundles its own copy of the store
  helper.

## Safety

- **Confirms before every payment.** A standing order is a reminder to *offer*,
  never permission to auto-charge.
- Budget-aware on every purchase.
- Only records a cycle as fulfilled after a real successful payment.

## Example

> "Reorder my Great Ghee every month." → recorded.
>
> A month later: "Anything due?" → Great Ghee is due → "$39 (~N sats), ship to
> your zip? yes" → paid → claim link → cadence resets.
