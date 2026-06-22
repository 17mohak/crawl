"""Crawl Engine entry point.

CE-001: Project builds successfully and runs locally.
"""
import argparse
import sys

from crawl_engine.config.loader import load_config
from crawl_engine.logging.logger import setup_logger
from crawl_engine.reliability.crawler import Crawler


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

    stats = Crawler(config, logger).run(resume=args.resume)

    print()
    print("Crawl finished.")
    print(f"  Pages crawled      : {stats.pages_crawled}")
    print(f"  Pages failed       : {stats.pages_failed}")
    print(f"  Pages skipped      : {stats.pages_skipped}")
    print(f"  Artifacts written  : {stats.artifacts_written}")
    print(f"  Artifacts unchanged: {stats.artifacts_unchanged}")
    print(f"  Links discovered   : {stats.links_discovered}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
