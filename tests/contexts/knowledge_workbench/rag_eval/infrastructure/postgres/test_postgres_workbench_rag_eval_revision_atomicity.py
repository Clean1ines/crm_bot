from __future__ import annotations

import copy
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone

import pytest

from src.contexts.knowledge_workbench.rag_eval.application.models.workbench_rag_eval import (
    WorkbenchRagEvalPromotionStatus,
)
from src.contexts.knowledge_workbench.rag_eval.application.models.workbench_rag_eval_embedding_revision import (
    WorkbenchRagEvalEmbeddingRevision,
    WorkbenchRagEvalEmbeddingRevisionStatus,
    WorkbenchRagEvalPromotionApplicationCandidate,
    WorkbenchRagEvalPromotionApplicationSnapshot,
    stable_runtime_snapshot_hash,
)
from src.contexts.knowledge_workbench.rag_eval.infrastructure.postgres.postgres_workbench_rag_eval_repository import (
    PostgresWorkbenchRagEvalRepository,
)


NOW = datetime(2026, 7, 13, 12, 0, tzinfo=timezone.utc)
PROJECT_ID = "11111111-1111-1111-1111-111111111111"


@dataclass(slots=True)
class DatabaseState:
    revision_ids: list[str] = field(default_factory=list)
    runtime_questions: tuple[str, ...] = ("Existing?",)
    runtime_embedding_text: str = "old text"
    runtime_embedding: tuple[float, ...] = (0.1, 0.2, 0.3)
    promotion_statuses: dict[str, str] = field(
        default_factory=lambda: {
            "promotion-1": "approved",
            "promotion-2": "approved",
        }
    )
    events: list[str] = field(default_factory=list)
    timeline: list[str] = field(default_factory=list)


@dataclass(slots=True)
class FakeTransaction:
    connection: "AtomicFakeConnection"
    before: DatabaseState | None = None

    async def __aenter__(self) -> object:
        self.before = copy.deepcopy(self.connection.state)
        return None

    async def __aexit__(
        self,
        exc_type: object,
        exc: object,
        traceback: object,
    ) -> bool | None:
        if exc_type is not None:
            assert self.before is not None
            self.connection.state = self.before
        return None


