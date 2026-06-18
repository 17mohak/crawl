"""Checkpoint save and reload.

CE-036: Checkpoint save and reload  (FR-019, FR-020 / AC-013 — resume continues
correctly after restart)

A checkpoint bundles the three pieces of crawl state needed to resume:
the BFS queue (pending URLs + counters), the Seen URL registry, and the running
stats. It is written atomically (temp file + ``os.replace``) so a crash during a
checkpoint write can't corrupt the existing checkpoint.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from crawl_engine.discovery.queue import CrawlQueue
from crawl_engine.discovery.registry import SeenRegistry


def save_checkpoint(
    path: str | Path,
    queue: CrawlQueue,
    registry: SeenRegistry,
    stats: dict,
) -> None:
    """Atomically write queue + registry + stats to ``path`` as JSON."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "queue": queue.snapshot(),
        "seen": registry.snapshot(),
        "stats": stats,
    }
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def load_checkpoint(path: str | Path) -> tuple[CrawlQueue, SeenRegistry, dict]:
    """Rebuild ``(queue, registry, stats)`` from a checkpoint written by
    :func:`save_checkpoint`."""
    path = Path(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    queue = CrawlQueue.restore(data["queue"])
    registry = SeenRegistry.restore(data["seen"])
    stats = data.get("stats", {})
    return queue, registry, stats


def checkpoint_exists(path: str | Path) -> bool:
    """True if a checkpoint file exists at ``path``."""
    return Path(path).exists()
