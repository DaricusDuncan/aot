"""Reversible tool-output eviction for long-running AOT sessions.

Problem
-------
Large tool outputs — web fetches, browser snapshots, MCP responses, big
directory listings — accumulate in the conversation history and never leave
until lossy compaction discards them *entirely*. By then the agent may still
need an exact value from one of them, and has to redo the work.

`context_compressor.py` already clamps terminal stdout and `read_file`, but
that is (a) not universal and (b) irreversible.

Approach
--------
Make eviction reversible. The full output is persisted to a per-session
SQLite store; the in-context message is replaced with a compact, informative
*stub*. The agent can call the `restore_tool_output` tool to pull any stubbed
output back into context on demand.

This buys two things:
  1. Token savings now — stale heavy outputs shrink to ~30 tokens.
  2. No information loss — anything evicted is one tool call away from return.

Design notes
------------
* Eviction is keyed on a content hash, so identical outputs are de-duplicated.
* `pin` lets the agent (or a tool) mark an output as "keep verbatim" — pinned
  outputs are never evicted (e.g. a config file being actively edited).
* The store is session-scoped by default but the path is configurable, so a
  handoff (see session_handoff.py) can keep restorable outputs across a reset.
* Designed to run in the preflight step, just before `ContextCompressor`.
  Evicting first means the compressor has less to summarise.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import sqlite3
import time
from dataclasses import dataclass, field
from typing import Any, Iterable

log = logging.getLogger("aot.tool_output_store")

# Stub marker — kept distinctive so the agent and the compressor both
# recognise an evicted output and never try to "summarise" it further.
STUB_MARKER = "⧉ AOT_EVICTED_OUTPUT"

# Rough token estimate when an exact tokeniser count is unavailable.
_CHARS_PER_TOKEN = 4


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // _CHARS_PER_TOKEN)


def _content_to_text(content: Any) -> str:
    """Flatten OpenAI-style message content (str | list of parts) to text."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        chunks: list[str] = []
        for part in content:
            if not isinstance(part, dict):
                chunks.append(str(part))
            elif part.get("type") == "text":
                chunks.append(part.get("text", ""))
            elif part.get("type") in ("image_url", "image"):
                chunks.append("[image]")
            else:
                chunks.append(json.dumps(part, separators=(",", ":")))
        return "\n".join(chunks)
    return str(content)


@dataclass
class EvictionConfig:
    """Tunable thresholds. Wire these to config.yaml under `tool_output:`."""

    enabled: bool = True
    # Outputs in the most recent N turns are always left verbatim.
    keep_recent_turns: int = 20
    # Only evict outputs estimated at or above this many tokens.
    min_evict_tokens: int = 800
    # Hard cap on a single stored output (avoids a runaway 5MB scrape).
    max_store_bytes: int = 2_000_000


@dataclass
class EvictionStats:
    evicted_count: int = 0
    tokens_reclaimed: int = 0
    keys: list[str] = field(default_factory=list)


