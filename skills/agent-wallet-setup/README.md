# agent-wallet-setup

**From nothing installed to an agent that pays L402 APIs from a wallet you chose, inside a ceiling you set.**

Before an agent can buy anything over Lightning, three dull things have to be
true: the Lightning Enable MCP (Model Context Protocol) server is installed and
registered with the agent's host, a wallet that returns preimages is connected,
and the agent is on a short budget leash. This skill does all three, then proves
them with one real 1-sat [L402](https://github.com/lightninglabs/L402) payment.

It is the buyer-side twin of [`producer-setup`](../producer-setup/). No Lightning
Enable account is involved: paying L402 APIs needs only a wallet.

## Why it's interesting

- **It knows your host.** Claude Code, Claude Desktop, Cursor, Codex CLI, and
  Hermes each register an MCP server differently. The skill picks the right
  command or config file, and the right install path for the runtime you have
  (.NET, Python, or Docker).
- **Secrets stay out of the chat.** The agent never echoes a wallet credential.
  Strike keys and LND macaroons go into the host's config by your hand; an NWC
  connection string can go either through `setup_wallet` once or straight into
  the config file.
- **Two budget layers, explained.** Your hard limits in
  `~/.lightning-enable/config.json`, which the agent can't raise, and a runtime
  cap the agent can only lower.
- **It ends with proof.** `test_l402_payment` pays a public 1-sat endpoint end
  to end: 402, pay, preimage, 200. A wallet that can't produce a preimage fails
  here, for 1 sat, instead of on a real purchase.

## How it works

1. **Ask first:** which wallet, roughly what it holds, the ceiling per payment
   and per session, and permission to install and spend about 1 sat.
2. **Detect the host** and pick the registration path: `claude mcp add`, a
   `claude_desktop_config.json` entry or the MCPB bundle, `.cursor/mcp.json`,
   the host's MCP config for Codex CLI, or `hermes mcp add`.
3. **Install** with `dotnet tool install -g LightningEnable.Mcp`,
   `pip install lightning-enable-mcp`, `uvx lightning-enable-mcp`, or the
   Docker image.
4. **Register, restart, verify** that the tools appear (`/mcp` in Claude Code).
5. **Connect the wallet** with `setup_wallet`: report first, then connect an NWC
   string, or have you set a Strike or LND credential in the environment.
6. **Set the leash:** `get_balance`, `budget action=status`, then
   `budget action=tighten` to your ceiling.
7. **Prove it:** `test_l402_payment`, about 1 sat.
8. **Hand off:** where the wallet lives, the caps, what was spent, how to
   upgrade, and which skill to use next.

## Requirements

- A host that runs MCP servers over stdio: Claude Code, Claude Desktop, Cursor,
  Codex CLI, or Hermes.
- .NET 8, 9, or 10; or Python 3.10 or later; or Docker.
- A **funded** wallet that returns Lightning preimages: NWC (Alby Hub, CoinOS,
  CLINK), LND, or Strike. OpenNode and Primal's NWC can't pay L402 challenges.
  This skill doesn't create or fund a wallet.

## Try it

> "Set up my agent to pay over Lightning. I have an Alby Hub wallet with about
> 5,000 sats; keep it under 50 sats a payment."

## Safety

- An explicit yes before installing anything and before the 1-sat test.
- The budget is tightened before the first payment. The agent never raises a
  limit, and never edits your limits file without you.
- Credentials are never echoed: the agent reports `<set>` or `<not set>`.
- Confirmation codes for larger payments go to you, never to the agent. On a
  hosted server, pick a confirmation channel or the server refuses those
  payments.
- Lightning Enable does not hold funds; the wallet facilitates custody and
  settlement.

## What it doesn't do

It doesn't create, fund, or back up a wallet, and it doesn't create a Lightning
Enable account. For selling, use [`producer-setup`](../producer-setup/).

## Next

- [`pay-l402-anywhere`](../pay-l402-anywhere/): pay an L402 URL you already have.
- [`discover-paid-apis`](../discover-paid-apis/): find a paid API and try it once.
- [`shop-l402-store`](../shop-l402-store/): buy from an L402 store.
