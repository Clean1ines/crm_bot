from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime

import pytest

from src.contexts.artifact_runtime.application.ports.artifact_unit_of_work_port import (
    ArtifactEvent,
)
from src.contexts.artifact_runtime.application.use_cases.persist_artifact import (
    PersistArtifact,
)
from src.contexts.artifact_runtime.domain.entities.pipeline_artifact import (
    PipelineArtifact,
)
from src.contexts.artifact_runtime.domain.value_objects.artifact_kind import (
    ArtifactKind,
)
from src.contexts.artifact_runtime.domain.value_objects.artifact_ref import (
    ArtifactRef,
)
from src.contexts.execution_runtime.application.ports.work_item_attempt_dispatch_read_repository_port import (
    WorkItemAttemptDispatchForExecution,
)
from src.contexts.execution_runtime.domain.value_objects.lease_token import LeaseToken
from src.contexts.llm_runtime.application.ports.llm_dispatch_executor_port import (
    LlmDispatchExecutionResult,
    LlmDispatchExecutionStatus,
)
from src.contexts.llm_runtime.application.results.llm_dispatch_output_artifact_payload import (
    LlmDispatchOutputArtifactPayload,
)
from src.interfaces.composition.persist_successful_llm_dispatch_artifacts import (
    PersistSuccessfulLlmDispatchArtifacts,
    PersistSuccessfulLlmDispatchArtifactsCommand,
)


@dataclass(slots=True)
class FakeArtifactUnitOfWork:
    saved_artifacts: list[PipelineArtifact] = field(default_factory=list)
    appended_events: list[ArtifactEvent] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)
    committed: bool = False
    rolled_back: bool = False

    async def save_artifact(self, artifact: PipelineArtifact) -> None:
        self.actions.append("save_artifact")
        self.saved_artifacts.append(artifact)

    async def append_event(self, event: ArtifactEvent) -> None:
        self.actions.append("append_event")
        self.appended_events.append(event)

    async def commit(self) -> None:
        self.actions.append("commit")
        self.committed = True

    async def rollback(self) -> None:
        self.actions.append("rollback")
        self.rolled_back = True


def _created_at() -> datetime:
    return datetime(2026, 6, 11, 12, 2, tzinfo=UTC)


def _finished_at() -> datetime:
    return datetime(2026, 6, 11, 12, 1, tzinfo=UTC)


def _dispatch_payload() -> dict[str, object]:
    return {
        "work_item_id": "work-1",
        "schedule_payload": {
            "provider_messages": (
                {
                    "role": "user",
                    "content": "Extract facts",
                },
            ),
            "prompt_a_provenance": {
                "workflow_run_id": "run-1",
                "stage_run_id": "claim_builder_section_extraction",
                "source_unit_ref": "source-unit-1",
                "work_item_id": "work-1",
                "prompt_id": "faq_claim_observations",
                "prompt_version": "v1",
            },
        },
        "llm_allocation": {
            "slot_index": 0,
        },
        "llm_execution_settings": {
            "reasoning_enabled": False,
        },
    }


def _dispatch() -> WorkItemAttemptDispatchForExecution:
    return WorkItemAttemptDispatchForExecution(
        attempt_id="attempt-1",
        work_item_id="work-1",
        attempt_number=2,
        lease_token=LeaseToken("lease-token-1"),
        worker_ref="worker-1",
        dispatch_payload=_dispatch_payload(),
        started_at=datetime(2026, 6, 11, 12, 0, tzinfo=UTC),
    )


def _successful_result(
    *,
    output_payload: dict[str, object] | None = None,
) -> LlmDispatchExecutionResult:
    return LlmDispatchExecutionResult(
        status=LlmDispatchExecutionStatus.SUCCEEDED,
        finished_at=_finished_at(),
        output_payload=output_payload
        if output_payload is not None
        else {
            "raw_text": '{"ok": true}',
            "usage": {
                "input_tokens": 7,
                "output_tokens": 11,
                "total_tokens": 18,
            },
        },
    )


def _runner(
    unit_of_work: FakeArtifactUnitOfWork,
) -> PersistSuccessfulLlmDispatchArtifacts:
    return PersistSuccessfulLlmDispatchArtifacts(
        persist_artifact=PersistArtifact(unit_of_work=unit_of_work),
    )


@pytest.mark.asyncio
async def test_successful_llm_dispatch_output_is_persisted_as_artifact() -> None:
    unit_of_work = FakeArtifactUnitOfWork()

    result = await _runner(unit_of_work).execute(
        PersistSuccessfulLlmDispatchArtifactsCommand(
            dispatch=_dispatch(),
            llm_result=_successful_result(),
            created_at=_created_at(),
        ),
    )

    assert result.artifacts == (ArtifactRef("llm-dispatch-output:attempt-1"),)
    assert len(unit_of_work.saved_artifacts) == 1
    artifact = unit_of_work.saved_artifacts[0]
    assert artifact.artifact_ref == ArtifactRef("llm-dispatch-output:attempt-1")
    assert artifact.artifact_kind == ArtifactKind("llm_dispatch_output")
    assert artifact.created_at == _created_at()
    assert artifact.updated_at == _created_at()
    assert unit_of_work.committed
    assert not unit_of_work.rolled_back


