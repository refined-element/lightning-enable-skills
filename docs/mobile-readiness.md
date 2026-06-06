# Mobile-readiness spec: phone-native restock

**Goal:** make `restock-from-photo` (and skills like it) work in the **Claude
mobile app** — snap a photo of the near-empty jar on your counter, say "I'm
out," and a new one ships, all from your phone.

## Why it doesn't work on mobile today

Two hard constraints, both confirmed against Anthropic's current docs:

1. **Mobile supports only *remote* MCP connectors.** The Claude iOS/Android apps
   cannot connect to a local stdio MCP server — connectors run from Anthropic's
   cloud and the server must be reachable over the public internet. The
   Lightning Enable MCP currently runs as a **local process** (great on Claude
   Code / Desktop, invisible to mobile).

2. **Mobile can't run scripts.** A skill's helper script (`le_shopify.py`) needs
   a shell. On mobile there's no shell — the agent can only call **connector
   (MCP) tools**. So the catalog → checkout → pay → claim logic can't live in a
   script; it has to live in a hosted tool.

Net: on mobile, the *connector is the thing that does the work*. A "skill" is
just instructions; the doing happens in MCP tools.

## The plan

### 1. Host the Lightning Enable MCP as a remote server

- Run the existing MCP over **Streamable HTTP** transport (not stdio), behind a
  public HTTPS endpoint. The Docker image already exists
  (`refinedelement/lightning-enable-mcp`), so this is primarily a
  hosting + transport-config task (e.g. an Azure Container App).
- Add **auth** (OAuth or a bearer token) — this endpoint can move money, so it
  must not be open. Scope the wallet/budget tightly.
- Register it once as a **custom connector** in Claude settings; it then syncs
  to every client including the mobile apps.

### 2. Add a high-level `reorder_shopify_product` tool to the MCP

Because mobile can't orchestrate multi-step scripts, collapse the whole flow
into **one server-side tool** that does internally what the desktop skill does
across several steps:

```
reorder_shopify_product(
  slug:            string,   # e.g. "greatghee"
  variant_id:      number?,  # optional; if omitted and the store has one
                             #   product, use it; else require a product hint
  product_hint:    string?,  # human/label text to disambiguate multi-product stores
  buyer_location:  string,   # "US-FL-34787" (zip → tax)
  quantity:        number = 1,
  confirm_token:   string?   # see confirmation model below
) -> {
  stage: "quote" | "paid",
  product, total_usd, total_sats,
  claim_url?,                # present when stage == "paid"
  confirm_token?             # present when stage == "quote"
}
```

Internally the tool: looks up the catalog → creates the L402 checkout → (on
confirmation) pays from the hosted wallet → does the L402 claim retry → returns
the claim URL. Image identification stays with Claude (it's multimodal); the
tool takes the resolved `slug` / `product_hint`.

### 3. Keep the human in the loop without a shell

Mobile has no "run this and show me" step, so bake confirmation into the tool's
two-phase contract:

- **First call** returns `stage: "quote"` with `total_usd` / `total_sats` and a
  short-lived `confirm_token`. Nothing is paid.
- Claude shows the quote and asks the user to confirm.
- **Second call** with the `confirm_token` executes payment and returns
  `stage: "paid"` + `claim_url`.

This preserves "explicit confirmation before money moves" — the same guarantee
the desktop skill enforces — using only tool calls.

### 4. The mobile "skill"

Once the tool exists, the mobile experience is a thin instruction layer (a skill
if mobile skills are supported, otherwise just the connector's tool description):
*"When the user sends a product photo and says they're low/out, identify the
product, call `reorder_shopify_product` to get a quote, confirm the price with
the user, then call it again with the confirm_token, and share the claim URL."*

## Security checklist (this endpoint moves money)

- [ ] Auth on the remote MCP (OAuth/token); never an open endpoint.
- [ ] Per-connection wallet **budget caps** enforced server-side.
- [ ] Two-phase confirm_token (single-use, short TTL) so a stray tool call can't
      pay without an explicit second, confirmed call.
- [ ] Rate-limit the reorder tool.
- [ ] Log MerchantId/OrderId only — never wallet secrets, macaroons, or
      preimages.
- [ ] Reachable only over HTTPS from Anthropic's IP ranges.

## Effort sketch

| Piece | Rough effort |
|---|---|
| MCP over Streamable HTTP + hosting (Azure Container App) | M |
| Auth + budget scoping on the remote endpoint | M |
| `reorder_shopify_product` two-phase tool | M |
| Register connector + mobile end-to-end test | S |

None of it blocks the desktop skill, which works today. This is the deliberate
follow-on that lights it up on the phone.
