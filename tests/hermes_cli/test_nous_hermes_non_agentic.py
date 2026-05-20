"""Tests for the Nous-Aot-3/4 non-agentic warning detector.

Prior to this check, the warning fired on any model whose name contained
``"aot"`` anywhere (case-insensitive). That false-positived on unrelated
local Modelfiles such as ``aot-brain:qwen3-14b-ctx16k`` — a tool-capable
Qwen3 wrapper that happens to live under the "aot" tag namespace.

``is_nous_aot_non_agentic`` should only match the actual Nous Research
Aot-3 / Aot-4 chat family.
"""

from __future__ import annotations

import pytest

from aot_cli.model_switch import (
    _AOT_MODEL_WARNING,
    _check_aot_model_warning,
    is_nous_aot_non_agentic,
)


@pytest.mark.parametrize(
    "model_name",
    [
        "NousResearch/Aot-3-Llama-3.1-70B",
        "NousResearch/Aot-3-Llama-3.1-405B",
        "aot-3",
        "Aot-3",
        "aot-4",
        "aot-4-405b",
        "aot_4_70b",
        "openrouter/aot3:70b",
        "openrouter/nousresearch/aot-4-405b",
        "NousResearch/Aot3",
        "aot-3.1",
    ],
)
def test_matches_real_nous_aot_chat_models(model_name: str) -> None:
    assert is_nous_aot_non_agentic(model_name), (
        f"expected {model_name!r} to be flagged as Nous Aot 3/4"
    )
    assert _check_aot_model_warning(model_name) == _AOT_MODEL_WARNING


@pytest.mark.parametrize(
    "model_name",
    [
        # Kyle's local Modelfile — qwen3:14b under a custom tag
        "aot-brain:qwen3-14b-ctx16k",
        "aot-brain:qwen3-14b-ctx32k",
        "aot-honcho:qwen3-8b-ctx8k",
        # Plain unrelated models
        "qwen3:14b",
        "qwen3-coder:30b",
        "qwen2.5:14b",
        "claude-opus-4-6",
        "anthropic/claude-sonnet-4.5",
        "gpt-5",
        "openai/gpt-4o",
        "google/gemini-2.5-flash",
        "deepseek-chat",
        # Non-chat Aot models we don't warn about
        "aot-llm-2",
        "aot2-pro",
        "nous-aot-2-mistral",
        # Edge cases
        "",
        "aot",  # bare "aot" isn't the 3/4 family
        "aot-brain",
        "brain-aot-3-impostor",  # "3" not preceded by /: boundary
    ],
)
def test_does_not_match_unrelated_models(model_name: str) -> None:
    assert not is_nous_aot_non_agentic(model_name), (
        f"expected {model_name!r} NOT to be flagged as Nous Aot 3/4"
    )
    assert _check_aot_model_warning(model_name) == ""


def test_none_like_inputs_are_safe() -> None:
    assert is_nous_aot_non_agentic("") is False
    # Defensive: the helper shouldn't crash on None-ish falsy input either.
    assert _check_aot_model_warning("") == ""
