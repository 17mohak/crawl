"""End-to-end integration + validation suite.

CE-040: Integration Test Suite     (AC-001..AC-016 — full pipeline)
CE-041: Determinism Validation     (NFR-001 / AC-017 — two runs, same output)
CE-042: Idempotency Validation     (NFR-002 / AC-018 — reruns make no duplicates)
CE-043: Provenance Validation      (NFR-005 / AC-019 — artifacts carry provenance)
CE-044: Reliability Validation     (NFR-007 / AC-020 — survives bounded failures)

All tests run the real crawl loop against an in-memory site (see conftest), so
they are deterministic and need no network.
"""
from pathlib import Path

import yaml

from crawl_engine.logging.logger import setup_logger
from crawl_engine.reliability.crawler import Crawler

from .conftest import BASE, FIXED_CLOCK, LocalSiteFetcher

REQUIRED_PROVENANCE_FIELDS = {
    "url",
    "canonical_url",
    "title",
    "crawled_at",
    "content_hash",
    "depth",
    "source_section",
}


def _md_files(output_dir: Path) -> list[Path]:
    return sorted(output_dir.rglob("*.md"))


def _frontmatter(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n"), f"{path} missing frontmatter"
    inner = text[4:text.index("\n---", 4)]
    return yaml.safe_load(inner)


def _run(cfg, name, **fetcher_kwargs):
    logger = setup_logger(cfg.log_path, name=name)
    fetcher = LocalSiteFetcher(**fetcher_kwargs)
    stats = Crawler(cfg, logger, fetcher=fetcher, clock=FIXED_CLOCK).run()
    return stats, fetcher


# ── CE-040: integration ───────────────────────────────────────────────────────

def test_full_crawl_produces_expected_artifacts(tmp_path, make_config):
    cfg = make_config(tmp_path)
    stats, fetcher = _run(cfg, "it_full")

    assert stats.pages_crawled == 3
    assert stats.pages_failed == 0
    files = {str(p.relative_to(cfg.output_dir)) for p in _md_files(cfg.output_dir)}
    assert files == {
        str(Path("members") / "index.md"),
        str(Path("members") / "service-retirement" / "index.md"),
        str(Path("members") / "forms" / "index.md"),
    }


def test_external_link_not_crawled(tmp_path, make_config):
    cfg = make_config(tmp_path)
    _, fetcher = _run(cfg, "it_external")
    assert not any("google.com" in u for u in fetcher.fetched)


def test_checkpoint_written_after_crawl(tmp_path, make_config):
    cfg = make_config(tmp_path)
    _run(cfg, "it_ckpt")
    assert cfg.checkpoint_path.exists()


# ── CE-041: determinism ───────────────────────────────────────────────────────

def test_two_runs_produce_byte_identical_output(tmp_path, make_config):
    cfg_a = make_config(tmp_path / "a", output_dir=tmp_path / "a" / "raw",
                        checkpoint_path=tmp_path / "a" / "cp.json",
                        log_path=tmp_path / "a" / "log.jsonl")
    cfg_b = make_config(tmp_path / "b", output_dir=tmp_path / "b" / "raw",
                        checkpoint_path=tmp_path / "b" / "cp.json",
                        log_path=tmp_path / "b" / "log.jsonl")
    _run(cfg_a, "it_det_a")
    _run(cfg_b, "it_det_b")

    files_a = _md_files(cfg_a.output_dir)
    files_b = _md_files(cfg_b.output_dir)
    rel_a = [p.relative_to(cfg_a.output_dir) for p in files_a]
    rel_b = [p.relative_to(cfg_b.output_dir) for p in files_b]
    assert rel_a == rel_b
    for ra in rel_a:
        assert (cfg_a.output_dir / ra).read_bytes() == (cfg_b.output_dir / ra).read_bytes()


# ── CE-042: idempotency ───────────────────────────────────────────────────────

def test_rerun_creates_no_duplicates_and_rewrites_nothing(tmp_path, make_config):
    cfg = make_config(tmp_path)
    _run(cfg, "it_idem_1")
    files_before = {p.relative_to(cfg.output_dir): p.read_bytes() for p in _md_files(cfg.output_dir)}

    stats2, _ = _run(cfg, "it_idem_2")
    files_after = {p.relative_to(cfg.output_dir): p.read_bytes() for p in _md_files(cfg.output_dir)}

    assert set(files_before) == set(files_after)          # no new files
    assert files_before == files_after                    # bytes unchanged
    assert stats2.artifacts_written == 0
    assert stats2.artifacts_unchanged == stats2.pages_crawled


# ── CE-043: provenance ────────────────────────────────────────────────────────

def test_every_artifact_carries_required_provenance_fields(tmp_path, make_config):
    cfg = make_config(tmp_path)
    _run(cfg, "it_prov")
    files = _md_files(cfg.output_dir)
    assert files, "expected at least one artifact"
    for path in files:
        fm = _frontmatter(path)
        missing = REQUIRED_PROVENANCE_FIELDS - set(fm)
        assert not missing, f"{path} missing provenance fields: {missing}"
        assert fm["content_hash"].startswith("sha256:")
        assert fm["url"].startswith(BASE)


# ── CE-044: reliability ───────────────────────────────────────────────────────

def test_crawl_survives_fetch_failures(tmp_path, make_config):
    # Make the forms page fail with a 503; the rest must still crawl.
    cfg = make_config(tmp_path)
    stats, _ = _run(cfg, "it_rel_fail", fail={f"{BASE}/members/forms"})
    assert stats.pages_failed == 1
    assert stats.pages_crawled == 2
    assert (cfg.output_dir / "members" / "index.md").exists()
    assert (cfg.output_dir / "members" / "service-retirement" / "index.md").exists()


def test_crawl_survives_processing_exceptions(tmp_path, make_config):
    cfg = make_config(tmp_path)
    stats, _ = _run(cfg, "it_rel_boom", boom={f"{BASE}/members/forms"})
    assert stats.pages_failed == 1
    assert stats.pages_crawled >= 2  # other pages still saved


def test_crawl_finishes_even_if_seed_fails(tmp_path, make_config):
    cfg = make_config(tmp_path)
    stats, _ = _run(cfg, "it_rel_seedfail", fail={f"{BASE}/members"})
    # Seed failed, nothing else discovered, but the run completes cleanly.
    assert stats.pages_failed == 1
    assert stats.pages_crawled == 0
