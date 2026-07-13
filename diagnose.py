"""diagnose.py - single-run diagnostic build for the OHSERS crawl engine.

Purpose: let anyone (e.g. Sameer) run the project ONCE and immediately identify
*which category* of failure they are seeing - packaging, configuration, network,
or crawl logic - without guessing.

It prints, in order:
  1. Python executable / interpreter / venv status
  2. Installed package versions (or "NOT INSTALLED")
  3. Whether the `crawl_engine` package imports (and from where)
  4. The configuration loaded, seed URLs, and key parameters
  5. An instrumented crawl: every fetch attempt + status, queue growth/shrink,
     URL rejection reasons, and any exception with a FULL traceback
  6. Final crawl statistics
  7. A VERDICT plus the full symptom -> root-cause decision tree

Design note: this script deliberately imports `crawl_engine` *late* and inside a
guarded block, so that when the package/deps are missing it still prints the
environment report and a clear PACKAGING verdict instead of a raw traceback.

It does NOT modify the crawl engine implementation; it wraps it at runtime.

Usage:
    python diagnose.py [--config config/config.yaml] [--max-pages 8]
Exit code == the numeric failure category (0 = healthy), for scripting.
"""
from __future__ import annotations

import argparse
import logging
import platform
import sys
import traceback
from collections import Counter
from pathlib import Path

# Bootstrap the src/ layout so the diagnostic runs from a clone without an
# editable install (missing third-party deps are still reported in section 2/3).
_SRC = Path(__file__).resolve().parent / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

SEP = "=" * 78

# Failure categories (also used as process exit codes).
OK = 0
PACKAGING = 2
CONFIG = 3
NETWORK = 4
CRAWL_LOGIC = 5
UNKNOWN = 6


def _line(label, value):
    print(f"  {label:<28} {value}")


# ── 1 & 2: environment (stdlib only - must work even with no deps) ────────────

def report_environment() -> None:
    print(SEP)
    print("1. INTERPRETER & ENVIRONMENT")
    print(SEP)
    _line("python executable", sys.executable)
    _line("python version", sys.version.split()[0])
    _line("platform", platform.platform())
    in_venv = sys.prefix != sys.base_prefix
    _line("virtual env active?", f"{in_venv}  (prefix={sys.prefix})")
    if not in_venv:
        _line("base_prefix", sys.base_prefix)
    import os
    _line("VIRTUAL_ENV env var", os.environ.get("VIRTUAL_ENV", "<unset>"))
    _line("sys.path[0]", sys.path[0] or "<cwd>")

    print()
    print(SEP)
    print("2. INSTALLED PACKAGE VERSIONS")
    print(SEP)
    try:
        from importlib.metadata import PackageNotFoundError, version
    except Exception:  # pragma: no cover
        print("  importlib.metadata unavailable")
        return
    for pkg in ("crawl-engine", "pydantic", "requests", "beautifulsoup4",
                "lxml", "html2text", "pyyaml", "pytest"):
        try:
            _line(pkg, version(pkg))
        except PackageNotFoundError:
            _line(pkg, "NOT INSTALLED")


# ── 3: package importability ──────────────────────────────────────────────────

def check_import():
    """Return (ok, error_str). Prints where crawl_engine loaded from."""
    print()
    print(SEP)
    print("3. PACKAGE IMPORT")
    print(SEP)
    try:
        import importlib

        import crawl_engine
        _line("import crawl_engine", "OK")
        _line("loaded from", crawl_engine.__file__)
        deps = ["requests", "bs4", "lxml", "yaml", "pydantic", "html2text"]
        missing = []
        for d in deps:
            try:
                importlib.import_module(d)
            except Exception as e:
                missing.append(f"{d} ({type(e).__name__})")
        if missing:
            _line("core deps import", "MISSING: " + ", ".join(missing))
            return False, "core deps missing: " + ", ".join(missing)
        _line("core deps import", "OK (" + ", ".join(deps) + ")")
        return True, None
    except Exception as exc:
        _line("import crawl_engine", f"FAILED: {type(exc).__name__}: {exc}")
        print("\n  --- full traceback ---")
        traceback.print_exc(file=sys.stdout)
        return False, f"{type(exc).__name__}: {exc}"


# ── 4 & 5: config + instrumented crawl ────────────────────────────────────────

class _Capture(logging.Handler):
    def __init__(self):
        super().__init__()
        self.records = []

    def emit(self, record):
        self.records.append(record)


