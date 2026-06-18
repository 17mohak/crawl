"""Seen URL registry.

CE-017: Implement Seen URL registry  (FR-003 / AC-001 — duplicate URLs never recrawled)

Tracks the set of canonical URLs that have already been processed so the crawl
visits each page exactly once. Callers are expected to pass *canonical* URLs
(see :func:`crawl_engine.discovery.canonicalize.canonicalize`) so that
equivalent spellings collapse to one key before they reach the registry.

The registry is intentionally decoupled from canonicalization: it stores
whatever strings it is given. This keeps it trivially testable and lets the
integrated workflow (CE-035) own the "canonicalize then check" ordering.
"""
from __future__ import annotations


class SeenRegistry:
    """A set-backed record of canonical URLs already seen this crawl."""

    def __init__(self) -> None:
        self._seen: set[str] = set()

    def mark_seen(self, url: str) -> bool:
        """Record ``url`` as seen.

        Returns ``True`` if this is the first time the URL has been seen (i.e.
        it should be crawled), ``False`` if it was already present (skip it).
        """
        if url in self._seen:
            return False
        self._seen.add(url)
        return True

    def __contains__(self, url: str) -> bool:
        return url in self._seen

    def __len__(self) -> int:
        return len(self._seen)

    # ── persistence (supports checkpoint/resume, CE-036) ─────────────────────

    def snapshot(self) -> dict:
        """Serialize to a plain dict. URLs are sorted for deterministic output."""
        return {"seen": sorted(self._seen)}

    @classmethod
    def restore(cls, data: dict) -> "SeenRegistry":
        """Rebuild a registry from a :meth:`snapshot` dict."""
        registry = cls()
        registry._seen = set(data.get("seen", []))
        return registry
