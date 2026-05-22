"""Opt-in e2e smoke test for the bundled Graphify plugin.

This test executes the real Graphify CLI through the plugin handler and verifies
that graph generation succeeds on a tiny fixture repository.

Run manually:
    GRAPHIFY_E2E=1 scripts/run_tests.sh tests/plugins/test_graphify_plugin_e2e.py -q
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import pytest

from plugins.graphify.tools import handle_graphify_build


LIVE = os.environ.get("GRAPHIFY_E2E") == "1"
HAS_GRAPHIFY = shutil.which("graphify") is not None
GRAPHIFY_BACKEND = os.environ.get("GRAPHIFY_E2E_BACKEND", "").strip()
GRAPHIFY_MODEL = os.environ.get("GRAPHIFY_E2E_MODEL", "").strip()

pytestmark = [
    pytest.mark.skipif(not LIVE, reason="live-only — set GRAPHIFY_E2E=1"),
    pytest.mark.skipif(not HAS_GRAPHIFY, reason="graphify CLI not installed on PATH"),
]


def _make_fixture_repo(repo: Path) -> None:
    (repo / "app").mkdir(parents=True, exist_ok=True)
    (repo / "app" / "service.py").write_text(
        "class UserService:\n"
        "    def get_user(self, user_id: int) -> dict:\n"
        "        return {\"id\": user_id, \"name\": \"demo\"}\n",
        encoding="utf-8",
    )
    (repo / "app" / "db.py").write_text(
        "class DatabaseClient:\n"
        "    def fetch(self, key: str) -> dict:\n"
        "        return {\"key\": key}\n",
        encoding="utf-8",
    )


def test_graphify_build_extract_generates_graph(tmp_path):
    repo = tmp_path / "graphify-e2e-fixture"
    repo.mkdir()
    _make_fixture_repo(repo)

    args = {
        "root_path": str(repo),
        "mode": "extract",
        "no_viz": True,
        "max_concurrency": 1,
    }
    if GRAPHIFY_BACKEND:
        args["backend"] = GRAPHIFY_BACKEND
    if GRAPHIFY_MODEL:
        args["model"] = GRAPHIFY_MODEL

    raw = handle_graphify_build(args)
    payload = json.loads(raw)

    assert payload["success"] is True, payload
    graph_path = repo / "graphify-out" / "graph.json"
    assert graph_path.exists(), (
        f"Expected generated graph at {graph_path}, got payload: {payload}"
    )
