---
sidebar_position: 33
title: "Use the Graphify Plugin"
description: "Enable the bundled Graphify plugin and generate/query a repository knowledge graph."
---

# Use the Graphify Plugin

The bundled `graphify` plugin adds native tools for building and exploring a repository knowledge graph from Aot chat sessions.

## Prerequisites

- Vendored Graphify source exists under `vendor/graphify` in this repository.
- Graphify backend credentials are configured for the semantic backend you plan to use.

## Enable the plugin

Enable once via CLI:

```bash
aot plugins enable graphify
```

Or add it in `~/.aot/config.yaml`:

```yaml
plugins:
  enabled:
    - graphify
```

## Generate a graph

Ask Aot to build a graph:

> Build a Graphify graph for this repository using extract mode and skip visualization.

This maps to `graphify_build` with:

```json
{
  "root_path": "/path/to/repo",
  "mode": "extract",
  "no_viz": true
}
```

Optional extraction tuning fields:

- `backend`
- `model`
- `token_budget`
- `max_concurrency`

On success, Graphify outputs are written under `graphify-out/` in the target repo.

## Query and inspect the graph

After extraction, ask follow-up questions like:

- “Query the graph for how auth connects to the database.”
- “Find the shortest path between UserService and PostgresClient.”
- “Explain the GraphSyncCoordinator entity from graph context.”

These map to:

- `graphify_query`
- `graphify_path`
- `graphify_explain`

For PR-focused graph analysis, use:

- `graphify_prs`

## Troubleshooting

- `graphify_not_available`: confirm `vendor/graphify` exists and is readable from your checkout.
- backend/auth errors during `extract`: verify your Graphify backend credentials and chosen backend/model settings.
- no output graph files: rerun with `mode: "extract"` first, then use `update` for incremental refreshes.