def run_instrumented(config_path: str, max_pages: int):
    """Load config, run a bounded instrumented crawl. Returns a signals dict."""
    from crawl_engine.config.loader import load_config
    from crawl_engine.extraction.fetcher import HttpFetcher
    from crawl_engine.logging.logger import setup_logger
    from crawl_engine.reliability import crawler as crawler_mod
    from crawl_engine.reliability.crawler import Crawler
    from crawl_engine.reliability.checkpoint import checkpoint_exists

    print()
    print(SEP)
    print("4. CONFIGURATION")
    print(SEP)
    try:
        cfg = load_config(config_path)
    except Exception as exc:
        _line("load_config", f"FAILED: {type(exc).__name__}: {exc}")
        print("\n  --- full traceback ---")
        traceback.print_exc(file=sys.stdout)
        return {"category": CONFIG, "detail": str(exc)}

    if max_pages:
        cfg.max_pages = max_pages
    _line("config file", config_path)
    _line("base_url", cfg.base_url)
    _line("seed_urls", "")
    for s in cfg.seed_urls:
        print(f"      - {s}")
    _line("allowed_paths", cfg.allowed_paths or "<all>")
    _line("max_depth / max_pages", f"{cfg.max_depth} / {cfg.max_pages}")
    _line("request_timeout", cfg.request_timeout)
    _line("retry attempts", cfg.retry.max_attempts)
    _line("user_agent", cfg.user_agent)

    cap = _Capture()
    logger = setup_logger(cfg.log_path, name="diagnose")
    for h in logger.handlers:  # silence the INFO console flood; keep file handler
        if isinstance(h, logging.StreamHandler) and not hasattr(h, "baseFilename"):
            h.setLevel(logging.ERROR)
    logger.addHandler(cap)

    # Wrap the fetcher to print every fetch attempt + response status.
    class DiagFetcher(HttpFetcher):
        def fetch(self, url, logger=None):
            res = super().fetch(url, logger=logger)
            status = res.status_code if res.status_code is not None else "-"
            print(f"    FETCH {'OK ' if res.ok else 'ERR'} status={status} "
                  f"attempts={res.attempts} err={res.error or ''}  {url}")
            return res

    # Patch parse/save references on the crawler module to capture tracebacks
    # (the crawler isolates exceptions internally; we log the traceback first).
    orig_parse, orig_save = crawler_mod.parse_page, crawler_mod.save_artifact

    def parse_wrap(*a, **k):
        try:
            return orig_parse(*a, **k)
        except Exception:
            print("\n    !!! EXCEPTION in parse_page - full traceback:")
            traceback.print_exc(file=sys.stdout)
            raise

    def save_wrap(*a, **k):
        try:
            return orig_save(*a, **k)
        except Exception:
            print("\n    !!! EXCEPTION in save_artifact - full traceback:")
            traceback.print_exc(file=sys.stdout)
            raise

    crawler_mod.parse_page = parse_wrap
    crawler_mod.save_artifact = save_wrap

    class TracedCrawler(Crawler):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            self.iteration = 0

        def _process_page(self, item):
            self.iteration += 1
            q_before = self.queue.pending_count
            s = self.stats
            c0, f0, k0, d0 = s.pages_crawled, s.pages_failed, s.pages_skipped, s.links_discovered
            super()._process_page(item)
            print(f"    iter {self.iteration:>3} depth={item.depth} "
                  f"queue {q_before}->{self.queue.pending_count} "
                  f"crawled+={s.pages_crawled-c0} failed+={s.pages_failed-f0} "
                  f"skipped+={s.pages_skipped-k0} discovered+={s.links_discovered-d0}")

    print()
    print(SEP)
    print("5. INSTRUMENTED CRAWL (bounded)")
    print(SEP)
    fatal = None
    try:
        stats = TracedCrawler(cfg, logger, fetcher=DiagFetcher(cfg)).run()
    except Exception as exc:  # a crash escaping the crawler's own isolation
        print("\n  !!! UNHANDLED EXCEPTION escaped the crawl loop - full traceback:")
        traceback.print_exc(file=sys.stdout)
        fatal = f"{type(exc).__name__}: {exc}"
        stats = None
    finally:
        crawler_mod.parse_page, crawler_mod.save_artifact = orig_parse, orig_save

    reasons = Counter(
        getattr(r, "structured", {}).get("reason")
        for r in cap.records if getattr(r, "event_type", "") == "url_skipped"
    )
    events = Counter(getattr(r, "event_type", "") for r in cap.records)

    print()
    print(SEP)
    print("6. FINAL CRAWL STATISTICS")
    print(SEP)
    if stats is not None:
        _line("pages_crawled", stats.pages_crawled)
        _line("pages_failed", stats.pages_failed)
        _line("pages_skipped", stats.pages_skipped)
        _line("artifacts_written", stats.artifacts_written)
        _line("artifacts_unchanged", stats.artifacts_unchanged)
        _line("links_discovered", stats.links_discovered)
    _line("url_skipped reasons", dict(reasons))
    _line("event counts", dict(events))
    _line("checkpoint written?", checkpoint_exists(cfg.checkpoint_path))

    return {
        "category": None,
        "fatal": fatal,
        "stats": stats,
        "reasons": dict(reasons),
        "events": dict(events),
        "seed_count": len(cfg.seed_urls),
    }


# ── 7: verdict + decision tree ────────────────────────────────────────────────

