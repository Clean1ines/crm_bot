from __future__ import annotations

import copy
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import pytest

from src.contexts.knowledge_workbench.rag_eval.application.models.workbench_rag_eval import (
    WorkbenchRagEvalPromotionStatus,
)
from src.contexts.knowledge_workbench.rag_eval.application.models.workbench_rag_eval_embedding_revision import (
    WORKBENCH_RUNTIME_EMBEDDING_DIMENSIONS,
    WorkbenchRagEvalEmbeddingRevision,
    WorkbenchRagEvalEmbeddingRevisionStatus,
    WorkbenchRagEvalPromotionApplicationCandidate,
    WorkbenchRagEvalPromotionApplicationSnapshot,
    stable_promotion_application_key,
    stable_runtime_snapshot_hash,
)
from src.contexts.knowledge_workbench.rag_eval.infrastructure.postgres.postgres_workbench_rag_eval_repository import (
    PostgresWorkbenchRagEvalRepository,
)


NOW = datetime(2026, 7, 13, 12, 0, tzinfo=timezone.utc)
PROJECT_ID = "11111111-1111-1111-1111-111111111111"
VECTOR_384 = (0.1,) * WORKBENCH_RUNTIME_EMBEDDING_DIMENSIONS
NEW_VECTOR_384 = (0.4,) * WORKBENCH_RUNTIME_EMBEDDING_DIMENSIONS
LEASE_OWNER = "lease-owner-1"


@dataclass(slots=True)
class DatabaseState:
    revision_ids: list[str] = field(default_factory=list)
    runtime_questions: tuple[str, ...] = ("Existing?",)
    runtime_embedding_text: str = "old text"
    runtime_embedding: tuple[float, ...] = VECTOR_384
    promotion_statuses: dict[str, str] = field(
        default_factory=lambda: {
            "promotion-1": "approved",
            "promotion-2": "approved",
        }
    )
    events: list[str] = field(default_factory=list)
    timeline: list[str] = field(default_factory=list)
    application_key: str = ""
    previous_runtime_hash: str = ""
    claim_status: str = "PREPARING"
    claim_revision_id: str | None = None
    claim_completed_at: datetime | None = None


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
        if "FROM knowledge_workbench_rag_eval_promoted_questions AS promotion" in query:
            return self._locked_rows()
        raise AssertionError(f"unexpected fetch SQL: {query}")

    async def fetchrow(
        self,
        query: str,
        *args: object,
    ) -> Mapping[str, object] | None:
        if "promotion_application_claims" in query and "FOR UPDATE" in query:
            return {
                "application_key": self.state.application_key,
                "project_id": PROJECT_ID,
                "runtime_entry_id": "entry-1",
                "source_rag_eval_run_id": "run-1",
                "promotion_ids": ["promotion-1", "promotion-2"],
                "previous_runtime_hash": self.state.previous_runtime_hash,
                "status": self.state.claim_status,
                "lease_owner": LEASE_OWNER,
                "lease_expires_at": NOW + timedelta(minutes=5),
                "revision_id": self.state.claim_revision_id,
                "created_at": NOW,
                "updated_at": self.state.claim_completed_at or NOW,
                "completed_at": self.state.claim_completed_at,
                "lease_is_active": True,
            }
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
                "Existing?",
                "Question 1?",
                "Question 2?",
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
            assert args[2] == WORKBENCH_RUNTIME_EMBEDDING_DIMENSIONS
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
        if "INSERT INTO workflow_runtime_command_log" in query:
            assert str(args[1]) == "RunRagEvalPostPromotionVerification"
            assert str(args[3]).startswith("rag-eval-post-promotion-verification:")
            return "INSERT 0 1"
        if (
            "UPDATE knowledge_workbench_rag_eval_promotion_application_claims" in query
            and "status = 'COMPLETED'" in query
        ):
            self._fail("claim_completion")
            assert str(args[0]) == self.state.application_key
            assert str(args[1]) == LEASE_OWNER
            self.state.claim_status = "COMPLETED"
            self.state.claim_revision_id = str(args[2])
            self.state.claim_completed_at = args[3]
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
                "active_promoted_questions": [],
                "exclusion_scope": None,
                "embedding_text": self.state.runtime_embedding_text,
                "embedding_model_id": "model-1",
                "embedding_dimensions": WORKBENCH_RUNTIME_EMBEDDING_DIMENSIONS,
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
    str,
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
    old_questions = ("Existing?",)
    old_text = "old text"
    old_hash = stable_runtime_snapshot_hash(
        possible_questions=old_questions,
        embedding_text=old_text,
        embedding=VECTOR_384,
        embedding_model_id="model-1",
        embedding_dimensions=WORKBENCH_RUNTIME_EMBEDDING_DIMENSIONS,
    )
    snapshot = WorkbenchRagEvalPromotionApplicationSnapshot(
        project_id=PROJECT_ID,
        runtime_entry_id="entry-1",
        fact_id="fact-1",
        runtime_status="active",
        runtime_visibility="published",
        claim="Claim",
        possible_questions=old_questions,
        active_promoted_questions=(),
        exclusion_scope=None,
        embedding_text=old_text,
        embedding=VECTOR_384,
        embedding_model_id="model-1",
        embedding_dimensions=WORKBENCH_RUNTIME_EMBEDDING_DIMENSIONS,
        candidates=candidates,
        runtime_hash=old_hash,
        active_revision_id=None,
    )
    new_questions = ("Existing?", "Question 1?", "Question 2?")
    new_text = "new text"
    new_hash = stable_runtime_snapshot_hash(
        possible_questions=new_questions,
        embedding_text=new_text,
        embedding=NEW_VECTOR_384,
        embedding_model_id="model-1",
        embedding_dimensions=WORKBENCH_RUNTIME_EMBEDDING_DIMENSIONS,
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
        previous_embedding=VECTOR_384,
        new_embedding=NEW_VECTOR_384,
        previous_promoted_questions=old_questions,
        new_promoted_questions=new_questions,
        embedding_model_id="model-1",
        embedding_dimensions=WORKBENCH_RUNTIME_EMBEDDING_DIMENSIONS,
        previous_runtime_hash=old_hash,
        new_runtime_hash=new_hash,
        created_at=NOW,
        accepted_at=None,
        regression_failed_at=None,
        rolled_back_at=None,
    )
    application_key = stable_promotion_application_key(
        project_id=PROJECT_ID,
        runtime_entry_id="entry-1",
        source_rag_eval_run_id="run-1",
        promotion_ids=revision.promotion_ids,
        previous_runtime_hash=old_hash,
    )
    return snapshot, revision, application_key


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure_step",
    [
        "revision_insert",
        "runtime_update",
        "promotion_update",
        "event_append",
        "claim_completion",
    ],
)
async def test_group_transaction_rolls_back_every_partial_state(
    failure_step: str,
) -> None:
    connection = AtomicFakeConnection(failure_step=failure_step)
    snapshot, revision, application_key = _snapshot_and_revision()
    connection.state.application_key = application_key
    connection.state.previous_runtime_hash = snapshot.runtime_hash
    before = copy.deepcopy(connection.state)

    with pytest.raises(RuntimeError, match="injected"):
        await PostgresWorkbenchRagEvalRepository(
            connection
        ).persist_promotion_application_revision(
            snapshot=snapshot,
            revision=revision,
            application_key=application_key,
            lease_owner=LEASE_OWNER,
        )

    assert connection.state == before


