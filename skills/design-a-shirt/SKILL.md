---
name: design-a-shirt
description: >-
  Design a custom T-shirt on a Lightning Enable store from the person's own PNG
  or one an image model makes, paid over L402 from the Lightning Enable MCP
  wallet: check the artwork against the print specs, upload it, pay the design
  fee, wait for the Printful mockup, hand the approval link to the person, quote
  the shirt to their state and ZIP, pay the order after their yes, and hand them
  the private claim link for the shipping address. Optionally publish the
  approved design as a listing other people can buy, on a store that has
  publishing on. Use when the user says "put this on a T-shirt", "make me a
  custom shirt", "design a tee with this image", "print my artwork on a shirt",
  or "sell my shirt design". Do NOT use to buy the store's ready-made or
  community merchandise (the plain catalog checkout in the store's skills.md),
  to pay a generic L402 API (use pay-l402-anywhere), or to sell an API or a
  digital resource (use sell-this or producer-setup).
---

# Design a shirt

Turn a PNG into a real, printed T-shirt, paid in sats. The agent does the
work: checks the artwork, uploads it, pays the design fee over
[L402](https://github.com/lightninglabs/L402), fetches the Printful mockup,
quotes the shirt and pays for it. The person makes the two decisions that are
theirs: **approving the design for manufacture** and **entering the shipping
address**.

Lightning Enable is the platform underneath: it issues the Lightning invoices
and keeps the store's designs, quotes and orders. The store at
`https://store.lightningenable.com` is one deployment of Lightning Enable's
[Run your own Lightning store](https://docs.lightningenable.com/products/run-your-own-store)
product. Any merchant on a paid Lightning Enable plan can run the same
storefront with their own Printful account, and every deployment answers the
same `/api/store/custom/*` routes, so this skill works against any of them: set
the base URL and go. No marketplace is involved; a published listing lives on
the store that sells it. **Lightning Enable does not hold funds; the payment
provider facilitates custody and settlement.** Printful manufactures and ships.

The source of truth for every route below is the store's own reference:
[`/llms-full.txt`](https://store.lightningenable.com/llms-full.txt), sections
"Custom Products" and "Designed by our customers". If a response disagrees with
this file, the response wins.

## Who does what, and why

| The agent may | Only the person may |
|---|---|
| Check, upload and re-upload the artwork | Approve the design for manufacture, on the store's approval page |
| Pay the design fee (Payment A) after showing it | Confirm they hold the rights to print and sell the artwork (`acknowledgeRights`) |
| Poll the design and fetch the mockup | Confirm they understand print differs from a screen (`acknowledgePhysicalVariation`) |
| Ask for size, state and ZIP, and request a quote | Say yes to the shirt's price in sats |
| Pay the order (Payment B) after that yes | Enter the name and street address, on the private claim page |
| Track the order | Decide to publish the design for others to buy, and confirm the rights to sell it |

Why the line sits there: Lightning payments are final and Printful starts real
manufacturing, so the store accepts approval only from a person looking at the
mockup. There is no agent-approval route and no mandate path. The address stays
off the API entirely: the agent never sees it, never sends it, and cannot leak
it. **Never tick, send or claim an acknowledgement on the person's behalf.**

## What you need

- **Lightning Enable MCP** 2.x with a funded wallet that returns **preimages**:
  NWC (CoinOS, Alby Hub, CLINK), LND, or Strike. OpenNode does not return a
  preimage and cannot complete either payment. `setup_wallet` reports the
  configured wallet; [`agent-wallet-setup`](../agent-wallet-setup/) connects one
  from nothing.
- **A shell with `curl`** (or another HTTP client). The upload is multipart and
  both payments need custom headers and an exact repeat of the request, so this
  skill drives the store over plain HTTP and pays with `pay_invoice`. The
  commands below are bash; on Windows run them in Git Bash or WSL, and use
  `python` where they say `python3` if that is the name installed.
- **Python 3.10+** for `scripts/check_artwork.py`, and **Pillow**
  (`pip install Pillow`) for its pixel checks. Without Pillow it checks the
  header only and says so.
- **The artwork**: the person's PNG, or an image model to make one (see
  [Making the artwork](#making-the-artwork-with-an-image-model)).
- Budget for two payments: the design fee (`designPriceSats`, set by the store; 1,250 sats on
  store.lightningenable.com) and the shirt (a flat USD price converted to sats at quote time there).
- Tools this skill uses:
  - `get_balance` and `budget(action="status")`: the funds and the spend caps,
    before each payment.
  - `pay_invoice`: pays each BOLT11 invoice and returns the preimage.
  - `receipts(source="durable")`: the wallet's own payment log, afterwards (it
    never holds a preimage).
  - `verify_confirmation_code`: only checks a code; it never pays.

Argument names below are the Python server's `snake_case`. The .NET server takes
the same arguments in `camelCase` (`max_sats` is `maxSats`,
`confirmation_nonce` is `confirmationNonce`). Response fields are `camelCase` in
both.

## Design specs

These come from the live custom catalog (`designRequirements` and
`printAreas`). Read the catalog each time; it is the authority.

| Spec | Value |
|---|---|
| Product | Classic T-Shirt (`classic-tshirt`, Printful product 71), black or white, sizes S to 2XL |
| Placement and technique | Front only, direct-to-garment (DTG) |
| Print area | 12 x 16 in (width x height) |
| Format | PNG only |
| Dimensions | At least 2,400 x 2,400 px; at most 12,000 px on a side |
| Pixel cap | At most 40 million pixels in total, so 12,000 x 12,000 is refused. 3,600 x 4,800 (17.3 million) is well inside |
| File size | At most 50 MB (52,428,800 bytes) |
| Resolution | 150 DPI or more recommended. 3,600 x 4,800 fills the area at 300 DPI; 2,400 x 2,400 prints 12 x 12 in at 200 DPI |
| Background | Transparent, in practice required. An opaque PNG prints its background as a solid rectangle. A fully transparent PNG (or one under 50% opacity everywhere) has nothing to print and is refused at upload, free |
| Placement on the shirt | The image is fitted into the print area at its own aspect ratio, centred horizontally and aligned to the top of the area, never stretched |

The effective DPI is the larger of `width / 12` and `height / 16`. A square
image fills the width and sits at the top of the area; a 3:4 portrait image
fills all of it.

### What the store warns about, and what to do

The store splits its checks around the design fee. The custom catalog states
the split in `artworkChecks`:

- **Before payment (at upload, free):** "size and declared type, PNG
  signature, dimensions and pixel count, decodability, visible content
  (NoVisibleContent is refused with 400 nothing_to_print), and the
  LowEffectiveDpi, NoTransparency and ExcessiveEmptyMargins warnings." These
  come back in the upload response's `warnings`, each with a `code` and a
  `message`. `ExcessiveEmptyMargins` is measured at upload only for artwork with
  transparency; an opaque image's margins are measured after payment.
- **After Payment A:** "metadata removal, colour-profile and animation
  discard, contrast against the garment and the final print file. An
  unprintable file ends in GenerationFailed with failureCode InvalidInput and
  keeps the fee; only technical failures are retried free." These show on the
  design status under `printValidation.warnings`.

`scripts/check_artwork.py` runs both sets locally, so the person sees the
after-payment findings, contrast above all, before anyone pays.

| Code | When | What it means | Do this |
|---|---|---|---|
| `NoVisibleContent` (`400 nothing_to_print`) | Upload, refused | Fully transparent, or under 50% opacity everywhere: nothing would print. Nothing charged | Make artwork with visible pixels and upload again |
| `LowEffectiveDpi` | Upload, warning | Below 150 DPI at the print size; the print may look soft. At the 2,400 px minimum an accepted file always reaches 200 DPI, so this appears only where a store sets a lower minimum | Generate or export larger, aiming for 3,600 x 4,800. Upscaling a small raster helps little; regenerate if you can |
| `NoTransparency` | Upload, warning | No transparent pixels: the background prints as a solid rectangle | Re-export with an alpha channel and the background removed |
| `ExcessiveEmptyMargins` | Upload (transparent artwork) or after payment (opaque), warning | More than 40% of the canvas is empty, so the design prints smaller than the area | Crop the canvas to the artwork with a small border, then resize so it still meets the minimum |
| `LowContrastWithGarment` | After payment, warning | Half or more of the visible artwork is too close to the shirt color | Pick the other shirt color, or recolor the artwork. Check it before paying |
| `ColorProfileDiscarded` | After payment, warning | An embedded color profile is removed; colors are treated as sRGB | Export in sRGB |
| `AnimationDiscarded` | After payment, warning | An animated PNG; only the first frame prints | Export a still PNG |
| `GenerationFailed`, `failureCode` `InvalidInput` | After payment, failure | The file passed the upload but still cannot be printed. The design fee is kept | Upload new artwork for a new design (new key, new fee) |

A warning does not block the design; the person sees the warnings on the
approval page and decides. A `GenerationFailed` with any other failure code is
technical and the store retries it free of charge; keep polling.

## Making the artwork with an image model

If the person has no PNG, generate one. Ask what they want on the shirt and the
shirt color first, then write the prompt.

**Prompt template:**

```
<subject>, <style>, centered single graphic for a T-shirt print,
isolated on a transparent background, flat <N>-color palette that contrasts
with a <black|white> shirt, bold clean shapes, thick outlines,
no mock shirt, no model, no frame, no watermark, no signature,
no text smaller than a headline
```

- **Isolated on a transparent background.** Ask for a transparent PNG
  explicitly. If the model only paints a solid background, remove it with a
  background-removal tool and check the result: a white halo around the
  artwork prints as a white fringe.
- **Only the graphic.** No shirt, no person wearing it, no product photo, no
  frame, no watermark. The store places the graphic itself.
- **Text big or not at all.** Nothing under about 40 px tall in the final file.
  Image models also misspell words; read every letter before uploading.
- **Avoid the shirt's own color** in large areas: near-black art vanishes on a
  black shirt, near-white on a white one. The store warns about this, but only
  after the fee.
- **Avoid soft gradients that fade into the shirt color, and hairline strokes.**
  DTG prints those as muddy edges or drops them; strokes should be at least a
  few pixels wide at the final size.
- **Target size: 3,600 x 4,800 px** (or 3,600 x 3,600 for a square design).
  Most models output smaller; generate at the largest size offered and upscale
  with a dedicated upscaler only if needed, then check the DPI again.

### Verify the PNG before uploading

```bash
python scripts/check_artwork.py design.png --color black
```

It reports dimensions, whether there is an alpha channel, the effective DPI and
printed size, and every finding: **refused at upload** (nothing is charged) or
a warning, including the ones the store only reports after the fee. Exit codes:

- `0`: the store accepts the file (warnings may still be listed).
- `1`: the upload would be refused; fix it first.
- `2`: a usage error, or a file that cannot be read or decoded (the store
  refuses an undecodable PNG too).
- `3`: the header checks pass but the pixels were not checked, because Pillow
  is missing. The store still checks visible content and margins at upload,
  but contrast with the shirt only after the fee, so install Pillow (or look at
  the artwork against the shirt color yourself) before paying.

`--json` gives the same report as JSON. It reads the local file only.

Show the person the image and the findings, and get their go-ahead on the
artwork before any payment.

**One upload, several designs.** An upload can start up to 5 designs within 24
hours, for example the same artwork on a black and a white shirt. Each design
pays its own design fee. After 5 designs (`upload_design_limit`) or 24 hours
(`upload_expired`), upload the PNG again.

## Flow

Use one base URL throughout:

```bash
STORE=https://store.lightningenable.com
```

Keep a private working folder for the request bodies and the 402 responses, so
a crash or a lost reply never loses an `Idempotency-Key` or a token:

```bash
W="$HOME/.le-shirt/$(date +%Y%m%d-%H%M%S)"; mkdir -p "$W"; chmod 700 "$W"
```

Generate every `Idempotency-Key` as a fresh UUID with `uuidgen` (or
`python3 -c 'import uuid; print(uuid.uuid4())'` where `uuidgen` is missing).
A UUID satisfies every route's rules: 1 to 200 characters from
`A-Z a-z 0-9 . _ : -`, and at least 16 for a listing checkout. Write each key to
the folder before you send it.

Pull a field out of a saved response without printing the rest:

```bash
field() { python3 -c 'import json, sys; d = json.load(open(sys.argv[1])); [d := d[k] for k in sys.argv[2:]]; print(d)' "$@"; }
field "$W/design-402.json" l402 invoice
```

Shell state may not survive between tool calls: set `STORE`, `W` (the same
folder path) and `field` again at the top of each command that uses them.

### 1. Read the custom catalog (free)

```bash
curl -sS "$STORE/api/store/custom/catalog"
```

A `404` with `custom_products_disabled` means this store has custom products
off: stop and say so. Otherwise note `designPriceSats`, `pricingMode`, the
colors, sizes, `designRequirements`, `printAreas` and `availability.shipsTo`.

### 2. Check, then upload the PNG (free)

```bash
python scripts/check_artwork.py design.png --color black
uuidgen > "$W/upload.key"
curl -sS -X POST "$STORE/api/store/custom/uploads" \
  -H "Idempotency-Key: $(cat "$W/upload.key")" \
  -F "file=@design.png;type=image/png"
```

`201` returns `uploadId`, `sha256`, `widthPx`, `heightPx`, `effectiveDpi` and
`warnings` (`LowEffectiveDpi`, `NoTransparency`, `ExcessiveEmptyMargins`).
Uploading never charges. A file that fails a pre-invoice check is `400
upload_rejected` (or `file_required`, `file_too_large`), and one with nothing
visible is `400 nothing_to_print` (`failureCode: NoVisibleContent`); nothing is
charged either way. `503 upload_busy` means the store is checking other
uploads: wait `Retry-After` (5 seconds) and repeat the exact request; the same
`Idempotency-Key` returns the stored upload. `productCode` is an optional form
field, `classic-tshirt` by default.

### 3. Pay the design fee (Payment A)

Tell the person the fee in sats (`designPriceSats`) and what it covers:
validation, print-file preparation, the Printful mockup, private storage and
free polling. It is **not refunded** if they dislike the result; technical
failures are retried free.

Write the body to a file so the paid retry sends the same bytes:

```bash
uuidgen > "$W/design.key"     # or: python3 -c 'import uuid; print(uuid.uuid4())'
cat > "$W/design.json" <<'JSON'
{"uploadId": "upl_...", "product": {"productCode": "classic-tshirt", "color": "black", "placement": "front"}}
JSON
curl -sS -X POST "$STORE/api/store/custom/designs" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: $(cat "$W/design.key")" \
  --data-binary @"$W/design.json" -o "$W/design-402.json" -w "%{http_code}\n"
```

The answer is `402` with `designId`, `priceSats` and
`l402: {macaroon, invoice, paymentHash, amountSats, expiresAt}`.

1. Check `l402.amountSats` equals `designPriceSats`. If not, stop and ask.
2. `get_balance()` and `budget(action="status")`: the balance and the caps
   must cover it.
3. Pay, with the cap set to the amount (`pay_invoice` defaults to a 1,000-sat
   cap, so always pass it):

   ```
   pay_invoice(invoice="<l402.invoice>", max_sats=<l402.amountSats>)
   ```

4. Repeat the **exact** request, same body file and same key, adding the
   credential:

   ```bash
   curl -sS -X POST "$STORE/api/store/custom/designs" \
     -H "Content-Type: application/json" \
     -H "Idempotency-Key: $(cat "$W/design.key")" \
     -H "Authorization: L402 $(field "$W/design-402.json" l402 macaroon):<preimage>" \
     --data-binary @"$W/design.json" -o "$W/design-paid.json" -w "%{http_code}\n"
   ```

   Reading the macaroon from the saved 402 keeps it out of the transcript; the
   preimage is the one `pay_invoice` just returned.

`202` returns `designId`, `status: DesignPaymentVerified`, **`claimToken`**
(`led_...`), `claimExpiresAt`, `paidSats` and `statusUrl`. The claim token is
shown only here (repeating the paid retry returns the same one). It is the
design's credential for status, approval and quotes: keep it in the working
folder, never in chat.

```bash
field "$W/design-paid.json" claimToken > "$W/design.token"
```

### 4. Wait for the mockup (free)

```bash
curl -sS "$STORE/api/store/custom/designs/<designId>" \
  -H "Authorization: Bearer $(cat "$W/design.token")"
```

Poll every 10 seconds. Statuses run `DesignPaymentVerified`,
`PreparingPrintFile`, `GeneratingMockup`, then `AwaitingApproval`. A Printful
render can take a minute or more. At `AwaitingApproval`:

- `mockups[]` lists the preview. `"placeholder": false` is a Printful render
  of the exact artwork, color and placement; `true` means the store shows the
  prepared print file instead. Fetch the image with
  `GET /api/store/custom/designs/<designId>/mockups/<mockupId>` (same Bearer
  token) if you want to show it.
- `artwork` gives the digest, size, `background` and `effectiveDpi`;
  `printValidation.warnings` lists the findings. Tell the person each warning in
  plain words and what it means for the print.
- `approvalUrl` is set.

`GenerationFailed` with `failureCode` `InvalidInput`: the artwork cannot be
printed. Fix it and start a new design (a new upload if needed, a new key, a
new fee). Any other `GenerationFailed` is retried free; keep polling.

### 5. Hand the approval to the person (the agent never approves)

Give the person the approval link: `approvalUrl` with the design claim token
appended.

```
https://store.lightningenable.com/store/custom/design/<designId>/approve?credential=<design claim token>
```

Or give them the bare `approvalUrl` and the token separately; the page asks
them to paste it. Send it only to that person, privately: the link is the
design's key. Tell them what they will do there: look at the mockup, the
product, the color, the print warnings and the fee paid, tick both statements
themselves (they hold the rights to print and sell the artwork; printed color,
size and placement differ from a screen), and approve or reject.

Then wait. Ask them to tell you when they are done, and poll the status (every
10 seconds is allowed; slower is fine while you wait for a person):

- `Approved`: go on. `approvedArtworkSha256` names the approved artwork.
- `RejectedByCustomer`: ask what to change. A new design pays a new fee; the
  same upload works for 24 hours and up to 5 designs.
- `Expired`: the design lapsed; start again if they still want it.

### 6. Quote the shirt (free)

Ask the person for the **size, state and ZIP code only**. Never ask for, store
or send a name or street address here.

```bash
uuidgen > "$W/quote.key"
curl -sS -X POST "$STORE/api/store/custom/designs/<designId>/quotes" \
  -H "Authorization: Bearer $(cat "$W/design.token")" \
  -H "Idempotency-Key: $(cat "$W/quote.key")" \
  -H "Content-Type: application/json" \
  -d '{"variant": {"size": "L"}, "destination": {"countryCode": "US", "stateCode": "PA", "postalCode": "19103"}, "shippingMethod": "STANDARD"}'
```

`200` returns `quoteId`, `totalUsd`, `priceSats`, `btcUsdRate`, `expiresAt`,
`binding` (including `destinationScope`, such as `US-PA-191`), `pricingMode`,
`pricingSource` and `pricingIsEstimate`. One unit per order, standard shipping
only. A quote lives about 15 minutes; repeating the request with the same key
returns the same quote.

Custom shirts ship to the 48 contiguous states and DC. Alaska, Hawaii, US
territories, APO/FPO/DPO and other countries are `400
destination_not_supported`. Tell the person, with the store's support line:
**"Shipping outside the continental US? Contact us at
support@lightningenable.com and we may be able to accommodate your order."**

### 7. Get the person's yes on the total

Show the person `priceSats` and `totalUsd`, the size, the color and that the
address must be inside the quoted state and ZIP area. Say that Lightning
payments are final and there are no automatic refunds. Wait for an explicit yes
to that number.

### 8. Pay for the shirt (Payment B)

```bash
uuidgen > "$W/checkout.key"
printf '%s' '{"quoteId": "quo_...", "designId": "des_..."}' > "$W/checkout.json"
curl -sS -X POST "$STORE/api/store/custom/checkout" \
  -H "Authorization: Bearer $(cat "$W/design.token")" \
  -H "Idempotency-Key: $(cat "$W/checkout.key")" \
  -H "Content-Type: application/json" \
  --data-binary @"$W/checkout.json" -o "$W/checkout-402.json" -w "%{http_code}\n"
```

`402` carries `orderId` and an invoice for exactly the quote's `priceSats`; the
invoice expires no later than the quote. A quote with under two minutes left
gets no invoice (`quote_expiring`): request a new quote and show the person the
new total. `503 pricing_unavailable` means the quote could not be turned into
an invoice: nothing was charged; request a new quote, show the new total, and
check out again.

1. Check `l402.amountSats` equals the quoted `priceSats`. If not, stop.
2. `get_balance()` and `budget(action="status")`.
3. `pay_invoice(invoice="<l402.invoice>", max_sats=<l402.amountSats>)`.
   A shirt is above the default auto-approve tiers, so expect
   `requiresConfirmation`: the MCP sends a code to the person on its approval
   channel (its console by default), never to you. Ask the person for it and
   re-call with the same arguments plus the code:

   ```
   pay_invoice(invoice="<l402.invoice>", max_sats=<l402.amountSats>, confirmation_nonce="<code from the person>")
   ```

   Never guess a code. If the caps are too low for one shirt, the operator
   raises `limits.maxPerPaymentSats` in `~/.lightning-enable/config.json` to
   just above the price; an agent can only lower limits.
4. Repeat the **exact** request with the L402 credential **in place of** the
   Bearer token:

   ```bash
   curl -sS -X POST "$STORE/api/store/custom/checkout" \
     -H "Authorization: L402 $(field "$W/checkout-402.json" l402 macaroon):<preimage>" \
     -H "Idempotency-Key: $(cat "$W/checkout.key")" \
     -H "Content-Type: application/json" \
     --data-binary @"$W/checkout.json" -o "$W/checkout-paid.json" -w "%{http_code}\n"
   ```

`200` returns `orderId`, `status: PaidAwaitingDetails`, `claimUrl`, the order
**`claimToken`** (`leo_...`), `claimExpiresAt`, `paidSats` and `statusUrl`. A
payment that settles after the quote expired is still honored.

```bash
field "$W/checkout-paid.json" claimToken > "$W/order.token"
```

### 9. Hand the claim link to the person

Give the person `claimUrl`, privately. They enter the name and shipping address
there, inside the quoted area (`destinationScope`); an address outside it is
refused and the claim stays open for a corrected one. The address is never
sent to or returned by the API. Then the store drafts the order at Printful,
checks Printful's price against the quote, and submits it once.

### 10. Track the order (free)

```bash
curl -sS "$STORE/api/store/custom/orders/<orderId>" \
  -H "Authorization: Bearer $(cat "$W/order.token")"
```

It returns status, product, size, color, quantity, sats paid, Printful status
and tracking, never the address. Statuses: `PaidAwaitingDetails` (waiting for
the address), `Claimed`, `PrintfulDraftCreated`, `PrintfulCostVerified`,
`SubmittedForFulfillment`, `InProduction`, `Shipped`, `Delivered`.

- `AddressInvalid`: Printful refused the address and the claim is open again;
  send the person the `claimUrl` again.
- `ManualReview`: a person at Lightning Enable contacts the buyer (for example,
  Printful's price rose past what the quote allowed). Nothing is charged twice.
- Stuck at `Claimed`, `PrintfulDraftCreated` or `PrintfulCostVerified`: the
  store finishes it in the background. To nudge it, with no body and never an
  address: `POST /api/store/custom/orders/<orderId>/fulfill` with the order
  Bearer token. `409 address_required` means the person has not entered the
  address yet.

Report back: what was made, sats paid for each payment (`receipts(source="durable")`
has the wallet's record), the order status, and the tracking once it ships.

## Publish and sell (when the store has publishing on)

Publishing is off on a store until its operator turns it on. As of October
2026, `store.lightningenable.com` has custom products on but listings off: the
listing routes answer `404 custom_listings_disabled` and a publish request
answers `409 publishing_disabled`. Offer this only when the person asks, and only for an
`Approved` design.

1. Ask for a listing title (1 to 120 characters) and for the person's explicit
   confirmation that the artwork may be **sold to other buyers**. That is their
   statement, not yours: never send `acknowledgeRights` without it.
2. Request it:

   ```bash
   curl -sS -X POST "$STORE/api/store/custom/designs/<designId>/publish" \
     -H "Authorization: Bearer $(cat "$W/design.token")" \
     -H "Content-Type: application/json" \
     -d '{"listingTitle": "Orange Bolt Tee", "acknowledgeRights": true}'
   ```

   The answer is `{designId, publicationStatus, listingId, listingTitle,
   listingUrl, publishedAt, listingExpiresAt, next}`. `publicationStatus` is
   `pending_review` while the store operator reviews it (the default), then
   `published` with `listingUrl`, or `rejected`. On the approval page the person
   can do the same themselves.
3. Read it with `GET /api/store/custom/designs/<designId>/publication` (same
   Bearer token). Once `published`, give the person `listingUrl` to share. A
   listing never shows the designer or the design id.
4. Take it down with `POST /api/store/custom/designs/<designId>/withdraw`.
   Withdrawn, rejected and expired listings are closed for good; a new request
   is `409 invalid_transition`. The design stays approved for the person's own
   orders, and orders already paid are still made.

**How buyers buy a listing.** A person opens `listingUrl`, picks a size, enters
their state and ZIP, sees the price in sats and pays a Lightning QR code on a
private hosted checkout, then gets their own claim link. An agent buys with
`POST /api/store/custom/listings/<listingId>/checkout`, an `Idempotency-Key`
of at least 16 characters (a new UUID per purchase), and a postal-level body
such as `{"size": "L", "quantity": 1, "destinationScope": "US-PA-191"}`; it
answers `402` with a fresh quote and invoice, then the same pay-and-repeat as
Payment B returns `claimUrl` and `claimToken`. `GET /api/store/custom/listings`
and `GET /api/store/custom/listings/<listingId>` list what is buyable. Each
buyer gets their own quote, order and claim; the design never changes.

## Lost 402s and retries

Both payments are safe to retry without paying twice, **as long as you resend
the exact request with the same `Idempotency-Key`**:

- **Invoice still payable:** the same 402 again, byte for byte (same invoice,
  same macaroon). Nothing new is minted. Pay it if you have not.
- **Invoice expired unpaid:** after its expiry plus a 120-second grace, a new
  invoice and macaroon for the same design or order. If the old one was paid
  after all, its credential still redeems. For Payment B the quote must still be
  payable, or you get `409 quote_expired`: request a new quote.
- **Invoice paid:** `409 payment_pending` with `paymentStatus` `paid` (or
  `processing` while it settles). No new invoice: repeat the request with the
  L402 credential from that payment.
- **Invoice bound but not re-sendable yet:** `409 payment_pending` with
  `paymentExpiresAt` (UTC). Pay the invoice if you still hold it and it is
  payable; otherwise repeat after that time. `paymentExpiresAt: null` means
  start over with a new key.

A new key is a new design or order. Never change the key to "unstick" a
request you may have paid: that is how a second invoice gets paid.

**If `pay_invoice` reports `status: "pending"`**, the payment may still settle.
Do not pay again. Repeat the unpaid store request with the same key; `409
payment_pending` tells you its state. If no preimage ever comes back, the
credential cannot be built: send the design or order id and the payment hash to
support@lightningenable.com.

## Credentials and privacy

- **Private, always:** the design claim token (`led_...`), the order claim
  token (`leo_...`), macaroons, preimages and any `Authorization` header. Keep
  them in the working folder; never paste them into chat, logs, issues or
  shared transcripts, and never add `-v` to `curl` (it prints request headers).
- **Tokens travel in headers.** The only URLs that carry a token are the two
  links you hand the person: the approval link (`?credential=`) and the store's
  `claimUrl`. Never put a token in any other URL, path or query.
- **Postal level only.** Size, state and ZIP for quotes; the name and street
  address only ever on the claim page, typed by the person.
- One L402 payment at a time: finish one 402, pay, repeat cycle before the next.

## Errors

Errors are JSON `{"error": "<code>", "message": "..."}`; the message says what
to do next. "Nothing charged" means no invoice was paid by that answer.

| Code | What it means | Do this |
|---|---|---|
| `404 custom_products_disabled` | This store has custom products off | Stop. Offer the regular catalog, or another store |
| `404 custom_listings_disabled` | Listings are off on this store | Publishing and listing purchases are unavailable here |
| `400 upload_rejected`, `file_required`, `file_too_large` | The PNG failed a pre-invoice check (including a damaged or undecodable PNG) | Fix it (run `check_artwork.py`), upload again. Nothing charged |
| `400 nothing_to_print` | `failureCode: NoVisibleContent`: fully transparent, or under 50% opacity everywhere | Upload artwork with visible pixels. Nothing charged |
| `503 upload_busy` | The store is decoding other uploads | Honour `Retry-After` (5 seconds) and repeat the exact request, same `Idempotency-Key`. Nothing stored or charged |
| `400 upload_expired` | The upload is over 24 hours old | Upload the PNG again |
| `409 upload_design_limit` | The upload already started 5 designs | Upload the PNG again |
| `400 idempotency_key_required`, `invalid_idempotency_key` | Missing or malformed key | Send a new UUID |
| `409 idempotency_key_reuse` | The key was used for a different request | Use a new key for the new request; resend the original body for the original key |
| `401 invalid_credential`, `invalid_preimage`, `credential_mismatch` | The credential is not for this exact request | Repeat the original request exactly: same body, same key, same path |
| `401 claim_token_required` | No Bearer token | Send `Authorization: Bearer <claim token>` |
| `404 claim_not_found` | Unknown design or order id, or a token that does not match it | Check you sent the right token for this id (the design token for designs and quotes, the order token for orders). Never guess or reuse another token |
| `404 quote_not_found` | Unknown quote id, or the token does not match | Request a new quote with the design token |
| `409 payment_pending` | An invoice is bound | See [Lost 402s](#lost-402s-and-retries): redeem it, pay it, or wait for `paymentExpiresAt` |
| `409 payment_superseded` | The credential is for an invoice replaced twice | Do not pay anything else. If you paid it, contact support@lightningenable.com with the id and payment hash |
| `409 design_already_paid`, `order_already_paid` | Already paid | Repeat with your L402 credential to get the claim token |
| `409 design_closed` | The design was rejected, taken down or expired | Start a new design with a new key. If you paid its invoice, contact support |
| `409 design_taken_down` | The design was taken down; the order is cancelled and takes no payment | Do not pay. If a payment still arrived it is recorded: contact support |
| `409 design_not_approved` | Not approved yet | Wait for the person to approve on the approval page |
| `409 quote_expired`, `quote_expiring`, `quote_already_ordered`, `quote_not_payable` | The quote cannot take a payment | Request a new quote and show the person the new total |
| `400 destination_not_supported` | Outside the 48 contiguous states and DC | Give the person the support line in the message (`support` in the body) |
| `400 invalid_size`, `invalid_color`, `invalid_placement`, `invalid_quantity`, `invalid_product` | A value the catalog does not offer | Use values from the custom catalog; one unit per order |
| `409 address_required` | No address yet | Send the person the `claimUrl` |
| `409 order_closed`, `order_in_review`, `quote_changed` | The order is held for a person at Lightning Enable | Contact support@lightningenable.com with the order id |
| `410 claim_expired` | The claim window ended | Contact support with the order id |
| `410 endpoint_moved` | A retired path-token route | Use `newPath`, token in the `Authorization` header |
| `409 listing_not_available` | Withdrawn, taken down or expired; with `reason: "publishing_disabled"` the store paused listing sales | Nothing charged. Do not pay an invoice you still hold for it; tell the buyer |
| `404 listing_not_found` | Unknown or closed listing | Check the id; it may have closed |
| `409 publishing_disabled` | The store takes no new listings | Publishing is not available on this store now |
| `409 publish_limit_reached` | The designer has the most listings allowed (`limit`) | Withdraw one first, or keep the design private |
| `400 invalid_listing_title`, `acknowledgement_required` | Title not 1 to 120 characters, or no rights confirmation | Fix the title; get the person's confirmation |
| `400 invoice_outlives_quote` | Not listed in the store's reference: a Lightning Enable API refusal of an invoice that would stay payable too long after the quote. The current store bounds the invoice itself | No invoice reached you, so there is nothing to pay. Request a new quote and try once more; if it repeats, contact support |
| `429 mint_rate_limited`, `listing_quote_limit`, or any rate limit | Too many requests | Wait `Retry-After` seconds (60 if absent). Nothing charged |
| `503 store_api_unavailable`, `artwork_storage_unavailable`, `invoice_unavailable`, `price_unavailable` | A dependency is busy | Retry after `Retry-After`; nothing is charged twice |
| `503 pricing_unavailable` | The quote could not be turned into an invoice | Nothing charged. Request a new quote, show the person the new total, then check out again |
| `503 pricing_not_configured`, `store_subscription_inactive` | The store is not set up to sell right now | Try later or contact the store |
| `503 fulfillment_unavailable`, `fulfillment_busy` | The order is saved; Printful is busy | Retry the fulfill nudge after `Retry-After`, or let the store finish it |

Per-IP rate limits: uploads 20 per hour, design requests 10 per minute, design
status 120 per minute, mockup images 30 per minute, quotes 20 per minute,
checkout 10 per minute, order status 60 per minute, fulfill 10 per minute. New
invoices also share a store-wide window of 60 per minute.

**Refunds.** There are no automatic Lightning refunds. The design fee is spent
once preparation starts (technical failures are retried free, never charged
twice). Printful problems with a paid order go to manual review. For any
exception, email support@lightningenable.com with the design or order id.

## Safety rules

- **The person approves; the agent never does.** No acknowledgement is ever set
  by the agent, and there is no API route that approves.
- **Show each amount before paying it**, and get an explicit yes to the shirt's
  total in sats. Pass `max_sats` equal to the invoice amount you showed.
- **Check the invoice matches**: `amountSats` equals `designPriceSats` for
  Payment A and the quote's `priceSats` for Payment B. A mismatch is a stop.
- **Check the artwork before paying the fee.** Run `check_artwork.py` with the
  shirt color and show the person every finding, the after-payment ones
  (contrast above all) included, before Payment A. Exit 3 means the pixels went
  unchecked: say so rather than calling the file fine.
- **Same key, same body, on every retry.** Never mint a second invoice to get
  around a 409.
- **Never self-approve a payment.** Confirmation codes come from the person.
- **Keep tokens, macaroons and preimages private**, and the address off the API.
- **One payment at a time.**

## Example

> User: "Put this lightning-bolt drawing on a black T-shirt for me, size L. I'm
> in 19103."
>
> 1. `check_artwork.py bolt.png --color black` → 3,600 x 4,800, alpha yes,
>    300 DPI, no findings. The person says the artwork is right.
> 2. Catalog → design fee 1,250 sats. Upload → `upl_...`, no warnings.
> 3. "The design fee is 1,250 sats and is not refunded if you don't like the
>    mockup. Pay it?" Yes. `POST /designs` → 402 → `get_balance()`,
>    `budget(action="status")` → `pay_invoice(invoice="lnbc...", max_sats=1250)`
>    → paid retry → `202`, claim token saved privately.
> 4. Poll → `AwaitingApproval`, Printful mockup ready, no warnings.
> 5. "Here is your approval link (keep it to yourself): ... Look at the mockup,
>    tick both statements if you agree, and approve." The person approves;
>    the status shows `Approved`.
> 6. Quote L to PA 19103 → 34,602 sats ($28.42), valid about 15 minutes.
>    "The shirt is 34,602 sats including shipping and tax estimate. Payments
>    are final. Pay it?" Yes.
> 7. `POST /checkout` → 402 →
>    `pay_invoice(invoice="lnbc...", max_sats=34602)` → confirmation needed →
>    the person reads the code from the MCP console → re-call with
>    `confirmation_nonce` → paid retry → `200` with `claimUrl`.
> 8. "Paid. Enter your shipping address here (private link): ... I'll keep an
>    eye on the order." Later: `Shipped`, with tracking.
