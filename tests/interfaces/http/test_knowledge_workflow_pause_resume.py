from __future__ import annotations

from dataclasses import dataclass, field

import pytest
from fastapi import HTTPException

from src.contexts.knowledge_workbench.application.sagas.pause_knowledge_extraction_workflow import (
    KnowledgeExtractionWorkflowPauseTerminalStateError,
    PauseKnowledgeExtractionWorkflowCommand,
    PauseKnowledgeExtractionWorkflowResult,
)
from src.contexts.knowledge_workbench.application.sagas.resume_knowledge_extraction_workflow import (
    KnowledgeExtractionWorkflowResumeNotPausedError,
    ResumeKnowledgeExtractionWorkflowCommand,
    ResumeKnowledgeExtractionWorkflowResult,
)
from src.interfaces.composition.knowledge_extraction_workflow_resume import (
    RunKnowledgeExtractionWorkflowResumeCommand,
    RunKnowledgeExtractionWorkflowResumeResult,
)
from src.interfaces.http import dependencies, knowledge


@dataclass(slots=True)
class FakeProjectRepository:
    access_checks: list[tuple[str, str]] = field(default_factory=list)

    async def project_exists(self, project_id: str) -> bool:
        return project_id == "project-1"

    async def user_has_project_role(
        self,
        project_id: str,
        user_id: str,
        allowed_roles: tuple[str, ...],
    ) -> bool:
        self.access_checks.append((project_id, user_id))
        return allowed_roles == ("owner", "admin", "manager")


@dataclass(slots=True)
class FakeUserRepository:
    async def is_platform_admin(self, user_id: str) -> bool:
        del user_id
        return False


@dataclass(slots=True)
class FakePauseRunner:
    commands: list[PauseKnowledgeExtractionWorkflowCommand] = field(
        default_factory=list,
    )

    async def execute(
        self,
        command: PauseKnowledgeExtractionWorkflowCommand,
    ) -> PauseKnowledgeExtractionWorkflowResult:
        self.commands.append(command)
        return PauseKnowledgeExtractionWorkflowResult(
            workflow_run_id=command.workflow_run_id,
            status="manually_paused",
            paused_at=command.occurred_at,
            already_paused=False,
        )


@dataclass(slots=True)
class FailingPauseRunner:
    error: Exception

    async def execute(
        self,
        command: PauseKnowledgeExtractionWorkflowCommand,
    ) -> PauseKnowledgeExtractionWorkflowResult:
        del command
        raise self.error


@dataclass(slots=True)
class FakeResumeTransitionRunner:
    commands: list[ResumeKnowledgeExtractionWorkflowCommand] = field(
        default_factory=list,
    )

    async def execute(
        self,
        command: ResumeKnowledgeExtractionWorkflowCommand,
    ) -> ResumeKnowledgeExtractionWorkflowResult:
        self.commands.append(command)
        return ResumeKnowledgeExtractionWorkflowResult(
            workflow_run_id=command.workflow_run_id,
            status="running",
            resumed_at=command.occurred_at,
            already_running=False,
        )


@dataclass(slots=True)
class FailingResumeTransitionRunner:
    error: Exception

    async def execute(
        self,
        command: ResumeKnowledgeExtractionWorkflowCommand,
    ) -> ResumeKnowledgeExtractionWorkflowResult:
        del command
        raise self.error


@dataclass(slots=True)
class FakeResumeDrainRunner:
    commands: list[RunKnowledgeExtractionWorkflowResumeCommand] = field(
        default_factory=list,
    )

    async def execute(
        self,
        command: RunKnowledgeExtractionWorkflowResumeCommand,
    ) -> RunKnowledgeExtractionWorkflowResumeResult:
        self.commands.append(command)
        return RunKnowledgeExtractionWorkflowResumeResult(
            workflow_run_id="workflow-1",
            source_document_ref="source-document:project-1:abc",
            drained_inspected_count=2,
            drained_dispatched_count=1,
            blocked_command_type=None,
            blocked_reason=None,
        )


@dataclass(slots=True)
class FakeLlmExecutor:
    pass


async def _fake_current_user_id(authorization: str | None) -> str:
    assert authorization == "Bearer test"
    return "owner-1"


