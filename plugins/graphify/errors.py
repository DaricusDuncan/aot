"""Shared error types for the Graphify plugin."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class GraphifyToolError(Exception):
    """Structured plugin error for predictable JSON tool responses."""

    code: str
    message: str
    details: str | None = None

    def __str__(self) -> str:
        if self.details:
            return f"{self.code}: {self.message} ({self.details})"
        return f"{self.code}: {self.message}"