@dataclass(slots=True)
class AtomicFakeConnection:
    failure_step: str | None = None
    state: DatabaseState = field(default_factory=DatabaseState)
    execute_calls: list[str] = field(default_factory=list)

    def transaction(self) -> FakeTransaction:
        return FakeTransaction(self)

    async def fetch(
        self,
        query: str,
        *args: object,
    ) -> list[Mapping[str, object]]:
        if "WORKBENCH_RAG_EVAL_NEVER" in query:
            raise AssertionError("unexpected SQL")
        if "FROM knowledge_workbench_rag_eval_promoted_questions AS promotion" in query:
            return self._locked_rows()
        raise AssertionError(f"unexpected fetch SQL: {query}")

    async def fetchrow(
        self,
        query: str,
        *args: object,
    ) -> Mapping[str, object] | None:
        if "INSERT INTO workflow_runtime_outbox_events" in query:
            self._fail("event_append")
            event_type = str(args[1])
            self.state.events.append(event_type)
            return {"sequence_number": len(self.state.events)}
        if "FROM knowledge_workbench_rag_eval_embedding_revisions" in query:
            return None
        raise AssertionError(f"unexpected fetchrow SQL: {query}")

    async def execute(self, query: str, *args: object) -> object:
        self.execute_calls.append(query)
        if "pg_advisory_xact_lock" in query:
            return "SELECT 1"
        if "INSERT INTO knowledge_workbench_rag_eval_embedding_revisions" in query:
            self._fail("revision_insert")
            self.state.revision_ids.append(str(args[0]))
            return "INSERT 0 1"
        if "UPDATE knowledge_workbench_runtime_retrieval_entries" in query:
            self._fail("runtime_update")
            self.state.runtime_questions = (
                tuple(args[2])
                if not isinstance(args[2], str)
                else (
                    "Existing?",
                    "Question 1?",
                    "Question 2?",
                )
            )
            self.state.runtime_embedding_text = str(args[3])
            return "UPDATE 1"
        if (
            "DELETE FROM knowledge_workbench_runtime_retrieval_entry_embeddings"
            in query
        ):
            return "DELETE 1"
        if (
            "INSERT INTO knowledge_workbench_runtime_retrieval_entry_embeddings"
            in query
        ):
            vector = str(args[3]).strip("[]")
            self.state.runtime_embedding = tuple(
                float(item) for item in vector.split(",")
            )
            return "INSERT 0 1"
        if "UPDATE knowledge_workbench_rag_eval_promoted_questions" in query:
            self._fail("promotion_update")
            promotion_ids = tuple(args[1])
            for promotion_id in promotion_ids:
                self.state.promotion_statuses[str(promotion_id)] = "applied"
            return f"UPDATE {len(promotion_ids)}"
        if "UPDATE knowledge_workbench_rag_eval_runs" in query:
            return "UPDATE 1"
        if "INSERT INTO workflow_runtime_timeline_entries" in query:
            self._fail("event_append")
            self.state.timeline.append(str(args[2]))
            return "INSERT 0 1"
        if "pg_notify" in query:
            return "SELECT 1"
        raise AssertionError(f"unexpected execute SQL: {query}")

    def _fail(self, step: str) -> None:
        if self.failure_step == step:
            raise RuntimeError(f"injected {step}")

    def _locked_rows(self) -> list[Mapping[str, object]]:
        return [
            {
                "promotion_id": promotion_id,
                "run_id": "run-1",
                "question_id": f"question-{index}",
                "project_id": PROJECT_ID,
                "target_runtime_entry_id": "entry-1",
                "target_fact_id": "fact-1",
                "question": f"Question {index}?",
                "status": status,
                "runtime_entry_id": "entry-1",
                "fact_id": "fact-1",
                "runtime_status": "active",
                "runtime_visibility": "published",
                "claim": "Claim",
                "possible_questions": list(self.state.runtime_questions),
                "exclusion_scope": None,
                "embedding_text": self.state.runtime_embedding_text,
                "embedding_model_id": "model-1",
                "embedding_dimensions": 3,
                "current_embedding": str(list(self.state.runtime_embedding)),
                "active_revision_id": (
                    self.state.revision_ids[0] if self.state.revision_ids else None
                ),
            }
            for index, (promotion_id, status) in enumerate(
                sorted(self.state.promotion_statuses.items()),
                start=1,
            )
        ]


