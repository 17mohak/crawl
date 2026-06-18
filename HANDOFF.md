# HANDOFF.md — Crawl Engine Build

## What this project is

This is the **crawl engine** for the Pension LLM Wiki Assistant research project (SERS internship,
supervisor: Sameer). It crawls ohsers.org (School Employees Retirement System of Ohio), extracts
pension content, and converts it into structured Markdown artifacts with YAML frontmatter. That
Markdown corpus is the shared input for a research comparison between two RAG architectures:

- **Architecture B** (baseline): Basic chunk-based RAG — indexes the raw Markdown directly.
- **Architecture A** (proposed): Ontology-Driven Wiki LLM — adds a structured knowledge layer
  (entities like `MemberTier`, `EligibilityRule`, `ServiceCredit`, `SurvivorBenefit`) on top of the
  same Markdown.

The crawl engine itself is architecture-agnostic. Its only job is to reliably turn ohsers.org pages
into clean, deterministic, idempotent Markdown files with provenance metadata. Both architectures
consume its output identically.

**This is an internship deliverable for Sameer, not a personal side project.** Code quality,
testability, and adherence to the backlog's acceptance criteria matter more than speed or cleverness.

---

## Current state (what's already built and verified)

Three tasks are done: **CE-001, CE-002, CE-003** — the "Project Setup" feature group. All other 42
tasks are **Not Started**.

| File | Task | What it does |
|---|---|---|
| `pyproject.toml` | CE-001 | Project metadata, dependencies, pytest config |
| `main.py` | CE-001 | CLI entry point — loads config, sets up logger, prints summary |
| `src/crawl_engine/config/loader.py` | CE-003 | Pydantic-validated YAML config loader (CFG-001 to CFG-009) |
| `src/crawl_engine/logging/logger.py` | CE-002 | JSONL structured event logger (`log_event()` helper) |
| `config/config.yaml` | CE-003 | Working config pre-filled with OHSERS seed URLs and paths |
| `tests/unit/test_config.py` | CE-003 | 9 tests, all passing |
| `tests/unit/test_logger.py` | CE-002 | 5 tests, all passing |

**Verified working:**
```bash
PYTHONPATH=src python main.py --config config/config.yaml   # runs cleanly
PYTHONPATH=src pytest tests/unit/ -v                          # 14/14 passing
```

### Design decisions already made (don't relitigate these without reason)

1. **Pydantic v2** for config validation, not raw dict access. Gives us typed config objects and
   validation errors instead of silent `KeyError`s deep in the crawl logic.
2. **`log_event(logger, event_type, **fields)`** is the standard way every module logs structured
   events. Don't use `logger.info("some string")` directly elsewhere in the codebase — always go
   through `log_event` so every log line is valid JSON with `timestamp`, `level`, `event_type` fields.
3. **Config-driven, not hardcoded.** Every crawl parameter (depth, page limit, timeout, retry policy,
   output dir, allowed paths) lives in `config/config.yaml` and is validated by
   `CrawlConfig` in `config/loader.py`. New features should add config fields here, not magic numbers
   in code.
4. **`src/` layout**, not flat. Package is `crawl_engine`, importable after `pip install -e .`. Until
   that's run, dev workflow uses `PYTHONPATH=src`.
5. Dependencies already chosen: `requests` (HTTP), `beautifulsoup4` + `lxml` (HTML parsing),
   `html2text` (Markdown conversion), `pyyaml` (config), `pydantic` (validation). Don't introduce
   alternatives (e.g. `httpx`, `markdownify`) without a clear reason — these were picked to keep the
   dependency surface small for a 3-month prototype.

---

## ⚠️ Open question that should block deep work — ask the user about this first

The backlog references requirement IDs (`FR-001` to `FR-023`, `NFR-001` to `NFR-007`,
`AC-001` to `AC-020`, `CFG-001` to `CFG-009`) that come from **a requirements document that has not
been seen**. The backlog only gives short labels (e.g. `FR-006` = "Download HTML pages"), not full
specs.

The original backlog as Sameer handed it over is in `docs/Crawl_Engine_Backlog.xlsx` (and mirrored
as `docs/crawl_engine_backlog.csv`). Everything in the tables below is my own reorganization of that
sheet by feature group with added build-order reasoning — if anything here seems off or incomplete,
go back to the original file, it's the source of truth, not this document.

