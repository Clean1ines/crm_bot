from __future__ import annotations

from collections.abc import Mapping, MutableMapping, MutableSequence
from datetime import datetime, timedelta, timezone
from typing import cast

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
    JsonValue,
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


def _now() -> datetime:
    return datetime(2026, 6, 8, 12, 0, tzinfo=timezone.utc)


def _artifact() -> PipelineArtifact:
    now = _now()
    return PipelineArtifact(
        artifact_ref=ArtifactRef("artifact-1"),
        artifact_kind=ArtifactKind("generic.step_result"),
        payload=ArtifactPayload({"value": 1}),
        status=ArtifactStatus.STORED,
        visibility=ArtifactVisibility.INTERNAL,
        retention_policy=RetentionPolicy.temporary(),
        lineage=ArtifactLineage(),
        created_at=now,
        updated_at=now,
    )


def test_artifact_kind_is_caller_owned_lowercase_identifier() -> None:
    assert ArtifactKind("generic.step_result").value == "generic.step_result"

    with pytest.raises(ValueError):
        ArtifactKind("")

    with pytest.raises(ValueError):
        ArtifactKind("BadKind")

    with pytest.raises(ValueError):
        ArtifactKind("bad kind")


def test_artifact_payload_is_opaque_and_copied() -> None:
    source = {"value": 1}
    payload = ArtifactPayload(source)

    source["value"] = 2

    assert payload.value["value"] == 1

    with pytest.raises(TypeError):
        payload.value["new"] = 3


def test_artifact_lineage_rejects_duplicate_parent_refs() -> None:
    ref = ArtifactRef("parent-1")

    with pytest.raises(ValueError):
        ArtifactLineage((ref, ref))


def test_pipeline_artifact_requires_timezone_aware_timestamps() -> None:
    naive = datetime(2026, 6, 8, 12, 0)

    with pytest.raises(ValueError):
        PipelineArtifact(
            artifact_ref=ArtifactRef("artifact-1"),
            artifact_kind=ArtifactKind("generic.step_result"),
            payload=ArtifactPayload({}),
            status=ArtifactStatus.STORED,
            visibility=ArtifactVisibility.INTERNAL,
            retention_policy=RetentionPolicy.temporary(),
            lineage=ArtifactLineage(),
            created_at=naive,
            updated_at=naive,
        )


def test_pipeline_artifact_lifecycle_transitions_are_explicit() -> None:
    artifact = _artifact()

    validated = artifact.validate(updated_at=_now() + timedelta(seconds=1))
    assert validated.status is ArtifactStatus.VALIDATED

    rejected = artifact.reject(updated_at=_now() + timedelta(seconds=1))
    assert rejected.status is ArtifactStatus.REJECTED
    assert rejected.status.is_terminal

    superseded = artifact.supersede(updated_at=_now() + timedelta(seconds=1))
    assert superseded.status is ArtifactStatus.SUPERSEDED
    assert superseded.status.is_terminal

    expired = artifact.expire(updated_at=_now() + timedelta(seconds=1))
    assert expired.status is ArtifactStatus.EXPIRED
    assert expired.status.is_terminal


def test_terminal_artifact_cannot_transition_again() -> None:
    rejected = _artifact().reject(updated_at=_now() + timedelta(seconds=1))

    with pytest.raises(ValueError):
        rejected.validate(updated_at=_now() + timedelta(seconds=2))


def test_artifact_payload_accepts_nested_object() -> None:
    payload = ArtifactPayload(
        {
            "nested": {
                "level": {
                    "answer": 42,
                },
            },
        }
    )

    nested = payload.value["nested"]
    assert isinstance(nested, Mapping)
    nested_mapping = cast(Mapping[str, JsonValue], nested)

    level = nested_mapping["level"]
    assert isinstance(level, Mapping)
    level_mapping = cast(Mapping[str, JsonValue], level)

    assert level_mapping["answer"] == 42


def test_artifact_payload_accepts_array_of_objects_for_claims() -> None:
    payload = ArtifactPayload(
        {
            "claims": [
                {
                    "claim": "Product turns documents into knowledge.",
                    "granularity": "atomic",
                    "possible_questions": ["What does the product do?"],
                    "exclusion_scope": "",
                    "evidence_block": "turns documents into knowledge",
                }
            ],
        }
    )

    claims = payload.value["claims"]

    assert isinstance(claims, tuple)
    assert len(claims) == 1

    first_claim = claims[0]
    assert isinstance(first_claim, Mapping)
    first_claim_mapping = cast(Mapping[str, JsonValue], first_claim)

    assert first_claim_mapping["claim"] == "Product turns documents into knowledge."


def test_artifact_payload_converts_lists_to_tuples_recursively() -> None:
    payload = ArtifactPayload(
        {
            "claims": [
                {
                    "claim": "Claim.",
                    "possible_questions": ["Question one?", "Question two?"],
                }
            ],
        }
    )

    claims = payload.value["claims"]
    assert isinstance(claims, tuple)

    first_claim = claims[0]
    assert isinstance(first_claim, Mapping)
    first_claim_mapping = cast(Mapping[str, JsonValue], first_claim)

    possible_questions = first_claim_mapping["possible_questions"]
    assert possible_questions == ("Question one?", "Question two?")


def test_artifact_payload_nested_mapping_is_immutable() -> None:
    payload = ArtifactPayload({"nested": {"value": 1}})

    nested = payload.value["nested"]
    assert isinstance(nested, Mapping)

    with pytest.raises(TypeError):
        cast(MutableMapping[str, JsonValue], nested)["value"] = "changed"


def test_artifact_payload_nested_array_is_immutable_tuple() -> None:
    payload = ArtifactPayload({"values": [1, 2, 3]})

    values = payload.value["values"]

    assert isinstance(values, tuple)
    assert values == (1, 2, 3)

    with pytest.raises(TypeError):
        cast(MutableSequence[JsonValue], values)[0] = "changed"


def test_artifact_payload_rejects_unsupported_values() -> None:
    unsupported_payload = cast(Mapping[str, JsonInputValue], {"value": object()})

    with pytest.raises(ValueError):
        ArtifactPayload(unsupported_payload)