class ToolOutputStore:
    """SQLite-backed store of full tool outputs, keyed by content hash."""

    def __init__(self, db_path: str, config: EvictionConfig | None = None) -> None:
        self.config = config or EvictionConfig()
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._conn = sqlite3.connect(db_path)
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tool_outputs (
                key           TEXT PRIMARY KEY,
                tool_name     TEXT,
                token_estimate INTEGER,
                created_turn  INTEGER,
                created_at    REAL,
                content       TEXT
            )
            """
        )
        self._conn.commit()
        self._pinned: set[str] = set()

    @staticmethod
    def _make_key(tool_name: str, text: str) -> str:
        digest = hashlib.sha256(f"{tool_name}\x00{text}".encode()).hexdigest()
        return digest[:16]

    def pin(self, key: str) -> None:
        self._pinned.add(key)

    def unpin(self, key: str) -> None:
        self._pinned.discard(key)

    def _put(self, tool_name: str, text: str, turn: int) -> str:
        key = self._make_key(tool_name, text)
        if len(text.encode()) > self.config.max_store_bytes:
            text = text[: self.config.max_store_bytes] + "\n[...store cap reached...]"
        self._conn.execute(
            "INSERT OR REPLACE INTO tool_outputs VALUES (?,?,?,?,?,?)",
            (key, tool_name, _estimate_tokens(text), turn, time.time(), text),
        )
        self._conn.commit()
        return key

    def restore(self, key: str) -> str | None:
        row = self._conn.execute(
            "SELECT content FROM tool_outputs WHERE key = ?", (key,)
        ).fetchone()
        return row[0] if row else None

    def metadata(self, key: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT tool_name, token_estimate, created_turn FROM tool_outputs "
            "WHERE key = ?",
            (key,),
        ).fetchone()
        if not row:
            return None
        return {"tool_name": row[0], "token_estimate": row[1], "created_turn": row[2]}

    def close(self) -> None:
        self._conn.close()

    def evict_stale_outputs(
        self, messages: list[dict[str, Any]], current_turn: int
    ) -> EvictionStats:
        """Replace stale, heavy tool outputs in-place with restorable stubs.

        Mutates `messages` and returns eviction stats.
        Call this before ContextCompressor so the compressor has less to summarise.
        """
        stats = EvictionStats()
        if not self.config.enabled:
            return stats

        cfg = self.config
        name_by_call_id = self._index_tool_names(messages)
        cutoff_index = self._turn_cutoff_index(messages, current_turn, cfg.keep_recent_turns)

        for idx, msg in enumerate(messages):
            if idx >= cutoff_index:
                break
            if msg.get("role") != "tool":
                continue
            content = msg.get("content")
            if isinstance(content, str) and content.startswith(STUB_MARKER):
                continue  # already evicted

            text = _content_to_text(content)
            tokens = _estimate_tokens(text)
            if tokens < cfg.min_evict_tokens:
                continue

            call_id = msg.get("tool_call_id", "")
            tool_name = name_by_call_id.get(call_id, "tool")
            key = self._make_key(tool_name, text)
            if key in self._pinned:
                continue

            self._put(tool_name, text, current_turn)
            msg["content"] = self._render_stub(key, tool_name, tokens)
            stats.evicted_count += 1
            stats.tokens_reclaimed += tokens - _estimate_tokens(msg["content"])
            stats.keys.append(key)

        if stats.evicted_count:
            log.info(
                "Evicted %d tool outputs, reclaimed ~%d tokens",
                stats.evicted_count,
                stats.tokens_reclaimed,
            )
        return stats

    @staticmethod
    def _render_stub(key: str, tool_name: str, original_tokens: int) -> str:
        return (
            f"{STUB_MARKER} key={key}\n"
            f"Output of `{tool_name}` (~{original_tokens} tokens) was moved out "
            f"of context to save space. It is NOT lost. If you need its exact "
            f"contents, call restore_tool_output(key=\"{key}\")."
        )

    @staticmethod
    def _index_tool_names(messages: Iterable[dict[str, Any]]) -> dict[str, str]:
        names: dict[str, str] = {}
        for msg in messages:
            if msg.get("role") != "assistant":
                continue
            for call in msg.get("tool_calls", []) or []:
                cid = call.get("id")
                fn = (call.get("function") or {}).get("name")
                if cid and fn:
                    names[cid] = fn
        return names

    @staticmethod
    def _turn_cutoff_index(
        messages: list[dict[str, Any]], current_turn: int, keep_recent_turns: int
    ) -> int:
        protect_from_turn = max(0, current_turn - keep_recent_turns)
        turn = 0
        for idx, msg in enumerate(messages):
            if msg.get("role") == "user":
                turn += 1
                if turn > protect_from_turn:
                    return idx
        return len(messages)


# ---------------------------------------------------------------------------
# Module-level singleton — lets the restore tool handler reach the active store
# without requiring kwargs threading through the entire dispatch path.
# ---------------------------------------------------------------------------

_current_store: ToolOutputStore | None = None


def set_store(store: ToolOutputStore | None) -> None:
    global _current_store
    _current_store = store


def get_store() -> ToolOutputStore | None:
    return _current_store


# ---------------------------------------------------------------------------
# Agent-facing tool schema + handler
# ---------------------------------------------------------------------------

RESTORE_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "restore_tool_output",
        "description": (
            "Restore the full contents of a tool output that was moved out of "
            "context to save space (shown as an AOT_EVICTED_OUTPUT stub). Pass "
            "the key from the stub."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "key": {"type": "string", "description": "The key from the stub."},
                "pin": {
                    "type": "boolean",
                    "description": "If true, keep this output verbatim for the "
                    "rest of the session (do not evict it again).",
                    "default": False,
                },
            },
            "required": ["key"],
        },
    },
}


def handle_restore_tool_output(
    store: ToolOutputStore, key: str, pin: bool = False
) -> str:
    """Tool handler. Called from tools/restore_tool_output.py."""
    text = store.restore(key)
    if text is None:
        return f"No evicted output found for key {key!r}."
    if pin:
        store.pin(key)
    meta = store.metadata(key) or {}
    header = (
        f"[restored output of `{meta.get('tool_name', 'tool')}`, "
        f"~{meta.get('token_estimate', '?')} tokens"
        f"{', pinned' if pin else ''}]\n"
    )
    return header + text
