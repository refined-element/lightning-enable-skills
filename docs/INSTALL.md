# Installing these skills

A skill is not a library. It is a set of instructions your agent loads and
acts on, and several of these skills can spend money from a wallet. So the
install flow treats a skill file the way you would treat a script you are
about to run as yourself: pinned to one immutable version, checked against
hashes you reviewed, and never dropped into your agent's skills folder until
after it checks out.

Three commands, in order. Nothing is installed until the third.

```bash
# 1. Stage the pinned commit. The commit comes from the manifest, so there is
#    exactly one version you handle: the one you checked out and reviewed.
python3 tools/install_skills.py fetch \
    --manifest manifests/<RELEASE_SHA>.json \
    --staging ./le-skills-staging

# 2. Check the whole bundle against a manifest you already have locally.
python3 tools/install_skills.py verify \
    --manifest manifests/<RELEASE_SHA>.json \
    --staging ./le-skills-staging

# 3. Copy verified local files into your skills folder.
python3 tools/install_skills.py install \
    --manifest manifests/<RELEASE_SHA>.json \
    --staging ./le-skills-staging \
    --dest ~/.claude/skills \
    --skill agent-wallet-setup
```

`<RELEASE_SHA>` is the commit you checked out; `ls manifests/` in that checkout
shows it. `--commit <sha>` is still accepted on `fetch` if you want to assert it
explicitly, and is required if you pass no manifest — a branch name, a tag or a
short SHA is refused either way.

`--skill` is repeatable; `--all-skills` installs every skill the manifest
covers. `status --dest ~/.claude/skills` prints what is installed and which
commit each skill came from.

## Why it is shaped like this

**The commit must be a full SHA.** `main` is mutable: whoever can push to it
can change what your agent does, after you reviewed it, without touching your
machine. `HEAD`, `latest`, a tag and an abbreviated SHA are all refused for the
same reason — each can be repointed. A 40-character SHA names one tree of
bytes forever. Taking it from the manifest rather than the command line keeps
that property and removes a value you could paste wrong.

**Links inside skill files are pinned too.** A hash-verified `SKILL.md` that
says *"follow the rules at ‹URL on main⁠›"* is not pinned in any useful sense —
and several of these skills did exactly that about money-spending rules. Every
link from this repository to itself, in `skills/**/*.md` and `references/*.md`,
now names a commit. A test fails the build if one goes back to a branch.

**Staging is not your skills folder.** The download lands in a directory you
name, and the installer refuses a staging path that has a `skills` component
under an agent-configuration directory — `~/.claude/skills`,
`~/.claude/plugins/<plugin>/skills`, `~/.config/claude/skills`, `.cursor/skills`
and so on. Unverified instructions must never sit somewhere an agent might pick
them up mid-check. This is a blocklist, not an exhaustive one: it cannot know
every host's layout, so choose a staging directory well away from your agent
config rather than relying on the check to catch it.

**The manifest has to be local.** `--manifest` takes a file path; a URL is
refused outright. This is the part that is easy to get wrong: downloading a
manifest and the files it describes from the same mutable ref is not
verification. One push changes both, and the hashes still agree. The manifest
is only worth anything if it is a copy you reviewed and hold.

**Verification is whole-bundle and fails closed.** Every file in the manifest
must be present with the exact SHA-256 recorded; any file in the bundle roots
that the manifest does *not* name is refused as unexpected; symlinks, FIFOs,
devices, unsafe paths and traversal attempts are refused. One wrong byte in one
`SKILL.md` stops the entire install, including for skills you did not ask for —
the bundle is reviewed as a unit. When it refuses, nothing is written to the
destination at all.

**Validation never runs what it is validating.** It opens files in binary mode
and hashes them. The installer starts no subprocess, imports nothing from
staging, and has no `exec`/`eval`/`compile`/`pickle` path.
`tests/test_install_skills.py::test_installer_never_executes_staged_code` pins
that as a source guard.

**Installing reads only verified local files.** Step 3 re-runs the full
verification itself — it does not trust that you ran step 2 — and then copies.
It opens no connection.

**Updates are a decision, not a refresh.** Each installed skill carries a
`.lightning-enable-install.json` receipt naming its commit. Re-running with the
same commit is a no-op. A manifest pinning a *different* commit is refused
until you pass `--allow-update`, which is you saying you reviewed the new
version. There is no "check for updates" anywhere in this tool; it never
contacts GitHub during install.

