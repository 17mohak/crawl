"""Unit tests for Markdown conversion, frontmatter, and hashing.

CE-027 (HTML->MD), CE-028 (frontmatter), CE-032 (content hash). AC-004 / AC-006.
"""
from datetime import datetime, timezone

import yaml

from crawl_engine.extraction.parser import ParsedPage
from crawl_engine.storage.markdown import (
    build_markdown_document,
    compute_content_hash,
    format_timestamp,
    html_to_markdown,
    render_frontmatter,
)

FIXED_TIME = datetime(2026, 6, 18, 10, 23, 0, tzinfo=timezone.utc)


def make_page(**overrides) -> ParsedPage:
    data = {
        "url": "https://www.ohsers.org/members/service-retirement/",
        "title": "Service Retirement",
        "content_html": "<h1>Service Retirement</h1><p>You may retire.</p>",
        "text": "Service Retirement You may retire.",
        "source_section": "members",
        "headings": ["Service Retirement"],
        "metadata": {},
    }
    data.update(overrides)
    return ParsedPage(**data)


# ── CE-027: HTML to Markdown ──────────────────────────────────────────────────

def test_html_converted_to_markdown():
    md = html_to_markdown("<h1>Title</h1><p>Body text.</p>")
    assert "# Title" in md
    assert "Body text." in md


def test_links_preserved_in_markdown():
    md = html_to_markdown('<p>See <a href="https://x.org">here</a></p>')
    assert "https://x.org" in md


def test_empty_html_yields_empty_markdown():
    assert html_to_markdown("") == ""


def test_markdown_conversion_is_deterministic():
    html = "<h1>T</h1><p>Some longer paragraph that could be wrapped at a column.</p>"
    assert html_to_markdown(html) == html_to_markdown(html)


# ── CE-032: content hash ──────────────────────────────────────────────────────

def test_content_hash_prefixed_and_consistent():
    h1 = compute_content_hash("hello")
    h2 = compute_content_hash("hello")
    assert h1 == h2
    assert h1.startswith("sha256:")


def test_content_hash_changes_with_content():
    assert compute_content_hash("a") != compute_content_hash("b")


# ── timestamp formatting ──────────────────────────────────────────────────────

def test_timestamp_formatted_with_trailing_z():
    assert format_timestamp(FIXED_TIME) == "2026-06-18T10:23:00Z"


# ── CE-028: frontmatter ───────────────────────────────────────────────────────

def test_frontmatter_delimited_and_parseable():
    fm = render_frontmatter({"url": "https://x", "depth": 2})
    assert fm.startswith("---\n")
    assert fm.rstrip().endswith("---")
    inner = fm.split("---\n", 1)[1].rsplit("---", 1)[0]
    parsed = yaml.safe_load(inner)
    assert parsed == {"url": "https://x", "depth": 2}


def test_frontmatter_preserves_field_order():
    fm = render_frontmatter({"url": "u", "title": "t", "depth": 1})
    assert fm.index("url:") < fm.index("title:") < fm.index("depth:")


# ── build_markdown_document integration ───────────────────────────────────────

def _frontmatter_dict(document: str) -> dict:
    inner = document.split("---\n", 1)[1].rsplit("---", 1)[0]
    return yaml.safe_load(inner)


def test_document_contains_all_inferred_frontmatter_fields():
    page = make_page()
    doc, content_hash = build_markdown_document(
        page, depth=2, canonical_url="https://www.ohsers.org/members/service-retirement",
        crawled_at=FIXED_TIME,
    )
    fm = _frontmatter_dict(doc)
    assert set(fm) == {
        "url", "canonical_url", "title", "crawled_at", "content_hash", "depth", "source_section",
    }
    assert fm["canonical_url"] == "https://www.ohsers.org/members/service-retirement"
    assert fm["title"] == "Service Retirement"
    assert fm["crawled_at"] == "2026-06-18T10:23:00Z"
    assert fm["depth"] == 2
    assert fm["source_section"] == "members"
    assert fm["content_hash"] == content_hash


def test_body_follows_frontmatter():
    page = make_page()
    doc, _ = build_markdown_document(page, 1, "https://x", crawled_at=FIXED_TIME)
    assert "# Service Retirement" in doc
    assert "You may retire." in doc


def test_content_hash_excludes_crawled_at():
    """Hash must be identical for two runs that differ only in crawl time."""
    page = make_page()
    t1 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    t2 = datetime(2026, 12, 31, tzinfo=timezone.utc)
    _, h1 = build_markdown_document(page, 1, "https://x", crawled_at=t1)
    _, h2 = build_markdown_document(page, 1, "https://x", crawled_at=t2)
    assert h1 == h2


def test_content_hash_changes_when_body_changes():
    _, h1 = build_markdown_document(make_page(), 1, "https://x", crawled_at=FIXED_TIME)
    _, h2 = build_markdown_document(
        make_page(content_html="<p>different</p>"), 1, "https://x", crawled_at=FIXED_TIME
    )
    assert h1 != h2