Sameer has been asked for the full requirements document. **If the user hasn't gotten it yet, say so
plainly and proceed using the backlog's own descriptions as the spec — they're detailed enough to
build correctly against, just not detailed enough to guarantee every edge case matches Sameer's
original intent.** Flag specific ambiguities as they come up (e.g. CE-028's "all required
frontmatter fields" — the field list below is inferred, not confirmed) rather than guessing silently.

---

## Full backlog (45 tasks, ~57 estimated days)

Status legend: ✅ Done · 🔲 Not started

### Project Setup — 3 tasks, 3 days — ✅ ALL DONE

| ID | Task | Req | AC | Status |
|---|---|---|---|---|
| CE-001 | Setup Python project structure | NFR-001 | AC-017 | ✅ |
| CE-002 | Configure JSONL logging framework | FR-022 | AC-015 | ✅ |
| CE-003 | Create configuration loader | CFG-001 to CFG-009 | AC-017 | ✅ |

### URL Discovery — 8 tasks, 9 days — 🔲 NOT STARTED (build this next)

| ID | Task | Req | AC | Days |
|---|---|---|---|---|
| CE-004 | Load seed URLs from configuration | FR-001 | AC-001 | 1 |
| CE-005 | Implement BFS Queue Manager | FR-001 | AC-001 | 1 |
| CE-006 | Queue persistence support | FR-019 | AC-013 | 1 |
| CE-007 | Max depth enforcement | CFG-004 | AC-001 | 1 |
| CE-008 | Max page enforcement | CFG-005 | AC-001 | 1 |
| CE-009 | Internal link extraction | FR-004 | AC-002 | 2 |
| CE-010 | External link detection | FR-005 | AC-002 | 1 |
| CE-011 | Allowed path filtering | FR-004 | AC-002 | 1 |

Build order within this group: CE-004 → CE-005 → CE-007 → CE-008 → CE-009 → CE-010 → CE-011 → CE-006.
Reasoning: get a basic queue with depth/page limits working before adding link extraction, since
extraction needs somewhere to push discovered URLs to. Queue persistence (CE-006) depends on the
queue already existing, so it's last in this group even though it's numbered CE-006.

### Canonicalization — 7 tasks, 7 days — 🔲 NOT STARTED

| ID | Task | Req | AC | Days |
|---|---|---|---|---|
| CE-012 | Lowercase scheme and host | FR-002 | AC-003 | 1 |
| CE-013 | Remove URL fragments | FR-002 | AC-003 | 1 |
| CE-014 | Remove tracking query params | FR-002 | AC-003 | 1 |
| CE-015 | Normalize trailing slashes | FR-002 | AC-003 | 1 |
| CE-016 | Resolve relative URLs | FR-002 | AC-003 | 1 |
| CE-017 | Implement Seen URL registry | FR-003 | AC-001 | 1 |
| CE-018 | Unit tests for canonicalization | FR-002, FR-003 | AC-003 | 1 |

These five normalization steps (CE-012 to CE-016) should compose into a single `canonicalize(url)`
function applied before a URL ever reaches the Seen URL registry (CE-017) or the BFS queue. Order of
operations matters: resolve relative → lowercase → strip fragment → strip tracking params → strip
trailing slash. Write CE-018's tests against edge cases like `HTTP://OHSERS.ORG/Members/?utm_source=x#top`
all resolving to the same canonical form as `https://www.ohsers.org/members`.

### HTML Extraction — 8 tasks, 11 days — 🔲 NOT STARTED

| ID | Task | Req | AC | Days |
|---|---|---|---|---|
| CE-019 | Build HTTP Fetch Service | FR-006 | AC-004 | 2 |
| CE-020 | Request timeout handling | CFG-006 | AC-012 | 1 |
| CE-021 | Retry with exponential backoff | FR-018 | AC-012 | 2 |
| CE-022 | HTML parser implementation | FR-006 | AC-004 | 1 |
| CE-023 | Page title extraction | FR-007 | AC-004 | 1 |
| CE-024 | Main content extraction | FR-006 | AC-004 | 2 |
| CE-025 | Navigation/noise removal | FR-006 | AC-004 | 1 |
| CE-026 | Metadata extraction | FR-007 | AC-004 | 1 |

CE-019 to CE-021 form the fetch layer (use `requests.Session`, respect `config.request_timeout` and
`config.retry`, already validated by `CrawlConfig` in CE-003). CE-022 to CE-026 form the parse layer
(use BeautifulSoup + lxml). Main content extraction (CE-024) is the hardest task here — ohsers.org's
actual DOM structure needs inspecting to figure out the right CSS selectors / heuristics for
separating real content from nav, footer, and sidebar noise (CE-025).

### Markdown Storage — 8 tasks, 10 days — 🔲 NOT STARTED

| ID | Task | Req | AC | Days |
|---|---|---|---|---|
| CE-027 | HTML to Markdown conversion | FR-006 | AC-004 | 2 |
| CE-028 | YAML frontmatter generation | FR-007 | AC-004 | 1 |
| CE-029 | URL-to-path mapping | FR-006 | AC-004 | 2 |
| CE-030 | Raw folder creation | FR-006 | AC-004 | 1 |
| CE-031 | Atomic file write support | FR-008 | AC-005 | 1 |
| CE-032 | Content hash generation | FR-009 | AC-006 | 1 |
| CE-033 | Skip unchanged content | FR-009 | AC-006 | 1 |
| CE-034 | Save markdown artifacts | FR-006, FR-007 | AC-004 | 1 |

This is the most consequential feature group — its output is what both research architectures
consume. Inferred frontmatter schema for CE-028 (confirm against the requirements doc once
available):

```yaml
---
url: https://www.ohsers.org/members/service-retirement/
canonical_url: https://www.ohsers.org/members/service-retirement
title: "Service Retirement"
crawled_at: 2026-06-18T10:23:00Z
content_hash: sha256:abc123...
depth: 2
source_section: members
---
```

CE-029 (URL-to-path mapping) needs to be deterministic: the same URL should always map to the same
file path across runs (NFR-001, AC-017, tested by CE-041). A reasonable approach: mirror the URL
path structure under `output_dir`, e.g. `https://www.ohsers.org/members/service-retirement/` →
`output/raw/members/service-retirement/index.md`.

> **Downstream context, not a task requirement:** the research proposal this corpus feeds into
> describes a future ontology layer with entities like `MemberTier`, `EligibilityRule`,
> `ServiceCredit`, and `SurvivorBenefit`. None of that extraction logic belongs in this backlog —
> the crawl engine's job stops at clean, provenance-tagged Markdown. But if there's ever a genuinely
> free choice about an optional frontmatter field (e.g. whether to capture breadcrumb / section
> hierarchy alongside `source_section`), preserving that structure now is low-cost and could save
> rework later. Don't go looking for ways to use this — it's just tie-breaker context, not a reason
> to add scope.

CE-031 (atomic writes) should write to a temp file and `os.replace()` into place, never write
directly to the target path — this is what prevents corrupt partial files if the process is killed
mid-write.

CE-032/CE-033 (hash + skip-unchanged) is the idempotency mechanism (NFR-002, tested by CE-042):
hash the extracted content, compare against a stored hash, skip the write if unchanged.

### Reliability — 4 tasks, 6 days — 🔲 NOT STARTED

| ID | Task | Req | AC | Days |
|---|---|---|---|---|
| CE-035 | Crawl workflow integration | FR-001 to FR-009 | AC-001 to AC-006 | 2 |
| CE-036 | Checkpoint save and reload | FR-019, FR-020 | AC-013 | 2 |
| CE-037 | Structured event logging | FR-022, FR-023 | AC-015 | 1 |
| CE-038 | Failure isolation | FR-021 | AC-014 | 1 |

CE-035 is where Discovery, Canonicalization, Extraction, and Storage actually get wired together into
one end-to-end crawl loop. CE-037 should mostly be "make sure every module is already calling
`log_event()` correctly" rather than new code, since the logger from CE-002 already exists. CE-038
(failure isolation) means a single page's fetch/parse/save failure must be caught, logged via
`log_event(logger, "page_failed", url=..., reason=..., attempt=...)`, and the crawl continues to the
next URL — never let one bad page kill the whole run.

### Testing — 6 tasks, 9 days — 🔲 NOT STARTED

| ID | Task | Req | AC | Days |
|---|---|---|---|---|
| CE-039 | Unit Test Suite | Test Strategy | AC-001 to AC-006 | 3 |
| CE-040 | Integration Test Suite | Test Strategy | AC-001 to AC-016 | 2 |
| CE-041 | Determinism Validation | NFR-001 | AC-017 | 1 |
| CE-042 | Idempotency Validation | NFR-002 | AC-018 | 1 |
| CE-043 | Provenance Validation | NFR-005 | AC-019 | 1 |
| CE-044 | Reliability Validation | NFR-007 | AC-020 | 1 |

**Don't save all of this for the end.** Write unit tests alongside each feature group as it's built
(the way CE-002/CE-003 already have `tests/unit/test_config.py` and `test_logger.py` sitting next to
them). Treat CE-039 as a checkpoint/cleanup pass, not the first time tests get written. CE-041 to
CE-044 are specific validation runs: e.g. CE-041 means literally running the crawler twice on the
same input and diffing the output directories — they should be byte-identical.

### Documentation — 1 task, 2 days — 🔲 NOT STARTED

| ID | Task | Req | AC | Days |
|---|---|---|---|---|
| CE-045 | Developer Runbook | Definition of Done | DoD | 2 |

---

## Timeline reality check

Total estimate is **57 days** against an internship window that's roughly 60 working days. That's
almost no slack. If things start slipping, the first thing to flag to Sameer is whether some of the
9 days in Testing can be absorbed into each feature group as it's built (which is the better practice
anyway) rather than treated as a separate phase at the end.

