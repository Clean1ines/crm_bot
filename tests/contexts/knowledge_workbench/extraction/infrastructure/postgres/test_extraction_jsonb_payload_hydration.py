from __future__ import annotations

import pytest

from src.contexts.knowledge_workbench.extraction.infrastructure.postgres.jsonb_payload_hydration import (
    hydrate_jsonb_object_payload,
)


def test_hydrates_mapping_as_plain_dict() -> None:
    payload = hydrate_jsonb_object_payload(
        {"retry_action": "retry"},
        field_name="claim_builder_retry_actions.payload",
    )

    assert dict(payload) == {"retry_action": "retry"}


def test_hydrates_json_object_string_as_plain_dict() -> None:
    payload = hydrate_jsonb_object_payload(
        '{"retry_action":"retry"}',
        field_name="claim_builder_retry_actions.payload",
    )

    assert dict(payload) == {"retry_action": "retry"}


def test_rejects_invalid_json_string_with_field_name() -> None:
    with pytest.raises(
        ValueError,
        match=(
            "claim_builder_retry_actions.payload must be JSON object Mapping; "
            "got invalid JSON str"
        ),
    ):
        hydrate_jsonb_object_payload(
            "not json",
            field_name="claim_builder_retry_actions.payload",
        )


def test_rejects_json_array_string_with_field_name_and_decoded_type() -> None:
    with pytest.raises(
        TypeError,
        match=(
            "claim_builder_retry_actions.payload must be JSON object Mapping; "
            "got str that decoded to list"
        ),
    ):
        hydrate_jsonb_object_payload(
            '["retry"]',
            field_name="claim_builder_retry_actions.payload",
        )


def test_rejects_none_for_required_payload() -> None:
    with pytest.raises(
        TypeError,
        match=(
            "claim_builder_retry_actions.payload must be JSON object Mapping; "
            "got NoneType"
        ),
    ):
        hydrate_jsonb_object_payload(
            None,
            field_name="claim_builder_retry_actions.payload",
        )
