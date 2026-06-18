# Crawl Engine — Developer Runbook

**CE-045.** Operational guide for running, configuring, extending, and
troubleshooting the OHSERS pension crawl engine.

The crawl engine turns `ohsers.org` pages into clean, deterministic, idempotent
Markdown artifacts with YAML provenance frontmatter. That corpus is the shared
input for the Pension LLM Wiki Assistant research comparison (Architecture A:
ontology-driven wiki; Architecture B: baseline chunk-RAG). The engine itself is
architecture-agnostic — its job ends at provenance-tagged Markdown.

---

## 1. Setup

Requires Python ≥ 3.11.

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

If you haven't run `pip install -e .`, prefix commands with `PYTHONPATH=src`.

---

## 2. Running a crawl

```bash
python main.py --config config/config.yaml
```

| Flag | Default | Meaning |
|---|---|---|
| `--config` | `config/config.yaml` | Path to the YAML config |
| `--resume` | off | Resume from the checkpoint if one exists |

On completion the engine prints a summary (pages crawled / failed / skipped,
artifacts written / unchanged, links discovered) and writes:

- Markdown artifacts under `output_dir` (default `output/raw/`)
- a JSONL event log at `log_path` (default `output/crawl.jsonl`)
- a checkpoint at `checkpoint_path` (default `output/checkpoint.json`)

### Resuming

The crawl checkpoints every `checkpoint_interval` pages and once at the end. To
continue an interrupted run:

```bash
python main.py --config config/config.yaml --resume
```

Resume rebuilds the BFS queue and the Seen-URL registry from the checkpoint, so
already-crawled URLs are not refetched. Combined with skip-unchanged writes
(below), resuming is always safe to re-run.

---

## 3. Configuration reference

All runtime behaviour is config-driven and validated by `CrawlConfig`
(`src/crawl_engine/config/loader.py`). Invalid configs fail fast with a clear
error.

| Key | CFG | Default | Purpose |
|---|---|---|---|
| `seed_urls` | CFG-001 | — (required) | Starting URLs |
| `base_url` | CFG-002 | — (required) | Host used to classify internal vs external links |
| `allowed_paths` | CFG-003 | `[]` (all) | Only crawl URLs under these path prefixes |
| `max_depth` | CFG-004 | `3` | Max BFS depth from a seed (seeds are depth 0) |
| `max_pages` | CFG-005 | `0` (unlimited) | Max pages to dispatch |
| `request_timeout` | CFG-006 | `30` | Per-request timeout (seconds) |
| `retry` | CFG-007 | 3 / 2.0 / 60.0 | `max_attempts`, `backoff_factor`, `backoff_max` |
| `output_dir` | CFG-008 | `output/raw` | Where artifacts are written |
| `checkpoint_path` | CFG-009 | `output/checkpoint.json` | Resume state |
| `log_path` | — | `output/crawl.jsonl` | JSONL event log |
| `user_agent` | — | `CrawlEngine/0.1 …` | UA sent with every request |
| `tracking_params` | — | utm_*, gclid, fbclid, … | Query keys stripped in canonicalization |
| `content_selectors` | — | main, article, #content, … | Main-content CSS selectors (first non-empty wins) |
| `noise_selectors` | — | nav, header, footer, script, … | Elements stripped before extraction |
| `checkpoint_interval` | — | `50` | Pages between checkpoint saves |

> **Tuning content extraction:** if artifacts contain navigation/boilerplate or
> miss real content, adjust `content_selectors` / `noise_selectors` in the YAML —
> no code change needed. The defaults are generic; see Known Limitations.

---

## 4. Output format

Each page maps deterministically to `<output_dir>/<url-path>/index.md`, e.g.
`https://www.ohsers.org/members/service-retirement` →
`output/raw/members/service-retirement/index.md`. This layout means a page and
its sub-pages never collide.

Each artifact is YAML frontmatter followed by the Markdown body:

```markdown
---
url: https://www.ohsers.org/members/service-retirement
canonical_url: https://www.ohsers.org/members/service-retirement
title: Service Retirement
crawled_at: '2026-06-18T10:23:00Z'
content_hash: sha256:abc123...
depth: 2
source_section: members
---

# Service Retirement

...converted markdown body...
```

