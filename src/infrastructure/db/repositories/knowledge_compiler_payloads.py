from __future__ import annotations

import json
from collections.abc import Mapping, Sequence

from src.domain.project_plane.knowledge_compilation import (
    AnswerCandidate,
    CompilationMetrics,
)


def compiler_metrics_payload(metrics: CompilationMetrics) -> dict[str, object]:
    return {
        "source_chunk_count": metrics.source_chunk_count,
        "answer_candidate_count": metrics.answer_candidate_count,
        "grounded_candidate_count": metrics.grounded_candidate_count,
        "rejected_candidate_count": metrics.rejected_candidate_count,
        "candidate_cluster_count": metrics.candidate_cluster_count,
        "canonical_entry_count": metrics.canonical_entry_count,
        "enriched_entry_count": metrics.enriched_entry_count,
        "embedded_entry_count": metrics.embedded_entry_count,
        "published_entry_count": metrics.published_entry_count,
        "fallback_row_count": metrics.fallback_row_count,
        "dropped_forbidden_count": metrics.dropped_forbidden_count,
        "entries_without_source_refs_count": metrics.entries_without_source_refs_count,
    }


def compiler_jsonb_array_payload(values: Sequence[Mapping[str, object]]) -> str:
    return json.dumps(list(values), ensure_ascii=False)


def answer_candidate_source_refs_payload(
    candidate: AnswerCandidate,
) -> list[dict[str, object]]:
    payload: list[dict[str, object]] = []
    for source_ref in candidate.source_refs:
        payload.append(
            {
                "source_index": source_ref.source_index,
                "quote": source_ref.quote,
                "source_chunk_id": source_ref.source_chunk_id,
                "start_offset": source_ref.start_offset,
                "end_offset": source_ref.end_offset,
                "confidence": source_ref.confidence,
            }
        )
    return payload
