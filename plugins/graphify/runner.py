"""Graphify command runner for plugin handlers."""

from __future__ import annotations

import subprocess
import time
from pathlib import Path

from plugins.graphify.errors import GraphifyToolError

DEFAULT_TIMEOUT_SECONDS = 180
ALLOWED_COMMANDS = {
    "extract",
    "update",
    "cluster-only",
    "query",
    "path",
    "explain",
    "prs",
}


def run_graphify_command(
    args: list[str],
    *,
    cwd: Path,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
) -> dict:
    """Execute a Graphify command and return a normalized result envelope."""
    if not args:
        raise GraphifyToolError(
            code="invalid_command",
            message="No graphify command arguments were provided.",
        )
    if args[0] not in ALLOWED_COMMANDS:
        raise GraphifyToolError(
            code="invalid_command",
            message=f"Unsupported graphify command: {args[0]}",
        )

    started = time.perf_counter()
    command = ["graphify", *args]
    try:
        proc = subprocess.run(
            command,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
            check=False,
        )
    except FileNotFoundError as exc:
        raise GraphifyToolError(
            code="graphify_not_installed",
            message="The graphify CLI is not available on PATH.",
            details=str(exc),
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise GraphifyToolError(
            code="command_timeout",
            message="Graphify command timed out.",
            details=f"timeout={timeout_seconds}s",
        ) from exc

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    return {
        "success": proc.returncode == 0,
        "exit_code": proc.returncode,
        "stdout": (proc.stdout or "").strip(),
        "stderr": (proc.stderr or "").strip(),
        "command": command,
        "cwd": str(cwd),
        "elapsed_ms": elapsed_ms,
    }
