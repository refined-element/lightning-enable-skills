---
name: shop-l402-store
description: >-
  Buy a physical product from a Lightning Enable Shopify store and pay for it
  over Bitcoin Lightning with the L402 protocol, for the user or as a gift to
  someone else. Use when the user asks to buy, reorder, or send a product from
  a store that sells over L402 ("order more of this" with or without a photo,
  "buy the chocolate electrolytes from drinksote", "send my friend a jar of
  ghee", "reorder my ghee"). The flow reads the catalog, opens an L402
  checkout, pays it from the Lightning Enable MCP wallet after an explicit yes,
  and hands back a claim link or finalizes a gift with the recipient's address.
  Do NOT use to pay for an API call or any other L402 resource (use
  pay-l402-anywhere), for the Lightning Enable merchandise store at
  store.lightningenable.com (a separate API the MCP handles with
  access_l402_resource), for a store that is not a Lightning Enable Shopify
  store, or for price checks and product questions with no request to buy.
---

# Shop an L402 store

Buy a real, shipped product from a Lightning Enable Shopify store: find the item,
open an L402 checkout, pay the Lightning invoice from the MCP wallet, and finish
the order. The buyer can ship it to themselves or send it to someone else as a
gift. The human decides what to buy and says yes to the total; the agent does the
payment plumbing.

The sats settle with the store's payment provider. **Lightning Enable does not
hold funds; the wallet and the payment provider facilitate custody and
settlement.** Lightning Enable mints the challenge, verifies the payment proof,
and creates the Shopify order.

## What you need

- **[Lightning Enable MCP](https://github.com/refined-element/lightning-enable-mcp)**
  installed and running, with a funded wallet that returns Lightning
  **preimages**: NWC, LND, or Strike. OpenNode does not return preimages and
  cannot complete an L402 purchase.
- Tools this skill uses (all in the default `standard` profile):
  - `get_balance`: the real funds in the wallet.
  - `budget`: `action="status"` reads the spending limits.
  - `pay_l402_challenge`: pays the checkout's invoice and returns the preimage.
  - `pay_invoice`: the fallback when only the BOLT11 invoice is at hand.
  - `discover_api`: searches the L402 registry for stores missing from
    `references/stores.md`.
- A shell with Python 3 to run `scripts/le_shopify.py`. It uses the standard
  library only and holds no credentials; the store endpoints are public.
- The **ship-to zip code**. Before payment that is the only address detail the
  flow uses, for sales tax. For a gift it is the recipient's zip.

Argument names below are the Python server's `snake_case`. The .NET server takes
the same arguments in `camelCase`: `max_sats` becomes `maxSats`,
`confirmation_nonce` becomes `confirmationNonce`. Response fields differ where
this skill says so.

This skill needs a shell and a local MCP, so it runs in Claude Code and Claude
Desktop. It does not run on the Claude mobile app, which supports remote MCP
connectors only and cannot run scripts. To reach the agent from a phone, run it
on a host with a shell and a chat gateway instead: see
[Hermes + NWC](https://docs.lightningenable.com/products/agentic-commerce/hermes-nwc-setup).

## Flow

Follow the steps in order. **Never skip the confirmation in step 6: this spends
real money.**

### 1. Identify the product and the store

The request comes from the human's words: "order more of this", "buy X from
drinksote", "send my friend a jar of ghee". A photo, when there is one, tells you
**which** product. It is not evidence that anything is running out. You cannot
reliably see how much is left in an opaque jar or a sealed box, so never claim
that you can, and never start a purchase because a photo looks empty.

Match the product to a store in `references/stores.md`. When it is not there:

- Search the registry: `discover_api(query="<product or store name>")`. A
  Lightning Enable Shopify store appears as `<slug> (Shopify)`, and its manifest
  URL path reads `/l402/proxy/shopify-<slug>/`.
- Or ask the human for the store's slug.

If you cannot identify the product with confidence, or the store is not a
Lightning Enable Shopify store, say so and stop. Do not guess and buy.

For the Lightning Enable merchandise store at store.lightningenable.com, stop
here: it is a different API, and the MCP buys from it with
`access_l402_resource`.

### 2. Look up the exact item

```
python scripts/le_shopify.py catalog <slug>
```

- **Success (`status: 200`):** pick the product and variant the human asked for.
  Keep its `variantId` and `priceUsd`. Skip a variant with `available: false` and
  tell the human it is out of stock.
- **`status: 404`:** wrong slug, or the store is inactive. Stop and say so.

On a store with many products, match the exact flavor, size, or count. When two
variants are close, ask.

### 3. Get the ship-to location

Build `US-<STATE>-<ZIP>`, for example `US-FL-34787`. It goes in the
`X-Buyer-Location` header and drives destination-based sales tax.

- **For yourself:** the buyer's own zip.
- **For a gift:** the recipient's zip. Tax and shipping follow the destination.

Collect nothing else yet. The stores in `references/stores.md` ship within the US
only; the catalog's `shipping.domesticOnly` says so.

### 4. Open the checkout (the L402 challenge)

```
python scripts/le_shopify.py checkout <slug> <variantId> <location> [quantity]
```

- **`status: 402` is the healthy answer.** Capture `totalUsd`, `totalSats`,
  `invoice` (the BOLT11 invoice), `macaroonBase64`, and `orderId`. The total
  includes shipping and tax. There is no claim token yet; it arrives only after
  payment.
- **`status: 400`:** a bad variant, an out-of-stock item, a quantity over 10, or
  a malformed location. The body says which. Fix it and try again.
- **`status: 503`:** the bitcoin price feed or the tax calculation failed, so no
  invoice was issued. Retry once after a short wait.

Default quantity is 1. Buy more than one only when the human asks, and
re-confirm the count.

### 5. Budget gate

```
get_balance()
budget(action="status")
```

If the wallet cannot cover `totalSats`, or the per-payment or per-session limit
is below it, stop and tell the human. Do not pay. The agent can only tighten the
limits, never raise them; the human raises them in
`~/.lightning-enable/config.json`.

### 6. Confirm, explicitly, every time

Show the human the product, the store, the total in dollars and sats, and where
it ships:

> Buy **{product}** from **{store}** for ${totalUsd} (about {totalSats} sats),
> shipping to {zip, or the recipient's city and state}. Pay it? (yes/no)

Proceed only on a clear yes.

### 7. Pay the invoice

```
pay_l402_challenge(invoice="<invoice>", macaroon="<macaroonBase64>",
                   max_sats=<totalSats>)
```

Always pass `max_sats`. Its default is 1,000 sats, far below most orders, so a
call without it refuses the payment.

- **Success:** capture the preimage, and never print it. The Python server
  returns it as `preimage`. The .NET server returns `l402Token`, which is
  `<macaroon>:<preimage>`; the preimage is the part after the last colon. In
  both, `usage.headerValue` reads `L402 <macaroon>:<preimage>`.
- **`requiresConfirmation: true`:** the payment is over the auto-approve
  threshold. The MCP prints a confirmation code to its **console**, where the
  human can read it and you cannot. Ask the human for the code, then repeat the
  same call with `confirmation_nonce="<code>"`. The code is bound to that amount
  and that tool. Never guess a code. If the result says no confirmation channel
  is available, stop and tell the human.
- **Budget denial, or the amount is over `max_sats`:** stop. Do not retry with a
  higher cap without a fresh yes.
- **Money may have moved without a preimage:** the Python server reports
  `status: "paid_no_preimage"` or `"pending"`; the .NET server reports
  `success: false` with `receipt_written` set to `true` or `false` (`null` means
  nothing was paid). Do not pay again. Tell the human, give them the `orderId`,
  and point them at the store and at support@lightningenable.com.

If the human holds only the BOLT11 invoice (no macaroon), use
`pay_invoice(invoice="<invoice>", max_sats=<totalSats>)`. It returns `preimage`
in both servers. The .NET `pay_invoice` takes no `max_sats`; its budget limits
alone cap the payment.

One payment at a time. Each checkout mints a fresh invoice and macaroon; a second
checkout in parallel crosses them.

### 8. Complete the checkout (the L402 retry)

```
python scripts/le_shopify.py complete <slug> <variantId> <location> <macaroonBase64> <preimage> [quantity]
```

Send the same variant, location, and quantity as step 4.

- **Success (`status: 200`):** the order is paid and awaiting shipping details.
  Capture `claimPageUrl`. The claim token is its `token` query parameter, a value
  that starts with `SC-`.
- **`status: 401`, `402`, or `404`:** the payment proof was rejected or matched
  no order, and money may be gone with no order to show for it. Do not pay again. Give the human the
  `orderId` and point them at the store and at support@lightningenable.com.
- **`claimPageUrl` is null:** the store has no claim page configured, so the flow
  cannot hand you the claim token. Tell the human the order is paid, give them the
  `orderId`, and point them at the store to finish shipping.

### 9. Hand off shipping

**For yourself:** give the human the `claimPageUrl` and tell them to enter their
shipping address there. Do not ask for, or submit, a full street address
yourself. The store's own claim page collects it by design.

**For a gift:**

1. Collect the recipient's first and last name, street address, city, state,
   zip, and country from the buyer. Ask for anything missing. Never invent a
   field.
2. Ask the buyer which email gets the order and shipping confirmations: theirs or
   the recipient's.
3. **Read the full address back to the buyer** and get a yes. A wrong address
   ships the gift to the wrong place.
4. Finalize the order:

   ```
   python scripts/le_shopify.py claim <slug> <claimToken> <email> '<shippingAddressJson>'
   ```

   `shippingAddressJson` carries `firstName`, `lastName`, `address1`, `city`,
   `province`, `zip`, and `country`, plus optional `address2` and `phone`:
   `{"firstName":"Ana","lastName":"Diaz","address1":"1 Main St","city":"Orlando","province":"FL","zip":"32801","country":"US"}`

   - **Success (`status: 200`):** the response carries `shopifyOrderNumber` and
     the status `PaidWithDetails`. Report the order as placed.
   - **`status: 400`:** an expired claim window, an order already claimed, or an
     address outside the store's shipping area. The body says which. Report it.
     A failed claim is not a placed order.
   - **`status: 404`:** the token does not match this store. Check the slug and
     the token.
5. Offer to draft a short gift note the buyer can send the recipient.

### 10. Repeat orders

This skill keeps no ledger and runs no timer. To reorder, the human asks again
when they run low. A human who wants a regular reminder can wire a scheduled task
in their own host that invokes this skill. Every cycle still needs the human's
explicit yes in step 6: a schedule is a reminder to offer, never permission to
pay.

## What can go wrong

| Symptom | Likely cause | Do this |
|---|---|---|
| `catalog` returns 404 | Wrong slug, or the store is inactive | Check the slug in `references/stores.md` or the registry. Do not guess another one. |
| `checkout` returns 400 | Bad variant, out of stock, quantity over 10, or a malformed location | Read the body, fix the named field, and try again. |
| `checkout` returns 503 | The price feed or the tax calculation failed; no invoice exists | Retry once after a short wait. |
| `pay_l402_challenge` refuses the amount | `max_sats` left at its 1,000-sat default, or set below `totalSats` | Pass `max_sats=<totalSats>`. |
| Budget denial | The configured per-payment or per-session limit is below the order | Stop. The human raises the limit in `~/.lightning-enable/config.json`. |
| A confirmation code is required | The order is over the auto-approve threshold | Ask the human to read the code from the MCP console, then repeat the call with `confirmation_nonce`. |
| Paid, but no preimage | The wallet does not return preimages (OpenNode, some Strike-to-Strike payments) | Do not pay again. Give the human the `orderId` and point them at the store and support. |
| `complete` returns 401, 402, or 404 | The payment proof was rejected or matched no order | Do not pay again. Give the human the `orderId` and point them at support. |
| `claimPageUrl` is null | The store has no claim page configured | Tell the human the order is paid and point them at the store. |
| `claim` returns 400 | Claim window expired, already claimed, or an address outside the shipping area | Report the reason from the body. Never report the order as placed. |

## Safety rules

- **Confirm before paying. Always.** Moving money needs an explicit human yes,
  with the product, the store, the total in dollars and sats, and the
  destination.
- **The intent to buy comes from the human.** Never decide on your own that
  something is running low, and never buy unprompted.
- **One order at a time.** Finish checkout, payment, and completion before
  starting another.
- **Respect the budget.** Honor `budget(action="status")` and pass `max_sats`.
  Never pay past a limit.
- **Never invent an address.** Before payment, use only the ship-to zip. For a
  gift, read the full address back before submitting it.
- **Keep secrets out of your output.** Never print the macaroon or the preimage;
  pass them to `complete` and report "paid". Report `<set>` or `<not set>` for
  any wallet credential.
- **For your own order, the store's claim page collects the full address.** Do
  not collect it yourself.

## What this is NOT

- **Not a subscription.** Nothing recurs on its own; every order is a fresh yes.
- **Not custody.** Lightning Enable does not hold funds; the wallet and the
  store's payment provider facilitate custody and settlement.
- **Not a general web shopper.** It buys only from Lightning Enable Shopify
  stores.

## Examples

> User: *[photo of a Great Ghee jar]* "I'm almost out of this. Order another."
>
> 1. Identify: a jar of Great Ghee, store `greatghee`.
> 2. `catalog greatghee`: one variant; keep its `variantId` and `priceUsd`.
> 3. Ask for the zip: `US-FL-34787`.
> 4. `checkout greatghee <variantId> US-FL-34787`: 402 with `totalUsd`,
>    `totalSats`, `invoice`, `macaroonBase64`.
> 5. `get_balance()` and `budget(action="status")`: enough headroom.
> 6. "Buy Great Ghee for ${totalUsd} (about {totalSats} sats), shipping to
>    34787. Pay it?" The human says yes.
> 7. `pay_l402_challenge(invoice=…, macaroon=…, max_sats=<totalSats>)`: preimage
>    captured.
> 8. `complete greatghee <variantId> US-FL-34787 <macaroon> <preimage>`:
>    `claimPageUrl`.
> 9. "Paid. Enter your shipping address here to finish: <claimPageUrl>."

> User: "Send my mom a jar of Great Ghee. She's at 1 Main St, Orlando FL 32801."
>
> 1. `catalog greatghee`, then `checkout greatghee <variantId> US-FL-32801`.
> 2. Budget gate, then "Send Great Ghee to your mom in Orlando for ${totalUsd}
>    (about {totalSats} sats). Pay it?" The buyer says yes.
> 3. `pay_l402_challenge(…)`, then `complete …`: the token from `claimPageUrl`.
> 4. Ask for her last name and which email gets the confirmation, read the
>    address back, and get a yes.
> 5. `claim greatghee SC-… you@example.com '{"firstName":"…","zip":"32801","country":"US",…}'`:
>    `shopifyOrderNumber`.
> 6. "Ordered. It ships to your mom in Orlando. Want a gift note?"