**Drift in an installed skill is checked against the manifest, not the
receipt.** The receipt says *which* commit is installed; the manifest says what
that commit contains. That split matters: the receipt sits inside the directory
it describes, with the same permissions as the files it vouches for, so anything
able to edit a `SKILL.md` could edit a digest beside it. The check is also
set-exact in both directions — a changed file, a missing file **and an added
file** are all drift. Added files are the sharp case: the report skill's helper
scripts import each other from their own directory, so a planted
`__pycache__/*.pyc` could be loaded in place of a verified `.py`. `--force`
always re-copies the whole directory, which is what makes "restores the verified
copy" true: planted files are removed, not merely overwritten.

**A multi-skill install is all-or-nothing.** Every per-skill refusal is decided
before the first file is copied, so a refusal on the third skill cannot leave
the first two already replaced.

## Verifying the installer itself

The installer is the thing doing the verifying, so it cannot be its own root of
trust: a replaced installer would simply report success. Two controls, and it is
worth being precise about what each one buys you.

**Out of band, once, before the first run.** Check out the pinned commit, then
hash the installer with a tool you already trust:

```bash
git clone https://github.com/refined-element/lightning-enable-skills
cd lightning-enable-skills
git checkout eebb4163519cf23bef592a44e453809fc9f79b10   # the commit, not main
sha256sum tools/install_skills.py
```

Compare with the digest in [`manifests/README.md`](../manifests/README.md),
and read the file — it is one stdlib module, and it is short enough to read.
This is the real control, and it is the one step nothing can do for you.

**At runtime, as a cross-check.** Every manifest records the SHA-256 of the
installer it was reviewed alongside, and `verify`/`install` refuse to run if
this installer does not match. That catches the ordinary mistake — an installer
and a manifest from two different versions — not a deliberately modified
installer, which could skip the check.

## Reviewing a manifest

A manifest is a deterministic function of a checkout. That is what makes it
reviewable: regenerate it and diff.

```bash
git checkout <sha>
python3 tools/make_manifest.py --checkout . --commit <sha> > /tmp/rebuilt.json
diff /tmp/rebuilt.json manifests/<sha>.json
```

An empty diff means the manifest describes that commit and nothing else. Then
read the diff of the *bundle* against the version you are already running:

```bash
git diff <old-sha> <new-sha> -- skills references
```

That diff is the thing to review. It is instructions your agent will follow.

## Working offline, or on a machine without network access

`fetch --archive <file.tar.gz>` stages from a local archive instead of
downloading, with the same member-by-member checks. Download
`https://codeload.github.com/refined-element/lightning-enable-skills/tar.gz/<sha>`
on one machine, carry it over, and `verify` against your local manifest on the
other. The verification is identical either way — it compares against the
manifest, not against where the bytes came from.

## What this does not protect against

Stated plainly, because a security control you misunderstand is worse than one
you do not have:

- **A commit you reviewed and approved that is itself malicious.** Pinning
  guarantees you get the bytes you reviewed. It says nothing about whether
  reviewing them was enough.
- **A compromised installer on first use.** Covered only by the out-of-band
  `sha256sum` above. There is no code signing here, and adding signing
  infrastructure was deliberately out of scope.
- **Anything your agent host does on its own.** If your host fetches or syncs
  skills from a remote source by itself, this installer never sees it. It
  manages files in the destination directory you name, and nothing else. Check
  your host's own skill-loading behavior; the installer cannot constrain it.
- **Changes after install.** The installer *detects* drift the next time it
  runs, against the manifest and set-exactly (see above). It is not a running
  integrity monitor: nothing stops another process from editing an installed
  `SKILL.md`, and anything that can write that directory can also write it
  again after a `--force` repair. Detection plus repair is what this gives you,
  not prevention.
- **Shared reference files are fetched, not installed.** `references/` is in
  the manifest and is hash-checked in staging, but only `skills/<name>/` is
  copied to your skills folder. The `SKILL.md` files cite those references by
  URL, and those URLs are now pinned to a commit — so the agent reads reviewed
  bytes, but it does read them over the network at that moment. If GitHub is
  unreachable the citation cannot be followed; a pinned URL cannot serve
  different content.
- **One link still points at a branch**, in
  `skills/agent-wallet-setup/SKILL.md`: the `mcpb/` folder of the separate
  `lightning-enable-mcp` repository. It is left deliberately. Pinning a commit
  in a repository this manifest does not cover would pin bytes nobody reviewed
  here, which is worse than naming the branch openly. It points at an installer
  bundle for a human to download, not at rules an agent applies.
- **The MCP server and the wallet.** Spend limits, the confirmation channel and
  the auto-approve threshold live in the Lightning Enable MCP and your
  `~/.lightning-enable/config.json`, not here. This flow changes nothing about
  them; the controls described in the repository README's safety model still
  apply exactly as before.
