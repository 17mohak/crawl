"""HTTP Fetch Service.

CE-019: Build HTTP Fetch Service        (FR-006 / AC-004 — HTML downloaded successfully)
CE-020: Request timeout handling        (CFG-006 / AC-012 — requests time out correctly)
CE-021: Retry with exponential backoff  (FR-018 / AC-012 — retries follow configured policy)

A thin, testable wrapper over ``requests.Session`` that fetches a URL with a
configured timeout and retries transient failures (connection errors, timeouts,
and 5xx / 429 responses) with exponential backoff. Permanent failures (4xx
other than 429) are returned immediately without retrying.

Both the underlying session and the sleep function are injectable so the retry
and backoff behaviour can be unit-tested without real network or wall-clock
delays.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Callable

import requests

from crawl_engine.config.loader import CrawlConfig
from crawl_engine.logging.logger import log_event

# Status codes worth retrying: server-side errors and explicit rate limiting.
_RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})


@dataclass
class FetchResult:
    """Outcome of a fetch attempt (or sequence of attempts)."""

    url: str
    ok: bool
    status_code: int | None = None
    html: str | None = None
    content_type: str | None = None
    final_url: str | None = None  # after redirects
    attempts: int = 0
    error: str | None = None

    @property
    def is_html(self) -> bool:
        """True if the response advertised an HTML content type."""
        return bool(self.content_type and "html" in self.content_type.lower())


def backoff_delay(attempt: int, factor: float, cap: float) -> float:
    """Seconds to wait before the next attempt: ``min(factor**attempt, cap)``.

    ``attempt`` is 1-based (the delay after the first failed attempt uses
    ``attempt=1``).
    """
    return min(factor**attempt, cap)


class HttpFetcher:
    """Fetches pages over HTTP with configurable timeout and retry policy."""

    def __init__(
        self,
        config: CrawlConfig,
        session: requests.Session | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.timeout = config.request_timeout
        self.max_attempts = config.retry.max_attempts
        self.backoff_factor = config.retry.backoff_factor
        self.backoff_max = config.retry.backoff_max

        self.session = session or requests.Session()
        self.session.headers.update({"User-Agent": config.user_agent})
        self._sleep = sleep

    def fetch(self, url: str, logger: logging.Logger | None = None) -> FetchResult:
        """Fetch ``url``, retrying transient failures per the configured policy.

        Returns a :class:`FetchResult`. Never raises for network/HTTP errors —
        failures are reported via ``ok=False`` and ``error`` so a single bad
        page can't crash the crawl (failure isolation, CE-038).
        """
        last_error: str | None = None

        for attempt in range(1, self.max_attempts + 1):
            try:
                resp = self.session.get(url, timeout=self.timeout, allow_redirects=True)
            except requests.exceptions.Timeout:
                last_error = "timeout"
            except requests.exceptions.ConnectionError:
                last_error = "connection_error"
            except requests.exceptions.RequestException as exc:
                # Non-transient request error — don't retry.
                return self._fail(url, attempt, f"request_error: {exc}", logger)
            else:
                if resp.status_code in _RETRYABLE_STATUS:
                    last_error = f"http_{resp.status_code}"
                else:
                    return self._from_response(url, resp, attempt, logger)

            # Reached only when this attempt failed transiently.
            if logger is not None:
                log_event(
                    logger,
                    "fetch_retry",
                    url=url,
                    attempt=attempt,
                    max_attempts=self.max_attempts,
                    reason=last_error,
                )
            if attempt < self.max_attempts:
                self._sleep(backoff_delay(attempt, self.backoff_factor, self.backoff_max))

        return self._fail(url, self.max_attempts, last_error or "unknown", logger)

    # ── helpers ──────────────────────────────────────────────────────────────

    def _from_response(
        self,
        url: str,
        resp: requests.Response,
        attempt: int,
        logger: logging.Logger | None,
    ) -> FetchResult:
        ok = 200 <= resp.status_code < 300
        result = FetchResult(
            url=url,
            ok=ok,
            status_code=resp.status_code,
            html=resp.text if ok else None,
            content_type=resp.headers.get("Content-Type"),
            final_url=resp.url,
            attempts=attempt,
            error=None if ok else f"http_{resp.status_code}",
        )
        if logger is not None:
            if ok:
                log_event(
                    logger,
                    "page_fetched",
                    url=url,
                    status_code=resp.status_code,
                    content_length=len(result.html or ""),
                    attempts=attempt,
                )
            else:
                log_event(
                    logger,
                    "page_failed",
                    url=url,
                    reason=result.error,
                    attempt=attempt,
                )
        return result

    def _fail(
        self,
        url: str,
        attempts: int,
        error: str,
        logger: logging.Logger | None,
    ) -> FetchResult:
        if logger is not None:
            log_event(logger, "page_failed", url=url, reason=error, attempt=attempts)
        return FetchResult(url=url, ok=False, attempts=attempts, error=error)
