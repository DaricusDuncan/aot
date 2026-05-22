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
    """Return successful tool output as JSON, parsing JSON stdout when possible."""
    stdout = result.get("stdout", "")
    parsed_stdout = None
    if isinstance(stdout, str) and stdout:
        try:
            parsed_stdout = json.loads(stdout)
        except json.JSONDecodeError:
            parsed_stdout = None

    payload = {
        "success": result.get("success", False),
        "result": result,
    }
    if parsed_stdout is not None:
        payload["parsed_stdout"] = parsed_stdout
    return json.dumps(payload)


def _err(exc: Exception) -> str:
    """Return normalized error output as JSON."""
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


def _forbid_fields(args: dict[str, Any], field_names: tuple[str, ...], *, mode: str) -> None:
    """Reject fields that are invalid for a given Graphify build mode."""
    invalid: list[str] = []
    for field in field_names:
        value = args.get(field)
        if value not in (None, "", False):
            invalid.append(field)
    if invalid:
        raise GraphifyToolError(
            code="invalid_argument",
            message=f"Field(s) {', '.join(invalid)} are not supported for mode '{mode}'.",
        )


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

        backend = (args.get("backend") or "").strip()
        model = (args.get("model") or "").strip()
        token_budget = require_positive_int(args.get("token_budget"), "token_budget")
        max_concurrency = require_positive_int(
            args.get("max_concurrency"), "max_concurrency"
        )
        no_viz = bool(args.get("no_viz"))

        if mode == "extract":
            cmd = ["extract", str(cwd)]
            if backend:
                cmd.extend(["--backend", backend])
            if model:
                cmd.extend(["--model", model])
            if token_budget is not None:
                cmd.extend(["--token-budget", str(token_budget)])
            if max_concurrency is not None:
                cmd.extend(["--max-concurrency", str(max_concurrency)])
            if no_viz:
                # extract does not expose --no-viz; --no-cluster is the closest
                # lower-overhead mode.
                cmd.append("--no-cluster")
        elif mode == "update":
            _forbid_fields(
                args,
                ("backend", "model", "token_budget", "max_concurrency"),
                mode=mode,
            )
            cmd = ["update", str(cwd)]
            if no_viz:
                # update supports --no-cluster to skip reclustering work.
                cmd.append("--no-cluster")
        else:
            _forbid_fields(
                args,
                ("backend", "model", "token_budget", "max_concurrency", "no_viz"),
                mode=mode,
            )
            cmd = ["cluster-only", str(cwd)]

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