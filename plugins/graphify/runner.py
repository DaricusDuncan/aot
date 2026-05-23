"""Graphify command runner for plugin handlers."""

from __future__ import annotations
import contextlib
import io
import os
import signal
import sys
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


class _CommandTimeout(Exception):
    """Internal timeout signal for in-process Graphify execution."""


@contextlib.contextmanager
def _chdir(path: Path):
    prev = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(prev)


@contextlib.contextmanager
def _argv(args: list[str]):
    prev = sys.argv[:]
    sys.argv = args
    try:
        yield
    finally:
        sys.argv = prev


@contextlib.contextmanager
def _timeout(seconds: int):
    if seconds <= 0 or os.name == "nt":
        yield
        return
    try:
        previous_handler = signal.getsignal(signal.SIGALRM)
    except ValueError:
        yield
        return

    def _raise_timeout(signum, frame):  # noqa: ARG001
        raise _CommandTimeout()

    try:
        signal.signal(signal.SIGALRM, _raise_timeout)
        signal.alarm(seconds)
    except ValueError:
        yield
        return
    try:
        yield
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous_handler)


def _ensure_vendored_graphify_on_path() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    vendored = repo_root / "vendor" / "graphify"
    if not vendored.exists():
        raise GraphifyToolError(
            code="graphify_not_available",
            message="Vendored graphify package is missing.",
            details=str(vendored),
        )
    vendored_str = str(vendored)
    if vendored_str not in sys.path:
        sys.path.insert(0, vendored_str)


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
    _ensure_vendored_graphify_on_path()
    try:
        from graphify.__main__ import main as graphify_main
    except Exception as exc:  # noqa: BLE001
        raise GraphifyToolError(
            code="graphify_not_available",
            message="Could not import vendored graphify module.",
            details=str(exc),
        ) from exc

    started = time.perf_counter()
    command = ["graphify", *args]
    stdout_buffer = io.StringIO()
    stderr_buffer = io.StringIO()
    exit_code = 0
    try:
        with (
            _chdir(cwd),
            _argv(command),
            _timeout(timeout_seconds),
            contextlib.redirect_stdout(stdout_buffer),
            contextlib.redirect_stderr(stderr_buffer),
        ):
            try:
                graphify_main()
            except SystemExit as exc:
                raw_code = exc.code
                if raw_code is None:
                    exit_code = 0
                elif isinstance(raw_code, int):
                    exit_code = raw_code
                else:
                    exit_code = 1
                    if raw_code:
                        print(raw_code, file=sys.stderr)
    except _CommandTimeout as exc:
        raise GraphifyToolError(
            code="command_timeout",
            message="Graphify command timed out.",
            details=f"timeout={timeout_seconds}s",
        ) from exc

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    return {
        "success": exit_code == 0,
        "exit_code": exit_code,
        "stdout": stdout_buffer.getvalue().strip(),
        "stderr": stderr_buffer.getvalue().strip(),
        "command": command,
        "cwd": str(cwd),
        "elapsed_ms": elapsed_ms,
    }
