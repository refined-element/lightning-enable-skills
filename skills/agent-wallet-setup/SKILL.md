---
name: agent-wallet-setup
description: >-
  Take an agent from nothing installed to a verified, budget-capped Lightning
  wallet that pays L402 APIs: install the Lightning Enable MCP (Model Context
  Protocol) server on the agent's host (Claude Code, Claude Desktop, Cursor,
  Codex CLI, Hermes), register it, connect a wallet (NWC, Strike, or LND),
  tighten the spend ceiling, and prove the loop with a 1-sat test payment. Use
  when the user wants their agent to BUY or PAY over Lightning and the MCP or the
  wallet is not set up yet ("set up my agent to pay over Lightning", "install the
  Lightning Enable MCP", "give Claude Code a Lightning wallet", "connect my
  wallet", "my agent needs to pay L402 APIs"). Do NOT use to sell an API (use
  producer-setup), to pay a specific URL once the wallet works (use
  pay-l402-anywhere), or for Lightning Enable account billing (use
  lightning-enable-account). The human supplies the wallet credential, a rough
  balance, and a spend ceiling.
---

# Agent wallet setup

The buyer side of the agent economy, in one skill: no MCP server installed, then
an agent that pays L402 challenges from a wallet the human chose, inside a
ceiling the human set, proven by one real 1-sat payment. The human makes three
decisions: which wallet, roughly how much it holds, and how much the agent may
spend. Everything between those decisions is a shell command or a tool call.

**Lightning Enable does not hold funds; the wallet facilitates custody and
settlement.** The MCP server runs on the human's own host and talks to the
wallet the human configures. No private keys reach Lightning Enable.

This skill loads before the MCP server exists, so steps 1 to 3 are shell
commands you run in the host (or hand to the human). Tool calls start at step 4.

## What is automated, and what is not

**Automated:** detecting the host, the install and registration commands, the
wallet report, connecting an NWC (Nostr Wallet Connect) wallet, the balance
check, tightening the budget, the 1-sat self-test, and the hand-off summary.

**Not automated. The human supplies or does these:**

- **A wallet that already exists and holds sats.** One of: an NWC connection
  string from Alby Hub, CoinOS, or CLINK; a Strike API key; or a Lightning
  Network Daemon (LND) node's REST host and macaroon. This skill does not create
  or fund a wallet.
- **A spend ceiling,** per payment and per session, in sats.
- **Restarting the host app.** You can't restart the app you run inside. The
  human restarts it after registration and after any wallet change.
- **Placing a credential** in an environment variable or the config file, when
  the human would rather it never enter the chat.

## What you need

