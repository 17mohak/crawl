"""Unit tests for URL canonicalization (CE-018).

Covers CE-012 (lowercase scheme/host), CE-013 (strip fragment),
CE-014 (strip tracking params), CE-015 (trailing slash), CE-016 (resolve
relative). AC-003: canonical URLs consistent.
"""
from crawl_engine.discovery.canonicalize import canonicalize


# ── CE-012: lowercase scheme and host ─────────────────────────────────────────

def test_scheme_lowercased():
    assert canonicalize("HTTP://www.ohsers.org/members") == "http://www.ohsers.org/members"


def test_host_lowercased():
    assert canonicalize("https://WWW.OHSERS.ORG/members") == "https://www.ohsers.org/members"


def test_path_case_preserved():
    # CE-012 is "scheme and host" only — path case must be kept (paths can be
    # case-sensitive on the origin server).
    assert canonicalize("https://www.ohsers.org/Members") == "https://www.ohsers.org/Members"


# ── CE-013: remove fragments ──────────────────────────────────────────────────

def test_fragment_removed():
    assert canonicalize("https://www.ohsers.org/members#top") == "https://www.ohsers.org/members"


def test_two_fragments_collapse_to_same_url():
    a = canonicalize("https://www.ohsers.org/members#a")
    b = canonicalize("https://www.ohsers.org/members#b")
    assert a == b


# ── CE-014: remove tracking params ────────────────────────────────────────────

def test_single_tracking_param_removed():
    assert (
        canonicalize("https://www.ohsers.org/members?utm_source=x")
        == "https://www.ohsers.org/members"
    )


def test_tracking_param_removed_case_insensitively():
    assert (
        canonicalize("https://www.ohsers.org/members?UTM_Source=x")
        == "https://www.ohsers.org/members"
    )


def test_non_tracking_param_preserved():
    assert (
        canonicalize("https://www.ohsers.org/members?id=42")
        == "https://www.ohsers.org/members?id=42"
    )


def test_tracking_stripped_but_real_param_kept():
    out = canonicalize("https://www.ohsers.org/search?q=cola&utm_campaign=spring")
    assert out == "https://www.ohsers.org/search?q=cola"


def test_custom_tracking_params_override_defaults():
    out = canonicalize("https://www.ohsers.org/members?ref=newsletter", tracking_params=["ref"])
    assert out == "https://www.ohsers.org/members"


# ── CE-015: normalize trailing slashes ────────────────────────────────────────

def test_trailing_slash_removed():
    assert canonicalize("https://www.ohsers.org/members/") == "https://www.ohsers.org/members"


def test_slash_and_no_slash_agree():
    assert canonicalize("https://www.ohsers.org/members/") == canonicalize(
        "https://www.ohsers.org/members"
    )


def test_root_with_and_without_slash_agree():
    assert canonicalize("https://www.ohsers.org/") == canonicalize("https://www.ohsers.org")


# ── CE-016: resolve relative URLs ─────────────────────────────────────────────

def test_relative_path_resolved_against_base():
    out = canonicalize("retirement/", base="https://www.ohsers.org/members/")
    assert out == "https://www.ohsers.org/members/retirement"


def test_root_relative_resolved_against_base():
    out = canonicalize("/employers/", base="https://www.ohsers.org/members/")
    assert out == "https://www.ohsers.org/employers"


def test_absolute_url_ignores_base():
    out = canonicalize("https://www.ohsers.org/forms", base="https://other.example.com/")
    assert out == "https://www.ohsers.org/forms"


# ── composition: several normalizations at once ───────────────────────────────

def test_combined_normalizations():
    messy = "https://WWW.OHSERS.ORG/members/?utm_source=x&id=7#section"
    assert canonicalize(messy) == "https://www.ohsers.org/members?id=7"


def test_equivalent_variants_collapse_to_one_key():
    variants = [
        "https://www.ohsers.org/members",
        "https://www.ohsers.org/members/",
        "https://www.ohsers.org/members#top",
        "https://www.ohsers.org/members/?utm_source=x",
        "https://WWW.ohsers.org/members/",
    ]
    canonical = {canonicalize(v) for v in variants}
    assert canonical == {"https://www.ohsers.org/members"}


def test_handoff_example_documents_actual_behavior():
    """HANDOFF.md's worked example overreaches the actual CE-012..016 tasks.

    It claims ``HTTP://OHSERS.ORG/Members/?utm_source=x#top`` canonicalizes to
    ``https://www.ohsers.org/members`` — but that would additionally require
    forcing http->https, adding 'www', and lowercasing the path, none of which
    are backlog tasks. This test pins the *faithful* behavior so the gap is
    explicit and easy to revisit once the requirements doc lands.
    """
    out = canonicalize("HTTP://OHSERS.ORG/Members/?utm_source=x#top")
    assert out == "http://ohsers.org/Members"
    assert out != "https://www.ohsers.org/members"
