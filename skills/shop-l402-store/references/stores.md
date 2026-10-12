# Known stores

Lightning Enable Shopify stores that sell physical products over L402. Each store
has a **slug** that goes in every API path (`/api/shopify/{slug}/catalog`,
`/checkout`, `/claim`).

Both slugs below answered `GET https://api.lightningenable.com/api/shopify/{slug}/catalog`
with HTTP 200 on 2026-10-11. Product names, variants, prices, and stock change on
the merchant's side, so treat this file as a map for identifying the store and
the catalog as the truth for everything else. Run
`python scripts/le_shopify.py catalog <slug>` before every order.

## greatghee: Great Ghee

- **Slug:** `greatghee`
- **Storefront:** greatghee.com
- **What it sells:** grass-fed A2/A2 ghee (a cooking fat) in a jar.
- **Products:** one product with one variant, `Grass-Fed A2/A2 Ghee Cooking Fat`.
  Take its `variantId` and `priceUsd` from the catalog.
- **Photo cue:** a jar of ghee in a kitchen or on a counter. The store sells one
  thing, so "send my friend a jar of ghee" or "order more ghee" maps straight
  here.
- **Shipping:** the catalog's `shipping` block reports domestic US only, with
  free shipping above a threshold. Read the block for the live numbers.

## drinksote: Salt of the Earth (SOTE)

- **Slug:** `drinksote`
- **Storefront:** drinksote.com
- **What it sells:** Salt of the Earth zero-sugar electrolyte powder in single
  stick packs, sold as single-flavor boxes and bags (12-stick box, 30-stick bag),
  variety packs, a citrus power pack, and creatine stick packs. It also sells
  merchandise: hoodies, shorts, hats, glass bottles, and stickers.
- **Consumables to match first:** the electrolyte powders by flavor (chocolate,
  grapefruit, lemon lime, orange, pink lemonade, strawberry kiwi, tropical
  hibiscus, unflavored, watermelon) and size, and the variety packs by stick
  count (12, 15, or 35 sticks).
- **Photo cue:** a box, bag, or packet of electrolyte sticks. Read the flavor and
  the stick count off the packaging. If the photo shows apparel or a bottle, that
  is merchandise: confirm the human really wants another one.
- **Do not buy without an explicit ask:** the `Salt of the Earth Gift Card`
  variants and the `Subscription Upgrade` item. Neither is a physical product to
  ship.
- **Note:** the catalog lists dozens of variants, and some are out of stock
  (`available: false`). Identify the exact product and variant; when two are
  close, ask.
- **Shipping:** domestic US only, per the catalog's `shipping` block.

## Finding other stores

A store missing from this list can still work, as long as it is a Lightning
Enable Shopify store:

- **The L402 registry.** Lightning Enable lists Shopify stores whose merchant
  opted in. Search it with the MCP:
  `discover_api(query="<product or store>")` or `discover_api(category="commerce")`.
  A store's registry entry is named `<slug> (Shopify)`, and its manifest URL
  path reads `/l402/proxy/shopify-<slug>/`. Either one gives you the slug.
- **The merchant or the human tells you the slug.** Check it with
  `python scripts/le_shopify.py catalog <slug>`. A 404 means the slug is wrong
  or the store is inactive: stop and say so.

Not a Lightning Enable Shopify store, so out of scope for this skill:

- **store.lightningenable.com** (the Lightning Enable merchandise store) uses a
  different API (`/api/store/catalog`, `/api/store/checkout`,
  `/api/store/claim`). The MCP handles that flow with `access_l402_resource`.
- **Any other Shopify store.** A store that has not connected Lightning Enable
  has no `/api/shopify/{slug}/catalog` and cannot take an L402 payment.

## Matching guidance

- One-product store (greatghee): the human's words or the photo only confirm
  intent. Still read the variant from the catalog.
- Many-product store (drinksote): match the exact product and variant. Prefer the
  consumable the human asked about, and ask when a flavor or size is unclear.
- Always read the resolved product, the store, and the total back to the human
  before paying.
