# Crawl Engine — Engineering Audit Report

**Auditor stance:** independent engineer reviewing the repository before any repair.
**Constraint:** no implementation code was modified, improved, or committed. This report is the deliverable.
**Date of audit:** 2026-07-01
**Repo state audited:** git `HEAD = dbe4fc3` ("CE-024: tune content/noise selectors against live ohsers.org DOM"); tracked tree clean; only untracked files are `AUDIT_REPORT.md`, `diagnose.py`, `requirements.txt`. (No git remote is configured that this audit could observe.)

---

## 0. Executive summary

Three claims prompted this audit: (a) many tests are failing, (b) `main.py` performs very
little crawling, (c) the implementation is inconsistent with intended behaviour.

**Under a correctly-configured environment, none of the three reproduce.** Every claim was
tested by execution, not assumption:

- **Tests:** `178 passed` (165 unit + 13 integration), ~4.4 s, zero failures/errors — run with
  the project venv and `PYTHONPATH=src` (§2).
- **Crawler:** a bounded end-to-end run against the live site crawled 6 pages, discovered
  **388 internal links**, wrote 6 Markdown artifacts, failed 0, and wrote a checkpoint (§3).
  The site is reachable from the audit host and returns HTTP 200.

**Both reported symptoms reproduce only as *environmental* faults**, and they match how the
project has been invoked in practice (commands issued from the parent directory / with a
non-venv interpreter):

| What was run | Result | Symptom it explains |
|---|---|---|
| `pytest tests/` from the **parent** dir | `collected 0 items … no tests ran` | "tests failing / not running" |
| `python main.py --config config/config.yaml` from **parent** dir | `Error: Config file not found: config\config.yaml` | "does nothing" |
| `import crawl_engine` under **system** Python (not the venv) | `ModuleNotFoundError: No module named 'crawl_engine'` | pytest collection errors → "many tests failing" |

The project lives in a **nested** layout: the shell's working directory is
`Downloads/crawl_engine`, but the actual project (with `config/`, `tests/`, `pyproject.toml`,
`.venv`) is one level down in `Downloads/crawl_engine/crawl_engine`. Run from the wrong level,
or with an interpreter that lacks the editable install, and the reported symptoms follow
directly.

**Genuine code defects exist** independent of the environment issue and are catalogued in §5:
D2 (path-filter trailing-slash logic bug — confirmed by reproduction), D11 (silent total-fetch
failure), D10 (checkpoint robustness), D3 (log volume), and lower-severity D4–D9.

**What could not be reproduced:** any *assertion-level* test failure, or an *early-stopping /
minimal* crawl, under a correctly installed environment with network access. If the operator
observed assertion failures (not import/collection errors) or a healthy-network run that still
stops early, the raw terminal output is needed to characterise a genuinely different
environment.

---

## 1. Environment & methodology

| Item | Value |
|---|---|
| OS | Windows 11 |
| Project (nested) root | `…\Downloads\crawl_engine\crawl_engine` |
| Project venv | `.venv\Scripts\python.exe` — Python 3.12.10; `crawl_engine` installed **editable** (`direct_url.json` → `"editable": true`) |
| System interpreter | `…\Programs\Python\Python312\python.exe` — no project deps; `import crawl_engine` fails |
| Installed deps (venv) | pydantic-core 2.46.4, requests 2.34.2, lxml 6.1.1, html2text 2025.4.15, pyyaml 6.0.3, pytest 9.1.0 |

**Method:** every claim reproduced by execution. Tests run with the venv interpreter; the
crawler exercised end-to-end via the repo's own `diagnose.py` (a non-invasive runtime wrapper,
not implementation code) against the live config bounded to a few pages. Specific defects
(D2) reproduced with minimal scripts calling the real functions.

---

## 2. Test suite execution

### 2.1 Authoritative result — documented environment (venv + `PYTHONPATH=src`)

```
$ PYTHONPATH=src .venv/Scripts/python.exe -m pytest tests/ -q
178 passed in 4.41s
```
Collection by directory: **165 unit + 13 integration = 178**. No failures, no errors, no
skips. Result confirmed on a repeat run.

### 2.2 Reproduction of "many tests failing" (environmental)

