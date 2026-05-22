"""Input validation helpers for Graphify tool handlers."""

from __future__ import annotations

from pathlib import Path

from plugins.graphify.errors import GraphifyToolError


def normalize_workdir(raw_path: str | None) -> Path:
    """Resolve and validate the Graphify working directory."""
    candidate = Path(raw_path).expanduser() if raw_path else Path.cwd()
    resolved = candidate.resolve()
    if not resolved.exists():
        raise GraphifyToolError(
            code="invalid_workdir",
            message="Working directory does not exist.",
            details=str(resolved),
        )
    if not resolved.is_dir():
        raise GraphifyToolError(
            code="invalid_workdir",
            message="Working directory must be a directory path.",
            details=str(resolved),
        )
    return resolved


def require_non_empty(value: str | None, field_name: str) -> str:
    """Ensure a required string field is present and non-empty."""
    cleaned = (value or "").strip()
    if not cleaned:
        raise GraphifyToolError(
            code="invalid_argument",
            message=f"Missing required field: {field_name}.",
        )
    return cleaned


def require_positive_int(value: int | None, field_name: str) -> int | None:
    """Validate optional positive integer fields."""
    if value is None:
        return None
    if value <= 0:
        raise GraphifyToolError(
            code="invalid_argument",
            message=f"{field_name} must be greater than 0.",
            details=str(value),
        )
    return value
