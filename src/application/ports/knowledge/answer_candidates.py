from __future__ import annotations

from collections.abc import Sequence
from src.domain.project_plane.knowledge_compilation import (
    AnswerCandidate,
    CandidateCluster,
)
from src.domain.project_plane.knowledge_views import KnowledgeAnswerCandidateSummaryView
from typing import Protocol


class KnowledgeAnswerCandidatePort(Protocol):
    async def delete_raw_answer_candidates_for_batch(
        self,
        *,
        project_id: str,
        document_id: str,
        batch_id: str,
    ) -> int: ...

    async def add_answer_candidates(
        self,
        *,
        project_id: str,
        document_id: str,
        candidates: Sequence[AnswerCandidate],
    ) -> int: ...

    async def add_candidate_clusters(
        self,
        *,
        project_id: str,
        document_id: str,
        clusters: Sequence[CandidateCluster],
    ) -> int: ...

    async def list_document_raw_answer_candidates(
        self,
        *,
        project_id: str,
        document_id: str,
    ) -> tuple[AnswerCandidate, ...]: ...

    async def get_document_answer_candidate_summary(
        self,
        *,
        project_id: str,
        document_id: str,
    ) -> KnowledgeAnswerCandidateSummaryView: ...
