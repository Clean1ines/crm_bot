from __future__ import annotations

import sys
from datetime import datetime, timezone
from types import ModuleType

import pytest

from src.contexts.knowledge_workbench.rag_eval.application.errors.workbench_rag_eval_promotion_application_errors import (
    WorkbenchRagEvalPromotionConflictCode,
    WorkbenchRagEvalPromotionConflictError,
)
from src.contexts.knowledge_workbench.rag_eval.application.models.workbench_rag_eval_embedding_revision import (
    WorkbenchRagEvalEmbeddingRevisionAvailableActions,
    WorkbenchRagEvalEmbeddingRevisionReadModel,
    WorkbenchRagEvalEmbeddingRevisionStatus,
    WorkbenchRagEvalPromotionApplicationError,
    WorkbenchRagEvalPromotionApplicationResult,
    WorkbenchRagEvalPromotionRevisionResult,
)
from tests.interfaces.http.test_workbench_rag_eval import _client


NOW = datetime(2026, 7, 13, 12, 0, tzinfo=timezone.utc)
PROJECT_ID = "11111111-1111-1111-1111-111111111111"


class FakeRevisionApplyUseCase:
    async def execute(self, *, project_id: str, promotion_id: str, applied_at):
        assert project_id == PROJECT_ID
        assert promotion_id == "promotion-1"
        assert applied_at.tzinfo is not None
        revision = WorkbenchRagEvalPromotionRevisionResult(
            revision_id="revision-1",
            runtime_entry_id="entry-1",
            source_rag_eval_run_id="run-1",
            status=WorkbenchRagEvalEmbeddingRevisionStatus.PENDING_VERIFICATION,
            promotion_ids=("promotion-1",),
            idempotent=False,
        )
        return WorkbenchRagEvalPromotionApplicationResult(
            requested_count=1,
            applied_count=1,
            skipped_count=0,
            embedding_recalculation_count=1,
            revisions=(revision,),
            errors=(),
        )


