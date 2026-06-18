"""HTML parsing and content extraction.

CE-022: HTML parser implementation   (FR-006 / AC-004 — HTML parsed without errors)
CE-023: Page title extraction        (FR-007 / AC-004 — title stored in metadata)
CE-024: Main content extraction      (FR-006 / AC-004 — main content extracted accurately)
CE-025: Navigation/noise removal     (FR-006 / AC-004 — noise removed from content)
CE-026: Metadata extraction          (FR-007 / AC-004 — required metadata captured)

Turns raw HTML into a :class:`ParsedPage`: a clean main-content subtree (with
nav/footer/script noise stripped), the page title, a list of headings, a
``source_section`` derived from the URL, and a metadata dict from ``<meta>``
tags. Content selection and noise removal are driven by config selectors
(``content_selectors`` / ``noise_selectors``) so they can be tuned to the
target site without code changes.

⚠️ CE-024 caveat: the default ``content_selectors`` are reasonable generic
heuristics, but the *right* selectors for ohsers.org need to be confirmed
against the live DOM. This is flagged for inspection once the site structure is
verified — see the project handoff notes.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import urlsplit

from bs4 import BeautifulSoup
from bs4.element import Tag

from crawl_engine.config.loader import CrawlConfig


@dataclass
class ParsedPage:
    """The structured result of parsing one HTML page."""

    url: str
    title: str
    content_html: str
    text: str
    source_section: str
    headings: list[str] = field(default_factory=list)
    metadata: dict[str, str] = field(default_factory=dict)


def _make_soup(html: str) -> BeautifulSoup:
    """CE-022: parse HTML with lxml (the configured parser)."""
    return BeautifulSoup(html or "", "lxml")


def extract_title(soup: BeautifulSoup) -> str:
    """CE-023: page title from <title>, falling back to <h1> then og:title."""
    if soup.title and soup.title.string and soup.title.string.strip():
        return soup.title.string.strip()
    h1 = soup.find("h1")
    if h1 and h1.get_text(strip=True):
        return h1.get_text(strip=True)
    og = soup.find("meta", attrs={"property": "og:title"})
    if og and og.get("content", "").strip():
        return og["content"].strip()
    return ""


def extract_metadata(soup: BeautifulSoup) -> dict[str, str]:
    """CE-026: collect useful <meta> values and document language.

    Captures ``description``, ``keywords``, OpenGraph ``og:*`` tags, and the
    ``<html lang>`` attribute when present. Empty values are omitted.
    """
    metadata: dict[str, str] = {}

    for name in ("description", "keywords", "author"):
        tag = soup.find("meta", attrs={"name": name})
        if tag and tag.get("content", "").strip():
            metadata[name] = tag["content"].strip()

    for tag in soup.find_all("meta", attrs={"property": True}):
        prop = tag.get("property", "")
        if prop.startswith("og:") and tag.get("content", "").strip():
            metadata[prop] = tag["content"].strip()

    html_tag = soup.find("html")
    if html_tag and html_tag.get("lang", "").strip():
        metadata["lang"] = html_tag["lang"].strip()

    return metadata


def strip_noise(soup: BeautifulSoup, noise_selectors: list[str]) -> None:
    """CE-025: remove nav/footer/script and other noise in place."""
    for selector in noise_selectors:
        for element in soup.select(selector):
            element.decompose()


def extract_main_content(soup: BeautifulSoup, content_selectors: list[str]) -> Tag:
    """CE-024: return the main-content subtree.

    Tries each selector in order and returns the first match that contains
    non-whitespace text. Falls back to <body>, then to the whole document.
    """
    for selector in content_selectors:
        element = soup.select_one(selector)
        if element and element.get_text(strip=True):
            return element
    if soup.body is not None:
        return soup.body
    return soup


def _source_section(url: str) -> str:
    """Derive a coarse section label from the first URL path segment.

    e.g. ``https://www.ohsers.org/members/retirement`` -> ``members``.
    """
    segments = [seg for seg in urlsplit(url).path.split("/") if seg]
    return segments[0] if segments else ""


def extract_headings(content: Tag) -> list[str]:
    """Collect h1–h4 heading texts in document order (for downstream chunking)."""
    headings = []
    for tag in content.find_all(["h1", "h2", "h3", "h4"]):
        text = tag.get_text(strip=True)
        if text:
            headings.append(text)
    return headings


def parse_page(html: str, url: str, config: CrawlConfig) -> ParsedPage:
    """Parse a page into a :class:`ParsedPage` (CE-022..CE-026).

    Title and metadata are read from the full document before noise removal;
    main content is extracted after noise is stripped so nav/footer/scripts
    don't leak into the saved artifact.
    """
    soup = _make_soup(html)

    title = extract_title(soup)            # CE-023 — read before stripping noise
    metadata = extract_metadata(soup)      # CE-026 — read before stripping noise

    strip_noise(soup, config.noise_selectors)                 # CE-025
    content = extract_main_content(soup, config.content_selectors)  # CE-024

    return ParsedPage(
        url=url,
        title=title,
        content_html=str(content),
        text=content.get_text(separator=" ", strip=True),
        source_section=_source_section(url),
        headings=extract_headings(content),
        metadata=metadata,
    )
