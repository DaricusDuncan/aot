---
sidebar_position: 33
title: "Use the Graphify Plugin"
description: "Enable the bundled Graphify plugin and generate/query a repository knowledge graph."
---

# Use the Graphify Plugin

The bundled `graphify` plugin adds native tools for building and exploring a repository knowledge graph from Aot chat sessions.

The plugin runs Graphify from vendored source in this repository (`vendor/graphify`) via an in-process runner. You do not need to install a separate `graphify` binary for normal plugin workflows.

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

After enabling, start using it from chat by asking the agent to call `graphify_build`, `graphify_query`, `graphify_path`, `graphify_explain`, or `graphify_prs`.

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

## Output directory and configuration

By default, Graphify writes generated artifacts to:

- `<target-root>/graphify-out/`

Where `<target-root>` is the `root_path` you pass to `graphify_build` (or the current repo root if you run against `.`).

Common output files include:

- `graphify-out/graph.json`
- `graphify-out/GRAPH_REPORT.md`
- `graphify-out/graph.html` (when visualization is generated)

To override the output directory name/path, set the `GRAPHIFY_OUT` environment variable before launching Aot. Graphify will then write to:

- `<target-root>/$GRAPHIFY_OUT/` for relative values (for example, `GRAPHIFY_OUT=graphify-out-feature`)
- the exact absolute path when `GRAPHIFY_OUT` is absolute

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
- If you use standalone Graphify CLI workflows outside the plugin, install/configure that CLI separately; plugin integration itself uses vendored in-repo Graphify.
