from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
STATE_CONTRACTS = ROOT / "src/domain/runtime/state_contracts.py"
RESPONSE_GENERATION = ROOT / "src/domain/runtime/response_generation.py"
PROMPT_BUILDER = ROOT / "src/agent/router/prompt_builder.py"
RESPONSE_GENERATOR = ROOT / "src/agent/nodes/response_generator.py"
COMMERCIAL_CONTEXT_NODE = ROOT / "src/agent/nodes/commercial_context_lookup.py"


def test_commercial_context_is_typed_in_runtime_state_contracts() -> None:
    source = STATE_CONTRACTS.read_text(encoding="utf-8")

    assert "commercial_context: Mapping[str, object]" in source
    assert "commercial_context_status: str | None" in source
    assert "commercial_context_sources: list[Mapping[str, object]]" in source


def test_response_generation_context_reads_and_passes_commercial_context() -> None:
    response_source = RESPONSE_GENERATION.read_text(encoding="utf-8")
    generator_source = RESPONSE_GENERATOR.read_text(encoding="utf-8")

    assert "commercial_context: Mapping[str, object] | None" in response_source
    assert "commercial_context=_mapping_or_none" in response_source
    assert "commercial_context=context.commercial_context" in generator_source


def test_prompt_builder_formats_structured_commercial_context_before_kb() -> None:
    source = PROMPT_BUILDER.read_text(encoding="utf-8")

    assert "def format_commercial_context(" in source
    assert "STRUCTURED COMMERCIAL CONTEXT" in source
    assert "GENERIC KNOWLEDGE BASE" in source
    assert "commercial_context_block = format_commercial_context" in source


def test_response_generator_does_not_call_commercial_price_tool_directly() -> None:
    generator_source = RESPONSE_GENERATOR.read_text(encoding="utf-8")
    node_source = COMMERCIAL_CONTEXT_NODE.read_text(encoding="utf-8")

    assert '"commercial_price_lookup"' not in generator_source
    assert '"commercial_price_lookup"' in node_source
