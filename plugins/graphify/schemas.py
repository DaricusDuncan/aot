"""Tool schemas for the Graphify plugin."""

from __future__ import annotations

GRAPHIFY_BUILD_SCHEMA = {
    "name": "graphify_build",
    "description": (
        "Build, update, or recluster a Graphify knowledge graph for a project. "
        "Use this when the user asks to create or refresh a graph representation "
        "of a repository."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "root_path": {
                "type": "string",
                "description": (
                    "Project directory to process. Defaults to the current working directory."
                ),
            },
            "mode": {
                "type": "string",
                "enum": ["extract", "update", "cluster_only"],
                "description": (
                    "Graphify operation mode: full extract, incremental update, or clustering only."
                ),
            },
            "no_viz": {
                "type": "boolean",
                "description": "Skip visualization output generation when supported.",
            },
            "backend": {
                "type": "string",
                "description": (
                    "Optional semantic backend for headless extraction "
                    "(for example: gemini, kimi, claude, openai, deepseek, ollama, bedrock)."
                ),
            },
            "model": {
                "type": "string",
                "description": "Optional backend model override.",
            },
            "token_budget": {
                "type": "integer",
                "description": "Optional per-chunk token budget for semantic extraction.",
            },
            "max_concurrency": {
                "type": "integer",
                "description": "Optional semantic extraction concurrency override.",
            },
        },
        "required": [],
    },
}

GRAPHIFY_QUERY_SCHEMA = {
    "name": "graphify_query",
    "description": (
        "Query a Graphify graph with a natural-language question and return graph-grounded results."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "question": {
                "type": "string",
                "description": "Question to ask against the graph.",
            },
            "root_path": {
                "type": "string",
                "description": (
                    "Project directory containing graphify-out/. Defaults to current working directory."
                ),
            },
            "graph_path": {
                "type": "string",
                "description": "Optional explicit path to graph.json.",
            },
            "dfs": {
                "type": "boolean",
                "description": "Enable DFS traversal mode for broader traversal.",
            },
            "budget": {
                "type": "integer",
                "description": "Optional traversal budget.",
            },
        },
        "required": ["question"],
    },
}

GRAPHIFY_PATH_SCHEMA = {
    "name": "graphify_path",
    "description": (
        "Find a shortest relationship path between two entities in a Graphify graph."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "source": {
                "type": "string",
                "description": "Start entity label or node identifier.",
            },
            "target": {
                "type": "string",
                "description": "End entity label or node identifier.",
            },
            "root_path": {
                "type": "string",
                "description": "Project directory containing graphify-out/.",
            },
            "graph_path": {
                "type": "string",
                "description": "Optional explicit path to graph.json.",
            },
        },
        "required": ["source", "target"],
    },
}

GRAPHIFY_EXPLAIN_SCHEMA = {
    "name": "graphify_explain",
    "description": (
        "Explain an entity using the graph neighborhood and relationships from Graphify."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "entity": {
                "type": "string",
                "description": "Entity label or node identifier to explain.",
            },
            "root_path": {
                "type": "string",
                "description": "Project directory containing graphify-out/.",
            },
            "graph_path": {
                "type": "string",
                "description": "Optional explicit path to graph.json.",
            },
        },
        "required": ["entity"],
    },
}

GRAPHIFY_PRS_SCHEMA = {
    "name": "graphify_prs",
    "description": (
        "Inspect pull-request graph impact and queue health using Graphify PR tooling."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "pr_number": {
                "type": "integer",
                "description": "Optional PR number for detailed inspection.",
            },
            "triage": {
                "type": "boolean",
                "description": "Run triage ranking mode.",
            },
            "conflicts": {
                "type": "boolean",
                "description": "Show likely merge-order conflict candidates.",
            },
            "base_branch": {
                "type": "string",
                "description": "Optional base branch filter.",
            },
            "repo": {
                "type": "string",
                "description": "Optional GitHub repository in owner/name format.",
            },
            "root_path": {
                "type": "string",
                "description": "Project directory to run from.",
            },
        },
        "required": [],
    },
}