```
# from the PARENT directory (Downloads/crawl_engine):
$ .../.venv/Scripts/python.exe -m pytest tests/
collected 0 items — no tests ran in 0.01s

# under the system interpreter (no editable install, no PYTHONPATH):
$ python -c "import crawl_engine"
ModuleNotFoundError: No module named 'crawl_engine'
```
If a runner has `pytest` but not the project installed, collection proceeds and **every test
errors at import** with `ModuleNotFoundError: No module named 'crawl_engine'` — which presents
to the operator as "many tests failing." No test *body* asserts falsely.

### 2.3 Failing-test catalogue

| Test | Assertion | Stack trace | Root cause | Test or impl wrong? |
|---|---|---|---|---|
| *(none under documented env)* | — | — | — | — |
| *all tests, wrong dir / non-venv interpreter* | none — collection/import error | `ModuleNotFoundError: crawl_engine` or `collected 0 items` | package not on path (no editable install / wrong CWD) | **Environment**, not code |

> **Limitation:** the exact command/interpreter that produced the operator's "failing tests"
> was not observed. Definitively: the committed code passes 178/178 under its venv, and the
> failures are reproducible purely as import/collection errors under an interpreter/CWD lacking
> the editable install. If the operator saw *assertion* failures with tracebacks, that
> indicates a different environment and should be shared for re-audit.

---

## 3. End-to-end crawler execution (as an end user)

Run via `diagnose.py` (bounds the crawl, wraps the real `Crawler` without modifying it),
against `config/config.yaml`, `--max-pages 6`:

```
FETCH OK status=200 attempts=1  https://www.ohsers.org/members
FETCH OK status=200 attempts=1  https://www.ohsers.org/employers
FETCH OK status=200 attempts=1  https://www.ohsers.org/retirees
FETCH OK status=200 attempts=1  https://www.ohsers.org/members/member-education
…
pages_crawled       6
pages_failed        0
pages_skipped       0
artifacts_written   6
artifacts_unchanged 0
links_discovered    388
url_skipped reasons {'path_not_allowed': 131, 'external': 35}
checkpoint written? True
VERDICT: OK — healthy crawl
```

Stage-by-stage verification:

| Stage | Observed | Verdict |
|---|---|---|
| Queue population (seeds) | 3 seeds canonicalized & queued at depth 0 | OK |
| URL discovery | 388 internal links from 6 pages | OK |
| Canonicalization | trailing slash stripped, fragments/tracking removed | OK (interacts with D2) |
| Filtering | external (35) + disallowed (131) skipped & logged | OK — but 131 includes section roots wrongly dropped by **D2** |
| Fetch loop | real HTTP, redirects followed, retry policy honoured | OK |
| Parser | title/content/metadata extracted; nav stripped | OK (CE-024 selector quality validated on `/members/` sample only) |
| Markdown generation | 6 artifacts with YAML frontmatter | OK |
| Checkpoint creation | `output/checkpoint.json` written on clean finish | OK (but see **D10**) |
| Resume | `--resume` loads checkpoint | OK (but see **D5**) |
| Output directory | mirrored URL structure → `raw/<path>/index.md` | OK |

**Where crawling stops:** at the configured `max_pages` budget, as designed. With the default
config (`max_pages: 500`) the queue is far from exhausted (388 links from 6 pages), so there is
**no early-exhaustion / minimal-crawl logic bug** on this host.

**Failure-mode reasoning (D11):** if fetches fail instead (unreachable host), no HTML is
returned → `extract_links` yields nothing → the queue drains after the seeds →
`is_exhausted()` becomes true → the loop ends cleanly with 0 artifacts and exit 0. That path
is indistinguishable from "the tool is broken" to an operator whose network can't reach the
site — the substance of symptom (b) when there is no crash.

---

## 4. CE requirement conformance

Assessed by execution + code inspection (not by mere presence of code). "Works?" judged under
the documented venv environment.

