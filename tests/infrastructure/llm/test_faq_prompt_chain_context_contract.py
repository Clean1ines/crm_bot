from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
V2 = ROOT / "src/infrastructure/llm/knowledge_surface_graph_compiler_v2.py"
FULL = ROOT / "src/infrastructure/llm/knowledge_surface_full_graph_compiler.py"
PARALLEL = ROOT / "src/infrastructure/llm/knowledge_surface_parallel_graph_compiler.py"


def test_llm_stage_methods_accept_and_forward_compilation_context() -> None:
    source = V2.read_text(encoding="utf-8")

    assert source.count("compilation_context: Mapping[str, object] | None = None") == 4
    assert (
        source.count('payload["compilation_context"] = dict(compilation_context)') == 4
    )


def test_full_and_parallel_compilers_build_intent_ledger_context() -> None:
    full = FULL.read_text(encoding="utf-8")
    parallel = PARALLEL.read_text(encoding="utf-8")

    assert "def _intent_ledger_context(" in full
    assert "known_answer_slots" in full
    assert "known_candidates_without_answer_yet" in full
    assert "duplicate_or_alias_relations" in full
    assert "merge_decision_is_authoritative" in full
    assert "compilation_context=_intent_ledger_context" in full
    assert "compilation_context=_intent_ledger_context" in parallel
