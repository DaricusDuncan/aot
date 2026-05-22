"""Hybrid context engine plugin.

Safety-first context compression that combines:
1) Rule-preserve pass for critical entities
2) Sentence-level pruning for readability
3) Optional lightweight token-level pruning on non-critical spans
4) Fidelity checks with automatic fallback when quality drops
"""

from __future__ import annotations

import json
import os
import re
import time
from typing import Any, Dict, List, Optional, Sequence, Tuple

from agent.context_engine import ContextEngine
from agent.model_metadata import estimate_messages_tokens_rough

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+|\n+")
_WHITESPACE_RE = re.compile(r"\s+")
_PATH_RE = re.compile(r"(?:^|[\s`])([A-Za-z0-9_\-./]+/[A-Za-z0-9_\-./]+|[A-Za-z0-9_\-./]+\.[A-Za-z0-9_]{1,8})(?:$|[\s`])")
_TICKET_RE = re.compile(r"\b[A-Z]{2,}-\d+\b")
_HASH_RE = re.compile(r"\b[0-9a-f]{7,40}\b")
_BACKTICK_RE = re.compile(r"`([^`]+)`")
_NUMBERED_RE = re.compile(r"\b\d+(?:\.\d+)?\b")
_STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "so", "to", "of", "for", "in", "on", "at", "by",
    "with", "from", "as", "that", "this", "these", "those", "it", "its", "is", "are",
    "was", "were", "be", "been", "being", "very", "really", "just", "quite", "actually",
    "basically", "literally", "then", "than", "also", "into", "about", "over", "under",
}
_FILLER_WORDS = {
    "really", "very", "quite", "basically", "literally", "simply", "just",
}


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _safe_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _as_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        v = value.strip().lower()
        if v in {"1", "true", "yes", "on"}:
            return True
        if v in {"0", "false", "no", "off"}:
            return False
    return default


