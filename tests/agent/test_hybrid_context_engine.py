from agent.context_engine import ContextEngine
from plugins.context_engine.hybrid import HybridContextEngine


def _sample_messages():
    return [
        {"role": "system", "content": "You are a coding assistant."},
        {"role": "user", "content": "Read src/main.py and fix bug ABC-123."},
        {"role": "assistant", "content": "I inspected src/main.py and found a null dereference in parse_config()."},
        {"role": "user", "content": "Also check logs in logs/error.log and commit abc123def if needed."},
        {"role": "assistant", "content": "I will patch src/main.py and run scripts/run_tests.sh."},
        {"role": "user", "content": "Please continue with the fix and include tests."},
        {"role": "assistant", "content": "Running tests now and preparing patch output."},
    ]


def test_hybrid_engine_is_context_engine():
    engine = HybridContextEngine(settings={"context_length": 100000})
    assert isinstance(engine, ContextEngine)
    assert engine.name == "hybrid"


def test_hybrid_compress_preserves_head_and_tail():
    engine = HybridContextEngine(
        settings={
            "context_length": 100000,
            "protect_first_n": 1,
            "protect_last_n": 2,
            "similarity_floor": 0.05,
        }
    )
    msgs = _sample_messages()
    compressed = engine.compress(msgs, focus_topic="src/main.py bug fix")

    assert compressed[0]["role"] == "system"
    assert compressed[-2:] == msgs[-2:]
    assert any(m.get("role") == "assistant" and "[HYBRID CONTEXT SNAPSHOT]" in str(m.get("content", "")) for m in compressed)
    assert engine.compression_count == 1


def test_hybrid_fidelity_gate_blocks_entity_loss():
    engine = HybridContextEngine(settings={"context_length": 100000, "similarity_floor": 0.99})
    source = "Patch src/main.py for ABC-123 and commit abc123def."
    candidate = "Summary without required references."
    assert engine._passes_fidelity_gate(source, candidate) is False


def test_hybrid_force_override_from_settings():
    engine = HybridContextEngine(
        settings={
            "context_length": 100000,
            "force_override": True,
            "protect_first_n": 1,
            "protect_last_n": 2,
        }
    )
    assert engine.should_compress(1) is True
    assert engine.should_compress_preflight(_sample_messages()) is True


def test_hybrid_force_override_from_env(monkeypatch):
    monkeypatch.setenv("AOT_FORCE_COMPRESSION_OVERRIDE", "true")
    engine = HybridContextEngine(settings={"context_length": 100000, "force_override": False})
    assert engine.force_override is True
    assert engine.should_compress(0) is True
    monkeypatch.delenv("AOT_FORCE_COMPRESSION_OVERRIDE", raising=False)

