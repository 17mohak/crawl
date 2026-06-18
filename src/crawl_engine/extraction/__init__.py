"""HTML Extraction: fetch service and HTML parser (CE-019..CE-026)."""
from crawl_engine.extraction.fetcher import FetchResult, HttpFetcher, backoff_delay
from crawl_engine.extraction.parser import (
    ParsedPage,
    extract_main_content,
    extract_metadata,
    extract_title,
    parse_page,
    strip_noise,
)

__all__ = [
    "HttpFetcher",
    "FetchResult",
    "backoff_delay",
    "ParsedPage",
    "parse_page",
    "extract_title",
    "extract_metadata",
    "extract_main_content",
    "strip_noise",
]
