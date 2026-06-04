from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

from src.domain.project_plane.knowledge_workbench import DomainInvariantError


class SurfaceCurationRejectedError(DomainInvariantError):
    pass


class SurfaceCurationRepositoryPort(Protocol):
    async def approve_surface(
        self,
        *,
        project_id: str,
        document_id: str,
        surface_id: str,
    ) -> Mapping[str, object]: ...

    async def reject_surface(
        self,
        *,
        project_id: str,
        document_id: str,
        surface_id: str,
        reason: str,
    ) -> Mapping[str, object]: ...

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
    ) -> Mapping[str, object]: ...

    async def merge_facts(
        self,
        *,
        project_id: str,
        document_id: str,
        target_fact_id: str,
        source_fact_ids: tuple[str, ...],
        reason: str,
    ) -> Mapping[str, object]: ...

    async def delete_fact(
        self,
        *,
        project_id: str,
        document_id: str,
        fact_id: str,
        reason: str,
    ) -> Mapping[str, object]: ...

    async def publish_selected_surfaces(
        self,
        *,
        project_id: str,
        document_id: str,
        surface_ids: tuple[str, ...],
    ) -> Mapping[str, object]: ...


@dataclass(frozen=True, slots=True)
class SurfaceCurationResult:
    project_id: str
    document_id: str
    action: str
    affected_count: int
    item: Mapping[str, object] | None = None
    items: Sequence[Mapping[str, object]] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "project_id": self.project_id,
            "document_id": self.document_id,
            "action": self.action,
            "affected_count": self.affected_count,
            "item": dict(self.item) if self.item is not None else None,
            "items": [dict(item) for item in self.items],
        }


class SurfaceCurationService:
    def __init__(self, repository: SurfaceCurationRepositoryPort) -> None:
        self._repository = repository

    async def approve_surface(
        self,
        *,
        project_id: str,
        document_id: str,
        surface_id: str,
    ) -> SurfaceCurationResult:
        item = await self._repository.approve_surface(
            project_id=_required(project_id, "project_id"),
            document_id=_required(document_id, "document_id"),
            surface_id=_required(surface_id, "surface_id"),
        )
        return SurfaceCurationResult(
            project_id=project_id,
            document_id=document_id,
            action="approve_surface",
            affected_count=1,
            item=item,
        )

    async def reject_surface(
        self,
        *,
        project_id: str,
        document_id: str,
        surface_id: str,
        reason: str,
    ) -> SurfaceCurationResult:
        item = await self._repository.reject_surface(
            project_id=_required(project_id, "project_id"),
            document_id=_required(document_id, "document_id"),
            surface_id=_required(surface_id, "surface_id"),
            reason=reason.strip(),
        )
        return SurfaceCurationResult(
            project_id=project_id,
            document_id=document_id,
            action="reject_surface",
            affected_count=1,
            item=item,
        )

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
    ) -> SurfaceCurationResult:
        item = await self._repository.edit_surface(
            project_id=_required(project_id, "project_id"),
            document_id=_required(document_id, "document_id"),
            surface_id=_required(surface_id, "surface_id"),
            title=_optional_clean(title),
            answer=_optional_clean(answer),
            short_answer=_optional_clean(short_answer),
            question_variants=question_variants,
            retrieval_scope=_optional_clean(retrieval_scope),
            exclusion_scope=_optional_clean(exclusion_scope),
        )
        return SurfaceCurationResult(
            project_id=project_id,
            document_id=document_id,
            action="edit_surface",
            affected_count=1,
            item=item,
        )

    async def merge_facts(
        self,
        *,
        project_id: str,
        document_id: str,
        target_fact_id: str,
        source_fact_ids: tuple[str, ...],
        reason: str,
    ) -> SurfaceCurationResult:
        cleaned_sources = tuple(
            dict.fromkeys(item.strip() for item in source_fact_ids if item.strip())
        )
        target = _required(target_fact_id, "target_fact_id")
        if not cleaned_sources:
            raise SurfaceCurationRejectedError("source_fact_ids must not be empty")
        if target in cleaned_sources:
            raise SurfaceCurationRejectedError(
                "source_fact_ids must not include target_fact_id"
            )

        item = await self._repository.merge_facts(
            project_id=_required(project_id, "project_id"),
            document_id=_required(document_id, "document_id"),
            target_fact_id=target,
            source_fact_ids=cleaned_sources,
            reason=reason.strip(),
        )
        return SurfaceCurationResult(
            project_id=project_id,
            document_id=document_id,
            action="merge_facts",
            affected_count=len(cleaned_sources) + 1,
            item=item,
        )

    async def delete_fact(
        self,
        *,
        project_id: str,
        document_id: str,
        fact_id: str,
        reason: str,
    ) -> SurfaceCurationResult:
        item = await self._repository.delete_fact(
            project_id=_required(project_id, "project_id"),
            document_id=_required(document_id, "document_id"),
            fact_id=_required(fact_id, "fact_id"),
            reason=reason.strip(),
        )
        return SurfaceCurationResult(
            project_id=project_id,
            document_id=document_id,
            action="delete_fact",
            affected_count=1,
            item=item,
        )

    async def publish_selected_surfaces(
        self,
        *,
        project_id: str,
        document_id: str,
        surface_ids: tuple[str, ...],
    ) -> SurfaceCurationResult:
        cleaned_surface_ids = tuple(
            dict.fromkeys(item.strip() for item in surface_ids if item.strip())
        )
        if not cleaned_surface_ids:
            raise SurfaceCurationRejectedError("surface_ids must not be empty")

        result = await self._repository.publish_selected_surfaces(
            project_id=_required(project_id, "project_id"),
            document_id=_required(document_id, "document_id"),
            surface_ids=cleaned_surface_ids,
        )
        items_raw = result.get("items")
        items: Sequence[Mapping[str, object]]
        if isinstance(items_raw, Sequence) and not isinstance(items_raw, (str, bytes)):
            items = tuple(item for item in items_raw if isinstance(item, Mapping))
        else:
            items = ()

        return SurfaceCurationResult(
            project_id=project_id,
            document_id=document_id,
            action="publish_selected_surfaces",
            affected_count=len(items),
            items=items,
        )


def _required(value: str, name: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise SurfaceCurationRejectedError(f"{name} is required")
    return cleaned


def _optional_clean(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned if cleaned else None


__all__ = [
    "SurfaceCurationRejectedError",
    "SurfaceCurationRepositoryPort",
    "SurfaceCurationResult",
    "SurfaceCurationService",
]
