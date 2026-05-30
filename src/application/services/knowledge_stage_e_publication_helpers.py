from __future__ import annotations


import uuid
from collections.abc import Sequence
from src.application.ports.knowledge.ready_answer_publication import (
    KnowledgeStageEPublicationPort,
)
from src.domain.project_plane.knowledge_compilation import (
    AnswerCandidate,
    AnswerCandidateStatus,
    CandidateCluster,
    CandidateClusterStatus,
    CanonicalKnowledgeEntry,
    CompilationMetrics,
    KnowledgeEntryKind,
    SourceChunk,
)


KCD_STAGE_K_COMPILER_VERSION = "kcd_v1_stage_k_answer_compiler"


def build_stage_e_answer_candidates_from_entries(
    entries: Sequence[CanonicalKnowledgeEntry],
) -> tuple[AnswerCandidate, ...]:
    candidates: list[AnswerCandidate] = []

    for entry in entries:
        candidate_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{entry.id}:candidate"))
        candidates.append(
            AnswerCandidate(
                id=candidate_id,
                document_id=entry.document_id,
                project_id=entry.project_id,
                compiler_run_id=entry.compiler_run_id,
                topic_key=entry.stable_key,
                title=entry.title,
                candidate_answer=entry.answer,
                source_refs=entry.source_refs,
                confidence=1.0 if entry.has_source_refs else None,
                status=AnswerCandidateStatus.MERGED,
                metadata={
                    "entry_id": entry.id,
                    "stable_key": entry.stable_key,
                    "entry_kind": entry.entry_kind.value,
                    "stage": (
                        "stage_k_answer_compiler"
                        if entry.compiler_version == KCD_STAGE_K_COMPILER_VERSION
                        else "stage_e_one_to_one_trace"
                    ),
                },
            )
        )

    return tuple(candidates)


def build_stage_e_candidate_clusters_from_entries(
    *,
    entries: Sequence[CanonicalKnowledgeEntry],
    candidates: Sequence[AnswerCandidate],
) -> tuple[CandidateCluster, ...]:
    clusters: list[CandidateCluster] = []

    for entry, candidate in zip(entries, candidates, strict=True):
        clusters.append(
            CandidateCluster(
                id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"{entry.id}:cluster")),
                document_id=entry.document_id,
                project_id=entry.project_id,
                compiler_run_id=entry.compiler_run_id,
                cluster_key=entry.stable_key,
                topic=entry.title,
                candidate_ids=(candidate.id,),
                status=CandidateClusterStatus.CANONICAL_ENTRY_CREATED,
                merge_strategy="stage_e_one_to_one",
                merge_reason=(
                    "Initial Stage E trace keeps one candidate per canonical entry "
                    "until real clustering is introduced."
                ),
                metadata={
                    "entry_id": entry.id,
                    "stable_key": entry.stable_key,
                    "entry_kind": entry.entry_kind.value,
                },
            )
        )

    return tuple(clusters)


def build_stage_e_compilation_metrics(
    *,
    source_chunks: Sequence[SourceChunk],
    entries: Sequence[CanonicalKnowledgeEntry],
    candidates: Sequence[AnswerCandidate],
    clusters: Sequence[CandidateCluster],
) -> CompilationMetrics:
    grounded_candidates = sum(1 for candidate in candidates if candidate.has_grounding)
    rejected_candidates = sum(
        1
        for candidate in candidates
        if candidate.status == AnswerCandidateStatus.REJECTED
    )
    published_entries = sum(1 for entry in entries if entry.is_published_runtime_entry)
    embedded_entries = len(entries)
    entries_without_source_refs = sum(
        1 for entry in entries if not entry.has_source_refs
    )

    return CompilationMetrics(
        source_chunk_count=len(source_chunks),
        answer_candidate_count=len(candidates),
        grounded_candidate_count=grounded_candidates,
        rejected_candidate_count=rejected_candidates,
        candidate_cluster_count=len(clusters),
        canonical_entry_count=len(entries),
        enriched_entry_count=len(entries),
        embedded_entry_count=embedded_entries,
        published_entry_count=published_entries,
        fallback_row_count=sum(
            1
            for entry in entries
            if entry.entry_kind == KnowledgeEntryKind.FALLBACK_CHUNK
        ),
        entries_without_source_refs_count=entries_without_source_refs,
    )


async def persist_stage_e_compiler_outputs(
    *,
    repo: KnowledgeStageEPublicationPort,
    project_id: str,
    document_id: str,
    compiler_run_id: str,
    source_chunks: Sequence[SourceChunk],
    entries: Sequence[CanonicalKnowledgeEntry],
    complete_run: bool = True,
) -> None:
    candidates = build_stage_e_answer_candidates_from_entries(entries)
    clusters = build_stage_e_candidate_clusters_from_entries(
        entries=entries,
        candidates=candidates,
    )

    try:
        await repo.add_answer_candidates(
            project_id=project_id,
            document_id=document_id,
            candidates=candidates,
        )
        await repo.add_canonical_entries(
            project_id=project_id,
            document_id=document_id,
            entries=entries,
        )
        await repo.add_candidate_clusters(
            project_id=project_id,
            document_id=document_id,
            clusters=clusters,
        )
        if complete_run:
            await repo.complete_compiler_run(
                compiler_run_id,
                build_stage_e_compilation_metrics(
                    source_chunks=source_chunks,
                    entries=entries,
                    candidates=candidates,
                    clusters=clusters,
                ),
            )
    except Exception as exc:
        await repo.fail_compiler_run(compiler_run_id, str(exc))
        raise


__all__ = [
    "build_stage_e_answer_candidates_from_entries",
    "build_stage_e_candidate_clusters_from_entries",
    "build_stage_e_compilation_metrics",
    "persist_stage_e_compiler_outputs",
]
