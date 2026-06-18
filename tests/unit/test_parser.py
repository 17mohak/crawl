"""Unit tests for HTML parsing and content extraction.

CE-022 (parse), CE-023 (title), CE-024 (main content),
CE-025 (noise removal), CE-026 (metadata). AC-004.
"""
from crawl_engine.config.loader import CrawlConfig
from crawl_engine.extraction.parser import (
    extract_main_content,
    extract_metadata,
    extract_title,
    parse_page,
    strip_noise,
)
from crawl_engine.extraction.parser import _make_soup

URL = "https://www.ohsers.org/members/service-retirement"


def make_config(**overrides) -> CrawlConfig:
    data = {
        "seed_urls": ["https://www.ohsers.org/members/"],
        "base_url": "https://www.ohsers.org",
    }
    data.update(overrides)
    return CrawlConfig(**data)


# ── CE-023: title extraction ──────────────────────────────────────────────────

def test_title_from_title_tag():
    soup = _make_soup("<html><head><title>Service Retirement</title></head></html>")
    assert extract_title(soup) == "Service Retirement"


def test_title_falls_back_to_h1():
    soup = _make_soup("<html><body><h1>Members</h1></body></html>")
    assert extract_title(soup) == "Members"


def test_title_falls_back_to_og_title():
    soup = _make_soup('<html><head><meta property="og:title" content="OG Title"></head></html>')
    assert extract_title(soup) == "OG Title"


def test_title_empty_when_absent():
    soup = _make_soup("<html><body><p>no title here</p></body></html>")
    assert extract_title(soup) == ""


# ── CE-026: metadata extraction ───────────────────────────────────────────────

def test_metadata_description_and_keywords():
    html = (
        '<meta name="description" content="Retirement info">'
        '<meta name="keywords" content="pension, sers">'
    )
    md = extract_metadata(_make_soup(html))
    assert md["description"] == "Retirement info"
    assert md["keywords"] == "pension, sers"


def test_metadata_open_graph():
    html = '<meta property="og:title" content="T"><meta property="og:type" content="article">'
    md = extract_metadata(_make_soup(html))
    assert md["og:title"] == "T"
    assert md["og:type"] == "article"


def test_metadata_lang():
    md = extract_metadata(_make_soup('<html lang="en"><body></body></html>'))
    assert md["lang"] == "en"


def test_metadata_omits_empty_values():
    md = extract_metadata(_make_soup('<meta name="description" content="">'))
    assert "description" not in md


# ── CE-025: noise removal ─────────────────────────────────────────────────────

def test_strip_noise_removes_nav_and_scripts():
    soup = _make_soup(
        "<body><nav>menu</nav><script>x=1</script><p>real</p><footer>foot</footer></body>"
    )
    strip_noise(soup, ["nav", "script", "footer"])
    assert "menu" not in soup.get_text()
    assert "foot" not in soup.get_text()
    assert "real" in soup.get_text()


# ── CE-024: main content extraction ───────────────────────────────────────────

def test_main_content_selected_by_selector():
    soup = _make_soup("<body><div>chrome</div><main><p>the content</p></main></body>")
    content = extract_main_content(soup, ["main"])
    assert content.get_text(strip=True) == "the content"


def test_main_content_tries_selectors_in_order():
    soup = _make_soup('<body><article>art</article><div id="content">div</div></body>')
    content = extract_main_content(soup, ["main", "article", "#content"])
    assert content.get_text(strip=True) == "art"


def test_main_content_skips_empty_selector_match():
    soup = _make_soup("<body><main></main><article>real content</article></body>")
    content = extract_main_content(soup, ["main", "article"])
    assert content.get_text(strip=True) == "real content"


def test_main_content_falls_back_to_body():
    soup = _make_soup("<body><p>just body</p></body>")
    content = extract_main_content(soup, ["main", "article"])
    assert "just body" in content.get_text()


# ── parse_page integration (CE-022) ───────────────────────────────────────────

def test_parse_page_end_to_end():
    html = """
    <html lang="en">
      <head>
        <title>Service Retirement</title>
        <meta name="description" content="How to retire">
      </head>
      <body>
        <nav>Home | Members</nav>
        <main>
          <h1>Service Retirement</h1>
          <p>You may retire at a certain age.</p>
          <h2>Eligibility</h2>
        </main>
        <footer>contact us</footer>
        <script>analytics()</script>
      </body>
    </html>
    """
    page = parse_page(html, URL, make_config())
    assert page.title == "Service Retirement"
    assert page.source_section == "members"
    assert page.metadata["description"] == "How to retire"
    assert page.metadata["lang"] == "en"
    assert page.headings == ["Service Retirement", "Eligibility"]
    # noise gone, content kept
    assert "retire at a certain age" in page.text
    assert "contact us" not in page.text
    assert "analytics" not in page.text
    assert "Home | Members" not in page.text


def test_parse_page_handles_empty_html():
    page = parse_page("", URL, make_config())
    assert page.title == ""
    assert page.source_section == "members"
    assert page.text == ""


def test_source_section_empty_for_root():
    page = parse_page("<html></html>", "https://www.ohsers.org/", make_config())
    assert page.source_section == ""
