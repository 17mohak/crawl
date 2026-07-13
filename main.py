"""Crawl Engine entry point.

CE-001: Project builds successfully and runs locally.
"""
import argparse
import sys
from pathlib import Path

# Bootstrap: make the src/ layout importable even without `pip install -e .`
# (dependencies still need to be installed). This lets `python main.py` work
# straight from a clone.
_SRC = Path(__file__).resolve().parent / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from crawl_engine.config.loader import load_config  # noqa: E402
from crawl_engine.logging.logger import setup_logger  # noqa: E402
from crawl_engine.reliability.crawler import Crawler  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="OHSERS Pension Content Crawl Engine",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--config",
        default="config/config.yaml",
        help="Path to YAML config file",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume from checkpoint if one exists",
    )
    args = parser.parse_args()

    try:
        config = load_config(args.config)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Config validation error: {e}", file=sys.stderr)
        return 1

    logger = setup_logger(config.log_path)

    print(f"Config loaded from: {args.config}")
    print(f"  Seeds        : {len(config.seed_urls)}")
    print(f"  Max depth    : {config.max_depth}")
    print(f"  Max pages    : {config.max_pages or 'unlimited'}")
    print(f"  Output dir   : {config.output_dir}")
    print(f"  Log file     : {config.log_path}")
    print(f"  Resume       : {args.resume}")
    print()
    print("Starting crawl...")

    try:
        stats = Crawler(config, logger).run(resume=args.resume)
    except KeyboardInterrupt:
        print(
            "\nInterrupted. Progress was checkpointed — resume with --resume.",
            file=sys.stderr,
        )
        return 130

    print()
    print("Crawl finished.")
    print(f"  Pages crawled      : {stats.pages_crawled}")
    print(f"  Pages failed       : {stats.pages_failed}")
    print(f"  Pages skipped      : {stats.pages_skipped}")
    print(f"  Artifacts written  : {stats.artifacts_written}")
    print(f"  Artifacts unchanged: {stats.artifacts_unchanged}")
    print(f"  Links discovered   : {stats.links_discovered}")

    # D11: don't report a silent "success" when nothing was actually crawled.
    if stats.pages_crawled == 0:
        if stats.pages_failed > 0:
            print(
                "\nERROR: 0 pages crawled and every fetch failed. The site appears "
                "unreachable\nfrom this machine. Check network / proxy / VPN / firewall, "
                "and whether the\nsite is blocking the configured user-agent. "
                "(See the log for per-URL reasons.)",
                file=sys.stderr,
            )
            return 2
        print(
            "\nWARNING: 0 pages crawled and no fetch failures. The seeds were likely "
            "filtered\nout (check base_url / allowed_paths) or the seed list is empty.",
            file=sys.stderr,
        )
        return 3

    return 0


if __name__ == "__main__":
    sys.exit(main())
