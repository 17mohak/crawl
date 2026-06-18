"""Shared fixtures/helpers for integration tests.

Provides a ``LocalSiteFetcher`` that serves an in-memory OHSERS-like site, so the
full crawl pipeline can run end-to-end without any network access. This keeps
integration tests deterministic and fast while still exercising the real
fetch -> parse -> store -> discover loop.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from crawl_engine.config.loader import CrawlConfig
from crawl_engine.extraction.fetcher import FetchResult

BASE = "https://www.ohsers.org"

FIXED_CLOCK = lambda: datetime(2026, 6, 18, 10, 0, 0, tzinfo=timezone.utc)  # noqa: E731


def _page(title: str, body: str, *links: str) -> str:
    anchors = "".join(f'<a href="{href}">link</a>' for href in links)
    return (
        f"<html lang='en'><head><title>{title}</title>"
        f"<meta name='description' content='{title} page'></head>"
        f"<body><nav>site nav</nav>"
        f"<main><h1>{title}</h1><p>{body}</p>{anchors}</main>"
        f"<footer>footer junk</footer><script>track()</script></body></html>"
    )


# A small but representative site: seed links out to several sections, some
# pages link back (cycles), one external link, and one cross-link.
SITE: dict[str, str] = {
    f"{BASE}/members": _page(
        "Members", "Member overview.",
        "/members/service-retirement", "/members/forms",
        "https://www.google.com/external", "/members",
    ),
    f"{BASE}/members/service-retirement": _page(
        "Service Retirement", "You may retire at a certain age.",
        "/members/forms", "/members",
    ),
    f"{BASE}/members/forms": _page(
        "Forms", "Downloadable forms.", "/members/service-retirement",
    ),
}


class LocalSiteFetcher:
    """Serves pages from an in-memory site dict; records what was fetched.

    Optional ``fail`` set marks URLs that should return a 5xx-style failure, and
    ``boom`` marks URLs whose processing should raise (to exercise CE-038/CE-044).
    """

    def __init__(self, site=None, fail=None, boom=None):
        self.site = dict(SITE if site is None else site)
        self.fail = set(fail or [])
        self.boom = set(boom or [])
        self.fetched: list[str] = []

    def fetch(self, url, logger=None):
        self.fetched.append(url)
        if url in self.boom:
            raise RuntimeError("processing boom")
        if url in self.fail:
            return FetchResult(url=url, ok=False, status_code=503, error="http_503", attempts=3)
        if url not in self.site:
            return FetchResult(url=url, ok=False, status_code=404, error="http_404", attempts=1)
        return FetchResult(
            url=url, ok=True, status_code=200, html=self.site[url],
            content_type="text/html; charset=utf-8", final_url=url, attempts=1,
        )


@pytest.fixture
def make_config():
    def _make(tmp_path, **overrides):
        data = {
            "seed_urls": [f"{BASE}/members/"],
            "base_url": BASE,
            "output_dir": tmp_path / "raw",
            "checkpoint_path": tmp_path / "checkpoint.json",
            "log_path": tmp_path / "crawl.jsonl",
            "max_depth": 4,
        }
        data.update(overrides)
        return CrawlConfig(**data)

    return _make
