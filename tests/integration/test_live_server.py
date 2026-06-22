"""Live HTTP integration tests against a real localhost server.

These exercise the genuine network path — `requests` over a socket, real 301
redirects on directory URLs, and relative-link resolution — which the
in-memory fetcher tests cannot. This is the layer that caught the relative-link
resolution bug (relative hrefs must resolve against the post-redirect URL, not
the slash-stripped canonical queue key).

Uses only loopback (127.0.0.1); never touches the public internet.
"""
import functools
import http.server
import socketserver
import threading

import pytest
import yaml

from crawl_engine.config.loader import CrawlConfig
from crawl_engine.logging.logger import setup_logger
from crawl_engine.reliability.crawler import Crawler


def _write_site(root):
    (root / "members" / "service-retirement").mkdir(parents=True)
    (root / "members" / "forms").mkdir()
    # NOTE: relative hrefs (not root-relative) — the realistic, bug-exposing case.
    (root / "members" / "index.html").write_text(
        "<html lang='en'><head><title>Members</title></head><body>"
        "<nav>site nav</nav><main><h1>Members</h1><p>overview</p>"
        "<a href='service-retirement/'>SR</a><a href='forms/'>Forms</a>"
        "<a href='https://example.com/ext'>ext</a></main>"
        "<footer>footer junk</footer></body></html>",
        encoding="utf-8",
    )
    (root / "members" / "service-retirement" / "index.html").write_text(
        "<html><head><title>Service Retirement</title></head><body><main>"
        "<h1>SR</h1><p>retire details</p><a href='../forms/'>forms</a></main></body></html>",
        encoding="utf-8",
    )
    (root / "members" / "forms" / "index.html").write_text(
        "<html><head><title>Forms</title></head><body><main><h1>Forms</h1>"
        "<p>forms list</p><a href='../service-retirement/'>sr</a></main></body></html>",
        encoding="utf-8",
    )


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):  # silence per-request stderr logging
        pass


@pytest.fixture
def live_site(tmp_path):
    """Serve a small OHSERS-like site on an ephemeral loopback port."""
    root = tmp_path / "site"
    _write_site(root)
    handler = functools.partial(_QuietHandler, directory=str(root))
    server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), handler)
    server.daemon_threads = True
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.shutdown()
        server.server_close()


def _config(tmp_path, base):
    return CrawlConfig(
        seed_urls=[f"{base}/members/"],
        base_url=base,
        allowed_paths=["/members/"],
        output_dir=tmp_path / "raw",
        checkpoint_path=tmp_path / "checkpoint.json",
        log_path=tmp_path / "crawl.jsonl",
        request_timeout=10,
        max_depth=5,
    )


def test_live_crawl_follows_relative_links_over_real_http(live_site, tmp_path):
    cfg = _config(tmp_path, live_site)
    logger = setup_logger(cfg.log_path, name="live_rel")
    stats = Crawler(cfg, logger).run()  # real HttpFetcher, real socket

    assert stats.pages_crawled == 3
    assert stats.pages_failed == 0
    produced = {p.relative_to(cfg.output_dir).as_posix() for p in cfg.output_dir.rglob("*.md")}
    assert produced == {
        "members/index.md",
        "members/service-retirement/index.md",
        "members/forms/index.md",
    }


def test_live_crawl_skips_external_and_strips_noise(live_site, tmp_path):
    cfg = _config(tmp_path, live_site)
    logger = setup_logger(cfg.log_path, name="live_noise")
    Crawler(cfg, logger).run()

    text = (cfg.output_dir / "members" / "index.md").read_text(encoding="utf-8")
    body = text.split("---", 2)[2]
    assert "site nav" not in body
    assert "footer junk" not in body
    assert "overview" in body
    # external link must not have produced an artifact
    assert not any("example.com" in p.as_posix() for p in cfg.output_dir.rglob("*"))


def test_live_crawl_is_idempotent_over_real_http(live_site, tmp_path):
    cfg = _config(tmp_path, live_site)
    Crawler(cfg, setup_logger(cfg.log_path, name="live_idem1")).run()
    before = {p: p.read_bytes() for p in cfg.output_dir.rglob("*.md")}

    stats2 = Crawler(cfg, setup_logger(cfg.log_path, name="live_idem2")).run()
    after = {p: p.read_bytes() for p in cfg.output_dir.rglob("*.md")}

    assert before == after  # no rewrites
    assert stats2.artifacts_written == 0
    assert stats2.artifacts_unchanged == stats2.pages_crawled


def test_live_artifact_has_valid_frontmatter(live_site, tmp_path):
    cfg = _config(tmp_path, live_site)
    Crawler(cfg, setup_logger(cfg.log_path, name="live_fm")).run()
    text = (cfg.output_dir / "members" / "service-retirement" / "index.md").read_text(encoding="utf-8")
    fm = yaml.safe_load(text[4:text.index("\n---", 4)])
    assert set(fm) == {
        "url", "canonical_url", "title", "crawled_at", "content_hash", "depth", "source_section",
    }
    assert fm["title"] == "Service Retirement"
    assert fm["content_hash"].startswith("sha256:")