---

## File structure

```
crawl_engine/
├── pyproject.toml              # CE-001
├── main.py                     # CE-001 — CLI entry point
├── README.md
├── HANDOFF.md                  # this file
├── CLAUDE_CODE_PROMPT.md       # starter prompt used to kick off this session
├── .gitignore
├── docs/
│   ├── Crawl_Engine_Backlog.xlsx   # original backlog from Sameer — source of truth
│   └── crawl_engine_backlog.csv    # same data, plain text for easier parsing
├── config/
│   └── config.yaml             # CE-003 — OHSERS seeds, paths, limits already filled in
├── src/crawl_engine/
│   ├── __init__.py
│   ├── config/
│   │   ├── __init__.py
│   │   └── loader.py           # CE-003 — CrawlConfig (Pydantic), load_config()
│   ├── logging/
│   │   ├── __init__.py
│   │   └── logger.py           # CE-002 — setup_logger(), log_event()
│   ├── discovery/
│   │   └── __init__.py         # 🔲 CE-004 to CE-011 go here
│   ├── extraction/
│   │   └── __init__.py         # 🔲 CE-019 to CE-026 go here
│   ├── storage/
│   │   └── __init__.py         # 🔲 CE-027 to CE-034 go here
│   └── reliability/
│       └── __init__.py         # 🔲 CE-035 to CE-038 go here
└── tests/
    ├── unit/
    │   ├── test_config.py      # 9 tests passing
    │   └── test_logger.py      # 5 tests passing
    └── integration/            # 🔲 empty, CE-040 goes here
```

