"""Unit tests for the end-to-end crawl workflow.

CE-035 (integration), CE-037 (events), CE-038 (failure isolation).
A fake fetcher serves canned pages so the whole loop runs without network.
"""
import json

from crawl_engine.config.loader import CrawlConfig
from crawl_engine.extraction.fetcher import FetchResult
from crawl_engine.logging.logger import setup_logger
from crawl_engine.reliability.crawler import Crawler

BASE = "https://www.ohsers.org"


class FakeFetcher:
    """Serves canned HTML per canonical URL; unknown URLs 404, marked ones raise."""

    def __init__(self, pages: dict[str, str], raise_on: set[str] | None = None,
                 non_html: set[str] | None = None):
        self.pages = pages
        self.raise_on = raise_on or set()
        self.non_html = non_html or set()
        self.fetched: list[str] = []

    def fetch(self, url, logger=None):
        self.fetched.append(url)
        if url in self.raise_on:
            raise RuntimeError("boom")
        if url not in self.pages:
            return FetchResult(url=url, ok=False, status_code=404, error="http_404", attempts=1)
        ctype = "application/pdf" if url in self.non_html else "text/html"
        return FetchResult(
            url=url, ok=True, status_code=200, html=self.pages[url],
            content_type=ctype, final_url=url, attempts=1,
        )


def make_config(tmp_path, **overrides) -> CrawlConfig:
    data = {
        "seed_urls": [f"{BASE}/members/"],
        "base_url": BASE,
        "output_dir": tmp_path / "raw",
        "checkpoint_path": tmp_path / "checkpoint.json",
        "log_path": tmp_path / "crawl.jsonl",
        "max_depth": 3,
    }
    data.update(overrides)
    return CrawlConfig(**data)


def page(title, *links):
    anchors = "".join(f'<a href="{href}">x</a>' for href in links)
    return f"<html><head><title>{title}</title></head><body><main><h1>{title}</h1>{anchors}</main></body></html>"


# ── CE-035: end-to-end integration ────────────────────────────────────────────

def test_crawl_follows_links_and_saves_artifacts(tmp_path):
    pages = {
        f"{BASE}/members": page("Members", "/members/retirement", "/members/forms"),
        f"{BASE}/members/retirement": page("Retirement"),
        f"{BASE}/members/forms": page("Forms"),
    }
    cfg = make_config(tmp_path)
    fetcher = FakeFetcher(pages)
    logger = setup_logger(cfg.log_path, name="test_crawl_e2e")

    stats = Crawler(cfg, logger, fetcher=fetcher).run()

    assert stats.pages_crawled == 3
    assert (cfg.output_dir / "members" / "index.md").exists()
    assert (cfg.output_dir / "members" / "retirement" / "index.md").exists()
    assert (cfg.output_dir / "members" / "forms" / "index.md").exists()


def test_crawl_dedups_repeated_links(tmp_path):
    # Both pages link back to each other and to themselves.
    pages = {
        f"{BASE}/members": page("Members", "/members/a", "/members/a", "/members/"),
        f"{BASE}/members/a": page("A", "/members", "/members/a"),
    }
    cfg = make_config(tmp_path)
    fetcher = FakeFetcher(pages)
    logger = setup_logger(cfg.log_path, name="test_crawl_dedup")

    Crawler(cfg, logger, fetcher=fetcher).run()

    # Each canonical URL fetched exactly once despite many inbound links.
    assert sorted(fetcher.fetched) == [f"{BASE}/members", f"{BASE}/members/a"]


def test_max_pages_limits_crawl(tmp_path):
    pages = {
        f"{BASE}/members": page("Members", "/members/a", "/members/b", "/members/c"),
        f"{BASE}/members/a": page("A"),
        f"{BASE}/members/b": page("B"),
        f"{BASE}/members/c": page("C"),
    }
    cfg = make_config(tmp_path, max_pages=2)
    fetcher = FakeFetcher(pages)
    logger = setup_logger(cfg.log_path, name="test_crawl_maxpages")

    Crawler(cfg, logger, fetcher=fetcher).run()
    assert len(fetcher.fetched) == 2


def test_non_html_skipped(tmp_path):
    pages = {
        f"{BASE}/members": page("Members", "/members/doc"),
        f"{BASE}/members/doc": "%PDF-1.4 binary",
    }
    cfg = make_config(tmp_path)
    fetcher = FakeFetcher(pages, non_html={f"{BASE}/members/doc"})
    logger = setup_logger(cfg.log_path, name="test_crawl_nonhtml")

    stats = Crawler(cfg, logger, fetcher=fetcher).run()
    assert stats.pages_skipped == 1
    assert not (cfg.output_dir / "members" / "doc" / "index.md").exists()


# ── CE-038: failure isolation ─────────────────────────────────────────────────

def test_fetch_failure_does_not_stop_crawl(tmp_path):
    pages = {
        f"{BASE}/members": page("Members", "/members/broken", "/members/ok"),
        f"{BASE}/members/ok": page("OK"),
        # /members/broken is absent -> 404
    }
    cfg = make_config(tmp_path)
    fetcher = FakeFetcher(pages)
    logger = setup_logger(cfg.log_path, name="test_crawl_fetchfail")

    stats = Crawler(cfg, logger, fetcher=fetcher).run()
    assert stats.pages_failed == 1
    assert stats.pages_crawled == 2  # members + ok
    assert (cfg.output_dir / "members" / "ok" / "index.md").exists()


def test_exception_during_processing_is_isolated(tmp_path):
    pages = {
        f"{BASE}/members": page("Members", "/members/boom", "/members/ok"),
        f"{BASE}/members/boom": page("Boom"),
        f"{BASE}/members/ok": page("OK"),
    }
    cfg = make_config(tmp_path)
    fetcher = FakeFetcher(pages, raise_on={f"{BASE}/members/boom"})
    logger = setup_logger(cfg.log_path, name="test_crawl_exc")

    stats = Crawler(cfg, logger, fetcher=fetcher).run()
    assert stats.pages_failed == 1
    assert (cfg.output_dir / "members" / "ok" / "index.md").exists()


# ── CE-037: structured events ─────────────────────────────────────────────────

def test_crawl_emits_started_and_finished_events(tmp_path):
    pages = {f"{BASE}/members": page("Members")}
    cfg = make_config(tmp_path)
    logger = setup_logger(cfg.log_path, name="test_crawl_events")

    Crawler(cfg, logger, fetcher=FakeFetcher(pages)).run()

    events = [json.loads(line) for line in cfg.log_path.read_text().strip().splitlines()]
    types = {e["event_type"] for e in events}
    assert "crawl_started" in types
    assert "crawl_finished" in types
    finished = next(e for e in events if e["event_type"] == "crawl_finished")
    assert finished["pages_crawled"] == 1


# ── CE-036: resume ────────────────────────────────────────────────────────────

def test_resume_skips_already_crawled(tmp_path):
    pages = {
        f"{BASE}/members": page("Members", "/members/a"),
        f"{BASE}/members/a": page("A"),
    }
    cfg = make_config(tmp_path)

    # First run completes fully and writes a checkpoint.
    logger = setup_logger(cfg.log_path, name="test_resume_1")
    Crawler(cfg, logger, fetcher=FakeFetcher(pages)).run()

    # Resume: queue is exhausted, so a fresh fetcher should fetch nothing.
    fetcher2 = FakeFetcher(pages)
    logger2 = setup_logger(cfg.log_path, name="test_resume_2")
    Crawler(cfg, logger2, fetcher=fetcher2).run(resume=True)
    assert fetcher2.fetched == []
