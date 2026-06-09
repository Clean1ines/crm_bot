from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.contexts.artifact_runtime.domain.entities.pipeline_artifact import (
    PipelineArtifact,
)
from src.contexts.artifact_runtime.domain.events.artifact_events import ArtifactStored
from src.contexts.artifact_runtime.domain.value_objects.artifact_kind import (
    ArtifactKind,
)
from src.contexts.artifact_runtime.domain.value_objects.artifact_lineage import (
    ArtifactLineage,
)
from src.contexts.artifact_runtime.domain.value_objects.artifact_payload import (
    ArtifactPayload,
    JsonInputValue,
)
from src.contexts.artifact_runtime.domain.value_objects.artifact_ref import ArtifactRef
from src.contexts.artifact_runtime.domain.value_objects.artifact_status import (
    ArtifactStatus,
)
from src.contexts.artifact_runtime.domain.value_objects.artifact_visibility import (
    ArtifactVisibility,
)
from src.contexts.artifact_runtime.domain.value_objects.retention_policy import (
    RetentionPolicy,
)
from src.contexts.knowledge_workbench.extraction.application.policies.claim_extraction_prompt_a_artifact_factory import (
    PROMPT_A_PARSED_CLAIM_OBSERVATIONS_ARTIFACT_KIND,
)
from src.contexts.knowledge_workbench.extraction.application.process_managers.apply_draft_claim_observation_artifact import (
    ApplyDraftClaimObservationArtifactCommand,
    ApplyDraftClaimObservationArtifactResult,
)
from src.contexts.knowledge_workbench.extraction.application.process_managers.apply_draft_claim_observation_artifact_on_artifact_stored import (
    ApplyDraftClaimObservationArtifactOnArtifactStored,
    ApplyDraftClaimObservationArtifactOnArtifactStoredCommand,
)
from src.contexts.knowledge_workbench.extraction.domain.events.draft_claim_observation_events import (
    DraftClaimObservationsApplied,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.source_unit_ref import (
    SourceUnitRef,
)


PROCESS_MANAGER_FILE = (
    Path(__file__).resolve().parents[6]
    / "src/contexts/knowledge_workbench/extraction/application/process_managers/apply_draft_claim_observation_artifact_on_artifact_stored.py"
)


class FakeArtifactLoader:
    def __init__(self, artifact: PipelineArtifact | None) -> None:
        self.artifact = artifact
        self.loaded_refs: list[ArtifactRef] = []

    async def load_artifact(self, artifact_ref: ArtifactRef) -> PipelineArtifact | None:
        self.loaded_refs.append(artifact_ref)
        return self.artifact


class FakeApplyUseCase:
    def __init__(self) -> None:
        self.commands: list[ApplyDraftClaimObservationArtifactCommand] = []
        self.result = ApplyDraftClaimObservationArtifactResult(
            observations=(),
            provenance_candidates=(),
            event=DraftClaimObservationsApplied(
                artifact_ref=ArtifactRef("parsed-artifact-1"),
                source_unit_ref=SourceUnitRef("document-1.unit.0"),
                observation_count=0,
                occurred_at=_now(),
            ),
        )

    async def execute(
        self,
        command: ApplyDraftClaimObservationArtifactCommand,
    ) -> ApplyDraftClaimObservationArtifactResult:
        self.commands.append(command)
        return self.result


def _now() -> datetime:
    return datetime(2026, 6, 9, 12, 0, tzinfo=timezone.utc)


def _claim_payload() -> dict[str, JsonInputValue]:
    return {
        "claim": "Product turns documents into knowledge.",
        "granularity": "atomic",
        "possible_questions": ("What does the product do?",),
        "exclusion_scope": "Pricing is not covered.",
        "evidence_block": "turns documents into knowledge",
    }


def _prompt_a_parsed_payload() -> dict[str, JsonInputValue]:
    return {
        "workflow_run_id": "workflow-1",
        "stage_run_id": "stage-1",
        "source_unit_ref": "document-1.unit.0",
        "work_item_id": "work-item-1",
        "work_item_attempt_id": "work-attempt-1",
        "llm_task_id": "llm-task-1",
        "llm_attempt_id": "llm-attempt-1",
        "prompt_id": "prompt-a",
        "prompt_version": "v1",
        "raw_artifact_ref": "raw-artifact-1",
        "claims": (_claim_payload(),),
    }


def _artifact(
    *,
    artifact_kind: ArtifactKind = PROMPT_A_PARSED_CLAIM_OBSERVATIONS_ARTIFACT_KIND,
    payload: dict[str, JsonInputValue] | None = None,
    artifact_ref: ArtifactRef = ArtifactRef("parsed-artifact-1"),
    lineage: ArtifactLineage = ArtifactLineage(
        parent_refs=(ArtifactRef("raw-artifact-1"),)
    ),
    created_at: datetime | None = None,
    updated_at: datetime | None = None,
) -> PipelineArtifact:
    created = created_at or _now()
    return PipelineArtifact(
        artifact_ref=artifact_ref,
        artifact_kind=artifact_kind,
        payload=ArtifactPayload(payload or _prompt_a_parsed_payload()),
        status=ArtifactStatus.VALIDATED,
        visibility=ArtifactVisibility.INTERNAL,
        retention_policy=RetentionPolicy.temporary(),
        lineage=lineage,
        created_at=created,
        updated_at=updated_at or created,
    )


def _event() -> ArtifactStored:
    return ArtifactStored(
        artifact_ref=ArtifactRef("parsed-artifact-1"),
        occurred_at=_now(),
    )


@pytest.mark.asyncio
async def test_applies_prompt_a_parsed_artifact_from_artifact_stored_event() -> None:
    artifact = _artifact()
    loader = FakeArtifactLoader(artifact)
    fake_apply = FakeApplyUseCase()
    occurred_at = datetime(2026, 6, 9, 13, 0, tzinfo=timezone.utc)

    result = await ApplyDraftClaimObservationArtifactOnArtifactStored(
        artifact_loader=loader,
        apply_use_case=fake_apply,
    ).execute(
        ApplyDraftClaimObservationArtifactOnArtifactStoredCommand(
            event=_event(),
            occurred_at=occurred_at,
        )
    )

    assert loader.loaded_refs == [_event().artifact_ref]
    assert result.status == "applied"
    assert result.apply_result is fake_apply.result
    assert len(fake_apply.commands) == 1
    command = fake_apply.commands[0]
    assert command.parsed_artifact is artifact
    assert command.source_unit_ref == SourceUnitRef("document-1.unit.0")
    assert command.created_at == artifact.created_at
    assert command.occurred_at == occurred_at


@pytest.mark.asyncio
async def test_ignores_missing_artifact() -> None:
    loader = FakeArtifactLoader(None)
    fake_apply = FakeApplyUseCase()

    result = await ApplyDraftClaimObservationArtifactOnArtifactStored(
        artifact_loader=loader,
        apply_use_case=fake_apply,
    ).execute(
        ApplyDraftClaimObservationArtifactOnArtifactStoredCommand(
            event=_event(),
            occurred_at=_now(),
        )
    )

    assert result.status == "ignored_missing_artifact"
    assert fake_apply.commands == []


@pytest.mark.asyncio
async def test_ignores_non_prompt_a_parsed_artifact() -> None:
    loader = FakeArtifactLoader(
        _artifact(artifact_kind=ArtifactKind("knowledge_workbench.other.parsed"))
    )
    fake_apply = FakeApplyUseCase()

    result = await ApplyDraftClaimObservationArtifactOnArtifactStored(
        artifact_loader=loader,
        apply_use_case=fake_apply,
    ).execute(
        ApplyDraftClaimObservationArtifactOnArtifactStoredCommand(
            event=_event(),
            occurred_at=_now(),
        )
    )

    assert result.status == "ignored_non_prompt_a_parsed_artifact"
    assert fake_apply.commands == []


@pytest.mark.asyncio
async def test_ignores_invalid_prompt_a_provenance() -> None:
    payload = _prompt_a_parsed_payload()
    del payload["source_unit_ref"]
    loader = FakeArtifactLoader(_artifact(payload=payload))
    fake_apply = FakeApplyUseCase()

    result = await ApplyDraftClaimObservationArtifactOnArtifactStored(
        artifact_loader=loader,
        apply_use_case=fake_apply,
    ).execute(
        ApplyDraftClaimObservationArtifactOnArtifactStoredCommand(
            event=_event(),
            occurred_at=_now(),
        )
    )

    assert result.status == "ignored_invalid_prompt_a_provenance"
    assert fake_apply.commands == []


def test_command_requires_timezone_aware_occurred_at() -> None:
    with pytest.raises(ValueError, match="occurred_at must be timezone-aware"):
        ApplyDraftClaimObservationArtifactOnArtifactStoredCommand(
            event=_event(),
            occurred_at=datetime(2026, 6, 9, 12, 0),
        )


def test_handler_source_has_no_runtime_infrastructure_or_queue_wiring() -> None:
    text = PROCESS_MANAGER_FILE.read_text(encoding="utf-8")

    required_markers = (
        "class ArtifactLoaderPort",
        "class ApplyDraftClaimObservationArtifactOnArtifactStored",
        "ApplyDraftClaimObservationArtifactAsync",
        "ApplyDraftClaimObservationArtifactCommand",
        "ClaimExtractionArtifactProvenance.from_parsed_artifact_payload_fields",
        "PROMPT_A_PARSED_CLAIM_OBSERVATIONS_ARTIFACT_KIND",
        "await self._artifact_loader.load_artifact",
        "await self._apply_use_case.execute",
    )
    forbidden_markers = (
        "RunClaimExtractionStageAsync",
        "RecordClaimExtractionSuccess",
        "ProcessClaimExtractionWorkItem",
        "Postgres",
        "postgres",
        "asyncpg",
        "src.infrastructure",
        "src.contexts.execution_runtime",
        "src.contexts.llm_runtime",
        "src.contexts.artifact_runtime.infrastructure",
        "JobDispatcher",
        "worker_loop",
        "outbox_events",
        "published_at",
        "CLAIM_OBSERVATIONS_PERSISTED",
        "REGISTRY_APPLICATION",
        "frontend",
        "consolidation",
        "publication",
        "type: ignore",
    )

    missing = [marker for marker in required_markers if marker not in text]
    offenders = [marker for marker in forbidden_markers if marker in text]

    assert not missing, "\n".join(missing)
    assert not offenders, "\n".join(offenders)
