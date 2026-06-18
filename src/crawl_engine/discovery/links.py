"""URL Discovery: link extraction and filtering.

CE-009: Internal link extraction   (FR-004 / AC-002 — internal links discovered correctly)
CE-010: External link detection    (FR-005 / AC-002 — external links skipped and logged)
CE-011: Allowed path filtering     (FR-004 / AC-002 — disallowed paths skipped)

Given the HTML of a fetched page, pull every ``<a href>``, resolve relative
references against the page URL, then sort each candidate into one of three
buckets:

* **internal & allowed** — same host as ``base_url`` and (if ``allowed_paths``
  is configured) under an allowed path prefix. These get returned for queuing.
* **external** — a different host. Skipped (CE-010).
* **disallowed** — same host but outside the allowed paths. Skipped (CE-011).

Note on host matching: this compares the exact host (case-insensitively).
Normalizing host variants such as ``ohsers.org`` vs ``www.ohsers.org`` is the
job of the canonicalization group (CE-012..CE-016) and is applied before a URL
reaches the Seen registry; it is intentionally not done here.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from crawl_engine.config.loader import CrawlConfig
from crawl_engine.logging.logger import log_event

# Schemes we never enqueue — only real HTTP(S) pages get crawled.
_CRAWLABLE_SCHEMES = {"http", "https"}


@dataclass
class LinkExtractionResult:
    """The categorized outcome of extracting links from one page."""

    internal: list[str] = field(default_factory=list)
    external: list[str] = field(default_factory=list)
    disallowed: list[str] = field(default_factory=list)


def _same_host(url: str, base_url: str) -> bool:
    """True if ``url`` has the same host as ``base_url`` (case-insensitive)."""
    return urlparse(url).netloc.lower() == urlparse(base_url).netloc.lower()


def _path_allowed(url: str, allowed_paths: list[str]) -> bool:
    """True if the URL's path is under one of the allowed prefixes.

    An empty ``allowed_paths`` list means every path on the host is allowed.
    """
    if not allowed_paths:
        return True
    path = urlparse(url).path
    return any(path.startswith(prefix) for prefix in allowed_paths)


def _iter_hrefs(html: str) -> list[str]:
    """Yield the raw href of every anchor in document order."""
    soup = BeautifulSoup(html, "lxml")
    hrefs = []
    for anchor in soup.find_all("a", href=True):
        href = anchor["href"].strip()
        if href:
            hrefs.append(href)
    return hrefs


def extract_links(
    html: str,
    page_url: str,
    config: CrawlConfig,
    logger: logging.Logger | None = None,
) -> LinkExtractionResult:
    """Extract and categorize all links from a page's HTML.

    Args:
        html: Raw HTML of the fetched page.
        page_url: Absolute URL the HTML was fetched from (used to resolve
            relative hrefs).
        config: Crawl config supplying ``base_url`` and ``allowed_paths``.
        logger: Optional logger; external/disallowed skips are logged via
            ``log_event`` when provided.

    Returns:
        A :class:`LinkExtractionResult` with deduplicated links in each bucket,
        preserving document order (deterministic for a given page).
    """
    result = LinkExtractionResult()
    seen: set[str] = set()

    for href in _iter_hrefs(html):
        absolute = urljoin(page_url, href)
        scheme = urlparse(absolute).scheme.lower()
        if scheme not in _CRAWLABLE_SCHEMES:
            continue  # mailto:, tel:, javascript:, etc. — not crawlable

        if absolute in seen:
            continue
        seen.add(absolute)

        if not _same_host(absolute, config.base_url):
            result.external.append(absolute)
            if logger is not None:
                log_event(logger, "url_skipped", url=absolute, reason="external", source=page_url)
            continue

        if not _path_allowed(absolute, config.allowed_paths):
            result.disallowed.append(absolute)
            if logger is not None:
                log_event(
                    logger,
                    "url_skipped",
                    url=absolute,
                    reason="path_not_allowed",
                    source=page_url,
                )
            continue

        result.internal.append(absolute)

    if logger is not None:
        log_event(
            logger,
            "links_extracted",
            source=page_url,
            internal=len(result.internal),
            external=len(result.external),
            disallowed=len(result.disallowed),
        )
    return result
