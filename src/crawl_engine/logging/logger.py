"""CE-002: Structured JSONL logging framework.

Every crawl event is written as a JSON object on a single line.
This makes logs machine-readable for post-crawl analysis and audit.
"""
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class JSONLFormatter(logging.Formatter):
    """Formats log records as single-line JSON objects."""

    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "event_type": getattr(record, "event_type", "log"),
            "message": record.getMessage(),
        }
        # Merge any structured fields attached by log_event()
        extra = getattr(record, "structured", {})
        entry.update(extra)
        return json.dumps(entry, default=str)


class _ConsoleVolumeFilter(logging.Filter):
    """Keeps high-frequency per-link events out of the console (still logged to
    the JSONL file). See D3."""

    NOISY = {"url_discovered", "url_skipped", "links_extracted"}

    def filter(self, record: logging.LogRecord) -> bool:
        return getattr(record, "event_type", None) not in self.NOISY


def setup_logger(log_path: Path, name: str = "crawl_engine") -> logging.Logger:
    """
    Create and configure the crawl logger.
    Writes JSONL to file and human-readable output to stdout.

    AC-015: Log file generated with required schema fields.
    """
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    if logger.handlers:
        # Already configured. If a *different* log_path is requested, repoint the
        # file handler instead of silently ignoring the new path (D6).
        target = str(Path(log_path).resolve())
        file_handlers = [h for h in logger.handlers if isinstance(h, logging.FileHandler)]
        if file_handlers and str(Path(file_handlers[0].baseFilename).resolve()) != target:
            Path(log_path).parent.mkdir(parents=True, exist_ok=True)
            new_fh = logging.FileHandler(log_path, encoding="utf-8")
            new_fh.setLevel(logging.DEBUG)
            new_fh.setFormatter(JSONLFormatter())
            for h in file_handlers:
                logger.removeHandler(h)
                h.close()
            logger.addHandler(new_fh)
        return logger

    log_path.parent.mkdir(parents=True, exist_ok=True)

    # JSONL file handler
    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(JSONLFormatter())
    logger.addHandler(file_handler)

    # Human-readable console handler. High-frequency per-link events are kept in
    # the JSONL file but filtered off stdout so a real crawl (hundreds of links
    # per page) does not flood the terminal (D3). Progress-level events
    # (fetched/saved/failed/started/finished/...) still print.
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
    console_handler.addFilter(_ConsoleVolumeFilter())
    logger.addHandler(console_handler)

    return logger


def log_event(
    logger: logging.Logger,
    event_type: str,
    level: int = logging.INFO,
    **fields: Any,
) -> None:
    """
    Emit a structured crawl event.

    Usage:
        log_event(logger, "url_discovered", url="https://ohsers.org/members/", depth=1)
        log_event(logger, "page_fetched", url="...", status_code=200, content_length=4321)
        log_event(logger, "page_failed", url="...", reason="timeout", attempt=2)
        log_event(logger, "file_saved", url="...", path="output/raw/members/index.md")
        log_event(logger, "url_skipped", url="...", reason="already_seen")
        log_event(logger, "crawl_started", seed_count=2, max_depth=4)
        log_event(logger, "crawl_finished", pages_crawled=312, pages_failed=4)
    """
    record = logging.LogRecord(
        name=logger.name,
        level=level,
        pathname="",
        lineno=0,
        msg=event_type,
        args=(),
        exc_info=None,
    )
    record.event_type = event_type
    record.structured = fields
    logger.handle(record)