Note: there's no `canonicalization/` module folder yet — CE-012 to CE-018 weren't assigned a home in
the original structure. Recommend creating `src/crawl_engine/discovery/canonicalize.py` since
canonicalization is tightly coupled to the discovery/dedup loop (the Seen URL registry in CE-017
needs canonical URLs as keys).

---

## How to run things

```bash
# First time setup
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[dev]"

# Run the crawler (currently just loads config + logs startup, no actual crawling yet)
python main.py --config config/config.yaml

# Run tests
pytest tests/unit/ -v

# If pip install -e hasn't been run yet, prefix commands with PYTHONPATH=src
PYTHONPATH=src python main.py --config config/config.yaml
PYTHONPATH=src pytest tests/unit/ -v
```

---

## Immediate next step

Start on **URL Discovery (CE-004 to CE-011)**. Suggested first move: implement `CrawlQueue` in
`src/crawl_engine/discovery/queue.py` — a BFS queue that wraps `collections.deque`, tracks
`(url, depth)` pairs, respects `max_depth` and `max_pages` from `CrawlConfig`, and exposes
`.push(url, depth)`, `.pop()`, `.is_exhausted()`. Write `tests/unit/test_queue.py` alongside it
following the same style as `test_config.py` and `test_logger.py`. Then move to link extraction
(CE-009/010/011) so the queue has something feeding it real URLs from ohsers.org pages.
