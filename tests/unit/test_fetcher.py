"""Unit tests for the HTTP Fetch Service.

CE-019: fetch service        (AC-004)
CE-020: timeout handling      (AC-012)
CE-021: retry with backoff    (AC-012)

A fake session drives the retry/backoff logic without real network or sleeps.
"""
import requests

from crawl_engine.config.loader import CrawlConfig
from crawl_engine.extraction.fetcher import HttpFetcher, backoff_delay


# ── test doubles ──────────────────────────────────────────────────────────────

class FakeResponse:
    def __init__(self, status_code=200, text="<html></html>", content_type="text/html", url=None):
        self.status_code = status_code
        self.text = text
        self.headers = {"Content-Type": content_type}
        self.url = url or "https://www.ohsers.org/members"


class FakeSession:
    """Returns/raises a scripted sequence of responses for successive .get calls."""

    def __init__(self, outcomes):
        self._outcomes = list(outcomes)
        self.headers = {}
        self.calls = 0

    def get(self, url, timeout=None, allow_redirects=True):
        self.calls += 1
        self.last_timeout = timeout
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def make_config(**overrides) -> CrawlConfig:
    data = {
        "seed_urls": ["https://www.ohsers.org/members/"],
        "base_url": "https://www.ohsers.org",
        "request_timeout": 30,
        "retry": {"max_attempts": 3, "backoff_factor": 2.0, "backoff_max": 60.0},
    }
    data.update(overrides)
    return CrawlConfig(**data)


def make_fetcher(outcomes, **cfg_overrides):
    sleeps = []
    session = FakeSession(outcomes)
    fetcher = HttpFetcher(make_config(**cfg_overrides), session=session, sleep=sleeps.append)
    return fetcher, session, sleeps


URL = "https://www.ohsers.org/members"


# ── backoff math (CE-021) ─────────────────────────────────────────────────────

def test_backoff_delay_grows_exponentially():
    assert backoff_delay(1, 2.0, 60.0) == 2.0
    assert backoff_delay(2, 2.0, 60.0) == 4.0
    assert backoff_delay(3, 2.0, 60.0) == 8.0


def test_backoff_delay_capped():
    assert backoff_delay(10, 2.0, 60.0) == 60.0


# ── happy path (CE-019) ───────────────────────────────────────────────────────

def test_successful_fetch_returns_html():
    fetcher, session, _ = make_fetcher([FakeResponse(200, "<html>hi</html>")])
    result = fetcher.fetch(URL)
    assert result.ok is True
    assert result.status_code == 200
    assert result.html == "<html>hi</html>"
    assert result.is_html is True
    assert result.attempts == 1
    assert session.calls == 1


def test_timeout_passed_to_session():
    fetcher, session, _ = make_fetcher([FakeResponse()], request_timeout=12)
    fetcher.fetch(URL)
    assert session.last_timeout == 12


def test_user_agent_set_on_session():
    fetcher, session, _ = make_fetcher([FakeResponse()])
    assert "User-Agent" in session.headers


# ── permanent failures: no retry (CE-019/021) ─────────────────────────────────

def test_404_not_retried():
    fetcher, session, _ = make_fetcher(
        [FakeResponse(404, text="nope")], retry={"max_attempts": 3, "backoff_factor": 2.0}
    )
    result = fetcher.fetch(URL)
    assert result.ok is False
    assert result.status_code == 404
    assert result.error == "http_404"
    assert session.calls == 1  # not retried


# ── transient failures: retry then succeed (CE-021) ───────────────────────────

def test_retries_on_500_then_succeeds():
    fetcher, session, sleeps = make_fetcher([FakeResponse(500), FakeResponse(200, "<html>ok</html>")])
    result = fetcher.fetch(URL)
    assert result.ok is True
    assert result.attempts == 2
    assert session.calls == 2
    assert sleeps == [2.0]  # one backoff between the two attempts


def test_retries_on_timeout_then_succeeds():
    fetcher, session, sleeps = make_fetcher(
        [requests.exceptions.Timeout(), FakeResponse(200, "<html>ok</html>")]
    )
    result = fetcher.fetch(URL)
    assert result.ok is True
    assert result.attempts == 2


def test_retries_on_connection_error_then_succeeds():
    fetcher, _, _ = make_fetcher(
        [requests.exceptions.ConnectionError(), FakeResponse(200)]
    )
    assert fetcher.fetch(URL).ok is True


# ── transient failures: exhaust attempts (CE-021) ─────────────────────────────

def test_gives_up_after_max_attempts():
    fetcher, session, sleeps = make_fetcher(
        [FakeResponse(503), FakeResponse(503), FakeResponse(503)]
    )
    result = fetcher.fetch(URL)
    assert result.ok is False
    assert result.error == "http_503"
    assert result.attempts == 3
    assert session.calls == 3
    assert sleeps == [2.0, 4.0]  # backoff between attempts 1->2 and 2->3, none after last


def test_all_timeouts_reports_timeout_error():
    fetcher, _, _ = make_fetcher([requests.exceptions.Timeout()] * 3)
    result = fetcher.fetch(URL)
    assert result.ok is False
    assert result.error == "timeout"
    assert result.attempts == 3
