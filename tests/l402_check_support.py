"""Offline helpers for the l402-compatibility-report tests.

Loads the JSON fixtures, and stands in for DNS and HTTP so that no test opens a
network connection or pays anything. Imported by the ``test_l402_*`` modules;
pytest does not collect it (no ``test_`` prefix). Importing it puts the skill's
``scripts/`` folder on ``sys.path``; the script modules themselves are imported
lazily, inside the helpers that need them.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILL_DIR = REPO_ROOT / "skills" / "l402-compatibility-report"
SCRIPTS = SKILL_DIR / "scripts"
CHALLENGES = REPO_ROOT / "tests" / "fixtures" / "l402-challenges"
EVIDENCE = REPO_ROOT / "tests" / "fixtures" / "l402-evidence"
PUBLIC_TEST_ADDRESS = "93.184.215.14"

if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


def fixture_names() -> list[str]:
    return sorted(p.stem for p in CHALLENGES.glob("*.json"))


def load_fixture(name: str) -> dict:
    return json.loads((CHALLENGES / f"{name}.json").read_text(encoding="utf-8"))


def load_evidence(name: str) -> dict:
    return json.loads((EVIDENCE / f"{name}.json").read_text(encoding="utf-8"))


def www_authenticate(fixture: dict) -> list[str]:
    return [v for k, v in fixture["responses"][0]["headers"] if k.lower() == "www-authenticate"]


def first_invoice(fixture: dict) -> str:
    return re.search(r'invoice="(ln[0-9a-z]+)"', " ".join(www_authenticate(fixture))).group(1)


def preimage_from_seed(seed: str) -> str:
    """A deterministic 64-hex test preimage. Built at runtime so no literal sits in the repo."""
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()


def fake_resolver(dns: dict):
    def resolve(host: str, port: int) -> list[str]:
        return list(dns.get(host, [PUBLIC_TEST_ADDRESS]))
    return resolve


def fake_transport(responses: list[dict], log: list | None = None):
    from l402_http import HttpResponse

    by_url = {r["url"]: r for r in responses}

    def send(target, method, headers, body, timeout):
        if log is not None:
            log.append({"url": target.url, "method": method, "headers": dict(headers), "body": body,
                        "address": target.addresses[0]})
        r = by_url.get(target.url)
        if r is None:
            return HttpResponse(status=404, headers=[], body=b"", elapsed_ms=20)
        return HttpResponse(
            status=r["status"],
            headers=[(k, v) for k, v in r["headers"]],
            body=r.get("body", "").encode("utf-8"),
            elapsed_ms=r.get("latency_ms", 150),
        )
    return send


def observed(fixture: dict) -> datetime:
    return datetime.fromisoformat(fixture["observed_at"].replace("Z", "+00:00"))


def run_fixture(fixture: dict, *, max_sats: int | None = None, extra_responses: list[dict] = (),
                headers: dict | None = None, body: bytes | None = None, log: list | None = None,
                profiles: tuple = ()):
    """Run the read-only check against a fixture; return (report, secrets)."""
    import l402_analyze
    import l402_check

    request = l402_analyze.ProbeRequest(
        url=fixture["request"]["url"],
        method=fixture["request"]["method"],
        headers=dict(headers or {}),
        body=body,
    )
    return l402_check.run_mode_a(
        request,
        timeout=5.0,
        allow_private=False,
        max_sats=max_sats,
        now=observed(fixture),
        resolver=fake_resolver(fixture.get("dns", {})),
        transport=fake_transport(list(fixture["responses"]) + list(extra_responses), log),
        profiles=profiles,
    )


def all_secret_strings(fixture: dict) -> set[str]:
    """Every invoice, macaroon, token, and request blob in a fixture's challenge headers."""
    found = set()
    for value in www_authenticate(fixture):
        found.update(re.findall(r'(?:macaroon|token|invoice|request|opaque)="([^"]{8,})"', value))
        found.update(re.findall(r"ln(?:bc|tb)[0-9a-z]{50,}", value))
    return found
