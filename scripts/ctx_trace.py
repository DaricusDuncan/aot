#!/usr/bin/env python3
"""Context-window trace report.

Reads ctx_trace_<session_id>.json files written by AOT when AOT_CTX_TRACE=1
and prints a human-readable table plus a token-pressure ASCII chart.

Usage:
    python scripts/ctx_trace.py                        # latest trace
    python scripts/ctx_trace.py <path-or-session-id>  # specific trace
    python scripts/ctx_trace.py --dir ~/.aot/sessions  # custom dir

Enable tracing in one of two ways:
    AOT_CTX_TRACE=1 aot                                # env var
    # or in config.yaml:
    context:
      trace: true
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def _find_latest(sessions_dir: Path) -> Path | None:
    candidates = sorted(sessions_dir.glob("ctx_trace_*.json"), key=lambda p: p.stat().st_mtime)
    return candidates[-1] if candidates else None


def _bar(pct: float | None, width: int = 28) -> str:
    if pct is None:
        return " " * width
    filled = min(width, round(pct / 100 * width))
    color = "\033[92m" if pct < 50 else "\033[93m" if pct < 85 else "\033[91m"
    reset = "\033[0m"
    return color + "█" * filled + "░" * (width - filled) + reset


def _fmt_k(n: int | None) -> str:
    if n is None:
        return "—"
    return f"{n/1000:.1f}k" if n >= 1000 else str(n)


def report(trace_path: Path) -> None:
    data: list[dict] = json.loads(trace_path.read_text(encoding="utf-8"))
    if not data:
        print("Trace file is empty.")
        return

    threshold = next((e["threshold"] for e in data if e.get("threshold")), 0)
    session_id = trace_path.stem.removeprefix("ctx_trace_")

    print(f"\n── Context-Window Trace: {session_id} ──")
    print(f"   {len(data)} API calls | threshold {_fmt_k(threshold)} tokens\n")

    # Pre-compute turns-since-last-compression for each entry.
    # A compression event is detected when the compressions counter increases.
    turns_since_compress: list[int | None] = []
    last_compress_call = None
    last_compress_count = 0
    for e in data:
        cc = e.get("compressions", 0)
        if cc > last_compress_count:
            last_compress_call = e["call"]
            last_compress_count = cc
        turns_since_compress.append(
            e["call"] - last_compress_call if last_compress_call is not None else None
        )

    # Header
    hdr = (
        f"{'Call':>4}  {'Msgs':>4}  {'Tokens':>7}  {'% Thresh':>8}  "
        f"{'Since▼':>6}  {'Evicted':>7}  {'Reclaimed':>9}  {'Compress':>9}  Pressure"
    )
    print(hdr)
    print("─" * len(hdr))

    total_evicted = 0
    total_reclaimed = 0
    compress_cycles: list[int] = []  # turns per compression cycle
    cycle_start_call = 1

    for i, e in enumerate(data):
        pct = e.get("pct")
        evicted = e.get("evicted", 0)
        reclaimed = e.get("tokens_reclaimed", 0)
        compressed = e.get("compressed", False)
        since = turns_since_compress[i]
        total_evicted += evicted
        total_reclaimed += reclaimed

        compress_marker = ""
        if compressed:
            before = e.get("msgs_before_compress", "?")
            after = e.get("msgs_after_compress", "?")
            compress_marker = f"▼{before}→{after}"
            cycle_turns = e["call"] - cycle_start_call
            compress_cycles.append(cycle_turns)
            cycle_start_call = e["call"]

        since_str = f"+{since}" if since is not None else "—"

        row = (
            f"{e['call']:>4}  "
            f"{e['msgs']:>4}  "
            f"{_fmt_k(e['tokens']):>7}  "
            f"{(str(pct)+'%') if pct is not None else '—':>8}  "
            f"{since_str:>6}  "
            f"{evicted if evicted else '·':>7}  "
            f"{_fmt_k(reclaimed) if reclaimed else '·':>9}  "
            f"{compress_marker:>9}  "
            f"{_bar(pct)}"
        )
        print(row)

    print()

    # Summary
    final = data[-1]
    compressions = final.get("compressions", 0)
    peak_pct = max((e.get("pct") or 0) for e in data)
    peak_tok = max(e.get("tokens", 0) for e in data)

    print("── Summary ──────────────────────────────")
    print(f"   Total API calls    : {len(data)}")
    print(f"   Total compressions : {compressions}")
    if compress_cycles:
        avg_runway = sum(compress_cycles) / len(compress_cycles)
        print(f"   Avg runway/cycle   : {avg_runway:.0f} calls between compressions")
        print(f"   Runway per cycle   : {' → '.join(str(c) for c in compress_cycles)} calls")
    print(f"   Total evictions    : {total_evicted} outputs, ~{_fmt_k(total_reclaimed)} tokens reclaimed")
    print(f"   Peak token usage   : {_fmt_k(peak_tok)} ({peak_pct:.0f}% of threshold)")
    if compressions == 0 and peak_pct >= 85:
        print("   ⚠️  Threshold nearly hit but no compression fired — check compression_enabled.")
    if compressions >= 2:
        print(f"   ⚠️  {compressions} compressions — summary fidelity may be degraded.")
    print()


def main() -> None:
    arg = sys.argv[1] if len(sys.argv) > 1 else None
    sessions_dir = Path(os.path.expanduser("~/.aot/sessions"))

    if "--dir" in sys.argv:
        idx = sys.argv.index("--dir")
        sessions_dir = Path(sys.argv[idx + 1]).expanduser()
        arg = sys.argv[idx + 2] if len(sys.argv) > idx + 2 else None

    if arg and arg != "--dir":
        p = Path(arg)
        if not p.exists():
            # Try as session ID
            p = sessions_dir / f"ctx_trace_{arg}.json"
        if not p.exists():
            print(f"Error: trace not found: {arg}")
            sys.exit(1)
        report(p)
    else:
        p = _find_latest(sessions_dir)
        if p is None:
            print("No ctx_trace_*.json files found in", sessions_dir)
            print("Run AOT with AOT_CTX_TRACE=1 to enable tracing.")
            sys.exit(1)
        report(p)


if __name__ == "__main__":
    main()
