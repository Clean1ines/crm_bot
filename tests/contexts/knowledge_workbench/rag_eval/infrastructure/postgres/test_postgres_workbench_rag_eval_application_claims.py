from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import pytest

from src.contexts.knowledge_workbench.rag_eval.application.errors.workbench_rag_eval_promotion_application_errors import (
    WorkbenchRagEvalPromotionConflictCode,
    WorkbenchRagEvalPromotionConflictError,
)
from src.contexts.knowledge_workbench.rag_eval.application.models.workbench_rag_eval_embedding_revision import (
    WorkbenchRagEvalPromotionApplicationClaimDecisionCode,
    stable_promotion_application_key,
)
from src.contexts.knowledge_workbench.rag_eval.infrastructure.postgres.postgres_workbench_rag_eval_repository import (
    PostgresWorkbenchRagEvalRepository,
)


NOW = datetime(2026, 7, 13, 12, 0, tzinfo=timezone.utc)
PROJECT_ID = "11111111-1111-1111-1111-111111111111"
PROMOTION_IDS = ("promotion-1", "promotion-2")
PREVIOUS_HASH = "runtime-hash-1"
APPLICATION_KEY = stable_promotion_application_key(
    project_id=PROJECT_ID,
    runtime_entry_id="entry-1",
    source_rag_eval_run_id="run-1",
    promotion_ids=PROMOTION_IDS,
    previous_runtime_hash=PREVIOUS_HASH,
)


@dataclass(slots=True)
class NoopTransaction:
    async def __aenter__(self) -> object:
        return None

    async def __aexit__(
        self,
        exc_type: object,
        exc: object,
        traceback: object,
    ) -> bool | None:
        return None


