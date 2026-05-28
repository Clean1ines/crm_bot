from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_faq_queue_uses_quality_gated_surface_compiler() -> None:
    source = (ROOT / "src/infrastructure/queue/handlers/knowledge_upload.py").read_text(
        encoding="utf-8"
    )
    faq_branch = source.split("if mode == MODE_FAQ:", 1)[1].split(
        "await KnowledgeIngestionService", 1
    )[0]

    assert "KnowledgeFaqSurfaceIngestionService" in faq_branch
    assert "GroqQualityGatedKnowledgeSurfaceCompiler" in faq_branch
    assert (
        "surface_compiler_factory=GroqQualityGatedKnowledgeSurfaceCompiler"
        in faq_branch
    )
    assert "surface_compiler_factory=GroqKnowledgeSurfaceCompiler" not in faq_branch
    assert "GroqKnowledgePreprocessor" not in faq_branch


def test_surface_compiler_contract_keeps_surfaces_and_reassignments() -> None:
    source = (ROOT / "src/infrastructure/llm/knowledge_surface_compiler.py").read_text(
        encoding="utf-8"
    )

    assert "parse_surface_compilation_payload" in source
    assert "fragments" in source
    assert "question_reassignments" in source
    assert "merge_decisions" in source
    assert "surfaces[]" in source
