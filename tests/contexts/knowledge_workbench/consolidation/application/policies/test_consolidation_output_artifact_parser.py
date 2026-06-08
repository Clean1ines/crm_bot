from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.contexts.artifact_runtime.domain.entities.pipeline_artifact import (
    PipelineArtifact,
)
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
from src.contexts.knowledge_workbench.consolidation.application.policies.consolidation_output_artifact_parser import (
    EXPECTED_CONSOLIDATION_OUTPUT_ARTIFACT_KIND,
    ConsolidationOutputArtifactParser,
    ConsolidationOutputArtifactParserInput,
    InvalidConsolidationOutputArtifact,
)
from src.contexts.knowledge_workbench.consolidation.domain.surfaces.value_objects.surface_kind import (
    SurfaceKind,
)


ROOT = Path(__file__).resolve().parents[6]
PARSER_FILE = (
    ROOT
    / "src"
    / "contexts"
    / "knowledge_workbench"
    / "consolidation"
    / "application"
    / "policies"
    / "consolidation_output_artifact_parser.py"
)


def _now() -> datetime:
    return datetime(2026, 6, 8, 12, 0, tzinfo=timezone.utc)


def _surface_payload(
    *,
    canonical_intent: JsonInputValue = "What is the product?",
    answer: JsonInputValue = "The product turns documents into knowledge.",
    surface_kind: JsonInputValue = "definition",
    source_observation_refs: JsonInputValue = ("draft-claim-1",),
    evidence_refs: JsonInputValue = ("draft-claim-1:evidence",),
    ontology_tags: JsonInputValue = ("product",),
    relations: JsonInputValue = (),
) -> dict[str, JsonInputValue]:
    return {
        "canonical_intent": canonical_intent,
        "answer": answer,
        "surface_kind": surface_kind,
        "source_observation_refs": source_observation_refs,
        "evidence_refs": evidence_refs,
        "ontology_tags": ontology_tags,
        "relations": relations,
    }


def _artifact(
    payload: dict[str, JsonInputValue],
    *,
    artifact_kind: ArtifactKind = EXPECTED_CONSOLIDATION_OUTPUT_ARTIFACT_KIND,
    artifact_ref: ArtifactRef = ArtifactRef("consolidation-artifact-1"),
) -> PipelineArtifact:
    return PipelineArtifact(
        artifact_ref=artifact_ref,
        artifact_kind=artifact_kind,
        payload=ArtifactPayload(payload),
        status=ArtifactStatus.VALIDATED,
        visibility=ArtifactVisibility.INTERNAL,
        retention_policy=RetentionPolicy.temporary(),
        lineage=ArtifactLineage(),
        created_at=_now(),
        updated_at=_now(),
    )


def _parse(
    payload: dict[str, JsonInputValue],
    *,
    artifact_kind: ArtifactKind = EXPECTED_CONSOLIDATION_OUTPUT_ARTIFACT_KIND,
    artifact_ref: ArtifactRef = ArtifactRef("consolidation-artifact-1"),
    created_at: datetime | None = None,
):
    return ConsolidationOutputArtifactParser().parse(
        ConsolidationOutputArtifactParserInput(
            artifact=_artifact(
                payload,
                artifact_kind=artifact_kind,
                artifact_ref=artifact_ref,
            ),
            created_at=created_at or _now(),
        )
    )


def test_parses_one_surface() -> None:
    surfaces = _parse({"surfaces": [_surface_payload()]})

    assert len(surfaces) == 1
    surface = surfaces[0]
    assert surface.surface_ref.value == "consolidation-artifact-1:surface:0"
    assert surface.canonical_intent.value == "What is the product?"
    assert surface.answer == "The product turns documents into knowledge."
    assert surface.surface_kind is SurfaceKind.DEFINITION
    assert tuple(ref.value for ref in surface.source_observation_refs) == (
        "draft-claim-1",
    )
    assert tuple(ref.value for ref in surface.evidence_refs) == (
        "draft-claim-1:evidence",
    )
    assert tuple(tag.value for tag in surface.ontology_tags) == ("product",)