@dataclass(slots=True)
class ClaimFakeConnection:
    claims: dict[str, dict[str, object]] = field(default_factory=dict)
    revisions: dict[str, dict[str, object]] = field(default_factory=dict)

    def transaction(self) -> NoopTransaction:
        return NoopTransaction()

    async def execute(self, query: str, *args: object) -> object:
        if "pg_advisory_xact_lock" in query:
            return "SELECT 1"
        raise AssertionError(f"unexpected execute SQL: {query}")

    async def fetch(self, query: str, *args: object) -> list[Mapping[str, object]]:
        raise AssertionError(f"unexpected fetch SQL: {query}")

    async def fetchrow(
        self,
        query: str,
        *args: object,
    ) -> Mapping[str, object] | None:
        normalized = " ".join(query.split())
        if (
            "FROM knowledge_workbench_rag_eval_embedding_revisions" in normalized
            and "WHERE application_key = $1" in normalized
        ):
            application_key = str(args[0])
            for row in self.revisions.values():
                if row["application_key"] == application_key:
                    return dict(row)
            return None
        if (
            "FROM knowledge_workbench_rag_eval_embedding_revisions" in normalized
            and "WHERE revision_id = $1" in normalized
        ):
            row = self.revisions.get(str(args[0]))
            return dict(row) if row is not None else None
        if (
            "FROM knowledge_workbench_rag_eval_promotion_application_claims"
            in normalized
            and "WHERE application_key = $1" in normalized
            and normalized.startswith("SELECT")
        ):
            row = self.claims.get(str(args[0]))
            return dict(row) if row is not None else None
        if (
            "FROM knowledge_workbench_rag_eval_promotion_application_claims"
            in normalized
            and "WHERE project_id = $1::uuid" in normalized
            and "status = 'PREPARING'" in normalized
        ):
            project_id = str(args[0])
            runtime_entry_id = str(args[1])
            for row in self.claims.values():
                if (
                    row["project_id"] == project_id
                    and row["runtime_entry_id"] == runtime_entry_id
                    and row["status"] == "PREPARING"
                ):
                    return dict(row)
            return None
        if normalized.startswith(
            "INSERT INTO knowledge_workbench_rag_eval_promotion_application_claims"
        ):
            row = {
                "application_key": str(args[0]),
                "project_id": str(args[1]),
                "runtime_entry_id": str(args[2]),
                "source_rag_eval_run_id": str(args[3]),
                "promotion_ids": list(PROMOTION_IDS),
                "previous_runtime_hash": str(args[5]),
                "status": "PREPARING",
                "lease_owner": str(args[6]),
                "lease_expires_at": args[7],
                "revision_id": None,
                "created_at": args[8],
                "updated_at": args[8],
                "completed_at": None,
            }
            self._assert_unique_active(row)
            self.claims[str(args[0])] = row
            return dict(row)
        if normalized.startswith(
            "UPDATE knowledge_workbench_rag_eval_promotion_application_claims SET status = 'PREPARING'"
        ):
            row = self.claims.get(str(args[0]))
            if row is None:
                return None
            if row["lease_owner"] != str(args[4]) or row["status"] != str(args[5]):
                return None
            row.update(
                {
                    "status": "PREPARING",
                    "lease_owner": str(args[1]),
                    "lease_expires_at": args[2],
                    "revision_id": None,
                    "updated_at": args[3],
                    "completed_at": None,
                }
            )
            self._assert_unique_active(row, ignore_key=str(args[0]))
            return dict(row)
        if normalized.startswith(
            "UPDATE knowledge_workbench_rag_eval_promotion_application_claims SET status = 'COMPLETED'"
        ):
            key = str(args[0])
            row = self.claims.get(key)
            if row is None:
                return None
            if "lease_owner = $2" in normalized:
                if (
                    row["lease_owner"] != str(args[1])
                    or row["status"] != "PREPARING"
                    or row["lease_expires_at"] <= NOW
                ):
                    return None
                revision_id = str(args[2])
                completed_at = args[3]
            else:
                if row["lease_owner"] != str(args[3]):
                    return None
                revision_id = str(args[1])
                completed_at = args[2]
            row.update(
                {
                    "status": "COMPLETED",
                    "revision_id": revision_id,
                    "updated_at": completed_at,
                    "completed_at": completed_at,
                }
            )
            return {"application_key": key, **row}
        if normalized.startswith(
            "UPDATE knowledge_workbench_rag_eval_promotion_application_claims SET status = 'FAILED'"
        ):
            key = str(args[0])
            row = self.claims.get(key)
            if (
                row is None
                or row["lease_owner"] != str(args[1])
                or row["status"] != "PREPARING"
                or row["lease_expires_at"] <= NOW
            ):
                return None
            row.update(
                {
                    "status": "FAILED",
                    "lease_expires_at": args[2],
                    "revision_id": None,
                    "updated_at": args[2],
                    "completed_at": None,
                }
            )
            return {"application_key": key}
        if normalized.startswith("SELECT status, revision_id, lease_owner"):
            row = self.claims.get(str(args[0]))
            if row is None:
                return None
            return {
                "status": row["status"],
                "revision_id": row["revision_id"],
                "lease_owner": row["lease_owner"],
            }
        raise AssertionError(f"unexpected fetchrow SQL: {query}")

    def _assert_unique_active(
        self,
        candidate: Mapping[str, object],
        *,
        ignore_key: str | None = None,
    ) -> None:
        if candidate["status"] != "PREPARING":
            return
        for key, row in self.claims.items():
            if key == ignore_key:
                continue
            if (
                row["status"] == "PREPARING"
                and row["project_id"] == candidate["project_id"]
                and row["runtime_entry_id"] == candidate["runtime_entry_id"]
            ):
                raise AssertionError("unique active claim violated")


def _repository(connection: ClaimFakeConnection) -> PostgresWorkbenchRagEvalRepository:
    return PostgresWorkbenchRagEvalRepository(connection)


