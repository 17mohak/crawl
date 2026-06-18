I'm continuing work on a crawl engine project for an internship (supervisor: Sameer). Read
HANDOFF.md in this directory first — it has the full context: what the project is for, what's
already built and verified (CE-001 to CE-003), the complete 45-task backlog with status, the design
decisions already made, and the recommended build order for what's next.

The original backlog is also in `docs/Crawl_Engine_Backlog.xlsx` (and as `docs/crawl_engine_backlog.csv`
if that's easier to parse) — this is the source of truth Sameer actually handed me. HANDOFF.md is my
own reorganization and interpretation of it, so if anything in HANDOFF.md seems to conflict with the
original sheet, the original sheet wins. Cross-check against it for the exact Task ID, Requirement ID,
Acceptance Criteria ID, and Definition of Done columns rather than relying solely on my summary.

After reading HANDOFF.md, here's what I need from you:

1. Confirm you understand the current state by running the existing tests
   (`PYTHONPATH=src pytest tests/unit/ -v`) and the entry point
   (`PYTHONPATH=src python main.py --config config/config.yaml`) so we're starting from a known-good
   baseline.

2. Start on URL Discovery (CE-004 to CE-011) in the order HANDOFF.md recommends. Follow the existing
   patterns in the codebase:
   - Use `log_event()` from `crawl_engine.logging.logger` for all structured logging, not raw
     `logger.info()` calls.
   - Add any new tunable parameters to `CrawlConfig` in `config/loader.py`, don't hardcode values.
   - Write unit tests alongside each piece of new code in `tests/unit/`, following the style of
     `test_config.py` and `test_logger.py` (clear test names, one behavior per test, edge cases
     covered).
   - Keep functions small and testable. This is a research prototype but the code quality should be
     production-reasonable — Sameer is reviewing this.

3. There's an open question flagged in HANDOFF.md: the backlog references a requirements document
   (FR-xxx, NFR-xxx, AC-xxx, CFG-xxx IDs) that I haven't received yet. I've asked Sameer for it. Until
   I have it, work from the backlog's own task descriptions and acceptance criteria — they're
   specific enough to build against. If you hit a genuine ambiguity (like the exact frontmatter field
   list for CE-028, which is only inferred in HANDOFF.md), flag it clearly rather than silently
   guessing, so I know what to double check once the requirements doc comes through.

4. After each feature group (Discovery, then Canonicalization, then HTML Extraction, then Markdown
   Storage, then Reliability), pause and give me a short summary of what got built, what's tested,
   and what's still open — don't silently barrel through all 42 remaining tasks in one go. I want
   visibility at each checkpoint so I can sanity check before we move to the next group.

Let's start with step 1.
