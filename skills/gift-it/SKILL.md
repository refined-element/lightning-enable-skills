---
name: gift-it
description: >-
  Buy a product as a GIFT and ship it to someone else, paid over Bitcoin
  Lightning via L402. Use when the user wants to send a product to another person
  ("send my friend a jar of ghee", "gift this to my mom", "ship one to this
  address as a present"). Like restock-from-photo, but the destination is the
  recipient's address (not the buyer's), and the order is finalized with that
  address via the claim API. Pairs with restock-from-photo.
---

# Gift it

Send a product to someone else, paid over Lightning. The buyer pays; the gift
ships to the recipient. Same L402 purchase rails as `restock-from-photo`, with
two differences: tax + shipping use the **recipient's** location, and the order
is finalized through the claim API with the recipient's address.

## What you need

- **Lightning Enable MCP** with a funded wallet (`pay_l402_challenge` /
  `pay_invoice`, `get_budget_status`).
- `scripts/le_shopify.py` (Python 3, stdlib only).
- The **recipient's** shipping details (name + address). The buyer provides
  these — they're sending the gift.

## Flow

1. **Identify the product + store** (`references` in `restock-from-photo`, or
   `le_shopify.py catalog <slug>` for the exact `variantId` + price). A photo
   works too — same identification as restock.

2. **Get the recipient's location.** Tax + shipping are destination-based, so
   use the **recipient's** zip: `US-<STATE>-<ZIP>`. You'll need their full
   address for the claim step; collect name + address now or after payment.

3. **Create the checkout (L402 challenge):**
   ```
   python scripts/le_shopify.py checkout <slug> <variantId> <recipientLocation> [qty]
   ```
   HTTP **402 is expected** — note `totalUsd`, `totalSats`, `invoice`,
   `macaroonBase64`.

4. **Budget gate** with `get_budget_status` / `check_wallet_balance`.

5. **Confirm with the buyer — explicitly.** Show: *"Gift **{product}** from
   **{store}** to **{recipient}** in {city, state} — ${totalUsd} (~{totalSats}
   sats). Pay now? (yes/no)"* Proceed only on yes.

6. **Pay** the `invoice` with the MCP wallet → capture the **preimage**.

7. **Get the claim token (L402 retry):**
   ```
   python scripts/le_shopify.py complete <slug> <variantId> <recipientLocation> <macaroonBase64> <preimage> [qty]
   ```
   Returns the **claim token**.

8. **Finalize the gift with the recipient's address** (this is the gift-specific
   step — restock hands the human a link instead):
   ```
   python scripts/le_shopify.py claim <slug> <claimToken> <email> '<shippingAddressJson>'
   ```
   - `email` — who gets the order/shipping confirmation. Ask the buyer whether to
     use their own email or the recipient's.
   - `shippingAddressJson` — the recipient's address, e.g.
     `{"firstName":"Mom","lastName":"Smith","address1":"1 Main St","city":"Orlando","province":"FL","zip":"32801","country":"US"}`

9. **Confirm it's on the way.** Report the order placed and, if the buyer wants,
   draft a short gift note they can send the recipient.

## Safety rules

- **Confirm before paying. Always.** Money moving = explicit buyer yes.
- **Verify the recipient address with the buyer** before submitting the claim —
  a wrong address ships the gift to the wrong place. Read it back to them.
- **Respect the budget** (`get_budget_status`).
- **Recipient location for tax**, not the buyer's — gifts are taxed/shipped to
  the destination.
- If any address field is missing or ambiguous, ask. Don't guess an address.

## Example

> User: "Send my mom a jar of Great Ghee — she's at 1 Main St, Orlando FL 32801."
>
> 1. `catalog greatghee` → variant `49883267432641`, $30.
> 2. recipient location `US-FL-32801`.
> 3. `checkout greatghee 49883267432641 US-FL-32801` → 402, total ~$39, N sats.
> 4. `get_budget_status` → ok.
> 5. Confirm: "Gift Great Ghee to your mom in Orlando — $39 (~N sats)? yes/no" → yes.
> 6. `pay_l402_challenge` → preimage.
> 7. `complete greatghee 49883267432641 US-FL-32801 <macaroon> <preimage>` → claim token.
> 8. `claim greatghee <token> you@email.com '{"firstName":"Mom",...,"zip":"32801","country":"US"}'`.
> 9. "Done — Great Ghee is on its way to your mom. Want a gift note?"