async def _claim(
    repository: PostgresWorkbenchRagEvalRepository,
    *,
    lease_owner: str = "owner-1",
    now: datetime = NOW,
    key: str = APPLICATION_KEY,
    promotion_ids: tuple[str, ...] = PROMOTION_IDS,
):
    return await repository.claim_promotion_application(
        application_key=key,
        project_id=PROJECT_ID,
        runtime_entry_id="entry-1",
        source_rag_eval_run_id="run-1",
        promotion_ids=promotion_ids,
        previous_runtime_hash=PREVIOUS_HASH,
        lease_owner=lease_owner,
        now=now,
        lease_expires_at=now + timedelta(minutes=5),
    )


@pytest.mark.asyncio
async def test_acquire_new_application_claim() -> None:
    connection = ClaimFakeConnection()
    decision = await _claim(_repository(connection))
    assert (
        decision.code is WorkbenchRagEvalPromotionApplicationClaimDecisionCode.ACQUIRED
    )
    assert decision.claim.status.value == "PREPARING"


@pytest.mark.asyncio
async def test_same_active_claim_returns_in_progress() -> None:
    connection = ClaimFakeConnection()
    repository = _repository(connection)
    await _claim(repository)
    decision = await _claim(repository, lease_owner="owner-2")
    assert decision.code is (
        WorkbenchRagEvalPromotionApplicationClaimDecisionCode.IN_PROGRESS
    )
    assert decision.claim.lease_owner == "owner-1"


@pytest.mark.asyncio
async def test_completed_same_claim_returns_existing_revision() -> None:
    connection = ClaimFakeConnection()
    repository = _repository(connection)
    acquired = await _claim(repository)
    revision_id = "revision-1"
    connection.revisions[revision_id] = {
        "application_key": APPLICATION_KEY,
        "revision_id": revision_id,
        "project_id": PROJECT_ID,
        "runtime_entry_id": "entry-1",
        "source_rag_eval_run_id": "run-1",
        "promotion_ids": list(PROMOTION_IDS),
        "status": "pending_verification",
        "previous_promoted_questions": ["Existing?"],
        "new_promoted_questions": ["Existing?", "New?"],
        "created_at": NOW,
        "accepted_at": None,
        "regression_failed_at": None,
        "rolled_back_at": None,
    }
    await repository.complete_promotion_application_claim(
        application_key=APPLICATION_KEY,
        lease_owner=acquired.claim.lease_owner,
        revision_id=revision_id,
        completed_at=NOW,
    )
    decision = await _claim(repository, lease_owner="owner-2", now=NOW)
    assert decision.code is (
        WorkbenchRagEvalPromotionApplicationClaimDecisionCode.ALREADY_COMPLETED
    )
    assert decision.revision is not None
    assert decision.revision.revision_id == revision_id


@pytest.mark.asyncio
async def test_expired_lease_is_recovered() -> None:
    connection = ClaimFakeConnection()
    repository = _repository(connection)
    acquired = await _claim(repository, now=NOW - timedelta(minutes=10))
    assert acquired.claim.lease_expires_at < NOW
    recovered = await _claim(repository, lease_owner="owner-2", now=NOW)
    assert recovered.code is (
        WorkbenchRagEvalPromotionApplicationClaimDecisionCode.RECOVERED_EXPIRED_LEASE
    )
    assert recovered.claim.lease_owner == "owner-2"


@pytest.mark.asyncio
async def test_conflicting_group_for_same_runtime_returns_conflict_decision() -> None:
    connection = ClaimFakeConnection()
    repository = _repository(connection)
    await _claim(repository)
    other_ids = ("promotion-3",)
    other_key = stable_promotion_application_key(
        project_id=PROJECT_ID,
        runtime_entry_id="entry-1",
        source_rag_eval_run_id="run-1",
        promotion_ids=other_ids,
        previous_runtime_hash=PREVIOUS_HASH,
    )
    decision = await _claim(
        repository,
        key=other_key,
        promotion_ids=other_ids,
        lease_owner="owner-2",
    )
    assert decision.code is (
        WorkbenchRagEvalPromotionApplicationClaimDecisionCode.CONFLICTING_ACTIVE_GROUP
    )


