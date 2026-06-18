"""URL Discovery & Canonicalization (CE-004..CE-018).

BFS queue, seed loading, link extraction, URL canonicalization, Seen registry.
"""
from crawl_engine.discovery.canonicalize import DEFAULT_TRACKING_PARAMS, canonicalize
from crawl_engine.discovery.links import LinkExtractionResult, extract_links
from crawl_engine.discovery.queue import CrawlQueue, QueueItem, load_seeds
from crawl_engine.discovery.registry import SeenRegistry

__all__ = [
    "CrawlQueue",
    "QueueItem",
    "load_seeds",
    "extract_links",
    "LinkExtractionResult",
    "canonicalize",
    "DEFAULT_TRACKING_PARAMS",
    "SeenRegistry",
]
