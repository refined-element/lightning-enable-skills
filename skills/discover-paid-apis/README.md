# discover-paid-apis

**Find a paid API in the Lightning Enable registry, with Amazap as an additional source, compare what you'd get, then try one with a single bounded purchase.**

Services that charge per call over Lightning are listed in more than one
place. This skill searches the Lightning Enable registry first, and Amazap as
an additional source:

- the **Lightning Enable registry**, a public list of APIs that publish an
  [L402](https://github.com/lightninglabs/L402) manifest, each paid directly
  from your own wallet; and
- **[Amazap](https://amazap.com)**, a separate marketplace where agents
  search pay-per-call APIs and digital services and buy calls with prepaid
  Amazap credits.

Every result is labeled with its source. Amazap is an extra source, not a
replacement for the registry, and it's optional. It's a separate product from
a collaborator in the Lightning ecosystem; Lightning Enable doesn't set its
prices, fees, credits, terms, or ranking.

## Why it's interesting

- **You see the price before anything moves.** Searching, reading a listing,
  and quoting are free. The only payment is one trial you approved, at the
  price you saw.
- **Two ways to buy, explained before you choose.** A registry result is paid
  directly over L402 from your connected wallet: the invoice amount goes to
  the API's seller, any Lightning routing fee is paid on top, the preimage is
  the proof of payment, Lightning Enable's spending controls apply, and no
  Amazap account or credits are needed. An Amazap listing is bought with
  Amazap credits, at Amazap's all-in price, under its terms and limits, with
  Amazap's own trust signals and purchasing features, such as re-crediting a
  failed paid call. The skill never ranks or hides a row for its source; you
  make the final choice.
- **Signals, as each source reports them.** Registry rows show the price, the
  endpoint count, the manifest, the OpenAPI document for a Lightning Enable
  proxy, and how many calls your session budget and wallet balance cover.
  Amazap rows show Amazap's trust label, quoted as returned, its health, paid
  track record, and whether they can be bought now. A signal a source doesn't
  report reads "not reported by this source", which is neutral, never a
  warning. A paused, degraded, or failing row is shown but never bought, and
  a row Amazap hides from search is left out.
- **The right cap for the right wallet.** An Amazap buy spends Amazap credits,
  under your cap and Amazap's account limits. A registry result is paid from
  your Lightning Enable MCP wallet, under your cap and the MCP budget. The
  MCP budget never bounds an Amazap buy, and Amazap's limits never bound a
  direct payment. The skill tells you which cap applies before it buys.
- **It ends with a receipt:** the sats charged, what's left, the listing, an
  order id or payment hash, and whether the service delivered.

## How it works

1. **Ask** what outcome you need, the most one trial may cost, and any limits
   on providers or data.
2. **Check the tools.** It reads `budget action=status` and `get_balance` for
   the direct path, then notes whether your host lists Amazap's tools. When
   Amazap's tools are listed, it reads your Amazap credits and current account
   limits from Amazap.
3. **Search** the registry with `discover_api` first, then Amazap as an
   additional source, unless you leave it out: its `search_catalog` when your
   host lists it, otherwise its public products API. Searching never spends.
4. **Compare** at most five labeled candidates, say how each would be bought,
   and recommend one, with a one-sentence reason drawn from its fit, a clear
   specification, and the signals its own source reports. When the same
   service is in both sources, both rows are shown with their own price and
   way to buy, and you pick the row. Paused, degraded, or failing rows are
   shown, not bought; hidden rows are dropped.
5. **Read the details, unpaid:** a registry API's manifest, or an Amazap
   listing's input schema.
6. **Quote** the exact price, and state which cap applies. For an Amazap
   listing that's the all-in total. For a registry result it's the invoice
   amount, which your cap and the MCP budget count; any Lightning routing fee
   is paid on top, within your wallet's fee limit. Over the cap, nothing is
   bought.
7. **One trial,** after your yes: `access_l402_resource` for a registry
   result, with `max_sats` set to the listed price, or Amazap's `buy`. On the
   Amazap path, the same yes accepts Amazap's current terms. If an Amazap
   quote went stale, or a registry invoice costs more than the listed price,
   nothing is charged: it shows you the new price and asks again.
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
  explicit yes, at the price you saw. Never several paid calls to compare
  services.
- A quote over your cap is refused, and nothing is bought.
- A stale quote is never bought on the old yes: you see the fresh total and
  say yes again. A registry invoice above the listed price is never paid;
  you see the real price and decide again.
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
  Amazap surfaced directly. That rule covers listings Amazap surfaced, never a
  result the registry returned, which is its own candidate with its own
  price. Direct payment is for a registry result or a URL you already have;
  to pay a URL you already have, use
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
[`producer-setup`](../producer-setup/), which publishes to the Lightning
Enable registry.
