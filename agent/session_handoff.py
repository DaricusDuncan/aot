"""Cross-session handoff for AOT.

Problem
-------
Even with compaction, a session eventually has to be reset. Today that reset
is a hard wall: the next session starts blank and the user re-explains the
task, re-opens files, and rebuilds the agent's mental model by hand.

Approach
--------
Turn the hard reset into a soft one. AOT's `ContextCompressor` already
produces a structured handoff summary (Completed Actions / In Progress /
Active Task / Active State). This module persists that summary per project
and reseeds a fresh session from it, so a new conversation begins already
knowing where the last one left off.

It also records which `ToolOutputStore` backed the previous session, so an
evicted output can still be restored after a reset (see tool_output_store.py).

Lifecycle
---------
    write_handoff()   - call after each compaction and on clean shutdown.
    load_handoff()    - call at session start when `--handoff` is passed.
    build_resume_messages() - convert a handoff into seed messages.

Storage layout
--------------
    ~/.aot/handoffs/<project_slug>.json        latest handoff
    ~/.aot/handoffs/<project_slug>.history/    timestamped previous handoffs
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import asdict, dataclass, field
from typing import Any

log = logging.getLogger("aot.session_handoff")

RESUME_PREFIX = (
    "SESSION RESUMED. The text below is a handoff summary from a previous "
    "AOT session that ran out of context. Treat it as established background: "
    "the work described as completed is done; continue from the Active Task."
)

_HANDOFF_SCHEMA_VERSION = 2


def _slugify(project: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", project.lower()).strip("-")
    return slug or "default"


@dataclass
class Handoff:
    """A serialisable snapshot of where a session left off."""

    project: str
    summary: str
    active_task: str = ""
    open_files: list[str] = field(default_factory=list)
    tool_output_db: str | None = None
    compaction_count: int = 0
    created_at: float = field(default_factory=time.time)
    schema_version: int = _HANDOFF_SCHEMA_VERSION

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, ensure_ascii=False)

    @classmethod
    def from_json(cls, raw: str) -> "Handoff":
        data = json.loads(raw)
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in data.items() if k in known})


class HandoffStore:
    """Reads and writes per-project handoffs under a base directory."""

    def __init__(self, base_dir: str | None = None) -> None:
        self.base_dir = base_dir or os.path.expanduser("~/.aot/handoffs")
        os.makedirs(self.base_dir, exist_ok=True)

    def _path(self, project: str) -> str:
        return os.path.join(self.base_dir, f"{_slugify(project)}.json")

    def _history_dir(self, project: str) -> str:
        d = os.path.join(self.base_dir, f"{_slugify(project)}.history")
        os.makedirs(d, exist_ok=True)
        return d

    def write_handoff(self, handoff: Handoff) -> str:
        path = self._path(handoff.project)
        if os.path.exists(path):
            try:
                prev = Handoff.from_json(_read(path))
                archive = os.path.join(
                    self._history_dir(handoff.project),
                    f"{int(prev.created_at)}.json",
                )
                _write(archive, prev.to_json())
            except Exception as exc:
                log.warning("Could not archive previous handoff: %s", exc)

        _write(path, handoff.to_json())
        log.info(
            "Wrote handoff for %r (compaction #%d)",
            handoff.project,
            handoff.compaction_count,
        )
        return path

    def load_handoff(self, project: str) -> Handoff | None:
        path = self._path(project)
        if not os.path.exists(path):
            return None
        try:
            return Handoff.from_json(_read(path))
        except Exception as exc:
            log.error("Corrupt handoff for %r: %s", project, exc)
            return None

    def list_history(self, project: str) -> list[str]:
        d = self._history_dir(project)
        return sorted(
            (os.path.join(d, f) for f in os.listdir(d) if f.endswith(".json")),
            reverse=True,
        )


def build_resume_messages(handoff: Handoff) -> list[dict[str, Any]]:
    """Convert a handoff into seed messages for a fresh conversation.

    Returns a user-role briefing and an assistant-role acknowledgement.
    Two messages (rather than stuffing the system prompt) keeps the system
    prompt cache key stable and makes the resume visible in the transcript.
    """
    briefing = (
        f"{RESUME_PREFIX}\n\n"
        f"--- HANDOFF SUMMARY ---\n{handoff.summary.strip()}\n"
    )
    if handoff.open_files:
        briefing += "\nFiles open in the previous session:\n" + "\n".join(
            f"  - {p}" for p in handoff.open_files
        )
    if handoff.tool_output_db:
        briefing += (
            f"\n\nEvicted tool outputs from the previous session remain "
            f"restorable via restore_tool_output (store: {handoff.tool_output_db})."
        )
    if handoff.compaction_count >= 2:
        briefing += (
            f"\n\nNote: the previous session was compacted "
            f"{handoff.compaction_count} times — fine detail may be lossy. "
            f"Verify exact values (paths, configs) before relying on them."
        )

    ack = (
        "Understood. I've loaded the handoff summary and will continue from "
        f"the Active Task: {handoff.active_task or '(see summary)'}."
    )

    return [
        {"role": "user", "content": briefing},
        {"role": "assistant", "content": ack},
    ]


def handoff_from_compaction(
    project: str,
    summary: str,
    active_task: str,
    *,
    open_files: list[str] | None = None,
    tool_output_db: str | None = None,
    previous: Handoff | None = None,
) -> Handoff:
    """Build a Handoff from the output of a compaction pass."""
    count = (previous.compaction_count + 1) if previous else 1
    return Handoff(
        project=project,
        summary=summary,
        active_task=active_task,
        open_files=open_files or [],
        tool_output_db=tool_output_db,
        compaction_count=count,
    )


def _read(path: str) -> str:
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


def _write(path: str, text: str) -> None:
    tmp = f"{path}.tmp.{os.getpid()}"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(text)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)