def _snapshot_and_revision() -> tuple[
    WorkbenchRagEvalPromotionApplicationSnapshot,
    WorkbenchRagEvalEmbeddingRevision,
]:
    candidates = (
        WorkbenchRagEvalPromotionApplicationCandidate(
            promotion_id="promotion-1",
            run_id="run-1",
            question_id="question-1",
            target_fact_id="fact-1",
            question="Question 1?",
            status=WorkbenchRagEvalPromotionStatus.APPROVED,
        ),
        WorkbenchRagEvalPromotionApplicationCandidate(
            promotion_id="promotion-2",
            run_id="run-1",
            question_id="question-2",
            target_fact_id="fact-1",
            question="Question 2?",
            status=WorkbenchRagEvalPromotionStatus.APPROVED,
        ),
    )
    old_embedding = (0.1, 0.2, 0.3)
    old_questions = ("Existing?",)
    old_text = "old text"
    old_hash = stable_runtime_snapshot_hash(
        possible_questions=old_questions,
        embedding_text=old_text,
        embedding=old_embedding,
        embedding_model_id="model-1",
        embedding_dimensions=3,
    )
    snapshot = WorkbenchRagEvalPromotionApplicationSnapshot(
        project_id=PROJECT_ID,
        runtime_entry_id="entry-1",
        fact_id="fact-1",
        runtime_status="active",
        runtime_visibility="published",
        claim="Claim",
        possible_questions=old_questions,
        exclusion_scope=None,
        embedding_text=old_text,
        embedding=old_embedding,
        embedding_model_id="model-1",
        embedding_dimensions=3,
        candidates=candidates,
        runtime_hash=old_hash,
        active_revision_id=None,
    )
    new_questions = ("Existing?", "Question 1?", "Question 2?")
    new_embedding = (0.4, 0.5, 0.6)
    new_text = "new text"
    new_hash = stable_runtime_snapshot_hash(
        possible_questions=new_questions,
        embedding_text=new_text,
        embedding=new_embedding,
        embedding_model_id="model-1",
        embedding_dimensions=3,
    )
    revision = WorkbenchRagEvalEmbeddingRevision(
        revision_id="revision-1",
        project_id=PROJECT_ID,
        runtime_entry_id="entry-1",
        source_rag_eval_run_id="run-1",
        promotion_ids=("promotion-1", "promotion-2"),
        status=WorkbenchRagEvalEmbeddingRevisionStatus.PENDING_VERIFICATION,
        previous_embedding_text=old_text,
        new_embedding_text=new_text,
        previous_embedding=old_embedding,
        new_embedding=new_embedding,
        previous_promoted_questions=old_questions,
        new_promoted_questions=new_questions,
        embedding_model_id="model-1",
        embedding_dimensions=3,
        previous_runtime_hash=old_hash,
        new_runtime_hash=new_hash,
        created_at=NOW,
        accepted_at=None,
        regression_failed_at=None,
        rolled_back_at=None,
    )
    return snapshot, revision


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure_step",
    [
        "revision_insert",
        "runtime_update",
        "promotion_update",
        "event_append",
    ],
)
async def test_group_transaction_rolls_back_every_partial_state(
    failure_step: str,
) -> None:
    connection = AtomicFakeConnection(failure_step=failure_step)
    before = copy.deepcopy(connection.state)
    snapshot, revision = _snapshot_and_revision()

    with pytest.raises(RuntimeError, match="injected"):
        await PostgresWorkbenchRagEvalRepository(
            connection
        ).persist_promotion_application_revision(
            snapshot=snapshot,
            revision=revision,
        )

    assert connection.state == before


@pytest.mark.asyncio
async def test_group_transaction_persists_revision_runtime_promotions_and_events() -> (
    None
):
    connection = AtomicFakeConnection()
    snapshot, revision = _snapshot_and_revision()

    persisted = await PostgresWorkbenchRagEvalRepository(
        connection
    ).persist_promotion_application_revision(
        snapshot=snapshot,
        revision=revision,
    )

    assert persisted.revision_id == "revision-1"
    assert connection.state.revision_ids == ["revision-1"]
    assert connection.state.runtime_questions == (
        "Existing?",
        "Question 1?",
        "Question 2?",
    )
    assert set(connection.state.promotion_statuses.values()) == {"applied"}
    assert connection.state.events == [
        "RAG_EVAL_PROMOTIONS_APPLIED",
        "RAG_EVAL_EMBEDDING_REVISION_CREATED",
    ]
    assert connection.state.timeline == connection.state.events


def test_repository_source_keeps_network_embedding_outside_transaction() -> None:
    from pathlib import Path

    source = Path(
        "src/contexts/knowledge_workbench/rag_eval/infrastructure/postgres/"
        "postgres_workbench_rag_eval_repository.py"
    ).read_text(encoding="utf-8")

    assert "embedding_generation_port" not in source
    assert "EmbeddingGenerationRequest" not in source
    assert "pg_advisory_xact_lock" in source
    assert "active PENDING_VERIFICATION revision already exists" in source
