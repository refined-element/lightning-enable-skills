---
name: restock-from-photo
description: >-
  When the user shares a PHOTO of a physical product they own (e.g. a jar of
  ghee, a box of electrolyte sticks) AND indicates they are low or out ("I'm
  out", "running low", "need more", "reorder this", "order another"), identify
  the product, confirm with the user, and reorder it over Bitcoin Lightning via
  the L402 protocol using the Lightning Enable MCP wallet. Use this whenever a
  product photo is paired with a restock intent. Do NOT use it for general
  product questions, price checks, or when no restock is requested.
---

# Restock from photo

Turn "here's a photo of my almost-empty thing + I'm out" into a real Lightning
purchase — identify the product, confirm, pay per-call over L402, hand back a
claim link. This is a showcase of agentic commerce: an AI completing a real
economic transaction, account-lessly, with a human only in the *confirmation*
loop, not the payment plumbing.

## What you need

- The **Lightning Enable MCP** connected with a funded Lightning wallet
  (provides `pay_l402_challenge` / `pay_invoice`, `check_wallet_balance`,
  `get_budget_status`). Open source: <https://github.com/refined-element/lightning-enable-mcp>
- A shell to run `scripts/le_shopify.py` (Python 3, stdlib only — no installs).
- The buyer's **zip code** (for sales-tax calculation). That's the only address
  detail needed before payment — full shipping is collected on the claim page
  afterward.

> Runtime note: this skill targets **Claude Code / Desktop**, where a shell and
> the local MCP are both available. It does not yet run on the Claude mobile
> app, because mobile only supports *remote* MCP connectors and cannot run
> scripts. See `docs/mobile-readiness.md` for the path to a phone-native version.

## The flow

Follow these steps in order. **Never skip the confirmation step — this spends
real money.**

1. **Identify the product** from the photo. Read the label/brand. Match it to a
   known store using `references/stores.md`. If you cannot confidently identify
   it or it isn't a known store, say so and stop — do not guess and buy.

2. **Treat "running low" as a request, not a verified fact.** You generally
   *cannot* reliably tell from a photo how much product remains (opaque jars,
   sealed boxes). The user's words are the trigger; the photo only tells you
   *which* product. Don't claim you can see it's empty.

3. **Look up the exact item:**
   ```
   python scripts/le_shopify.py catalog <slug>
   ```
   Pick the `variantId` and `priceUsd` of the product the user is reordering.
   For multi-product stores, match carefully to the photographed item.

4. **Get the buyer's zip** if you don't already have it. Build the location
   string `US-<STATE>-<ZIP>` (e.g. `US-FL-34787`). Only the zip is needed now.

5. **Create the checkout (L402 challenge):**
   ```
   python scripts/le_shopify.py checkout <slug> <variantId> <buyerLocation> [qty]
   ```
   HTTP **402 is the expected, healthy response** — it returns `totalUsd`,
   `totalSats`, `invoice` (BOLT11), and `macaroonBase64`. Note the totals.

6. **Budget gate.** Call the MCP `get_budget_status` (and/or
   `check_wallet_balance`). If the purchase would exceed the configured budget
   or the wallet can't cover it, stop and tell the user — do not pay.

7. **Confirm the purchase — explicitly, every time.** Show the user:
   *"Reorder **{product}** from **{store}** — ${totalUsd} (~{totalSats} sats),
   shipping to your {zip}. Pay now? (yes/no)"*
   Proceed only on a clear yes.

8. **Pay** the BOLT11 `invoice` with the MCP wallet
   (`pay_l402_challenge` or `pay_invoice`). Capture the **preimage**.

9. **Complete the order (L402 retry):**
   ```
   python scripts/le_shopify.py complete <slug> <variantId> <buyerLocation> <macaroonBase64> <preimage> [qty]
   ```
   This returns the **claim token + claim-page URL**.

10. **Hand off shipping to the human.** Give the user the claim-page URL and tell
    them to enter their shipping address there to finalize delivery. Do **not**
    ask for or submit a full street address yourself — that's collected on the
    merchant's claim page by design.

## Safety rules (non-negotiable)

- **Confirm before paying. Always.** Money moving = explicit human yes.
- **Never auto-decide the user is "low"** and buy unprompted. The restock intent
  must come from the user.
- **Respect the budget.** Honor `get_budget_status`; never pay past it.
- **One item at a time** unless the user clearly asks for more; cap quantity
  sensibly and re-confirm if >1.
- **No invented addresses.** Pre-payment you only ever use the zip (for tax).
- If anything is ambiguous (which product, which variant, the zip), **ask** —
  don't assume.

## Example

> User: *[photo of a Great Ghee jar]* "I'm almost out of this"
>
> 1. Identify → "Grass-Fed A2/A2 Ghee" → store `greatghee`.
> 2. `catalog greatghee` → variant `49883267432641`, $30.
> 3. Ask zip → `US-FL-34787`.
> 4. `checkout greatghee 49883267432641 US-FL-34787` → 402, total $39 (~incl.
>    shipping+tax), N sats, invoice, macaroon.
> 5. `get_budget_status` → ok.
> 6. Confirm: "Reorder Great Ghee for $39 (~N sats)? yes/no" → **yes**.
> 7. `pay_l402_challenge` → preimage.
> 8. `complete greatghee 49883267432641 US-FL-34787 <macaroon> <preimage>` →
>    claim URL.
> 9. "Paid! Finish shipping here: <claim URL>."
