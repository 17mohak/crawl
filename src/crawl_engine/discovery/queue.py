"""URL Discovery: BFS queue manager.

CE-005: Implement BFS Queue Manager  (FR-001 / AC-001 — URLs processed in BFS order)
CE-007: Max depth enforcement        (CFG-004 / AC-001 — crawl stops beyond configured depth)
CE-008: Max page enforcement         (CFG-005 / AC-001 — crawl stops after configured page count)
CE-004: Load seed URLs               (FR-001 / AC-001 — seeds loaded from config and queued)
CE-006: Queue persistence support    (FR-019 / AC-013 — queue state saved and reloadable)

The queue is a thin wrapper over ``collections.deque`` holding ``(url, depth)``
pairs in FIFO (breadth-first) order. It owns two limits — ``max_depth`` and
``max_pages`` — both sourced from ``CrawlConfig`` so nothing is hardcoded.

Deduplication of *canonical* URLs is the job of the Seen URL registry
(CE-017, canonicalization group). This queue keeps only a lightweight guard
against enqueuing the exact same URL string twice within a run; the canonical
registry supersedes it in the integrated workflow.
"""
from __future__ import annotations

import json
import logging
from collections import deque
from dataclasses import dataclass
from pathlib import Path

from crawl_engine.config.loader import CrawlConfig
from crawl_engine.logging.logger import log_event


@dataclass(frozen=True)
class QueueItem:
    """A single unit of work: a URL and its BFS depth from the nearest seed."""

    url: str
    depth: int


class CrawlQueue:
    """Breadth-first queue of URLs to crawl, with depth and page limits.

    Args:
        max_depth: Maximum link depth to follow. Seeds are depth 0, so a
            ``max_depth`` of 4 means URLs discovered up to 4 hops away are
            queued. Pushes deeper than this are rejected.
        max_pages: Maximum number of pages to dispatch over the whole run.
            ``0`` means unlimited. Once this many items have been popped, the
            queue reports itself exhausted.
    """

    def __init__(self, max_depth: int, max_pages: int = 0) -> None:
        if max_depth < 1:
            raise ValueError("max_depth must be >= 1")
        if max_pages < 0:
            raise ValueError("max_pages must be >= 0 (0 = unlimited)")

        self.max_depth = max_depth
        self.max_pages = max_pages

        self._pending: deque[QueueItem] = deque()
        self._enqueued: set[str] = set()
        self._dispatched: int = 0

    @classmethod
    def from_config(cls, config: CrawlConfig) -> "CrawlQueue":
        """Build a queue using the depth/page limits from a validated config."""
        return cls(max_depth=config.max_depth, max_pages=config.max_pages)

    # ── core BFS operations ─────────────────────────────────────────────────

    def push(self, url: str, depth: int, logger: logging.Logger | None = None) -> bool:
        """Enqueue a URL at the given depth.

        Returns ``True`` if the URL was added, ``False`` if it was rejected
        because it exceeds ``max_depth`` or was already enqueued this run.
        """
        if depth < 0:
            raise ValueError("depth must be >= 0")

        if depth > self.max_depth:
            if logger is not None:
                log_event(
                    logger,
                    "url_skipped",
                    url=url,
                    depth=depth,
                    reason="max_depth_exceeded",
                    max_depth=self.max_depth,
                )
            return False

        if url in self._enqueued:
            if logger is not None:
                log_event(logger, "url_skipped", url=url, depth=depth, reason="already_queued")
            return False

        self._pending.append(QueueItem(url=url, depth=depth))
        self._enqueued.add(url)
        if logger is not None:
            log_event(logger, "url_discovered", url=url, depth=depth)
        return True

    def pop(self) -> QueueItem | None:
        """Dequeue the next URL in BFS order, or ``None`` if exhausted.

        Counts toward the ``max_pages`` budget. Once the page budget is spent
        the queue refuses to dispatch further items even if pending ones remain.
        """
        if self.is_exhausted():
            return None
        item = self._pending.popleft()
        self._dispatched += 1
        return item

    def is_exhausted(self) -> bool:
        """True if there is nothing left to dispatch or the page budget is spent."""
        if self.max_pages and self._dispatched >= self.max_pages:
            return True
        return not self._pending

    # ── introspection ───────────────────────────────────────────────────────

    @property
    def pending_count(self) -> int:
        """Number of URLs still waiting to be dispatched."""
        return len(self._pending)

    @property
    def dispatched_count(self) -> int:
        """Number of URLs popped so far (counts against ``max_pages``)."""
        return self._dispatched

    def __len__(self) -> int:
        return len(self._pending)

    # ── persistence (CE-006) ────────────────────────────────────────────────

    def snapshot(self) -> dict:
        """Serialize queue state to a plain dict for checkpointing."""
        return {
            "max_depth": self.max_depth,
            "max_pages": self.max_pages,
            "dispatched": self._dispatched,
            "pending": [{"url": i.url, "depth": i.depth} for i in self._pending],
            "enqueued": sorted(self._enqueued),
        }

    @classmethod
    def restore(cls, data: dict) -> "CrawlQueue":
        """Rebuild a queue from a :meth:`snapshot` dict."""
        queue = cls(max_depth=data["max_depth"], max_pages=data.get("max_pages", 0))
        queue._dispatched = data.get("dispatched", 0)
        queue._enqueued = set(data.get("enqueued", []))
        queue._pending = deque(
            QueueItem(url=item["url"], depth=item["depth"]) for item in data.get("pending", [])
        )
        return queue

    def save(self, path: str | Path, logger: logging.Logger | None = None) -> None:
        """Write the queue snapshot to ``path`` as JSON (atomically)."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(self.snapshot(), indent=2), encoding="utf-8")
        tmp.replace(path)
        if logger is not None:
            log_event(
                logger,
                "queue_saved",
                path=str(path),
                pending=self.pending_count,
                dispatched=self._dispatched,
            )

    @classmethod
    def load(cls, path: str | Path, logger: logging.Logger | None = None) -> "CrawlQueue":
        """Load a queue snapshot previously written by :meth:`save`."""
        path = Path(path)
        data = json.loads(path.read_text(encoding="utf-8"))
        queue = cls.restore(data)
        if logger is not None:
            log_event(
                logger,
                "queue_loaded",
                path=str(path),
                pending=queue.pending_count,
                dispatched=queue.dispatched_count,
            )
        return queue


def load_seeds(
    queue: CrawlQueue,
    config: CrawlConfig,
    logger: logging.Logger | None = None,
) -> int:
    """CE-004: Push every configured seed URL onto the queue at depth 0.

    Returns the number of seeds actually queued (duplicates are skipped).
    """
    queued = 0
    for url in config.seed_urls:
        if queue.push(url, depth=0, logger=logger):
            queued += 1
    if logger is not None:
        log_event(logger, "seeds_loaded", seed_count=len(config.seed_urls), queued=queued)
    return queued
