"""URL-to-path mapping.

CE-029: URL-to-path mapping  (FR-006 / AC-004 — path structure generated correctly)
CE-030: Raw folder creation  (FR-006 / AC-004 — folders auto-created)

Maps a (canonical) URL to a deterministic file path under ``output_dir`` by
mirroring the URL's path structure, with each page stored as ``index.md`` inside
a directory named for its path. This avoids file-vs-directory collisions: both
``/members`` and ``/members/retirement`` can exist
(``members/index.md`` and ``members/retirement/index.md``).

Determinism (NFR-001, tested by CE-041) is the whole point here: the same URL
must map to the same path on every run, regardless of crawl order.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path
from urllib.parse import urlsplit

# Characters not safe in path components on common filesystems (notably Windows).
_UNSAFE_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def _safe_segment(segment: str) -> str:
    """Replace filesystem-unsafe characters in a single path segment."""
    return _UNSAFE_CHARS.sub("-", segment)


def url_to_path(url: str, output_dir: str | Path) -> Path:
    """Map ``url`` to a deterministic ``index.md`` path under ``output_dir``.

    Examples:
        ``https://www.ohsers.org/members/service-retirement``
          -> ``<output_dir>/members/service-retirement/index.md``
        ``https://www.ohsers.org/``            -> ``<output_dir>/index.md``

    If the URL carries a query string, a short stable hash of it is folded into
    the filename so distinct queries don't overwrite each other.
    """
    parts = urlsplit(url)
    segments = [seg for seg in parts.path.split("/") if seg and seg not in (".", "..")]
    safe_segments = [_safe_segment(seg) for seg in segments]

    directory = Path(output_dir)
    if safe_segments:
        directory = directory.joinpath(*safe_segments)

    if parts.query:
        query_hash = hashlib.sha1(parts.query.encode("utf-8")).hexdigest()[:8]
        filename = f"index__{query_hash}.md"
    else:
        filename = "index.md"

    return directory / filename
