#!/usr/bin/env python3
"""
le_shopify.py — Lightning Enable Shopify L402 helpers for the restock-from-photo skill.

Handles the parts of the flow that must be byte-exact (catalog lookup, the L402
checkout challenge, and the post-payment claim retry). The PAYMENT leg is
deliberately NOT in here: on Claude Code / Desktop the agent pays the returned
BOLT11 invoice using the Lightning Enable MCP wallet tools
(`pay_l402_challenge` / `pay_invoice`), then calls `complete` with the preimage.

No credentials live in this file. The catalog and checkout endpoints are public
(no API key); payment authority lives entirely in the agent's MCP wallet.

Usage:
  le_shopify.py catalog  <slug>
  le_shopify.py checkout <slug> <variantId> <buyerLocation> [quantity]
  le_shopify.py complete <slug> <variantId> <buyerLocation> <macaroonB64> <preimage> [quantity]

buyerLocation format: {country}-{state}-{zip}, e.g. US-FL-34787
  — this is the BUYER's location, used server-side for sales-tax calculation.
"""
import json
import sys
import urllib.error
import urllib.request

BASE = "https://api.lightningenable.com"


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


def checkout(slug, variant_id, buyer_location, qty=1):
    # NOTE: HTTP 402 is the EXPECTED, healthy response here — it carries the
    # Lightning invoice + macaroon. Anything else (400/404/500) is a real error.
    status, body = _req(
        "POST",
        f"/api/shopify/{slug}/checkout",
        headers={"X-Buyer-Location": buyer_location},
        body={"items": [{"variantId": int(variant_id), "quantity": int(qty)}]},
    )
    print(json.dumps({"status": status, "checkout": body}, indent=2))


def complete(slug, variant_id, buyer_location, macaroon_b64, preimage, qty=1):
    # Standard L402 retry: the SAME checkout endpoint, now carrying the paid
    # credential. The server delegates to claim logic and returns the claim
    # token + claim-page URL the human uses to enter shipping.
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


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 1
    cmd = argv[1]
    try:
        if cmd == "catalog" and len(argv) == 3:
            catalog(argv[2])
        elif cmd == "checkout" and len(argv) in (5, 6):
            checkout(argv[2], argv[3], argv[4], argv[5] if len(argv) == 6 else 1)
        elif cmd == "complete" and len(argv) in (7, 8):
            complete(argv[2], argv[3], argv[4], argv[5], argv[6],
                     argv[7] if len(argv) == 8 else 1)
        else:
            print(__doc__)
            return 1
    except Exception as e:  # noqa: BLE001 - surface any failure as JSON for the agent
        print(json.dumps({"error": str(e)}))
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
