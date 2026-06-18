"""Unit tests for atomic writing, skip-unchanged, and save orchestration.

CE-031 (atomic write), CE-033 (skip unchanged), CE-034 (save artifact).
AC-005 / AC-006. Also exercises idempotency (CE-042) and rerun determinism
(CE-041) at the single-artifact level.
"""
from datetime import datetime, timezone

from crawl_engine.config.loader import CrawlConfig
from crawl_engine.extraction.parser import ParsedPage
from crawl_engine.storage.writer import (
    atomic_write,
    read_existing_hash,
    save_artifact,
)

FIXED_TIME = datetime(2026, 6, 18, 10, 23, 0, tzinfo=timezone.utc)
LATER_TIME = datetime(2026, 7, 1, 9, 0, 0, tzinfo=timezone.utc)


def make_config(tmp_path) -> CrawlConfig:
    return CrawlConfig(
        seed_urls=["https://www.ohsers.org/members/"],
        base_url="https://www.ohsers.org",
        output_dir=tmp_path / "raw",
    )


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


# ── CE-031: atomic write ──────────────────────────────────────────────────────

def test_atomic_write_creates_file_and_dirs(tmp_path):
    target = tmp_path / "a" / "b" / "c" / "index.md"
    atomic_write(target, "hello")
    assert target.read_text(encoding="utf-8") == "hello"


def test_atomic_write_leaves_no_tmp_file(tmp_path):
    target = tmp_path / "index.md"
    atomic_write(target, "hello")
    assert list(tmp_path.glob("*.tmp")) == []


def test_atomic_write_overwrites_existing(tmp_path):
    target = tmp_path / "index.md"
    atomic_write(target, "first")
    atomic_write(target, "second")
    assert target.read_text(encoding="utf-8") == "second"


# ── read_existing_hash ────────────────────────────────────────────────────────

def test_read_existing_hash_none_when_missing(tmp_path):
    assert read_existing_hash(tmp_path / "nope.md") is None


def test_read_existing_hash_none_without_frontmatter(tmp_path):
    p = tmp_path / "x.md"
    p.write_text("no frontmatter here", encoding="utf-8")
    assert read_existing_hash(p) is None


def test_read_existing_hash_parses_frontmatter(tmp_path):
    p = tmp_path / "x.md"
    p.write_text("---\ncontent_hash: sha256:abc\ndepth: 1\n---\n\nbody", encoding="utf-8")
    assert read_existing_hash(p) == "sha256:abc"


# ── CE-034: save artifact ─────────────────────────────────────────────────────

def test_save_writes_artifact_to_deterministic_path(tmp_path):
    cfg = make_config(tmp_path)
    result = save_artifact(make_page(), depth=2, config=cfg, crawled_at=FIXED_TIME)
    expected = cfg.output_dir / "members" / "service-retirement" / "index.md"
    assert result.written is True
    assert result.skipped is False
    assert result.path == expected
    assert expected.exists()
    assert "# Service Retirement" in expected.read_text(encoding="utf-8")


def test_saved_file_has_frontmatter_with_provenance(tmp_path):
    cfg = make_config(tmp_path)
    result = save_artifact(make_page(), depth=2, config=cfg, crawled_at=FIXED_TIME)
    text = result.path.read_text(encoding="utf-8")
    assert text.startswith("---\n")
    assert "canonical_url: https://www.ohsers.org/members/service-retirement" in text
    assert "content_hash: sha256:" in text


# ── CE-033: skip unchanged ────────────────────────────────────────────────────

def test_second_save_skips_unchanged_content(tmp_path):
    cfg = make_config(tmp_path)
    first = save_artifact(make_page(), depth=2, config=cfg, crawled_at=FIXED_TIME)
    second = save_artifact(make_page(), depth=2, config=cfg, crawled_at=LATER_TIME)
    assert first.written is True
    assert second.written is False
    assert second.skipped is True


def test_rerun_leaves_file_byte_identical(tmp_path):
    """CE-041 at artifact level: a re-run on unchanged content rewrites nothing,
    so the file (including its original crawled_at) is byte-for-byte identical."""
    cfg = make_config(tmp_path)
    save_artifact(make_page(), depth=2, config=cfg, crawled_at=FIXED_TIME)
    path = cfg.output_dir / "members" / "service-retirement" / "index.md"
    before = path.read_bytes()
    # second run later in time, same content
    save_artifact(make_page(), depth=2, config=cfg, crawled_at=LATER_TIME)
    after = path.read_bytes()
    assert before == after
    assert b"2026-06-18T10:23:00Z" in after  # original timestamp preserved


def test_changed_content_is_rewritten(tmp_path):
    cfg = make_config(tmp_path)
    save_artifact(make_page(), depth=2, config=cfg, crawled_at=FIXED_TIME)
    changed = save_artifact(
        make_page(content_html="<h1>Service Retirement</h1><p>Updated rules.</p>"),
        depth=2, config=cfg, crawled_at=LATER_TIME,
    )
    assert changed.written is True
    assert changed.skipped is False
    assert "Updated rules." in changed.path.read_text(encoding="utf-8")
