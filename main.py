"""Crawl Engine entry point.

CE-001: Project builds successfully and runs locally.
"""
import argparse
import sys
from pathlib import Path

from crawl_engine.config.loader import load_config
from crawl_engine.logging.logger import log_event, setup_logger


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

    log_event(
        logger,
        "crawl_started",
        seed_urls=config.seed_urls,
        max_depth=config.max_depth,
        max_pages=config.max_pages,
        output_dir=str(config.output_dir),
        resume=args.resume,
    )

    print(f"Config loaded from: {args.config}")
    print(f"  Seeds        : {len(config.seed_urls)}")
    print(f"  Max depth    : {config.max_depth}")
    print(f"  Max pages    : {config.max_pages or 'unlimited'}")
    print(f"  Output dir   : {config.output_dir}")
    print(f"  Log file     : {config.log_path}")
    print()
    print("CE-001 to CE-003 complete.")
    print("Next: implement URL Discovery (CE-004 to CE-011).")

    return 0


if __name__ == "__main__":
    sys.exit(main())
