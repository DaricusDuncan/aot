"""Tool registration for restore_tool_output.

Auto-discovered by tools/registry.py at import time.
Delegates to agent/tool_output_store.py for the actual store access.
"""
from tools.registry import registry

_SCHEMA = {
    "name": "restore_tool_output",
    "description": (
        "Restore the full contents of a tool output that was moved out of "
        "context to save space (shown as an AOT_EVICTED_OUTPUT stub). "
        "Pass the key from the stub. Optionally pin the output so it is not "
        "evicted again this session."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "key": {
                "type": "string",
                "description": "The eviction key from the stub (e.g. 'a1b2c3d4e5f60718').",
            },
            "pin": {
                "type": "boolean",
                "description": (
                    "If true, keep this output verbatim for the rest of the "
                    "session so it is not evicted again."
                ),
                "default": False,
            },
        },
        "required": ["key"],
    },
}


def _handler(args: dict, **_kw) -> str:
    from agent.tool_output_store import get_store, handle_restore_tool_output

    store = get_store()
    if store is None:
        return "Tool output store is not active in this session."
    return handle_restore_tool_output(store, args["key"], args.get("pin", False))


registry.register(
    name="restore_tool_output",
    toolset="aot-cli",
    schema=_SCHEMA,
    handler=_handler,
    emoji="♻️",
    description="Restore an evicted tool output from the session store.",
)
