from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
COMPILER = ROOT / "src/infrastructure/llm/knowledge_surface_parallel_graph_compiler.py"


def test_parallel_faq_compiler_persists_source_unit_checkpoints() -> None:
    source = COMPILER.read_text(encoding="utf-8")

    assert "SOURCE_UNIT_CHECKPOINT_VERSION = 1" in source
    assert "source_unit_checkpoint" in source
    assert "_unit_result_to_checkpoint" in source
    assert "_unit_result_from_checkpoint" in source


def test_parallel_faq_compiler_reuses_checkpoint_before_llm_work() -> None:
    source = COMPILER.read_text(encoding="utf-8")

    assert "set_source_unit_result_checkpoints" in source
    assert "checkpoint_results.get(unit.source_unit_key)" in source
    assert "source_unit_checkpoint_reused" in source
    assert "return replace(cached_result, unit_index=unit_index)" in source
