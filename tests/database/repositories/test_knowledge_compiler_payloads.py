from __future__ import annotations

from dataclasses import dataclass

from src.domain.project_plane.knowledge_compilation import (
    CompilationMetrics,
    SourceRef,
)
from src.infrastructure.db.repositories.knowledge_compiler_payloads import (
    answer_candidate_source_refs_payload,
    compiler_jsonb_array_payload,
    compiler_metrics_payload,
)


@dataclass(frozen=True, slots=True)
class _CandidateLike:
    source_refs: tuple[SourceRef, ...]


def test_compiler_metrics_payload_preserves_stage_e_metric_names() -> None:
    metrics = CompilationMetrics(
        source_chunk_count=1,
        answer_candidate_count=2,
        grounded_candidate_count=3,
        rejected_candidate_count=4,
        candidate_cluster_count=5,
        canonical_entry_count=6,
        enriched_entry_count=7,
        embedded_entry_count=8,
        published_entry_count=9,
        fallback_row_count=10,
        dropped_forbidden_count=11,
        entries_without_source_refs_count=12,
    )

    assert compiler_metrics_payload(metrics) == {
        "source_chunk_count": 1,
        "answer_candidate_count": 2,
        "grounded_candidate_count": 3,
        "rejected_candidate_count": 4,
        "candidate_cluster_count": 5,
        "canonical_entry_count": 6,
        "enriched_entry_count": 7,
        "embedded_entry_count": 8,
        "published_entry_count": 9,
        "fallback_row_count": 10,
        "dropped_forbidden_count": 11,
        "entries_without_source_refs_count": 12,
    }


def test_compiler_jsonb_array_payload_serializes_sequence_without_ascii_loss() -> None:
    assert compiler_jsonb_array_payload(({"title": "Цена"}, {"title": "Доставка"})) == (
        '[{"title": "Цена"}, {"title": "Доставка"}]'
    )


def test_answer_candidate_source_refs_payload_preserves_grounding_fields() -> None:
    candidate = _CandidateLike(
        source_refs=(
            SourceRef(
                source_index=2,
                quote="quoted source",
                source_chunk_id="chunk-1",
                start_offset=10,
                end_offset=20,
                confidence=0.8,
            ),
        )
    )

    assert answer_candidate_source_refs_payload(candidate) == [
        {
            "source_index": 2,
            "quote": "quoted source",
            "source_chunk_id": "chunk-1",
            "start_offset": 10,
            "end_offset": 20,
            "confidence": 0.8,
        }
    ]
