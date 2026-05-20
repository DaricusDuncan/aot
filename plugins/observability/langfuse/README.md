# Langfuse Observability Plugin

This plugin ships bundled with Aot but is **opt-in** — it only loads when
you explicitly enable it.

## Enable

```bash
pip install langfuse
aot plugins enable observability/langfuse
```

Or check the box in the interactive `aot plugins` UI.

## Required credentials

Set these in `~/.aot/.env`:

```bash
AOT_LANGFUSE_PUBLIC_KEY=pk-lf-...
AOT_LANGFUSE_SECRET_KEY=sk-lf-...
AOT_LANGFUSE_BASE_URL=https://cloud.langfuse.com   # or your self-hosted URL
```

Without the SDK or credentials the hooks no-op silently — the plugin fails
open.

## Verify

```bash
aot plugins list                 # observability/langfuse should show "enabled"
aot chat -q "hello"              # then check Langfuse for a "Aot turn" trace
```

## Optional tuning

```bash
AOT_LANGFUSE_ENV=production       # environment tag
AOT_LANGFUSE_RELEASE=v1.0.0       # release tag
AOT_LANGFUSE_SAMPLE_RATE=0.5      # sample 50% of traces
AOT_LANGFUSE_MAX_CHARS=12000      # max chars per field (default: 12000)
AOT_LANGFUSE_DEBUG=true           # verbose plugin logging
```

## Disable

```bash
aot plugins disable observability/langfuse
```
