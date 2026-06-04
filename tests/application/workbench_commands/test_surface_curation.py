from __future__ import annotations

from dataclasses import dataclass, field
from collections.abc import Mapping

import pytest

from src.application.workbench_commands.surface_curation import (
    SurfaceCurationRejectedError,
    SurfaceCurationService,
)


@dataclass(slots=True)
class FakeRepository:
    calls: list[str] = field(default_factory=list)

    async def approve_surface(
        self,
        *,
        project_id: str,
        document_id: str,
        surface_id: str,
    ) -> Mapping[str, object]:
        self.calls.append(f"approve:{surface_id}")
        return {"surface_id": surface_id}

    async def reject_surface(
        self,
        *,
        project_id: str,
        document_id: str,
        surface_id: str,
        reason: str,
    ) -> Mapping[str, object]:
        self.calls.append(f"reject:{surface_id}:{reason}")
        return {"surface_id": surface_id, "reason": reason}

    async def edit_surface(
        self,
        *,
        project_id: str,
        document_id: str,
        surface_id: str,
        title: str | None,
        answer: str | None,
        short_answer: str | None,
        question_variants: tuple[str, ...] | None,
        retrieval_scope: str | None,
        exclusion_scope: str | None,
    ) -> Mapping[str, object]:
        self.calls.append(f"edit:{surface_id}:{answer}")
        return {"surface_id": surface_id, "answer": answer}

    async def merge_facts(
        self,
        *,
        project_id: str,
        document_id: str,
        target_fact_id: str,
        source_fact_ids: tuple[str, ...],
        reason: str,
    ) -> Mapping[str, object]:
        self.calls.append(f"merge:{target_fact_id}:{','.join(source_fact_ids)}")
        return {"fact_id": target_fact_id}

    async def delete_fact(
        self,
        *,
        project_id: str,
        document_id: str,
        fact_id: str,
        reason: str,
    ) -> Mapping[str, object]:
        self.calls.append(f"delete:{fact_id}:{reason}")
        return {"fact_id": fact_id}

    async def publish_selected_surfaces(
        self,
        *,
        project_id: str,
        document_id: str,
        surface_ids: tuple[str, ...],
    ) -> Mapping[str, object]:
        self.calls.append(f"publish:{','.join(surface_ids)}")
        return {"items": tuple({"surface_id": item} for item in surface_ids)}


@pytest.mark.asyncio
async def test_surface_curation_service_executes_all_mutation_commands() -> None:
    repository = FakeRepository()
    service = SurfaceCurationService(repository)

    approved = await service.approve_surface(
        project_id="project-1",
        document_id="document-1",
        surface_id="surface-1",
    )
    rejected = await service.reject_surface(
        project_id="project-1",
        document_id="document-1",
        surface_id="surface-2",
        reason="bad",
    )
    edited = await service.edit_surface(
        project_id="project-1",
        document_id="document-1",
        surface_id="surface-3",
        title=None,
        answer="edited answer",
        short_answer=None,
        question_variants=("q1",),
        retrieval_scope=None,
        exclusion_scope=None,
    )
    merged = await service.merge_facts(
        project_id="project-1",
        document_id="document-1",
        target_fact_id="fact-target",
        source_fact_ids=("fact-source",),
        reason="same",
    )
    deleted = await service.delete_fact(
        project_id="project-1",
        document_id="document-1",
        fact_id="fact-deleted",
        reason="manual",
    )
    published = await service.publish_selected_surfaces(
        project_id="project-1",
        document_id="document-1",
        surface_ids=("surface-4", "surface-5"),
    )

    assert approved.action == "approve_surface"
    assert rejected.action == "reject_surface"
    assert edited.action == "edit_surface"
    assert merged.action == "merge_facts"
    assert deleted.action == "delete_fact"
    assert published.action == "publish_selected_surfaces"
    assert published.affected_count == 2

    assert repository.calls == [
        "approve:surface-1",
        "reject:surface-2:bad",
        "edit:surface-3:edited answer",
        "merge:fact-target:fact-source",
        "delete:fact-deleted:manual",
        "publish:surface-4,surface-5",
    ]


@pytest.mark.asyncio
async def test_surface_curation_service_rejects_invalid_merge_and_empty_publish() -> (
    None
):
    service = SurfaceCurationService(FakeRepository())

    with pytest.raises(SurfaceCurationRejectedError, match="source_fact_ids"):
        await service.merge_facts(
            project_id="project-1",
            document_id="document-1",
            target_fact_id="fact-1",
            source_fact_ids=(),
            reason="",
        )

    with pytest.raises(SurfaceCurationRejectedError, match="source_fact_ids"):
        await service.merge_facts(
            project_id="project-1",
            document_id="document-1",
            target_fact_id="fact-1",
            source_fact_ids=("fact-1",),
            reason="",
        )

    with pytest.raises(SurfaceCurationRejectedError, match="surface_ids"):
        await service.publish_selected_surfaces(
            project_id="project-1",
            document_id="document-1",
            surface_ids=(),
        )
