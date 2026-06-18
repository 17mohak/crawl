"""Unit tests for URL Discovery link extraction.

CE-009: Internal link extraction   (AC-002)
CE-010: External link detection    (AC-002)
CE-011: Allowed path filtering      (AC-002)
"""
from crawl_engine.config.loader import CrawlConfig
from crawl_engine.discovery.links import extract_links


BASE = "https://www.ohsers.org"
PAGE = "https://www.ohsers.org/members/"


def make_config(allowed_paths=None) -> CrawlConfig:
    return CrawlConfig(
        seed_urls=["https://www.ohsers.org/members/"],
        base_url=BASE,
        allowed_paths=allowed_paths or [],
    )


# ── internal link extraction (CE-009) ─────────────────────────────────────────

def test_extracts_absolute_internal_link():
    html = '<a href="https://www.ohsers.org/members/retirement/">Retirement</a>'
    result = extract_links(html, PAGE, make_config())
    assert result.internal == ["https://www.ohsers.org/members/retirement/"]


def test_resolves_relative_link_against_page_url():
    html = '<a href="retirement/">Retirement</a>'
    result = extract_links(html, PAGE, make_config())
    assert result.internal == ["https://www.ohsers.org/members/retirement/"]


def test_resolves_root_relative_link():
    html = '<a href="/employers/">Employers</a>'
    result = extract_links(html, PAGE, make_config())
    assert result.internal == ["https://www.ohsers.org/employers/"]


def test_deduplicates_repeated_links():
    html = '<a href="/a/">A</a><a href="/a/">A again</a>'
    result = extract_links(html, PAGE, make_config())
    assert result.internal == ["https://www.ohsers.org/a/"]


def test_preserves_document_order():
    html = '<a href="/b/">B</a><a href="/a/">A</a>'
    result = extract_links(html, PAGE, make_config())
    assert result.internal == ["https://www.ohsers.org/b/", "https://www.ohsers.org/a/"]


def test_anchors_without_href_ignored():
    html = '<a name="top">anchor</a><a href="/a/">A</a>'
    result = extract_links(html, PAGE, make_config())
    assert result.internal == ["https://www.ohsers.org/a/"]


def test_non_crawlable_schemes_ignored():
    html = (
        '<a href="mailto:info@ohsers.org">Email</a>'
        '<a href="tel:+18005551234">Call</a>'
        '<a href="javascript:void(0)">JS</a>'
        '<a href="/a/">A</a>'
    )
    result = extract_links(html, PAGE, make_config())
    assert result.internal == ["https://www.ohsers.org/a/"]
    assert result.external == []


# ── external link detection (CE-010) ──────────────────────────────────────────

def test_external_link_detected_and_separated():
    html = '<a href="https://www.google.com/">Google</a><a href="/a/">A</a>'
    result = extract_links(html, PAGE, make_config())
    assert result.external == ["https://www.google.com/"]
    assert result.internal == ["https://www.ohsers.org/a/"]


def test_external_link_logged(tmp_path):
    import json
    from crawl_engine.logging.logger import setup_logger

    log_path = tmp_path / "crawl.jsonl"
    logger = setup_logger(log_path, name="test_links_external")
    html = '<a href="https://external.example.com/x">X</a>'
    extract_links(html, PAGE, make_config(), logger=logger)

    events = [json.loads(line) for line in log_path.read_text().strip().splitlines()]
    skipped = [e for e in events if e["event_type"] == "url_skipped"]
    assert any(e["reason"] == "external" for e in skipped)


# ── allowed path filtering (CE-011) ───────────────────────────────────────────

def test_allowed_paths_keeps_matching_internal_links():
    html = '<a href="/members/x">in</a><a href="/secret/y">out</a>'
    result = extract_links(html, PAGE, make_config(allowed_paths=["/members/"]))
    assert result.internal == ["https://www.ohsers.org/members/x"]
    assert result.disallowed == ["https://www.ohsers.org/secret/y"]


def test_empty_allowed_paths_allows_all_internal():
    html = '<a href="/members/x">a</a><a href="/anything/y">b</a>'
    result = extract_links(html, PAGE, make_config(allowed_paths=[]))
    assert len(result.internal) == 2
    assert result.disallowed == []


def test_disallowed_path_logged(tmp_path):
    import json
    from crawl_engine.logging.logger import setup_logger

    log_path = tmp_path / "crawl.jsonl"
    logger = setup_logger(log_path, name="test_links_disallowed")
    html = '<a href="/secret/y">out</a>'
    extract_links(html, PAGE, make_config(allowed_paths=["/members/"]), logger=logger)

    events = [json.loads(line) for line in log_path.read_text().strip().splitlines()]
    assert any(
        e["event_type"] == "url_skipped" and e["reason"] == "path_not_allowed" for e in events
    )


def test_empty_html_yields_no_links():
    result = extract_links("", PAGE, make_config())
    assert result.internal == []
    assert result.external == []
    assert result.disallowed == []
