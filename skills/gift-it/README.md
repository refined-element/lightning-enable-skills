# gift-it

**Send someone a product as a gift, paid over Bitcoin Lightning.**

"Send my mom a jar of ghee." The buyer pays over Lightning via L402; the gift
ships to the recipient. Same purchase rails as
[`restock-from-photo`](../restock-from-photo/) — but the destination is the
*recipient's* address, and the order is finalized for them automatically.

## Why it's interesting

- **Pay for someone else, account-lessly.** No gift cards, no recipient account,
  no checkout page — the buyer pays a Lightning invoice and the gift ships.
- **The agent handles the address.** Unlike a self-restock (where you finish your
  own shipping on a claim page), a gift is shipped *to someone else*, so the
  agent collects the recipient's address and finalizes the order through the
  claim API — the buyer doesn't fill a web form.
- **Naturally shareable.** Gifting is inherently social — a fun, real demo of
  agentic commerce that other people see.

## How it works

1. Identify the product + store (photo or catalog lookup).
2. Use the **recipient's** zip for tax/shipping (gifts are destination-based).
3. Create the L402 checkout → pay the invoice from the MCP wallet → get the
   claim token.
4. **Confirm the price and recipient with the buyer**, then submit the
   recipient's address via the claim API to finalize the order.

## Requirements

- [Lightning Enable MCP](https://github.com/refined-element/lightning-enable-mcp)
  with a funded wallet.
- Python 3 (stdlib only). Self-contained.
- The recipient's name + shipping address (the buyer provides these).

## Safety

- **Confirms before paying** — explicit buyer yes, every time.
- **Reads the recipient address back** before submitting — a wrong address ships
  the gift to the wrong place.
- Budget-aware; never guesses a missing address field.

## Example

> "Send my mom a jar of Great Ghee — 1 Main St, Orlando FL 32801."

→ checks out to `US-FL-32801` → "Gift Great Ghee to your mom — $39 (~N sats)?
yes" → pays over Lightning → finalizes with her address → "On its way! Want a
gift note?"