DECISION_TREE = """
    Import error (ModuleNotFoundError)                  -> PACKAGING        (D1)
      "No module named 'crawl_engine'" / 'pytest' / 'pydantic'
      Fix: activate the project venv; `pip install -e ".[dev]"`; point the IDE
      interpreter at that venv.

    pytest assertion failure + traceback                -> IMPLEMENTATION / TEST DEFECT
      A test body fails an assert (not a collection/import error). Capture the
      traceback; this is a genuine code or test bug to file.

    Config load error (FileNotFoundError/ValidationError) -> CONFIGURATION
      Bad path or invalid YAML/values. Fix the config file.

    0 pages crawled AND fetches FAILED                  -> NETWORK           (D11)
      Every FETCH line shows ERR (timeout/connection/4xx/5xx). The site is
      unreachable from here: proxy / firewall / VPN / offline / IP or
      user-agent block. Not a code bug.

    0 pages crawled AND no fetch failures               -> CONFIGURATION / CRAWL LOGIC
      Seeds filtered out before fetch (allowed_paths / base_url mismatch), or
      seeds empty. Check the rejection reasons and seed/base_url.

    Fetches SUCCEED but queue drains with few pages     -> CRAWL LOGIC
      page_fetched OK yet links_discovered stays ~0 or everything is rejected
      (see 'url_skipped reasons'); suspect link extraction / allowed_paths
      filtering (D2 trailing-slash).

    Interrupted run, then checkpoint MISSING            -> D10
      No checkpoint until `checkpoint_interval` pages / clean finish; resume
      restarts from seeds.

    Healthy: pages_crawled>0, artifacts written, queue stays fed -> OK
"""


def verdict(signals) -> int:
    print()
    print(SEP)
    print("7. VERDICT")
    print(SEP)

    cat = signals.get("category")
    if cat == CONFIG:
        print("  >> CATEGORY: CONFIGURATION - config failed to load (see traceback above).")
        _print_tree()
        return CONFIG

    if signals.get("fatal"):
        print(f"  >> CATEGORY: IMPLEMENTATION - an exception escaped the crawl loop: "
              f"{signals['fatal']}")
        _print_tree()
        return CRAWL_LOGIC

    stats = signals.get("stats")
    events = signals.get("events", {})
    reasons = signals.get("reasons", {})
    fetched_ok = events.get("page_fetched", 0)
    failed = events.get("page_failed", 0)

    if stats is None:
        print("  >> CATEGORY: UNKNOWN - no stats produced.")
        _print_tree()
        return UNKNOWN

    if stats.pages_crawled == 0 and failed > 0:
        print("  >> CATEGORY: NETWORK (D11) - every fetch failed; the site is unreachable")
        print("     from this machine (proxy / firewall / VPN / offline / IP or UA block).")
        print("     This is NOT a code or packaging defect.")
    elif stats.pages_crawled == 0 and failed == 0:
        print("  >> CATEGORY: CONFIGURATION / CRAWL LOGIC - nothing fetched and nothing failed;")
        print("     seeds were likely filtered out (allowed_paths/base_url) or empty.")
        print(f"     rejection reasons = {reasons}")
    elif fetched_ok > 0 and stats.pages_crawled <= signals.get("seed_count", 1) \
            and stats.links_discovered == 0:
        print("  >> CATEGORY: CRAWL LOGIC - fetches succeeded but no links were discovered/")
        print("     enqueued; suspect link extraction / allowed_paths filtering (D2).")
    else:
        print(f"  >> CATEGORY: OK - healthy crawl "
              f"(crawled={stats.pages_crawled}, written={stats.artifacts_written}, "
              f"discovered={stats.links_discovered}).")
        _print_tree()
        return OK

    _print_tree()
    return NETWORK if (stats.pages_crawled == 0 and failed > 0) else CRAWL_LOGIC


def _print_tree():
    print()
    print("  SYMPTOM -> ROOT-CAUSE DECISION TREE")
    print(DECISION_TREE)


def main() -> int:
    ap = argparse.ArgumentParser(description="Single-run diagnostic for the crawl engine.")
    ap.add_argument("--config", default="config/config.yaml")
    ap.add_argument("--max-pages", type=int, default=8,
                    help="bound the diagnostic crawl (0 = use config value)")
    args = ap.parse_args()

    report_environment()
    ok, _err = check_import()
    if not ok:
        print()
        print(SEP)
        print("7. VERDICT")
        print(SEP)
        print("  >> CATEGORY: PACKAGING (D1) - the package/dependencies are not importable in")
        print("     THIS interpreter. Activate the project venv and run "
              '`pip install -e ".[dev]"`,')
        print("     or point your IDE's interpreter at that venv, then re-run.")
        _print_tree()
        return PACKAGING

    signals = run_instrumented(args.config, args.max_pages)
    return verdict(signals)


if __name__ == "__main__":
    sys.exit(main())