| CE | Requirement | Implemented | Works | Notes |
|---|---|---|---|---|
| CE-001 | Project builds & runs locally | Yes | **Partial** | Only via editable install / `PYTHONPATH=src`; fails under wrong CWD / system interpreter |
| CE-002 | JSONL logging | Yes | Yes | Schema fields present; console volume noisy → D3 |
| CE-003 | Config loader (CFG-001..009) | Yes | Yes | Pydantic-validated; tested |
| CE-004 | Load seed URLs | Yes | Yes | Canonicalized then queued at depth 0 |
| CE-005 | BFS queue | Yes | Yes | FIFO verified |
| CE-006 | Queue persistence | Yes | Yes | snapshot/restore + checkpoint |
| CE-007 | Max depth | Yes | Yes | Verified |
| CE-008 | Max pages | Yes | Yes | Verified (stop-at-budget) |
| CE-009 | Internal link extraction | Yes | Yes | Resolved against post-redirect URL |
| CE-010 | External link detection | Yes | Yes | Skipped + logged |
| CE-011 | Allowed-path filtering | Yes | **Partial** | Trailing-slash-sensitive → **D2** (reproduced) |
| CE-012–016 | Canonicalization | Yes | **Partial** | Faithful to task wording; no www/https folding → D9 |
| CE-017 | Seen registry | Yes | Yes | Dedup on canonical URLs |
| CE-018 | Canonicalization tests | Yes | Yes | Pass |
| CE-019 | HTTP fetch service | Yes | Yes | `requests.Session` |
| CE-020 | Timeout | Yes | Yes | Per-request |
| CE-021 | Retry + backoff | Yes | Yes | Transient-only; tested |
| CE-022 | HTML parser | Yes | Yes | lxml |
| CE-023 | Title | Yes | Yes | `<title>`→`<h1>`→og:title |
| CE-024 | Main content | Yes | Yes* | Selectors validated on `/members/` sample only |
| CE-025 | Noise removal | Yes | Yes* | WordPress/div-menu nav stripped on tested pages |
| CE-026 | Metadata | Yes | Yes | meta/og/lang |
| CE-027 | HTML→Markdown | Yes | Yes | html2text, `body_width=0` |
| CE-028 | YAML frontmatter | Yes | **Partial** | Schema **inferred**, unconfirmed; `url` ≡ `canonical_url` → D4 |
| CE-029 | URL→path mapping | Yes | Yes | Deterministic |
| CE-030 | Folder creation | Yes | Yes | Auto-created |
| CE-031 | Atomic write | Yes | Yes | temp + `os.replace` |
| CE-032 | Content hash | Yes | Yes | sha256, excludes `crawled_at` |
| CE-033 | Skip unchanged | Yes | Yes | Idempotent (verified) |
| CE-034 | Save artifacts | Yes | Yes | Verified |
| CE-035 | Workflow integration | Yes | Yes | End-to-end verified |
| CE-036 | Checkpoint save/reload | Yes | **Partial** | Resume works; no checkpoint until 50 pages / on interrupt → **D10**; reporting → D5 |
| CE-037 | Structured event logging | Yes | Yes | All events via `log_event`; volume → D3 |
| CE-038 | Failure isolation | Yes | Yes | Per-page try/except; tested |
| CE-039–044 | Test/validation suites | Yes | Yes | 178 pass; live-socket tests are env-sensitive → D8 |
| CE-045 | Runbook | Yes | Yes | `docs/RUNBOOK.md` present |

`*` = validated on a limited sample of page types.

**No CE requirement is fully broken.** CE-001 and CE-011 are the substantive *Partial*s (setup
+ D2). CE-028 / CE-012–016 carry scope caveats (D4, D9).

---

## 5. Defect report

### D1 — Not runnable without editable install / correct CWD · **Severity: Critical (setup)**
- **Location:** packaging (`src/` layout, `pyproject.toml`) + entry points ([main.py:8](src/crawl_engine/../../main.py), `tests/`).
- **Root cause:** `crawl_engine` is importable only after `pip install -e .` or with
  `PYTHONPATH=src`, and `main.py` resolves `config/config.yaml` relative to CWD. The nested
  directory layout invites running from the parent, and the system interpreter lacks the deps.
- **Observed:** from parent dir → `pytest`: `collected 0 items`; `main.py`: `Config file not
  found`. System interpreter → `ModuleNotFoundError: No module named 'crawl_engine'`.
- **Expected:** documented commands work, or fail with an actionable message.
- **Reproduce:** run `pytest tests/` or `python main.py …` from `Downloads/crawl_engine`
  (the parent), or with a non-venv Python.
- **Suggested repair (not applied):** add a console-script entry point in `pyproject.toml`;
  a `sys.path` bootstrap fallback in `main.py`; resolve config path relative to the file;
  document the exact `cd`/venv step; point the IDE interpreter at `.venv`.
