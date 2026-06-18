"""Unit tests for CE-002: JSONL logging framework.

AC-015: Log file generated with required schema fields.
"""
import json
import logging
from pathlib import Path

import pytest

from crawl_engine.logging.logger import log_event, setup_logger


def test_log_file_created(tmp_path):
    log_path = tmp_path / "crawl.jsonl"
    setup_logger(log_path, name="test_create")
    assert log_path.exists()


def test_log_event_writes_jsonl(tmp_path):
    log_path = tmp_path / "crawl.jsonl"
    logger = setup_logger(log_path, name="test_write")

    log_event(logger, "url_discovered", url="https://www.ohsers.org/members/", depth=1)

    lines = log_path.read_text().strip().splitlines()
    assert len(lines) == 1

    entry = json.loads(lines[0])
    assert entry["event_type"] == "url_discovered"
    assert entry["url"] == "https://www.ohsers.org/members/"
    assert entry["depth"] == 1
    assert "timestamp" in entry
    assert "level" in entry


def test_required_schema_fields_present(tmp_path):
    log_path = tmp_path / "crawl.jsonl"
    logger = setup_logger(log_path, name="test_schema")

    log_event(logger, "page_fetched", url="https://www.ohsers.org/", status_code=200)

    entry = json.loads(log_path.read_text().strip())
    for field in ("timestamp", "level", "event_type", "message"):
        assert field in entry, f"Required field '{field}' missing from log entry"


def test_multiple_events_each_on_own_line(tmp_path):
    log_path = tmp_path / "crawl.jsonl"
    logger = setup_logger(log_path, name="test_multi")

    log_event(logger, "crawl_started", seed_count=2)
    log_event(logger, "url_discovered", url="https://www.ohsers.org/members/", depth=1)
    log_event(logger, "page_failed", url="https://www.ohsers.org/broken/", reason="timeout")

    lines = log_path.read_text().strip().splitlines()
    assert len(lines) == 3
    for line in lines:
        json.loads(line)  # every line must be valid JSON


def test_extra_fields_included(tmp_path):
    log_path = tmp_path / "crawl.jsonl"
    logger = setup_logger(log_path, name="test_extra")

    log_event(
        logger, "file_saved",
        url="https://www.ohsers.org/members/",
        path="output/raw/members/index.md",
        content_hash="abc123",
    )

    entry = json.loads(log_path.read_text().strip())
    assert entry["path"] == "output/raw/members/index.md"
    assert entry["content_hash"] == "abc123"
