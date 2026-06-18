"""Markdown conversion, frontmatter, and content hashing.

CE-027: HTML to Markdown conversion  (FR-006 / AC-004 — content converted successfully)
CE-028: YAML frontmatter generation  (FR-007 / AC-004 — all required frontmatter fields present)
CE-032: Content hash generation      (FR-009 / AC-006 — hash generated consistently)

⚠️ CE-028 schema is INFERRED, not confirmed. The backlog only says "all required
frontmatter fields present" and points at a requirements doc (FR-007) that has
not been received. The field set below comes from HANDOFF.md's worked example.
It is built so adding/renaming a field later is a one-line change. Confirm the
exact contract with the supervisor before treating this as final.

Determinism note (NFR-001 / CE-041): ``content_hash`` is computed over the
*stable* content (title + markdown body) and deliberately excludes the volatile
``crawled_at`` timestamp. Combined with skip-unchanged (CE-033), this is what
lets a re-run produce byte-identical output: unchanged content hashes the same,
so the existing file (with its original timestamp) is left untouched.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone

import html2text
import yaml

from crawl_engine.extraction.parser import ParsedPage


def html_to_markdown(html: str) -> str:
    """CE-027: convert an HTML fragment to Markdown.

    ``body_width = 0`` disables line wrapping so output is stable and not
    re-flowed at an arbitrary column (important for deterministic hashing/diffs).
    """
    converter = html2text.HTML2Text()
    converter.body_width = 0
    converter.ignore_images = False
    converter.ignore_links = False
    markdown = converter.handle(html or "").strip()
    return markdown + "\n" if markdown else ""


def compute_content_hash(text: str) -> str:
    """CE-032: stable ``sha256:<hex>`` digest of UTF-8 text."""
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def format_timestamp(dt: datetime) -> str:
    """Format a datetime as ISO-8601 UTC with a trailing Z (e.g. 2026-06-18T10:23:00Z)."""
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def render_frontmatter(fields: dict) -> str:
    """CE-028: render an ordered dict as a YAML frontmatter block.

    ``sort_keys=False`` preserves the insertion order of ``fields`` so the
    output layout is deterministic and matches the documented schema order.
    """
    body = yaml.safe_dump(fields, sort_keys=False, default_flow_style=False, allow_unicode=True)
    return f"---\n{body}---\n"


def build_markdown_document(
    page: ParsedPage,
    depth: int,
    canonical_url: str,
    crawled_at: datetime | None = None,
) -> tuple[str, str]:
    """Assemble a full Markdown artifact (frontmatter + body) for a parsed page.

    Returns ``(document_text, content_hash)``. The content hash covers only the
    stable content (title + body), not the frontmatter, so it can be compared
    across runs for skip-unchanged (CE-033).
    """
    if crawled_at is None:
        crawled_at = datetime.now(timezone.utc)

    body = html_to_markdown(page.content_html)
    content_hash = compute_content_hash(f"{page.title}\n{body}")

    # INFERRED CE-028 schema — order is intentional and load-bearing for layout.
    frontmatter = render_frontmatter(
        {
            "url": page.url,
            "canonical_url": canonical_url,
            "title": page.title,
            "crawled_at": format_timestamp(crawled_at),
            "content_hash": content_hash,
            "depth": depth,
            "source_section": page.source_section,
        }
    )

    document = f"{frontmatter}\n{body}"
    return document, content_hash