@pytest.mark.asyncio
async def test_group_transaction_persists_revision_runtime_promotions_and_events() -> (
    None
):
    connection = AtomicFakeConnection()
    snapshot, revision, application_key = _snapshot_and_revision()
    connection.state.application_key = application_key
    connection.state.previous_runtime_hash = snapshot.runtime_hash

    persisted = await PostgresWorkbenchRagEvalRepository(
        connection
    ).persist_promotion_application_revision(
        snapshot=snapshot,
        revision=revision,
        application_key=application_key,
        lease_owner=LEASE_OWNER,
    )

    assert persisted.revision_id == "revision-1"
    assert connection.state.revision_ids == ["revision-1"]
    assert connection.state.runtime_questions == (
        "Existing?",
        "Question 1?",
        "Question 2?",
    )
    assert len(connection.state.runtime_embedding) == 384
    assert set(connection.state.promotion_statuses.values()) == {"applied"}
    assert connection.state.events == [
        "RAG_EVAL_PROMOTIONS_APPLIED",
        "RAG_EVAL_EMBEDDING_REVISION_CREATED",
    ]
    assert connection.state.timeline == connection.state.events
    assert connection.state.claim_status == "COMPLETED"
    assert connection.state.claim_revision_id == "revision-1"
    assert connection.state.claim_completed_at == NOW


def test_repository_source_keeps_network_embedding_outside_transaction() -> None:
    from pathlib import Path

    source = Path(
        "src/contexts/knowledge_workbench/rag_eval/infrastructure/postgres/"
        "postgres_workbench_rag_eval_repository.py"
    ).read_text(encoding="utf-8")

    assert "embedding_generation_port" not in source
    assert "EmbeddingGenerationRequest" not in source
    assert "claim_promotion_application" in source
    assert "application_key" in source

    persist_start = source.index(
        "    async def persist_promotion_application_revision("
    )
    persist_end = source.index(
        "    async def list_embedding_revisions(",
        persist_start,
    )
    persist_source = source[persist_start:persist_end]

    assert "SET status = 'COMPLETED'" in persist_source
    assert "WHERE application_key = $1" in persist_source
    assert "AND lease_owner = $2" in persist_source
    assert "AND status = 'PREPARING'" in persist_source
    assert "AND lease_expires_at > CURRENT_TIMESTAMP" in persist_source
    assert 'operation="promotion application claim completion"' in persist_source
    assert "complete_promotion_application_claim" not in persist_source