@pytest.mark.asyncio
async def test_artifact_payload_includes_attempt_work_item_dispatch_and_output_metadata() -> (
    None
):
    unit_of_work = FakeArtifactUnitOfWork()

    await _runner(unit_of_work).execute(
        PersistSuccessfulLlmDispatchArtifactsCommand(
            dispatch=_dispatch(),
            llm_result=_successful_result(output_payload={"raw_text": "{}"}),
            created_at=_created_at(),
        ),
    )

    payload = _plain_json_value(unit_of_work.saved_artifacts[0].payload.value)
    parsed_payload = LlmDispatchOutputArtifactPayload.from_mapping(
        unit_of_work.saved_artifacts[0].payload.value,
    )
    assert parsed_payload.raw_text() == "{}"
    assert parsed_payload.prompt_a_provenance_seed()["prompt_id"] == (
        "faq_claim_observations"
    )

    assert payload == {
        "attempt_id": "attempt-1",
        "work_item_id": "work-1",
        "attempt_number": 2,
        "worker_ref": "worker-1",
        "dispatch_payload": {
            "work_item_id": "work-1",
            "schedule_payload": {
                "provider_messages": [
                    {
                        "role": "user",
                        "content": "Extract facts",
                    },
                ],
                "prompt_a_provenance": {
                    "workflow_run_id": "run-1",
                    "stage_run_id": "claim_builder_section_extraction",
                    "source_unit_ref": "source-unit-1",
                    "work_item_id": "work-1",
                    "prompt_id": "faq_claim_observations",
                    "prompt_version": "v1",
                },
            },
            "llm_allocation": {
                "slot_index": 0,
            },
            "llm_execution_settings": {
                "reasoning_enabled": False,
            },
        },
        "output_payload": {"raw_text": "{}"},
        "finished_at": _finished_at().isoformat(),
    }


@pytest.mark.asyncio
async def test_non_success_result_rejected() -> None:
    unit_of_work = FakeArtifactUnitOfWork()

    with pytest.raises(ValueError, match="succeeded"):
        await _runner(unit_of_work).execute(
            PersistSuccessfulLlmDispatchArtifactsCommand(
                dispatch=_dispatch(),
                llm_result=LlmDispatchExecutionResult(
                    status=LlmDispatchExecutionStatus.TERMINAL_FAILED,
                    finished_at=_finished_at(),
                    error_kind="invalid_dispatch_payload",
                ),
                created_at=_created_at(),
            ),
        )

    assert unit_of_work.saved_artifacts == []


@pytest.mark.asyncio
async def test_success_without_output_payload_rejected() -> None:
    unit_of_work = FakeArtifactUnitOfWork()

    with pytest.raises(ValueError, match="output_payload"):
        await _runner(unit_of_work).execute(
            PersistSuccessfulLlmDispatchArtifactsCommand(
                dispatch=_dispatch(),
                llm_result=LlmDispatchExecutionResult(
                    status=LlmDispatchExecutionStatus.SUCCEEDED,
                    finished_at=_finished_at(),
                    output_payload={},
                ),
                created_at=_created_at(),
            ),
        )

    assert unit_of_work.saved_artifacts == []


@pytest.mark.asyncio
async def test_naive_created_at_rejected() -> None:
    unit_of_work = FakeArtifactUnitOfWork()

    with pytest.raises(ValueError, match="created_at"):
        await _runner(unit_of_work).execute(
            PersistSuccessfulLlmDispatchArtifactsCommand(
                dispatch=_dispatch(),
                llm_result=_successful_result(),
                created_at=datetime(2026, 6, 11, 12, 2),
            ),
        )

    assert unit_of_work.saved_artifacts == []


def _plain_json_value(value: object) -> object:
    if isinstance(value, Mapping):
        return {str(key): _plain_json_value(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [_plain_json_value(item) for item in value]
    return value


def test_composition_does_not_import_disallowed_semantic_or_provider_paths() -> None:
    from pathlib import Path

    source = Path(
        "src/interfaces/composition/persist_successful_llm_dispatch_artifacts.py",
    ).read_text(encoding="utf-8")

    forbidden = (
        "knowledge_workbench",
        "draft_claim",
        "claim",
        "Prompt",
        "GroqDispatchExecutor",
        "GroqProviderAdapter",
        "LlmProviderPort",
        "ExecuteLlmTask",
        "ExecuteAndRecordLlmTask",
        "RecordWorkItemAttemptOutcome",
    )
    for marker in forbidden:
        assert marker not in source
