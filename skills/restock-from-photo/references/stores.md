# Known stores

Map a photographed product to a Lightning Enable Shopify L402 store. Each store
is identified by a **slug** used in the API paths
(`/api/shopify/{slug}/catalog`, `/checkout`).

To add your own store, run `python scripts/le_shopify.py catalog <slug>` and add
a row here with the products and their `variantId`s.

## greatghee — Great Ghee

- **Slug:** `greatghee`
- **Storefront:** greatghee.com
- **What it is:** Grass-fed A2/A2 ghee (cooking fat) in a jar.
- **Reorder target:** single product, single variant.
  - `Grass-Fed A2/A2 Ghee Cooking Fat` — variant `49883267432641` — ~$30
- **Photo cue:** a jar of ghee on a counter / in a kitchen. Unambiguous — this
  store sells one thing, so any "I'm out of ghee" + photo maps straight here.
- **Shipping:** domestic US only; free over $99, else ~$9.

## drinksote — Salt of the Earth (SOTE)

- **Slug:** `drinksote`
- **Storefront:** drinksote.com
- **What it is:** "Salt of the Earth" — electrolyte / hydration **sticks**
  (the consumable), plus some apparel + accessories (merch).
- **Reorder target (the consumable):** the stick packs. Match the photographed
  flavor/size to the closest variety pack. Examples (run `catalog drinksote`
  for the live list + current `variantId`s):
  - `15-Stick Variety Pack — citrus + chocolate + unflavored`
  - `35-Stick Variety Pack, 5-sticks of each flavor`
- **Photo cue:** a box / packet of electrolyte sticks. If the photo is apparel
  (hoodie, hat, bottle), that's merch — confirm the user really wants to
  reorder that, since it isn't a consumable.
- **Note:** this store has ~23 products. Identify the *specific* item in the
  photo before checkout; when unsure which variety pack, ask.

---

### Matching guidance

- Single-product stores (greatghee): trivial — the photo just confirms intent.
- Multi-product stores (drinksote): identify the exact item; prefer the
  consumable the user is "running low" on; ask if ambiguous.
- Always confirm the resolved product + price with the user before paying.
