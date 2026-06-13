from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
from typing import cast

from src.contexts.llm_runtime.application.ports.llm_dispatch_executor_port import (
    LlmDispatchExecutionInput,
    LlmDispatchExecutionResult,
    LlmDispatchExecutionStatus,
    LlmDispatchExecutorPort,
)
from src.infrastructure.db.repositories.user_repository import UserRepository
from src.interfaces.composition import (
    knowledge_extraction_after_upload_composition as composition,
)
from src.interfaces.composition.knowledge_extraction_after_upload_composition import (
    make_knowledge_extraction_workflow_after_upload,
)
from src.interfaces.composition.knowledge_extraction_workflow_after_upload import (
    RunKnowledgeExtractionWorkflowAfterUpload,
)
from src.interfaces.composition.prepare_llm_dispatch_batch import AsyncPool


class FakeLlmExecutor(LlmDispatchExecutorPort):
    async def execute_dispatch(
        self,
        execution_input: LlmDispatchExecutionInput,
    ) -> LlmDispatchExecutionResult:
        del execution_input
        return LlmDispatchExecutionResult(
            status=LlmDispatchExecutionStatus.SUCCEEDED,
            finished_at=datetime(2026, 6, 13, 12, 0, tzinfo=timezone.utc),
            output_payload={"raw_text": '{"claims":[]}'},
        )


def _pool() -> AsyncPool:
    return cast(AsyncPool, object())


def _user_repo() -> UserRepository:
    return cast(UserRepository, object())


def _project_repo() -> Mapping[str, object]:
    return {}


def test_factory_creates_after_upload_runner_without_llm_executor() -> None:
    runner = make_knowledge_extraction_workflow_after_upload(
        pool=_pool(),
        project_repo=_project_repo(),
        user_repo=_user_repo(),
    )

    assert isinstance(runner, RunKnowledgeExtractionWorkflowAfterUpload)
    assert runner._prepare_llm_dispatch_batch is None
    assert runner._execute_prepared_llm_dispatch_attempt is None
    assert runner._capacity_observation_repository is None


def test_factory_wires_prepare_llm_dispatch_batch_when_executor_is_provided() -> None:
    runner = make_knowledge_extraction_workflow_after_upload(
        pool=_pool(),
        project_repo=_project_repo(),
        user_repo=_user_repo(),
        llm_executor=FakeLlmExecutor(),
    )

    assert runner._prepare_llm_dispatch_batch is not None


def test_factory_wires_execute_prepared_llm_dispatch_attempt_when_executor_is_provided() -> (
    None
):
    llm_executor = FakeLlmExecutor()
    runner = make_knowledge_extraction_workflow_after_upload(
        pool=_pool(),
        project_repo=_project_repo(),
        user_repo=_user_repo(),
        llm_executor=llm_executor,
    )

    execute_attempt = runner._execute_prepared_llm_dispatch_attempt
    assert execute_attempt is not None
    assert execute_attempt.llm_executor is llm_executor
    assert runner._capacity_observation_repository is None


def test_factory_with_fake_executor_is_ready_to_dispatch_beyond_schedule() -> None:
    runner = make_knowledge_extraction_workflow_after_upload(
        pool=_pool(),
        project_repo=_project_repo(),
        user_repo=_user_repo(),
        llm_executor=FakeLlmExecutor(),
    )

    assert runner._prepare_llm_dispatch_batch is not None
    assert runner._execute_prepared_llm_dispatch_attempt is not None
    assert runner._claim_builder_output_validation_policy is not None


def test_factory_no_longer_contains_noop_capacity_observation_repository() -> None:
    noop_name = "_Noop" + "LlmAttemptCapacityObservationRepository"
    assert not hasattr(composition, noop_name)