class HybridContextEngine(ContextEngine):
    """Readable, safety-first context compression engine."""

    @property
    def name(self) -> str:
        return "hybrid"

    def __init__(self, settings: Optional[Dict[str, Any]] = None):
        cfg = self._resolve_settings(settings)

        self.threshold_percent = _clamp(
            _safe_float(cfg.get("threshold"), 0.50), 0.30, 0.95
        )
        self.protect_first_n = max(0, _safe_int(cfg.get("protect_first_n"), 3))
        self.protect_last_n = max(1, _safe_int(cfg.get("protect_last_n"), 8))
        self.target_ratio = _clamp(
            _safe_float(cfg.get("target_ratio"), 0.35), 0.10, 0.90
        )
        self.sentence_keep_ratio = _clamp(
            _safe_float(cfg.get("sentence_keep_ratio"), 0.55), 0.20, 1.0
        )
        self.token_pruning_enabled = bool(cfg.get("token_pruning_enabled", True))
        self.token_keep_ratio = _clamp(
            _safe_float(cfg.get("token_keep_ratio"), 0.85), 0.40, 1.0
        )
        self.similarity_floor = _clamp(
            _safe_float(cfg.get("similarity_floor"), 0.35), 0.05, 0.95
        )
        self.max_summary_chars = max(1200, _safe_int(cfg.get("max_summary_chars"), 12000))
        self.max_entities_check = max(5, _safe_int(cfg.get("max_entities_check"), 40))
        _cfg_force_override = _as_bool(cfg.get("force_override"), False)
        _env_force_override = _as_bool(os.getenv("AOT_FORCE_COMPRESSION_OVERRIDE"), False)
        self.force_override = _cfg_force_override or _env_force_override

        self.context_length = max(1, _safe_int(cfg.get("context_length"), 200000))
        self.threshold_tokens = int(self.context_length * self.threshold_percent)
        self.compression_count = 0
        self.last_prompt_tokens = 0
        self.last_completion_tokens = 0
        self.last_total_tokens = 0
        self.last_compression_ms = 0.0
        self.last_reduction_ratio = 0.0

    @staticmethod
    def _resolve_settings(overrides: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        base = {
            "threshold": 0.50,
            "protect_first_n": 3,
            "protect_last_n": 8,
            "target_ratio": 0.35,
            "sentence_keep_ratio": 0.55,
            "token_pruning_enabled": True,
            "token_keep_ratio": 0.85,
            "similarity_floor": 0.35,
            "max_summary_chars": 12000,
            "max_entities_check": 40,
            "force_override": False,
        }
        try:
            from aot_cli.config import load_config

            cfg = load_config() or {}
            context_cfg = cfg.get("context", {}) if isinstance(cfg, dict) else {}
            hybrid_cfg = context_cfg.get("hybrid", {}) if isinstance(context_cfg, dict) else {}
            if isinstance(hybrid_cfg, dict):
                base.update(hybrid_cfg)
        except Exception:
            pass
        if isinstance(overrides, dict):
            base.update(overrides)
        return base

    def update_from_response(self, usage: Dict[str, Any]) -> None:
        self.last_prompt_tokens = int(usage.get("prompt_tokens", 0) or 0)
        self.last_completion_tokens = int(usage.get("completion_tokens", 0) or 0)
        self.last_total_tokens = int(
            usage.get("total_tokens", self.last_prompt_tokens + self.last_completion_tokens) or 0
        )

    def should_compress(self, prompt_tokens: int = None) -> bool:
        if self.force_override:
            return True
        tokens = self.last_prompt_tokens if prompt_tokens is None else int(prompt_tokens)
        return tokens >= self.threshold_tokens

    def should_compress_preflight(self, messages: List[Dict[str, Any]]) -> bool:
        if self.force_override:
            return self.has_content_to_compress(messages)
        try:
            return estimate_messages_tokens_rough(messages or []) >= self.threshold_tokens
        except Exception:
            return False

    def has_content_to_compress(self, messages: List[Dict[str, Any]]) -> bool:
        if not messages:
            return False
        head = self._head_boundary(messages)
        tail = self._tail_start(messages, head)
        return tail > head

    def update_model(
        self,
        model: str,
        context_length: int,
        base_url: str = "",
        api_key: str = "",
        provider: str = "",
    ) -> None:
        self.context_length = max(1, int(context_length or self.context_length))
        self.threshold_tokens = int(self.context_length * self.threshold_percent)

    def get_status(self) -> Dict[str, Any]:
        base = super().get_status()
        base.update(
            {
                "engine": self.name,
                "last_compression_ms": round(self.last_compression_ms, 2),
                "last_reduction_ratio": round(self.last_reduction_ratio, 4),
            }
        )
        return base

    def compress(
        self,
        messages: List[Dict[str, Any]],
        current_tokens: int = None,
        focus_topic: str = None,
    ) -> List[Dict[str, Any]]:
        if not messages:
            return messages

        started = time.perf_counter()
        head_idx = self._head_boundary(messages)
        tail_idx = self._tail_start(messages, head_idx)
        if tail_idx <= head_idx:
            return messages

        head = [m.copy() for m in messages[:head_idx]]
        middle = messages[head_idx:tail_idx]
        tail = [m.copy() for m in messages[tail_idx:]]
        if not middle:
            return messages

        focus_terms = self._build_focus_terms(tail, focus_topic)
        compressed_lines: List[str] = []
        for msg in middle:
            snippet = self._compress_message(msg, focus_terms)
            if snippet:
                compressed_lines.append(snippet)

        if not compressed_lines:
            return messages

        target_summary_chars = int(self.threshold_tokens * self.target_ratio * 4)
        summary_char_budget = max(1200, min(self.max_summary_chars, target_summary_chars))
        snapshot = self._build_snapshot(compressed_lines, tail, focus_topic, summary_char_budget)
        if not snapshot.strip():
            return messages

        combined_middle_text = "\n".join(self._render_middle_line(m) for m in middle)
        if not self._passes_fidelity_gate(combined_middle_text, snapshot):
            return messages

        snapshot_msg = {"role": "assistant", "content": snapshot}
        compressed_messages = head + [snapshot_msg] + tail

        original_tokens = estimate_messages_tokens_rough(messages)
        compressed_tokens = estimate_messages_tokens_rough(compressed_messages)
        if original_tokens > 0:
            self.last_reduction_ratio = max(
                0.0, 1.0 - (compressed_tokens / float(original_tokens))
            )
        else:
            self.last_reduction_ratio = 0.0
        self.last_compression_ms = (time.perf_counter() - started) * 1000.0
        self.compression_count += 1
        return compressed_messages

    def _head_boundary(self, messages: Sequence[Dict[str, Any]]) -> int:
        non_system_seen = 0
        idx = 0
        while idx < len(messages):
            role = str(messages[idx].get("role", ""))
            if role != "system":
                if non_system_seen >= self.protect_first_n:
                    break
                non_system_seen += 1
            idx += 1
        return idx

    def _tail_start(self, messages: Sequence[Dict[str, Any]], head_idx: int) -> int:
        if not messages:
            return 0
        keep = min(self.protect_last_n, len(messages))
        return max(head_idx, len(messages) - keep)

    def _build_focus_terms(
        self, tail_messages: Sequence[Dict[str, Any]], focus_topic: Optional[str]
    ) -> set[str]:
        seed = []
        if focus_topic:
            seed.append(focus_topic)
        for msg in tail_messages[-4:]:
            text = self._message_text(msg)
            if text:
                seed.append(text[:800])
        tokens = self._tokenize(" ".join(seed))
        return {t for t in tokens if len(t) > 2 and t not in _STOPWORDS}

    def _compress_message(self, msg: Dict[str, Any], focus_terms: set[str]) -> str:
        role = str(msg.get("role", "unknown"))
        text = self._message_text(msg)
        if not text:
            return ""

        if role == "tool":
            return f"- [tool] {self._truncate_with_tail(text, 220)}"
        if msg.get("tool_calls"):
            fn_names = []
            for tc in msg.get("tool_calls") or []:
                if isinstance(tc, dict):
                    fn_names.append((tc.get("function") or {}).get("name", "?"))
            name_blob = ", ".join(n for n in fn_names if n)[:120]
            return f"- [assistant tool_calls={name_blob or '?'}] {self._truncate_with_tail(text, 220)}"

        sentence_pruned = self._sentence_prune(text, focus_terms)
        token_pruned = self._token_prune(sentence_pruned)
        return f"- [{role}] {token_pruned}"

    def _sentence_prune(self, text: str, focus_terms: set[str]) -> str:
        parts = [p.strip() for p in _SENTENCE_SPLIT_RE.split(text) if p.strip()]
        if len(parts) <= 2:
            return self._normalize_space(text)

        scored: List[Tuple[float, int, str]] = []
        for i, part in enumerate(parts):
            tokens = set(self._tokenize(part))
            overlap = len(tokens & focus_terms)
            score = overlap + (0.5 if self._contains_critical(part) else 0.0)
            scored.append((score, i, part))

        keep_n = max(2, int(len(parts) * self.sentence_keep_ratio))
        keep_n = min(keep_n, len(parts))
        # Always preserve first and last sentence for coherence.
        forced = {0, len(parts) - 1}
        ranked = sorted(scored, key=lambda x: (x[0], -x[1]), reverse=True)
        chosen = set(i for _, i, _ in ranked[:keep_n]) | forced
        ordered = [parts[i] for i in range(len(parts)) if i in chosen]
        return self._normalize_space(" ".join(ordered))

    def _token_prune(self, text: str) -> str:
        normalized = self._normalize_space(text)
        if not self.token_pruning_enabled or not normalized:
            return normalized
        words = normalized.split(" ")
        if len(words) < 14:
            return normalized

        keep_target = max(10, int(len(words) * self.token_keep_ratio))
        pruned = []
        for w in words:
            lw = w.lower().strip(".,;:!?")
            if lw in _FILLER_WORDS and len(pruned) > 2:
                continue
            pruned.append(w)
        if len(pruned) > keep_target:
            front = max(6, keep_target // 2)
            back = max(4, keep_target - front)
            pruned = pruned[:front] + pruned[-back:]
        return self._normalize_space(" ".join(pruned))

    def _passes_fidelity_gate(self, source: str, candidate: str) -> bool:
        if not source.strip() or not candidate.strip():
            return False
        entities = self._collect_entities(source)
        for ent in entities:
            if ent and ent not in candidate:
                return False
        sim = self._jaccard_similarity(source, candidate)
        return sim >= self.similarity_floor

    def _collect_entities(self, text: str) -> List[str]:
        entities: List[str] = []
        for regex in (_BACKTICK_RE, _PATH_RE, _TICKET_RE, _HASH_RE):
            for m in regex.findall(text):
                if isinstance(m, tuple):
                    token = m[0]
                else:
                    token = m
                token = str(token).strip()
                if token and token not in entities:
                    entities.append(token)
                    if len(entities) >= self.max_entities_check:
                        return entities
        for m in _NUMBERED_RE.findall(text):
            if len(entities) >= self.max_entities_check:
                break
            if m not in entities:
                entities.append(m)
        return entities

    def _build_snapshot(
        self,
        lines: Sequence[str],
        tail: Sequence[Dict[str, Any]],
        focus_topic: Optional[str],
        char_budget: int,
    ) -> str:
        active_task = self._infer_active_task(tail)
        header = (
            "[HYBRID CONTEXT SNAPSHOT]\n"
            "Reference only. Preserve this as background state; respond to newer turns after this snapshot.\n\n"
        )
        focus_line = f"Focus topic: {focus_topic}\n\n" if focus_topic else ""
        task_line = f"Active task: {active_task}\n\n"
        body = "\n".join(lines)
        snapshot = header + focus_line + task_line + body
        if len(snapshot) <= char_budget:
            return snapshot
        return self._truncate_with_tail(snapshot, char_budget)

    def _infer_active_task(self, tail: Sequence[Dict[str, Any]]) -> str:
        for msg in reversed(tail):
            if str(msg.get("role", "")) == "user":
                text = self._normalize_space(self._message_text(msg))
                if text:
                    return self._truncate_with_tail(text, 220)
        return "Continue from latest unresolved user request."

    @staticmethod
    def _tokenize(text: str) -> List[str]:
        return re.findall(r"[a-zA-Z0-9_./:-]+", text.lower())

    @staticmethod
    def _normalize_space(text: str) -> str:
        return _WHITESPACE_RE.sub(" ", text or "").strip()

    @staticmethod
    def _truncate_with_tail(text: str, max_chars: int) -> str:
        if len(text) <= max_chars:
            return text
        if max_chars < 40:
            return text[:max_chars]
        head = int(max_chars * 0.7)
        tail = max_chars - head - 13
        return text[:head].rstrip() + " ...[snip]... " + text[-tail:].lstrip()

    @staticmethod
    def _contains_critical(text: str) -> bool:
        if _BACKTICK_RE.search(text):
            return True
        if _PATH_RE.search(text):
            return True
        if _TICKET_RE.search(text):
            return True
        if _HASH_RE.search(text):
            return True
        return False

    @staticmethod
    def _jaccard_similarity(a: str, b: str) -> float:
        a_set = {t for t in re.findall(r"[a-zA-Z0-9_./:-]+", a.lower()) if t not in _STOPWORDS}
        b_set = {t for t in re.findall(r"[a-zA-Z0-9_./:-]+", b.lower()) if t not in _STOPWORDS}
        if not a_set or not b_set:
            return 0.0
        inter = len(a_set & b_set)
        union = len(a_set | b_set)
        return inter / float(union) if union else 0.0

    @staticmethod
    def _render_middle_line(msg: Dict[str, Any]) -> str:
        role = str(msg.get("role", "unknown"))
        content = msg.get("content", "")
        if isinstance(content, str):
            text = content
        else:
            text = json.dumps(content, ensure_ascii=False)
        return f"[{role}] {text}"

    @staticmethod
    def _message_text(msg: Dict[str, Any]) -> str:
        content = msg.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = []
            for p in content:
                if isinstance(p, str):
                    parts.append(p)
                elif isinstance(p, dict):
                    txt = p.get("text")
                    if isinstance(txt, str) and txt:
                        parts.append(txt)
                    elif p.get("type") in {"image", "image_url", "input_image"}:
                        parts.append("[image]")
            return "\n".join(parts)
        if isinstance(content, dict):
            if content.get("_multimodal") and isinstance(content.get("text_summary"), str):
                return content["text_summary"]
            return json.dumps(content, ensure_ascii=False)
        return str(content or "")

    @staticmethod
    def is_available() -> bool:
        return True


def register(ctx) -> None:
    """Register the hybrid context engine with plugin context."""
    ctx.register_context_engine(HybridContextEngine())
