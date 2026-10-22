#!/usr/bin/env python3
"""Fetch, verify, and install lightning-enable skills from a pinned commit.

The problem this closes: `curl` a `SKILL.md` from `main` into an agent's
auto-loaded skills folder and you have granted whoever can move `main` the
ability to change, at any moment and without review, instructions your agent
executes against a wallet. `main` is mutable. A commit SHA is not.

The trust chain here, in order:

1. **You** obtain this file from a reviewed checkout at a pinned commit and
   read it. Nothing below can establish that for you -- a tampered installer
   would simply report success. Check it out of band before the first run::

       sha256sum tools/install_skills.py

   and compare against the digest published in ``manifests/README.md``.
2. **The manifest** is a local file you reviewed, naming one commit and the
   SHA-256 of every file in the bundle. ``--manifest`` must be a local path;
   an ``http://`` or ``https://`` argument is refused, because fetching the
   manifest and the files from the same mutable ref verifies nothing.
3. **The bundle** is downloaded, at the pinned commit, into a staging
   directory that is never an agent's skills folder, and is checked against
   the manifest in full -- every hash, no missing file, no extra file, no
   unsafe path, no symlink -- before a single byte is installed.
4. **Installation** copies from verified staging only. It never reaches the
   network. An update to a different commit needs ``--allow-update`` naming
   that choice; there is no silent refresh.

Validation never loads or executes anything from staging. It opens files
``"rb"`` and hashes them. This module runs no subprocess, imports nothing from
staging, and calls no ``eval``/``exec``/``compile``/``pickle``; the guard test
``tests/test_install_skills.py::test_installer_never_executes_staged_code``
pins that.

Standard library only, Python 3.10+.

Usage::

    python3 tools/install_skills.py fetch \
        --manifest manifests/<sha>.json --staging ./staging

    python3 tools/install_skills.py verify \
        --manifest manifests/<sha>.json --staging ./staging

    python3 tools/install_skills.py install \
        --manifest manifests/<sha>.json --staging ./staging \
        --dest ~/.claude/skills --skill agent-wallet-setup

    python3 tools/install_skills.py status --dest ~/.claude/skills
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import re
import shutil
import sys
import tarfile
import tempfile
import urllib.request
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

SCHEMA = "lightning-enable-skills/bundle-manifest@1"
DEFAULT_REPO = "refined-element/lightning-enable-skills"

# The bundle is what gets fetched, verified, and (for `skills/`) installed.
# `tools/` is deliberately NOT in it: you do not download your own verifier.
# This installer comes from your reviewed checkout, not from the archive.
BUNDLE_ROOTS = ("references", "skills")

FULL_SHA = re.compile(r"\A[0-9a-fA-F]{40}\Z")
SHA256_HEX = re.compile(r"\A[0-9a-f]{64}\Z")
REPO_SLUG = re.compile(r"\A[A-Za-z0-9._-]{1,100}/[A-Za-z0-9._-]{1,100}\Z")
SKILL_NAME = re.compile(r"\A[a-z0-9]+(-[a-z0-9]+)*\Z")

RECEIPT_NAME = ".lightning-enable-install.json"

# Staging must never be a folder an agent loads skills from: downloaded,
# not-yet-verified instructions sitting in one is the whole failure mode this
# installer exists to prevent.
#
# Matched as a "skills" directory under any agent-configuration directory. Not adjacency:
# plugin-distributed skills live at ~/.claude/plugins/<plugin>/skills, which is
# how this repo is consumed, and an adjacent-pair check misses it. This is a
# blocklist and cannot know every host's layout -- the docs say "these paths",
# not "every path an agent loads from".
AGENT_CONFIG_DIRS = frozenset(
    {
        "claude",
        ".claude",
        "agent",
        ".agent",
        "agents",
        ".agents",
        ".codeium",
        ".cursor",
        "codex",
        ".codex",
        "plugins",
        ".config",
    }
)
SKILLS_DIR_NAMES = frozenset({"skills"})

MAX_ARCHIVE_BYTES = 256 * 1024 * 1024
MAX_MEMBER_BYTES = 32 * 1024 * 1024
MAX_MEMBERS = 20_000


class InstallError(Exception):
    """A fail-closed refusal. ``code`` is stable; the message explains it."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


# --------------------------------------------------------------------------
# Reference and path validation
# --------------------------------------------------------------------------