@pytest.mark.asyncio
async def test_pause_endpoint_validates_access_and_calls_pause_composition(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(dependencies, "get_current_user_id", _fake_current_user_id)
    pause_runner = FakePauseRunner()

    def fake_pause_factory(*, pool: object) -> FakePauseRunner:
        assert pool == "pool"
        return pause_runner

    monkeypatch.setattr(
        knowledge,
        "make_pause_knowledge_extraction_workflow",
        fake_pause_factory,
    )

    project_repo = FakeProjectRepository()
    response = await knowledge.pause_knowledge_extraction_workflow(
        project_id="project-1",
        workflow_run_id="workflow-1",
        authorization="Bearer test",
        reason="manual_pause",
        pool="pool",
        project_repo=project_repo,
        user_repo=FakeUserRepository(),
    )

    assert project_repo.access_checks == [("project-1", "owner-1")]
    assert response["workflow_run_id"] == "workflow-1"
    assert response["status"] == "manually_paused"
    assert response["already_paused"] is False
    assert len(pause_runner.commands) == 1
    command = pause_runner.commands[0]
    assert command.workflow_run_id == "workflow-1"
    assert command.project_id == "project-1"
    assert command.actor_user_id == "owner-1"
    assert command.reason == "manual_pause"


@pytest.mark.asyncio
async def test_pause_endpoint_maps_terminal_state_to_409(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(dependencies, "get_current_user_id", _fake_current_user_id)

    def fake_pause_factory(*, pool: object) -> FailingPauseRunner:
        del pool
        return FailingPauseRunner(
            error=KnowledgeExtractionWorkflowPauseTerminalStateError("terminal"),
        )

    monkeypatch.setattr(
        knowledge,
        "make_pause_knowledge_extraction_workflow",
        fake_pause_factory,
    )

    with pytest.raises(HTTPException) as exc_info:
        await knowledge.pause_knowledge_extraction_workflow(
            project_id="project-1",
            workflow_run_id="workflow-1",
            authorization="Bearer test",
            reason="manual_pause",
            pool="pool",
            project_repo=FakeProjectRepository(),
            user_repo=FakeUserRepository(),
        )

    assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_resume_endpoint_unpauses_then_drains_existing_workflow(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(dependencies, "get_current_user_id", _fake_current_user_id)
    transition_runner = FakeResumeTransitionRunner()
    drain_runner = FakeResumeDrainRunner()
    llm_executor = FakeLlmExecutor()

    def fake_transition_factory(*, pool: object) -> FakeResumeTransitionRunner:
        assert pool == "pool"
        return transition_runner

    def fake_drain_factory(
        *,
        pool: object,
        llm_executor: object | None = None,
    ) -> FakeResumeDrainRunner:
        assert pool == "pool"
        assert llm_executor is llm_executor_ref
        return drain_runner

    llm_executor_ref = llm_executor

    monkeypatch.setattr(
        knowledge,
        "make_resume_knowledge_extraction_workflow_transition",
        fake_transition_factory,
    )
    monkeypatch.setattr(
        knowledge,
        "make_knowledge_extraction_workflow_resume",
        fake_drain_factory,
    )

    response = await knowledge.resume_knowledge_extraction_workflow(
        project_id="project-1",
        workflow_run_id="workflow-1",
        authorization="Bearer test",
        max_drain_commands=7,
        pool="pool",
        project_repo=FakeProjectRepository(),
        user_repo=FakeUserRepository(),
        llm_executor=llm_executor,
    )

    assert response["workflow_run_id"] == "workflow-1"
    assert response["status"] == "running"
    assert response["source_document_ref"] == "source-document:project-1:abc"
    assert response["drained_inspected_count"] == 2
    assert response["drained_dispatched_count"] == 1

    assert len(transition_runner.commands) == 1
    transition_command = transition_runner.commands[0]
    assert transition_command.workflow_run_id == "workflow-1"
    assert transition_command.project_id == "project-1"
    assert transition_command.actor_user_id == "owner-1"
    assert transition_command.max_drain_commands == 7

    assert len(drain_runner.commands) == 1
    drain_command = drain_runner.commands[0]
    assert drain_command.project_id == "project-1"
    assert drain_command.document_id == "workflow-1"
    assert drain_command.max_drain_commands == 7


@pytest.mark.asyncio
async def test_resume_endpoint_maps_not_paused_to_409(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(dependencies, "get_current_user_id", _fake_current_user_id)

    def fake_transition_factory(*, pool: object) -> FailingResumeTransitionRunner:
        del pool
        return FailingResumeTransitionRunner(
            error=KnowledgeExtractionWorkflowResumeNotPausedError("not paused"),
        )

    monkeypatch.setattr(
        knowledge,
        "make_resume_knowledge_extraction_workflow_transition",
        fake_transition_factory,
    )

    with pytest.raises(HTTPException) as exc_info:
        await knowledge.resume_knowledge_extraction_workflow(
            project_id="project-1",
            workflow_run_id="workflow-1",
            authorization="Bearer test",
            max_drain_commands=7,
            pool="pool",
            project_repo=FakeProjectRepository(),
            user_repo=FakeUserRepository(),
            llm_executor=FakeLlmExecutor(),
        )

    assert exc_info.value.status_code == 409