@pytest.mark.asyncio
async def test_stale_owner_cannot_complete_or_fail_recovered_claim() -> None:
    connection = ClaimFakeConnection()
    repository = _repository(connection)
    await _claim(repository, lease_owner="owner-1", now=NOW - timedelta(minutes=10))
    await _claim(repository, lease_owner="owner-2", now=NOW)

    with pytest.raises(WorkbenchRagEvalPromotionConflictError) as complete_error:
        await repository.complete_promotion_application_claim(
            application_key=APPLICATION_KEY,
            lease_owner="owner-1",
            revision_id="revision-1",
            completed_at=NOW,
        )
    assert complete_error.value.code is (
        WorkbenchRagEvalPromotionConflictCode.APPLICATION_LEASE_LOST
    )

    with pytest.raises(WorkbenchRagEvalPromotionConflictError) as fail_error:
        await repository.fail_promotion_application_claim(
            application_key=APPLICATION_KEY,
            lease_owner="owner-1",
            failed_at=NOW,
        )
    assert fail_error.value.code is (
        WorkbenchRagEvalPromotionConflictCode.APPLICATION_LEASE_LOST
    )


@pytest.mark.asyncio
async def test_stale_owner_cannot_idempotently_complete_recovered_owner_revision() -> (
    None
):
    connection = ClaimFakeConnection()
    repository = _repository(connection)
    await _claim(repository, lease_owner="owner-1", now=NOW - timedelta(minutes=10))
    recovered = await _claim(repository, lease_owner="owner-2", now=NOW)

    revision_id = "revision-1"
    connection.revisions[revision_id] = {
        "application_key": APPLICATION_KEY,
        "revision_id": revision_id,
        "project_id": PROJECT_ID,
        "runtime_entry_id": "entry-1",
        "source_rag_eval_run_id": "run-1",
        "promotion_ids": list(PROMOTION_IDS),
        "status": "pending_verification",
        "previous_promoted_questions": ["Existing?"],
        "new_promoted_questions": ["Existing?", "New?"],
        "created_at": NOW,
        "accepted_at": None,
        "regression_failed_at": None,
        "rolled_back_at": None,
    }
    await repository.complete_promotion_application_claim(
        application_key=APPLICATION_KEY,
        lease_owner=recovered.claim.lease_owner,
        revision_id=revision_id,
        completed_at=NOW,
    )

    with pytest.raises(WorkbenchRagEvalPromotionConflictError) as exc_info:
        await repository.complete_promotion_application_claim(
            application_key=APPLICATION_KEY,
            lease_owner="owner-1",
            revision_id=revision_id,
            completed_at=NOW,
        )
    assert exc_info.value.code is (
        WorkbenchRagEvalPromotionConflictCode.APPLICATION_LEASE_LOST
    )


@pytest.mark.asyncio
async def test_failed_same_claim_can_be_acquired_again() -> None:
    connection = ClaimFakeConnection()
    repository = _repository(connection)
    await _claim(repository, lease_owner="owner-1")
    await repository.fail_promotion_application_claim(
        application_key=APPLICATION_KEY,
        lease_owner="owner-1",
        failed_at=NOW,
    )
    decision = await _claim(repository, lease_owner="owner-2", now=NOW)
    assert (
        decision.code is WorkbenchRagEvalPromotionApplicationClaimDecisionCode.ACQUIRED
    )
    assert decision.claim.lease_owner == "owner-2"


def test_migration_enforces_unique_active_claim_and_canonical_statuses() -> None:
    from pathlib import Path

    migration = Path(
        "migrations/128_create_workbench_rag_eval_embedding_revisions.sql"
    ).read_text(encoding="utf-8")
    assert "knowledge_workbench_rag_eval_promotion_application_claims" in migration
    assert "status IN ('PREPARING', 'COMPLETED', 'FAILED')" in migration
    assert "WHERE status = 'PREPARING'" in migration
    assert "project_id,\n        runtime_entry_id" in migration
