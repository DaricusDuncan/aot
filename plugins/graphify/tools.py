"""Tool handlers for Graphify plugin commands."""

from __future__ import annotations

import json
from typing import Any

from plugins.graphify.errors import GraphifyToolError
from plugins.graphify.runner import run_graphify_command
from plugins.graphify.validation import (
    normalize_workdir,
    require_non_empty,
    require_positive_int,
)


def _ok(result: dict) -> str:
    return json.dumps({"success": result.get("success", False), "result": result})


def _err(exc: Exception) -> str:
    if isinstance(exc, GraphifyToolError):
        payload = {
            "success": False,
            "error": {
                "code": exc.code,
                "message": exc.message,
                "details": exc.details,
            },
        }
    else:
        payload = {
            "success": False,
            "error": {
                "code": "graphify_tool_error",
                "message": str(exc),
            },
        }
    return json.dumps(payload)


def handle_graphify_build(args: dict[str, Any], **kwargs: Any) -> str:
    """Run graphify extract/update/cluster-only against a project directory."""
    del kwargs
    try:
        cwd = normalize_workdir(args.get("root_path"))
        mode = (args.get("mode") or "extract").strip().lower()
        if mode not in {"extract", "update", "cluster_only"}:
            raise GraphifyToolError(
                code="invalid_argument",
                message="mode must be one of: extract, update, cluster_only.",
                details=mode,
            )

        if mode == "extract":
            cmd = ["extract", str(cwd)]
        elif mode == "update":
            cmd = ["update", str(cwd)]
        else:
            cmd = ["cluster-only", str(cwd)]

        if bool(args.get("no_viz")):
            cmd.append("--no-viz")
        backend = (args.get("backend") or "").strip()
        if backend:
            cmd.extend(["--backend", backend])
        model = (args.get("model") or "").strip()
        if model:
            cmd.extend(["--model", model])
        token_budget = require_positive_int(args.get("token_budget"), "token_budget")
        if token_budget is not None:
            cmd.extend(["--token-budget", str(token_budget)])
        max_concurrency = require_positive_int(
            args.get("max_concurrency"), "max_concurrency"
        )
        if max_concurrency is not None:
            cmd.extend(["--max-concurrency", str(max_concurrency)])

        return _ok(run_graphify_command(cmd, cwd=cwd))
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


def handle_graphify_query(args: dict[str, Any], **kwargs: Any) -> str:
    """Query the graph with natural language."""
    del kwargs
    try:
        cwd = normalize_workdir(args.get("root_path"))
        question = require_non_empty(args.get("question"), "question")
        cmd = ["query", question]
        graph_path = (args.get("graph_path") or "").strip()
        if graph_path:
            cmd.extend(["--graph", graph_path])
        if bool(args.get("dfs")):
            cmd.append("--dfs")
        budget = require_positive_int(args.get("budget"), "budget")
        if budget is not None:
            cmd.extend(["--budget", str(budget)])
        return _ok(run_graphify_command(cmd, cwd=cwd))
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


def handle_graphify_path(args: dict[str, Any], **kwargs: Any) -> str:
    """Find a shortest path between two graph entities."""
    del kwargs
    try:
        cwd = normalize_workdir(args.get("root_path"))
        source = require_non_empty(args.get("source"), "source")
        target = require_non_empty(args.get("target"), "target")
        cmd = ["path", source, target]
        graph_path = (args.get("graph_path") or "").strip()
        if graph_path:
            cmd.extend(["--graph", graph_path])
        return _ok(run_graphify_command(cmd, cwd=cwd))
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


def handle_graphify_explain(args: dict[str, Any], **kwargs: Any) -> str:
    """Explain an entity using graph context."""
    del kwargs
    try:
        cwd = normalize_workdir(args.get("root_path"))
        entity = require_non_empty(args.get("entity"), "entity")
        cmd = ["explain", entity]
        graph_path = (args.get("graph_path") or "").strip()
        if graph_path:
            cmd.extend(["--graph", graph_path])
        return _ok(run_graphify_command(cmd, cwd=cwd))
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


def handle_graphify_prs(args: dict[str, Any], **kwargs: Any) -> str:
    """Inspect Graphify PR analytics."""
    del kwargs
    try:
        cwd = normalize_workdir(args.get("root_path"))
        cmd = ["prs"]
        pr_number = args.get("pr_number")
        if pr_number is not None:
            if not isinstance(pr_number, int) or pr_number <= 0:
                raise GraphifyToolError(
                    code="invalid_argument",
                    message="pr_number must be a positive integer.",
                    details=str(pr_number),
                )
            cmd.append(str(pr_number))
        if bool(args.get("triage")):
            cmd.append("--triage")
        if bool(args.get("conflicts")):
            cmd.append("--conflicts")
        base_branch = (args.get("base_branch") or "").strip()
        if base_branch:
            cmd.extend(["--base", base_branch])
        repo = (args.get("repo") or "").strip()
        if repo:
            cmd.extend(["--repo", repo])
        return _ok(run_graphify_command(cmd, cwd=cwd))
    except Exception as exc:  # noqa: BLE001
        return _err(exc)
