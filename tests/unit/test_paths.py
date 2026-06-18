"""Unit tests for URL-to-path mapping (CE-029).

AC-004 / NFR-001: path structure generated correctly and deterministically.
"""
from pathlib import Path

from crawl_engine.storage.paths import url_to_path

OUT = Path("output/raw")


def test_simple_path_maps_to_index_md():
    assert url_to_path("https://www.ohsers.org/members/service-retirement", OUT) == (
        OUT / "members" / "service-retirement" / "index.md"
    )


def test_root_maps_to_index_md():
    assert url_to_path("https://www.ohsers.org/", OUT) == OUT / "index.md"
    assert url_to_path("https://www.ohsers.org", OUT) == OUT / "index.md"


def test_page_and_subpage_do_not_collide():
    parent = url_to_path("https://www.ohsers.org/members", OUT)
    child = url_to_path("https://www.ohsers.org/members/retirement", OUT)
    assert parent == OUT / "members" / "index.md"
    assert child == OUT / "members" / "retirement" / "index.md"
    assert parent != child


def test_mapping_is_deterministic():
    url = "https://www.ohsers.org/members/forms"
    assert url_to_path(url, OUT) == url_to_path(url, OUT)


def test_query_string_folded_into_filename():
    p = url_to_path("https://www.ohsers.org/search?q=cola", OUT)
    assert p.parent == OUT / "search"
    assert p.name.startswith("index__")
    assert p.suffix == ".md"


def test_different_queries_map_to_different_files():
    a = url_to_path("https://www.ohsers.org/search?q=cola", OUT)
    b = url_to_path("https://www.ohsers.org/search?q=disability", OUT)
    assert a != b


def test_unsafe_characters_sanitized():
    # A path segment with characters illegal on Windows must not leak through.
    p = url_to_path("https://www.ohsers.org/a:b/c", OUT)
    assert ":" not in str(p.relative_to(OUT).parts[0])
