from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime

from src.contexts.artifact_runtime.domain.entities.pipeline_artifact import (
    PipelineArtifact,
)
from src.contexts.artifact_runtime.domain.value_objects.artifact_kind import (
    ArtifactKind,
)
from src.contexts.artifact_runtime.domain.value_objects.artifact_payload import (
    JsonInputValue,
)
from src.contexts.knowledge_workbench.consolidation.domain.surfaces.entities.consolidated_surface import (
    ConsolidatedSurface,
)
from src.contexts.knowledge_workbench.consolidation.domain.surfaces.value_objects.canonical_intent import (
    CanonicalIntent,
)
from src.contexts.knowledge_workbench.consolidation.domain.surfaces.value_objects.consolidated_surface_ref import (
    ConsolidatedSurfaceRef,
)
from src.contexts.knowledge_workbench.consolidation.domain.surfaces.value_objects.ontology_tag import (
    OntologyTag,
)
from src.contexts.knowledge_workbench.consolidation.domain.surfaces.value_objects.surface_evidence_ref import (
    SurfaceEvidenceRef,
)
from src.contexts.knowledge_workbench.consolidation.domain.surfaces.value_objects.surface_kind import (
    SurfaceKind,
)
from src.contexts.knowledge_workbench.consolidation.domain.surfaces.value_objects.surface_relation import (
    SurfaceRelation,
)
from src.contexts.knowledge_workbench.extraction.domain.value_objects.draft_claim_observation_ref import (
    DraftClaimObservationRef,
)


EXPECTED_CONSOLIDATION_OUTPUT_ARTIFACT_KIND = ArtifactKind(
    "knowledge_workbench.consolidation.parsed"
)
_TOP_LEVEL_FIELDS = frozenset({"surfaces"})
_SURFACE_FIELDS = frozenset(
    {
        "canonical_intent",
        "answer",
        "surface_kind",
        "source_observation_refs",
        "evidence_refs",
        "ontology_tags",
        "relations",
    }
)
_RELATION_FIELDS = frozenset({"relation_kind", "target_surface_ref"})