- A host that runs MCP servers over stdio: Claude Code, Claude Desktop, Cursor,
  Codex CLI or another [agentskills.io](https://agentskills.io) host, or Hermes.
- One runtime: .NET 8, 9, or 10 for the NuGet tool; Python 3.10 or later for
  `pip` or `uvx`; or Docker.
- A wallet that returns Lightning **preimages**: NWC (Alby Hub, CoinOS, CLINK),
  LND, or Strike. OpenNode does not return preimages and can't pay L402
  challenges. Neither can Primal's NWC.
- Tools this skill uses, once the server is installed:
  - `setup_wallet`: reports the configured wallet, or connects one over NWC.
  - `get_balance`: the real funds.
  - `budget`: `action="status"` reads the limits, `action="tighten"` lowers them.
  - `test_l402_payment`: pays a public 1-sat L402 endpoint end to end.
  - `receipts`: the payment log, for the hand-off.

Argument names below are the Python server's `snake_case`. The .NET server takes
the same arguments in `camelCase`: `nwc_connection_string` →
`nwcConnectionString`, `per_request` → `perRequest`, `per_session` →
`perSession`, `confirmation_nonce` → `confirmationNonce`. Response fields are
`camelCase` in both.

## Flow

### 0. Human checkpoints

Ask for all of this in one message, then **stop and wait**. Step 6 moves money,
and steps 1 to 3 install software on the human's machine.

1. **Wallet.** "Which wallet should I pay from: an NWC connection from Alby Hub,
   CoinOS, or CLINK; a Strike API key; or your own LND node?" A small, dedicated
   wallet is the right shape. Never the human's main funds.
2. **Balance.** "About how many sats does it hold?" The self-test needs only a
   few sats, but a wallet at zero fails it.
3. **Ceiling.** "What is the most I may spend in one payment, and in one
   session?" In sats.
4. **Permission.** "May I install the Lightning Enable MCP server, and spend
   about 1 sat on a test payment to prove the wallet works?"

Say plainly how credentials travel, because **every credential is a secret:**

- The human puts a Strike key or an LND macaroon in the host's MCP
  configuration or an environment variable, or runs the registration command
  that carries it themselves.
- For NWC, the human either pastes the connection string once so you can pass it
  to `setup_wallet`, or writes it into `~/.lightning-enable/config.json` by hand
  so it never enters the chat at all.
- You never echo a credential, never write one into a summary, a repo file, a
  commit, or a command you run, and you report `<set>` or `<not set>` instead.
- If a Strike key or an LND macaroon lands in the chat, do not repeat it. Tell
  the human it is in the transcript so they can decide whether to rotate it.

### 1. Detect the host and pick the registration path

If you can't tell which host you are running in, ask. Then check the runtimes
the human has, so you pick an install path that works:

```bash
dotnet --version     # .NET SDK or runtime, for the NuGet tool
python3 --version    # or: python --version, for pip / uvx
uvx --version        # uv's no-install runner
docker --version
```

Every host registers the same server: the command `lightning-enable-mcp` once
installed (.NET tool or `pip`), or `uvx lightning-enable-mcp` for Python with no
install. Credentials and options go in as environment variables.

**Claude Code.** Register with `claude mcp add`:

```bash
# Installed (.NET tool or pip)
claude mcp add --transport stdio lightning-enable -- lightning-enable-mcp

# Python, no install
claude mcp add --transport stdio lightning-enable -- uvx lightning-enable-mcp
```

Add `--env NAME=value` before the `--` for each environment variable, for
example `--env LIGHTNING_ENABLE_TOOL_PROFILE=lite`. When the value is a
credential (`--env STRIKE_API_KEY=...`), give the human the command to run
themselves, so the key never passes through your shell history or the
transcript. A project-scoped `.mcp.json` in the project root works too, with
the same `command`, `args`, and `env`. Never commit it with a key in it.

**Claude Desktop.** It does not use `claude mcp add`. It reads
`claude_desktop_config.json`:

- **macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows:** `%APPDATA%\Claude\claude_desktop_config.json`
- **Linux:** `~/.config/claude/claude_desktop_config.json`

```json
{
  "mcpServers": {
    "lightning-enable": {
      "command": "uvx",
      "args": ["lightning-enable-mcp"],
      "env": {
        "NWC_CONNECTION_STRING": "<the human fills this in>"
      }
    }
  }
}
```

With an installed package, set `"command": "lightning-enable-mcp"` and drop
`args`. If the host can't find the command, use its full path. For a one-click
install with no JSON to edit, the MCP repo ships an MCPB bundle (see the
[`mcpb/` folder](https://github.com/refined-element/lightning-enable-mcp/tree/main/mcpb)):
the human drags the `.mcpb` file into Claude Desktop's **Settings → Extensions**,
and Claude Desktop asks for the wallet credentials in its own settings screen.

**Cursor.** Same JSON shape, in `.cursor/mcp.json` (this project) or
`~/.cursor/mcp.json` (every project), or through **Cursor Settings → Tools &
MCP → New MCP Server**. Keep credentials in the global file, never in the
project file. Cursor needs a full restart, not a closed window.

**Codex CLI and other agentskills.io hosts.** Add a stdio MCP server named
`lightning-enable` to that host's MCP configuration, with the same command,
arguments, and environment variables as above. Lightning Enable does not
document each host's config file, so take the location from the host's own MCP
documentation.

**Hermes.** Follow
[Run L402 anywhere: Hermes + NWC](https://docs.lightningenable.com/products/agentic-commerce/hermes-nwc-setup).
The short version, with the wallet already in `~/.lightning-enable/config.json`:

```bash
hermes mcp add lightning-enable --command lightning-enable-mcp
hermes mcp test lightning-enable
```

**Docker.** Use `"command": "docker"` with
`"args": ["run", "--rm", "-i", "refinedelement/lightning-enable-mcp:latest"]`.
A container sees neither the host's environment nor `~/.lightning-enable/`
unless they are passed in: `-e NAME` in `args` forwards one variable, and a
volume mount shares the config directory.

### 2. Install

Pick one, with the human's yes from step 0. None of these carries a credential,
so you can run them yourself:

```bash
dotnet tool install -g LightningEnable.Mcp               # .NET 8, 9, or 10
pip install lightning-enable-mcp                         # Python 3.10 or later
docker pull refinedelement/lightning-enable-mcp:latest   # Docker
```

- **`uvx` (Python):** needs no install step. Do not run
  `uvx lightning-enable-mcp` yourself: it starts the server, which waits for a
  host on standard input and never returns. Put it in the host config from
  step 1 and let the host launch it.
- **.NET missing:** the SDK is at https://dot.net/download.
- **`uvx` missing:** `pip install uv`, or
  `curl -LsSf https://astral.sh/uv/install.sh | sh`.
- **NWC on Python:** the base install covers NWC on every platform, Windows
  included, with no compiler. Older docs say to install
  `lightning-enable-mcp[nwc]`; that extra is an empty alias kept so old commands
  still resolve, so either command works.
- **Python older than 3.10:** the package refuses to install. Use 3.10 or later.

To upgrade later:

```bash
dotnet tool update -g LightningEnable.Mcp
pip install --upgrade lightning-enable-mcp
docker pull refinedelement/lightning-enable-mcp:latest
```

For `uvx`, add `--refresh` before `lightning-enable-mcp` in the host config's
`args`, restart the host once, then take it out again.

At startup the server checks for a later release and prints the upgrade command
to its console (stderr) when one exists.

### 3. Register, restart, verify

Run the registration from step 1, then ask the human to restart the host.

In some hosts a restart ends this conversation. Before you ask for it, tell the
human what to say afterward ("continue the agent wallet setup at step 4"), so
the next session picks up where this one stopped.

After the restart, confirm the server is connected:

- **Claude Code:** `/mcp` lists `lightning-enable` as connected.
- **Cursor:** **Cursor Settings → Tools & MCP** shows `lightning-enable` with a
  green status.
- **Hermes:** `hermes mcp test lightning-enable` reports the tools discovered.

Then check that `setup_wallet`, `get_balance`, `budget`, and `test_l402_payment`
are among your tools. Never state how many tools the server has.

**Tool profiles.** `LIGHTNING_ENABLE_TOOL_PROFILE` picks how much of the tool
surface the server lists. `standard` is the default and lists every tool,
including the selling and account tools. `lite` lists only `setup_wallet`,
`access_l402_resource`, `pay_invoice`, `get_balance`, `budget`, and `receipts`,
which is enough for an agent that only pays. `lite` does not list
`test_l402_payment` or `discover_api`, and most hosts only offer the model the
tools a server lists, so stay on `standard` through this setup. Switch to `lite`
after step 6 if the human wants the smaller context footprint.

### 4. Connect the wallet

Call `setup_wallet` **with no arguments first**:

```
setup_wallet()
```

- **A wallet is configured:** it reports `wallet` (the provider), `source` (an
  environment variable or the config file), and `configuredWallets`. It never
  reports the credential. If the provider is OpenNode, stop: OpenNode can't pay
  L402 challenges, so ask the human for an NWC, Strike, or LND wallet.
- **No wallet yet:** the same call returns the setup options. Continue with the
  wallet the human chose in step 0:
  - **NWC:** pass the string the human gave you:
    `setup_wallet(nwc_connection_string="nostr+walletconnect://...")`. The tool
    validates the string, probes the live wallet, and only then writes it to
    `wallets.nwcConnectionString` in `~/.lightning-enable/config.json`, with the
    file's permissions restricted to the human's user. It reports the wallet's
    declared `methods`, `balanceSats`, and `canPayL402`. If the human wrote the
    string into the config file by hand instead, call `setup_wallet()` again
    after the restart to confirm it.
  - **Strike:** the human sets `STRIKE_API_KEY` (from
    https://dashboard.strike.me) in the server's environment, using the step 1
    command or config, and restarts the host.
  - **LND:** the human sets `LND_REST_HOST` (`host:port`) and
    `LND_MACAROON_HEX`. For a self-signed node certificate, `LND_TLS_CERT_PATH`
    pins TLS to that certificate; `LND_SKIP_TLS_VERIFY=true` is the escape
    hatch, not the recommendation. See
    [LND setup](https://docs.lightningenable.com/products/agentic-commerce/lnd-setup).
- **It refuses to write the config:** an environment variable already selects a
  wallet, and the server would ignore the file. `source` names the variable. Ask
  the human to unset it and call `setup_wallet` again, or to keep the wallet the
  environment selects.
- **The probe fails or times out:** the relay is unreachable, the connection was
  revoked in the wallet app, or the secret is wrong. Nothing is saved. Ask the
  human to check the connection in the wallet app, or try another NIP-47 wallet.
- **"That is not a valid NWC connection string":** the error names the bad
  field without quoting the string. Ask the human to copy the whole string
  again, relay and secret included.
- **`canPayL402: false`:** the wallet did not declare `pay_invoice`. Ask the
  human to check what this connection may do in the wallet app.

**Which wallet wins.** When several are configured, the order is **LND > NWC >
Strike > OpenNode**, and an **environment variable beats the config file**.
`WALLET_PRIORITY` (environment) or `wallets.priority` (config file) moves one
configured wallet to the front.

After `setup_wallet` writes the config, the human restarts the host again. Then
run `setup_wallet()` once more and confirm the provider and source are the ones
the human expects.

### 5. Read the funds, set the leash

```
get_balance()
budget(action="status")
budget(action="tighten", per_request=<ceiling per payment>, per_session=<ceiling per session>)
```

State the result back in plain terms: "the wallet holds about 4,800 sats; I am
capped at 50 sats a payment and 500 a session."

The budget has two layers. Explain both:

1. **The operator's limits** live in `~/.lightning-enable/config.json` and are
   read-only at runtime. The `limits` block takes USD caps (`maxPerPayment`,
   `maxPerSession`), sats caps (`maxPerPaymentSats`, `maxPerSessionSats`), and
   `autoApproveSats`; where both denominations are set, the stricter cap wins.
   The `tiers` block (`autoApprove`, `logAndApprove`, `formConfirm`, in USD)
   decides which payments need a human confirmation code. The file format is in
   the MCP README's
   [Spending limits](https://github.com/refined-element/lightning-enable-mcp#spending-limits)
   section. You may draft a snippet with the human's numbers; the human saves
   it. Never raise a limit in that file yourself.
2. **The runtime caps** that `budget(action="tighten")` sets. They only go down,
   never above the operator's limits, and they last until the server restarts.
   Tighten again after any restart.

`budget(action="status")` reports which denomination is binding
(`bindingDenomination`) and whether a BTC price was available. When every price
source is down, a USD limit can't be checked, so payments under it are refused:
the budget fails closed. Sats caps keep working through an outage, and
`autoApproveSats` lets payments at or under it through without a code.

The self-test in step 6 asks the budget for up to 10 sats. A per-payment cap
under 10 sats blocks it, so tighten to 10 or more first, or run step 6 and then
tighten lower.

**Stop here if the balance is zero.** The self-test fails with a less obvious
error.

### 6. Prove it: one 1-sat L402 payment

This is the one paid step. It needs the yes from step 0.

```
test_l402_payment()
```

It pays the public 1-sat L402 endpoint at
`https://api.lightningenable.com/l402/test/ping` end to end: 402, pay the
invoice, receive the preimage, retry with the credential, 200. The URL is fixed
inside the tool and the spend is capped at 10 sats, so it can't be pointed at
anything else.

- **`test: "passed"`:** the wallet works. It reports `amountSats` and
  `walletWorking: true`.
- **`test: "needs_confirmation"`:** the budget tiers want a human code for this
  amount. The server sent the code to the human, never to you. Ask the human for
  it, then call `test_l402_payment(confirmation_nonce="<code>")`. Never guess a
  code.
- **`test: "failed"`:** read `reason` and repeat `howToFix` to the human:
  `no_wallet`, `no_preimage`, `insufficient_funds`, `budget_block`, `network`,
  `rate_limited`, or `unknown`.
- **`test: "inconclusive"`:** usually the test invoice was already paid in the
  last minute (the endpoint reuses it briefly to prevent a double charge). Wait
  a minute and run it once more. Don't loop.

### 7. Hosted or headless hosts

A payment above the auto-approve threshold needs a code a human reads back to
you. On a laptop the code goes to the server's console (stderr). On a hosted
server (a claude.ai connector, a container, a fleet) nobody may be watching
stderr, so the operator picks a **confirmation channel** with
`LIGHTNING_ENABLE_CONFIRMATION_CHANNEL` or `confirmation.channel` in the config
file:

| Channel | Above the threshold |
|---|---|
| `stderr` (default) | The code prints to the server console. |
| `refuse` | The payment is refused, and no code is minted. |
| `webhook` | The pending confirmation is POSTed, HMAC-signed, to the operator's URL. |
| `file` | The same JSON line is appended to a file the operator tails. |

`LIGHTNING_ENABLE_HOSTED=1` declares a hosted deployment: with no channel set
and no terminal attached, the server refuses over-threshold payments instead of
printing a code nobody reads. Two rules hold on every channel: **the code never
reaches you**, and **a delivery failure refuses the payment**. Details are in
the MCP README's
[Deploying hosted](https://github.com/refined-element/lightning-enable-mcp#deploying-hosted)
section.

### 8. Hand off

Tell the human, in this order:

- **Where the wallet lives:** the provider and source from `setup_wallet()`,
  stated as "NWC, from the config file" or "Strike, from `STRIKE_API_KEY`",
  never the credential.
- **The caps:** the operator's limits in `~/.lightning-enable/config.json` and
  the runtime caps you set, plus the reminder that runtime caps reset when the
  server restarts.
- **What was spent:** the self-test's `amountSats`. `receipts(source="durable")`
  shows the persistent payment log at `~/.lightning-enable/receipts.jsonl`, and
  `receipts(source="session")` shows this session's payments.
- **How to update the server:** the upgrade command for the install path used
  in step 2.
- **What to do next:**
  - [`pay-l402-anywhere`](../pay-l402-anywhere/) to pay an L402 URL.
  - [`discover-paid-apis`](../discover-paid-apis/) to find a paid API and try it.
  - [`producer-setup`](../producer-setup/) to sell an API over Lightning. If the
    human also wants a Lightning Enable account, that is producer-setup's step 2
    (`create_lightning_enable_account`). Don't run it here.

## What can go wrong

| Symptom | Likely cause | Do this |
|---|---|---|
| The tools don't appear after install | The host was not restarted, the command is not on the host's `PATH`, or the .NET runtime is missing | Restart the host fully. Use the full path to `lightning-enable-mcp`, or switch to `uvx`. Install .NET 8, 9, or 10 from https://dot.net/download. |
| `/mcp` shows the server failed to start | Wrong command or arguments, or a missing runtime | Run `lightning-enable-mcp` (or `uvx lightning-enable-mcp`) in a terminal to see the startup error, then fix the registration. |
| `pip install` refuses the package | Python older than 3.10 | Install Python 3.10 or later, or use the .NET tool. |
| A fresh Python install fails importing `ConstBitStream` | A release before 2.1.0 with `bitstring` 5 | Upgrade to 2.1.0 or later, which pins `bitstring<5`. |
| A Windows guide says NWC needs `pip install lightning-enable-mcp[nwc]` | Older docs | The base install covers NWC on Windows. The extra is empty, so either command works. |
| `setup_wallet` refuses to write the config | An environment variable already selects a wallet, so the file would be ignored | Ask the human to unset the variable `source` names, then call `setup_wallet` again. |
| `setup_wallet` probe fails or times out | Relay unreachable, connection revoked, or wrong secret | Nothing was saved. Check the connection in the wallet app, or try another NIP-47 wallet (Alby Hub, CoinOS, CLINK). |
| `setup_wallet` reports OpenNode | OpenNode is the only wallet configured | OpenNode can't pay L402. Add an NWC, Strike, or LND wallet. |
| `test_l402_payment` fails with `no_preimage` | The wallet paid but returned no preimage | Switch to NWC (Alby Hub, CoinOS, CLINK), LND, or Strike. OpenNode and Primal's NWC can't do L402. |
| `test_l402_payment` fails with `budget_block` | A cap below the test amount, or the session cap is spent | Read `budget(action="status")`. Raise nothing yourself; ask the human to change the config file if needed. A runtime cap resets on restart. |
| A payment is refused during a price outage | USD limits can't be checked without a BTC price | Expected: the budget fails closed. Sats caps plus `autoApproveSats` in the config file keep small payments working. |
| `needs_confirmation` and no human sees a code | The server runs hosted, and the code goes to a console nobody reads | Set a confirmation channel (step 7). With `LIGHTNING_ENABLE_HOSTED=1` and no channel, the server refuses instead. |
| The wallet changed but the agent still uses the old one | The host was not restarted, or an environment variable outranks the config file | Restart the host, then check `source` in `setup_wallet()`. |

## Safety rules

- **Explicit human yes before any spend.** The self-test is the only payment in
  this skill, and it costs about 1 sat.
- **Tighten the budget before the first payment,** not after.
- **Never echo secrets.** NWC connection strings, Strike keys, LND macaroons,
  API keys, macaroons, and preimages never appear in your output, a file you
  write, or a command you run. Report `<set>` or `<not set>`.
- **Never raise a limit.** `budget(action="tighten")` only goes down, and the
  operator's config file is the human's to edit.
- **One L402 payment at a time.** Finish one 402, pay, access cycle before
  starting another.
- **Never guess or relay your own confirmation code.** It comes from the human.
- **Never commit a config file that holds a credential,** and never put one in
  a project-scoped MCP file that others share.

## What this is NOT

- **Not custody.** Lightning Enable does not hold funds; the wallet facilitates
  custody and settlement.
- **Not a wallet.** This skill connects a wallet the human already has. It
  doesn't create, fund, or back one up.
- **Not account signup.** Paying L402 APIs needs no Lightning Enable account.
  Selling does: that is [`producer-setup`](../producer-setup/).
- **Not a spending authority.** The human sets the ceiling. The agent only
  lowers it.

## Example

> User: "Give Claude Code a Lightning wallet so it can pay for APIs. I have an
> Alby Hub with about 5,000 sats. Keep it to 50 sats a payment."
>
> 1. Ask for the wallet, the balance, the per-session ceiling, and permission to
>    install and spend about 1 sat. The human answers: Alby Hub NWC, 500 sats a
>    session, yes.
> 2. `python3 --version` → 3.12. `pip install lightning-enable-mcp`.
> 3. `claude mcp add --transport stdio lightning-enable -- lightning-enable-mcp`.
>    "Restart Claude Code, then say: continue the agent wallet setup at step 4."
> 4. `/mcp` → connected. `setup_wallet()` → no wallet. The human pastes the NWC
>    string; `setup_wallet(nwc_connection_string="...")` → saved, `canPayL402:
>    true`, about 5,000 sats. "Restart once more so the server loads the wallet."
> 5. `get_balance()` → 4,980 sats.
>    `budget(action="tighten", per_request=50, per_session=500)`.
> 6. `test_l402_payment()` → `passed`, 1 sat.
> 7. Hand off: "NWC from the config file, `<set>`. Capped at 50 sats a payment
>    and 500 a session until the next restart. Spent 1 sat. Next:
>    discover-paid-apis to find something worth paying for."