def test_single_apply_response_includes_pending_revision(monkeypatch) -> None:
    async def allow_access(**kwargs):
        del kwargs
        return None

    def fake_factory(**kwargs):
        assert "pool" in kwargs
        return FakeRevisionApplyUseCase()

    composition_module = ModuleType("src.interfaces.composition.workbench_rag_eval")
    setattr(
        composition_module,
        "make_apply_workbench_rag_eval_promotion",
        fake_factory,
    )
    monkeypatch.setitem(
        sys.modules,
        "src.interfaces.composition.workbench_rag_eval",
        composition_module,
    )
    monkeypatch.setattr(
        "src.interfaces.http.knowledge._require_project_access",
        allow_access,
    )

    response = _client().post(
        f"/api/projects/{PROJECT_ID}/knowledge/rag-eval/workbench/"
        "promotion-candidates/promotion-1/apply",
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["applied_count"] == 1
    assert payload["embedding_recalculation_count"] == 1
    assert payload["revisions"][0] == {
        "revision_id": "revision-1",
        "runtime_entry_id": "entry-1",
        "source_rag_eval_run_id": "run-1",
        "status": "pending_verification",
        "promotion_ids": ["promotion-1"],
        "idempotent": False,
    }
    assert payload["result"] == {
        key: value for key, value in payload.items() if key != "result"
    }


class FakeRevisionReadRepository:
    def __init__(self, pool):
        del pool

    async def get_run(self, *, run_id: str, project_id: str):
        assert run_id == "run-1"
        assert project_id == PROJECT_ID
        return object()

    async def list_embedding_revisions(
        self,
        *,
        project_id: str,
        source_rag_eval_run_id: str,
    ):
        assert project_id == PROJECT_ID
        assert source_rag_eval_run_id == "run-1"
        return (
            WorkbenchRagEvalEmbeddingRevisionReadModel(
                revision_id="revision-1",
                project_id=PROJECT_ID,
                runtime_entry_id="entry-1",
                source_rag_eval_run_id="run-1",
                promotion_ids=("promotion-1",),
                status=(WorkbenchRagEvalEmbeddingRevisionStatus.PENDING_VERIFICATION),
                previous_promoted_questions=("Existing?",),
                new_promoted_questions=("Existing?", "New?"),
                created_at=NOW,
                accepted_at=None,
                regression_failed_at=None,
                rolled_back_at=None,
                available_actions=WorkbenchRagEvalEmbeddingRevisionAvailableActions(
                    can_accept=True,
                    can_rollback=False,
                ),
            ),
        )


def test_revision_read_projection_omits_raw_vectors(monkeypatch) -> None:
    async def allow_access(**kwargs):
        del kwargs
        return None

    monkeypatch.setattr(
        "src.interfaces.http.knowledge._require_project_access",
        allow_access,
    )
    monkeypatch.setattr(
        "src.interfaces.http.knowledge.PostgresWorkbenchRagEvalRepository",
        FakeRevisionReadRepository,
    )

    response = _client().get(
        f"/api/projects/{PROJECT_ID}/knowledge/rag-eval/workbench/"
        "runs/run-1/embedding-revisions",
    )

    assert response.status_code == 200
    revision = response.json()["revisions"][0]
    assert revision["revision_id"] == "revision-1"
    assert revision["status"] == "pending_verification"
    assert revision["available_actions"] == {
        "can_accept": True,
        "can_rollback": False,
    }
    assert "previous_embedding" not in revision
    assert "new_embedding" not in revision


class FakeAcceptRevisionUseCase:
    async def execute(self, command):
        assert command.project_id == PROJECT_ID
        assert command.revision_id == "revision-1"
        assert command.now.tzinfo is not None
        return WorkbenchRagEvalEmbeddingRevisionReadModel(
            revision_id="revision-1",
            project_id=PROJECT_ID,
            runtime_entry_id="entry-1",
            source_rag_eval_run_id="run-1",
            promotion_ids=("promotion-1",),
            status=WorkbenchRagEvalEmbeddingRevisionStatus.ACCEPTED,
            previous_promoted_questions=("Existing?",),
            new_promoted_questions=("Existing?", "New?"),
            created_at=NOW,
            accepted_at=command.now,
            regression_failed_at=None,
            rolled_back_at=None,
        )


class FakeRollbackRevisionUseCase:
    async def execute(self, command):
        assert command.project_id == PROJECT_ID
        assert command.revision_id == "revision-1"
        assert command.now.tzinfo is not None
        return WorkbenchRagEvalEmbeddingRevisionReadModel(
            revision_id="revision-1",
            project_id=PROJECT_ID,
            runtime_entry_id="entry-1",
            source_rag_eval_run_id="run-1",
            promotion_ids=("promotion-1",),
            status=WorkbenchRagEvalEmbeddingRevisionStatus.ROLLED_BACK,
            previous_promoted_questions=("Existing?",),
            new_promoted_questions=("Existing?", "New?"),
            created_at=NOW,
            accepted_at=None,
            regression_failed_at=None,
            rolled_back_at=command.now,
        )


def test_accept_revision_endpoint_returns_revision_without_vectors(monkeypatch) -> None:
    async def allow_access(**kwargs):
        del kwargs
        return None

    def fake_factory(**kwargs):
        assert "pool" in kwargs
        return FakeAcceptRevisionUseCase()

    composition_module = ModuleType("src.interfaces.composition.workbench_rag_eval")
    setattr(
        composition_module,
        "make_accept_workbench_rag_eval_embedding_revision",
        fake_factory,
    )
    monkeypatch.setitem(
        sys.modules,
        "src.interfaces.composition.workbench_rag_eval",
        composition_module,
    )
    monkeypatch.setattr(
        "src.interfaces.http.knowledge._require_project_access",
        allow_access,
    )

    response = _client().post(
        f"/api/projects/{PROJECT_ID}/knowledge/rag-eval/workbench/"
        "embedding-revisions/revision-1/accept",
    )

    assert response.status_code == 200
    revision = response.json()["revision"]
    assert revision["status"] == "accepted"
    assert "previous_embedding" not in revision
    assert "new_embedding" not in revision


def test_rollback_revision_endpoint_returns_revision_without_vectors(
    monkeypatch,
) -> None:
    async def allow_access(**kwargs):
        del kwargs
        return None

    def fake_factory(**kwargs):
        assert "pool" in kwargs
        return FakeRollbackRevisionUseCase()

    composition_module = ModuleType("src.interfaces.composition.workbench_rag_eval")
    setattr(
        composition_module,
        "make_rollback_workbench_rag_eval_embedding_revision",
        fake_factory,
    )
    monkeypatch.setitem(
        sys.modules,
        "src.interfaces.composition.workbench_rag_eval",
        composition_module,
    )
    monkeypatch.setattr(
        "src.interfaces.http.knowledge._require_project_access",
        allow_access,
    )

    response = _client().post(
        f"/api/projects/{PROJECT_ID}/knowledge/rag-eval/workbench/"
        "embedding-revisions/revision-1/rollback",
    )

    assert response.status_code == 200
    revision = response.json()["revision"]
    assert revision["status"] == "rolled_back"
    assert "previous_embedding" not in revision
    assert "new_embedding" not in revision


class FakeConflictApplyUseCase:
    def __init__(self, code: WorkbenchRagEvalPromotionConflictCode) -> None:
        self.code = code

    async def execute(self, **kwargs):
        del kwargs
        raise WorkbenchRagEvalPromotionConflictError(
            self.code.value,
            code=self.code,
        )


@pytest.mark.parametrize(
    "code",
    (
        WorkbenchRagEvalPromotionConflictCode.APPLICATION_IN_PROGRESS,
        WorkbenchRagEvalPromotionConflictCode.CONFLICTING_ACTIVE_APPLICATION,
        WorkbenchRagEvalPromotionConflictCode.APPLICATION_LEASE_LOST,
    ),
)
def test_single_apply_expected_concurrency_conflicts_map_to_409(
    monkeypatch,
    code: WorkbenchRagEvalPromotionConflictCode,
) -> None:
    async def allow_access(**kwargs):
        del kwargs
        return None

    def fake_factory(**kwargs):
        del kwargs
        return FakeConflictApplyUseCase(code)

    composition_module = ModuleType("src.interfaces.composition.workbench_rag_eval")
    setattr(
        composition_module,
        "make_apply_workbench_rag_eval_promotion",
        fake_factory,
    )
    monkeypatch.setitem(
        sys.modules,
        "src.interfaces.composition.workbench_rag_eval",
        composition_module,
    )
    monkeypatch.setattr(
        "src.interfaces.http.knowledge._require_project_access",
        allow_access,
    )

    response = _client().post(
        f"/api/projects/{PROJECT_ID}/knowledge/rag-eval/workbench/"
        "promotion-candidates/promotion-1/apply",
    )

    assert response.status_code == 409
    assert response.json()["detail"] == code.value


class FakeBatchConflictApplyUseCase:
    def __init__(self, code: WorkbenchRagEvalPromotionConflictCode) -> None:
        self.code = code

    async def execute(self, **kwargs):
        del kwargs
        error = WorkbenchRagEvalPromotionApplicationError(
            code=self.code.value,
            message=self.code.value,
            promotion_ids=("promotion-1",),
            runtime_entry_id="entry-1",
        )
        return WorkbenchRagEvalPromotionApplicationResult(
            requested_count=1,
            applied_count=0,
            skipped_count=1,
            embedding_recalculation_count=0,
            revisions=(),
            errors=(error,),
        )


@pytest.mark.parametrize(
    "code",
    (
        WorkbenchRagEvalPromotionConflictCode.APPLICATION_IN_PROGRESS,
        WorkbenchRagEvalPromotionConflictCode.CONFLICTING_ACTIVE_APPLICATION,
        WorkbenchRagEvalPromotionConflictCode.APPLICATION_LEASE_LOST,
    ),
)
def test_batch_apply_expected_concurrency_conflicts_map_to_409(
    monkeypatch,
    code: WorkbenchRagEvalPromotionConflictCode,
) -> None:
    async def allow_access(**kwargs):
        del kwargs
        return None

    def fake_factory(**kwargs):
        del kwargs
        return FakeBatchConflictApplyUseCase(code)

    composition_module = ModuleType("src.interfaces.composition.workbench_rag_eval")
    setattr(
        composition_module,
        "make_apply_workbench_rag_eval_promotions_batch",
        fake_factory,
    )
    monkeypatch.setitem(
        sys.modules,
        "src.interfaces.composition.workbench_rag_eval",
        composition_module,
    )
    monkeypatch.setattr(
        "src.interfaces.http.knowledge._require_project_access",
        allow_access,
    )

    response = _client().post(
        f"/api/projects/{PROJECT_ID}/knowledge/rag-eval/workbench/"
        "promotion-candidates/apply-batch",
        json={
            "mode": "selected",
            "promotion_ids": ["promotion-1"],
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"] == code.value
