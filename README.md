# lightning-enable-skills

[![Discord](https://img.shields.io/discord/1405389254892195951?label=community&logo=discord&color=5865F2)](https://discord.gg/rX7NxHY8vx)


Inventive [Claude Skills](https://support.claude.com/en/articles/12512180-use-skills-in-claude)
that put **agentic commerce** to work over Bitcoin Lightning + the
[L402 protocol](https://github.com/lightninglabs/L402), powered by the
[Lightning Enable MCP](https://github.com/refined-element/lightning-enable-mcp).

The idea: an AI agent doing **real economic work** — paying per-call,
account-lessly, with a human in the *confirmation* loop, not the payment
plumbing. These are small, fun, genuinely useful demonstrations of what that
unlocks.

## Skills

The skills target Lightning Enable MCP 2.x and call only the tool names its
default `standard` profile advertises.

### Get started

| Skill | What it does |
|---|---|
| 🔌 **[agent-wallet-setup](skills/agent-wallet-setup/)** | From nothing to a verified paying wallet: install the MCP on your host, connect a wallet, set a spend ceiling, prove it with a 1-sat L402 payment. |
| 🧾 **[lightning-enable-account](skills/lightning-enable-account/)** | Check your Lightning Enable plan and paid-through date, renew in sats with a human yes, understand what a lapse does. |

### Buy

| Skill | What it does |
|---|---|
| ⚡ **[pay-l402-anywhere](skills/pay-l402-anywhere/)** | Pay any L402-gated endpoint from a bounded wallet: discover, confirm, pay per call. The general buyer. |
| 🔭 **[discover-paid-apis](skills/discover-paid-apis/)** | Find paid APIs in the L402 registry, see what you can afford, try one with a single paid call. |
| 📚 **[cited-answer](skills/cited-answer/)** | Answer a question by buying exactly the paid data it needs over L402, cite every figure, show the sats receipt. |

### Sell

| Skill | What it does |
|---|---|
| 🏗️ **[producer-setup](skills/producer-setup/)** | From nothing to a live paid API on your own wallet: connect, sign up over L402, publish, self-test. |
| 🔁 **[create-l402-proxy](skills/create-l402-proxy/)** | Put an existing API behind a paid L402 proxy on an account you already have: receive wallet, proxy, priced routes, publish, self-test. |
| 🏷️ **[sell-this](skills/sell-this/)** | Charge for one resource: mint an L402 challenge, verify payment, deliver. |
| 🤝 **[negotiate-and-buy](skills/negotiate-and-buy/)** | Agent-to-agent commerce, buyer side: discover another agent's service over Nostr, vet it, settle over Lightning. |
| 📣 **[offer-agent-service](skills/offer-agent-service/)** | Agent-to-agent commerce, seller side: publish a service on the agent relay, price it, get paid over Lightning. |

### Build

| Skill | What it does |
|---|---|
| 🧩 **[l402-client-integration](skills/l402-client-integration/)** | Add auto-paying L402 to your own code with `l402-requests` (Python), `L402Requests` (.NET), or `l402-requests` (npm). |
| 🧱 **[l402-server-integration](skills/l402-server-integration/)** | Charge for your own API in-process with `L402Server.AspNetCore` or `l402-express`, no proxy. |
| 🩺 **[l402-compatibility-report](skills/l402-compatibility-report/)** | Check how far an endpoint gets through L402 without paying, then, with your yes, test paid delivery with one capped payment through the Lightning Enable MCP. |

Each skill folder has a human-facing `README.md` (what it is) and an agent-facing
`SKILL.md` (the instructions Claude loads).

**Buy + sell, end to end:** `agent-wallet-setup` gives an agent a bounded wallet,
and `lightning-enable-account` keeps a seller's plan paid in sats. On the buy
side, `pay-l402-anywhere` is the general buyer, `discover-paid-apis` finds
something worth buying, and `cited-answer` is a task-specific buyer. On the sell side, `producer-setup` is how an agent
*becomes* a seller from a standing start, `create-l402-proxy` puts a whole API
behind a paywall on an existing account, and `sell-this` charges for a single
resource. `negotiate-and-buy` and `offer-agent-service` are the two halves of
agents transacting with each other on the Nostr relay. The `l402-*-integration`
skills move the same protocol into your own code, and `l402-compatibility-report`
checks the result: the unpaid challenge first, then, with your yes, one paid
call. Shared rules for those checks live in
[`references/l402-verification-levels.md`](references/l402-verification-levels.md).
After the self-test, `producer-setup`, `create-l402-proxy`, and
`l402-server-integration` can draft an optional listing on
[Amazap](https://amazap.com/sell) that you review and submit yourself; the
rules are in [`references/amazap-marketplace.md`](references/amazap-marketplace.md).
Lightning Enable does not hold funds; the wallet or the payment provider
facilitates custody and settlement.

## What works where

| Surface | Status | Why |
|---|---|---|
| **Claude Code / Desktop** | ✅ Works now | Runs the local Lightning Enable MCP and its wallet; the skills load from your skills folder. |
| **Hermes** (Telegram/Signal/etc.) | ✅ Works now | Runs locally with the MCP wallet **and** bridges to your phone over chat apps — the mobile path *without* a hosted MCP. See [Run L402 anywhere: Hermes + NWC](https://docs.lightningenable.com/products/agentic-commerce/hermes-nwc-setup). |
| **Cursor / Codex CLI** | ✅ Works now | `SKILL.md` follows the [agentskills.io](https://agentskills.io) standard — the same skill file loads unmodified. |
| **Claude mobile app** | ⏳ Not yet | Claude's own mobile app only supports *remote* MCP connectors, and the Lightning Enable MCP runs locally. For mobile, use **Hermes**: see [Run L402 anywhere: Hermes + NWC](https://docs.lightningenable.com/products/agentic-commerce/hermes-nwc-setup). |

## Install

Skills live in `~/.claude/skills/` (personal, all projects) or `.claude/skills/`
(per-project). For example:

```bash
git clone https://github.com/refined-element/lightning-enable-skills
cp -r lightning-enable-skills/skills/agent-wallet-setup ~/.claude/skills/
```

Then ask your agent to set you up to pay over Lightning. `agent-wallet-setup`
installs the [Lightning Enable MCP](https://github.com/refined-element/lightning-enable-mcp),
connects a wallet, sets a spend ceiling, and proves the loop with a 1-sat
payment. Copy any other skill folder the same way.

## How a skill works (30 seconds)

A skill is a folder with a `SKILL.md` (YAML frontmatter + instructions) and
optional scripts/reference files. Claude reads every skill's `description`
up front; when your request matches, it loads that skill's full body on demand
(**progressive disclosure**). Deterministic work goes in scripts; judgment
stays in the model.

## Safety model

Every skill here that spends money follows the same rules:

- **Explicit confirmation before any payment.** No silent spending. When a
  payment is over the MCP's auto-approve threshold, the confirmation code goes
  to the human through the server's confirmation channel (its console by
  default), never to the agent.
- **Budget-aware.** Honors the MCP's spending caps (`budget(action="status")`);
  an agent can tighten them, never raise them.
- **One L402 payment at a time.** Each 402 mints a fresh invoice, so payments
  never run concurrently.
- **Intent-driven.** The agent never decides *for* you that you need to buy.
- **No secrets in this repo.** Payment authority lives only in your local MCP
  wallet. Skills report a wallet string or API key as set or not set, never its
  value.
- **Lightning Enable does not hold funds.** The wallet or the payment provider
  facilitates custody and settlement.

## Ideas / roadmap

This repo is meant to grow. Candidate next steps (PRs / suggestions welcome):

- **`api-arbitrage`**: compare several L402 providers for the same data, buy
  the cheapest, show the savings.
- **A hosted MCP for the Claude mobile app**, so the skills run from Claude's
  own app without a local server.

## Support

If something's broken or not working, email support@lightningenable.com — a real person reads it. For general questions, join the Discord: https://discord.gg/rX7NxHY8vx.
Bug reports and feature requests: open an issue on this repo.

## License

MIT — see [LICENSE](LICENSE). Built by [Refined Element, LLC](https://refinedelement.com).
Part of the [Lightning Enable](https://www.lightningenable.com) ecosystem.
