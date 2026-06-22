"""Unit tests for CE-003: Configuration loader.

AC-017: Config loads and validates successfully.
"""
from pathlib import Path

import pytest
import yaml

from crawl_engine.config.loader import load_config


# ── helpers ───────────────────────────────────────────────────────────────────

def write_config(tmp_path: Path, data: dict) -> Path:
    p = tmp_path / "config.yaml"
    p.write_text(yaml.dump(data), encoding="utf-8")
    return p


VALID = {
    "seed_urls": ["https://www.ohsers.org/members/"],
    "base_url": "https://www.ohsers.org",
}


# ── happy path ────────────────────────────────────────────────────────────────

def test_minimal_config_loads(tmp_path):
    cfg = load_config(write_config(tmp_path, VALID))
    assert cfg.seed_urls == ["https://www.ohsers.org/members/"]
    assert cfg.base_url == "https://www.ohsers.org"


def test_defaults_applied(tmp_path):
    cfg = load_config(write_config(tmp_path, VALID))
    assert cfg.max_depth == 3
    assert cfg.max_pages == 0
    assert cfg.request_timeout == 30
    assert cfg.allowed_paths == []
    assert cfg.retry.max_attempts == 3


def test_full_config_loads(tmp_path):
    data = {
        **VALID,
        "allowed_paths": ["/members/", "/employers/"],
        "max_depth": 5,
        "max_pages": 200,
        "request_timeout": 45,
        "retry": {"max_attempts": 5, "backoff_factor": 3.0, "backoff_max": 120.0},
        "output_dir": "output/raw",
        "checkpoint_path": "output/checkpoint.json",
        "log_path": "output/crawl.jsonl",
    }
    cfg = load_config(write_config(tmp_path, data))
    assert cfg.max_depth == 5
    assert cfg.retry.max_attempts == 5
    assert cfg.allowed_paths == ["/members/", "/employers/"]


def test_paths_returned_as_path_objects(tmp_path):
    cfg = load_config(write_config(tmp_path, VALID))
    assert isinstance(cfg.output_dir, Path)
    assert isinstance(cfg.checkpoint_path, Path)
    assert isinstance(cfg.log_path, Path)


# ── validation errors ─────────────────────────────────────────────────────────

def test_missing_seed_urls_raises(tmp_path):
    with pytest.raises(Exception):
        load_config(write_config(tmp_path, {"base_url": "https://www.ohsers.org"}))


def test_empty_seed_urls_raises(tmp_path):
    with pytest.raises(Exception):
        load_config(write_config(tmp_path, {**VALID, "seed_urls": []}))


def test_invalid_depth_raises(tmp_path):
    with pytest.raises(Exception):
        load_config(write_config(tmp_path, {**VALID, "max_depth": 0}))


def test_seed_not_under_base_raises(tmp_path):
    with pytest.raises(Exception):
        load_config(write_config(tmp_path, {
            "seed_urls": ["https://other.example.com/"],
            "base_url": "https://www.ohsers.org",
        }))


def test_file_not_found_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_config(tmp_path / "nonexistent.yaml")
