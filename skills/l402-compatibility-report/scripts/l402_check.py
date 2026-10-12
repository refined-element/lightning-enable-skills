#!/usr/bin/env python3
"""l402_check.py: report how well an endpoint implements L402, without paying.

This first version holds the read-only run (``run_mode_a``); the command line
lands in a later step. Standard library only; Python 3.10 or later.
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import l402_analyze  # noqa: E402
import l402_http  # noqa: E402

ROOT_METADATA_PATHS = ("/openapi.json", "/llms.txt")


def run_mode_a(
    request: l402_analyze.ProbeRequest,
    *,
    timeout: float,
    allow_private: bool,
    max_sats: int | None,
    now: datetime,
    resolver=None,
    transport=None,
) -> tuple[dict, set[str]]:
    """Probe once, then the host-root metadata files; return (report, secrets).

    The metadata files are fetched only after the main request got a 402, as
    unpaid GETs with no caller headers and no body, over the same pinned
    transport; only their presence is recorded. Raises
    ``l402_http.RefusedHeaderError`` before any request when a caller header
    is a credential, a Host or framing header, or cannot be sent intact.
    """
    result = l402_http.probe(
        request.url, method=request.method, headers=request.headers, body=request.body,
        timeout=timeout, allow_private=allow_private, resolver=resolver, transport=transport,
    )
    root_metadata = {}
    if (result.error_kind is None and result.final_target is not None
            and result.response is not None and result.response.status == 402):
        for path in ROOT_METADATA_PATHS:
            extra = l402_http.probe(result.final_target.origin + path, timeout=timeout,
                                    allow_private=allow_private, resolver=resolver, transport=transport)
            root_metadata[path] = extra.response.status if extra.response is not None and not extra.hops else None
    report = l402_analyze.analyze(request, result, now=now, root_metadata=root_metadata, max_sats=max_sats)
    return report, l402_analyze.collect_secrets(request, result)
