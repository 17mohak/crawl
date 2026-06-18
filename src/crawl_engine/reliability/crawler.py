"""End-to-end crawl workflow.

CE-035: Crawl workflow integration  (FR-001..FR-009 / AC-001..AC-006)
CE-037: Structured event logging    (FR-022, FR-023 / AC-015)
CE-038: Failure isolation           (FR-021 / AC-014 — one bad page never stops the crawl)

The :class:`Crawler` ties the feature groups together into one BFS loop:

    seed -> pop URL -> fetch -> parse -> save -> extract links
         -> canonicalize + dedup -> enqueue -> repeat until exhausted

Every per-page step runs inside a guard so that a single fetch/parse/save
failure is logged and counted, and the crawl moves on to the next URL (CE-038).
Progress is checkpointed every ``checkpoint_interval`` pages so the run can be
resumed (CE-036).
"""
from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Callable

from crawl_engine.config.loader import CrawlConfig
from crawl_engine.discovery.canonicalize import canonicalize
from crawl_engine.discovery.links import extract_links
from crawl_engine.discovery.queue import CrawlQueue, QueueItem
from crawl_engine.discovery.registry import SeenRegistry
from crawl_engine.extraction.fetcher import HttpFetcher
from crawl_engine.extraction.parser import parse_page
from crawl_engine.logging.logger import log_event
from crawl_engine.reliability.checkpoint import (
    checkpoint_exists,
    load_checkpoint,
    save_checkpoint,
)
from crawl_engine.storage.writer import save_artifact


@dataclass
class CrawlStats:
    """Running tallies for one crawl, also persisted in the checkpoint."""

    pages_crawled: int = 0
    pages_failed: int = 0
    pages_skipped: int = 0
    artifacts_written: int = 0
    artifacts_unchanged: int = 0
    links_discovered: int = 0


class Crawler:
    """Runs a complete BFS crawl from seed URLs to Markdown artifacts."""

    def __init__(
        self,
        config: CrawlConfig,
        logger: logging.Logger,
        fetcher: HttpFetcher | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.config = config
        self.logger = logger
        self.fetcher = fetcher or HttpFetcher(config)
        self.queue = CrawlQueue.from_config(config)
        self.seen = SeenRegistry()
        self.stats = CrawlStats()
        # Injectable clock for the crawled_at timestamp. A fixed clock makes a
        # whole crawl byte-for-byte reproducible (determinism validation, CE-041).
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    # ── public API ────────────────────────────────────────────────────────────

    def run(self, resume: bool = False) -> CrawlStats:
        """Run the crawl to completion and return the final stats."""
        if resume and checkpoint_exists(self.config.checkpoint_path):
            self.queue, self.seen, stats_dict = load_checkpoint(self.config.checkpoint_path)
            self.stats = CrawlStats(**stats_dict)
            log_event(
                self.logger,
                "crawl_resumed",
                pending=self.queue.pending_count,
                seen=len(self.seen),
            )
        else:
            self._seed()

        log_event(
            self.logger,
            "crawl_started",
            seed_count=len(self.config.seed_urls),
            max_depth=self.config.max_depth,
            max_pages=self.config.max_pages,
            resume=resume,
        )

        processed_since_checkpoint = 0
        while not self.queue.is_exhausted():
            item = self.queue.pop()
            if item is None:
                break
            self._process_page(item)
            processed_since_checkpoint += 1
            if processed_since_checkpoint >= self.config.checkpoint_interval:
                self._checkpoint()
                processed_since_checkpoint = 0

        self._checkpoint()
        log_event(
            self.logger,
            "crawl_finished",
            pages_crawled=self.stats.pages_crawled,
            pages_failed=self.stats.pages_failed,
            pages_skipped=self.stats.pages_skipped,
            artifacts_written=self.stats.artifacts_written,
            artifacts_unchanged=self.stats.artifacts_unchanged,
        )
        return self.stats

    # ── internals ──────────────────────────────────────────────────────────────

    def _seed(self) -> None:
        """Canonicalize seed URLs, register them, and queue them at depth 0."""
        for url in self.config.seed_urls:
            canonical = canonicalize(url, tracking_params=self.config.tracking_params)
            if self.seen.mark_seen(canonical):
                self.queue.push(canonical, depth=0, logger=self.logger)

    def _process_page(self, item: QueueItem) -> None:
        """Fetch, parse, save, and expand one URL — isolated from crawl failure.

        CE-038: any exception here is caught, logged, counted, and swallowed so
        the loop continues with the next URL.
        """
        try:
            result = self.fetcher.fetch(item.url, logger=self.logger)
            if not result.ok:
                # fetcher already logged page_failed with the reason
                self.stats.pages_failed += 1
                return
            if not result.is_html:
                self.stats.pages_skipped += 1
                log_event(self.logger, "url_skipped", url=item.url, reason="non_html")
                return

            page = parse_page(result.html, item.url, self.config)
            save = save_artifact(
                page, item.depth, self.config, crawled_at=self._clock(), logger=self.logger
            )
            self.stats.pages_crawled += 1
            if save.written:
                self.stats.artifacts_written += 1
            else:
                self.stats.artifacts_unchanged += 1

            self._enqueue_links(result.html, item)
        except Exception as exc:  # noqa: BLE001 — failure isolation is the point
            self.stats.pages_failed += 1
            log_event(
                self.logger,
                "page_failed",
                url=item.url,
                reason=f"{type(exc).__name__}: {exc}",
                depth=item.depth,
            )

    def _enqueue_links(self, html: str, item: QueueItem) -> None:
        """Extract internal links, canonicalize, dedup, and enqueue the new ones."""
        links = extract_links(html, item.url, self.config, logger=self.logger)
        self.stats.links_discovered += len(links.internal)
        for url in links.internal:
            canonical = canonicalize(url, tracking_params=self.config.tracking_params)
            if self.seen.mark_seen(canonical):
                self.queue.push(canonical, depth=item.depth + 1, logger=self.logger)

    def _checkpoint(self) -> None:
        save_checkpoint(
            self.config.checkpoint_path, self.queue, self.seen, asdict(self.stats)
        )
