"""Unit tests for URL Discovery queue.

CE-005: BFS ordering              (AC-001)
CE-007: Max depth enforcement     (AC-001)
CE-008: Max page enforcement      (AC-001)
CE-004: Seed loading              (AC-001)
CE-006: Queue persistence         (AC-013)
"""
import pytest

from crawl_engine.config.loader import CrawlConfig
from crawl_engine.discovery.queue import CrawlQueue, QueueItem, load_seeds


# ── construction ────────────────────────────────────────────────────────────

def test_new_queue_is_exhausted():
    q = CrawlQueue(max_depth=3)
    assert q.is_exhausted()
    assert len(q) == 0


def test_invalid_max_depth_raises():
    with pytest.raises(ValueError):
        CrawlQueue(max_depth=0)


def test_invalid_max_pages_raises():
    with pytest.raises(ValueError):
        CrawlQueue(max_depth=3, max_pages=-1)


def test_from_config_uses_config_limits():
    cfg = CrawlConfig(
        seed_urls=["https://www.ohsers.org/members/"],
        base_url="https://www.ohsers.org",
        max_depth=5,
        max_pages=200,
    )
    q = CrawlQueue.from_config(cfg)
    assert q.max_depth == 5
    assert q.max_pages == 200


# ── BFS ordering (CE-005) ─────────────────────────────────────────────────────

def test_pop_returns_items_in_fifo_order():
    q = CrawlQueue(max_depth=3)
    q.push("https://a", 0)
    q.push("https://b", 1)
    q.push("https://c", 1)
    assert q.pop() == QueueItem("https://a", 0)
    assert q.pop() == QueueItem("https://b", 1)
    assert q.pop() == QueueItem("https://c", 1)


def test_pop_empty_returns_none():
    q = CrawlQueue(max_depth=3)
    assert q.pop() is None


def test_push_rejects_duplicate_url():
    q = CrawlQueue(max_depth=3)
    assert q.push("https://a", 0) is True
    assert q.push("https://a", 1) is False
    assert q.pending_count == 1


def test_negative_depth_raises():
    q = CrawlQueue(max_depth=3)
    with pytest.raises(ValueError):
        q.push("https://a", -1)


# ── max depth (CE-007) ────────────────────────────────────────────────────────

def test_push_at_max_depth_is_allowed():
    q = CrawlQueue(max_depth=2)
    assert q.push("https://a", 2) is True


def test_push_beyond_max_depth_rejected():
    q = CrawlQueue(max_depth=2)
    assert q.push("https://a", 3) is False
    assert q.pending_count == 0


# ── max pages (CE-008) ────────────────────────────────────────────────────────

def test_max_pages_caps_dispatch():
    q = CrawlQueue(max_depth=5, max_pages=2)
    for i in range(5):
        q.push(f"https://a/{i}", 1)
    assert q.pop() is not None
    assert q.pop() is not None
    assert q.is_exhausted()          # budget spent even though items remain
    assert q.pop() is None
    assert q.dispatched_count == 2


def test_max_pages_zero_means_unlimited():
    q = CrawlQueue(max_depth=5, max_pages=0)
    for i in range(10):
        q.push(f"https://a/{i}", 1)
    popped = 0
    while not q.is_exhausted():
        assert q.pop() is not None
        popped += 1
    assert popped == 10


# ── seed loading (CE-004) ─────────────────────────────────────────────────────

def test_load_seeds_queues_all_seeds_at_depth_zero():
    cfg = CrawlConfig(
        seed_urls=[
            "https://www.ohsers.org/members/",
            "https://www.ohsers.org/employers/",
        ],
        base_url="https://www.ohsers.org",
    )
    q = CrawlQueue.from_config(cfg)
    n = load_seeds(q, cfg)
    assert n == 2
    assert q.pop() == QueueItem("https://www.ohsers.org/members/", 0)
    assert q.pop() == QueueItem("https://www.ohsers.org/employers/", 0)


def test_load_seeds_skips_duplicate_seeds():
    cfg = CrawlConfig(
        seed_urls=["https://www.ohsers.org/members/", "https://www.ohsers.org/members/"],
        base_url="https://www.ohsers.org",
    )
    q = CrawlQueue.from_config(cfg)
    assert load_seeds(q, cfg) == 1


# ── persistence (CE-006) ──────────────────────────────────────────────────────

def test_snapshot_restore_roundtrip_preserves_state():
    q = CrawlQueue(max_depth=4, max_pages=10)
    q.push("https://a", 0)
    q.push("https://b", 1)
    q.pop()  # dispatch one

    restored = CrawlQueue.restore(q.snapshot())
    assert restored.max_depth == 4
    assert restored.max_pages == 10
    assert restored.dispatched_count == 1
    assert restored.pop() == QueueItem("https://b", 1)


def test_restored_queue_remembers_already_enqueued():
    q = CrawlQueue(max_depth=4)
    q.push("https://a", 0)
    restored = CrawlQueue.restore(q.snapshot())
    # 'a' was already enqueued, so it must not be re-added after restore
    assert restored.push("https://a", 0) is False


def test_save_and_load_to_disk(tmp_path):
    path = tmp_path / "queue.json"
    q = CrawlQueue(max_depth=4, max_pages=10)
    q.push("https://a", 0)
    q.push("https://b", 1)
    q.save(path)
    assert path.exists()

    loaded = CrawlQueue.load(path)
    assert loaded.pending_count == 2
    assert loaded.pop() == QueueItem("https://a", 0)