- **Requirements affected:** CE-001. **Most probable cause of "many tests failing" and of
  "main.py does nothing" (immediate error).**

### D2 — `allowed_paths` filtering is trailing-slash-sensitive · **Severity: Medium (logic — reproduced)**
- **Location:** [links.py:50-58](src/crawl_engine/discovery/links.py#L50-L58), `_path_allowed` (`return any(path.startswith(prefix) …)`).
- **Root cause:** prefixes carry trailing slashes (`/forms/`), but `canonicalize()` **strips**
  the trailing slash. So the canonical form `/forms` fails `"/forms".startswith("/forms/")`.
- **Observed (reproduced):** `_path_allowed("https://x/forms", ["/forms/"]) → False`;
  `"/forms/" → True`. And `canonicalize(".../forms/") → ".../forms"`, then allow-check → `False`.
- **Expected:** a section-root link (`/forms`) is in-scope.
- **Downstream impact:** section landing pages linked without a trailing slash are silently
  skipped → under-crawling. Contributes to the 131 `path_not_allowed` skips observed in §3.
- **Suggested repair (not applied):** compare on slash-normalized forms, or allow prefix OR
  exact-section-root.
- **Requirements affected:** CE-011 (FR-004/AC-002).

### D3 — Console log volume floods stdout · **Severity: Medium (usability)**
- **Location:** [logger.py:52-55](src/crawl_engine/logging/logger.py#L52-L55) (console handler at INFO).
- **Root cause:** high-frequency events (`url_discovered`, `url_skipped`, `links_extracted`,
  `page_fetched`, `file_saved`) all emit at INFO to stdout.
- **Observed:** a 6-page bounded run generated hundreds of records; `max_pages: 500` would
  print on the order of 10⁴–10⁵ lines.
- **Suggested repair (not applied):** raise console level to exclude per-link events; keep
  verbose events in the JSONL file only.
- **Requirements affected:** CE-002/CE-037 (functionally satisfied; quality issue).

### D4 — `url` and `canonical_url` frontmatter fields are always identical · **Severity: Low (provenance)**
- **Location:** [crawler.py:146](src/crawl_engine/reliability/crawler.py#L146) (`parse_page(result.html, item.url, …)`) → [markdown.py:84-94](src/crawl_engine/storage/markdown.py#L84-L94).
- **Root cause:** the crawler only ever processes already-canonical URLs, so `page.url` equals
  its own canonicalization; neither reflects the actual post-redirect fetched URL.
- **Observed:** artifact frontmatter shows `url` == `canonical_url` (both slash-stripped) even
  though the page is served with a trailing slash.
- **Suggested repair (not applied):** record `result.final_url` (or original `item.url`) as
  `url`, keep `canonicalize(...)` as `canonical_url`.
- **Requirements affected:** CE-028, FR-007/NFR-005.

### D5 — `--resume` reports restored cumulative stats · **Severity: Low (reporting)**
- **Location:** [crawler.py:74-95](src/crawl_engine/reliability/crawler.py#L74-L95); printed in `main.py`.
- **Root cause:** on resume, `CrawlStats` is rebuilt from the checkpoint. After a *completed*
  crawl the queue is exhausted, yet the summary prints the restored totals as if work occurred.
- **Suggested repair (not applied):** track/print session-delta counters, or label as cumulative.
- **Requirements affected:** CE-036 (functionally correct; clarity).

### D6 — `setup_logger` ignores a changed `log_path` on re-call · **Severity: Low (edge)**
- **Location:** [logger.py:40-41](src/crawl_engine/logging/logger.py#L40-L41) (`if logger.handlers: return logger`).
- **Root cause:** early-return when handlers exist; a second call with the same `name` but a
  different `log_path` silently returns the old logger.
- **Downstream impact:** negligible for the single-run CLI; a trap for future callers.

### D7 — No robots.txt compliance / politeness / rate limiting · **Severity: Medium (operational; out of CE scope)**
- **Location:** [fetcher.py](src/crawl_engine/extraction/fetcher.py) / [crawler.py](src/crawl_engine/reliability/crawler.py) — no delay, no robots parsing.
- **Root cause:** not implemented; no CE task requires it.
- **Downstream impact:** a full `max_pages: 500` run hits the live site back-to-back;
  etiquette/operational risk. A fixed non-browser user-agent can also trigger site-side blocks
  that manifest as D11.
- **Suggested repair (not applied):** optional inter-request delay and/or robots handling —
  confirm scope first.

### D8 — 4 integration tests bind a live localhost socket · **Severity: Low/Medium (test fragility)**
- **Location:** [test_live_server.py](tests/integration/test_live_server.py) (`ThreadingTCPServer` on 127.0.0.1).
- **Root cause:** requires loopback binding; in a locked-down sandbox these would error and
  read as "failing tests."
- **Suggested repair (not applied):** add a `network`/`live` marker so they can be deselected.
- **Requirements affected:** CE-040.

### D9 — Canonicalization does not fold `www`/non-`www` or `http`/`https` · **Severity: Low (dedup edge)**
- **Location:** [canonicalize.py](src/crawl_engine/discovery/canonicalize.py).
- **Root cause:** intentional scope decision matching literal CE-012..016 wording; documented.
- **Downstream impact:** same content under `ohsers.org` vs `www.ohsers.org`, or `http` vs
  `https`, would be treated as distinct → duplicate crawls/artifacts.
- **Suggested repair (not applied):** add host/scheme folding if the requirements call for it.

### D10 — No checkpoint until 50 pages / none on interruption · **Severity: Medium (resume robustness)**
- **Location:** [crawler.py:97-108](src/crawl_engine/reliability/crawler.py#L97-L108) — checkpoint written only when
  `processed_since_checkpoint >= checkpoint_interval` (default 50) or once after a clean loop exit; no SIGINT/SIGTERM handler.
- **Root cause:** the first checkpoint appears only after `checkpoint_interval` pages or on
  normal completion; an interruption before then writes nothing.
- **Downstream impact:** up to `checkpoint_interval` pages of progress lost on interruption;
  total loss if fewer than that were done. `--resume` then restarts from seeds. Undermines the
  resume guarantee for long, interruptible crawls.
- **Reproduce:** run the default config, interrupt before 50 pages, check for `output/checkpoint.json`.
- **Suggested repair (not applied):** checkpoint after seeding / after the first page; install
  a signal handler that checkpoints before exit; consider a smaller default interval.
- **Requirements affected:** CE-036 (FR-019/FR-020/AC-013), CE-038/NFR-007.

### D11 — Total fetch failure is silent; a network/proxy block looks like "barely any crawling" · **Severity: High (operability)**
- **Location:** [fetcher.py:78-116](src/crawl_engine/extraction/fetcher.py#L78-L116) (returns `ok=False` on all failures)
  + [crawler.py](src/crawl_engine/reliability/crawler.py) (per-page failures isolated/counted; no aggregate "everything failed" detection)
  + `main.py` (prints counts only).
- **Root cause:** failures are isolated by design (CE-038), but there is **no detection of the
  pathological case where every fetch fails** (site unreachable). The crawler discovers no
  links, drains the queue, and exits 0 with `Pages crawled: 0` and no clear diagnostic.
- **Expected:** if all/most fetches fail — especially the seeds — exit non-zero and print an
  actionable message ("could not reach <host>; check network/proxy/VPN/user-agent").
- **Downstream impact:** an operator behind a proxy/firewall/VPN, offline, or whose IP/UA
  (`CrawlEngine/0.1 (research prototype)`) is blocked sees the crawler "run and produce almost
  nothing" — the most probable non-packaging explanation for symptom (b).
- **Reproduce:** point `seed_urls`/`base_url` at an unreachable host (or run offline/behind a
  blocking proxy); observe a clean exit with zero artifacts.
- **Suggested repair (not applied):** detect all-seeds-failed / high failure ratio → exit
  non-zero with a network diagnostic; surface the first fetch error verbatim.
- **Requirements affected:** operability of CE-019/CE-035; NFR-007 (reliability/observability).

---

## 6. Architecture inspection

| Aspect | Finding |
|---|---|
| Incorrect assumptions | Path filtering assumes trailing-slash-terminated prefixes while canonicalization strips them (D2). Provenance assumes canonical == requested URL (D4). |
| Logic bugs | D2 (path filter). No other crawl-breaking logic bug found. |
| Unreachable / dead code | One intentional defensive `break` in `crawler.py` (`# pragma: no cover`, guarded by `is_exhausted()`); not a defect. No dead code found. |
| Duplicated logic | Atomic-write (temp + `os.replace`) is implemented 3× — `storage/writer.py::atomic_write`, `discovery/queue.py::save`, `reliability/checkpoint.py`. Minor DRY issue, not a defect. |
| Broken control flow | None. Crawl loop, retry loop, and failure isolation are sound. |
| State corruption | None. Atomic writes protect artifacts and checkpoints. |
| Queue handling | Correct FIFO/BFS; depth & page limits enforced; per-run string dedup guard plus canonical Seen registry. |
| Canonicalization | Correct for stated scope; scope caveats (D9); interacts badly with D2. |
| Parser | Sound; `extract_main_content` falls back body→document; selector quality validated on a limited page sample (CE-024 caveat). |
| Storage | Sound; deterministic paths, atomic writes, idempotent skips, hash excludes timestamp. |
| Checkpoint / resume | Load/restore correct; but no early/interrupt checkpoint (D10); reporting nuance (D5). |
| CLI | Correct under venv; fails under wrong CWD / system interpreter (D1); no rate limiting (D7). |
| Observability | Total-fetch-failure exits 0 with no clear diagnostic (D11); console log volume high (D3). |
| Determinism note | `url_to_path` does not lowercase the path; two URLs differing only by path case map to different dirs that collide on case-insensitive (Windows) filesystems — a latent, order-dependent edge relevant to NFR-001, though canonicalization deliberately preserves path case. |

---

## 7. Conclusion & recommended triage order

Under a correct environment with network access, the suite passes **178/178** and the crawler
crawls deeply and continuously (§2.1, §3). The committed code is **not broken at its core.**
The operator's two symptoms most likely have environmental causes:

- **"Barely any crawling" (runs, then near-empty, no traceback)** → **D11**: the run
  environment cannot reach the site, or the crawler was invoked such that seeds fail. Every
  fetch fails, nothing is discovered, the tool exits 0 with no clear error.
- **"Many tests failing" / "main.py does nothing" (error, not assertion)** → **D1**: wrong
  working directory (parent instead of the nested project root) or a non-venv interpreter
  without the editable install. (A locked-down sandbox could also fail the 4 socket tests, D8.)

**Still unresolved, needs operator data:** no *assertion-level* test failure could be
reproduced under any correctly-installed environment. Share the raw terminal output — the
first error line disambiguates: `ModuleNotFoundError` / `collected 0 items` → D1;
`Pages crawled: 0 / Pages failed: N` → D11; a pytest assertion + traceback → a distinct
environment to re-audit.

Recommended repair order (pending go-ahead — **no fixes made**):

1. **Confirm the operator's environment / raw output** to pin D1 vs D8 vs D11 per symptom.
2. **D11** — detect total/seed fetch failure; exit non-zero with a network diagnostic.
3. **D1** — make the project unambiguously runnable (console-script entry point, file-relative
   config path, IDE interpreter guidance).
4. **D2** — fix trailing-slash path filtering (genuine under-crawl logic bug).
5. **D10** — checkpoint early / on interrupt.
6. **D3 / D7** — log volume; politeness/robots (scope confirmation needed).
7. **D4 / D5 / D8 / D6 / D9** — provenance, reporting, test fragility, edge robustness.

Two items are **owner decisions, not defects**: the CE-028 frontmatter schema (currently
inferred) and whether ORC Ch. 3309 ingestion is in scope.

---

## 8. Diagnostic aid

`diagnose.py` (repo root, non-invasive — imports and wraps the engine, changes no
implementation code) produces a one-run verdict categorising the failure as PACKAGING /
CONFIG / NETWORK / CRAWL-LOGIC / OK, with the process exit code encoding the category. Run it
first when a symptom appears:

```
# with the project venv active and `pip install -e ".[dev]"` done, from the nested project root:
python diagnose.py                         # uses config/config.yaml, bounded to 8 pages
python diagnose.py --config <file> --max-pages 5
```

During this audit it returned **OK** (healthy crawl, exit 0) under the documented environment.

---

*No crawl-engine implementation code was modified and no commits were made during this audit.
Evidence was gathered by running the existing test suite and `diagnose.py`, and by minimal
scripts calling the real functions (D2). This report is the deliverable.*
