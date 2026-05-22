#!/usr/bin/env python3
"""Benchmark harness for the hybrid context engine.

Loads a conversation transcript, runs hybrid compression, and reports:
- token reduction
- latency
- message-count change
- basic entity-retention check

Accepted input formats:
1) JSON list of OpenAI-style messages
2) JSON object with a top-level "messages" list
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
from pathlib import Path
from typing import Any, Dict, List

from agent.model_metadata import estimate_messages_tokens_rough
from plugins.context_engine.hybrid import HybridContextEngine


def _load_messages(path: Path) -> List[Dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        messages = data
    elif isinstance(data, dict) and isinstance(data.get("messages"), list):
        messages = data["messages"]
    else:
        raise ValueError("Input must be a JSON list or an object with 'messages'.")
    normalized = []
    for m in messages:
        if not isinstance(m, dict):
            continue
        if "role" not in m:
            continue
        normalized.append(m)
    if not normalized:
        raise ValueError("No valid messages found in input.")
    return normalized


def _fmt_ms(v: float) -> str:
    return f"{v:.2f}ms"


def run_once(messages: List[Dict[str, Any]], engine: HybridContextEngine, focus_topic: str = "") -> Dict[str, Any]:
    start = time.perf_counter()
    compressed = engine.compress(messages, focus_topic=(focus_topic or None))
    elapsed_ms = (time.perf_counter() - start) * 1000.0

    before_tokens = estimate_messages_tokens_rough(messages)
    after_tokens = estimate_messages_tokens_rough(compressed)
    reduction = (1.0 - (after_tokens / before_tokens)) if before_tokens else 0.0

    middle_text = "\n".join(engine._render_middle_line(m) for m in messages)
    compressed_text = "\n".join(engine._render_middle_line(m) for m in compressed)
    required_entities = engine._collect_entities(middle_text)
    missing_entities = [e for e in required_entities if e not in compressed_text]

    return {
        "before_messages": len(messages),
        "after_messages": len(compressed),
        "before_tokens": before_tokens,
        "after_tokens": after_tokens,
        "reduction_ratio": reduction,
        "elapsed_ms": elapsed_ms,
        "required_entities": len(required_entities),
        "missing_entities": len(missing_entities),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark hybrid context compression.")
    parser.add_argument("input", help="Path to transcript JSON.")
    parser.add_argument("--runs", type=int, default=5, help="Number of benchmark runs.")
    parser.add_argument("--focus", default="", help="Optional focus topic.")
    args = parser.parse_args()

    transcript_path = Path(args.input).expanduser().resolve()
    messages = _load_messages(transcript_path)
    engine = HybridContextEngine()

    runs = max(1, args.runs)
    results = [run_once(messages, engine, focus_topic=args.focus) for _ in range(runs)]

    latencies = [r["elapsed_ms"] for r in results]
    reductions = [r["reduction_ratio"] for r in results]

    baseline = results[0]
    print(f"input={transcript_path}")
    print(f"messages: {baseline['before_messages']} -> {baseline['after_messages']}")
    print(f"tokens:   {baseline['before_tokens']} -> {baseline['after_tokens']}")
    print(f"reduction: {baseline['reduction_ratio'] * 100:.2f}%")
    print(
        "latency: "
        f"mean={_fmt_ms(statistics.mean(latencies))} "
        f"p95={_fmt_ms(sorted(latencies)[max(0, int(0.95 * len(latencies)) - 1)])} "
        f"min={_fmt_ms(min(latencies))} "
        f"max={_fmt_ms(max(latencies))}"
    )
    print(
        f"entity-retention: required={baseline['required_entities']} "
        f"missing={baseline['missing_entities']}"
    )
    if len(results) > 1:
        print(
            f"reduction-variance: min={min(reductions) * 100:.2f}% "
            f"max={max(reductions) * 100:.2f}%"
        )


if __name__ == "__main__":
    main()
