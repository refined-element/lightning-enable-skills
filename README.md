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

### 🫙 `restock-from-photo`

Show a photo of a product you own and say *"I'm running low"* — the agent
identifies it, confirms with you, and reorders it over Lightning via L402,
then hands back a claim link to finish shipping.

- Photo → product identification (Claude is natively multimodal).
- Real L402 purchase: `402 Payment Required` → pay the invoice from your MCP
  wallet → preimage → order placed.
- Human stays in control: it always confirms before spending, respects your
  wallet budget, and never invents addresses.
- Works today against the example stores **Great Ghee** (`greatghee`) and
  **Salt of the Earth / SOTE** (`drinksote`); add your own in
  [`references/stores.md`](skills/restock-from-photo/references/stores.md).

See [`skills/restock-from-photo/SKILL.md`](skills/restock-from-photo/SKILL.md).

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

This repo is meant to grow. Candidate skills (PRs / suggestions welcome):

- **`pantry-watch`** — periodically check a shopping list and reorder staples
  when you confirm.
- **`pay-per-call-research`** — answer a question by buying exactly the paid
  data it needs over L402 (FRED, market data, etc.) and citing it.
- **`api-meter-guard`** — watch an L402 API spend and alert / cap before a
  budget blows.
- **`agent-vending`** — let your agent *sell* a resource over L402 (producer
  side), not just buy.

## License

MIT — see [LICENSE](LICENSE). Built by [Refined Element, LLC](https://refinedelement.com).
Part of the [Lightning Enable](https://www.lightningenable.com) ecosystem.
