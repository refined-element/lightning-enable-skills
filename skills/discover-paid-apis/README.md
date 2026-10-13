# discover-paid-apis

**Find a paid API or digital service in two places, compare what you'd get, then try one with a single bounded purchase.**

Services that charge per call over Lightning are listed in two places, and this
skill searches both:

- the **Lightning Enable registry**, a public list of APIs that publish an
  [L402](https://github.com/lightninglabs/L402) manifest; and
- **[Amazap](https://amazap.com)**, a storefront where agents search
  pay-per-call APIs and digital services and buy calls with prepaid Amazap
  credits.

Every result is labeled with its source. Amazap is an extra source, not a
replacement for the registry, and it's optional. It's a separate product from
a collaborator in the Lightning ecosystem; Lightning Enable doesn't set its
prices, fees, credits, terms, or ranking.

## Why it's interesting

- **You see the price before anything moves.** Searching, reading a listing,
  and quoting are free. The only payment is one trial you approved, at an
  all-in price you saw.
- **Trust signals, as reported.** Amazap rows show Amazap's trust label,
  health, paid track record, and whether they can be bought now. A paused,
  degraded, or failing row is shown but never bought, and a row Amazap hides
  from search is left out. Registry rows show how many calls your session
  budget and wallet balance cover.
- **The right cap for the right wallet.** An Amazap buy spends Amazap credits,
  under your cap and Amazap's account limits. A registry result is paid from
  your Lightning Enable MCP wallet, under your cap and the MCP budget. The
  MCP budget never bounds an Amazap buy. The skill tells you which cap applies
  before it buys.
- **It ends with a receipt:** the sats charged, what's left, the listing, an
  order id or payment hash, and whether the service delivered.

## How it works

1. **Ask** what outcome you need, the most one trial may cost, and any limits
   on providers or data.
2. **Check the tools.** It notes whether your host lists Amazap's tools, and
   reads `budget action=status` and `get_balance` for the direct path. When
   Amazap's tools are listed, it reads your Amazap credits and current account
   limits from Amazap.
3. **Search both sources:** `discover_api` for the registry, and Amazap's
   `search_catalog` when your host lists it, otherwise Amazap's public
   products API.
4. **Compare** at most five labeled candidates and recommend one, with a
   one-sentence reason. Paused, degraded, or failing rows are shown, not
   bought; hidden rows are dropped.
5. **Read the details, unpaid:** a registry API's manifest, or an Amazap
   listing's input schema.
6. **Quote** the exact all-in total, and state which cap applies. Over the
   cap, nothing is bought.
7. **One trial,** after your yes: Amazap's `buy`, or `access_l402_resource`
   for a registry result. On the Amazap path, the same yes accepts Amazap's
   current terms. If the quote went stale, it shows you the fresh total and
   asks again.
8. **Report** the result and the receipt, then hand off to
   [`pay-l402-anywhere`](../pay-l402-anywhere/) for a URL you already have,
   or [`cited-answer`](../cited-answer/) for research.

## Requirements

- The [Lightning Enable MCP](https://github.com/refined-element/lightning-enable-mcp)
  server, for the registry search and the direct path. Paying a registry
  result needs a wallet that returns preimages (NWC, LND, or Strike); if that
  isn't set up yet, run [`agent-wallet-setup`](../agent-wallet-setup/) first.
- Optional: Amazap's MCP (https://amazap.com/mcp) and some Amazap credits, for
  an Amazap buy. Without it, Amazap search still works through Amazap's public
  products API.
- No Lightning Enable account.

## Try it

> "Find me a weather API and try one forecast for Berlin. Spend no more than
> 30 sats."

## Safety

- At most one trial purchase per run unless you ask for more, after an
  explicit yes, at an all-in price you saw. Never several paid calls to
  compare services.
- A quote over your cap is refused, and nothing is bought.
- A stale quote is never bought on the old yes: you see the fresh total and
  say yes again.
- It never sends secrets, private or logged-in URLs, credentials, personal
  data, or proprietary content as input unless you approve that.
- If your Amazap credits run short, it asks before a top-up, and you choose
  the amount. You pay the top-up invoice yourself, unless you explicitly ask
  the agent to pay it from your MCP wallet. Then it's its own `pay_invoice`
  payment that you approve at that exact amount. Your trial cap doesn't cover
  a top-up; when the MCP wallet pays it, the MCP budget limits do.
- After a paid failure it reports what happened and asks before trying
  anything else. A failed Amazap call is re-credited as Amazap credits, never
  cash.
- It never steers you away from Amazap's all-in price toward paying a listing
  Amazap surfaced directly. Direct payment is for a registry result or a URL
  you already have; to pay a URL you already have, use
  [`pay-l402-anywhere`](../pay-l402-anywhere/).
- Macaroons, preimages, invoices, and tokens never appear in the agent's
  output.
- Amazap's fees, limits, and terms belong to Amazap and change; the skill reads
  them live (https://amazap.com/llms.txt and https://amazap.com/credits).
- Lightning Enable does not hold funds; the payment provider facilitates
  custody and settlement.

## What it doesn't do

It doesn't vouch for a seller, set up a wallet, top up Amazap credits without
your yes, or pay registry endpoints that need POST (its direct path is
read-only: GET and HEAD). To sell an API of your own, see
[`producer-setup`](../producer-setup/), which can also draft an optional
Amazap listing.
