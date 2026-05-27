from __future__ import annotations

from pathlib import Path

import pytest

from src.domain.project_plane.knowledge_preprocessing import (
    MODE_FAQ,
    KnowledgePreprocessingValidationError,
)
from src.domain.project_plane.retrieval_surface_compilation import (
    RetrievalSurfaceSourceUnit,
)
from src.infrastructure.llm.knowledge_surface_compiler import (
    parse_surface_compilation_payload,
)

ROOT = Path(__file__).resolve().parents[2]


def _source_unit() -> RetrievalSurfaceSourceUnit:
    return RetrievalSurfaceSourceUnit(
        id="unit-1",
        run_id="run-1",
        document_id="doc-1",
        source_unit_key="product",
        source_chunk_indexes=(0,),
        title="Что это за продукт",
        body="CRM bot compiles FAQ retrieval surfaces.",
        children=(),
        raw_text="CRM bot compiles FAQ retrieval surfaces.",
        section_path=("Что это за продукт",),
        source_refs=("chunk:0",),
        preprocessing_mode=MODE_FAQ,
    )


def test_surface_compiler_parses_real_contract_without_fragments() -> None:
    result = parse_surface_compilation_payload(
        {
            "surfaces": [
                {
                    "local_surface_key": "product_overview",
                    "source_unit_key": "product",
                    "title": "Что это за продукт",
                    "canonical_question": "Что делает продукт?",
                    "surface_kind": "umbrella",
                    "answer_scope": "Product overview",
                    "question_scope": "General product questions",
                    "exclusion_scope": "Channel-specific questions",
                    "answer": "Продукт превращает документы FAQ в проверяемые поисковые поверхности.",
                    "short_answer": "Продукт компилирует FAQ в поисковые поверхности.",
                    "source_chunk_indexes": [0],
                    "source_refs": ["chunk:0"],
                    "confidence": 0.91,
                },
                {
                    "local_surface_key": "retrieval_surface",
                    "source_unit_key": "product",
                    "title": "Поисковая поверхность",
                    "canonical_question": "Что такое поисковая поверхность?",
                    "surface_kind": "retrieval_quality",
                    "answer_scope": "Retrieval surface definition",
                    "question_scope": "Search surface questions",
                    "exclusion_scope": "Product overview",
                    "answer": "Поисковая поверхность — отдельная карточка намерения с вопросами и source refs.",
                    "short_answer": "Это карточка намерения для retrieval.",
                    "source_chunk_indexes": [0],
                    "source_refs": ["chunk:0"],
                    "confidence": 0.88,
                },
            ],
            "relations": [
                {
                    "parent_surface_key": "product_overview",
                    "child_surface_key": "retrieval_surface",
                    "relation_type": "umbrella_contains",
                    "reason": "Overview contains retrieval-quality child topic.",
                    "confidence": 0.8,
                }
            ],
            "question_ownership": [
                {
                    "question": "Что такое поисковая поверхность?",
                    "owner_surface_key": "retrieval_surface",
                    "question_kind": "faq_question",
                    "confidence": 0.9,
                    "reason": "Specific retrieval concept, not product overview.",
                    "rejected_from_surface_keys": ["product_overview"],
                }
            ],
            "merge_decisions": [
                {
                    "survivor_surface_key": "product_overview",
                    "merged_surface_keys": [],
                    "keep_separate_surface_keys": [
                        "product_overview",
                        "retrieval_surface",
                    ],
                    "decision_type": "keep_separate",
                    "reason": "Umbrella and child stay separate.",
                    "confidence": 0.9,
                }
            ],
        },
        mode=MODE_FAQ,
        model="test-model",
        run_id="run-1",
        document_id="doc-1",
        source_units=(_source_unit(),),
    )

    assert result.prompt_version == "faq_retrieval_surface_compilation_v1"
    assert [surface.surface_kind for surface in result.graph.surfaces] == [
        "umbrella",
        "retrieval_quality",
    ]
    assert result.graph.ownership[0].owner_surface_key == "retrieval_surface"
    assert result.graph.ownership[0].rejected_from_surface_keys == ("product_overview",)
    assert result.graph.merge_decisions[0].decision_type == "keep_separate"


def test_surface_compiler_rejects_legacy_fragments_contract() -> None:
    with pytest.raises(
        KnowledgePreprocessingValidationError, match="surfaces\[\].*fragments"
    ):
        parse_surface_compilation_payload(
            {"fragments": [], "surfaces": []},
            mode=MODE_FAQ,
            model="test-model",
            run_id="run-1",
            document_id="doc-1",
            source_units=(_source_unit(),),
        )


def test_short_answer_service_label_is_not_surface_title() -> None:
    result = parse_surface_compilation_payload(
        {
            "surfaces": [
                {
                    "local_surface_key": "short_answer_label",
                    "source_unit_key": "product",
                    "title": "Короткий ответ клиенту",
                    "canonical_question": "Короткий ответ клиенту",
                    "surface_kind": "standalone",
                    "answer": "Служебный короткий ответ.",
                },
                {
                    "local_surface_key": "product_overview",
                    "source_unit_key": "product",
                    "title": "Что это за продукт",
                    "canonical_question": "Что делает продукт?",
                    "surface_kind": "umbrella",
                    "answer": "Продукт компилирует FAQ в поисковые поверхности.",
                    "short_answer": "Компиляция FAQ в retrieval surfaces.",
                },
            ],
            "relations": [],
            "question_ownership": [],
            "merge_decisions": [],
        },
        mode=MODE_FAQ,
        model="test-model",
        run_id="run-1",
        document_id="doc-1",
        source_units=(_source_unit(),),
    )

    assert [surface.title for surface in result.graph.surfaces] == [
        "Что это за продукт"
    ]
    assert (
        result.graph.surfaces[0].metadata["short_answer_service_labels_absorbed"] == 1
    )


