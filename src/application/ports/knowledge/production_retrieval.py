from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Protocol

from src.domain.project_plane.production_retrieval import (
    ProductionRetrievalCaller,
    ProductionRetrievalMode,
    ProductionRetrievalPolicy,
    resolve_production_retrieval_policy,
)


@dataclass(frozen=True, slots=True)
class ProductionRetrievalRequest:
    project_id: str
    query: str
    caller: ProductionRetrievalCaller
    limit: int = 5
    document_id: str | None = None
    mode: ProductionRetrievalMode | None = None
    include_diagnostics: bool = False

    @property
    def policy(self) -> ProductionRetrievalPolicy:
        resolved = resolve_production_retrieval_policy(self.caller)
        if self.mode is None or self.mode == resolved.mode:
            return resolved
        return ProductionRetrievalPolicy(
            caller=self.caller,
            mode=self.mode,
            runtime_equivalent=False,
            production_safe=False,
            diagnostic=True,
            source_name="diagnostic_override",
            reason="explicit request mode override is diagnostic-only",
        )


@dataclass(frozen=True, slots=True)
class ProductionRetrievalResultItem:
    id: str
    document_id: str
    title: str
    answer: str
    score: float
    surface_id: str | None = None
    short_answer: str = ""
    source_refs: tuple[str, ...] = ()
    metadata: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ProductionRetrievalResult:
    request: ProductionRetrievalRequest
    items: Sequence[ProductionRetrievalResultItem]
    policy: ProductionRetrievalPolicy
    diagnostics: Mapping[str, object] = field(default_factory=dict)


class ProductionRetrievalPort(Protocol):
    async def retrieve(
        self,
        request: ProductionRetrievalRequest,
    ) -> ProductionRetrievalResult:
        """Retrieve project knowledge through the explicit production retrieval path."""


__all__ = (
    "ProductionRetrievalPort",
    "ProductionRetrievalRequest",
    "ProductionRetrievalResult",
    "ProductionRetrievalResultItem",
)
