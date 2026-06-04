import pytest

from src.application.workbench_commands.publish_ready import (
    FaqWorkbenchPublishReadyService,
    PublishReadyCommand,
    PublishReadyRejectedError,
)
from src.domain.project_plane.knowledge_workbench import DomainInvariantError


class FakePublishReadyRepository:
    def __init__(self, snapshot_id: str | None = "snapshot-final-reconciled-1") -> None:
        self.snapshot_id = snapshot_id
        self.calls: list[dict[str, str]] = []

    async def publish_latest_reconciled_fact_registry_snapshot(
        self,
        *,
        project_id: str,
        document_id: str,
    ) -> str | None:
        self.calls.append(
            {
                "project_id": project_id,
                "document_id": document_id,
                "method": "publish_latest_reconciled_fact_registry_snapshot",
            }
        )
        return self.snapshot_id


@pytest.mark.asyncio
async def test_publish_ready_publishes_only_reconciled_fact_registry_snapshot() -> None:
    repository = FakePublishReadyRepository("snapshot-final-reconciled-1")

    result = await FaqWorkbenchPublishReadyService(repository).publish_ready(
        PublishReadyCommand(project_id="project-1", document_id="document-1")
    )

    assert result.project_id == "project-1"
    assert result.document_id == "document-1"
    assert result.published_snapshot_id == "snapshot-final-reconciled-1"
    assert result.published is True
    assert repository.calls == [
        {
            "project_id": "project-1",
            "document_id": "document-1",
            "method": "publish_latest_reconciled_fact_registry_snapshot",
        }
    ]


@pytest.mark.asyncio
async def test_publish_ready_rejects_when_no_reconciled_snapshot_exists() -> None:
    repository = FakePublishReadyRepository(None)

    with pytest.raises(
        PublishReadyRejectedError,
        match="no reconciled fact registry snapshot",
    ):
        await FaqWorkbenchPublishReadyService(repository).publish_ready(
            PublishReadyCommand(project_id="project-1", document_id="document-1")
        )


def test_publish_ready_command_requires_project_id() -> None:
    with pytest.raises(DomainInvariantError, match="project_id"):
        PublishReadyCommand(project_id="", document_id="document-1")


def test_publish_ready_command_requires_document_id() -> None:
    with pytest.raises(DomainInvariantError, match="document_id"):
        PublishReadyCommand(project_id="project-1", document_id="")


def test_publish_ready_command_does_not_use_surface_session_contract() -> None:
    source = "src/application/workbench_commands/publish_ready.py"
    text = __import__("pathlib").Path(source).read_text(encoding="utf-8")

    assert "publish_latest_reconciled_fact_registry_snapshot" in text
    assert "publish_latest_fact_registry_snapshot" not in text
    assert "published_surface_ids" not in text
    assert "surface_session" not in text
    assert "surface_id" not in text
