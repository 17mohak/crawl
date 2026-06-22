"""CE-003: Configuration loader.

Loads a YAML config file and validates it against a typed schema.
All runtime behaviour of the crawl engine is driven by this config
so that nothing is hardcoded.

CFG-001: seed_urls
CFG-002: base_url
CFG-003: allowed_paths
CFG-004: max_depth
CFG-005: max_pages
CFG-006: request_timeout
CFG-007: max_retries / backoff
CFG-008: output_dir
CFG-009: checkpoint_path

AC-017: Config loads and validates successfully.
"""
from pathlib import Path

import yaml
from pydantic import BaseModel, field_validator, model_validator


class RetryConfig(BaseModel):
    max_attempts: int = 3
    backoff_factor: float = 2.0   # seconds between attempts: factor^attempt
    backoff_max: float = 60.0     # cap on wait time


class CrawlConfig(BaseModel):
    # CFG-001
    seed_urls: list[str]

    # CFG-002
    base_url: str

    # CFG-003: empty list = all paths allowed
    allowed_paths: list[str] = []

    # Query-string keys stripped during canonicalization (CE-014).
    # Matched case-insensitively. Defaults cover the common analytics/ad trackers.
    tracking_params: list[str] = [
        "utm_source",
        "utm_medium",
        "utm_campaign",
        "utm_term",
        "utm_content",
        "gclid",
        "gclsrc",
        "dclid",
        "fbclid",
        "msclkid",
        "mc_cid",
        "mc_eid",
        "yclid",
        "igshid",
        "_ga",
    ]

    # Main-content extraction (CE-024): CSS selectors tried in order; the first
    # that matches non-empty content wins. Falls back to <body> if none match.
    content_selectors: list[str] = [
        "main",
        "article",
        "[role=main]",
        "#main-content",
        "#main",
        "#content",
        ".main-content",
        ".content",
    ]

    # Noise removal (CE-025): elements matching these selectors are stripped
    # before content extraction (nav, chrome, scripts, etc.). Includes common
    # WordPress/Bootstrap menu patterns, since many sites (incl. ohsers.org)
    # build navigation from <div>/<ul> menus rather than semantic <nav> tags.
    noise_selectors: list[str] = [
        "script",
        "style",
        "noscript",
        "nav",
        "header",
        "footer",
        "aside",
        "form",
        ".sidebar",
        ".breadcrumb",
        ".breadcrumbs",
        ".skip-link",
        "[role=navigation]",
        "[role=banner]",
        "[role=contentinfo]",
        ".navbar-nav",          # Bootstrap nav lists
        ".menu-item",           # WordPress menu items
        "[class*=menu-container]",  # WordPress menu wrappers
        "[class*=nav-menu]",
    ]

    # CFG-004
    max_depth: int = 3

    # CFG-005: 0 = no limit
    max_pages: int = 0

    # CFG-006
    request_timeout: int = 30

    # CFG-007
    retry: RetryConfig = RetryConfig()

    # CFG-008
    output_dir: Path = Path("output/raw")

    # CFG-009
    checkpoint_path: Path = Path("output/checkpoint.json")

    # How many pages to process between checkpoint saves (CE-036).
    checkpoint_interval: int = 50

    # Logging
    log_path: Path = Path("output/crawl.jsonl")

    # User-agent sent with every request
    user_agent: str = "CrawlEngine/0.1 (research prototype)"

    @field_validator("seed_urls")
    @classmethod
    def require_at_least_one_seed(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("seed_urls must contain at least one URL")
        return v

    @field_validator("max_depth")
    @classmethod
    def positive_depth(cls, v: int) -> int:
        if v < 1:
            raise ValueError("max_depth must be >= 1")
        return v

    @field_validator("request_timeout")
    @classmethod
    def positive_timeout(cls, v: int) -> int:
        if v < 1:
            raise ValueError("request_timeout must be >= 1")
        return v

    @model_validator(mode="after")
    def base_url_in_seeds(self) -> "CrawlConfig":
        """Warn if no seed URL starts with base_url — likely a config mistake."""
        if not any(u.startswith(self.base_url) for u in self.seed_urls):
            raise ValueError(
                f"None of the seed_urls begin with base_url '{self.base_url}'. "
                "Check your config — seed URLs should be under the base domain."
            )
        return self


def load_config(path: str | Path) -> CrawlConfig:
    """
    Load and validate configuration from a YAML file.

    Raises:
        FileNotFoundError: if the config file doesn't exist.
        pydantic.ValidationError: if required fields are missing or invalid.
    """
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with config_path.open(encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    if not isinstance(raw, dict):
        raise ValueError(f"Config file must contain a YAML mapping, got {type(raw)}")

    return CrawlConfig(**raw)
