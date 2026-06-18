"""Artifact writing: atomic writes, skip-unchanged, and save orchestration.

CE-031: Atomic file write support  (FR-008 / AC-005 — no corrupt partial files)
CE-033: Skip unchanged content     (FR-009 / AC-006 — no rewrite when content unchanged)
CE-034: Save markdown artifacts    (FR-006, FR-007 / AC-004 — markdown file saved)

``save_artifact`` ties the storage group together: map URL -> path, build the
Markdown document, and either write it atomically or skip it if the content is
unchanged since the last run. Skipping is what gives the crawl idempotency
(NFR-002 / CE-042) and lets re-runs leave the output directory byte-identical
(NFR-001 / CE-041).
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import yaml

from crawl_engine.config.loader import CrawlConfig
from crawl_engine.discovery.canonicalize import canonicalize
from crawl_engine.extraction.parser import ParsedPage
from crawl_engine.logging.logger import log_event
from crawl_engine.storage.markdown import build_markdown_document
from crawl_engine.storage.paths import url_to_path


@dataclass
class SaveResult:
    """Outcome of attempting to save one artifact."""

    path: Path
    content_hash: str
    written: bool
    skipped: bool


def atomic_write(path: str | Path, text: str) -> None:
    """CE-030 + CE-031: create parent dirs and write ``text`` atomically.

    Writes to a temp file in the same directory then ``os.replace``s it into
    place. ``os.replace`` is atomic on the same filesystem, so a reader never
    sees a half-written file even if the process is killed mid-write.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)  # CE-030
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)  # CE-031: atomic swap


def read_existing_hash(path: str | Path) -> str | None:
    """Return the ``content_hash`` from an existing artifact's frontmatter, if any.

    Returns ``None`` if the file is missing, has no frontmatter, or can't be
    parsed — in all of which cases the caller should treat the page as changed.
    """
    path = Path(path)
    if not path.exists():
        return None

    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return None

    end = text.find("\n---", 3)
    if end == -1:
        return None

    try:
        data = yaml.safe_load(text[3:end])
    except yaml.YAMLError:
        return None

    if isinstance(data, dict):
        value = data.get("content_hash")
        return value if isinstance(value, str) else None
    return None


def save_artifact(
    page: ParsedPage,
    depth: int,
    config: CrawlConfig,
    crawled_at: datetime | None = None,
    logger: logging.Logger | None = None,
) -> SaveResult:
    """CE-033 + CE-034: save a parsed page as a Markdown artifact, or skip it.

    Computes the deterministic output path and document, then compares the new
    content hash against any existing artifact's stored hash. If they match the
    write is skipped (CE-033); otherwise the document is written atomically.
    """
    if crawled_at is None:
        crawled_at = datetime.now(timezone.utc)

    canonical = canonicalize(page.url, tracking_params=config.tracking_params)
    path = url_to_path(canonical, config.output_dir)
    document, content_hash = build_markdown_document(page, depth, canonical, crawled_at)

    existing_hash = read_existing_hash(path)
    if existing_hash == content_hash:
        if logger is not None:
            log_event(
                logger,
                "file_skipped",
                url=page.url,
                path=str(path),
                reason="unchanged",
                content_hash=content_hash,
            )
        return SaveResult(path=path, content_hash=content_hash, written=False, skipped=True)

    atomic_write(path, document)
    if logger is not None:
        log_event(
            logger,
            "file_saved",
            url=page.url,
            path=str(path),
            content_hash=content_hash,
            depth=depth,
        )
    return SaveResult(path=path, content_hash=content_hash, written=True, skipped=False)