class InvalidConsolidationOutputArtifact(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ConsolidationOutputArtifactParserInput:
    artifact: PipelineArtifact
    created_at: datetime

    def __post_init__(self) -> None:
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise ValueError("created_at must be timezone-aware")


class ConsolidationOutputArtifactParser:
    """Parse Prompt C parsed artifact into pre-publication consolidated surfaces.

    Empty surfaces are allowed because consolidation may legitimately decide that
    a cluster/subcluster contains no publishable surface after deduplication.
    """

    def parse(
        self,
        input: ConsolidationOutputArtifactParserInput,
    ) -> tuple[ConsolidatedSurface, ...]:
        artifact = input.artifact

        if artifact.artifact_kind != EXPECTED_CONSOLIDATION_OUTPUT_ARTIFACT_KIND:
            raise InvalidConsolidationOutputArtifact("wrong artifact kind")

        payload = artifact.payload.value
        if set(payload.keys()) != _TOP_LEVEL_FIELDS:
            raise InvalidConsolidationOutputArtifact(
                "payload must contain exactly the surfaces field"
            )

        surfaces_value = payload["surfaces"]
        if not isinstance(surfaces_value, (list, tuple)):
            raise InvalidConsolidationOutputArtifact("surfaces must be a list or tuple")

        return tuple(
            self._build_surface(
                artifact=artifact,
                surface_value=surface_value,
                index=index,
                created_at=input.created_at,
            )
            for index, surface_value in enumerate(surfaces_value)
        )

    def _build_surface(
        self,
        *,
        artifact: PipelineArtifact,
        surface_value: JsonInputValue,
        index: int,
        created_at: datetime,
    ) -> ConsolidatedSurface:
        surface_mapping = self._surface_mapping(surface_value)

        try:
            return ConsolidatedSurface(
                surface_ref=ConsolidatedSurfaceRef(
                    f"{artifact.artifact_ref.value}:surface:{index}"
                ),
                canonical_intent=CanonicalIntent(
                    self._required_string(surface_mapping, "canonical_intent")
                ),
                answer=self._required_string(surface_mapping, "answer"),
                surface_kind=self._surface_kind(surface_mapping),
                source_observation_refs=self._draft_claim_refs(
                    surface_mapping,
                    "source_observation_refs",
                ),
                evidence_refs=self._evidence_refs(surface_mapping),
                ontology_tags=self._ontology_tags(surface_mapping),
                relations=self._relations(surface_mapping),
                created_at=created_at,
            )
        except ValueError as exc:
            raise InvalidConsolidationOutputArtifact(str(exc)) from exc

    def _surface_mapping(
        self,
        surface_value: JsonInputValue,
    ) -> Mapping[str, JsonInputValue]:
        if not isinstance(surface_value, Mapping):
            raise InvalidConsolidationOutputArtifact("surface item must be an object")

        if set(surface_value.keys()) != _SURFACE_FIELDS:
            raise InvalidConsolidationOutputArtifact(
                "surface object must contain exactly consolidation surface fields"
            )

        for field_name, field_value in surface_value.items():
            if field_value is None:
                raise InvalidConsolidationOutputArtifact(
                    f"surface field {field_name} must not be null"
                )

        return surface_value

    def _required_string(
        self,
        surface_mapping: Mapping[str, JsonInputValue],
        field_name: str,
    ) -> str:
        value = surface_mapping[field_name]
        if not isinstance(value, str):
            raise InvalidConsolidationOutputArtifact(
                f"surface field {field_name} must be a string"
            )
        return value

    def _surface_kind(
        self,
        surface_mapping: Mapping[str, JsonInputValue],
    ) -> SurfaceKind:
        value = self._required_string(surface_mapping, "surface_kind")
        try:
            return SurfaceKind(value)
        except ValueError as exc:
            raise InvalidConsolidationOutputArtifact(
                f"invalid surface_kind: {value}"
            ) from exc

    def _string_sequence(
        self,
        surface_mapping: Mapping[str, JsonInputValue],
        field_name: str,
    ) -> tuple[str, ...]:
        value = surface_mapping[field_name]
        if not isinstance(value, (list, tuple)):
            raise InvalidConsolidationOutputArtifact(
                f"surface field {field_name} must be a list or tuple"
            )

        strings: list[str] = []
        for item in value:
            if not isinstance(item, str):
                raise InvalidConsolidationOutputArtifact(
                    f"surface field {field_name} must contain only strings"
                )
            strings.append(item)

        return tuple(strings)

    def _draft_claim_refs(
        self,
        surface_mapping: Mapping[str, JsonInputValue],
        field_name: str,
    ) -> tuple[DraftClaimObservationRef, ...]:
        return tuple(
            DraftClaimObservationRef(value)
            for value in self._string_sequence(surface_mapping, field_name)
        )

    def _evidence_refs(
        self,
        surface_mapping: Mapping[str, JsonInputValue],
    ) -> tuple[SurfaceEvidenceRef, ...]:
        return tuple(
            SurfaceEvidenceRef(value)
            for value in self._string_sequence(surface_mapping, "evidence_refs")
        )

    def _ontology_tags(
        self,
        surface_mapping: Mapping[str, JsonInputValue],
    ) -> tuple[OntologyTag, ...]:
        return tuple(
            OntologyTag(value)
            for value in self._string_sequence(surface_mapping, "ontology_tags")
        )

    def _relations(
        self,
        surface_mapping: Mapping[str, JsonInputValue],
    ) -> tuple[SurfaceRelation, ...]:
        value = surface_mapping["relations"]
        if not isinstance(value, (list, tuple)):
            raise InvalidConsolidationOutputArtifact(
                "surface field relations must be a list or tuple"
            )

        relations: list[SurfaceRelation] = []
        for relation_value in value:
            if not isinstance(relation_value, Mapping):
                raise InvalidConsolidationOutputArtifact(
                    "relation item must be an object"
                )
            if set(relation_value.keys()) != _RELATION_FIELDS:
                raise InvalidConsolidationOutputArtifact(
                    "relation object must contain exactly relation_kind and target_surface_ref"
                )

            relation_kind = relation_value["relation_kind"]
            target_surface_ref = relation_value["target_surface_ref"]
            if not isinstance(relation_kind, str) or not isinstance(
                target_surface_ref,
                str,
            ):
                raise InvalidConsolidationOutputArtifact(
                    "relation fields must be strings"
                )

            relations.append(
                SurfaceRelation(
                    relation_kind=relation_kind,
                    target_surface_ref=ConsolidatedSurfaceRef(target_surface_ref),
                )
            )

        return tuple(relations)
