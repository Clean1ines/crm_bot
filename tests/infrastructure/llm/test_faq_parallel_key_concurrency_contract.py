from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
COMPILER = ROOT / "src/infrastructure/llm/knowledge_surface_parallel_graph_compiler.py"


def test_parallel_source_unit_concurrency_is_fixed_to_three() -> None:
    source = COMPILER.read_text(encoding="utf-8")

    assert "DEFAULT_FAQ_SURFACE_GRAPH_CONCURRENCY = 3" in source
    assert "def _concurrency" in source
    assert "return DEFAULT_FAQ_SURFACE_GRAPH_CONCURRENCY" in source

    # The compiler must not use env/key-count adaptive scheduling anymore.
    assert "os.getenv" not in source
    assert "raw_value = os.getenv" not in source
    assert "return max(1, min(max(parsed, key_count), 8))" not in source


def test_parallel_source_unit_metrics_still_report_groq_key_count() -> None:
    source = COMPILER.read_text(encoding="utf-8")

    assert "configured_groq_api_keys" in source
    assert "def _configured_key_count" in source
    assert '"configured_groq_key_count": configured_key_count' in source
    assert '"parallel_source_unit_slots": concurrency' in source
