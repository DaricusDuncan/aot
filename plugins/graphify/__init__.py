"""Graphify plugin registration.

This plugin exposes Graphify CLI operations as Aot tools so agents can
build and query project knowledge graphs without manual shell orchestration.
"""

from __future__ import annotations

from plugins.graphify.schemas import (
    GRAPHIFY_BUILD_SCHEMA,
    GRAPHIFY_EXPLAIN_SCHEMA,
    GRAPHIFY_PATH_SCHEMA,
    GRAPHIFY_PRS_SCHEMA,
    GRAPHIFY_QUERY_SCHEMA,
)
from plugins.graphify.tools import (
    handle_graphify_build,
    handle_graphify_explain,
    handle_graphify_path,
    handle_graphify_prs,
    handle_graphify_query,
)

_TOOLS = (
    ("graphify_build", GRAPHIFY_BUILD_SCHEMA, handle_graphify_build, "🕸️"),
    ("graphify_query", GRAPHIFY_QUERY_SCHEMA, handle_graphify_query, "🔎"),
    ("graphify_path", GRAPHIFY_PATH_SCHEMA, handle_graphify_path, "🧭"),
    ("graphify_explain", GRAPHIFY_EXPLAIN_SCHEMA, handle_graphify_explain, "🧠"),
    ("graphify_prs", GRAPHIFY_PRS_SCHEMA, handle_graphify_prs, "🧪"),
)


def register(ctx) -> None:
    """Register Graphify tools with the plugin runtime."""
    for name, schema, handler, emoji in _TOOLS:
        ctx.register_tool(
            name=name,
            toolset="graphify",
            schema=schema,
            handler=handler,
            emoji=emoji,
        )
