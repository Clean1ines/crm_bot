from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

import pytest

from src.contexts.knowledge_workbench.rag_eval.application.errors.workbench_rag_eval_promotion_application_errors import (
    WorkbenchRagEvalPromotionConflictCode,
    WorkbenchRagEvalPromotionConflictError,
)
from src.contexts.knowledge_workbench.rag_eval.infrastructure.postgres.postgres_workbench_rag_eval_repository import (
    PostgresWorkbenchRagEvalRepository,
)


PROJECT_ID = "11111111-1111-1111-1111-111111111111"


@dataclass(slots=True)
class InvalidDimensionsConnection:
    async def fetch(
        self,
        query: str,
        *args: object,
    ) -> list[Mapping[str, object]]:
        assert "WORKBENCH_RAG_EVAL" not in query
        assert args == (PROJECT_ID, ["promotion-1"], "entry-1", "model-1")
        return [
            {
                "promotion_id": "promotion-1",
                "run_id": "run-1",
                "question_id": "question-1",
                "project_id": PROJECT_ID,
                "target_runtime_entry_id": "entry-1",
                "target_fact_id": "fact-1",
                "question": "New question?",
                "status": "approved",
                "runtime_entry_id": "entry-1",
                "fact_id": "fact-1",
                "runtime_status": "active",
                "runtime_visibility": "published",
                "claim": "Claim",
                "possible_questions": ["Existing?"],
                "active_promoted_questions": [],
                "exclusion_scope": None,
                "embedding_text": "old text",
                "embedding_model_id": "model-1",
                "embedding_dimensions": 3,
                "current_embedding": "[0.1,0.2,0.3]",
                "active_revision_id": None,
            }
        ]


@pytest.mark.asyncio
async def test_repository_hydration_rejects_noncanonical_dimensions() -> None:
    repository = PostgresWorkbenchRagEvalRepository(InvalidDimensionsConnection())

    with pytest.raises(WorkbenchRagEvalPromotionConflictError) as error:
        await repository.load_promotion_application_group(
            project_id=PROJECT_ID,
            promotion_ids=("promotion-1",),
            target_runtime_entry_id="entry-1",
            embedding_model_id="model-1",
        )

    assert error.value.code is (
        WorkbenchRagEvalPromotionConflictCode.STALE_RUNTIME_SNAPSHOT
    )


def test_revision_migration_fixes_dimensions_at_384() -> None:
    from pathlib import Path

    migration = Path(
        "migrations/128_create_workbench_rag_eval_embedding_revisions.sql"
    ).read_text(encoding="utf-8")

    assert "previous_embedding vector(384) NOT NULL" in migration
    assert "new_embedding vector(384) NOT NULL" in migration
    assert "CHECK (embedding_dimensions = 384)" in migration
    assert "CHECK (embedding_dimensions > 0)" not in migration