> ⚠️ **Frontmatter schema is inferred, not yet confirmed.** The field set above
> comes from the handoff example; the requirements document behind FR-007 has
> not been received. Confirm the exact contract with the supervisor before
> treating it as final. Adding/renaming a field is a one-line change in
> `storage/markdown.py`.

---

## 5. Guarantees

- **Determinism (NFR-001):** the same input produces the same output paths and
  content. Two from-scratch runs with the same crawl time are byte-identical.
  `crawled_at` is the only intentionally time-varying field.
- **Idempotency (NFR-002):** writes are skipped when a page's content hash is
  unchanged, so re-running creates no duplicates and rewrites nothing. The hash
  covers title + body and excludes `crawled_at`.
- **Atomic writes:** artifacts and checkpoints are written to a temp file then
  `os.replace`d into place — a crash never leaves a corrupt partial file.
- **Failure isolation (NFR-007):** a single page's fetch/parse/save failure is
  logged (`page_failed`) and counted; the crawl continues to the next URL.

---

## 6. Logging

Every event is one JSON object per line (JSONL) for machine analysis. All
modules emit via `log_event()`; never use `logger.info("string")` directly.

Common event types: `crawl_started`, `crawl_resumed`, `crawl_finished`,
`url_discovered`, `url_skipped` (reasons: `external`, `path_not_allowed`,
`already_queued`, `max_depth_exceeded`, `non_html`), `page_fetched`,
`fetch_retry`, `page_failed`, `links_extracted`, `file_saved`, `file_skipped`,
`queue_saved`.

Inspect, e.g.:

```bash
grep page_failed output/crawl.jsonl
```

---

## 7. Testing

```bash
pytest tests/ -v                                  # unit + integration
pytest tests/unit/ -v                             # unit only
pytest tests/ --cov=crawl_engine --cov-report=term-missing
```

Integration tests (`tests/integration/`) run the full crawl loop against an
in-memory site (`conftest.py::LocalSiteFetcher`) — no network. They cover the
validation tasks: determinism (CE-041), idempotency (CE-042), provenance
(CE-043), and reliability/bounded-failure (CE-044).

---

## 8. Architecture

```
main.py
  └─ reliability.Crawler.run()            # CE-035 — BFS loop, ties it together
       ├─ discovery.canonicalize()        # CE-012..016 — normalize URLs
       ├─ discovery.CrawlQueue            # CE-005..008 — BFS, depth/page limits
       ├─ discovery.SeenRegistry          # CE-017 — dedup on canonical URLs
       ├─ extraction.HttpFetcher.fetch()  # CE-019..021 — fetch, timeout, retry
       ├─ extraction.parse_page()         # CE-022..026 — title/content/meta
       ├─ storage.save_artifact()         # CE-027..034 — markdown + frontmatter
       │                                  #   + atomic write + skip-unchanged
       └─ discovery.extract_links()       # CE-009..011 — internal links to enqueue
  reliability.checkpoint                  # CE-036 — save/load queue+seen+stats
  logging.log_event()                     # CE-002 — JSONL events throughout
```

---

## 9. Known limitations / open items

1. **No live crawl has been run.** All tests use synthetic HTML. The default
   `content_selectors`/`noise_selectors` are generic and **unverified against
   the real `ohsers.org` DOM** (CE-024). Validate and tune them on real pages
   before relying on extraction quality.
2. **Frontmatter schema unconfirmed** (see §4) — pending the requirements doc.
3. **URL canonicalization is faithful to the backlog scope only** — it lowercases
   scheme/host, strips fragments, strips tracking params, and normalizes trailing
   slashes. It does *not* force `http`→`https`, fold `www`, or lowercase the
   path. If `ohsers.org` mixes those variants for internal links, add those
   steps in `discovery/canonicalize.py`.
4. **Scope is `ohsers.org` only.** The research proposal also references Ohio
   Revised Code Ch. 3309 statutory text; ingesting that is not currently in this
   engine's scope — confirm whether it should be.
