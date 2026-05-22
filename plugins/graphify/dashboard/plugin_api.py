"""Graphify dashboard plugin API routes.

Mounted at /api/plugins/graphify/.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query

from aot_constants import get_aot_home

router = APIRouter()


def _session_id_from_trace_path(path: Path) -> str:
    name = path.stem
    if name.startswith("ctx_trace_"):
        return name[len("ctx_trace_") :]
    return name


def _trace_files() -> list[Path]:
    sessions_dir = get_aot_home() / "sessions"
    files = sorted(
        sessions_dir.glob("ctx_trace_*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return files


def _trace_file_for_session(session_id: str) -> Path:
    path = get_aot_home() / "sessions" / f"ctx_trace_{session_id}.json"
    if not path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"No context trace found for session '{session_id}'.",
        )
    return path


def _coerce_node_id(value: Any) -> str:
    if isinstance(value, dict):
        for key in ("id", "name", "label", "node", "key"):
            if key in value and value[key] not in (None, ""):
                return str(value[key])
        return ""
    if value in (None, ""):
        return ""
    return str(value)


def _normalize_graph(raw: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    raw_nodes = raw.get("nodes") or raw.get("vertices") or []
    raw_edges = raw.get("edges") or raw.get("links") or raw.get("relationships") or []

    nodes_by_id: dict[str, dict[str, Any]] = {}
    for idx, item in enumerate(raw_nodes):
        if not isinstance(item, dict):
            item = {"label": str(item)}
        node_id = _coerce_node_id(item.get("id")) or _coerce_node_id(item.get("name")) or _coerce_node_id(item.get("label"))
        if not node_id:
            node_id = f"node_{idx}"
        label = str(item.get("label") or item.get("name") or node_id)
        node = {
            "id": node_id,
            "label": label,
            "type": item.get("type") or item.get("kind") or item.get("group") or "node",
            "raw": item,
        }
        nodes_by_id[node_id] = node

    normalized_edges: list[dict[str, Any]] = []
    for idx, item in enumerate(raw_edges):
        if not isinstance(item, dict):
            continue
        source = (
            _coerce_node_id(item.get("source"))
            or _coerce_node_id(item.get("from"))
            or _coerce_node_id(item.get("src"))
            or _coerce_node_id(item.get("u"))
            or _coerce_node_id(item.get("left"))
        )
        target = (
            _coerce_node_id(item.get("target"))
            or _coerce_node_id(item.get("to"))
            or _coerce_node_id(item.get("dst"))
            or _coerce_node_id(item.get("v"))
            or _coerce_node_id(item.get("right"))
        )
        if not source or not target:
            continue
        if source not in nodes_by_id:
            nodes_by_id[source] = {
                "id": source,
                "label": source,
                "type": "inferred",
                "raw": {},
            }
        if target not in nodes_by_id:
            nodes_by_id[target] = {
                "id": target,
                "label": target,
                "type": "inferred",
                "raw": {},
            }
        normalized_edges.append(
            {
                "id": str(item.get("id") or f"edge_{idx}"),
                "source": source,
                "target": target,
                "label": str(item.get("label") or item.get("type") or item.get("relation") or ""),
                "weight": item.get("weight"),
                "raw": item,
            }
        )

    degree: dict[str, int] = {node_id: 0 for node_id in nodes_by_id}
    for edge in normalized_edges:
        degree[edge["source"]] = degree.get(edge["source"], 0) + 1
        degree[edge["target"]] = degree.get(edge["target"], 0) + 1

    normalized_nodes = []
    for node in nodes_by_id.values():
        normalized_nodes.append(
            {
                **node,
                "degree": degree.get(node["id"], 0),
            }
        )

    normalized_nodes.sort(key=lambda n: (str(n["label"]).lower(), n["id"]))
    return {"nodes": normalized_nodes, "edges": normalized_edges}


def _graph_path(root_path: Optional[str], graph_path: Optional[str]) -> Path:
    if graph_path:
        path = Path(graph_path).expanduser().resolve()
    else:
        root = Path(root_path).expanduser().resolve() if root_path else Path.cwd().resolve()
        path = root / "graphify-out" / "graph.json"
    if not path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Graph file not found at '{path}'. Run graphify extract first.",
        )
    if not path.is_file():
        raise HTTPException(status_code=400, detail=f"Graph path '{path}' is not a file.")
    return path


def _load_trace(path: Path) -> list[dict[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Trace file '{path.name}' is not valid JSON: {exc}",
        ) from exc
    if not isinstance(payload, list):
        raise HTTPException(
            status_code=500,
            detail=f"Trace file '{path.name}' must contain a JSON array.",
        )
    entries: list[dict[str, Any]] = []
    for item in payload:
        if isinstance(item, dict):
            entries.append(item)
    return entries


def _trace_summary(entries: list[dict[str, Any]]) -> dict[str, Any]:
    if not entries:
        return {
            "total_calls": 0,
            "peak_pct": 0.0,
            "successful_compressions": 0,
            "compression_attempts": 0,
            "latest_tokens": 0,
            "latest_threshold": 0,
        }
    latest = entries[-1]
    peak_pct = max(float(entry.get("pct") or 0.0) for entry in entries)
    successful = sum(1 for entry in entries if entry.get("compressed") is True)
    attempted = sum(
        1
        for entry in entries
        if entry.get("compression_attempted") is True
        or "msgs_before_compress" in entry
    )
    return {
        "total_calls": len(entries),
        "peak_pct": peak_pct,
        "successful_compressions": successful,
        "compression_attempts": attempted,
        "latest_tokens": int(latest.get("tokens") or 0),
        "latest_threshold": int(latest.get("threshold") or 0),
        "latest_compression_count": int(latest.get("compressions") or 0),
    }


@router.get("/graph")
def get_graph(
    root_path: Optional[str] = Query(None, description="Project root path containing graphify-out/graph.json"),
    graph_path: Optional[str] = Query(None, description="Explicit graph JSON file path"),
):
    path = _graph_path(root_path, graph_path)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Graph file '{path}' is not valid JSON: {exc}",
        ) from exc
    if not isinstance(raw, dict):
        raise HTTPException(
            status_code=500,
            detail=f"Graph file '{path}' must contain a JSON object.",
        )
    graph = _normalize_graph(raw)
    return {
        "source_path": str(path),
        "node_count": len(graph["nodes"]),
        "edge_count": len(graph["edges"]),
        "graph": graph,
    }


@router.get("/context-trace/list")
def list_context_traces():
    traces = _trace_files()
    return {
        "traces": [
            {
                "session_id": _session_id_from_trace_path(path),
                "path": str(path),
                "modified_at": path.stat().st_mtime,
                "size_bytes": path.stat().st_size,
            }
            for path in traces
        ]
    }


@router.get("/context-trace/latest")
def get_context_trace_latest(
    session_id: Optional[str] = Query(None, description="Optional session id to load"),
):
    if session_id:
        path = _trace_file_for_session(session_id)
    else:
        traces = _trace_files()
        if not traces:
            raise HTTPException(
                status_code=404,
                detail="No context trace files found. Enable tracing and run a session first.",
            )
        path = traces[0]
    entries = _load_trace(path)
    return {
        "session_id": _session_id_from_trace_path(path),
        "path": str(path),
        "summary": _trace_summary(entries),
        "entries": entries,
    }
