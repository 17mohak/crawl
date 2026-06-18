"""URL Canonicalization.

CE-012: Lowercase scheme and host       (FR-002 / AC-003)
CE-013: Remove URL fragments            (FR-002 / AC-003)
CE-014: Remove tracking query params    (FR-002 / AC-003)
CE-015: Normalize trailing slashes      (FR-002 / AC-003)
CE-016: Resolve relative URLs           (FR-002 / AC-003)

These five steps compose into a single :func:`canonicalize` applied to every
URL *before* it reaches the Seen URL registry (CE-017) or the BFS queue, so two
spellings of the same page collapse to one key.

Order of operations (per the build plan):
    resolve relative → lowercase scheme/host → strip fragment
    → strip tracking params → strip trailing slash

Scope note — this implements exactly the five backlog tasks and nothing more.
In particular it does NOT force ``http``→``https``, add/remove ``www``, or
lowercase the *path* (paths can be case-sensitive on the origin server).
CE-012 says "lowercase scheme and host", so only those are lowercased. See the
discrepancy flagged for HANDOFF.md's worked example in the canonicalization
tests.
"""
from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

# Sensible defaults if no tracking-param list is supplied. The authoritative
# list lives in CrawlConfig.tracking_params (CFG / CE-014) so it stays tunable.
DEFAULT_TRACKING_PARAMS: frozenset[str] = frozenset(
    {
        "utm_source",
        "utm_medium",
        "utm_campaign",
        "utm_term",
        "utm_content",
        "gclid",
        "gclsrc",
        "dclid",
        "fbclid",
        "msclkid",
        "mc_cid",
        "mc_eid",
        "yclid",
        "igshid",
        "_ga",
    }
)


def canonicalize(
    url: str,
    base: str | None = None,
    tracking_params: list[str] | frozenset[str] | None = None,
) -> str:
    """Return the canonical form of ``url``.

    Args:
        url: The URL to canonicalize. May be relative if ``base`` is given.
        base: Absolute URL the page was found on; used to resolve relative
            references (CE-016). If ``None``, ``url`` is assumed absolute.
        tracking_params: Query keys to strip (CE-014), matched
            case-insensitively. Defaults to :data:`DEFAULT_TRACKING_PARAMS`.

    Returns:
        A canonical absolute URL string. Equivalent inputs (differing only by
        fragment, tracking params, trailing slash, or scheme/host casing) map
        to the same output.
    """
    tracking = {
        p.lower()
        for p in (DEFAULT_TRACKING_PARAMS if tracking_params is None else tracking_params)
    }

    # CE-016: resolve relative against the base page URL.
    if base:
        url = urljoin(base, url)

    parts = urlsplit(url)

    # CE-012: lowercase scheme and host only (not the path).
    scheme = parts.scheme.lower()
    netloc = parts.netloc.lower()

    # CE-014: drop tracking query params, keep the rest in their original order.
    kept_pairs = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if key.lower() not in tracking
    ]
    query = urlencode(kept_pairs)

    # CE-015: normalize trailing slashes. A bare host ("/" or "") canonicalizes
    # to an empty path so "host" and "host/" agree; deeper paths lose any
    # trailing slash so "/members" and "/members/" agree.
    path = parts.path
    if path != "/":
        path = path.rstrip("/")
    else:
        path = ""

    # CE-013: fragment dropped by passing "" as the final component.
    return urlunsplit((scheme, netloc, path, query, ""))
