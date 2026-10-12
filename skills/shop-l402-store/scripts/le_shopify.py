#!/usr/bin/env python3
"""
le_shopify.py: Lightning Enable Shopify L402 helpers for the shop-l402-store skill.

Handles the parts of the flow that must be byte-exact: the catalog lookup, the
L402 checkout challenge, the post-payment checkout retry, and the claim. The
PAYMENT leg is deliberately NOT in here. The agent pays the returned BOLT11
invoice with the Lightning Enable MCP: `pay_l402_challenge` (invoice + macaroon),
or `pay_invoice` when only the BOLT11 invoice is at hand. It then calls
`complete` with the preimage.

No credentials live in this file. The store endpoints are public (no API key);
payment authority lives entirely in the agent's MCP wallet. The macaroon and the
preimage pass through the command line for `complete`; this script never writes
them anywhere.

Usage:
  le_shopify.py catalog  <slug>
  le_shopify.py checkout <slug> <variantId> <buyerLocation> [quantity]
  le_shopify.py complete <slug> <variantId> <buyerLocation> <macaroonB64> <preimage> [quantity]
  le_shopify.py claim    <slug> <claimToken> <email> <shippingAddressJson>

buyerLocation format: {country}-{state}-{zip}, for example US-FL-34787.
  The location the goods ship to, used server-side for sales-tax calculation.
  For your own order that is your zip; for a gift it is the recipient's zip.

`complete` returns `claimPageUrl`. The claim token is its `token` query
parameter (it starts with `SC-`). `claimPageUrl` is null when the store has no
claim page configured.

shippingAddressJson (for `claim`): a JSON object, for example
  '{"firstName":"A","lastName":"B","address1":"1 Main St","city":"Orlando",
    "province":"FL","zip":"32801","country":"US"}'
  ("address2" and "phone" are optional). `claim` finalizes an order once it is
  paid and awaiting details; the token alone is sufficient at that point.

Exit codes: 0 ok, 1 usage, 2 exception, 3 the API rejected the call. On a
non-zero exit the JSON body is still printed (read "status"), but do NOT report
the step as done: a failed claim is not a placed order.
"""
import json
import sys
import urllib.error
import urllib.request

BASE = "https://api.lightningenable.com"


def _ok(status, also=()):
    return 200 <= status < 300 or status in also


def _req(method, path, headers=None, body=None):
    url = BASE + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Accept", "application/json")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        payload = e.read().decode()
        try:
            payload = json.loads(payload)
        except Exception:
            pass
        return e.code, payload


def catalog(slug):
    status, body = _req("GET", f"/api/shopify/{slug}/catalog")
    print(json.dumps({"status": status, "catalog": body}, indent=2))
    return _ok(status)


def checkout(slug, variant_id, buyer_location, qty=1):
    # NOTE: HTTP 402 is the EXPECTED, healthy response here: it carries the
    # Lightning invoice + macaroon. Anything else (400/404/500) is a real error.
    status, body = _req(
        "POST",
        f"/api/shopify/{slug}/checkout",
        headers={"X-Buyer-Location": buyer_location},
        body={"items": [{"variantId": int(variant_id), "quantity": int(qty)}]},
    )
    print(json.dumps({"status": status, "checkout": body}, indent=2))
    return _ok(status, also=(402,))


def complete(slug, variant_id, buyer_location, macaroon_b64, preimage, qty=1):
    # Standard L402 retry: the SAME checkout endpoint, now carrying the paid
    # credential. The server delegates to claim logic and returns the claim
    # token + claim-page URL the human uses to enter shipping.
    # A 402 here is NOT healthy (unlike `checkout`): it means the paid credential
    # was rejected, and money may be gone with no order to show for it.
    status, body = _req(
        "POST",
        f"/api/shopify/{slug}/checkout",
        headers={
            "X-Buyer-Location": buyer_location,
            "Authorization": f"L402 {macaroon_b64}:{preimage}",
        },
        body={"items": [{"variantId": int(variant_id), "quantity": int(qty)}]},
    )
    print(json.dumps({"status": status, "claim": body}, indent=2))
    return _ok(status)


def claim(slug, claim_token, email, shipping_json):
    # Finalize a paid order with a shipping address. Used for GIFTS (ship to
    # someone else): take the claim token from the `token` query parameter of
    # the `claimPageUrl` that `complete` returns, then submit the recipient's
    # address here. The token alone is accepted once the order is paid and
    # awaiting details. For your own order, hand the human the `claimPageUrl`
    # instead and let them enter the address there.
    address = json.loads(shipping_json)
    status, body = _req(
        "POST",
        f"/api/shopify/{slug}/claim",
        body={"claimToken": claim_token, "email": email, "shippingAddress": address},
    )
    print(json.dumps({"status": status, "order": body}, indent=2))
    return _ok(status)


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 1
    cmd = argv[1]
    try:
        if cmd == "catalog" and len(argv) == 3:
            ok = catalog(argv[2])
        elif cmd == "checkout" and len(argv) in (5, 6):
            ok = checkout(argv[2], argv[3], argv[4], argv[5] if len(argv) == 6 else 1)
        elif cmd == "complete" and len(argv) in (7, 8):
            ok = complete(argv[2], argv[3], argv[4], argv[5], argv[6],
                          argv[7] if len(argv) == 8 else 1)
        elif cmd == "claim" and len(argv) == 6:
            ok = claim(argv[2], argv[3], argv[4], argv[5])
        else:
            print(__doc__)
            return 1
    except Exception as e:  # noqa: BLE001 - surface any failure as JSON for the agent
        print(json.dumps({"error": str(e)}))
        return 2
    # The API's own verdict decides the exit code: never report a rejected call
    # as success just because the request itself completed.
    return 0 if ok else 3


if __name__ == "__main__":
    sys.exit(main(sys.argv))
