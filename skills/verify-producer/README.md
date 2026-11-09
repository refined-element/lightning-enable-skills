# verify-producer

**Prove you own the API behind your Lightning Enable proxy, so it can be listed publicly.**

Anyone can point a Lightning Enable proxy at any public URL, so before a proxy
appears in the public registry, in agent discovery, or on Nostr, its owner
proves control of the API behind it. This skill has your agent do that: get a
verification token, publish it in a place only the API's owner can write to,
ask Lightning Enable to check, and then, with your yes, turn on public listing.

An unverified proxy keeps working by its direct URL. Verification adds the
listing and the verified mark buyers read. Nothing in this skill pays or moves
money. Lightning Enable does not hold funds; your wallet provider facilitates
custody and settlement.

## What you need

- A shell with `curl`. The skill's `scripts/verify.sh` makes every call, keeps
  the API key off the command line, and stores the token in a file with
  mode 600.
- Your Lightning Enable API key and the proxy's ID. A proxy made with
  [`sell-with-lightning-address`](../sell-with-lightning-address/) has both.
- One of these: deploy access to the API's web server, its DNS records, or its
  response headers.

## Try it

> "Verify my proxy forecast-api-a1b2 and list it publicly."

## What it does

1. Reads the proxy's verification state and the exact instructions for it.
2. Takes the token from the claim response, or issues one. The token is shown
   once, so it goes straight into a local file.
3. Publishes the token by one method:
   - **Well-known file:** if the agent can deploy to the API's host, it writes
     `/.well-known/lightning-enable.json`. Proves control of the web root.
   - **DNS TXT record** at `_lightning-enable.{your API's host}`: the agent
     gives you the exact record. Proves control of the DNS zone.
   - **Response header** `X-Lightning-Enable-Verify`: the agent gives you the
     header for your API. Proves control of the API's responses.
4. Runs the check, waits out a pending one, polls a bounded number of times
   while DNS settles, and explains any failure in plain words.
5. With your yes, turns on public listing, and explains the daily re-check:
   three failed checks in a row unlist the proxy until you verify again.

A proxy marked `grandfathered` (listed before verification existed) or
`platform` (a Shopify store entry) needs nothing; the agent says so and stops.

## Not this skill

- Create the paid endpoint first:
  [`sell-with-lightning-address`](../sell-with-lightning-address/),
  [`producer-setup`](../producer-setup/), or
  [`create-l402-proxy`](../create-l402-proxy/).
- Check how an endpoint behaves over L402:
  [`l402-compatibility-report`](../l402-compatibility-report/).

The full guide: [Verify ownership of your API](https://docs.lightningenable.com/products/agentic-commerce/verify-ownership).
