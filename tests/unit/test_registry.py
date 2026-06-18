"""Unit tests for the Seen URL registry (CE-017).

AC-001: duplicate URLs never recrawled.
"""
from crawl_engine.discovery.registry import SeenRegistry


def test_new_registry_is_empty():
    r = SeenRegistry()
    assert len(r) == 0
    assert "https://www.ohsers.org/members" not in r


def test_mark_seen_returns_true_first_time():
    r = SeenRegistry()
    assert r.mark_seen("https://www.ohsers.org/members") is True


def test_mark_seen_returns_false_on_duplicate():
    r = SeenRegistry()
    r.mark_seen("https://www.ohsers.org/members")
    assert r.mark_seen("https://www.ohsers.org/members") is False


def test_contains_after_mark():
    r = SeenRegistry()
    r.mark_seen("https://www.ohsers.org/members")
    assert "https://www.ohsers.org/members" in r


def test_distinct_urls_tracked_separately():
    r = SeenRegistry()
    assert r.mark_seen("https://www.ohsers.org/members") is True
    assert r.mark_seen("https://www.ohsers.org/employers") is True
    assert len(r) == 2


def test_snapshot_restore_roundtrip():
    r = SeenRegistry()
    r.mark_seen("https://www.ohsers.org/members")
    r.mark_seen("https://www.ohsers.org/employers")

    restored = SeenRegistry.restore(r.snapshot())
    assert len(restored) == 2
    assert "https://www.ohsers.org/members" in restored
    # already-seen URLs stay seen after restore
    assert restored.mark_seen("https://www.ohsers.org/members") is False


def test_snapshot_is_sorted_and_deterministic():
    r = SeenRegistry()
    r.mark_seen("https://www.ohsers.org/zeta")
    r.mark_seen("https://www.ohsers.org/alpha")
    assert r.snapshot() == {
        "seen": ["https://www.ohsers.org/alpha", "https://www.ohsers.org/zeta"]
    }
