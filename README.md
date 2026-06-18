# Crawl Engine

Web crawler for ingesting OHSERS pension content into structured Markdown artifacts.
Part of the Pension LLM Wiki Assistant research project.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

## Run

```bash
python main.py --config config/config.yaml
```

## Test

```bash
pytest tests/ -v
```

## Project structure

```
src/crawl_engine/
├── config/        # CE-003: Configuration loader
├── logging/       # CE-002: JSONL logging framework
├── discovery/     # CE-004 to CE-011: URL queue, BFS, link extraction
├── extraction/    # CE-019 to CE-026: HTTP fetch, HTML parse, content extract
├── storage/       # CE-027 to CE-034: Markdown conversion, YAML frontmatter, file write
└── reliability/   # CE-035 to CE-038: Checkpoint, failure isolation
```

## Backlog status

| Feature | Tasks | Status |
|---|---|---|
| Project Setup | CE-001 to CE-003 | ✅ Done |
| URL Discovery | CE-004 to CE-011 | Not started |
| Canonicalization | CE-012 to CE-018 | Not started |
| HTML Extraction | CE-019 to CE-026 | Not started |
| Markdown Storage | CE-027 to CE-034 | Not started |
| Reliability | CE-035 to CE-038 | Not started |
| Testing | CE-039 to CE-044 | Not started |
| Documentation | CE-045 | Not started |

## Development note

Until the package is installed via `pip install -e .`, run with:

```bash
PYTHONPATH=src python main.py --config config/config.yaml
PYTHONPATH=src pytest tests/unit/ -v
```
