#!/usr/bin/env python3
"""Generate a bundle manifest for one commit. Maintainer tool.

A manifest is a deterministic function of a checkout: run this twice on the
same tree and you get byte-identical output. That is the point -- a reviewer
checks out the commit the manifest claims, runs this, and diffs. If the diff
is empty, the manifest describes that commit and nothing else.

    git checkout <sha>
    python3 tools/make_manifest.py --checkout . --commit <sha> \
        --out manifests/<sha>.json
    diff <(git show <sha>:manifests/<sha>.json) manifests/<sha>.json

The manifest covers ``skills/`` and ``references/``: everything an installed
skill is made of, plus the shared instruction files skills cite. Never-tracked
build artifacts (``__pycache__``, ``*.pyc``, ``.DS_Store``) are skipped, since a
fetched archive never carries them; the verifier still refuses them in staging. It does not
cover ``tools/`` -- the installer is not fetched by the installer. It records
the installer's SHA-256 separately so a mismatched pair is caught, and so the
digest can be published for an out-of-band check.

Standard library only, Python 3.10+.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from install_skills import (  # noqa: E402  - sibling module, local import by design
    BUNDLE_ROOTS,
    DEFAULT_REPO,
    SCHEMA,
    InstallError,
    require_bundle_path,
    require_pinned_commit,
    sha256_file,
)


# Never tracked, so a fetched archive never carries them. They are skipped here
# so the manifest stays a function of the tracked tree whatever state the working
# copy is in. The verifier does NOT skip them: a staged bundle carrying one is
# refused as an unexpected file, which is the fail-closed direction.
ARTIFACT_NAMES = frozenset({".DS_Store", "Thumbs.db"})
ARTIFACT_DIRS = frozenset({"__pycache__", ".pytest_cache", ".ipynb_checkpoints"})
ARTIFACT_SUFFIXES = (".pyc", ".pyo", ".pyd")


def is_build_artifact(rel: str) -> bool:
    parts = rel.split("/")
    return (
        parts[-1] in ARTIFACT_NAMES
        or any(part in ARTIFACT_DIRS for part in parts)
        or rel.endswith(ARTIFACT_SUFFIXES)
    )


def collect(checkout: Path) -> dict[str, str]:
    """Hash every file under the bundle roots. Symlinks are refused."""
    files: dict[str, str] = {}
    for root in BUNDLE_ROOTS:
        root_dir = checkout / root
        if not root_dir.is_dir():
            raise InstallError("checkout_shape", f"{checkout} has no {root}/ directory.")
        for entry in sorted(root_dir.rglob("*")):
            if entry.is_symlink():
                raise InstallError("unsafe_symlink", f"{entry} is a symlink.")
            if entry.is_dir():
                continue
            if not entry.is_file():
                raise InstallError("unsafe_file_type", f"{entry} is not a regular file.")
            rel = entry.relative_to(checkout).as_posix()
            if is_build_artifact(rel):
                continue
            files[str(require_bundle_path(rel))] = sha256_file(entry)
    if not files:
        raise InstallError("checkout_shape", f"No bundle files found under {checkout}.")
    return files


def build(checkout: Path, commit: str, repo: str, installer: Path) -> dict:
    if not installer.is_file():
        raise InstallError("installer_missing", f"No installer at {installer}.")
    return {
        "schema": SCHEMA,
        "repo": repo,
        "commit": require_pinned_commit(commit),
        "installer_sha256": sha256_file(installer),
        "bundle_roots": list(BUNDLE_ROOTS),
        "files": dict(sorted(collect(checkout).items())),
    }


def render(manifest: dict) -> str:
    return json.dumps(manifest, indent=2, sort_keys=True) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="make_manifest.py",
        description="Generate a reviewed bundle manifest for one commit.",
    )
    parser.add_argument("--checkout", default=".", help="path to the checkout at --commit")
    parser.add_argument("--commit", required=True, help="full 40-character commit SHA")
    parser.add_argument("--repo", default=DEFAULT_REPO)
    parser.add_argument(
        "--installer",
        help="path to install_skills.py (default: the one next to this script)",
    )
    parser.add_argument("--out", help="write here instead of stdout")
    args = parser.parse_args(argv)

    checkout = Path(args.checkout).expanduser()
    installer = (
        Path(args.installer).expanduser()
        if args.installer
        else Path(__file__).resolve().parent / "install_skills.py"
    )
    try:
        text = render(build(checkout, args.commit, args.repo, installer))
    except InstallError as exc:
        print(f"error [{exc.code}]: {exc}", file=sys.stderr)
        return 2

    if args.out:
        Path(args.out).expanduser().write_text(text, encoding="utf-8")
        print(f"wrote {args.out}", file=sys.stderr)
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
