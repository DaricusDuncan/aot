"""Tests for the Graphify plugin.

Includes:
- unit tests for command construction/validation in plugins.graphify.tools
- integration check that AIAgent chat requests include Graphify tools once the
  plugin is enabled and discovered
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import yaml


def _mock_response(content: str = "ok"):
    """Create a minimal ChatCompletion-like response object."""
    msg = SimpleNamespace(content=content, tool_calls=None)
    choice = SimpleNamespace(message=msg, finish_reason="stop")
    return SimpleNamespace(choices=[choice], model="test/model", usage=None)


def _write_enabled_config(aot_home: Path) -> None:
    """Write config.yaml enabling the bundled graphify plugin."""
    cfg = {"plugins": {"enabled": ["graphify"]}}
    (aot_home / "config.yaml").write_text(yaml.safe_dump(cfg), encoding="utf-8")


class TestGraphifyToolHandlers:
    def test_build_extract_maps_arguments_to_graphify_cli(self, tmp_path):
        from plugins.graphify.tools import handle_graphify_build

        project = tmp_path / "repo"
        project.mkdir()

        captured = {}

        def _fake_run(args, *, cwd, timeout_seconds=180):
            captured["args"] = args
            captured["cwd"] = cwd
            captured["timeout_seconds"] = timeout_seconds
            return {
                "success": True,
                "exit_code": 0,
                "stdout": '{"status":"ok"}',
                "stderr": "",
                "command": ["graphify", *args],
                "cwd": str(cwd),
                "elapsed_ms": 12,
            }

        with patch("plugins.graphify.tools.run_graphify_command", side_effect=_fake_run):
            result = handle_graphify_build(
                {
                    "root_path": str(project),
                    "mode": "extract",
                    "backend": "gemini",
                    "model": "gemini-3-flash-preview",
                    "token_budget": 12000,
                    "max_concurrency": 2,
                    "no_viz": True,
                }
            )

        assert '"success": true' in result
        assert captured["args"] == [
            "extract",
            str(project.resolve()),
            "--backend",
            "gemini",
            "--model",
            "gemini-3-flash-preview",
            "--token-budget",
            "12000",
            "--max-concurrency",
            "2",
            "--no-cluster",
        ]

    def test_build_update_rejects_extract_only_fields(self, tmp_path):
        from plugins.graphify.tools import handle_graphify_build

        project = tmp_path / "repo"
        project.mkdir()

        result = handle_graphify_build(
            {
                "root_path": str(project),
                "mode": "update",
                "backend": "gemini",
            }
        )

        assert '"success": false' in result
        assert "not supported for mode 'update'" in result

    def test_query_passes_optional_graph_and_budget(self, tmp_path):
        from plugins.graphify.tools import handle_graphify_query

        project = tmp_path / "repo"
        project.mkdir()
        graph = project / "graphify-out" / "graph.json"
        graph.parent.mkdir()
        graph.write_text("{}", encoding="utf-8")

        captured = {}

        def _fake_run(args, *, cwd, timeout_seconds=180):
            captured["args"] = args
            captured["cwd"] = cwd
            return {
                "success": True,
                "exit_code": 0,
                "stdout": "answer",
                "stderr": "",
                "command": ["graphify", *args],
                "cwd": str(cwd),
                "elapsed_ms": 9,
            }

        with patch("plugins.graphify.tools.run_graphify_command", side_effect=_fake_run):
            _ = handle_graphify_query(
                {
                    "root_path": str(project),
                    "question": "what connects auth to db?",
                    "graph_path": str(graph),
                    "dfs": True,
                    "budget": 1500,
                }
            )

        assert captured["args"] == [
            "query",
            "what connects auth to db?",
            "--graph",
            str(graph),
            "--dfs",
            "--budget",
            "1500",
        ]

    def test_prs_requires_positive_pr_number(self, tmp_path):
        from plugins.graphify.tools import handle_graphify_prs

        project = tmp_path / "repo"
        project.mkdir()
        result = handle_graphify_prs({"root_path": str(project), "pr_number": 0})
        assert '"success": false' in result
        assert "pr_number must be a positive integer" in result


class TestGraphifyPluginChatIntegration:
    def test_aiagent_chat_request_includes_graphify_tools_when_plugin_enabled(self, tmp_path, monkeypatch):
        """Integration: enable graphify plugin and verify chat request tool list includes it."""
        aot_home = tmp_path / ".aot"
        aot_home.mkdir()
        _write_enabled_config(aot_home)
        monkeypatch.setenv("AOT_HOME", str(aot_home))

        from aot_cli.plugins import discover_plugins

        # Force reload of plugin state for this isolated AOT_HOME.
        discover_plugins(force=True)

        import run_agent
        from run_agent import AIAgent

        with patch.object(run_agent, "OpenAI"):
            agent = AIAgent(
                api_key="test-key-1234567890",
                base_url="https://openrouter.ai/api/v1",
                quiet_mode=True,
                skip_context_files=True,
                skip_memory=True,
            )

            called = {}

            def _capture_create(api_kwargs=None, **kwargs):
                if isinstance(api_kwargs, dict):
                    called["kwargs"] = api_kwargs
                else:
                    called["kwargs"] = kwargs
                return _mock_response("Graphify integrated.")
            agent._interruptible_api_call = _capture_create
            agent.client.chat.completions.create = _capture_create
            result = agent.run_conversation("Summarize this repo quickly.")

        assert result["completed"] is True
        assert "Graphify integrated." in result["final_response"]
        tools = called["kwargs"]["tools"]
        tool_names = {t["function"]["name"] for t in tools}
        assert "graphify_build" in tool_names
        assert "graphify_query" in tool_names
