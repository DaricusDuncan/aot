"""Resolve AOT_HOME for standalone skill scripts.

Skill scripts may run outside the Aot process (e.g. system Python,
nix env, CI) where ``aot_constants`` is not importable.  This module
provides the same ``get_aot_home()`` and ``display_aot_home()``
contracts as ``aot_constants`` without requiring it on ``sys.path``.

When ``aot_constants`` IS available it is used directly so that any
future enhancements (profile resolution, Docker detection, etc.) are
picked up automatically.  The fallback path replicates the core logic
from ``aot_constants.py`` using only the stdlib.

All scripts under ``google-workspace/scripts/`` should import from here
instead of duplicating the ``AOT_HOME = Path(os.getenv(...))`` pattern.
"""

from __future__ import annotations

import os
from pathlib import Path

try:
    from aot_constants import display_aot_home as display_aot_home
    from aot_constants import get_aot_home as get_aot_home
except (ModuleNotFoundError, ImportError):

    def get_aot_home() -> Path:
        """Return the Aot home directory (default: ~/.aot).

        Mirrors ``aot_constants.get_aot_home()``."""
        val = os.environ.get("AOT_HOME", "").strip()
        return Path(val) if val else Path.home() / ".aot"

    def display_aot_home() -> str:
        """Return a user-friendly ``~/``-shortened display string.

        Mirrors ``aot_constants.display_aot_home()``."""
        home = get_aot_home()
        try:
            return "~/" + str(home.relative_to(Path.home()))
        except ValueError:
            return str(home)
