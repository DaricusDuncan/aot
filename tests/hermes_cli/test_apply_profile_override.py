"""Regression tests for _apply_profile_override AOT_HOME guard (issue #22502).

When AOT_HOME is set to the aot root (e.g. systemd hardcodes
AOT_HOME=/root/.aot), _apply_profile_override must still read
active_profile and update AOT_HOME to the profile directory.

When AOT_HOME is already a profile directory (.../profiles/<name>),
_apply_profile_override must trust it and return without re-reading
active_profile (child-process inheritance contract).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest


def _run_apply_profile_override(
    tmp_path, monkeypatch, *, aot_home: str | None, active_profile: str | None,
    argv: list[str] | None = None,
):
    """Run _apply_profile_override in isolation.

    Returns the value of os.environ["AOT_HOME"] after the call,
    or None if unset.
    """
    aot_root = tmp_path / ".aot"
    aot_root.mkdir(parents=True, exist_ok=True)

    if active_profile is not None:
        (aot_root / "active_profile").write_text(active_profile)

    if active_profile and active_profile != "default":
        (aot_root / "profiles" / active_profile).mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    if aot_home is not None:
        monkeypatch.setenv("AOT_HOME", aot_home)
    else:
        monkeypatch.delenv("AOT_HOME", raising=False)

    monkeypatch.setattr(sys, "argv", argv or ["aot", "gateway", "start"])

    from aot_cli.main import _apply_profile_override
    _apply_profile_override()

    return os.environ.get("AOT_HOME")


class TestApplyProfileOverrideAotHomeGuard:
    """Regression guard for issue #22502.

    Verifies that AOT_HOME pointing to the aot root does NOT suppress
    the active_profile check, while AOT_HOME already pointing to a
    profile directory IS trusted as-is.
    """

    def test_aot_home_at_root_with_active_profile_is_redirected(
        self, tmp_path, monkeypatch
    ):
        """AOT_HOME=/root/.aot + active_profile=coder must redirect
        AOT_HOME to .../profiles/coder.

        Bug scenario from #22502: systemd sets AOT_HOME to the aot root
        and the user switches to a profile via `aot profile use`.
        Before the fix, the guard returned early and active_profile was ignored.
        """
        aot_root = tmp_path / ".aot"
        aot_root.mkdir(parents=True, exist_ok=True)

        result = _run_apply_profile_override(
            tmp_path,
            monkeypatch,
            aot_home=str(aot_root),
            active_profile="coder",
        )

        assert result is not None, "AOT_HOME must be set after profile redirect"
        assert "profiles" in result, (
            f"Expected AOT_HOME to point into profiles/ dir, got: {result!r}"
        )
        assert result.endswith("coder"), (
            f"Expected AOT_HOME to end with 'coder', got: {result!r}"
        )

    def test_aot_home_already_profile_dir_is_trusted(self, tmp_path, monkeypatch):
        """AOT_HOME=.../profiles/coder must not be overridden even when
        active_profile says something different.

        Preserves the child-process inheritance contract: a subprocess spawned
        with AOT_HOME already set to a specific profile must stay in that
        profile.
        """
        aot_root = tmp_path / ".aot"
        profile_dir = aot_root / "profiles" / "coder"
        profile_dir.mkdir(parents=True, exist_ok=True)

        (aot_root / "active_profile").write_text("other")

        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        monkeypatch.setenv("AOT_HOME", str(profile_dir))
        monkeypatch.setattr(sys, "argv", ["aot", "gateway", "start"])

        from aot_cli.main import _apply_profile_override
        _apply_profile_override()

        assert os.environ.get("AOT_HOME") == str(profile_dir), (
            "AOT_HOME must remain unchanged when already pointing to a profile dir"
        )

    def test_aot_home_unset_reads_active_profile(self, tmp_path, monkeypatch):
        """Classic case: AOT_HOME unset + active_profile=coder must set
        AOT_HOME to the profile directory (existing behaviour must not regress).
        """
        result = _run_apply_profile_override(
            tmp_path,
            monkeypatch,
            aot_home=None,
            active_profile="coder",
        )

        assert result is not None
        assert "coder" in result

    def test_aot_home_unset_default_profile_no_redirect(self, tmp_path, monkeypatch):
        """active_profile=default must not redirect AOT_HOME."""
        aot_root = tmp_path / ".aot"
        aot_root.mkdir(parents=True, exist_ok=True)

        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        monkeypatch.delenv("AOT_HOME", raising=False)
        monkeypatch.setattr(sys, "argv", ["aot", "gateway", "start"])
        (aot_root / "active_profile").write_text("default")

        from aot_cli.main import _apply_profile_override
        _apply_profile_override()

        assert os.environ.get("AOT_HOME") is None
