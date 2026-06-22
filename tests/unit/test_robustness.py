"""Robustness & edge-case suite — error paths, logging branches, adversarial input.

Complements the per-feature unit tests by exercising the branches that only
fire when a logger is supplied, when inputs are malformed, or when config is
invalid. Keeps the engine honest about "fails loudly / degrades gracefully".
"""
import json

import pytest
import requests
import yaml

from crawl_engine.config.loader import CrawlConfig, load_config
from crawl_engine.discovery.canonicalize import canonicalize
from crawl_engine.discovery.queue import CrawlQueue, load_seeds
from crawl_engine.extraction.fetcher import HttpFetcher
from crawl_engine.extraction.parser import parse_page
from crawl_engine.logging.logger import setup_logger
from crawl_engine.storage.paths import url_to_path
from crawl_engine.storage.writer import read_existing_hash


def _events(path):
    return [json.loads(line) for line in path.read_text().strip().splitlines()]


def _cfg(**overrides):
    data = {"seed_urls": ["https://www.ohsers.org/members/"], "base_url": "https://www.ohsers.org"}
    data.update(overrides)
    return CrawlConfig(**data)


# ── config validation error paths ─────────────────────────────────────────────

def test_request_timeout_below_one_rejected():
    with pytest.raises(Exception):
        _cfg(request_timeout=0)


def test_load_config_rejects_non_mapping(tmp_path):
    p = tmp_path / "bad.yaml"
    p.write_text("- just\n- a\n- list\n", encoding="utf-8")
    with pytest.raises(ValueError):
        load_config(p)


def test_load_config_reads_valid_file(tmp_path):
    p = tmp_path / "c.yaml"
    p.write_text(yaml.dump({"seed_urls": ["https://www.ohsers.org/m"], "base_url": "https://www.ohsers.org"}), encoding="utf-8")
    assert load_config(p).base_url == "https://www.ohsers.org"


# ── logger re-configuration branch ────────────────────────────────────────────

def test_setup_logger_is_idempotent(tmp_path):
    log_path = tmp_path / "log.jsonl"
    first = setup_logger(log_path, name="reconfig_test")
    handler_count = len(first.handlers)
    second = setup_logger(log_path, name="reconfig_test")
    assert second is first
    assert len(second.handlers) == handler_count  # handlers not doubled


# ── queue logging branches ────────────────────────────────────────────────────

def test_queue_logs_skips_and_persistence(tmp_path):
    log_path = tmp_path / "log.jsonl"
    logger = setup_logger(log_path, name="queue_log_test")
    q = CrawlQueue(max_depth=1)

    assert q.push("https://a", 0, logger=logger) is True       # url_discovered
    assert q.push("https://a", 0, logger=logger) is False      # already_queued
    assert q.push("https://b", 5, logger=logger) is False      # max_depth_exceeded

    path = tmp_path / "q.json"
    q.save(path, logger=logger)                                 # queue_saved
    CrawlQueue.load(path, logger=logger)                        # queue_loaded

    reasons = {e.get("reason") for e in _events(log_path)}
    types = {e["event_type"] for e in _events(log_path)}
    assert "already_queued" in reasons
    assert "max_depth_exceeded" in reasons
    assert {"queue_saved", "queue_loaded"} <= types


def test_load_seeds_logs_summary(tmp_path):
    log_path = tmp_path / "log.jsonl"
    logger = setup_logger(log_path, name="seed_log_test")
    cfg = _cfg(seed_urls=["https://www.ohsers.org/a", "https://www.ohsers.org/b"])
    q = CrawlQueue.from_config(cfg)
    assert load_seeds(q, cfg, logger=logger) == 2
    assert any(e["event_type"] == "seeds_loaded" for e in _events(log_path))


# ── fetcher logging + non-transient error ─────────────────────────────────────

class _Resp:
    def __init__(self, status=200, text="<html></html>"):
        self.status_code = status
        self.text = text
        self.headers = {"Content-Type": "text/html"}
        self.url = "https://www.ohsers.org/x"


class _Session:
    def __init__(self, outcome):
        self.outcome = outcome
        self.headers = {}

    def get(self, url, timeout=None, allow_redirects=True):
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


def test_fetcher_logs_page_fetched(tmp_path):
    log_path = tmp_path / "log.jsonl"
    logger = setup_logger(log_path, name="fetch_ok_log")
    f = HttpFetcher(_cfg(), session=_Session(_Resp(200)), sleep=lambda s: None)
    f.fetch("https://www.ohsers.org/x", logger=logger)
    assert any(e["event_type"] == "page_fetched" for e in _events(log_path))


