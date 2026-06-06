# lightning-enable-skills

Inventive [Claude Skills](https://support.claude.com/en/articles/12512180-use-skills-in-claude)
that put **agentic commerce** to work over Bitcoin Lightning + the
[L402 protocol](https://github.com/lightninglabs/L402), powered by the
[Lightning Enable MCP](https://github.com/refined-element/lightning-enable-mcp).

The idea: an AI agent doing **real economic work** — paying per-call,
account-lessly, with a human in the *confirmation* loop, not the payment
plumbing. These are small, fun, genuinely useful demonstrations of what that
unlocks.

## Skills

| Skill | What it does |
|---|---|
| 🫙 **[restock-from-photo](skills/restock-from-photo/)** | Photo of a product + "I'm running low" → identify → confirm → **reorder** over L402 → claim link. |
| 📚 **[cited-answer](skills/cited-answer/)** | Answer a question by **buying** exactly the paid data it needs over L402, cite every figure, show the sats receipt. |
| 🏷️ **[sell-this](skills/sell-this/)** | Turn a resource into a **paid endpoint** — mint an L402 paywall, verify payment, then deliver. (Producer side.) |
| 📊 **[l402-meter](skills/l402-meter/)** | A running **satoshi meter + guardrail** for an agent's spend — warns at 80%, stops at 100%. |
| 🔁 **[standing-order](skills/standing-order/)** | **Recurring restock** over Lightning — no card on file, a human yes every cycle. |
| 🎁 **[gift-it](skills/gift-it/)** | Buy a product as a **gift** and ship it to someone else, paid over Lightning. |
| 🤝 **[negotiate-and-buy](skills/negotiate-and-buy/)** | **Agent-to-agent commerce**: discover another agent's service over Nostr, vet it, agree terms, settle over Lightning. |

Each skill folder has a human-facing `README.md` (what it is) and an agent-facing
`SKILL.md` (the instructions Claude loads).

**Buy + sell, end to end:** `cited-answer` / `restock-from-photo` / `standing-order`
are the buyer side; `sell-this` is the seller side; `negotiate-and-buy` is two
agents transacting with each other; `l402-meter` keeps any of them honest about
spend.

## What works where

| Surface | Status | Why |
|---|---|---|
| **Claude Code / Desktop** | ✅ Works now | Has a shell (to run the helper script) + the local Lightning Enable MCP wallet. |
| **Claude mobile app** | ⏳ Not yet | Mobile only supports *remote* MCP connectors and can't run scripts. The logic must move into a hosted MCP tool. See [`docs/mobile-readiness.md`](docs/mobile-readiness.md). |

## Install

Skills live in `~/.claude/skills/` (personal, all projects) or `.claude/skills/`
(per-project). For example:

```bash
git clone https://github.com/refined-element/lightning-enable-skills
cp -r lightning-enable-skills/skills/restock-from-photo ~/.claude/skills/
```

Then connect the [Lightning Enable MCP](https://github.com/refined-element/lightning-enable-mcp)
with a funded wallet, share a product photo, and say you're running low.

## How a skill works (30 seconds)

A skill is a folder with a `SKILL.md` (YAML frontmatter + instructions) and
optional scripts/reference files. Claude reads every skill's `description`
up front; when your request matches, it loads that skill's full body on demand
(**progressive disclosure**). Deterministic work goes in scripts; judgment
stays in the model.

## Safety model

Every skill here that spends money follows the same rules:

- **Explicit confirmation before any payment.** No silent spending.
- **Budget-aware.** Honors the MCP wallet's `get_budget_status`.
- **Intent-driven.** The agent never decides *for* you that you need to buy.
- **No secrets in this repo.** Catalog/checkout endpoints are public; payment
  authority lives only in your local MCP wallet.

## Ideas / roadmap

This repo is meant to grow. Candidate next skills (PRs / suggestions welcome):

- **`discover-and-try`** — "find me a weather/health/finance API I can use" →
  discover on the L402 registry, show what you can afford, run a sample paid call.
- **`pantry-from-receipt`** — photograph a grocery receipt or shelf → match items
  to L402 stores → offer to reorder what you're low on.
- **`api-arbitrage`** — compare multiple L402 providers for the same data, buy
  the cheapest, show the savings.

## License

MIT — see [LICENSE](LICENSE). Built by [Refined Element, LLC](https://refinedelement.com).
Part of the [Lightning Enable](https://www.lightningenable.com) ecosystem.