def test_all_standalone_chunk_like_surfaces_are_rejected() -> None:
    with pytest.raises(KnowledgePreprocessingValidationError, match="all-standalone"):
        parse_surface_compilation_payload(
            {
                "surfaces": [
                    {
                        "local_surface_key": "chunk_0",
                        "source_unit_key": "product",
                        "title": "Фрагмент 1",
                        "surface_kind": "standalone",
                        "answer": "Chunk copy one.",
                    },
                    {
                        "local_surface_key": "chunk_1",
                        "source_unit_key": "product",
                        "title": "Фрагмент 2",
                        "surface_kind": "standalone",
                        "answer": "Chunk copy two.",
                    },
                ],
                "relations": [],
                "question_ownership": [],
                "merge_decisions": [],
            },
            mode=MODE_FAQ,
            model="test-model",
            run_id="run-1",
            document_id="doc-1",
            source_units=(_source_unit(),),
        )


def test_faq_queue_wiring_uses_surface_compiler_not_legacy_preprocessor() -> None:
    source = (ROOT / "src/infrastructure/queue/handlers/knowledge_upload.py").read_text(
        encoding="utf-8"
    )
    faq_branch = source.split("if mode == MODE_FAQ:", 1)[1].split(
        "await KnowledgeIngestionService", 1
    )[0]

    assert "KnowledgeFaqSurfaceIngestionService" in faq_branch
    assert "surface_compiler_factory=GroqKnowledgeSurfaceCompiler" in faq_branch
    assert "GroqKnowledgePreprocessor" not in faq_branch
    assert "preprocess(" not in faq_branch


def test_surface_publication_creates_runtime_entry_instead_of_409_guard() -> None:
    source = (ROOT / "src/interfaces/http/knowledge_surface.py").read_text(
        encoding="utf-8"
    )

    assert "add_canonical_entries" in source
    assert "KnowledgeEntryKind.FAQ_ANSWER" in source
    assert "link_surface_to_runtime_entry" in source
    assert "linked_canonical_entry_id" in source
    assert "Surface has no linked runtime entry yet" not in source


def test_fastapi_registers_surface_router_before_legacy_knowledge_router() -> None:
    source = (ROOT / "src/interfaces/http/app.py").read_text(encoding="utf-8")

    assert source.index("app.include_router(knowledge_surface_router)") < source.index(
        "app.include_router(knowledge_router)"
    )


def test_frontend_surface_api_exists_and_is_rendered() -> None:
    api_source = (
        ROOT / "frontend/src/shared/api/modules/knowledgeSurface.ts"
    ).read_text(encoding="utf-8")
    card_source = (
        ROOT / "frontend/src/pages/knowledge/components/KnowledgeDocumentCard.tsx"
    ).read_text(encoding="utf-8")

    for needle in (
        "surface-compilation",
        "surface-relations",
        "surface-ownership",
        "publish",
    ):
        assert needle in api_source
    assert "SurfaceCompilationSummary" in card_source
    assert "enabled={doc.preprocessing_mode === 'faq'}" in card_source


def test_surface_compiler_parses_explicit_question_reassignments() -> None:
    result = parse_surface_compilation_payload(
        {
            "surfaces": [
                {
                    "local_surface_key": "product_overview",
                    "source_unit_key": "product",
                    "title": "Что это за продукт",
                    "canonical_question": "Что делает продукт?",
                    "surface_kind": "umbrella",
                    "answer": "Продукт компилирует FAQ в поисковые поверхности.",
                },
                {
                    "local_surface_key": "pricing",
                    "source_unit_key": "product",
                    "title": "Стоимость",
                    "canonical_question": "Сколько стоит продукт?",
                    "surface_kind": "specific",
                    "answer": "Стоимость относится к отдельной коммерческой поверхности.",
                },
            ],
            "relations": [],
            "question_ownership": [
                {
                    "question": "Сколько стоит продукт?",
                    "owner_surface_key": "pricing",
                    "rejected_from_surface_keys": ["product_overview"],
                }
            ],
            "question_reassignments": [
                {
                    "question": "Сколько стоит продукт?",
                    "from_surface_key": "product_overview",
                    "to_surface_key": "pricing",
                    "reason": "Pricing question must not be owned by product overview.",
                    "confidence": 0.92,
                }
            ],
            "merge_decisions": [],
        },
        mode=MODE_FAQ,
        model="test-model",
        run_id="run-1",
        document_id="doc-1",
        source_units=(_source_unit(),),
    )

    assert len(result.graph.reassignments) == 1
    reassignment = result.graph.reassignments[0]
    assert reassignment.question == "Сколько стоит продукт?"
    assert reassignment.from_surface_key == "product_overview"
    assert reassignment.to_surface_key == "pricing"
    assert result.metrics["reassignment_count"] == 1
