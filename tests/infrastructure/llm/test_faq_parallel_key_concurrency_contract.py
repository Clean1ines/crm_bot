from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
COMPILER = ROOT / "src/infrastructure/llm/knowledge_surface_parallel_graph_compiler.py"


def test_parallel_source_unit_concurrency_uses_configured_groq_key_count() -> None:
    source = COMPILER.read_text(encoding="utf-8")

    assert "configured_groq_api_keys" in source
    assert "def _configured_key_count" in source
    assert "return max(1, min(max(parsed, key_count), 8))" in source
    assert '"configured_groq_key_count": configured_key_count' in source
    assert '"parallel_source_unit_slots": concurrency' in source