def test_fetcher_logs_page_failed_on_404(tmp_path):
    log_path = tmp_path / "log.jsonl"
    logger = setup_logger(log_path, name="fetch_404_log")
    f = HttpFetcher(_cfg(), session=_Session(_Resp(404)), sleep=lambda s: None)
    result = f.fetch("https://www.ohsers.org/x", logger=logger)
    assert result.ok is False
    assert any(e["event_type"] == "page_failed" for e in _events(log_path))


def test_fetcher_non_transient_request_error_not_retried(tmp_path):
    log_path = tmp_path / "log.jsonl"
    logger = setup_logger(log_path, name="fetch_badurl_log")
    f = HttpFetcher(
        _cfg(retry={"max_attempts": 3, "backoff_factor": 2.0}),
        session=_Session(requests.exceptions.MissingSchema("bad url")),
        sleep=lambda s: None,
    )
    result = f.fetch("not-a-url", logger=logger)
    assert result.ok is False
    assert result.error.startswith("request_error")
    assert result.attempts == 1  # not retried


# ── read_existing_hash malformed-frontmatter robustness ───────────────────────

def test_read_hash_none_when_no_closing_delimiter(tmp_path):
    p = tmp_path / "a.md"
    p.write_text("---\ncontent_hash: sha256:x\n(no closing)", encoding="utf-8")
    assert read_existing_hash(p) is None


def test_read_hash_none_on_malformed_yaml(tmp_path):
    p = tmp_path / "b.md"
    p.write_text("---\n: : : not yaml :\n---\nbody", encoding="utf-8")
    assert read_existing_hash(p) is None


def test_read_hash_none_when_field_absent(tmp_path):
    p = tmp_path / "c.md"
    p.write_text("---\ntitle: T\ndepth: 1\n---\nbody", encoding="utf-8")
    assert read_existing_hash(p) is None


def test_read_hash_none_when_frontmatter_not_mapping(tmp_path):
    p = tmp_path / "d.md"
    p.write_text("---\n- a\n- b\n---\nbody", encoding="utf-8")
    assert read_existing_hash(p) is None


# ── adversarial parsing / mapping / canonicalization ──────────────────────────

def test_parse_truncated_html_does_not_raise():
    page = parse_page("<html><body><main><h1>Hi<p>unclosed", "https://www.ohsers.org/m", _cfg())
    assert "Hi" in page.text


def test_parse_preserves_unicode():
    html = "<html><body><main><p>café résumé 日本語</p></main></body></html>"
    page = parse_page(html, "https://www.ohsers.org/m", _cfg())
    assert "café" in page.text and "日本語" in page.text


def test_url_to_path_handles_unicode_and_depth():
    p = url_to_path("https://www.ohsers.org/members/café/2024", "out")
    assert p.name == "index.md"
    assert "café" in str(p)


def test_canonicalize_lowercases_host_with_port():
    out = canonicalize("https://WWW.OHSERS.ORG:8080/Members/?utm_source=x#f")
    assert out == "https://www.ohsers.org:8080/Members"


def test_canonicalize_empty_path_no_trailing_slash():
    assert canonicalize("https://www.ohsers.org") == "https://www.ohsers.org"


# ── default-clock branches (crawled_at defaults to now) ───────────────────────

class _SeqSession:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.headers = {}

    def get(self, url, timeout=None, allow_redirects=True):
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def test_fetcher_logs_retry_event(tmp_path):
    log_path = tmp_path / "log.jsonl"
    logger = setup_logger(log_path, name="retry_event_log")
    f = HttpFetcher(
        _cfg(retry={"max_attempts": 3, "backoff_factor": 2.0}),
        session=_SeqSession([_Resp(500), _Resp(200)]),
        sleep=lambda s: None,
    )
    f.fetch("https://www.ohsers.org/x", logger=logger)
    assert any(e["event_type"] == "fetch_retry" for e in _events(log_path))


def test_build_document_defaults_crawled_at_to_now():
    from crawl_engine.extraction.parser import ParsedPage
    from crawl_engine.storage.markdown import build_markdown_document

    page = ParsedPage(url="https://x", title="T", content_html="<p>b</p>",
                      text="b", source_section="", headings=[], metadata={})
    doc, _ = build_markdown_document(page, 1, "https://x")  # no crawled_at supplied
    assert "crawled_at:" in doc


def test_save_artifact_defaults_crawled_at_to_now(tmp_path):
    from crawl_engine.extraction.parser import ParsedPage
    from crawl_engine.storage.writer import save_artifact

    cfg = _cfg(output_dir=tmp_path / "raw")
    page = ParsedPage(url="https://www.ohsers.org/m", title="T", content_html="<p>b</p>",
                      text="b", source_section="m", headings=[], metadata={})
    result = save_artifact(page, 1, cfg)  # no crawled_at supplied
    assert result.written is True
    assert result.path.exists()