def test_parses_multiple_surfaces() -> None:
    surfaces = _parse(
        {
            "surfaces": [
                _surface_payload(canonical_intent="First?"),
                _surface_payload(canonical_intent="Second?"),
            ]
        }
    )

    assert tuple(surface.canonical_intent.value for surface in surfaces) == (
        "First?",
        "Second?",
    )
    assert tuple(surface.surface_ref.value for surface in surfaces) == (
        "consolidation-artifact-1:surface:0",
        "consolidation-artifact-1:surface:1",
    )


def test_empty_surfaces_are_allowed() -> None:
    assert _parse({"surfaces": []}) == ()


def test_invalid_surface_kind_rejected() -> None:
    with pytest.raises(InvalidConsolidationOutputArtifact):
        _parse({"surfaces": [_surface_payload(surface_kind="unknown")]})


def test_missing_source_observation_refs_rejected() -> None:
    payload = _surface_payload()
    del payload["source_observation_refs"]

    with pytest.raises(InvalidConsolidationOutputArtifact):
        _parse({"surfaces": [payload]})


def test_empty_source_observation_refs_rejected_by_surface_domain() -> None:
    with pytest.raises(InvalidConsolidationOutputArtifact):
        _parse({"surfaces": [_surface_payload(source_observation_refs=[])]})


def test_wrong_artifact_kind_rejected() -> None:
    with pytest.raises(InvalidConsolidationOutputArtifact):
        _parse(
            {"surfaces": []},
            artifact_kind=ArtifactKind("knowledge_workbench.other.parsed"),
        )


def test_missing_surfaces_rejected() -> None:
    with pytest.raises(InvalidConsolidationOutputArtifact):
        _parse({})


def test_extra_top_level_field_rejected() -> None:
    with pytest.raises(InvalidConsolidationOutputArtifact):
        _parse({"surfaces": [], "extra": True})


def test_extra_surface_field_rejected() -> None:
    payload = _surface_payload()
    payload["extra"] = "not allowed"

    with pytest.raises(InvalidConsolidationOutputArtifact):
        _parse({"surfaces": [payload]})


def test_relation_objects_are_parsed() -> None:
    surfaces = _parse(
        {
            "surfaces": [
                _surface_payload(
                    relations=(
                        {
                            "relation_kind": "supports",
                            "target_surface_ref": "surface-2",
                        },
                    )
                )
            ]
        }
    )

    assert len(surfaces[0].relations) == 1
    assert surfaces[0].relations[0].relation_kind == "supports"
    assert surfaces[0].relations[0].target_surface_ref.value == "surface-2"


def test_invalid_relation_rejected() -> None:
    with pytest.raises(InvalidConsolidationOutputArtifact):
        _parse(
            {
                "surfaces": [
                    _surface_payload(
                        relations=(
                            {
                                "relation_kind": "supports",
                                "target_surface_ref": "surface-2",
                                "extra": "not allowed",
                            },
                        )
                    )
                ]
            }
        )


def test_naive_created_at_rejected() -> None:
    with pytest.raises(ValueError):
        _parse({"surfaces": []}, created_at=datetime(2026, 6, 8, 12, 0))


def test_parser_has_no_groq_db_or_draft_prompt_a_imports() -> None:
    text = PARSER_FILE.read_text(encoding="utf-8")

    forbidden_markers = (
        "Groq",
        "groq",
        "Qwen",
        "qwen",
        "Postgres",
        "postgres",
        "DraftClaimObservationArtifactParser",
        "draft_claim_observation_artifact_parser",
        "Prompt A",
        "faq_claim_observations",
        ".commit(",
        ".rollback(",
    )

    offenders = [marker for marker in forbidden_markers if marker in text]

    assert not offenders
