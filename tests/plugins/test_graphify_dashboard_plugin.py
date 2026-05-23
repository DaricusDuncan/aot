"""Tests for Graphify dashboard plugin API."""

from __future__ import annotations

import json

from fastapi import FastAPI
from fastapi.testclient import TestClient


def _client() -> TestClient:
    from plugins.graphify.dashboard.plugin_api import router

    app = FastAPI()
    app.include_router(router, prefix="/api/plugins/graphify")
    return TestClient(app)


def test_graph_endpoint_normalizes_nodes_and_edges(tmp_path):
    repo = tmp_path / "repo"
    graph_dir = repo / "graphify-out"
    graph_dir.mkdir(parents=True)
    graph_path = graph_dir / "graph.json"
    graph_path.write_text(
        json.dumps(
            {
                "nodes": [
                    {"id": "A", "label": "AuthService"},
                    {"id": "B", "label": "DatabaseClient"},
                ],
                "edges": [
                    {"source": "A", "target": "B", "type": "calls"},
                ],
            }
        ),
        encoding="utf-8",
    )

    client = _client()
    response = client.get("/api/plugins/graphify/graph", params={"root_path": str(repo)})
    assert response.status_code == 200
    payload = response.json()
    assert payload["node_count"] == 2
    assert payload["edge_count"] == 1
    assert payload["graph"]["nodes"][0]["id"] in {"A", "B"}
    assert payload["graph"]["edges"][0]["source"] == "A"
    assert payload["graph"]["edges"][0]["target"] == "B"


def test_graph_endpoint_returns_404_when_graph_missing(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    client = _client()
    response = client.get("/api/plugins/graphify/graph", params={"root_path": str(repo)})
    assert response.status_code == 404
    assert "Run graphify extract first" in response.json()["detail"]


def test_context_trace_list_and_latest_use_aot_home(tmp_path, monkeypatch):
    aot_home = tmp_path / ".aot"
    sessions = aot_home / "sessions"
    sessions.mkdir(parents=True)
    monkeypatch.setenv("AOT_HOME", str(aot_home))

    first = sessions / "ctx_trace_alpha.json"
    second = sessions / "ctx_trace_beta.json"
    first.write_text(
        json.dumps([{"call": 1, "pct": 30.0, "tokens": 1000, "threshold": 5000, "compressions": 0}]),
        encoding="utf-8",
    )
    second.write_text(
        json.dumps(
            [
                {
                    "call": 1,
                    "pct": 70.0,
                    "tokens": 3500,
                    "threshold": 5000,
                    "compressions": 1,
                    "compression_attempted": True,
                    "compressed": True,
                }
            ]
        ),
        encoding="utf-8",
    )

    client = _client()

    list_resp = client.get("/api/plugins/graphify/context-trace/list")
    assert list_resp.status_code == 200
    traces = list_resp.json()["traces"]
    assert {trace["session_id"] for trace in traces} == {"alpha", "beta"}

    latest_resp = client.get("/api/plugins/graphify/context-trace/latest", params={"session_id": "beta"})
    assert latest_resp.status_code == 200
    latest = latest_resp.json()
    assert latest["session_id"] == "beta"
    assert latest["summary"]["total_calls"] == 1
    assert latest["summary"]["successful_compressions"] == 1
    assert latest["summary"]["compression_attempts"] == 1