def require_pinned_commit(ref: str) -> str:
    """Return the normalized 40-hex commit, or refuse.

    Only a full commit SHA is accepted. ``main``, ``HEAD``, ``latest``, a tag,
    a short SHA and a ``refs/...`` spec are all refused: every one of them can
    be made to point somewhere else after you reviewed it.
    """
    if ref is None:
        raise InstallError("mutable_ref", "No commit given. Pass --commit <40-hex SHA>.")
    if ref != ref.strip():
        raise InstallError(
            "mutable_ref",
            f"Commit {ref!r} has surrounding whitespace. Pass the bare 40-character SHA.",
        )
    if not FULL_SHA.match(ref):
        raise InstallError(
            "mutable_ref",
            f"{ref!r} is not a full 40-character commit SHA. Branch names, tags, "
            "'HEAD', 'latest' and abbreviated SHAs are refused on purpose: they can "
            "be repointed after you review them. Pass the full SHA.",
        )
    return ref.lower()


def safe_relpath(raw: str) -> PurePosixPath:
    """Validate one manifest/archive path and return it, or refuse.

    Refused: absolute paths, backslashes, drive letters, ``.``/``..``
    components, empty components, trailing slash, control characters, and
    anything that does not round-trip -- i.e. anything that could land a write
    outside the directory it was meant for.
    """
    if not raw or raw != raw.strip():
        raise InstallError("unsafe_path", f"Path {raw!r} is empty or padded with whitespace.")
    if "\\" in raw:
        raise InstallError("unsafe_path", f"Path {raw!r} contains a backslash.")
    if raw.startswith("/") or raw.startswith("~"):
        raise InstallError("unsafe_path", f"Path {raw!r} is not relative.")
    if re.match(r"\A[A-Za-z]:", raw):
        raise InstallError("unsafe_path", f"Path {raw!r} carries a drive letter.")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in raw):
        raise InstallError("unsafe_path", f"Path {raw!r} contains a control character.")
    parts = raw.split("/")
    for part in parts:
        if part in ("", ".", ".."):
            raise InstallError(
                "unsafe_path",
                f"Path {raw!r} has an empty, '.' or '..' component -- it could escape "
                "the directory it is written into.",
            )
    path = PurePosixPath(raw)
    if str(path) != raw:
        raise InstallError("unsafe_path", f"Path {raw!r} is not in normal form.")
    return path


def require_bundle_path(raw: str) -> PurePosixPath:
    """``safe_relpath`` plus: the path must sit under a declared bundle root."""
    path = safe_relpath(raw)
    if path.parts[0] not in BUNDLE_ROOTS:
        raise InstallError(
            "unexpected_file",
            f"Path {raw!r} is outside the bundle roots {list(BUNDLE_ROOTS)}.",
        )
    if len(path.parts) < 2:
        raise InstallError(
            "unexpected_file",
            f"Path {raw!r} is a bundle root, not a file inside one.",
        )
    return path


def reject_autoload_dir(path: Path, what: str) -> None:
    """Refuse a staging directory that is, or sits under, a skills folder.

    Matches a ``skills`` component that has an agent-configuration directory
    somewhere above it, so ``~/.claude/skills``, ``~/.claude/plugins/x/skills``
    and ``~/.config/claude/skills`` are all caught. ``resolve()`` runs first, so
    a symlink pointing into one of these is caught too.
    """
    resolved = path.expanduser().resolve()
    lowered = [part.lower() for part in resolved.parts]
    for index, part in enumerate(lowered):
        if part in SKILLS_DIR_NAMES and any(
            ancestor in AGENT_CONFIG_DIRS for ancestor in lowered[:index]
        ):
            matched = "/".join(resolved.parts[: index + 1])
            raise InstallError(
                "staging_is_autoload_dir",
                f"{what} {resolved} is inside an agent's skills folder ({matched}). "
                "Unverified downloads must never land where an agent loads them. "
                "Stage somewhere else, then install.",
            )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


# --------------------------------------------------------------------------
# Manifest
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Manifest:
    path: Path
    repo: str
    commit: str
    installer_sha256: str
    files: dict[str, str]

    @property
    def skills(self) -> list[str]:
        names = {
            PurePosixPath(p).parts[1]
            for p in self.files
            if PurePosixPath(p).parts[0] == "skills" and len(PurePosixPath(p).parts) > 1
        }
        return sorted(names)


