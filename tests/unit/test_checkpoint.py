"""Unit tests for checkpoint save/reload (CE-036).

AC-013: queue state saved and reloadable; resume continues correctly.
"""
from crawl_engine.discovery.queue import CrawlQueue, QueueItem
from crawl_engine.discovery.registry import SeenRegistry
from crawl_engine.reliability.checkpoint import (
    checkpoint_exists,
    load_checkpoint,
    save_checkpoint,
)


def test_checkpoint_exists_reports_presence(tmp_path):
    path = tmp_path / "checkpoint.json"
    assert checkpoint_exists(path) is False
    path.write_text("{}", encoding="utf-8")
    assert checkpoint_exists(path) is True


def test_checkpoint_roundtrip_restores_queue_and_registry(tmp_path):
    path = tmp_path / "checkpoint.json"

    queue = CrawlQueue(max_depth=4, max_pages=100)
    queue.push("https://www.ohsers.org/members", 0)
    queue.push("https://www.ohsers.org/employers", 1)
    queue.pop()  # dispatch one

    registry = SeenRegistry()
    registry.mark_seen("https://www.ohsers.org/members")
    registry.mark_seen("https://www.ohsers.org/employers")

    stats = {"pages_crawled": 1, "pages_failed": 0}

    save_checkpoint(path, queue, registry, stats)
    assert path.exists()

    q2, r2, s2 = load_checkpoint(path)
    assert q2.dispatched_count == 1  # one dispatched before the save
    assert q2.pop() == QueueItem("https://www.ohsers.org/employers", 1)  # pending item resumes
    assert "https://www.ohsers.org/members" in r2
    assert s2 == {"pages_crawled": 1, "pages_failed": 0}


def test_checkpoint_preserves_dispatched_count(tmp_path):
    path = tmp_path / "checkpoint.json"
    queue = CrawlQueue(max_depth=4)
    queue.push("https://a", 0)
    queue.pop()
    save_checkpoint(path, queue, SeenRegistry(), {})
    q2, _, _ = load_checkpoint(path)
    assert q2.dispatched_count == 1


def test_checkpoint_write_is_atomic_no_tmp_left(tmp_path):
    path = tmp_path / "checkpoint.json"
    save_checkpoint(path, CrawlQueue(max_depth=2), SeenRegistry(), {})
    assert list(tmp_path.glob("*.tmp")) == []
