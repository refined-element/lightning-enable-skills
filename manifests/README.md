# Bundle manifests

One file per released commit, named for that commit. Each one lists the
SHA-256 of every file in the installable bundle — `skills/` and `references/` —
plus the digest of the installer it was reviewed alongside.

A manifest is only worth something as a *local, reviewed* artifact. If you
download it from the same mutable ref as the files it describes, it verifies
nothing: one push changes both, and the hashes still agree. Get it by checking
out the commit it pins, or by diffing it against a regeneration (below).

See [`../docs/INSTALL.md`](../docs/INSTALL.md) for the install flow.

## Released manifests

| Commit | Manifest | Bundle files | `tools/install_skills.py` SHA-256 |
|---|---|---|---|
| `587a7b7f5e867cde0bf3a0bc2a65bfbce48c42a0` | [`587a7b7f…json`](587a7b7f5e867cde0bf3a0bc2a65bfbce48c42a0.json) | 43 | see the manifest's `installer_sha256` |

The installer digest is recorded in each manifest's `installer_sha256` field
and is what `verify` and `install` check themselves against. Read it out of the
manifest and compare before the first run:

```bash
sha256sum tools/install_skills.py
python3 -c "import json;print(json.load(open('manifests/587a7b7f5e867cde0bf3a0bc2a65bfbce48c42a0.json'))['installer_sha256'])"
```

Those two must agree. They are published together on purpose: the manifest you
reviewed names the verifier you reviewed, so a mismatched pair is caught rather
than silently accepted. It is a cross-check, not a root of trust — see
[`../docs/INSTALL.md`](../docs/INSTALL.md#verifying-the-installer-itself).

## Reviewing one

A manifest is a deterministic function of the checkout. Regenerate it and the
output is byte-identical, which is what makes review mechanical:

```bash
git checkout <sha>
python3 tools/make_manifest.py --checkout . --commit <sha> > /tmp/rebuilt.json
diff /tmp/rebuilt.json manifests/<sha>.json   # empty = it describes that commit
```

Then review what actually changed since the version you run today:

```bash
git diff <old-sha> <new-sha> -- skills references
```

`tests/test_install_skills.py::test_the_shipped_manifest_is_regenerable_from_this_checkout`
runs that regeneration in CI, so a skill edited without a fresh manifest fails
the build rather than shipping a manifest that describes a tree nobody has.

## Adding one (maintainers)

After the bundle change is merged and you have its commit SHA:

```bash
git checkout <sha>
python3 tools/make_manifest.py --checkout . --commit <sha> \
    --out manifests/<sha>.json
sha256sum tools/install_skills.py        # add to the table above
```

Commit the manifest on top of `<sha>`, then update the table and the examples
in `README.md` and `docs/INSTALL.md` to the new commit.

Two things to keep straight:

- **`tools/` is not in the bundle.** You do not download your own verifier. The
  installer comes from a reviewed checkout; the manifest only records its
  digest. Adding `tools/` to `BUNDLE_ROOTS` would let a fetched archive replace
  the thing doing the checking.
- **`manifests/` is not in the bundle either**, so adding a manifest never
  changes any hash inside one. A manifest generated before it was committed
  stays correct after.

If you change `tools/install_skills.py`, every manifest's `installer_sha256`
goes stale. Regenerate the manifest for the current bundle commit in the same
change; the test above will tell you if you forget.