def load_manifest(raw_arg: str) -> Manifest:
    """Read a manifest from a LOCAL path. A URL is refused.

    Downloading the manifest alongside the files it describes is not
    verification: whoever can change the files can change the manifest in the
    same push. The manifest has to be something you already reviewed and hold.
    """
    if "://" in raw_arg:
        raise InstallError(
            "remote_manifest",
            f"--manifest {raw_arg!r} is a URL. The manifest must be a local file you "
            "have reviewed. Fetching the manifest and the bundle from the same "
            "mutable ref verifies nothing -- one push changes both.",
        )
    path = Path(raw_arg).expanduser()
    if not path.is_file():
        raise InstallError("manifest_missing", f"No manifest file at {path}.")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise InstallError("manifest_unreadable", f"{path} is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise InstallError("manifest_unreadable", f"{path} is not a JSON object.")

    schema = data.get("schema")
    if schema != SCHEMA:
        raise InstallError(
            "manifest_schema",
            f"{path} declares schema {schema!r}; this installer reads {SCHEMA!r}.",
        )

    repo = data.get("repo", "")
    if not isinstance(repo, str) or not REPO_SLUG.match(repo):
        raise InstallError("manifest_schema", f"{path} has no valid 'repo' slug.")

    commit = require_pinned_commit(str(data.get("commit", "")))

    installer_sha256 = data.get("installer_sha256", "")
    if not isinstance(installer_sha256, str) or not SHA256_HEX.match(installer_sha256):
        raise InstallError(
            "manifest_schema",
            f"{path} has no valid 'installer_sha256' (64 lowercase hex characters).",
        )

    raw_files = data.get("files")
    if not isinstance(raw_files, dict) or not raw_files:
        raise InstallError("manifest_schema", f"{path} has no 'files' map.")

    files: dict[str, str] = {}
    for raw_path, raw_digest in raw_files.items():
        if not isinstance(raw_path, str) or not isinstance(raw_digest, str):
            raise InstallError("manifest_schema", f"{path} has a non-string files entry.")
        bundle_path = require_bundle_path(raw_path)
        if not SHA256_HEX.match(raw_digest):
            raise InstallError(
                "manifest_schema",
                f"{path}: {raw_path!r} has digest {raw_digest!r}, not 64 lowercase hex.",
            )
        files[str(bundle_path)] = raw_digest

    manifest = Manifest(
        path=path,
        repo=repo,
        commit=commit,
        installer_sha256=installer_sha256,
        files=files,
    )
    _require_every_skill_has_a_skill_file(manifest)
    return manifest


def _require_every_skill_has_a_skill_file(manifest: Manifest) -> None:
    """A skill with no ``SKILL.md`` is not a skill; refuse the manifest."""
    for name in manifest.skills:
        if f"skills/{name}/SKILL.md" not in manifest.files:
            raise InstallError(
                "manifest_schema",
                f"{manifest.path}: skill {name!r} has no skills/{name}/SKILL.md entry. "
                "The manifest must cover the complete bundle.",
            )


def check_installer_integrity(manifest: Manifest, installer: Path | None = None) -> str:
    """Compare this file's own digest with the reviewed manifest's.

    Defense in depth, not a root of trust: an installer that had been replaced
    could skip this check. The real control is the out-of-band ``sha256sum``
    documented in ``manifests/README.md``. This catches the ordinary case --
    an installer and a manifest from two different versions.
    """
    installer = installer or Path(__file__).resolve()
    actual = sha256_file(installer)
    if not hmac.compare_digest(actual, manifest.installer_sha256):
        raise InstallError(
            "installer_mismatch",
            f"This installer ({installer}) hashes to {actual}, but "
            f"{manifest.path} was reviewed against {manifest.installer_sha256}. "
            "The installer and the manifest are from different versions. Check out "
            "the commit this manifest pins and re-read the installer before running it.",
        )
    return actual


# --------------------------------------------------------------------------
# Staging inspection -- reads bytes, never runs them
# --------------------------------------------------------------------------


def scan_staging(staging: Path) -> dict[str, Path]:
    """Map bundle-relative path -> real file, refusing anything unsafe.

    Symlinks (file or directory), devices, FIFOs and sockets are refused
    outright: a symlink in an archive is how a "copy these files" step writes
    outside the directory it was pointed at.
    """
    if not staging.is_dir():
        raise InstallError("staging_missing", f"No staging directory at {staging}.")
    if staging.is_symlink():
        raise InstallError("unsafe_symlink", f"Staging directory {staging} is a symlink.")

    strays = sorted(
        entry.name for entry in staging.iterdir() if entry.name not in BUNDLE_ROOTS
    )
    if strays:
        raise InstallError(
            "unexpected_file",
            f"{staging} holds entries outside the bundle roots {list(BUNDLE_ROOTS)}: "
            f"{strays}. Stage with `fetch` into an empty directory so that "
            "'no unexpected files' means the whole tree.",
        )

    found: dict[str, Path] = {}
    for root in BUNDLE_ROOTS:
        root_dir = staging / root
        if not root_dir.exists():
            continue
        if root_dir.is_symlink():
            raise InstallError("unsafe_symlink", f"{root_dir} is a symlink.")
        for dirpath, dirnames, filenames in os.walk(root_dir, followlinks=False):
            here = Path(dirpath)
            for name in sorted(dirnames):
                if (here / name).is_symlink():
                    raise InstallError(
                        "unsafe_symlink",
                        f"{(here / name).relative_to(staging)} is a symlinked directory. "
                        "Refusing the bundle.",
                    )
            for name in sorted(filenames):
                entry = here / name
                rel = entry.relative_to(staging).as_posix()
                if entry.is_symlink():
                    raise InstallError(
                        "unsafe_symlink",
                        f"{rel} is a symlink. Refusing the bundle.",
                    )
                if not entry.is_file():
                    raise InstallError(
                        "unsafe_file_type",
                        f"{rel} is not a regular file. Refusing the bundle.",
                    )
                found[str(require_bundle_path(rel))] = entry
    return found


@dataclass
class VerifyReport:
    manifest: Manifest
    staging: Path
    missing: list[str]
    unexpected: list[str]
    mismatched: list[str]

    @property
    def ok(self) -> bool:
        return not (self.missing or self.unexpected or self.mismatched)

    def problems(self) -> list[str]:
        lines: list[str] = []
        for path in self.missing:
            lines.append(f"  missing     {path}")
        for path in self.unexpected:
            lines.append(f"  unexpected  {path}")
        for path in self.mismatched:
            lines.append(f"  hash differs {path}")
        return lines


def verify_staging(manifest: Manifest, staging: Path) -> VerifyReport:
    """Hash every staged file and compare with the manifest. Set-exact."""
    found = scan_staging(staging)
    expected = manifest.files

    missing = sorted(set(expected) - set(found))
    unexpected = sorted(set(found) - set(expected))
    mismatched = []
    for path in sorted(set(expected) & set(found)):
        if not hmac.compare_digest(sha256_file(found[path]), expected[path]):
            mismatched.append(path)

    return VerifyReport(
        manifest=manifest,
        staging=staging,
        missing=missing,
        unexpected=unexpected,
        mismatched=mismatched,
    )


# --------------------------------------------------------------------------
# Fetch
# --------------------------------------------------------------------------


def archive_url(repo: str, commit: str) -> str:
    if not REPO_SLUG.match(repo):
        raise InstallError("bad_repo", f"{repo!r} is not an 'owner/name' slug.")
    return f"https://codeload.github.com/{repo}/tar.gz/{commit}"


class HttpsOnlyRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Follow redirects only while they stay on HTTPS."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D102
        if not newurl.lower().startswith("https://"):
            raise InstallError(
                "insecure_redirect",
                f"{req.full_url} redirected to {newurl!r}, which is not HTTPS. Refusing.",
            )
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def download_archive(url: str, destination: Path) -> int:
    """Stream an archive to ``destination``. HTTPS only, and size-bounded.

    The bytes are untrusted either way -- they are checked against the local
    manifest before anything is installed -- but there is no reason to accept a
    transport downgrade on the way in.
    """
    if not url.lower().startswith("https://"):
        raise InstallError("insecure_url", f"{url!r} is not an HTTPS URL.")
    opener = urllib.request.build_opener(HttpsOnlyRedirectHandler)
    request = urllib.request.Request(url, headers={"Accept": "application/x-gzip"})
    total = 0
    with opener.open(request) as response:
        if not str(response.url).lower().startswith("https://"):
            raise InstallError("insecure_redirect", f"{url} was served over plain HTTP.")
        with open(destination, "wb") as handle:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_ARCHIVE_BYTES:
                    raise InstallError(
                        "archive_too_large",
                        f"Archive exceeded {MAX_ARCHIVE_BYTES} bytes. Refusing.",
                    )
                handle.write(chunk)
    return total


def extract_bundle(archive: Path, staging: Path) -> list[str]:
    """Extract only the bundle roots into ``staging``, member by member.

    Python 3.12 added ``tarfile``'s ``data`` filter; 3.10 and 3.11 do not have
    it, and this repo supports 3.10. So each member is checked here instead:
    regular files only, safe relative paths, one shared top-level directory,
    and a per-member size bound. Nothing outside ``BUNDLE_ROOTS`` is written at
    all -- the archive also holds tests and CI config, which are not part of
    what gets installed.
    """
    staging.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    top_level: str | None = None
    extracted_bytes = 0

    with tarfile.open(archive, "r:gz") as tar:
        for index, member in enumerate(tar):
            if index >= MAX_MEMBERS:
                raise InstallError("archive_too_large", "Archive has too many members.")
            if member.issym() or member.islnk():
                raise InstallError(
                    "unsafe_symlink",
                    f"Archive member {member.name!r} is a link. Refusing the archive.",
                )
            if member.isdir():
                continue
            if not member.isfile():
                raise InstallError(
                    "unsafe_file_type",
                    f"Archive member {member.name!r} is not a regular file.",
                )
            if member.size > MAX_MEMBER_BYTES:
                raise InstallError(
                    "archive_too_large",
                    f"Archive member {member.name!r} is larger than {MAX_MEMBER_BYTES} bytes.",
                )
            extracted_bytes += member.size
            if extracted_bytes > MAX_ARCHIVE_BYTES:
                raise InstallError(
                    "archive_too_large",
                    f"Archive expands to more than {MAX_ARCHIVE_BYTES} bytes. Refusing.",
                )

            name = safe_relpath(member.name)
            if len(name.parts) < 2:
                continue
            if top_level is None:
                top_level = name.parts[0]
            elif name.parts[0] != top_level:
                raise InstallError(
                    "archive_shape",
                    f"Archive has more than one top-level directory "
                    f"({top_level!r} and {name.parts[0]!r}).",
                )

            inner = PurePosixPath(*name.parts[1:])
            if inner.parts[0] not in BUNDLE_ROOTS:
                continue

            target = staging / inner
            source = tar.extractfile(member)
            if source is None:
                raise InstallError(
                    "archive_shape", f"Archive member {member.name!r} has no content."
                )
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                with source, open(target, "wb") as handle:
                    shutil.copyfileobj(source, handle, length=1024 * 1024)
                os.chmod(target, 0o644)
            except OSError as exc:
                raise InstallError(
                    "archive_shape",
                    f"Archive member {member.name!r} could not be written to "
                    f"{inner}: {exc}. Refusing the archive.",
                ) from exc
            written.append(str(inner))

    if not written:
        raise InstallError(
            "archive_shape",
            f"Archive held nothing under {list(BUNDLE_ROOTS)}. Wrong commit or wrong repo?",
        )
    return sorted(written)


# --------------------------------------------------------------------------
# Install
# --------------------------------------------------------------------------


def read_receipt(skill_dir: Path) -> dict | None:
    receipt = skill_dir / RECEIPT_NAME
    if not receipt.is_file():
        return None
    try:
        data = json.loads(receipt.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _destination_drift(skill_dir: Path, expected: dict[str, str]) -> list[str]:
    """How the installed directory differs from what the MANIFEST says it holds.

    ``expected`` maps skill-relative path -> SHA-256, taken from the manifest.
    The receipt is deliberately NOT the source of truth here: it lives inside
    the directory it vouches for, with the same permissions as the files it
    describes, so anyone who can edit a ``SKILL.md`` can edit the digest beside
    it. The receipt records only WHICH commit is installed; the manifest says
    what that commit contains.

    Set-exact in both directions, like ``scan_staging``: a changed file, a
    missing file and an ADDED file are all drift. Added files matter --
    ``skills/l402-compatibility-report/scripts/*.py`` sibling-import each other,
    so a planted ``__pycache__/*.pyc`` in the installed directory can be loaded
    in place of a verified ``.py``. That is why the destination is enumerated
    rather than just spot-checked against a list.
    """
    drifted: list[str] = []
    for rel, digest in sorted(expected.items()):
        path = skill_dir / PurePosixPath(rel)
        if (
            not path.is_file()
            or path.is_symlink()
            or not hmac.compare_digest(sha256_file(path), digest)
        ):
            drifted.append(rel)

    if not skill_dir.is_dir() or skill_dir.is_symlink():
        return drifted or ["<missing>"]
    for dirpath, dirnames, filenames in os.walk(skill_dir, followlinks=False):
        here = Path(dirpath)
        for name in sorted(dirnames):
            if (here / name).is_symlink():
                drifted.append((here / name).relative_to(skill_dir).as_posix() + "/")
        for name in sorted(filenames):
            rel = (here / name).relative_to(skill_dir).as_posix()
            if rel != RECEIPT_NAME and rel not in expected:
                drifted.append(rel)
    return sorted(set(drifted))


def preflight_skill(
    manifest: Manifest,
    dest: Path,
    name: str,
    *,
    allow_update: bool = False,
    force: bool = False,
) -> None:
    """Raise whatever ``install_skill`` would raise, before anything is copied.

    Lets ``cmd_install`` decide every per-skill refusal up front, so a multi-skill
    run is all-or-nothing rather than stopping half way through with some skills
    already replaced.
    """
    target = dest / name
    existing = read_receipt(target)
    expected = {
        str(PurePosixPath(rel).relative_to(f"skills/{name}")): digest
        for rel, digest in manifest.files.items()
        if rel.startswith(f"skills/{name}/")
    }
    if existing is not None:
        if existing.get("commit") == manifest.commit:
            drifted = _destination_drift(target, expected)
            if drifted and not force:
                raise InstallError(
                    "local_modification",
                    f"{target} is installed from the same commit, but the directory no "
                    f"longer matches the manifest: {', '.join(drifted)}. Something "
                    "changed the instructions your agent loads. Review them, then "
                    "re-run with --force to restore the verified copies.",
                )
        elif not allow_update:
            raise InstallError(
                "update_requires_opt_in",
                f"{target} already holds {name} from commit "
                f"{existing.get('commit', 'unknown')}. This manifest pins "
                f"{manifest.commit}. Updating replaces instructions your agent runs, "
                "so it is an explicit choice: review the new version, then re-run with "
                "--allow-update.",
            )
    elif target.exists():
        if target.is_symlink():
            raise InstallError("unsafe_symlink", f"{target} is a symlink. Refusing to replace it.")
        if not force:
            raise InstallError(
                "unmanaged_destination",
                f"{target} exists and was not installed by this tool (no {RECEIPT_NAME}). "
                "Refusing to overwrite it. Move it aside, or pass --force if you are "
                "sure it can be replaced.",
            )


def install_skill(
    manifest: Manifest,
    staging: Path,
    dest: Path,
    name: str,
    *,
    allow_update: bool = False,
    force: bool = False,
) -> str:
    """Copy one verified skill into ``dest``.

    Returns ``installed`` (new), ``unchanged`` (same commit, bytes intact),
    ``restored`` (same commit, on-disk edits replaced under ``--force``) or
    ``updated`` (a different commit, under ``--allow-update``).

    Never touches the network. The caller has already verified ``staging``
    against ``manifest`` in full; this only copies files the manifest names.
    """
    source = staging / "skills" / name
    target = dest / name
    existing = read_receipt(target)
    restoring = False

    files = sorted(p for p in manifest.files if p.startswith(f"skills/{name}/"))
    expected = {
        str(PurePosixPath(rel).relative_to(f"skills/{name}")): manifest.files[rel]
        for rel in files
    }

    if existing is not None:
        if existing.get("commit") == manifest.commit:
            drifted = _destination_drift(target, expected)
            if drifted and not force:
                raise InstallError(
                    "local_modification",
                    f"{target} is installed from the same commit, but the directory no "
                    f"longer matches the manifest: {', '.join(drifted)}. Something "
                    "changed the instructions your agent loads. Review them, then "
                    "re-run with --force to restore the verified copies.",
                )
            if not force:
                return "unchanged"
            # --force always re-copies, drift or not: it is the documented repair,
            # and a short-circuit here would leave planted extra files in place.
            restoring = True
        elif not allow_update:
            raise InstallError(
                "update_requires_opt_in",
                f"{target} already holds {name} from commit "
                f"{existing.get('commit', 'unknown')}. This manifest pins "
                f"{manifest.commit}. Updating replaces instructions your agent runs, "
                "so it is an explicit choice: review the new version, then re-run with "
                "--allow-update.",
            )
    elif target.exists():
        if target.is_symlink():
            raise InstallError("unsafe_symlink", f"{target} is a symlink. Refusing to replace it.")
        if not force:
            raise InstallError(
                "unmanaged_destination",
                f"{target} exists and was not installed by this tool (no {RECEIPT_NAME}). "
                "Refusing to overwrite it. Move it aside, or pass --force if you are "
                "sure it can be replaced.",
            )

    dest.mkdir(parents=True, exist_ok=True)

    staged_target = Path(
        tempfile.mkdtemp(prefix=f".{name}.incoming-", dir=dest)
    )
    try:
        for rel in files:
            inner = PurePosixPath(rel).relative_to(f"skills/{name}")
            out = staged_target / inner
            out.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source / inner, out)
            os.chmod(out, 0o644)

        receipt = {
            "schema": "lightning-enable-skills/install-receipt@1",
            "skill": name,
            "repo": manifest.repo,
            "commit": manifest.commit,
            "manifest_path": str(manifest.path.resolve()),
            "manifest_sha256": sha256_file(manifest.path),
            "installer_sha256": manifest.installer_sha256,
            "files": dict(expected),
        }
        (staged_target / RECEIPT_NAME).write_text(
            json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        os.chmod(staged_target / RECEIPT_NAME, 0o644)
        os.chmod(staged_target, 0o755)

        replaced: Path | None = None
        if target.exists():
            replaced = Path(tempfile.mkdtemp(prefix=f".{name}.replaced-", dir=dest))
            replaced.rmdir()
            os.replace(target, replaced)
        try:
            os.replace(staged_target, target)
        except OSError:
            if replaced is not None:
                os.replace(replaced, target)
            raise
        if replaced is not None:
            shutil.rmtree(replaced, ignore_errors=True)
            return "restored" if restoring else "updated"
        return "installed"
    finally:
        if staged_target.exists():
            shutil.rmtree(staged_target, ignore_errors=True)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def cmd_fetch(args: argparse.Namespace) -> int:
    # The commit may come from the reviewed manifest instead of being retyped.
    # That is not a weakening of "an explicit full SHA is required": the SHA
    # still comes from a pinned, local, reviewed artifact rather than a branch
    # name -- and it is one fewer value for a human to paste wrong. A manifest
    # pinning anything but a 40-hex SHA is refused when it is loaded.
    manifest = load_manifest(args.manifest) if args.manifest else None
    if manifest is not None:
        check_installer_integrity(manifest)
        commit = manifest.commit
        if args.commit and require_pinned_commit(args.commit) != commit:
            raise InstallError(
                "commit_mismatch",
                f"--commit {args.commit} does not match the commit this manifest "
                f"pins ({commit}).",
            )
    elif args.commit:
        commit = require_pinned_commit(args.commit)
    else:
        raise InstallError(
            "mutable_ref",
            "Pass --manifest <local manifest> (the commit comes from it) or "
            "--commit <40-hex SHA>.",
        )
    staging = Path(args.staging).expanduser()
    reject_autoload_dir(staging, "Staging directory")

    if staging.exists():
        if not staging.is_dir():
            raise InstallError("staging_occupied", f"{staging} exists and is not a directory.")
        if any(staging.iterdir()):
            raise InstallError(
                "staging_occupied",
                f"{staging} is not empty. Stage into a fresh directory so 'unexpected "
                "file' means something.",
            )

    with tempfile.TemporaryDirectory(prefix="le-skills-archive-") as tmp:
        archive = Path(tmp) / "bundle.tar.gz"
        if args.archive:
            local = Path(args.archive).expanduser()
            if not local.is_file():
                raise InstallError("archive_missing", f"No archive at {local}.")
            shutil.copyfile(local, archive)
            origin = str(local)
        else:
            url = archive_url(args.repo, commit)
            download_archive(url, archive)
            origin = url
        written = extract_bundle(archive, staging)

    print(f"Fetched {len(written)} bundle files from {origin}")
    if args.archive:
        # Nothing here checked that this archive IS that commit; `verify` against
        # the local manifest is what binds it. Don't print an unchecked claim.
        print(f"  declared commit (UNVERIFIED until you run verify): {commit}")
    else:
        print(f"  commit:  {commit}")
    print(f"  staging: {staging.resolve()}")
    print()
    print("Nothing is installed yet. Next:")
    manifest_arg = args.manifest or "<local manifest>"
    print(f"  python3 {sys.argv[0]} verify --manifest {manifest_arg} --staging {staging}")
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    manifest = load_manifest(args.manifest)
    check_installer_integrity(manifest)
    if args.commit:
        wanted = require_pinned_commit(args.commit)
        if wanted != manifest.commit:
            raise InstallError(
                "commit_mismatch",
                f"--commit {wanted} does not match the manifest's {manifest.commit}.",
            )
    staging = Path(args.staging).expanduser()
    reject_autoload_dir(staging, "Staging directory")
    report = verify_staging(manifest, staging)
    print_verify(report)
    return 0 if report.ok else 1


def print_verify(report: VerifyReport) -> None:
    manifest = report.manifest
    print(f"Manifest: {manifest.path}")
    print(f"  repo:    {manifest.repo}")
    print(f"  commit:  {manifest.commit}")
    print(f"  files:   {len(manifest.files)}")
    print(f"Staging:  {report.staging.resolve()}")
    if report.ok:
        print(f"OK: all {len(manifest.files)} files match the reviewed manifest.")
        print(f"Skills in this bundle: {', '.join(manifest.skills)}")
        return
    print("REFUSED: the staged bundle does not match the manifest.")
    for line in report.problems():
        print(line)
    print()
    print("Nothing was installed. Re-fetch at the manifest's commit, or review the")
    print("difference before going further -- these files are instructions your agent runs.")


def cmd_install(args: argparse.Namespace) -> int:
    manifest = load_manifest(args.manifest)
    check_installer_integrity(manifest)
    staging = Path(args.staging).expanduser()
    dest = Path(args.dest).expanduser()
    # The destination is meant to be a skills folder; staging never is.
    reject_autoload_dir(staging, "Staging directory")

    # Always re-verify. A prior `verify` run proves nothing about this one.
    report = verify_staging(manifest, staging)
    if not report.ok:
        print_verify(report)
        raise InstallError(
            "verification_failed",
            "Refusing to install from a bundle that does not match the manifest.",
        )

    if args.all_skills:
        wanted = manifest.skills
    else:
        wanted = list(dict.fromkeys(args.skill or []))
    if not wanted:
        raise InstallError(
            "no_skill_selected",
            "Name at least one --skill, or pass --all-skills. "
            f"This manifest covers: {', '.join(manifest.skills)}",
        )
    for name in wanted:
        if not SKILL_NAME.match(name):
            raise InstallError("unknown_skill", f"{name!r} is not a valid skill name.")
        if name not in manifest.skills:
            raise InstallError(
                "unknown_skill",
                f"{name!r} is not in this manifest. It covers: {', '.join(manifest.skills)}",
            )

    # Pre-flight: a refusal on the third skill must not leave the first two
    # replaced. Every per-skill refusal is decided from state on disk, so it can
    # be decided for all of them before the first copy happens.
    for name in wanted:
        preflight_skill(manifest, dest, name, allow_update=args.allow_update, force=args.force)

    print(f"Verified {len(manifest.files)} files against {manifest.path}")
    print(f"Installing from commit {manifest.commit} into {dest.resolve() if dest.exists() else dest}")
    for name in wanted:
        outcome = install_skill(
            manifest,
            staging,
            dest,
            name,
            allow_update=args.allow_update,
            force=args.force,
        )
        print(f"  {outcome:<10} {name}")
    print()
    print("Installed from verified local files. No network access was used in this step.")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    dest = Path(args.dest).expanduser()
    if not dest.is_dir():
        raise InstallError("dest_missing", f"No directory at {dest}.")
    rows = []
    for child in sorted(dest.iterdir()):
        if not child.is_dir() or child.is_symlink():
            continue
        receipt = read_receipt(child)
        if receipt is None:
            rows.append((child.name, "unmanaged", ""))
        else:
            rows.append((child.name, receipt.get("commit", "?"), receipt.get("repo", "?")))
    if not rows:
        print(f"No skills in {dest}.")
        return 0
    width = max(len(name) for name, _, _ in rows)
    for name, commit, repo in rows:
        print(f"{name:<{width}}  {commit}  {repo}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="install_skills.py",
        description=(
            "Install lightning-enable skills from a pinned commit, verified against a "
            "local reviewed manifest. Mutable refs (main, HEAD, tags, short SHAs) are "
            "refused."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    fetch = sub.add_parser("fetch", help="download a pinned commit into a staging directory")
    fetch.add_argument(
        "--manifest",
        help="LOCAL reviewed manifest; the commit to fetch is read from it",
    )
    fetch.add_argument(
        "--commit",
        help="full 40-character commit SHA (not needed when --manifest is given)",
    )
    fetch.add_argument("--staging", required=True, help="empty directory to stage into")
    fetch.add_argument("--repo", default=DEFAULT_REPO, help=f"owner/name (default {DEFAULT_REPO})")
    fetch.add_argument("--archive", help="use this local .tar.gz instead of downloading")
    fetch.set_defaults(func=cmd_fetch)

    verify = sub.add_parser("verify", help="check a staging directory against a local manifest")
    verify.add_argument("--manifest", required=True, help="path to a LOCAL reviewed manifest")
    verify.add_argument("--staging", required=True)
    verify.add_argument("--commit", help="optional: assert the manifest pins this commit")
    verify.set_defaults(func=cmd_verify)

    install = sub.add_parser("install", help="verify, then copy verified files into a skills dir")
    install.add_argument("--manifest", required=True, help="path to a LOCAL reviewed manifest")
    install.add_argument("--staging", required=True)
    install.add_argument("--dest", required=True, help="skills directory, e.g. ~/.claude/skills")
    install.add_argument("--skill", action="append", help="skill to install (repeatable)")
    install.add_argument("--all-skills", action="store_true")
    install.add_argument(
        "--allow-update",
        action="store_true",
        help="replace an installed skill that came from a different commit",
    )
    install.add_argument(
        "--force",
        action="store_true",
        help="replace a directory this tool did not install",
    )
    install.set_defaults(func=cmd_install)

    status = sub.add_parser("status", help="show what is installed, and from which commit")
    status.add_argument("--dest", required=True)
    status.set_defaults(func=cmd_status)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except InstallError as exc:
        print(f"error [{exc.code}]: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
