"""URL Discovery: BFS queue, seed loading, and link extraction (CE-004..CE-011)."""
from crawl_engine.discovery.links import LinkExtractionResult, extract_links
from crawl_engine.discovery.queue import CrawlQueue, QueueItem, load_seeds

__all__ = [
    "CrawlQueue",
    "QueueItem",
    "load_seeds",
    "extract_links",
    "LinkExtractionResult",
]
